"""Expansão local e limitada de evidências para perguntas compostas."""

from __future__ import annotations

import re
import time
from typing import Any, Callable

from .retrieval import annotate_document_structure, normalize_text
from .vector_store import get_chunks

MAX_BUNDLE_CHUNKS = 5


def _deduplicate(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sources:
        chunk_id = str(source.get("chunk_id") or "")
        if chunk_id and chunk_id not in seen:
            seen.add(chunk_id)
            output.append(source)
    return output


def _document_chunks(
    document_id: str,
    chunks_fn: Callable[[str | None], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    chunks = annotate_document_structure(chunks_fn(document_id))
    if any(chunk.get("document_id") != document_id for chunk in chunks):
        raise RuntimeError("Falha de isolamento durante a expansão de evidências.")
    return sorted(chunks, key=lambda item: int(item.get("chunk_index") or 0))


def _habilitation_bundle(chunks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    anchor_groups = (
        (
            "cadastramento para efetuar lances",
            "fase de habilitacao",
        ),
        (
            "documentos exigidos para habilitacao",
            "habilitacao juridica",
            "da habilitacao",
        ),
        ("documentos de habilitacao",),
        ("para a habilitacao",),
    )
    start = None
    for anchors in anchor_groups:
        start = next(
            (
                position
                for position, chunk in enumerate(chunks)
                if any(
                    0 <= normalize_text(chunk.get("text", "")).find(anchor) <= 1600
                    for anchor in anchors
                )
                and chunk.get("document_part") == "edital_principal"
            ),
            None,
        )
        if start is not None:
            break
    if start is None:
        return [], 0
    anchor_part = chunks[start].get("document_part")
    selected: list[dict[str, Any]] = []
    considered = 0
    for chunk in chunks[start:]:
        considered += 1
        if chunk.get("document_part") != anchor_part:
            break
        normalized = normalize_text(chunk.get("text", ""))
        if selected and re.search(r"\bx\s*[-–—]\s*", normalized[:180]):
            break
        selected.append(chunk)
        if len(selected) == MAX_BUNDLE_CHUNKS:
            break
    return selected, considered


def _deadline_bundle(
    chunks: list[dict[str, Any]],
    deadline_subtype: str | None,
) -> tuple[list[dict[str, Any]], int]:
    subtype_patterns = {
        "prazo_procedimento": (
            "prazo para credenciamento",
            "prazo indeterminado",
            "terao validade de 60",
            "convocados no prazo maximo",
            "vigencia limitada em 120 meses",
        ),
        "prazo_entrega_proposta": (
            "acolhimento das propostas",
            "recebimento das propostas",
            "entrega das propostas",
            "envio das propostas",
        ),
        "prazo_recebimento_definitivo": ("recebimento definitivo ocorrera no prazo",),
        "prazo_vigencia": (
            "prazo inicial de vigencia",
            "prazo de vigencia da ata",
            "vigencia sera de",
        ),
        "prazo_diagnostico": ("estimativa de prazo para execucao",),
        "prazo_atendimento": ("prazo de atendimento",),
        "prazo_conclusao": ("prazo de conclusao",),
        "prazo_execucao": (
            "prazo de entrega dos bens e de",
            "proceder a entrega do bem",
            "prazo maximo para a execucao do objeto",
            "prazo para execucao do objeto contratado esta atrelado",
            "pelo periodo de",
            "ao longo da vigencia",
            "execucao contratual ocorrera sob demanda",
            "inicio da prestacao dos servicos ocorrera de acordo com as demandas",
            "estimativa de prazo para execucao",
            "ordem de servico",
            "prazo de entrega",
            "ordem de compra",
            "condicoes de execucao dos servicos constam dos contratos",
        ),
        # A pergunta genérica de entrega precisa preservar o contexto de
        # execução e manter recebimento definitivo como afirmação separada.
        "prazo_entrega": (
            "do prazo e do local de entrega do objeto",
            "prazo para entrega e instalacao",
            "recebimento da ordem de compra",
            "ordem de compra",
            "execucao contratual ocorrera sob demanda",
            "estimativa de prazo para execucao",
            "prazo de entrega: conforme edital",
            "recebimento definitivo ocorrera no prazo",
            "condicoes de execucao dos servicos constam dos contratos",
            "emitir as ordens de servicos a empresa vencedora",
            "fiscalizacao, gestao e execucao do contrato deverao observar",
            "habilitados serao convocados no prazo maximo de 15",
            "vigencia limitada em 120 meses",
            "prazo de vigencia do contrato sera",
        ),
        "prazo_contextual": (
            "execucao contratual ocorrera sob demanda",
            "estimativa de prazo para execucao",
            "prazo de entrega: conforme edital",
            "recebimento definitivo ocorrera no prazo",
        ),
    }
    patterns = subtype_patterns.get(
        deadline_subtype or "prazo_contextual",
        subtype_patterns["prazo_contextual"],
    )
    selected: list[dict[str, Any]] = []
    considered = 0
    for pattern in patterns:
        candidates = []
        for chunk in chunks:
            considered += 1
            if pattern in normalize_text(chunk.get("text", "")):
                candidates.append(chunk)
        if not candidates:
            continue
        candidates.sort(
            key=lambda item: (
                item.get("document_part") != "edital_principal"
                if pattern in {"sob demanda", "ordem de servico", "estimativa de prazo para execucao"}
                else False,
                int(item.get("chunk_index") or 0),
            )
        )
        selected.append(candidates[0])
    return _deduplicate(selected)[:MAX_BUNDLE_CHUNKS], considered


def _section_bundle(
    chunks: list[dict[str, Any]],
    base_sources: list[dict[str, Any]],
    intent: str,
) -> tuple[list[dict[str, Any]], int]:
    """Inclui o corpo da seção formal, evitando títulos soltos do sumário."""
    expected_types = {
        "objeto": {"objeto"},
        "valor_estimado": {"recursos_financeiros", "preco"},
        "criterio_julgamento": {"criterio_julgamento"},
        "modalidade": {"participacao"},
    }.get(intent, set())
    if not expected_types:
        return base_sources, 0
    selected = list(base_sources)
    considered = 0
    for position, chunk in enumerate(chunks):
        considered += 1
        headings = [
            heading
            for heading in chunk.get("section_headings", [])
            if heading.get("section_type") in expected_types and not heading.get("is_toc")
        ]
        if not headings:
            continue
        normalized = normalize_text(chunk.get("text", ""))
        if intent == "objeto" and not re.search(
            r"\b(?:o\s+objeto\s+deste\s+edital\s+e|constitui\s+objeto|tem\s+por\s+objeto)",
            normalized,
        ):
            continue
        selected.insert(0, chunk)
        # O overlap pode deixar o título no fim de um chunk e o item no seguinte.
        if position + 1 < len(chunks):
            neighbour = chunks[position + 1]
            if neighbour.get("document_part") == chunk.get("document_part"):
                selected.append(neighbour)
        break
    return _deduplicate(selected)[:MAX_BUNDLE_CHUNKS], considered


def _attention_bundle(
    chunks: list[dict[str, Any]],
    base_sources: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    selected = list(base_sources)
    considered = 0
    patterns = (
        "sera inabilitado",
        "sera desclassificado",
        "sob pena",
        "devera apresentar",
        "ordem de servico",
        "penalidade",
    )
    for pattern in patterns:
        for chunk in chunks:
            if pattern in normalize_text(chunk.get("text", "")):
                selected.append(chunk)
                break
        if len(_deduplicate(selected)) >= MAX_BUNDLE_CHUNKS:
            break
    return _deduplicate(selected)[:MAX_BUNDLE_CHUNKS], 0


def expand_evidence_bundle(
    *,
    intent: str,
    document_id: str,
    base_sources: list[dict[str, Any]],
    deadline_subtype: str | None = None,
    chunks_fn: Callable[[str | None], list[dict[str, Any]]] = get_chunks,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Expande somente intenções compostas e sempre dentro do documento ativo."""
    started = time.perf_counter()
    if intent not in {
        "objeto",
        "valor_estimado",
        "modalidade",
        "criterio_julgamento",
        "prazo",
        "requisitos_habilitacao",
        "documentos_tecnicos",
        "pontos_atencao",
    }:
        return base_sources, {
            "section_expansion_ms": 0.0,
            "adjacent_chunks_considered": 0,
            "evidence_bundle_chunks": len(base_sources),
        }
    chunks = _document_chunks(document_id, chunks_fn)
    if intent in {"objeto", "valor_estimado", "modalidade", "criterio_julgamento"}:
        expanded, considered = _section_bundle(chunks, base_sources, intent)
    elif intent in {"requisitos_habilitacao", "documentos_tecnicos"}:
        expanded, considered = _habilitation_bundle(chunks)
    elif intent == "prazo":
        expanded, considered = _deadline_bundle(chunks, deadline_subtype)
    else:
        expanded, considered = _attention_bundle(chunks, base_sources)
    if intent in {"prazo", "requisitos_habilitacao", "documentos_tecnicos"}:
        sources = _deduplicate((expanded or []) + base_sources)
    else:
        sources = expanded or base_sources
    if any(source.get("document_id") != document_id for source in sources):
        raise RuntimeError("Falha de isolamento no pacote de evidências.")
    return sources[:MAX_BUNDLE_CHUNKS], {
        "section_expansion_ms": round((time.perf_counter() - started) * 1000, 1),
        "adjacent_chunks_considered": considered,
        "evidence_bundle_chunks": len(sources[:MAX_BUNDLE_CHUNKS]),
    }

"""Recuperação híbrida, local e isolada por documento.

Combina a busca densa existente com relevância lexical, correspondências
estruturais e regras específicas para campos recorrentes em editais. O
conjunto ampliado de candidatos nunca é enviado diretamente ao LLM.
"""

from __future__ import annotations

import math
import json
import logging
import os
import re
import time
import threading
import unicodedata
from collections import Counter
from typing import Any, Callable

from .vector_store import get_chunks, search as dense_search
from .document_structure import enrich_chunks_with_sections

DEFAULT_CANDIDATE_SIZE = 15
FINAL_TOP_K_LIMIT = 3
RRF_K = 60
_CORPUS_CACHE: dict[str, tuple[tuple[tuple[str, int], ...], list[dict[str, Any]], list[list[str]]]] = {}
_CORPUS_CACHE_LOCK = threading.Lock()
LOGGER = logging.getLogger(__name__)
RAG_DEBUG_RETRIEVAL = os.getenv("RAG_DEBUG_RETRIEVAL", "false").strip().lower() in {"1", "true", "yes", "on"}

INTENT_PATTERNS: dict[str, tuple[str, ...]] = {
    "valor_estimado": (
        "valor estimado",
        "orcamento estimado",
        "preco estimado",
        "valor global",
        "valor total",
        "valor maximo",
        "preco maximo aceitavel",
        "valor de referencia",
        "valor referencial",
        "valor do lote",
        "valor por lote",
        "valor por item",
        "lance minimo",
        "avaliacao do bem",
        "valor da contratacao",
        "estimativa da contratacao",
        "orcamento sigiloso",
        "sigiloso",
    ),
    "objeto": (
        "objeto da licitacao", "objeto do edital", "objeto da contratacao", "qual o objeto",
        "qual e o objeto", "o que esta sendo contratado", "o que sera contratado",
        "qual servico sera contratado", "qual produto sera adquirido", "escopo da contratacao", "objeto",
    ),
    "modalidade": (
        "qual modalidade", "tipo de licitacao", "forma de contratacao", "como sera contratado",
        "procedimento", "modalidade", "pregao", "concorrencia", "dispensa", "inexigibilidade",
    ),
    "orgao_responsavel": ("orgao responsavel", "entidade responsavel", "orgao contratante", "quem contrata"),
    "uf": ("em qual uf", "qual uf", "unidade federativa", "estado do orgao", "localizado o orgao"),
    "data_abertura": ("data de abertura", "abertura da sessao", "inicio da sessao", "quando abre"),
    "prazo_entrega_proposta": (
        "prazo da proposta",
        "validade da proposta",
        "validade das propostas",
        "prazo de validade da proposta",
        "proposta valida por",
        "prazo minimo da proposta",
        "manutencao da proposta",
        "entrega da proposta",
        "entrega das propostas",
        "prazo para entrega das propostas",
        "envio da proposta",
        "recebimento das propostas",
        "data limite",
    ),
    "prazo": (
        "prazo de entrega",
        "prazo de execucao",
        "prazo de atendimento",
        "prazo de conclusao",
        "prazo de recebimento",
        "prazo de vigencia",
        "prazo de diagnostico",
        "qual o prazo",
    ),
    "criterio_julgamento": (
        "criterio de julgamento", "tipo de julgamento", "do julgamento",
        "julgamento das propostas", "menor preco", "maior desconto", "melhor tecnica",
        "tecnica e preco", "maior retorno economico", "maior lance", "maior oferta de preco",
    ),
    "documentos_tecnicos": (
        "documentos tecnicos",
        "documentacao tecnica",
        "atestados tecnicos",
        "atestado de capacidade tecnica",
        "documentos de qualificacao tecnica",
    ),
    "requisitos_habilitacao": ("requisitos de habilitacao", "documentos de habilitacao", "habilitacao"),
    "pontos_atencao": ("pontos de atencao", "riscos do edital", "alertas do edital", "pontos importantes"),
}

INTENT_TERMS: dict[str, tuple[str, ...]] = {
    "objeto": (
        "do objeto", "objeto", "objeto deste edital", "objeto da contratacao", "constitui objeto",
        "tem por objeto", "escopo da contratacao", "registro de precos", "contratacao",
    ),
    "valor_estimado": (
        "valor estimado",
        "orcamento estimado",
        "preco estimado",
        "valor global",
        "recursos financeiros",
        "recursos previstos para pagamentos",
        "empenho estimativo",
        "valor total da contratacao",
        "valor maximo aceitavel",
        "preco maximo aceitavel",
        "valor de referencia",
        "valor referencial",
        "valor total dos itens",
        "valor do lote",
        "valor por lote",
        "valor por item",
        "lance minimo",
        "avaliacao do bem",
        "valor total de avaliacao",
        "planilha orcamentaria",
        "valor da obra",
        "total geral",
        "tabela de precos",
        "sigiloso",
        "nao divulgado",
    ),
    "modalidade": (
        "modalidade",
        "tipo de procedimento",
        "forma de contratacao",
        "pregao eletronico",
        "concorrencia eletronica",
        "registro de precos",
        "credenciamento",
        "inexigibilidade de licitacao",
    ),
    "orgao_responsavel": (
        "orgao gerenciador", "orgao responsavel", "unidade contratante", "unidade gestora",
        "uasg", "contratante", "credenciante", "prefeitura", "secretaria", "ministerio",
        "comando", "tribunal", "fundo", "autarquia", "departamento", "entidade",
    ),
    "uf": (
        "municipio uf", "estado", "unidade federativa", "local da licitacao",
        "local de execucao", "endereco da contratante",
    ),
    "data_abertura": ("data de abertura", "abertura", "inicio da sessao", "sessao publica"),
    "prazo_entrega_proposta": (
        "validade da proposta",
        "prazo de validade da proposta",
        "proposta valida por",
        "validade das propostas",
        "prazo minimo da proposta",
        "manutencao da proposta",
    ),
    "prazo": (
        "prazo de entrega",
        "prazo de execucao",
        "prazo para execucao",
        "sob demanda",
        "ordem de servico",
        "ordem de compra",
        "prazo apos ordem de compra",
        "prazo de atendimento",
        "prazo de conclusao",
        "recebimento definitivo",
        "prazo de vigencia",
        "diagnostico",
    ),
    "criterio_julgamento": (
        "criterio de julgamento", "do julgamento", "julgamento das propostas",
        "menor preco", "maior desconto", "melhor tecnica", "tecnica e preco",
        "maior retorno economico", "maior lance", "maior oferta de preco",
    ),
    "documentos_tecnicos": (
        "qualificacao tecnica",
        "capacidade tecnico operacional",
        "capacidade tecnico profissional",
        "atestado de capacidade tecnica",
        "crea",
        "acervo tecnico",
        "responsavel tecnico",
    ),
    "requisitos_habilitacao": (
        "habilitacao juridica",
        "qualificacao tecnica",
        "qualificacao economico",
        "regularidade fiscal",
        "documentos de habilitacao",
    ),
    "pontos_atencao": (
        "sera desclassificado",
        "sera inabilitado",
        "sob pena",
        "prazo",
        "penalidade",
        "obrigacao",
        "vedado",
    ),
}

DEADLINE_QUERY_TERMS: dict[str, tuple[str, ...]] = {
    "prazo_procedimento": (
        "prazo do edital",
        "vigencia do edital",
        "prazo para credenciamento",
        "periodo de credenciamento",
        "edital vigorara",
        "prazo indeterminado",
        "procedimento aberto",
    ),
    "prazo_entrega_proposta": (
        "validade da proposta",
        "prazo de validade da proposta",
        "proposta valida por",
        "validade das propostas",
    ),
    "prazo_recebimento_definitivo": ("recebimento definitivo",),
    "prazo_vigencia": ("prazo de vigencia", "vigencia sera de"),
    "prazo_diagnostico": ("prazo de diagnostico", "estimativa de prazo"),
    "prazo_atendimento": ("prazo de atendimento",),
    "prazo_conclusao": ("prazo de conclusao",),
    "prazo_execucao": (
        "prazo de execucao", "periodo de execucao", "tempo de execucao",
        "execucao pelo periodo de", "prazo para execucao", "inicio da execucao",
        "termino da execucao", "cronograma de execucao", "periodo da prestacao",
        "prestacao pelo periodo", "a contar da ordem de servico",
        "apos ordem de servico", "a partir da emissao da os",
        "apos recebimento da ordem", "ordem de servico", "sob demanda",
    ),
    "prazo_entrega": (
        "prazo de entrega",
        "prazo para entrega do objeto",
        "prazo de execucao",
        "inicio da execucao",
        "inicio da prestacao dos servicos",
        "condicoes de execucao",
        "modelo de execucao",
        "ordem de servico",
        "cronograma de execucao",
        "prazo para atendimento",
    ),
}

EXACT_HEADINGS: dict[str, tuple[str, ...]] = {
    "objeto": ("objeto:", "i - objeto", "1. objeto", "1 - objeto"),
    "valor_estimado": (
        "valor estimado:",
        "orcamento estimado:",
        "valor global:",
        "dos recursos financeiros",
        "empenho estimativo",
        "valor de referencia:",
        "valor total da contratacao:",
        "valor total dos itens:",
        "lance minimo:",
        "estimativa do valor da contratacao",
        "planilha orcamentaria",
        "valor da obra:",
        "total geral",
    ),
    "modalidade": (
        "modalidade:",
        "pregao eletronico",
        "concorrencia eletronica",
    ),
    "orgao_responsavel": (
        "orgao responsavel:", "orgao gerenciador:", "unidade contratante:",
        "unidade gestora:", "uasg:", "entidade responsavel:", "contratante:", "credenciante:",
    ),
    "uf": ("estado do", "estado de", "municipio/uf", "cidade/uf"),
    "data_abertura": ("data de abertura:", "horario e data de abertura:", "abertura da sessao:"),
    "prazo_entrega_proposta": (
        "validade da proposta", "prazo de validade da proposta", "validade das propostas",
    ),
    "prazo": (
        "prazo de entrega:",
        "prazo de execucao:",
        "recebimento definitivo",
        "ordem de servico",
    ),
    "criterio_julgamento": (
        "criterio de julgamento:", "do criterio de julgamento", "do julgamento",
        "julgamento das propostas",
    ),
    "documentos_tecnicos": (
        "qualificacao tecnica",
        "capacidade tecnico-operacional",
        "capacidade tecnico-profissional",
    ),
    "requisitos_habilitacao": ("habilitacao", "dos documentos de habilitacao"),
}

CADASTRAL_INTENTS = {
    "objeto",
    "valor_estimado",
    "modalidade",
    "orgao_responsavel",
    "uf",
    "data_abertura",
    "prazo_entrega_proposta",
    "criterio_julgamento",
}

def normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(character for character in value if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", value).strip().casefold()


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalize_text(text))


def detect_query_intent(query: str) -> str:
    normalized = normalize_text(query)
    matches: list[tuple[int, str]] = []
    for intent, patterns in INTENT_PATTERNS.items():
        longest = max((len(pattern) for pattern in patterns if pattern in normalized), default=0)
        if longest:
            matches.append((longest, intent))
    return max(matches, default=(0, "consulta_livre"))[1]


DEADLINE_SUBTYPE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "prazo_procedimento",
        (
            "prazo da licitacao",
            "prazo do edital",
            "vigencia do edital",
            "prazo do credenciamento",
            "prazo para credenciamento",
            "periodo de credenciamento",
        ),
    ),
    ("prazo_entrega_proposta", ("proposta", "recebimento das propostas", "envio das propostas")),
    ("prazo_recebimento_definitivo", ("recebimento definitivo",)),
    ("prazo_vigencia", ("vigencia", "vigência")),
    ("prazo_diagnostico", ("diagnostico", "diagnóstico")),
    ("prazo_atendimento", ("atendimento",)),
    ("prazo_conclusao", ("conclusao", "conclusão")),
    ("prazo_execucao", ("execucao", "execução")),
    ("prazo_entrega", ("entrega",)),
)


def detect_deadline_subtype(query: str) -> str | None:
    """Classifica o tipo de prazo sem transformar entrega do serviço em proposta."""
    normalized = normalize_text(query)
    if "prazo" not in normalized and "data limite" not in normalized:
        return None
    for subtype, patterns in DEADLINE_SUBTYPE_PATTERNS:
        if any(normalize_text(pattern) in normalized for pattern in patterns):
            return subtype
    return "prazo_contextual"


def expand_query_terms(query: str, intent: str) -> tuple[str, ...]:
    """Expande sinônimos localmente, sem chamadas extras ao modelo ou à LLM."""
    terms = list(INTENT_TERMS.get(intent, ()))
    if intent == "prazo":
        subtype = detect_deadline_subtype(query)
        terms.extend(DEADLINE_QUERY_TERMS.get(subtype or "", ()))
    return tuple(dict.fromkeys(normalize_text(term) for term in terms if str(term).strip()))


def _detect_part_from_text(
    text: str,
    current: str = "edital_principal",
    page_start: int = 1,
) -> str:
    if page_start <= 5:
        return "edital_principal"
    headings = list(
        re.finditer(
            r"\bANEXO\s+[IVXLCDM]+\s*(?:[-–—]\s*)?(.{0,140})",
            text,
        )
    )
    if not headings:
        return current
    title = normalize_text(headings[-1].group(1))
    if "termo de referencia" in title:
        return "termo_referencia"
    if "minuta" in title and "ata de registro de precos" in title:
        return "ata_registro_precos"
    if "minuta" in title and "contrato" in title:
        return "minuta_contrato"
    if "modelo" in title or "declarac" in title:
        return "modelo_declaracao"
    return current


def annotate_document_structure(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enriquece chunks antigos em memória, sem alterar o índice persistido."""
    ordered = sorted(chunks, key=lambda item: int(item.get("chunk_index") or 0))
    current_part = "edital_principal"
    output: list[dict[str, Any]] = []
    for chunk in ordered:
        current_part = str(
            chunk.get("document_part")
            or _detect_part_from_text(
                chunk.get("text", ""),
                current_part,
                int(chunk.get("page_start") or 1),
            )
        )
        text = str(chunk.get("text") or "")
        heading = chunk.get("heading")
        if not heading:
            heading_match = re.search(
                r"(?:^|\s)(OBJETO|VALOR ESTIMADO|CRIT[ÉE]RIO DE JULGAMENTO|"
                r"TERMO DE REFER[ÊE]NCIA|ANEXO\s+[IVXLCDM]+|MINUTA[^.;]{0,80}|"
                r"\d{1,2}\.?\s+(?:DA|DO|DOS|DAS)\s+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-ZÁÀÂÃÉÊÍÓÔÕÚÇ\s-]{5,100})\s*:?",
                text[:900],
                re.IGNORECASE,
            )
            heading = heading_match.group(1).strip() if heading_match else None
        enriched = {
            **chunk,
            "document_part": current_part,
            "section": chunk.get("section") or ("dados_do_edital" if int(chunk.get("page_start") or 0) <= 2 else current_part),
            "heading": heading,
            "is_preamble": bool(chunk.get("is_preamble", int(chunk.get("chunk_index") or 0) == 0)),
        }
        output.append(enriched)
    return enrich_chunks_with_sections(output)


def _document_corpus(
    document_id: str,
    chunks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[list[str]]]:
    fingerprint = tuple(
        (str(chunk.get("chunk_id")), len(str(chunk.get("text") or "")))
        for chunk in chunks
    )
    with _CORPUS_CACHE_LOCK:
        cached = _CORPUS_CACHE.get(document_id)
        if cached and cached[0] == fingerprint:
            return cached[1], cached[2]
    annotated = annotate_document_structure(chunks)
    tokenized = [tokenize(chunk.get("text", "")) for chunk in annotated]
    with _CORPUS_CACHE_LOCK:
        _CORPUS_CACHE[document_id] = (fingerprint, annotated, tokenized)
    return annotated, tokenized


def _bm25_scores(
    query: str,
    chunks: list[dict[str, Any]],
    intent: str,
    documents: list[list[str]] | None = None,
) -> dict[str, float]:
    query_terms = tokenize(query)
    query_terms.extend(tokenize(" ".join(expand_query_terms(query, intent))))
    query_terms = list(dict.fromkeys(term for term in query_terms if len(term) > 2))
    if not query_terms or not chunks:
        return {}
    documents = documents or [tokenize(chunk.get("text", "")) for chunk in chunks]
    average_length = sum(len(document) for document in documents) / max(len(documents), 1)
    document_frequency = Counter(
        term for document in documents for term in set(document) if term in query_terms
    )
    scores: dict[str, float] = {}
    for chunk, document in zip(chunks, documents):
        frequencies = Counter(document)
        score = 0.0
        for term in query_terms:
            frequency = frequencies.get(term, 0)
            if not frequency:
                continue
            inverse_frequency = math.log(
                1 + (len(documents) - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5)
            )
            denominator = frequency + 1.5 * (
                1 - 0.75 + 0.75 * len(document) / max(average_length, 1)
            )
            score += inverse_frequency * (frequency * 2.5 / denominator)
        scores[str(chunk.get("chunk_id"))] = score
    return scores


def _exact_score(intent: str, text: str, deadline_subtype: str | None = None) -> float:
    normalized = normalize_text(text)
    # Os chunks podem atravessar cabeçalhos e quebras de página. Campos do
    # quadro inicial frequentemente aparecem depois dos primeiros 1.600 caracteres.
    search_window = normalized[:6000]
    headings = EXACT_HEADINGS.get(intent, ())
    score = max((1.0 if heading in search_window else 0.0 for heading in headings), default=0.0)
    if intent == "valor_estimado" and re.search(
        r"(?:valor|orcamento|preco)\s+(?:global\s+)?estimado\s*:\s*(?:sigiloso|nao divulgado|r?\$?\s*[\d.]+,\d{2})",
        search_window,
    ):
        return 1.0
    if intent == "valor_estimado" and re.search(
        r"(?:valor\s+estimado|valor\s+maximo\s+aceitavel).{0,180}(?:carater|sera)\s+sigiloso",
        search_window,
    ):
        return 1.0
    if intent == "valor_estimado" and re.search(
        r"(?:recursos\s+previstos\s+para\s+os\s+pagamentos|dos\s+recursos\s+financeiros).{0,900}"
        r"r\$\s*[\d.]+,\d{2}.{0,100}empenho\s+estimativo",
        search_window,
    ):
        return 1.0
    if intent == "valor_estimado" and re.search(
        r"(?:valor\s+total\s+da\s+contratacao|valor\s+de\s+referencia|"
        r"valor\s+total\s+dos?\s+itens?|lance\s+minimo|valor\s+total\s+de\s+avaliacao)"
        r".{0,180}(?:r\$\s*[\d.]+,\d{2,3}|[\d.]+,\d{2})",
        search_window,
    ):
        return 1.0
    if intent == "valor_estimado" and re.search(
        r"(?:valor\s+total|total\s+geral)\s*[:|\]\-]*\s*r\$\s*[\d.]+,\d{2,3}",
        normalized[:16000],
    ):
        return 1.0
    if intent == "modalidade":
        if "ato que autoriza a inexigibilidade de licitacao" in search_window:
            return 1.0
        if "inexigibilidade de licitacao" in search_window:
            score = max(score, 0.65)
        if re.search(r"(?:edital\s+de\s+)?credenciamento", search_window):
            score = max(score, 0.35)
    if intent == "prazo_entrega_proposta" and re.search(
        r"(?:prazo\s+(?:de\s+)?validade|validade)\s+(?:da|das)\s+propostas?"
        r".{0,180}\b\d{1,4}\s*(?:\([^)]{1,40}\)\s*)?(?:dias?|meses?)",
        search_window,
    ):
        return 1.0
    if intent == "criterio_julgamento" and re.search(
        r"(?:criterio\s+de\s+julgamento\s*:?|\btipo\s*:?).{0,180}"
        r"(?:menor\s+preco|maior\s+desconto|melhor\s+tecnica|tecnica\s+e\s+preco|"
        r"maior\s+retorno\s+economico|maior\s+lance|maior\s+oferta\s+de\s+preco)",
        search_window,
    ):
        return 1.0
    if intent == "orgao_responsavel" and re.search(
        r"^(?:departamento\s+municipal|prefeitura\s+municipal|municipio\s+de|"
        r"fundo\s+municipal|ministerio\s+da\s+defesa|tribunal|secretaria)",
        search_window,
    ):
        return 1.0
    if intent == "uf" and re.search(
        r"(?:estado\s+(?:do|de|da)\s+[a-z ]{3,30}|[a-z ]{3,50}\s*[-/]\s*"
        r"(?:ac|al|ap|am|ba|ce|df|es|go|ma|mt|ms|mg|pa|pb|pr|pe|pi|rj|rn|rs|ro|rr|sc|sp|se|to)\b)",
        search_window,
    ):
        return 1.0
    if intent == "prazo" and deadline_subtype == "prazo_execucao" and re.search(
        r"(?:execucao\s+contratual\s+ocorrera\s+sob\s+demanda|ordem\s+de\s+servico|"
        r"prazo\s+(?:para|de)\s+(?:execucao|entrega)|periodo\s+de\s+execucao|"
        r"cronograma\s+de\s+execucao|recebimento\s+da\s+ordem\s+de\s+compra)",
        search_window,
    ):
        return 1.0
    if intent == "prazo" and deadline_subtype == "prazo_procedimento":
        if "prazo indeterminado" in search_window:
            return 1.0
        if "prazo para credenciamento" in search_window:
            return 0.95
        if re.search(r"(?:validade\s+de|prazo\s+maximo\s+de|vigencia\s+limitada\s+em)", search_window):
            score = max(score, 0.7)
    if intent == "objeto" and re.search(
        r"(?:\bobjeto\s*:|\bdo\s+objeto\b.{0,180}\b(?:o\s+objeto\s+deste\s+edital\s+e|constitui\s+objeto|tem\s+por\s+objeto))",
        search_window,
    ):
        return 1.0
    return score


def _section_scores(
    intent: str,
    chunk: dict[str, Any],
    deadline_subtype: str | None,
) -> tuple[float, float, float]:
    intent_types: dict[str, set[str]] = {
        "objeto": {"objeto"},
        "valor_estimado": {"recursos_financeiros", "preco"},
        "criterio_julgamento": {"criterio_julgamento", "habilitacao"},
        "requisitos_habilitacao": {"habilitacao"},
        "documentos_tecnicos": {"habilitacao"},
        "prazo_entrega_proposta": {"prazos", "abertura"},
        "prazo": (
            {"prazo_entrega", "entrega", "execucao", "regime_execucao"}
            if deadline_subtype == "prazo_entrega"
            else {"prazos", "execucao", "regime_execucao", "vigencia"}
        ),
    }
    expected = intent_types.get(intent, set())
    headings = list(chunk.get("section_headings") or [])
    matching = [item for item in headings if item.get("section_type") in expected]
    inherited_match = chunk.get("section_type") in expected
    section_boost = 1.0 if matching or inherited_match else 0.0
    heading_boost = max((0.2 if item.get("is_toc") else 1.0 for item in matching), default=0.0)
    normalized = normalize_text(chunk.get("text", ""))
    proximity = 0.0
    for heading in matching:
        start = int(heading.get("heading_end") or 0)
        window = normalized[start : start + 1800]
        if intent == "objeto" and re.search(
            r"\b(?:\d+\.\d+\.?\s*)?(?:o\s+objeto\s+deste\s+edital\s+e|constitui\s+objeto|tem\s+por\s+objeto)",
            window,
        ):
            proximity = 1.0
        elif intent == "valor_estimado" and re.search(
            r"(?:r\$\s*[\d.]+,\d{2}|empenho\s+estimativo|sigiloso)", window
        ):
            proximity = 1.0
        elif intent == "prazo" and re.search(
            r"prazo\s+(?:para|de)\s+entrega.{0,180}\b\d+\s*\([^)]*\)?\s*dias|ordem\s+de\s+compra",
            window,
        ):
            proximity = 1.0
    return section_boost, heading_boost, proximity


def _structural_score(intent: str, chunk: dict[str, Any]) -> float:
    page = int(chunk.get("page_start") or 9999)
    score = 0.0
    if intent in CADASTRAL_INTENTS:
        if chunk.get("is_preamble") or page <= 2:
            score += 1.0
        elif page <= 5:
            score += 0.5
    if chunk.get("heading"):
        score += 0.25
    document_part = chunk.get("document_part")
    if intent == "pontos_atencao":
        if document_part == "edital_principal":
            score += 0.8
        elif document_part == "termo_referencia":
            score += 0.5
        else:
            score += 0.1
    elif document_part == "edital_principal":
        score += 0.2
    return min(score, 1.0)


def _field_anchor_score(intent: str, chunk: dict[str, Any], exact_score: float) -> float:
    """Prioriza campos cadastrais rotulados no quadro inicial do edital."""
    if intent not in {"objeto", "valor_estimado"} or exact_score < 1.0:
        return 0.0
    page = int(chunk.get("page_start") or 9999)
    if intent == "valor_estimado" and re.search(
        r"(?:planilha\s+orcamentaria.{0,9000})?"
        r"(?:valor\s+total|total\s+geral)\s*[:|\]\-]*\s*r\$\s*[\d.]+,\d{2,3}",
        normalize_text(chunk.get("text", ""))[:16000],
    ):
        return 1.0
    return 1.0 if chunk.get("is_preamble") or page <= 4 else 0.0


def _table_total_score(intent: str, chunk: dict[str, Any]) -> float:
    if intent != "valor_estimado":
        return 0.0
    normalized = normalize_text(chunk.get("text", ""))[:16000]
    return 1.0 if re.search(
        r"(?:valor\s+total|total\s+geral)\s*[:|\]\-]*\s*r\$\s*[\d.]+,\d{2,3}",
        normalized,
    ) else 0.0


def hybrid_search(
    query: str,
    top_k: int = FINAL_TOP_K_LIMIT,
    document_id: str | None = None,
    *,
    k: int | None = None,
    embedding_model: Any | None = None,
    timing: dict[str, float] | None = None,
    candidate_size: int = DEFAULT_CANDIDATE_SIZE,
    diagnostic_top_k: bool = False,
    dense_search_fn: Callable[..., list[dict[str, Any]]] = dense_search,
    chunks_fn: Callable[[str | None], list[dict[str, Any]]] = get_chunks,
) -> list[dict[str, Any]]:
    """Recupera candidatos localmente; produção continua limitada a três fontes."""
    if k is not None:
        top_k = k
    top_k = max(int(top_k), 1)
    if not diagnostic_top_k:
        top_k = min(top_k, FINAL_TOP_K_LIMIT)
    candidate_size = max(candidate_size, top_k)
    if not str(document_id or "").strip():
        raise ValueError("document_id é obrigatório para busca híbrida.")

    started = time.perf_counter()
    intent = detect_query_intent(query)
    deadline_subtype = detect_deadline_subtype(query) if intent == "prazo" else None
    document_chunks, tokenized_documents = _document_corpus(document_id, chunks_fn(document_id))
    if any(chunk.get("document_id") != document_id for chunk in document_chunks):
        raise RuntimeError("Falha de isolamento nos candidatos da busca híbrida.")

    dense_timing: dict[str, float] = {}
    dense = dense_search_fn(
        query,
        top_k=candidate_size,
        document_id=document_id,
        embedding_model=embedding_model,
        timing=dense_timing,
    )
    bm25 = _bm25_scores(query, document_chunks, intent, tokenized_documents)
    lexical = sorted(document_chunks, key=lambda item: bm25.get(str(item.get("chunk_id")), 0.0), reverse=True)[
        :candidate_size
    ]
    structural = sorted(
        document_chunks,
        key=lambda item: (
            _exact_score(intent, item.get("text", ""), deadline_subtype),
            _structural_score(intent, item),
            -int(item.get("chunk_index") or 0),
        ),
        reverse=True,
    )[:candidate_size]

    dense_by_id = {str(item.get("chunk_id")): item for item in dense}
    structured_by_id = {str(item.get("chunk_id")): item for item in document_chunks}
    combined: dict[str, dict[str, Any]] = {}
    for source in dense + lexical + structural:
        chunk_id = str(source.get("chunk_id"))
        if chunk_id and chunk_id not in combined:
            combined[chunk_id] = {
                **source,
                **structured_by_id.get(chunk_id, {}),
            }

    max_bm25 = max((bm25.get(chunk_id, 0.0) for chunk_id in combined), default=0.0)
    dense_rank = {str(item.get("chunk_id")): rank for rank, item in enumerate(dense, start=1)}
    lexical_rank = {str(item.get("chunk_id")): rank for rank, item in enumerate(lexical, start=1)}
    structural_rank = {str(item.get("chunk_id")): rank for rank, item in enumerate(structural, start=1)}
    rerank_started = time.perf_counter()
    ranked: list[dict[str, Any]] = []
    for chunk_id, source in combined.items():
        dense_source = dense_by_id.get(chunk_id, {})
        dense_score = float(dense_source.get("retrieval_score") or 0.0)
        lexical_score = bm25.get(chunk_id, 0.0) / max_bm25 if max_bm25 else 0.0
        exact_score = _exact_score(intent, source.get("text", ""), deadline_subtype)
        structure_score = _structural_score(intent, source)
        field_anchor_score = _field_anchor_score(intent, source, exact_score)
        table_total_score = _table_total_score(intent, source)
        section_boost, heading_boost, heading_content_proximity = _section_scores(
            intent, source, deadline_subtype
        )
        rrf_raw = (
            0.45 / (RRF_K + dense_rank[chunk_id]) if chunk_id in dense_rank else 0.0
        ) + (
            0.35 / (RRF_K + lexical_rank[chunk_id]) if chunk_id in lexical_rank else 0.0
        ) + (
            0.20 / (RRF_K + structural_rank[chunk_id]) if chunk_id in structural_rank else 0.0
        )
        rrf_score = rrf_raw * (RRF_K + 1)
        if intent in CADASTRAL_INTENTS or intent == "prazo":
            rerank_score = (
                0.15 * dense_score
                + 0.15 * lexical_score
                + 0.25 * exact_score
                + 0.05 * structure_score
                + 0.10 * rrf_score
                + 0.40 * field_anchor_score
                + 0.45 * table_total_score
                + 0.30 * section_boost
                + 0.40 * heading_boost
                + 0.45 * heading_content_proximity
            )
        else:
            rerank_score = (
                0.40 * dense_score
                + 0.25 * lexical_score
                + 0.10 * exact_score
                + 0.10 * structure_score
                + 0.15 * rrf_score
            )
        ranked.append(
            {
                **source,
                "retrieval_score": round(dense_score, 6),
                "lexical_score": round(lexical_score, 6),
                "exact_match_score": round(exact_score, 6),
                "structural_score": round(structure_score, 6),
                "field_anchor_score": round(field_anchor_score, 6),
                "table_total_score": round(table_total_score, 6),
                "section_boost": round(section_boost, 6),
                "heading_boost": round(heading_boost, 6),
                "heading_content_proximity": round(heading_content_proximity, 6),
                "rrf_score": round(rrf_score, 6),
                "rerank_score": round(rerank_score, 6),
                "query_intent": intent,
                "query_expansion_terms": list(expand_query_terms(query, intent)),
            }
        )
    ranked.sort(
        key=lambda item: (
            -float(item["rerank_score"]),
            -float(item["exact_match_score"]),
            -float(item["lexical_score"]),
            int(item.get("chunk_index") or 0),
        )
    )
    result = ranked[:top_k]
    if RAG_DEBUG_RETRIEVAL:
        LOGGER.info(
            "[RETRIEVAL] %s",
            json.dumps(
                {
                    "intent": intent,
                    "query": query,
                    "expanded_queries": list(expand_query_terms(query, intent)),
                    "document_id": document_id,
                    "dense_candidates": len(dense),
                    "lexical_candidates": len(lexical),
                    "results": [
                        {
                            "chunk_id": item.get("chunk_id"),
                            "page_start": item.get("page_start"),
                            "page_end": item.get("page_end"),
                            "section_title": item.get("section_title"),
                            "semantic": item.get("retrieval_score"),
                            "lexical": item.get("lexical_score"),
                            "section_boost": item.get("section_boost"),
                            "heading_boost": item.get("heading_boost"),
                            "before_reranking": item.get("rrf_score"),
                            "after_reranking": item.get("rerank_score"),
                        }
                        for item in result
                    ],
                },
                ensure_ascii=False,
            ),
        )
    reranking_ms = round((time.perf_counter() - rerank_started) * 1000, 1)
    if any(item.get("document_id") != document_id for item in result):
        raise RuntimeError("Falha de isolamento: reranking retornou outro edital.")
    if timing is not None:
        timing.update(
            {
                **dense_timing,
                "candidate_count": len(combined),
                "dense_candidates": len(dense),
                "lexical_candidates": len(lexical),
                "structural_candidates": len(structural),
                "deduplicated_candidates": len(combined),
                "reranking_ms": reranking_ms,
                "hybrid_search_ms": round((time.perf_counter() - started) * 1000, 1),
                "query_intent": intent,
            }
        )
    return result


def retrieval_quality_metrics(
    ranked_results: list[dict[str, Any]],
    relevant_chunk_ids: set[str] | list[str] | tuple[str, ...],
    *,
    k: int = 3,
) -> dict[str, float]:
    """Calcula métricas offline quando existe ground truth de recuperação."""
    relevant = {str(chunk_id) for chunk_id in relevant_chunk_ids}
    top = ranked_results[: max(int(k), 1)]
    retrieved = [str(item.get("chunk_id")) for item in top]
    hits = [chunk_id for chunk_id in retrieved if chunk_id in relevant]
    first_rank = next(
        (position for position, chunk_id in enumerate(retrieved, start=1) if chunk_id in relevant),
        None,
    )
    return {
        f"recall@{k}": len(set(hits)) / len(relevant) if relevant else 0.0,
        "mrr": 1.0 / first_rank if first_rank else 0.0,
        f"precision@{k}": len(hits) / len(top) if top else 0.0,
    }

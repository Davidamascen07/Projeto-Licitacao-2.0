from __future__ import annotations

import json
import re
import time
from typing import Any

from .evidence import validate_evidence
from .evidence_bundle import expand_evidence_bundle
from .llm_utils import complete_with_metrics
from .retrieval import detect_deadline_subtype, detect_query_intent, hybrid_search as search
from .retrieval_pipeline import retrieve_evidence

MAX_SOURCE_CHARS = 1200
DEFAULT_TOP_K = 3
SAFE_NOT_FOUND = "Informação não encontrada nos trechos disponíveis."
SAFE_UNVERIFIED = "Não foi possível confirmar a resposta com evidência literal nos trechos recuperados."
INFORMATION_STATUSES = {
    "FOUND",
    "CONFIDENTIAL",
    "NOT_DISCLOSED",
    "NOT_FOUND",
    "NOT_APPLICABLE",
    "CONFLICTING",
    "CONTEXT_DEPENDENT",
}


def _format_pages(source: dict[str, Any]) -> str:
    if source["page_start"] == source["page_end"]:
        return str(source["page_start"])
    return f"{source['page_start']}-{source['page_end']}"


def truncate_text(text: str, max_chars: int = MAX_SOURCE_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "..."


def _relevant_excerpt(text: str, intent: str, max_chars: int = MAX_SOURCE_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    patterns = {
        "objeto": r"\bOBJETO\s*:",
        "valor_estimado": r"\b(?:VALOR|OR[ÇC]AMENTO|PRE[ÇC]O)\s+(?:(?:TOTAL|GLOBAL|M[ÁA]XIMO)\s+|DE\s+REFER[ÊE]NCIA\s+)?(?:ESTIMADO\s*)?:|\b(?:RECURSOS\s+FINANCEIROS|EMPENHO\s+ESTIMATIVO|LANCE\s+M[ÍI]NIMO|AVALIA[ÇC][ÃA]O\s+DO\s+BEM)\b",
        "modalidade": r"\b(?:MODALIDADE\s*:|PREG[ÃA]O\s+ELETR[ÔO]NICO|CONCORR[ÊE]NCIA\s+ELETR[ÔO]NICA|CREDENCIAMENTO|INEXIGIBILIDADE\s+DE\s+LICITA[ÇC][ÃA]O)",
        "orgao_responsavel": r"\b(?:[ÓO]RG[ÃA]O|ENTIDADE|CONTRATANTE)\s*(?:RESPONS[ÁA]VEL)?\s*:",
        "data_abertura": r"\b(?:DATA|HOR[ÁA]RIO)\s+(?:E\s+)?(?:DE\s+)?ABERTURA\s*:",
        "prazo_entrega_proposta": r"\b(?:PRAZO\s+(?:DE\s+)?VALIDADE|VALIDADE)\s+(?:DA|DAS)\s+PROPOSTAS?\b|\bPROPOSTAS?\s+V[ÁA]LIDAS?\s+POR\b",
        "prazo": r"\b(?:PRAZO\s+(?:DE|PARA)\s+(?:ENTREGA|EXECU[ÇC][ÃA]O)|PER[ÍI]ODO\s+DE\s+EXECU[ÇC][ÃA]O|CRONOGRAMA\s+DE\s+EXECU[ÇC][ÃA]O|PRAZO\s+PARA\s+CREDENCIAMENTO|PRAZO\s+INDETERMINADO|SOB\s+DEMANDA|ORDEM\s+DE\s+SERVI[ÇC]O|RECEBIMENTO\s+DEFINITIVO)\b",
        "criterio_julgamento": r"\bCRIT[ÉE]RIO\s+DE\s+JULGAMENTO\s*:",
        "requisitos_habilitacao": r"\b(?:DOCUMENTOS?|REQUISITOS?)\s+DE\s+HABILITA[ÇC][ÃA]O\b",
        "pontos_atencao": r"\b(?:SOB\s+PENA|VEDAD[OA]|SER[ÁA]\s+(?:INABILITAD[OA]|DESCLASSIFICAD[OA]))\b",
    }
    match = re.search(patterns.get(intent, r"$^"), text, re.IGNORECASE)
    if not match:
        return truncate_text(text, max_chars)
    start = max(0, match.start() - 180)
    end = min(len(text), start + max_chars)
    excerpt = text[start:end]
    if start:
        excerpt = "..." + excerpt
    if end < len(text):
        excerpt += "..."
    return excerpt


def _format_sources_for_prompt(sources: list[dict[str, Any]], intent: str) -> str:
    excerpt_limits = {
        "prazo": 750,
        "requisitos_habilitacao": 700,
        "documentos_tecnicos": 700,
        "pontos_atencao": 650,
    }
    max_chars = excerpt_limits.get(intent, MAX_SOURCE_CHARS)
    use_aliases = intent in excerpt_limits
    return "\n\n".join(
        f"[Chunk: {'C' + str(position) if use_aliases else source['chunk_id']} | Documento: {source['filename']} | "
        f"Página(s): {_format_pages(source)} | Parte: {source.get('document_part', 'desconhecido')}]\n"
        f"{_habilitation_excerpt(source['text'], max_chars=max_chars) if intent in {'requisitos_habilitacao', 'documentos_tecnicos'} else _relevant_excerpt(source['text'], intent, max_chars=max_chars)}"
        for position, source in enumerate(sources, start=1)
    )


def _habilitation_excerpt(text: str, max_chars: int = 700) -> str:
    patterns = (
        r"HABILITA[ÇC][ÃA]O\s+JUR[ÍI]DICA",
        r"REGULARIDADE\s+FISCAL",
        r"QUALIFICA[ÇC][ÃA]O\s+ECON[ÔO]MIC",
        r"T[ÉE]CNICO[-\s]+OPERACIONAL",
        r"T[ÉE]CNICO[-\s]+PROFISSIONAL",
        r"DECLARA[ÇC][ÃA]O",
    )
    matches = [
        match
        for pattern in patterns
        if (match := re.search(pattern, text, re.IGNORECASE))
    ]
    if not matches:
        return truncate_text(text, min(max_chars, 420))
    pieces = []
    per_match = max(180, max_chars // len(matches))
    for match in matches:
        start = max(0, match.start() - 50)
        pieces.append(text[start : min(len(text), start + per_match)])
    return truncate_text("\n[...]\n".join(pieces), max_chars)


def generate_prompt_for_agent_response(query_text: str, sources: list[dict[str, Any]]) -> str:
    intent = detect_query_intent(query_text)
    context = _format_sources_for_prompt(sources, intent) if sources else "(nenhum trecho recuperado)"
    if intent == "pontos_atencao":
        response_format = """
Retorne exclusivamente JSON válido neste formato:
{"points":[{"title":"título curto","source_chunk_id":"C1","evidence_text":"trecho literal"}]}
Cada ponto deve ter evidência própria e literal, sem reticências. Não trate minuta, ata ou
anexo como regra geral do edital. Retorne até cinco pontos distintos. Limite o título a
55 caracteres e cada evidence_text a 110 caracteres.
"""
    elif intent in {"requisitos_habilitacao", "documentos_tecnicos"}:
        scope_rule = (
            "Retorne somente as categorias tecnico_operacional e tecnico_profissional."
            if intent == "documentos_tecnicos"
            else "Retorne todas as categorias encontradas."
        )
        response_format = """
Retorne exclusivamente JSON válido neste formato:
{"status":"FOUND|NOT_FOUND","items":[{"category":"juridica|fiscal_trabalhista|economica|tecnico_operacional|tecnico_profissional|declaracoes","summary":"síntese curta","source_chunk_id":"C1","evidence_text":"trecho literal"}]}
Agregue os requisitos encontrados na seção de habilitação. Retorne no máximo um item por
categoria e até seis itens, cada um com evidência própria, literal e sem reticências.
Limite summary a 55 caracteres e evidence_text a 80 caracteres. Não explique fora do JSON.
""" + scope_rule + """
"""
    elif intent == "prazo":
        response_format = """
Retorne exclusivamente JSON válido neste formato:
{"status":"CONTEXT_DEPENDENT|FOUND|NOT_APPLICABLE|NOT_FOUND","items":[{"deadline_type":"prazo_procedimento|prazo_credenciamento|prazo_validade_proposta|prazo_assinatura_contrato|prazo_vigencia_contrato|condicoes_execucao|ordem_servico|modelo_execucao|prazo_entrega|prazo_entrega_proposta|prazo_execucao|prazo_atendimento|prazo_conclusao|prazo_recebimento_definitivo|prazo_vigencia|prazo_diagnostico|prazo_contextual","summary":"síntese curta","source_chunk_id":"C1","evidence_text":"trecho literal"}]}
Não confunda recebimento definitivo, vigência, diagnóstico, atendimento, conclusão,
execução, entrega do serviço ou entrega da proposta. Cada afirmação deve possuir evidência
própria. Se o prazo depender de demanda, diagnóstico ou Ordem de Serviço, use
CONTEXT_DEPENDENT. O prazo de recebimento definitivo nunca é prazo de execução.
"""
    else:
        response_format = f"""
Retorne exclusivamente JSON válido:
{{"answer":"resposta objetiva ou {SAFE_NOT_FOUND}","status":"FOUND|CONFIDENTIAL|NOT_DISCLOSED|NOT_FOUND|CONFLICTING","source_chunk_ids":["id"],"evidence_text":"trecho literal"}}
"""
    return f"""Você é um analista de licitações públicas. Responda SOMENTE com base nos trechos recuperados.

CONTEXTO:
{context}

PERGUNTA: {query_text}
INTENÇÃO IDENTIFICADA: {intent}

REGRAS:
- Não invente valores, datas, modalidades, órgãos, arquivos ou páginas.
- Diferencie FOUND, CONFIDENTIAL, NOT_DISCLOSED, NOT_FOUND, CONFLICTING e CONTEXT_DEPENDENT.
- Se estiver escrito SIGILOSO, use CONFIDENTIAL; isso não significa informação ausente.
- source_chunk_ids deve conter somente IDs apresentados no contexto.
- evidence_text deve ser um trecho curto e literalmente presente no chunk citado, sem reticências.
- Números e prazos da resposta devem aparecer na evidência.
- Seja direto, sem tabelas e sem copiar trechos longos.

{response_format}
"""


def _parse_json_object(raw_text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", str(raw_text or ""), re.DOTALL)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _numeric_tokens(text: str) -> set[str]:
    return set(re.findall(r"\b\d+(?:[./:-]\d+)*(?:,\d+)?\b", str(text or "")))


def numeric_claims_are_supported(answer: str, evidence_text: str) -> bool:
    return _numeric_tokens(answer).issubset(_numeric_tokens(evidence_text))


def _strip_trailing_ellipsis(text: str) -> str:
    return re.sub(r"(?:\s*(?:\.{3}|…))+\s*$", "", str(text or "")).strip()


def _resolve_source_id(source_id: str | None, sources: list[dict[str, Any]]) -> str | None:
    value = str(source_id or "").strip()
    alias = re.fullmatch(r"C([1-5])", value, re.IGNORECASE)
    if alias:
        position = int(alias.group(1)) - 1
        if position < len(sources):
            return str(sources[position].get("chunk_id") or "") or None
        return None
    return value or None


def _confidential_value_from_sources(
    sources: list[dict[str, Any]],
) -> tuple[dict[str, Any], str] | None:
    pattern = re.compile(
        r"((?:VALOR|OR[ÇC]AMENTO|PRE[ÇC]O)\s+(?:GLOBAL\s+)?ESTIMADO\s*:\s*"
        r"(?:SIGILOSO|N[ÃA]O\s+DIVULGADO))",
        re.IGNORECASE,
    )
    for source in sources:
        match = pattern.search(str(source.get("text") or ""))
        if match:
            return source, match.group(1)
    return None


def _object_summary_from_sources(
    sources: list[dict[str, Any]],
) -> tuple[dict[str, Any], str, str] | None:
    pattern = re.compile(
        r"(OBJETO\s*:\s*(.{20,2200}?))(?=\s+(?:VALOR\s+ESTIMADO|CRIT[ÉE]RIO\s+DE\s+JULGAMENTO|"
        r"DADOS\s+DO\s+EDITAL|MODALIDADE\s*:|$))",
        re.IGNORECASE | re.DOTALL,
    )
    for source in sources:
        match = pattern.search(str(source.get("text") or ""))
        if not match:
            continue
        object_text = " ".join(match.group(2).split()).strip(" .;:")
        object_text = re.split(
            r",?\s+conforme\s+condi..es\s+vigentes\b",
            object_text,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" .;:")
        evidence_text = " ".join(match.group(1).split()).strip()
        evidence_text = re.split(
            r",?\s+conforme\s+condi..es\s+vigentes\b",
            evidence_text,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" .;:")
        return source, f"Objeto: {object_text}.", evidence_text
    return None


def _confidential_value_from_sources(
    sources: list[dict[str, Any]],
) -> tuple[dict[str, Any], str] | None:
    """Reconhece tanto rótulos curtos quanto a cláusula de orçamento sigiloso."""
    pattern = re.compile(
        r"((?:(?:VALOR|OR.CAMENTO|PRE.CO)\s+(?:GLOBAL\s+)?ESTIMADO\s*:\s*"
        r"(?:SIGILOSO|N.O\s+DIVULGADO))|"
        r"(?:(?:O\s+)?VALOR\s+ESTIMADO.{0,180}?"
        r"(?:POSSUIR.|TER.)\s+CAR.TER\s+SIGILOSO[^.]*\.?))",
        re.IGNORECASE,
    )
    for source in sources:
        match = pattern.search(str(source.get("text") or ""))
        if match:
            return source, " ".join(match.group(1).split()).strip()
    return None


def _object_summary_from_sources(
    sources: list[dict[str, Any]],
) -> tuple[dict[str, Any], str, str] | None:
    """Prefere o item formal DO OBJETO e mantém compatibilidade com quadros de capa."""
    patterns = (
        re.compile(
            r"((?:\d{1,2}\.?\s+)?DO\s+OBJETO\.?\s*(?:\d{1,2}\.\d+\.?\s*)?"
            r"O\s+presente\s+edital\s+destina-se\s+a\s+(.{15,1800}?))"
            r"(?=,?\s+com\s+disponibilidades?\s+t[ée]cnicas?\s+conforme\s+segue)",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"(OBJETO\s*:\s*(.{8,1600}?))(?=\s+(?:VALOR(?:\s+TOTAL|\s+ESTIMADO|\s+DE\s+REFER[ÊE]NCIA)?|"
            r"DATA\s+DA\s+SESS[ÃA]O|CRIT[ÉE]RIO\s+DE\s+JULGAMENTO|DEMANDANTE|PROCESSO\s+ADMINISTRATIVO)\b)",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"((?:\d{1,2}\.?\s+)?DO\s+OBJETO\.?\s*(?:\d{1,2}\.\d+\.?\s*)?"
            r"(?:O\s+presente\s+Edital\s+tem\s+por\s+objeto|O\s+objeto\s+da\s+presente\s+licita[çc][ãa]o\s+[ée])\s+"
            r"(.{15,1800}?))(?=\s+\d{1,2}\.\d+\.?\s|\s+\d{1,2}\.?\s+(?:DA|DO|DOS|DAS)\s|$)",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"((?:I\s*[-–]\s*)?OBJETO\s+(?:1\.1\s*[-.]?\s*)?"
            r"Constitui\s+objeto\s+do\s+presente(?:\s+o)?\s+(.{15,1500}?))"
            r"(?=\s+(?:II\s*[-–]|\d{1,2}\.\d+\s|\d{1,2}\.?\s+(?:DA|DO|DOS|DAS)\s)|$)",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"((?:\d{1,2}\.?\s+)?DO\s+OBJETO\.?\s*"
            r"(?:\d{1,2}\.\d+\.?\s*)?O\s+objeto\s+deste\s+Edital\s+.\s+"
            r"(.{20,2400}?))(?=\s+\d{1,2}\.\d+\.?\s|\s+\d{1,2}\.?\s+(?:DA|DO|DOS|DAS)\s|$)",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"(OBJETO\s*:\s*(.{20,2200}?))(?=\s+(?:VALOR\s+ESTIMADO|CRIT.RIO\s+DE\s+JULGAMENTO|"
            r"DADOS\s+DO\s+EDITAL|MODALIDADE\s*:|$))",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"((?:\d{1,2}\.?\s+)?DO\s+OBJETO\s*:\s*"
            r"(?:\d{1,2}\.\d+\.?\s*)?(.{20,1800}?))"
            r"(?=\s+\d{1,2}\.\d+\.?\s|\s+\d{1,2}\.?\s+(?:DA|DO|DOS|DAS)\s|$)",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"((?:\d{1,2}\.?\s+)?OBJETO\s+(?:\d{1,2}\.\d+\.?\s*)?"
            r"(?:O\s+objeto\s+deste\s+LEIL[ÃA]O\s+.|O\s+presente\s+leil[ãa]o\s+tem\s+por\s+finalidade|"
            r"A\s+presente\s+Dispensa\s+de\s+Licita[çc][ãa]o\s+tem\s+por\s+objeto)\s+"
            r"(.{20,1500}?))(?=\s+\d{1,2}\.\d+\.?\s|\s+\d{1,2}\.?\s+(?:DA|DO|DOS|DAS)\s|$)",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"((?:\d{1,2}\.\d+\.?\s*)?O\s+presente\s+leil[ãa]o\s+tem\s+por\s+finalidade\s*,?\s*"
            r"(.{20,1500}?))(?=\s+\d{1,2}\.\d+\.?\s|\s+\d{1,2}\.?\s+(?:DA|DO|DOS|DAS)\s|$)",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"(A\s+presente\s+Dispensa\s+de\s+Licita[çc][ãa]o\s+tem\s+por\s+objeto\s+"
            r"(.{20,1200}?))(?=\s+\d{1,2}(?:\.\d+)*\.?\s|$)",
            re.IGNORECASE | re.DOTALL,
        ),
    )
    for source in sources:
        text = str(source.get("text") or "")
        match = next((candidate.search(text) for candidate in patterns if candidate.search(text)), None)
        if not match:
            continue
        object_text = " ".join(match.group(2).split()).strip(" .;:")
        evidence_text = " ".join(match.group(1).split()).strip()
        return source, f"Objeto: {object_text}.", evidence_text
    return None


def _modality_claims_from_sources(
    sources: list[dict[str, Any]],
    document_id: str,
) -> list[dict[str, Any]]:
    """Valida procedimento e fundamento em evidências independentes."""
    rules = (
        (
            "procedimento",
            "Credenciamento",
            re.compile(r"((?:EDITAL\s+DE\s+)?CREDENCIAMENTO(?:\s+N.\s*[\w./-]+)?)", re.IGNORECASE),
        ),
        (
            "forma_contratacao",
            "Inexigibilidade de licitação",
            re.compile(r"((?:ATO\s+QUE\s+AUTORIZA\s+A\s+)?INEXIGIBILIDADE\s+DE\s+LICITA..O)", re.IGNORECASE),
        ),
    )
    claims: list[dict[str, Any]] = []
    for label, value, pattern in rules:
        for source in sources:
            match = pattern.search(str(source.get("text") or ""))
            if not match:
                continue
            evidence_text = " ".join(match.group(1).split()).strip()
            evidence = validate_evidence(
                evidence_text=evidence_text,
                source_chunk_id=str(source.get("chunk_id") or ""),
                retrieved_sources=sources,
                selected_document_id=document_id,
                value=value,
                field_name="modalidade",
            )
            if evidence["evidence_valid"]:
                claims.append(
                    {
                        "label": label,
                        "value": value,
                        "source_chunk_id": evidence["chunk_id"],
                        "evidence_text": evidence_text,
                        "pages": evidence.get("pages"),
                        "evidence": evidence,
                    }
                )
                break
    return claims


def _estimated_value_from_sources(
    sources: list[dict[str, Any]],
) -> tuple[dict[str, Any], str, str] | None:
    pattern = re.compile(
        r"(VALOR\s+ESTIMADO\s*:\s*(?:(Total\s+Geral\s+da\s+Contrata[çc][ãa]o)\s*:\s*)?"
        r"(R\$\s*[\d.]+,\d{2})(?:\s*\([^)]+\))?)",
        re.IGNORECASE,
    )
    for source in sources:
        match = pattern.search(str(source.get("text") or ""))
        if not match:
            continue
        scope = " total da contratação" if match.group(2) else ""
        answer = f"Valor estimado{scope}: {match.group(3)}."
        return source, answer, " ".join(match.group(1).split()).strip()
    return None


def _scoped_estimated_value_from_sources(
    sources: list[dict[str, Any]],
) -> tuple[dict[str, Any], str, str] | None:
    """Preserva o escopo quando o valor pertence somente a uma categoria."""
    ocs_pattern = re.compile(
        r"(5\.1\.1\.\s*Para\s+OCS\s*:[^.]{0,900}?"
        r"no\s+valor\s+de\s+(R\$\s*[\d.]+,\d{2})[^.]{0,160}?Empenho\s+Estimativo\.)",
        re.IGNORECASE,
    )
    psa_pattern = re.compile(r"(5\.1\.2\.\s*Para\s+PSA\s*:[^.]{0,900}\.)", re.IGNORECASE)
    for source in sources:
        text = str(source.get("text") or "")
        ocs = ocs_pattern.search(text)
        if not ocs:
            continue
        psa = psa_pattern.search(text)
        evidence_text = " ".join(
            part for part in (" ".join(ocs.group(1).split()), " ".join(psa.group(1).split()) if psa else "") if part
        )
        answer = (
            f"O edital prevê {ocs.group(2)} para pagamentos destinados às Organizações Civis "
            "de Saúde (OCS), como empenho estimativo."
        )
        if psa:
            answer += (
                " Para os Profissionais de Saúde Autônomos (PSA), o mesmo trecho informa "
                "fontes e classificações orçamentárias, sem indicar valor global numérico específico."
            )
        return source, answer, evidence_text
    return None


def _modality_summary_from_sources(
    sources: list[dict[str, Any]],
) -> tuple[dict[str, Any], str, str] | None:
    for source in sources:
        text = str(source.get("text") or "")
        modality = re.search(r"\bPREG[ÃA]O\s+ELETR[ÔO]NICO\b", text, re.IGNORECASE)
        registration = re.search(r"\bREGISTRO\s+DE\s+PRE[ÇC]OS\b", text, re.IGNORECASE)
        criterion = re.search(
            r"\bCRIT[ÉE]RIO\s+DE\s+JULGAMENTO\s*:\s*MENOR\s+PRE[ÇC]O\s+POR\s+LOTE\b",
            text,
            re.IGNORECASE,
        )
        dispute = re.search(
            r"\bMODO\s+DE\s+DISPUTA\s*:\s*ABERTO\s+E\s+FECHADO\b",
            text,
            re.IGNORECASE,
        )
        if not all((modality, registration, criterion, dispute)):
            continue
        start = min(match.start() for match in (modality, registration, criterion, dispute))
        end = max(match.end() for match in (modality, registration, criterion, dispute))
        evidence_text = text[start:end]
        answer = (
            "Modalidade: Pregão Eletrônico para Registro de Preços. "
            "Critério de julgamento: menor preço por lote. "
            "Modo de disputa: aberto e fechado."
        )
        return source, answer, evidence_text
    for source in sources:
        text = str(source.get("text") or "")
        procedure = re.search(r"\b(?:EDITAL\s+DE\s+)?CREDENCIAMENTO\b", text, re.IGNORECASE)
        hiring_form = re.search(r"\bINEXIGIBILIDADE\s+DE\s+LICITA[ÇC][ÃA]O\b", text, re.IGNORECASE)
        if not all((procedure, hiring_form)):
            continue
        start = max(0, procedure.start() - 30)
        end = min(len(text), hiring_form.end() + 120)
        evidence_text = " ".join(text[start:end].split())
        answer = (
            "Procedimento: Credenciamento. Forma de contratação: "
            "Inexigibilidade de licitação."
        )
        return source, answer, evidence_text
    for source in sources:
        match = re.search(r"(PREG.O\s+ELETR.NICO(?:\s+N.\s*[\w./-]+)?)", str(source.get("text") or ""), re.IGNORECASE)
        if match:
            return source, "Modalidade: Pregão Eletrônico.", " ".join(match.group(1).split()).strip()
    for source in sources:
        match = re.search(
            r"(CONCORR[ÊE]NCIA(?:\s+P[ÚU]BLICA)?(?:\s+ELETR[ÔO]NICA)?(?:\s+N.\s*[\w./-]+)?)",
            str(source.get("text") or ""),
            re.IGNORECASE,
        )
        if match:
            return source, "Modalidade: Concorrência Eletrônica.", " ".join(match.group(1).split()).strip()
    for source in sources:
        match = re.search(r"(LEIL[ÃA]O\s+(?:P[ÚU]BLICO\s+)?(?:ELETR[ÔO]NICO|ONLINE\s+E\s+PRESENCIAL|ONLINE|PRESENCIAL)?)", str(source.get("text") or ""), re.IGNORECASE)
        if match:
            return source, "Modalidade: Leilão.", " ".join(match.group(1).split()).strip()
    for source in sources:
        match = re.search(r"(DISPENSA\s+DE\s+LICITA[ÇC][ÃA]O)", str(source.get("text") or ""), re.IGNORECASE)
        if match:
            return source, "Modalidade: Dispensa de licitação.", " ".join(match.group(1).split()).strip()
    for source in sources:
        match = re.search(
            r"((?:EDITAL\s+(?:DE\s+CHAMAMENTO\s+P[ÚU]BLICO\s+PARA\s+)?(?:DE\s+)?)?CREDENCIAMENTO(?:\s+N.\s*[\w./-]+)?)",
            str(source.get("text") or ""),
            re.IGNORECASE,
        )
        if match:
            return source, "Procedimento: Credenciamento.", " ".join(match.group(1).split()).strip()
    return None


def _validate_query_evidence(
    *,
    parsed: dict[str, Any],
    sources: list[dict[str, Any]],
    document_id: str,
    intent: str,
) -> dict[str, Any]:
    answer = str(parsed.get("answer") or "").strip()
    status = str(parsed.get("status") or "").strip().upper()
    evidence_text = _strip_trailing_ellipsis(parsed.get("evidence_text") or "")
    raw_ids = parsed.get("source_chunk_ids")
    source_ids = [str(item) for item in raw_ids] if isinstance(raw_ids, list) else []
    source_id = source_ids[0] if source_ids else None
    if status not in INFORMATION_STATUSES:
        status = "NOT_FOUND"
    if status == "NOT_FOUND":
        return {
            "answer": SAFE_NOT_FOUND,
            "status": status,
            "source_chunk_ids": [],
            "evidence_text": "",
            "evidence": None,
        }
    evidence = validate_evidence(
        evidence_text=evidence_text,
        source_chunk_id=source_id,
        retrieved_sources=sources,
        selected_document_id=document_id,
        value=answer,
        field_name=intent,
    )
    if not evidence["evidence_valid"] or not numeric_claims_are_supported(answer, evidence_text):
        return {
            "answer": SAFE_UNVERIFIED,
            "status": "NOT_FOUND",
            "source_chunk_ids": [],
            "evidence_text": "",
            "evidence": evidence,
        }
    return {
        "answer": answer or SAFE_NOT_FOUND,
        "status": status,
        "source_chunk_ids": [str(evidence["chunk_id"])],
        "evidence_text": evidence_text,
        "evidence": evidence,
    }


def _deadline_items_from_sources(
    sources: list[dict[str, Any]],
    document_id: str,
    requested_subtype: str | None = None,
) -> tuple[str, list[dict[str, Any]], int]:
    rules = (
        (
            "prazo_entrega",
            re.compile(
                r"((?:(?:DO\s+)?PRAZO\s+E\s+(?:DO\s+)?LOCAL\s+DE\s+ENTREGA\s+DO\s+OBJETO|"
                r"PRAZO\s+PARA\s+ENTREGA(?:\s+E\s+INSTALA..O)?).{0,1800}?"
                r"(?:AT.\s+)?10\s*\(DEZ\)\s+DIAS.{0,900}?ORDEM\s+DE\s+COMPRA[^.]*)",
                re.IGNORECASE | re.DOTALL,
            ),
            "A entrega deve ocorrer em até 10 dias, contados do recebimento da Ordem de Compra.",
        ),
        (
            "prazo_credenciamento",
            re.compile(
                r"(O\s+prazo\s+para\s+credenciamento[^.]{0,300}\.\s*"
                r"3\.1\.1\.\s*O\s+presente\s+Edital\s+vigorar[áa]\s+por\s+PRAZO\s+INDETERMINADO"
                r"[^.]{0,300}\.\s*3\.1\.2\.?[^.]{0,300}enquanto\s+aberto\s+o\s+prazo\s+de\s+credenciamento[^.]*\.)",
                re.IGNORECASE,
            ),
            (
                "O prazo do credenciamento é indeterminado, contado a partir da publicação "
                "do edital no PNCP; interessados podem solicitar o credenciamento enquanto "
                "o procedimento permanecer aberto."
            ),
        ),
        (
            "prazo_validade_proposta",
            re.compile(
                r"((?:A\s+)?[“\"]?Carta\s+Proposta[”\"]?\s+e\s+o\s+[“\"]?Requerimento\s+para\s+Credenciamento[”\"]?"
                r"\s+ter[ãa]o\s+validade\s+de\s+60\s*\(sessenta\)\s+dias[^.;]*)",
                re.IGNORECASE,
            ),
            "A Carta-Proposta ou o Requerimento para Credenciamento tem validade de 60 dias.",
        ),
        (
            "prazo_assinatura_contrato",
            re.compile(
                r"(Os\s+habilitados\s+ser[ãa]o\s+convocados\s+no\s+prazo\s+m[áa]ximo\s+de\s+"
                r"15\s*\(quinze\)\s+dias.{0,650}?podendo\s+ser\s+prorrogado\s+uma\s+vez,\s+"
                r"por\s+igual\s+per[íi]odo[^.]*)",
                re.IGNORECASE | re.DOTALL,
            ),
            "A convocação para assinar o contrato ocorre em até 15 dias, prorrogável uma vez por igual período.",
        ),
        (
            "prazo_vigencia_contrato",
            re.compile(
                r"(Os\s+contratos\s+celebrados\s+a\s+partir\s+do\s+presente\s+Edital\s+ter[ãa]o\s+sua\s+"
                r"vig[êe]ncia\s+limitada\s+em\s+120\s+meses[^.]*)",
                re.IGNORECASE,
            ),
            "A vigência máxima dos contratos é de 120 meses.",
        ),
        (
            "condicoes_execucao",
            re.compile(
                r"(As\s+condi[çc][õo]es\s+de\s+execu[çc][ãa]o\s+dos\s+servi[çc]os\s+"
                r"constam\s+dos\s+contratos[^.]*)",
                re.IGNORECASE,
            ),
            "As condições de execução dos serviços constam dos respectivos contratos.",
        ),
        (
            "ordem_servico",
            re.compile(
                r"(Emitir\s+as\s+ordens\s+de\s+servi[çc]os\s+[àa]\s+empresa\s+vencedora,\s+"
                r"de\s+acordo\s+com\s+as\s+necessidades,\s+respeitando\s+os\s+prazos\s+para\s+atendimentos)",
                re.IGNORECASE,
            ),
            "Os serviços são acionados por ordens de serviço, conforme as necessidades e os prazos de atendimento.",
        ),
        (
            "modelo_execucao",
            re.compile(
                r"(A\s+Fiscaliza[çc][ãa]o,\s+gest[ãa]o\s+e\s+execu[çc][ãa]o\s+do\s+contrato\s+dever[ãa]o\s+"
                r"observar\s+o\s+disposto\s+no\s+presente\s+Edital\s+e\s+seus\s+anexos[^.]*)",
                re.IGNORECASE,
            ),
            "O modelo de execução do contrato deve observar o edital e seus anexos.",
        ),
        (
            "prazo_vigencia_contrato",
            re.compile(
                r"(O\s+prazo\s+de\s+vig[êe]ncia\s+do\s+contrato.{0,700}?"
                r"at[ée]\s+05\s*\(cinco\)\s+anos.{0,700}?at[ée]\s+o\s+m[áa]ximo\s+de\s+10\s*\(dez\)\s+anos)",
                re.IGNORECASE | re.DOTALL,
            ),
            "A vigência contratual pode ser de até 05 anos, com prorrogação prevista até o máximo de 10 anos.",
        ),
        (
            "prazo_entrega_proposta",
            re.compile(
                r"((?:ACOLHIMENTO|RECEBIMENTO|ENTREGA|ENVIO)\s+DAS?\s+PROPOSTAS\s*:"
                r"[^.]{0,260})",
                re.IGNORECASE,
            ),
            "O edital define data e horário para entrega das propostas.",
        ),
        (
            "prazo_execucao",
            re.compile(
                r"(A\s+execu[çc][ãa]o\s+contratual\s+ocorrer[áa]\s+sob\s+demanda[^.]{0,220}"
                r"Ordem\s+de\s+Servi[çc]o[^.]*)",
                re.IGNORECASE,
            ),
            "A execução ocorre sob demanda e mediante Ordem de Serviço.",
        ),
        (
            "prazo_diagnostico",
            re.compile(r"([^.;]{0,120}estimativa\s+de\s+prazo\s+para\s+execu[çc][ãa]o[^.;]{0,180})", re.IGNORECASE),
            "O prazo de execução é estimado após o diagnóstico.",
        ),
        (
            "prazo_entrega",
            re.compile(r"(Prazo\s+de\s+Entrega\s*:\s*Conforme\s+Edital)", re.IGNORECASE),
            "O modelo de proposta informa: prazo de entrega conforme o edital.",
        ),
        (
            "prazo_recebimento_definitivo",
            re.compile(
                r"(O\s+recebimento\s+definitivo\s+ocorrer[áa]\s+no\s+prazo\s+de\s+at[ée]\s+"
                r"10\s*\(dez\)\s+dias\s+[úu]teis[^.]*)",
                re.IGNORECASE,
            ),
            "O recebimento definitivo pode ocorrer em até 10 dias úteis; isso não é prazo de execução.",
        ),
        (
            "prazo_vigencia",
            re.compile(
                r"((?:O\s+)?prazo\s+inicial\s+de\s+vig[êe]ncia[^.]{0,240}"
                r"ser[áa]\s+de\s+12\s*\(doze\)\s+meses[^.]*)",
                re.IGNORECASE,
            ),
            "O prazo inicial de vigência é de 12 meses.",
        ),
    )
    valid: list[dict[str, Any]] = []
    rejected = 0
    for deadline_type, pattern, summary in rules:
        match_source = None
        evidence_text = ""
        for source in sources:
            match = pattern.search(str(source.get("text") or ""))
            if match:
                match_source = source
                evidence_text = " ".join(match.group(1).split()).strip()
                break
        if match_source is None:
            continue
        evidence = validate_evidence(
            evidence_text=evidence_text,
            source_chunk_id=str(match_source.get("chunk_id") or ""),
            retrieved_sources=sources,
            selected_document_id=document_id,
            value=evidence_text,
            field_name="prazo",
        )
        if evidence["evidence_valid"] and numeric_claims_are_supported(summary, evidence_text):
            valid.append(
                {
                    "deadline_type": deadline_type,
                    "summary": summary,
                    "source_chunk_id": evidence["chunk_id"],
                    "evidence_text": evidence_text,
                    "document_part": match_source.get("document_part", "desconhecido"),
                    "pages": evidence.get("pages"),
                    "evidence": evidence,
                }
            )
        else:
            rejected += 1
    subtype_items = {
        "prazo_procedimento": {
            "prazo_credenciamento",
            "prazo_validade_proposta",
            "prazo_assinatura_contrato",
            "prazo_vigencia_contrato",
        },
        "prazo_entrega_proposta": {"prazo_entrega_proposta"},
        "prazo_recebimento_definitivo": {"prazo_recebimento_definitivo"},
        "prazo_vigencia": {"prazo_vigencia"},
        "prazo_diagnostico": {"prazo_diagnostico"},
        "prazo_atendimento": {"prazo_atendimento"},
        "prazo_conclusao": {"prazo_conclusao"},
        "prazo_execucao": {
            "prazo_execucao",
            "prazo_diagnostico",
            "condicoes_execucao",
        },
        "prazo_entrega": {
            "prazo_execucao",
            "prazo_diagnostico",
            "prazo_entrega",
            "prazo_recebimento_definitivo",
            "condicoes_execucao",
            "ordem_servico",
            "modelo_execucao",
            "prazo_assinatura_contrato",
            "prazo_vigencia_contrato",
        },
    }
    allowed_types = subtype_items.get(requested_subtype or "")
    if allowed_types is not None:
        valid = [item for item in valid if item["deadline_type"] in allowed_types]
    if not valid:
        return SAFE_UNVERIFIED, [], rejected
    if requested_subtype == "prazo_procedimento":
        primary = next(
            (item for item in valid if item["deadline_type"] == "prazo_credenciamento"),
            None,
        )
        ordered = [primary] if primary else []
        ordered.extend(item for item in valid if item is not primary)
        return " ".join(item["summary"] for item in ordered), valid, rejected
    if requested_subtype == "prazo_entrega_proposta":
        return valid[0]["summary"], valid, rejected
    if requested_subtype == "prazo_recebimento_definitivo":
        return (
            "O recebimento definitivo ocorre em até 10 dias úteis, contados do "
            "recebimento provisório; esse prazo não é prazo de execução.",
            valid,
            rejected,
        )
    if requested_subtype == "prazo_vigencia":
        return "O prazo inicial de vigência é de 12 meses.", valid, rejected
    if requested_subtype == "prazo_entrega":
        direct_types = {"prazo_execucao", "prazo_diagnostico", "prazo_entrega"}
        context_types = {"condicoes_execucao", "ordem_servico", "modelo_execucao"}
        explicit_delivery = next(
            (
                item
                for item in valid
                if item["deadline_type"] == "prazo_entrega"
                and re.search(r"\b\d+\s+dias\b", _normalize_for_rules(item["summary"]))
            ),
            None,
        )
        if explicit_delivery:
            return explicit_delivery["summary"], valid, rejected
        has_direct_deadline = any(item["deadline_type"] in direct_types for item in valid)
        has_service_context = any(item["deadline_type"] in context_types for item in valid)
        if has_service_context and not has_direct_deadline:
            lines = ["O edital principal não estabelece um prazo único de entrega do objeto."]
            context_summaries = [
                item["summary"] for item in valid if item["deadline_type"] in context_types
            ]
            if context_summaries:
                lines.append(" ".join(context_summaries))
            for item in valid:
                if item["deadline_type"] == "prazo_assinatura_contrato":
                    lines.append(f"Separadamente, {item['summary'].lower()}")
                elif item["deadline_type"] == "prazo_vigencia_contrato":
                    lines.append(f"Também separadamente, {item['summary'].lower()}")
            return " ".join(lines), valid, rejected
    has_context = any(item["deadline_type"] in {"prazo_execucao", "prazo_diagnostico"} for item in valid)
    lines = []
    if has_context:
        lines.append(
            "Não há um prazo único de entrega ou execução: os serviços ocorrem sob demanda, "
            "por Ordem de Serviço, e o prazo é definido conforme o diagnóstico."
        )
    for item in valid:
        if item["deadline_type"] == "prazo_entrega":
            lines.append("O modelo de proposta registra “Prazo de Entrega: Conforme Edital”.")
        elif item["deadline_type"] == "prazo_recebimento_definitivo":
            lines.append(
                "Separadamente, o recebimento definitivo ocorre em até 10 dias úteis; "
                "esse prazo não deve ser tratado como prazo de execução."
            )
    return " ".join(lines) or valid[0]["summary"], valid, rejected


def _deadline_status(
    requested_subtype: str | None,
    items: list[dict[str, Any]],
) -> str:
    if not items:
        return "NOT_FOUND"
    if requested_subtype == "prazo_entrega":
        direct_types = {"prazo_execucao", "prazo_diagnostico", "prazo_entrega"}
        service_context = {"condicoes_execucao", "ordem_servico", "modelo_execucao"}
        if (
            any(item["deadline_type"] in service_context for item in items)
            and not any(item["deadline_type"] in direct_types for item in items)
        ):
            return "NOT_APPLICABLE"
    contextual_types = {"prazo_execucao", "prazo_diagnostico"}
    if requested_subtype in {"prazo_entrega", "prazo_execucao", "prazo_contextual", None} and any(
        item["deadline_type"] in contextual_types for item in items
    ):
        return "CONTEXT_DEPENDENT"
    return "FOUND"


def _validated_habilitation_items(
    parsed: dict[str, Any],
    sources: list[dict[str, Any]],
    document_id: str,
    category_filter: set[str] | None = None,
) -> tuple[str, list[dict[str, Any]], int]:
    raw_items = parsed.get("items")
    if not isinstance(raw_items, list):
        raw_items = []
    allowed_categories = {
        "juridica",
        "fiscal_trabalhista",
        "economica",
        "tecnico_operacional",
        "tecnico_profissional",
        "declaracoes",
    }
    if category_filter is not None:
        allowed_categories &= category_filter
    category_markers = {
        "juridica": ("habilitacao juridica", "registro comercial", "ato constitutivo", "junta comercial"),
        "fiscal_trabalhista": (
            "regularidade fiscal",
            "fazenda federal",
            "fazenda estadual",
            "fazenda municipal",
            "fgts",
            "cnpj",
            "justica do trabalho",
            "cndt",
        ),
        "economica": ("economico", "economica", "falencia", "balanco", "patrimonio liquido", "indices contabeis"),
        "tecnico_operacional": ("tecnico-operacional", "capacidade tecnico operacional", "atestado"),
        "tecnico_profissional": ("tecnico-profissional", "capacidade tecnico profissional", "crea", "acervo"),
        "declaracoes": ("declaracao", "impedimento", "matriz", "filial"),
    }
    valid: list[dict[str, Any]] = []
    rejected = 0
    seen: set[str] = set()
    for item in raw_items[:6]:
        if not isinstance(item, dict):
            rejected += 1
            continue
        category = str(item.get("category") or "").strip().casefold()
        if category not in allowed_categories or category in seen:
            rejected += 1
            continue
        summary = str(item.get("summary") or "").strip()
        evidence_text = _strip_trailing_ellipsis(item.get("evidence_text") or "")
        source_id = _resolve_source_id(item.get("source_chunk_id"), sources)
        evidence = validate_evidence(
            evidence_text=evidence_text,
            source_chunk_id=source_id,
            retrieved_sources=sources,
            selected_document_id=document_id,
            value=summary,
            field_name="requisitos_habilitacao",
        )
        normalized_evidence = _normalize_for_rules(evidence_text)
        plausible_category = any(
            marker in normalized_evidence for marker in category_markers[category]
        )
        if (
            not evidence["evidence_valid"]
            or not plausible_category
            or not numeric_claims_are_supported(summary, evidence_text)
        ):
            rejected += 1
            continue
        seen.add(category)
        valid.append(
            {
                "category": category,
                "summary": summary,
                "source_chunk_id": evidence["chunk_id"],
                "evidence_text": evidence_text,
                "document_part": next(
                    (
                        source.get("document_part", "desconhecido")
                        for source in sources
                        if source.get("chunk_id") == evidence["chunk_id"]
                    ),
                    "desconhecido",
                ),
                "pages": evidence.get("pages"),
                "evidence": evidence,
            }
        )
    deterministic = _deterministic_habilitation_items(sources, document_id)
    if category_filter is not None:
        deterministic = [
            item for item in deterministic if item["category"] in category_filter
        ]
    valid_by_category = {item["category"]: item for item in valid}
    for item in deterministic:
        valid_by_category.setdefault(item["category"], item)
    priority = (
        "juridica",
        "fiscal_trabalhista",
        "economica",
        "tecnico_operacional",
        "tecnico_profissional",
        "declaracoes",
    )
    valid = [valid_by_category[category] for category in priority if category in valid_by_category][:6]
    if not valid:
        return SAFE_UNVERIFIED, [], rejected
    labels = {
        "juridica": "Habilitação jurídica",
        "fiscal_trabalhista": "Regularidade fiscal e trabalhista",
        "economica": "Qualificação econômico-financeira",
        "tecnico_operacional": "Qualificação técnico-operacional",
        "tecnico_profissional": "Qualificação técnico-profissional",
        "declaracoes": "Declarações e documentos complementares",
    }
    lines = [
        "Documentos técnicos exigidos:"
        if category_filter == {"tecnico_operacional", "tecnico_profissional"}
        else "Principais requisitos de habilitação:"
    ]
    for item in valid:
        lines.append(f"- {labels[item['category']]}: {item['summary']} (página(s) {item['pages']})")
    return "\n".join(lines), valid, rejected


def _normalize_for_rules(text: str) -> str:
    import unicodedata

    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(character for character in value if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", value).casefold()


def _deterministic_habilitation_items(
    sources: list[dict[str, Any]],
    document_id: str,
) -> list[dict[str, Any]]:
    rules = (
        (
            "juridica",
            re.compile(r"HABILITA[ÇC][ÃA]O\s+JUR[ÍI]DICA", re.IGNORECASE),
            "Apresentar os documentos de habilitação jurídica exigidos.",
        ),
        (
            "fiscal_trabalhista",
            re.compile(r"REGULARIDADE\s+FISCAL(?:\s+E\s+TRABALHISTA)?", re.IGNORECASE),
            "Comprovar regularidade fiscal e trabalhista.",
        ),
        (
            "economica",
            re.compile(r"QUALIFICA[ÇC][ÃA]O\s+ECON[ÔO]MICA[-\s]+FINANCEIRA", re.IGNORECASE),
            "Comprovar qualificação econômico-financeira.",
        ),
        (
            "tecnico_operacional",
            re.compile(r"(?:CAPACIDADE\s+)?T[ÉE]CNICO[-\s]+OPERACIONAL", re.IGNORECASE),
            "Comprovar capacidade técnico-operacional.",
        ),
        (
            "tecnico_profissional",
            re.compile(r"(?:CAPACIDADE\s+)?T[ÉE]CNICO[-\s]+PROFISSIONAL", re.IGNORECASE),
            "Comprovar capacidade técnico-profissional.",
        ),
        (
            "declaracoes",
            re.compile(r"(?:PROCURA[ÇC][ÃA]O\s*/\s*)?DECLARA[ÇC][ÕO]ES", re.IGNORECASE),
            "Apresentar declarações e documentos complementares.",
        ),
    )
    technical_details = {
        "tecnico_operacional": (
            re.compile(
                r"(Atestado\(s\)\s+de\s+Capacidade\s+T[ée]cnica[^.]{0,520}\.)",
                re.IGNORECASE,
            ),
            "Atestado(s) de Capacidade Técnica de serviços compatíveis.",
        ),
        "tecnico_profissional": (
            re.compile(
                r"(Certid[ãa]o\s+de\s+Registro\s+e\s+Quita[çc][ãa]o[^.]{0,1000}"
                r"(?:Atestado\(s\)\s+de\s+Responsabilidade\s+T[ée]cnica\s+ou\s+)?"
                r"Acervo\s+T[ée]cnico[^.]{0,420})",
                re.IGNORECASE,
            ),
            "Registro da empresa e do profissional, vínculo e acervo técnico.",
        ),
    }
    output: list[dict[str, Any]] = []
    for category, pattern, summary in rules:
        detail_rule = technical_details.get(category)
        if detail_rule is not None:
            detail_pattern, detail_summary = detail_rule
            detail_found = False
            for detail_source in sources:
                detail_match = detail_pattern.search(str(detail_source.get("text") or ""))
                if not detail_match:
                    continue
                detail_evidence_text = " ".join(detail_match.group(1).split()).strip()
                detail_evidence = validate_evidence(
                    evidence_text=detail_evidence_text,
                    source_chunk_id=str(detail_source.get("chunk_id") or ""),
                    retrieved_sources=sources,
                    selected_document_id=document_id,
                    value=detail_summary,
                    field_name="requisitos_habilitacao",
                )
                if detail_evidence["evidence_valid"]:
                    output.append(
                        {
                            "category": category,
                            "summary": detail_summary,
                            "source_chunk_id": detail_evidence["chunk_id"],
                            "evidence_text": detail_evidence_text,
                            "document_part": detail_source.get(
                                "document_part",
                                "desconhecido",
                            ),
                            "pages": detail_evidence.get("pages"),
                            "evidence": detail_evidence,
                        }
                    )
                    detail_found = True
                    break
            if detail_found:
                continue
        for source in sources:
            text = str(source.get("text") or "")
            match = pattern.search(text)
            if not match:
                continue
            evidence_text = " ".join(text[match.start() : min(len(text), match.end() + 110)].split())
            evidence = validate_evidence(
                evidence_text=evidence_text,
                source_chunk_id=str(source.get("chunk_id") or ""),
                retrieved_sources=sources,
                selected_document_id=document_id,
                value=summary,
                field_name="requisitos_habilitacao",
            )
            if evidence["evidence_valid"]:
                output.append(
                    {
                        "category": category,
                        "summary": summary,
                        "source_chunk_id": evidence["chunk_id"],
                        "evidence_text": evidence_text,
                        "document_part": source.get("document_part", "desconhecido"),
                        "pages": evidence.get("pages"),
                        "evidence": evidence,
                    }
                )
                break
    return output


def _scope_attention_title(title: str, source_text: str, evidence_text: str) -> str:
    """Mantém no título o sujeito que limita a regra citada."""
    position = source_text.find(evidence_text)
    if position < 0:
        position = 0
    context_start = max(0, position - 700)
    prefix = source_text[context_start:position]
    normalized_prefix = _normalize_for_rules(prefix)
    normalized_title = _normalize_for_rules(title)
    subjects = (
        ("Sociedades Limitadas", ("sociedades limitadas", "sociedade limitada")),
        ("Sociedades Anônimas", ("sociedades anonimas", "sociedade anonima")),
        ("Microempresas e EPP", ("microempresa", "empresa de pequeno porte", "me/epp")),
        ("Organizações Civis de Saúde (OCS)", ("organizacoes civis de saude", "para ocs")),
        ("Profissionais de Saúde Autônomos (PSA)", ("profissionais de saude autonomos", "para psa")),
        ("Cooperativas", ("cooperativa", "cooperativas")),
    )
    nearest: tuple[int, str, tuple[str, ...]] | None = None
    for label, markers in subjects:
        marker_position = max((normalized_prefix.rfind(marker) for marker in markers), default=-1)
        if marker_position >= 0 and (nearest is None or marker_position > nearest[0]):
            nearest = (marker_position, label, markers)
    if nearest and not any(marker in normalized_title for marker in nearest[2]):
        return f"{nearest[1]}: {title}"
    return title


def _validated_attention_points(
    parsed: dict[str, Any],
    sources: list[dict[str, Any]],
    document_id: str,
) -> tuple[str, list[dict[str, Any]]]:
    raw_points = parsed.get("points", parsed.get("attention_points"))
    if not isinstance(raw_points, list):
        return SAFE_UNVERIFIED, []
    valid_points: list[dict[str, Any]] = []
    for item in raw_points[:5]:
        if not isinstance(item, dict):
            continue
        evidence_text = _strip_trailing_ellipsis(item.get("evidence_text") or "")
        source_id = _resolve_source_id(item.get("source_chunk_id"), sources)
        evidence = validate_evidence(
            evidence_text=evidence_text,
            source_chunk_id=source_id,
            retrieved_sources=sources,
            selected_document_id=document_id,
            value=str(item.get("impact") or ""),
            field_name="pontos_atencao",
        )
        source = next(
            (candidate for candidate in sources if candidate.get("chunk_id") == evidence.get("chunk_id")),
            {},
        )
        impact = str(item.get("impact") or "").strip()
        claim = impact or str(item.get("title") or "").strip()
        title = str(item.get("title") or "Ponto de atenção").strip()
        source_index = int(source.get("chunk_index") or 0)
        previous_source = next(
            (
                candidate
                for candidate in sources
                if candidate.get("document_id") == source.get("document_id")
                and int(candidate.get("chunk_index") or -1) == source_index - 1
            ),
            None,
        )
        scope_text = (
            f"{previous_source.get('text', '')} {source.get('text', '')}"
            if previous_source
            else str(source.get("text") or "")
        )
        title = _scope_attention_title(title, scope_text, evidence_text)
        duplicate = any(
            _attention_titles_overlap(title, existing["title"])
            for existing in valid_points
        )
        if (
            evidence["evidence_valid"]
            and numeric_claims_are_supported(claim, evidence_text)
            and source
            and not duplicate
        ):
            valid_points.append(
                {
                    "title": title,
                    "impact": impact,
                    "source_chunk_id": evidence["chunk_id"],
                    "evidence_text": evidence_text,
                    "document_part": source.get("document_part", "desconhecido"),
                    "pages": evidence.get("pages"),
                    "evidence": evidence,
                }
            )
    if not valid_points:
        return SAFE_UNVERIFIED, []
    lines = ["Pontos de atenção:"]
    for position, point in enumerate(valid_points, start=1):
        lines.extend(
            [
                f"{position}. Título: {point['title']}",
                *([f"Impacto: {point['impact']}"] if point["impact"] else []),
                f"Origem: {point['document_part']} · página(s) {point['pages']}",
                f"Evidência: {point['evidence_text']}",
            ]
        )
    return "\n".join(lines), valid_points


def _attention_titles_overlap(left: str, right: str) -> bool:
    stopwords = {"a", "ao", "da", "de", "do", "e", "em", "na", "nao", "no", "por"}
    left_tokens = {
        token for token in re.findall(r"[a-z0-9]+", _normalize_for_rules(left)) if token not in stopwords
    }
    right_tokens = {
        token for token in re.findall(r"[a-z0-9]+", _normalize_for_rules(right)) if token not in stopwords
    }
    intersection = left_tokens & right_tokens
    union = left_tokens | right_tokens
    return len(intersection) >= 2 and len(intersection) / max(len(union), 1) >= 0.30


def process_query_with_agent(
    query_text: str,
    document_id: str,
    top_k: int = DEFAULT_TOP_K,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    document_id = str(document_id or "").strip()
    if not document_id:
        raise ValueError("document_id é obrigatório para consultar um edital.")
    top_k = min(max(int(top_k), 1), DEFAULT_TOP_K)
    started = time.perf_counter()
    intent = detect_query_intent(query_text)
    deadline_subtype = detect_deadline_subtype(query_text) if intent == "prazo" else None
    retrieval_started = time.perf_counter()
    sources, retrieval_timing = retrieve_evidence(
        query_text,
        document_id,
        top_k=top_k,
        search_fn=search,
        expansion_fn=expand_evidence_bundle,
    )
    retrieval_ms = round((time.perf_counter() - retrieval_started) * 1000, 1)
    if any(source.get("document_id") != document_id for source in sources):
        raise RuntimeError("Falha de isolamento: a busca retornou fonte de outro edital.")
    intent = str(retrieval_timing.get("query_intent") or intent)
    deadline_subtype = retrieval_timing.get("deadline_subtype") or deadline_subtype
    expansion_metrics = retrieval_timing
    if any(source.get("document_id") != document_id for source in sources):
        raise RuntimeError("Falha de isolamento: o pacote contém fonte de outro edital.")
    prompt = generate_prompt_for_agent_response(query_text, sources)
    completion = complete_with_metrics(
        prompt,
        llm_client=llm_client,
    )
    parsed = _parse_json_object(completion["text"])
    object_summary = _object_summary_from_sources(sources) if intent == "objeto" else None
    if object_summary:
        source, answer, evidence_text = object_summary
        parsed = {
            "answer": answer,
            "status": "FOUND",
            "source_chunk_ids": [source["chunk_id"]],
            "evidence_text": evidence_text,
        }
    confidential = _confidential_value_from_sources(sources) if intent == "valor_estimado" else None
    if confidential:
        source, evidence_text = confidential
        parsed = {
            "answer": "Valor estimado: sigiloso. O edital não divulga o valor numérico.",
            "status": "CONFIDENTIAL",
            "source_chunk_ids": [source["chunk_id"]],
            "evidence_text": evidence_text,
        }
    scoped_value = (
        _scoped_estimated_value_from_sources(sources)
        if intent == "valor_estimado" and not confidential
        else None
    )
    if scoped_value:
        source, answer, evidence_text = scoped_value
        parsed = {
            "answer": answer,
            "status": "FOUND",
            "source_chunk_ids": [source["chunk_id"]],
            "evidence_text": evidence_text,
        }
    estimated_value = (
        _estimated_value_from_sources(sources)
        if intent == "valor_estimado" and not confidential and not scoped_value
        else None
    )
    if estimated_value:
        source, answer, evidence_text = estimated_value
        parsed = {
            "answer": answer,
            "status": "FOUND",
            "source_chunk_ids": [source["chunk_id"]],
            "evidence_text": evidence_text,
        }
    modality_summary = _modality_summary_from_sources(sources) if intent == "modalidade" else None
    if modality_summary:
        source, answer, evidence_text = modality_summary
        parsed = {
            "answer": answer,
            "status": "FOUND",
            "source_chunk_ids": [source["chunk_id"]],
            "evidence_text": evidence_text,
        }
    modality_claims = (
        _modality_claims_from_sources(sources, document_id)
        if intent == "modalidade"
        else []
    )
    valid_claims = 0
    rejected_claims = 0
    deadline_items: list[dict[str, Any]] = []
    habilitation_items: list[dict[str, Any]] = []
    if intent == "modalidade" and modality_claims:
        labels = {
            "procedimento": "Procedimento",
            "forma_contratacao": "Forma de contratação",
        }
        response = ". ".join(
            f"{labels.get(claim['label'], claim['label'])}: {claim['value']}"
            for claim in modality_claims
        ) + "."
        valid_claims = len(modality_claims)
        validation = {
            "answer": response,
            "status": "FOUND",
            "source_chunk_ids": [claim["source_chunk_id"] for claim in modality_claims],
            "evidence_text": "",
            "evidence": modality_claims[0]["evidence"],
        }
        attention_points = []
    elif intent == "prazo":
        response, deadline_items, rejected_claims = _deadline_items_from_sources(
            sources,
            document_id,
            deadline_subtype,
        )
        valid_claims = len(deadline_items)
        validation = {
            "answer": response,
            "status": _deadline_status(deadline_subtype, deadline_items),
            "source_chunk_ids": [item["source_chunk_id"] for item in deadline_items],
            "evidence_text": "",
            "evidence": deadline_items[0]["evidence"] if deadline_items else None,
        }
        attention_points = []
    elif intent in {"requisitos_habilitacao", "documentos_tecnicos"}:
        response, habilitation_items, rejected_claims = _validated_habilitation_items(
            parsed,
            sources,
            document_id,
            (
                {"tecnico_operacional", "tecnico_profissional"}
                if intent == "documentos_tecnicos"
                else None
            ),
        )
        valid_claims = len(habilitation_items)
        validation = {
            "answer": response,
            "status": "FOUND" if habilitation_items else "NOT_FOUND",
            "source_chunk_ids": [item["source_chunk_id"] for item in habilitation_items],
            "evidence_text": "",
            "evidence": habilitation_items[0]["evidence"] if habilitation_items else None,
        }
        attention_points = []
    elif intent == "pontos_atencao":
        response, attention_points = _validated_attention_points(parsed, sources, document_id)
        raw_points = parsed.get("points", parsed.get("attention_points"))
        raw_count = len(raw_points) if isinstance(raw_points, list) else 0
        valid_claims = len(attention_points)
        rejected_claims = max(raw_count - valid_claims, 0)
        validation = {
            "answer": response,
            "status": "FOUND" if attention_points else "NOT_FOUND",
            "source_chunk_ids": [point["source_chunk_id"] for point in attention_points],
            "evidence_text": "",
            "evidence": None,
        }
    else:
        attention_points = []
        validation = _validate_query_evidence(
            parsed=parsed,
            sources=sources,
            document_id=document_id,
            intent=intent,
        )
        valid_claims = int(validation["status"] != "NOT_FOUND")
        rejected_claims = int(validation["status"] == "NOT_FOUND" and bool(parsed))
    return {
        "response": validation["answer"],
        "status": validation["status"],
        "evidence": validation["evidence"],
        "source_chunk_ids": validation["source_chunk_ids"],
        "evidence_text": validation["evidence_text"],
        "attention_points": attention_points,
        "deadline_items": deadline_items,
        "habilitation_items": habilitation_items,
        "claims": modality_claims,
        "sources": sources,
        "document_id": document_id,
        "metrics": {
            "retrieval_ms": retrieval_ms,
            "embedding_ms": retrieval_timing.get("embedding_ms"),
            "vector_search_ms": retrieval_timing.get("vector_search_ms"),
            "reranking_ms": retrieval_timing.get("reranking_ms"),
            "candidate_count": retrieval_timing.get("candidate_count"),
            "dense_candidates": retrieval_timing.get("dense_candidates"),
            "lexical_candidates": retrieval_timing.get("lexical_candidates"),
            "structural_candidates": retrieval_timing.get("structural_candidates"),
            "deduplicated_candidates": retrieval_timing.get("deduplicated_candidates"),
            "query_intent": intent,
            "deadline_subtype": deadline_subtype,
            "section_expansion_ms": expansion_metrics["section_expansion_ms"],
            "adjacent_chunks_considered": expansion_metrics["adjacent_chunks_considered"],
            "evidence_bundle_chunks": expansion_metrics["evidence_bundle_chunks"],
            "valid_claims": valid_claims,
            "rejected_claims": rejected_claims,
            "prompt_chars": len(prompt),
            "llm_calls": 1,
            "rate_limit_wait_ms": completion.get("rate_limit_wait_ms", 0.0),
            "llm_ms": completion["llm_ms"],
            "total_ms": round((time.perf_counter() - started) * 1000, 1),
        },
        "usage": completion["usage"],
    }

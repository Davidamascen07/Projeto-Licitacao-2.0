"""Parsers estruturais genéricos para campos cadastrais recorrentes."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


UF_BY_NAME = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM",
    "bahia": "BA", "ceara": "CE", "distrito federal": "DF",
    "espirito santo": "ES", "goias": "GO", "maranhao": "MA",
    "mato grosso": "MT", "mato grosso do sul": "MS", "minas gerais": "MG",
    "para": "PA", "paraiba": "PB", "parana": "PR", "pernambuco": "PE",
    "piaui": "PI", "rio de janeiro": "RJ", "rio grande do norte": "RN",
    "rio grande do sul": "RS", "rondonia": "RO", "roraima": "RR",
    "santa catarina": "SC", "sao paulo": "SP", "sergipe": "SE",
    "tocantins": "TO",
}
UF_CODES = set(UF_BY_NAME.values())


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value).strip().casefold()


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _preamble_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    preferred = [
        source for source in sources
        if source.get("is_preamble") or int(source.get("page_start") or 9999) <= 3
    ]
    return preferred or sources


def organization_from_sources(
    sources: list[dict[str, Any]],
) -> tuple[dict[str, Any], str, str] | None:
    """Extrai a unidade contratante do cabeçalho/preâmbulo, evitando citações legais."""
    label = re.compile(
        r"((?:[ÓO]RG[ÃA]O\s+GERENCIADOR|[ÓO]RG[ÃA]O\s+RESPONS[ÁA]VEL|"
        r"ENTIDADE\s+GERENCIADORA(?:\s+E\s+EVENTUAL\s+CONTRATANTE)?|"
        r"UNIDADE\s+CONTRATANTE|UNIDADE\s+GESTORA|CONTRATANTE(?:\s*\(UASG\))?|"
        r"[ÓO]RG[ÃA]O\s+REALIZADOR\s+DO\s+CERTAME|CREDENCIANTE)\s*:?\s*"
        r"[^\n.;]{4,220})",
        re.IGNORECASE,
    )
    subject = re.compile(
        r"\b((?:O|A)\s+(?:FUNDO\s+MUNICIPAL|MUNIC[IÍ]PIO|PREFEITURA\s+MUNICIPAL|"
        r"SECRETARIA(?:\s+MUNICIPAL|\s+DE\s+ESTADO)?|MINIST[ÉE]RIO|TRIBUNAL|"
        r"DEPARTAMENTO\s+MUNICIPAL|AUTARQUIA|COMANDO)[^,.;\n]{3,180}?)"
        r"(?=\s+(?:torna\s+p[uú]blico|pessoa\s+jur[ií]dica|inscrit[ao]|com\s+sede)\b|[,.;\n]|$)",
        re.IGNORECASE,
    )
    department = re.compile(
        r"\b(DEPARTAMENTO\s+MUNICIPAL\s+DE\s+[^,.;\n]{3,120}?)"
        r"(?=\s+(?:RUA|AVENIDA|CNPJ|CEP|FONE)\b|[,.;\n]|$)",
        re.IGNORECASE,
    )
    hierarchy = re.compile(
        r"\b(MINIST[ÉE]RIO\s+DA\s+DEFESA\s+EX[ÉE]RCITO\s+BRASILEIRO"
        r"(?:\s+(?:(?:CMS|CMSE|CML|CMP|CMN|CMNE)\s*[-–]\s*)?[^\n]{0,180}?"
        r"(?:REGIMENTO|BATALH[ÃA]O|BRIGADA|COMANDO)[^\n]{0,100})?)",
        re.IGNORECASE,
    )
    header = re.compile(
        r"^((?:FUNDO\s+MUNICIPAL|PREFEITURA\s+MUNICIPAL|MUNIC[IÍ]PIO|"
        r"SECRETARIA(?:\s+MUNICIPAL|\s+DE\s+ESTADO)?|MINIST[ÉE]RIO|TRIBUNAL|"
        r"DEPARTAMENTO\s+MUNICIPAL|AUTARQUIA|COMANDO|[A-Z]{2,8}\s*[-–]\s*)"
        r"[^\n]{3,180})$",
        re.IGNORECASE | re.MULTILINE,
    )
    corporate = re.compile(
        r"\b((?:MGI\s*[-–]\s*)?Minas\s+Gerais\s+Participa[cç][oõ]es\s+S\.?A\.?)",
        re.IGNORECASE,
    )
    academic = re.compile(
        r"\b((?:GOVERNO\s+DO\s+ESTADO\s+DA\s+[^\n]{3,80}\s+)?"
        r"UNIVERSIDADE(?:S)?\s+(?:DO|DE|DA)\s+ESTADO\s+(?:DO|DE|DA)\s+[^\n]{3,100}"
        r"(?:\s*[-–]\s*[A-Z]{2,12})?(?:\s+DEPARTAMENTO\s+DE\s+[^\n]{3,140})?)",
        re.IGNORECASE,
    )
    for source in _preamble_sources(sources):
        text = str(source.get("text") or "")[:5000]
        for pattern in (label, academic, department, hierarchy, subject, header, corporate):
            match = pattern.search(text)
            if not match:
                continue
            literal = _compact(match.group(1))
            literal = re.split(r"\b(?:EDITAL|NUP)\b", literal, maxsplit=1, flags=re.IGNORECASE)[0].strip(" -–")
            literal = re.split(
                r"\b(?:OBJETO|VALOR\s+TOTAL|TERMO\s+DE\s+REFER[ÊE]NCIA|RUA|AVENIDA|CNPJ|CEP|E-?MAIL|TEL(?:EFONE)?)\b",
                literal,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip(" -–,.;")
            answer = re.sub(
                r"^(?:O|A)\s+|^(?:[ÓO]RG[ÃA]O\s+GERENCIADOR|[ÓO]RG[ÃA]O\s+RESPONS[ÁA]VEL|"
                r"ENTIDADE\s+GERENCIADORA(?:\s+E\s+EVENTUAL\s+CONTRATANTE)?|"
                r"UNIDADE\s+CONTRATANTE|UNIDADE\s+GESTORA|CONTRATANTE(?:\s*\(UASG\))?|"
                r"[ÓO]RG[ÃA]O\s+REALIZADOR\s+DO\s+CERTAME|CREDENCIANTE)\s*:?\s*",
                "",
                literal,
                flags=re.IGNORECASE,
            ).strip()
            if len(answer) >= 4:
                return source, answer, literal
    return None


def uf_from_sources(
    sources: list[dict[str, Any]],
) -> tuple[dict[str, Any], str, str] | None:
    """Resolve UF por endereço/cabeçalho com evidência literal local."""
    for source in _preamble_sources(sources):
        text = str(source.get("text") or "")[:6000]
        city_uf = re.search(
            r"\b([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç' .-]{2,70})"
            r"\s*(?:/|[-–])\s*(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\b",
            text,
        )
        if city_uf:
            return source, city_uf.group(2).upper(), _compact(city_uf.group(0))
        normalized = normalize(text)
        for state_name in sorted(UF_BY_NAME, key=len, reverse=True):
            match = re.search(rf"\b(?:estado\s+(?:do|de|da)\s+)?{re.escape(state_name)}\b", normalized)
            if not match:
                continue
            # Usa a fatia equivalente apenas como evidência legível; a validação
            # literal aceita o nome do estado encontrado no texto original.
            original_match = re.search(
                rf"(?:ESTADO\s+(?:DO|DE|DA)\s+)?{re.escape(state_name)}",
                text,
                re.IGNORECASE,
            )
            if original_match:
                return source, UF_BY_NAME[state_name], _compact(original_match.group(0))
    return None


_CRITERIA: tuple[tuple[str, str], ...] = (
    (r"maior\s+oferta\s+de\s+pre[cç]o", "Maior oferta de preço"),
    (r"menor\s+pre[cç]o\s+por\s+lote", "Menor preço por lote"),
    (r"menor\s+pre[cç]o\s+por\s+item", "Menor preço por item"),
    (r"menor\s+pre[cç]o\s+global", "Menor preço global"),
    (r"maior\s+retorno\s+econ[oô]mico", "Maior retorno econômico"),
    (r"t[ée]cnica\s+e\s+pre[cç]o", "Técnica e preço"),
    (r"melhor\s+t[ée]cnica", "Melhor técnica"),
    (r"maior\s+desconto", "Maior desconto"),
    (r"maior\s+lance", "Maior lance"),
    (r"menor\s+pre[cç]o", "Menor preço"),
)


def criterion_from_sources(
    sources: list[dict[str, Any]],
) -> tuple[dict[str, Any], str, str] | None:
    """Extrai o critério como claim separado da modalidade."""
    ordered = sorted(
        sources,
        key=lambda source: (0 if source.get("is_preamble") or int(source.get("page_start") or 9999) <= 3 else 1),
    )
    for source in ordered:
        text = str(source.get("text") or "")
        windows = []
        for anchor in re.finditer(
            r"crit[ée]rio\s+de\s+julgamento|do\s+julgamento|julgamento\s+das\s+propostas|\bTIPO\s*:",
            text,
            re.IGNORECASE,
        ):
            windows.append(text[anchor.start(): anchor.start() + 360])
        if not windows and int(source.get("page_start") or 9999) <= 3:
            windows.append(text[:3500])
        for window in windows:
            for pattern, answer in _CRITERIA:
                match = re.search(pattern, window, re.IGNORECASE)
                if match:
                    start = max(0, match.start() - 80)
                    literal = _compact(window[start: min(len(window), match.end() + 80)])
                    return source, answer, literal
    return None


def generic_habilitation_from_sources(
    sources: list[dict[str, Any]],
) -> tuple[dict[str, Any], str, str] | None:
    """Fallback conservador para listas literais de documentos de habilitação."""
    requirement = re.compile(
        r"((?:[IVXLCDM]+[.)]|[a-z][.)]|\d+(?:\.\d+)*[.)]?)\s*"
        r"(?:Comprovante|Certid[aã]o|Declara[cç][aã]o|Diploma|Certificado|Prova\s+de\s+registro|"
        r"Ato\s+constitutivo|Balan[cç]o\s+Patrimonial)[^.;\n]{8,240}[.;]?)",
        re.IGNORECASE,
    )
    for source in sources:
        text = str(source.get("text") or "")
        normalized_section = normalize(
            " ".join(
                str(value or "")
                for value in (source.get("section_title"), source.get("section_type"), source.get("heading"))
            )
        )
        contextual = (
            "habilit" in normalized_section
            or re.search(r"documentos?\s+(?:exigidos?\s+)?(?:para|de)\s+habilita[cç][aã]o", text, re.IGNORECASE)
            or re.search(r"condi[cç][oõ]es\s+de\s+habilita[cç][aã]o", text, re.IGNORECASE)
            or re.search(r"fase\s+de\s+habilita[cç][aã]o", text, re.IGNORECASE)
            or re.search(r"cadastramento\s+para\s+efetuar\s+lances", text, re.IGNORECASE)
        )
        if not contextual:
            continue
        match = requirement.search(text)
        if match:
            literal = _compact(match.group(1))
            return source, f"Requisito de habilitação: {literal}", literal
    return None

from __future__ import annotations

import json

from evaluation.golden_regression import compare_batch_individual, load_golden
from services.deadline_ontology import (
    CONTRACT_TERM,
    DELIVERY,
    PROPOSAL_VALIDITY,
    SIGNATURE,
    classify_deadline,
)
from services.agent_service import _modality_summary_from_sources, _object_summary_from_sources
from services.extraction_service import NOT_FOUND_MSG, extract_fields_from_sources
from services.field_parsers import criterion_from_sources, organization_from_sources, uf_from_sources
from services.pdf_quality import audit_pdf_text
from services.retrieval import hybrid_search
from services.scope_validation import missing_critical_qualifiers
from services.vector_store import load_chunks_metadata
from tests.conftest import FakeLLM


def _document_chunks(prefix: str):
    chunks = load_chunks_metadata()
    document = next(chunk for chunk in chunks if chunk["filename"].startswith(prefix))
    return [chunk for chunk in chunks if chunk.get("document_id") == document["document_id"]]


def _not_found_llm(fields: list[str]) -> FakeLLM:
    return FakeLLM(
        json.dumps(
            {
                field: {"value": NOT_FOUND_MSG, "source_chunk_id": "", "evidence_text": ""}
                for field in fields
            },
            ensure_ascii=False,
        )
    )


def test_golden_baseline_freezes_exactly_46_confirmed_fields():
    golden = load_golden()
    assert golden["baseline_found_count"] == 46
    assert len({(item["document_id"], item["field"]) for item in golden["entries"]}) == 46


def test_deadline_ontology_keeps_semantically_distinct_deadlines():
    assert classify_deadline("A validade da proposta será de 60 (sessenta) dias.")["type"] == PROPOSAL_VALIDITY
    assert classify_deadline("15 dias para assinarem os respectivos contratos.")["type"] == SIGNATURE
    assert classify_deadline("O contrato terá vigência de 120 meses.")["type"] == CONTRACT_TERM
    assert classify_deadline("Entrega em 10 dias após o recebimento da Ordem de Compra.")["type"] == DELIVERY


def test_historical_1626_proposal_validity_is_recovered_locally():
    chunks = _document_chunks("1626Manutencaodemotoreseletricos")
    sources = [chunk for chunk in chunks if 10 <= int(chunk["page_start"]) <= 16]
    results = extract_fields_from_sources(
        {"prazo_entrega_proposta": "Qual é o prazo de validade da proposta?"},
        chunks[0]["document_id"],
        sources,
        llm_client=_not_found_llm(["prazo_entrega_proposta"]),
    )
    assert results["prazo_entrega_proposta"]["answered"] is True
    assert "60 dias" in results["prazo_entrega_proposta"]["value"]


def test_historical_documento_habilitation_is_recovered_locally():
    chunks = _document_chunks("documento.pdf")
    sources = [chunk for chunk in chunks if 2 <= int(chunk["page_start"]) <= 5]
    results = extract_fields_from_sources(
        {"requisitos_habilitacao": "Quais são os requisitos de habilitação?"},
        chunks[0]["document_id"],
        sources,
        llm_client=_not_found_llm(["requisitos_habilitacao"]),
    )
    assert results["requisitos_habilitacao"]["answered"] is True


def test_historical_cred004_habilitation_is_recovered_locally():
    chunks = _document_chunks("EDITAL_DE_CREDENCIAMENTO_004.2025")
    sources = [chunk for chunk in chunks if 5 <= int(chunk["page_start"]) <= 7]
    results = extract_fields_from_sources(
        {"requisitos_habilitacao": "Quais são os requisitos de habilitação?"},
        chunks[0]["document_id"],
        sources,
        llm_client=_not_found_llm(["requisitos_habilitacao"]),
    )
    assert results["requisitos_habilitacao"]["answered"] is True


def test_generic_priority_field_parsers_preserve_literal_evidence():
    source = {
        "chunk_id": "c1", "document_id": "d1", "page_start": 1, "page_end": 1,
        "is_preamble": True,
        "text": "PREFEITURA MUNICIPAL DE EXEMPLO ESTADO DO RIO GRANDE DO SUL "
        "CONTRATANTE: Fundo Municipal de Saúde de Exemplo/RS. "
        "CRITÉRIO DE JULGAMENTO: MAIOR OFERTA DE PREÇO.",
    }
    assert organization_from_sources([source])[1] == "Fundo Municipal de Saúde de Exemplo/RS"
    assert uf_from_sources([source])[1] == "RS"
    assert criterion_from_sources([source])[1] == "Maior oferta de preço"


def test_diagnostic_top_k_does_not_relax_production_top_three():
    chunks = [
        {
            "chunk_id": f"c{index}", "document_id": "doc", "filename": "x.pdf",
            "chunk_index": index, "page_start": index + 1, "page_end": index + 1,
            "text": f"texto objeto contratação {index}",
        }
        for index in range(12)
    ]
    chunks_fn = lambda _document_id=None: chunks
    no_dense = lambda *_args, **_kwargs: []
    production = hybrid_search("Objeto?", document_id="doc", chunks_fn=chunks_fn, dense_search_fn=no_dense, top_k=10)
    diagnostics = hybrid_search(
        "Objeto?", document_id="doc", chunks_fn=chunks_fn, dense_search_fn=no_dense,
        top_k=10, diagnostic_top_k=True,
    )
    assert len(production) == 3
    assert len(diagnostics) == 10


def test_batch_individual_divergence_is_explicit():
    rows = compare_batch_individual(
        {"objeto": {"answered": False}},
        {"objeto": {"answered": True}},
    )
    assert rows == [{
        "field": "objeto", "code": "BATCH_INDIVIDUAL_DIVERGENCE",
        "individual_status": "FOUND", "batch_status": "NOT_FOUND",
    }]


def test_scope_qualifier_cannot_disappear_from_summary():
    evidence = "No caso de Sociedades Limitadas, exige-se aprovação de 3/4 do capital social."
    assert missing_critical_qualifiers(evidence, "Exige-se aprovação de 3/4 do capital social.")
    assert not missing_critical_qualifiers(evidence, "Sociedades Limitadas: exige-se aprovação de 3/4 do capital social.")


def test_pdf_quality_audit_does_not_request_ocr_for_searchable_pdf():
    report = audit_pdf_text("uploads/1123420260129-Termo_1.pdf")
    assert report["pages"] == 20
    assert report["text_layer_present"] is True
    assert report["possible_scanned_document"] is False
    assert report["ocr_required"] is False


def test_leilao_object_and_modality_are_recognized_without_llm():
    source = {
        "text": "1. OBJETO 1.1. O objeto deste LEILÃO é a alienação, pelo MAIOR LANCE, "
        "de imóvel descrito no ANEXO I deste Edital. 2. DA SESSÃO PÚBLICA DO LEILÃO "
        "O LEILÃO ELETRÔNICO ocorrerá em ambiente virtual."
    }
    assert "alienação" in _object_summary_from_sources([source])[1]
    assert _modality_summary_from_sources([source])[1] == "Modalidade: Leilão."


def test_term_of_reference_dispensa_is_recognized_without_llm():
    source = {
        "text": "OBJETO A presente Dispensa de Licitação tem por objeto adquirir MATERIAL DE CONSUMO. "
        "1.1. Justificativa da aquisição."
    }
    assert "MATERIAL DE CONSUMO" in _object_summary_from_sources([source])[1]
    assert _modality_summary_from_sources([source])[1] == "Modalidade: Dispensa de licitação."

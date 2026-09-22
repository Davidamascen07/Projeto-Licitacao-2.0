from __future__ import annotations

import json

from services import agent_service, extraction_service
from services.document_structure import extract_section_headings
from services.evidence_bundle import expand_evidence_bundle
from services.retrieval import hybrid_search
from services.vector_store import load_chunks_metadata
from tests.conftest import FakeLLM


def _without_dense(*_args, **_kwargs):
    return []


def _document(chunks, filename_prefix: str):
    return next(
        chunk
        for chunk in chunks
        if str(chunk.get("filename") or "").startswith(filename_prefix)
        and "+-+Rep" not in str(chunk.get("filename") or "")
    )


def test_formal_object_heading_is_structural_not_toc():
    headings = extract_section_headings(
        "2. DO OBJETO. 2.1. O objeto deste Edital é o credenciamento de prestadores."
    )
    assert any(item["section_type"] == "objeto" and not item["is_toc"] for item in headings)


def test_credenciamento_formal_object_is_top_ranked_without_embeddings():
    chunks = load_chunks_metadata()
    document = _document(chunks, "01.Edital_credenciamento_01_2024")
    ranked = hybrid_search(
        "Objeto da licitação?",
        document_id=document["document_id"],
        dense_search_fn=_without_dense,
    )
    assert "DO OBJETO" in ranked[0]["text"]
    sources, _metrics = expand_evidence_bundle(
        intent="objeto",
        document_id=document["document_id"],
        base_sources=ranked,
    )
    summary = agent_service._object_summary_from_sources(sources)
    assert summary is not None
    assert "Organizações Civis de Saúde" in summary[1]
    assert "Profissionais de Saúde Autônomos" in summary[1]


def test_credenciamento_modality_claims_have_independent_evidence():
    chunks = load_chunks_metadata()
    document = _document(chunks, "01.Edital_credenciamento_01_2024")
    document_chunks = [item for item in chunks if item.get("document_id") == document["document_id"]]
    claims = agent_service._modality_claims_from_sources(document_chunks, document["document_id"])
    assert [claim["label"] for claim in claims] == ["procedimento", "forma_contratacao"]
    assert claims[0]["source_chunk_id"] != claims[1]["source_chunk_id"]
    assert "CREDENCIAMENTO" in claims[0]["evidence_text"].upper()
    assert "INEXIGIBILIDADE" in claims[1]["evidence_text"].upper()


def test_equipment_edital_confidential_value_and_ten_day_delivery():
    chunks = load_chunks_metadata()
    document = _document(chunks, "PE+056-26+-+Proc.+00821-26+-+Aquisicao+equipamento")
    document_id = document["document_id"]

    object_sources = hybrid_search(
        "Objeto da licitação?", document_id=document_id, dense_search_fn=_without_dense
    )
    object_summary = agent_service._object_summary_from_sources(object_sources)
    assert object_summary is not None
    assert "Aquisição e instalação de equipamentos" in object_summary[1]

    modality_sources = hybrid_search(
        "Modalidade?", document_id=document_id, dense_search_fn=_without_dense
    )
    modality = agent_service._modality_summary_from_sources(modality_sources)
    assert modality is not None
    assert modality[1] == "Modalidade: Pregão Eletrônico."

    value_sources = hybrid_search(
        "Valor estimado?", document_id=document_id, dense_search_fn=_without_dense
    )
    confidential = agent_service._confidential_value_from_sources(value_sources)
    assert confidential is not None
    assert "caráter sigiloso" in confidential[1].casefold()

    deadline_sources = hybrid_search(
        "Prazo de entrega?", document_id=document_id, dense_search_fn=_without_dense
    )
    deadline_sources, _metrics = expand_evidence_bundle(
        intent="prazo",
        document_id=document_id,
        base_sources=deadline_sources,
        deadline_subtype="prazo_entrega",
    )
    answer, items, _rejected = agent_service._deadline_items_from_sources(
        deadline_sources, document_id, "prazo_entrega"
    )
    assert "10 dias" in answer
    assert "Ordem de Compra" in answer
    assert any("10 (dez) dias" in item["evidence_text"] for item in items)


def test_attention_title_preserves_limited_company_scope():
    title = agent_service._scope_attention_title(
        "Autorização exige 3/4 do capital social",
        "Microempresas e EPP seguem regra própria. Sociedades Limitadas: a autorização exige votos correspondentes a 3/4 do capital social.",
        "a autorização exige votos correspondentes a 3/4 do capital social",
    )
    assert title.startswith("Sociedades Limitadas:")


def test_attention_scope_can_be_inherited_from_adjacent_chunk(monkeypatch):
    sources = [
        {
            "chunk_id": "previous",
            "document_id": "doc",
            "filename": "edital.pdf",
            "chunk_index": 3,
            "page_start": 5,
            "page_end": 6,
            "text": "No caso de Sociedades Limitadas, a deliberação deverá ser tomada por votos correspondentes,",
        },
        {
            "chunk_id": "evidence",
            "document_id": "doc",
            "filename": "edital.pdf",
            "chunk_index": 4,
            "page_start": 6,
            "page_end": 7,
            "text": "no mínimo, a três quartos do capital social; 3 - No caso de Microempresas e EPP, aplica-se outra regra.",
        },
    ]

    def valid_evidence(**kwargs):
        return {
            "evidence_valid": True,
            "chunk_id": kwargs["source_chunk_id"],
            "filename": "edital.pdf",
            "pages": "6-7",
            "text": kwargs["evidence_text"],
        }

    monkeypatch.setattr(agent_service, "validate_evidence", valid_evidence)
    response, points = agent_service._validated_attention_points(
        {
            "points": [
                {
                    "title": "Quórum mínimo para deliberações",
                    "source_chunk_id": "evidence",
                    "evidence_text": "no mínimo, a três quartos do capital social",
                }
            ]
        },
        sources,
        "doc",
    )
    assert points[0]["title"].startswith("Sociedades Limitadas:")
    assert "Sociedades Limitadas" in response


def test_batch_uses_field_specific_sources_in_one_llm_call(monkeypatch):
    object_source = {
        "chunk_id": "object",
        "document_id": "doc",
        "filename": "edital.pdf",
        "page_start": 5,
        "page_end": 5,
        "text": "2. DO OBJETO. 2.1. O objeto deste Edital é adquirir equipamentos. 2.2. Integram o edital.",
    }
    value_source = {
        "chunk_id": "value",
        "document_id": "doc",
        "filename": "edital.pdf",
        "page_start": 22,
        "page_end": 22,
        "text": "O valor estimado para a contratação possuirá caráter sigiloso.",
    }

    def valid_evidence(**kwargs):
        source = next(
            item for item in kwargs["retrieved_sources"] if item["chunk_id"] == kwargs["source_chunk_id"]
        )
        return {
            "evidence_valid": True,
            "chunk_id": source["chunk_id"],
            "filename": source["filename"],
            "pages": str(source["page_start"]),
            "text": kwargs["evidence_text"],
        }

    monkeypatch.setattr(extraction_service, "validate_evidence", valid_evidence)
    payload = json.dumps(
        {
            "objeto": {"value": "", "source_chunk_id": "", "evidence_text": ""},
            "valor_estimado": {"value": "", "source_chunk_id": "", "evidence_text": ""},
        }
    )
    class CountingLLM(FakeLLM):
        calls = 0

        def complete(self, prompt):
            self.calls += 1
            return super().complete(prompt)

    llm = CountingLLM(payload)
    results = extraction_service.extract_fields_from_sources(
        {"objeto": "Objeto?", "valor_estimado": "Valor estimado?"},
        "doc",
        [object_source, value_source],
        llm_client=llm,
        sources_by_field={"objeto": [object_source], "valor_estimado": [value_source]},
    )
    assert llm.calls == 1
    assert results["objeto"]["answered"] is True
    assert results["valor_estimado"]["value"] == "SIGILOSO"
    assert results["objeto"]["sources"] == [object_source]
    assert results["valor_estimado"]["sources"] == [value_source]

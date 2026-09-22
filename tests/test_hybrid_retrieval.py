from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from services import agent_service
from services.retrieval import (
    annotate_document_structure,
    detect_deadline_subtype,
    detect_query_intent,
    expand_query_terms,
    hybrid_search,
    retrieval_quality_metrics,
)
from tests.conftest import FakeEmbeddingModel


def _chunk(
    chunk_id: str,
    text: str,
    index: int,
    *,
    document_id: str = "doc-1",
    page: int | None = None,
) -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "filename": f"{document_id}.pdf",
        "chunk_index": index,
        "page_start": page or index + 1,
        "page_end": page or index + 1,
        "text": text,
    }


def _fake_dense(rows):
    def search(_query, *, top_k, document_id, embedding_model=None, timing=None):
        assert document_id == "doc-1"
        if timing is not None:
            timing.update({"embedding_ms": 1.0, "vector_search_ms": 2.0})
        return [{**row, "retrieval_score": 0.90 - position * 0.01} for position, row in enumerate(rows[:top_k])]

    return search


@pytest.mark.parametrize(
    ("query", "intent"),
    [
        ("Objeto da licitação?", "objeto"),
        ("Qual o orçamento sigiloso?", "valor_estimado"),
        ("Data de abertura da sessão", "data_abertura"),
        ("Liste até 5 pontos de atenção do edital", "pontos_atencao"),
        ("Explique este equipamento", "consulta_livre"),
    ],
)
def test_detect_query_intent_accepts_accents_and_variations(query, intent):
    assert detect_query_intent(query) == intent


def test_exact_object_and_confidential_value_reach_top_three():
    correct = _chunk(
        "cover",
        "OBJETO: contratação de manutenção. VALOR ESTIMADO: SIGILOSO.",
        0,
        page=1,
    )
    incidental = [
        _chunk(f"other-{index}", f"O valor do contrato e o objeto citado na cláusula {index}.", index + 1)
        for index in range(20)
    ]
    chunks = [correct, *incidental]
    dense = _fake_dense(incidental + [correct])

    object_rows = hybrid_search(
        "Objeto da licitação?",
        document_id="doc-1",
        top_k=3,
        dense_search_fn=dense,
        chunks_fn=lambda _document_id: chunks,
    )
    value_rows = hybrid_search(
        "Valor estimado?",
        document_id="doc-1",
        top_k=3,
        dense_search_fn=dense,
        chunks_fn=lambda _document_id: chunks,
    )

    assert object_rows[0]["chunk_id"] == "cover"
    assert value_rows[0]["chunk_id"] == "cover"
    assert value_rows[0]["exact_match_score"] == 1.0
    assert len(value_rows) == 3


def test_procedure_deadline_expansion_recovers_credenciamento_chunk():
    correct = _chunk(
        "credenciamento-deadline",
        (
            "3. DA PARTICIPAÇÃO NO CREDENCIAMENTO. 3.1. O prazo para credenciamento "
            "iniciar-se-á na publicação no PNCP. 3.1.1. O presente Edital vigorará por "
            "PRAZO INDETERMINADO."
        ),
        3,
        page=6,
    )
    incidental = [
        _chunk(
            f"incidental-{index}",
            f"A obrigação contratual possui prazo administrativo número {index}.",
            index + 10,
            page=index + 20,
        )
        for index in range(20)
    ]

    rows = hybrid_search(
        "Qual o prazo da licitação?",
        document_id="doc-1",
        top_k=3,
        dense_search_fn=_fake_dense(incidental + [correct]),
        chunks_fn=lambda _document_id: [correct, *incidental],
    )

    assert detect_deadline_subtype("Qual o prazo da licitação?") == "prazo_procedimento"
    assert "prazo para credenciamento" in expand_query_terms("Qual o prazo da licitação?", "prazo")
    assert rows[0]["chunk_id"] == "credenciamento-deadline"
    assert rows[0]["exact_match_score"] == 1.0
    assert rows[0]["rrf_score"] > 0


def test_synonym_expansion_recovers_scoped_value_and_credenciamento_modality():
    value = _chunk(
        "resources",
        "5. DOS RECURSOS FINANCEIROS. Para OCS, no valor de R$ 950.000,00 - Empenho Estimativo.",
        10,
        page=13,
    )
    modality = _chunk(
        "procedure",
        "EDITAL DE CREDENCIAMENTO. Publicação do ato que autoriza a Inexigibilidade de Licitação no PNCP.",
        11,
        page=14,
    )
    incidental = [_chunk(f"other-{index}", "Cláusula administrativa sem o campo consultado.", index) for index in range(18)]
    chunks = [value, modality, *incidental]

    value_rows = hybrid_search(
        "Qual o valor estimado?",
        document_id="doc-1",
        dense_search_fn=_fake_dense(incidental + [value, modality]),
        chunks_fn=lambda _document_id: chunks,
    )
    modality_rows = hybrid_search(
        "Qual a modalidade?",
        document_id="doc-1",
        dense_search_fn=_fake_dense(incidental + [value, modality]),
        chunks_fn=lambda _document_id: chunks,
    )

    assert value_rows[0]["chunk_id"] == "resources"
    assert modality_rows[0]["chunk_id"] == "procedure"


def test_hybrid_search_requires_scope_and_never_returns_other_document():
    with pytest.raises(ValueError, match="document_id"):
        hybrid_search(
            "valor",
            document_id=None,
            dense_search_fn=lambda *_args, **_kwargs: [],
            chunks_fn=lambda _document_id: [],
        )

    with pytest.raises(RuntimeError, match="isolamento"):
        hybrid_search(
            "valor",
            document_id="doc-1",
            dense_search_fn=lambda *_args, **_kwargs: [],
            chunks_fn=lambda _document_id: [_chunk("wrong", "valor", 0, document_id="doc-2")],
        )


def test_candidate_metrics_are_local_and_final_sources_are_capped():
    chunks = [_chunk(f"c-{index}", f"valor estimado informação {index}", index) for index in range(25)]
    timing = {}
    rows = hybrid_search(
        "Valor estimado?",
        document_id="doc-1",
        top_k=99,
        candidate_size=15,
        timing=timing,
        dense_search_fn=_fake_dense(chunks),
        chunks_fn=lambda _document_id: chunks,
    )

    assert len(rows) == 3
    assert timing["dense_candidates"] == 15
    assert timing["candidate_count"] >= 15
    assert timing["reranking_ms"] >= 0


def test_retrieval_quality_metrics_are_separate_from_answer_metrics():
    rows = [{"chunk_id": "wrong"}, {"chunk_id": "right"}, {"chunk_id": "other"}]
    metrics = retrieval_quality_metrics(rows, {"right"}, k=3)
    assert metrics == {"recall@3": 1.0, "mrr": 0.5, "precision@3": pytest.approx(1 / 3)}


def test_legacy_chunks_receive_structure_without_persistence():
    chunks = [
        _chunk("main", "EDITAL OBJETO: contratação.", 0, page=1),
        _chunk("annex", "ANEXO VI – MINUTA DA ATA DE REGISTRO DE PREÇOS", 8, page=80),
        _chunk("continuation", "CLÁUSULA PRIMEIRA - DO OBJETO", 9, page=81),
    ]
    enriched = annotate_document_structure(chunks)

    assert enriched[0]["document_part"] == "edital_principal"
    assert enriched[0]["is_preamble"] is True
    assert enriched[1]["document_part"] == "ata_registro_precos"
    assert enriched[2]["document_part"] == "ata_registro_precos"
    assert "document_part" not in chunks[0]


def test_confidential_value_has_explicit_state_and_one_llm_call(monkeypatch):
    source = _chunk(
        "cover",
        "DADOS DO EDITAL VALOR ESTIMADO: SIGILOSO.",
        0,
        page=1,
    )
    source["document_part"] = "edital_principal"
    source["retrieval_score"] = 0.9

    def fake_search(_query, *, top_k, document_id, timing):
        timing.update(
            {
                "query_intent": "valor_estimado",
                "candidate_count": 20,
                "reranking_ms": 1.0,
                "embedding_ms": 2.0,
                "vector_search_ms": 3.0,
            }
        )
        return [source]

    monkeypatch.setattr(agent_service, "search", fake_search)
    monkeypatch.setattr(
        agent_service,
        "validate_evidence",
        lambda **kwargs: {
            "evidence_valid": True,
            "chunk_id": kwargs["source_chunk_id"],
            "pages": "1",
        },
    )

    class RecordingLLM:
        calls = 0

        def complete(self, _prompt):
            self.calls += 1
            return SimpleNamespace(
                text=json.dumps(
                    {
                        "answer": "não encontrado",
                        "status": "NOT_FOUND",
                        "source_chunk_ids": [],
                        "evidence_text": "",
                    }
                ),
                raw={"usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}},
            )

    llm = RecordingLLM()
    result = agent_service.process_query_with_agent(
        "Valor estimado?",
        "doc-1",
        llm_client=llm,
    )

    assert llm.calls == 1
    assert result["status"] == "CONFIDENTIAL"
    assert result["response"] == "Valor estimado: sigiloso. O edital não divulga o valor numérico."
    assert result["evidence_text"].casefold() == "valor estimado: sigiloso"


def test_modality_summary_includes_registration_criterion_and_dispute():
    source = _chunk(
        "cover",
        (
            "EDITAL DE PREGÃO ELETRÔNICO PARA REGISTRO DE PREÇOS. "
            "MODO DE DISPUTA: ABERTO E FECHADO. "
            "CRITÉRIO DE JULGAMENTO: MENOR PREÇO POR LOTE."
        ),
        0,
        page=1,
    )
    found = agent_service._modality_summary_from_sources([source])
    assert found is not None
    _, answer, evidence = found
    assert "Pregão Eletrônico para Registro de Preços" in answer
    assert "menor preço por lote" in answer
    assert "aberto e fechado" in answer
    assert "MODO DE DISPUTA: ABERTO E FECHADO" in evidence


def test_credenciamento_modality_distinguishes_procedure_from_hiring_form():
    source = _chunk(
        "credential",
        (
            "EDITAL DE CREDENCIAMENTO 01/2024. Incumbirá à CREDENCIANTE providenciar a "
            "publicação do ato que autoriza a Inexigibilidade de Licitação no PNCP."
        ),
        11,
        page=13,
    )

    found = agent_service._modality_summary_from_sources([source])

    assert found is not None
    _, answer, evidence = found
    assert answer == "Procedimento: Credenciamento. Forma de contratação: Inexigibilidade de licitação."
    assert "CREDENCIAMENTO" in evidence
    assert "Inexigibilidade de Licitação" in evidence


def test_scoped_ocs_value_is_not_generalized_to_psa():
    source = _chunk(
        "resources",
        (
            "5.1.1. Para OCS: Orçamento Geral da União, no valor de R$ 950.000,00 "
            "(novecentos e cinquenta mil reais) – Empenho Estimativo. "
            "5.1.2. Para PSA: Orçamento Geral da União, Recursos da Gestão 00001 e "
            "Natureza de Despesa 339036."
        ),
        10,
        page=13,
    )

    found = agent_service._scoped_estimated_value_from_sources([source])

    assert found is not None
    _, answer, evidence = found
    assert "R$ 950.000,00" in answer
    assert "Organizações Civis de Saúde (OCS)" in answer
    assert "sem indicar valor global numérico específico" in answer
    assert "5.1.2. Para PSA" in evidence


def test_cover_object_and_total_value_have_deterministic_answers():
    source = _chunk(
        "cover-fields",
        (
            "OBJETO: REGISTRO DE PREÇOS PARA EXECUÇÃO E MANUTENÇÃO DE SERVIÇOS DE "
            "TERRAPLENAGEM, MACRODRENAGEM, MICRODRENAGEM E CONTENÇÃO NOS MUNICÍPIOS "
            "INTEGRANTES DO CIMVI, de acordo com o Edital e anexos. "
            "VALOR ESTIMADO: Total Geral da Contratação: R$ 128.068.464,63 "
            "(cento e vinte e oito milhões de reais). CRITÉRIO DE JULGAMENTO: Menor preço."
        ),
        0,
        page=2,
    )

    object_found = agent_service._object_summary_from_sources([source])
    value_found = agent_service._estimated_value_from_sources([source])

    assert object_found is not None
    assert "TERRAPLENAGEM" in object_found[1]
    assert object_found[2].startswith("OBJETO:")
    assert value_found is not None
    assert value_found[1] == "Valor estimado total da contratação: R$ 128.068.464,63."
    assert "Total Geral da Contratação" in value_found[2]


def test_numeric_claim_must_exist_in_literal_evidence():
    assert agent_service.numeric_claims_are_supported(
        "O prazo é de 4 horas.",
        "prazo de 4 horas",
    )
    assert not agent_service.numeric_claims_are_supported(
        "O prazo é de 24 horas.",
        "prazo de 4 horas",
    )
    assert agent_service._strip_trailing_ellipsis("trecho literal...") == "trecho literal"
    assert agent_service._strip_trailing_ellipsis("trecho literal…") == "trecho literal"


def test_prompt_excerpt_keeps_exact_field_even_late_in_large_chunk():
    text = ("introdução " * 300) + "VALOR ESTIMADO: SIGILOSO " + ("fim " * 300)
    excerpt = agent_service._relevant_excerpt(text, "valor_estimado", max_chars=500)
    assert "VALOR ESTIMADO: SIGILOSO" in excerpt
    assert len(excerpt) <= 506


def test_attention_points_keep_individual_origin_and_evidence(monkeypatch):
    source = {
        **_chunk("annex", "O documento complementar deverá ser enviado em 4 horas.", 9, page=81),
        "document_part": "ata_registro_precos",
    }
    monkeypatch.setattr(
        agent_service,
        "validate_evidence",
        lambda **kwargs: {
            "evidence_valid": True,
            "chunk_id": kwargs["source_chunk_id"],
            "pages": "81",
        },
    )
    response, points = agent_service._validated_attention_points(
        {
            "attention_points": [
                {
                    "title": "Documento complementar",
                    "impact": "Enviar em 4 horas.",
                    "source_chunk_id": "annex",
                    "evidence_text": "documento complementar deverá ser enviado em 4 horas",
                },
                {
                    "title": "Prazo incorreto",
                    "impact": "Enviar em 24 horas.",
                    "source_chunk_id": "annex",
                    "evidence_text": "documento complementar deverá ser enviado em 4 horas",
                },
            ]
        },
        [source],
        "doc-1",
    )

    assert len(points) == 1
    assert points[0]["document_part"] == "ata_registro_precos"
    assert "página(s) 81" in response


def test_attention_prompt_has_one_unambiguous_schema():
    prompt = agent_service.generate_prompt_for_agent_response(
        "Liste até 5 pontos de atenção do edital",
        [_chunk("main", "Será inabilitado se não enviar o documento.", 0, page=1)],
    )
    assert '"points"' in prompt
    assert '"status":"FOUND|CONFIDENTIAL' not in prompt
    assert "cinco pontos" in prompt

from __future__ import annotations

from services import agent_service
from services.evidence_bundle import expand_evidence_bundle
from services.retrieval import detect_deadline_subtype, detect_query_intent


def _chunk(chunk_id: str, index: int, text: str, *, part: str = "edital_principal") -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": "doc-1",
        "filename": "edital.pdf",
        "chunk_index": index,
        "page_start": index + 1,
        "page_end": index + 2,
        "text": text,
        "document_part": part,
    }


def test_generic_delivery_deadline_is_not_proposal_deadline():
    assert detect_query_intent("Prazo de entrega?") == "prazo"
    assert detect_deadline_subtype("Prazo de entrega?") == "prazo_entrega"
    assert detect_query_intent("Prazo para entrega das propostas?") == "prazo_entrega_proposta"


def test_habilitation_expands_consecutive_chunks_only_inside_section():
    chunks = [
        _chunk("before", 1, "Introdução"),
        _chunk("legal", 2, "9.2 DOCUMENTOS EXIGIDOS PARA HABILITAÇÃO. 9.2.1 HABILITAÇÃO JURÍDICA"),
        _chunk("fiscal", 3, "9.2.2 REGULARIDADE FISCAL E TRABALHISTA"),
        _chunk("economic", 4, "9.2.3 QUALIFICAÇÃO ECONÔMICO-FINANCEIRA"),
        _chunk("technical", 5, "9.2.4 QUALIFICAÇÃO TÉCNICA"),
        _chunk("declarations", 6, "Declarações complementares"),
        _chunk("outside", 7, "ANEXO I", part="termo_referencia"),
    ]
    sources, metrics = expand_evidence_bundle(
        intent="requisitos_habilitacao",
        document_id="doc-1",
        base_sources=[chunks[0]],
        chunks_fn=lambda _document_id: chunks,
    )
    assert [source["chunk_id"] for source in sources] == [
        "legal",
        "fiscal",
        "economic",
        "technical",
        "declarations",
    ]
    assert metrics["evidence_bundle_chunks"] == 5
    assert all(source["document_id"] == "doc-1" for source in sources)


def test_deadline_bundle_keeps_execution_and_receipt_as_different_claims(monkeypatch):
    sources = [
        _chunk(
            "execution",
            1,
            "A execução contratual ocorrerá sob demanda, mediante emissão de Ordem de Serviço pelo DAE",
        ),
        _chunk("diagnosis", 2, "O diagnóstico apresentará estimativa de prazo para execução do serviço"),
        _chunk("proposal", 3, "Prazo de Entrega: Conforme Edital", part="modelo_declaracao"),
        _chunk(
            "receipt",
            4,
            "O recebimento definitivo ocorrerá no prazo de até 10 (dez) dias úteis após o recebimento provisório",
            part="termo_referencia",
        ),
    ]
    monkeypatch.setattr(
        agent_service,
        "validate_evidence",
        lambda **kwargs: {
            "evidence_valid": True,
            "chunk_id": kwargs["source_chunk_id"],
            "pages": "1",
        },
    )
    response, items, rejected = agent_service._deadline_items_from_sources(sources, "doc-1")
    assert rejected == 0
    assert {item["deadline_type"] for item in items} == {
        "prazo_execucao",
        "prazo_diagnostico",
        "prazo_entrega",
        "prazo_recebimento_definitivo",
    }
    assert "Não há um prazo único" in response
    assert "não deve ser tratado como prazo de execução" in response


def test_procedure_deadline_returns_primary_and_complementary_deadlines(monkeypatch):
    chunks = [
        _chunk(
            "main-deadline",
            3,
            (
                "3.1. O prazo para credenciamento iniciar-se-á a partir da publicação no PNCP. "
                "3.1.1. O presente Edital vigorará por PRAZO INDETERMINADO, a partir da sua "
                "publicação no PNCP. 3.1.2. Poderá haver o credenciamento de interessados "
                "enquanto aberto o prazo de credenciamento."
            ),
        ),
        _chunk(
            "proposal-validity",
            5,
            (
                "A Carta Proposta e o Requerimento para Credenciamento terão validade de "
                "60 (sessenta) dias, contados da data da entrega"
            ),
        ),
        _chunk(
            "contract-deadlines",
            11,
            (
                "Os habilitados serão convocados no prazo máximo de 15 (quinze) dias, contados "
                "da apresentação, para assinarem os respectivos contratos, podendo ser prorrogado "
                "uma vez, por igual período. Os contratos celebrados a partir do presente Edital "
                "terão sua vigência limitada em 120 meses de sua assinatura."
            ),
        ),
    ]
    monkeypatch.setattr(
        agent_service,
        "validate_evidence",
        lambda **kwargs: {
            "evidence_valid": True,
            "chunk_id": kwargs["source_chunk_id"],
            "pages": "6",
        },
    )

    sources, metrics = expand_evidence_bundle(
        intent="prazo",
        document_id="doc-1",
        base_sources=[],
        deadline_subtype="prazo_procedimento",
        chunks_fn=lambda _document_id: chunks,
    )
    response, items, rejected = agent_service._deadline_items_from_sources(
        sources,
        "doc-1",
        "prazo_procedimento",
    )

    assert rejected == 0
    assert metrics["evidence_bundle_chunks"] == 3
    assert {item["deadline_type"] for item in items} == {
        "prazo_credenciamento",
        "prazo_validade_proposta",
        "prazo_assinatura_contrato",
        "prazo_vigencia_contrato",
    }
    assert response.startswith("O prazo do credenciamento é indeterminado")
    assert "60 dias" in response
    assert "15 dias" in response
    assert "120 meses" in response


def test_service_credential_has_no_single_delivery_deadline(monkeypatch):
    source = _chunk(
        "service-contract",
        11,
        (
            "Os habilitados serão convocados no prazo máximo de 15 (quinze) dias, para "
            "assinarem os respectivos contratos, podendo ser prorrogado uma vez, por igual período. "
            "Os contratos celebrados a partir do presente Edital terão sua vigência limitada em "
            "120 meses de sua assinatura. 7.1. As condições de execução dos serviços constam "
            "dos contratos, observadas as regras gerais abaixo registradas."
        ),
    )
    monkeypatch.setattr(
        agent_service,
        "validate_evidence",
        lambda **kwargs: {
            "evidence_valid": True,
            "chunk_id": kwargs["source_chunk_id"],
            "pages": "13-14",
        },
    )

    response, items, rejected = agent_service._deadline_items_from_sources(
        [source],
        "doc-1",
        "prazo_entrega",
    )

    assert rejected == 0
    assert agent_service._deadline_status("prazo_entrega", items) == "NOT_APPLICABLE"
    assert response.startswith("O edital principal não estabelece um prazo único de entrega")
    assert "condições de execução dos serviços constam" in response
    assert "15 dias" in response
    assert "120 meses" in response


def test_service_orders_and_annexes_do_not_become_delivery_deadline(monkeypatch):
    sources = [
        _chunk(
            "service-orders",
            30,
            (
                "Emitir as ordens de serviços à empresa vencedora, de acordo com as necessidades, "
                "respeitando os prazos para atendimentos. A Fiscalização, gestão e execução do "
                "contrato deverão observar o disposto no presente Edital e seus anexos, os quais "
                "constituem elementos integrantes entre si."
            ),
        ),
        _chunk(
            "contract-validity",
            28,
            (
                "O prazo de vigência do contrato e suas prorrogações observarão os prazos "
                "estabelecidos na Lei, podendo ser de até 05 (cinco) anos, contados do início da "
                "prestação dos serviços, podendo ser prorrogada, na forma dos anexos, até o máximo "
                "de 10 (dez) anos"
            ),
        ),
    ]
    monkeypatch.setattr(
        agent_service,
        "validate_evidence",
        lambda **kwargs: {
            "evidence_valid": True,
            "chunk_id": kwargs["source_chunk_id"],
            "pages": "44-48",
        },
    )

    response, items, rejected = agent_service._deadline_items_from_sources(
        sources,
        "doc-1",
        "prazo_entrega",
    )

    assert rejected == 0
    assert agent_service._deadline_status("prazo_entrega", items) == "NOT_APPLICABLE"
    assert "não estabelece um prazo único de entrega" in response
    assert "ordens de serviço" in response
    assert "edital e seus anexos" in response
    assert "05 anos" in response and "10 anos" in response


def test_invalid_habilitation_item_does_not_remove_valid_items(monkeypatch):
    sources = [_chunk("legal", 1, "HABILITAÇÃO JURÍDICA: registro comercial.")]
    monkeypatch.setattr(
        agent_service,
        "validate_evidence",
        lambda **kwargs: {
            "evidence_valid": kwargs["source_chunk_id"] == "legal",
            "chunk_id": kwargs["source_chunk_id"],
            "pages": "2",
        },
    )
    response, items, rejected = agent_service._validated_habilitation_items(
        {
            "items": [
                {
                    "category": "juridica",
                    "summary": "Apresentar registro comercial.",
                    "source_chunk_id": "legal",
                    "evidence_text": "HABILITAÇÃO JURÍDICA: registro comercial",
                },
                {
                    "category": "economica",
                    "summary": "Documento inexistente.",
                    "source_chunk_id": "wrong",
                    "evidence_text": "inventado",
                },
            ]
        },
        sources,
        "doc-1",
    )
    assert len(items) == 1
    assert rejected == 1
    assert "Habilitação jurídica" in response


def test_attention_titles_remove_semantic_duplicates():
    assert agent_service._attention_titles_overlap(
        "Envio de proposta adequada ao último lance",
        "Proposta não enviada conforme último lance",
    )
    assert not agent_service._attention_titles_overlap(
        "Documentos de habilitação",
        "Prazo de execução sob demanda",
    )

from __future__ import annotations

from evaluation.decision_audit import _absence_decision, load_validated_current
from evaluation.golden_regression import compare_batch_individual
from services.decision_taxonomy import (
    ACTUALLY_ABSENT,
    FIELD_CONFIDENTIAL,
    FIELD_VARIABLE_BY_ITEM,
    NOT_APPLICABLE,
    UNRESOLVED,
    decision_payload,
)
from services.execution_ontology import (
    DELIVERY_DEADLINE,
    EXECUTION_EQUALS_CONTRACT_TERM,
    ON_DEMAND,
    execution_candidate,
)
from services.deadline_ontology import proposal_validity_from_sources
from services.document_profile import classify_document_profile
from services.field_parsers import (
    criterion_from_sources,
    generic_habilitation_from_sources,
    organization_from_sources,
)
from services.scope_validation import missing_critical_qualifiers
from services.value_ontology import (
    BUDGET_VALUE,
    CONFIDENTIAL_VALUE,
    REFERENCE_VALUE,
    VARIABLE_VALUE,
    estimated_value_candidate,
    value_answer,
)


def source(text: str, chunk_id: str = "c1") -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": "doc-1",
        "filename": "edital.pdf",
        "page_start": 1,
        "page_end": 1,
        "text": text,
    }


def quality() -> dict:
    return {"ocr_required": False, "text_layer_present": True}


def test_confidential_value_is_a_found_external_decision():
    candidate = estimated_value_candidate(
        [source("O valor estimado da contratação possuirá caráter sigiloso.")]
    )
    assert candidate and candidate["value_type"] == CONFIDENTIAL_VALUE
    decision = decision_payload(
        field="valor_estimado",
        internal_status=FIELD_CONFIDENTIAL,
        reason="literal",
    )
    assert decision["final_status"] == "FOUND"


def test_values_by_lot_are_variable_and_are_not_summed():
    candidate = estimated_value_candidate(
        [source("\nLOTE 01 equipamento R$ 10,00\nLOTE 02 material R$ 20,00")]
    )
    assert candidate and candidate["value_type"] == VARIABLE_VALUE
    assert candidate["value"] == ""


def test_global_value_keeps_specific_scope_as_qualifier():
    evidence = "Para OCS: empenho estimativo no valor de R$ 950.000,00;"
    assert missing_critical_qualifiers(evidence, "Para OCS: R$ 950.000,00") == []
    assert missing_critical_qualifiers(evidence, "R$ 950.000,00")


def test_real_value_absence_after_full_text_audit():
    status, _ = _absence_decision(
        "valor_estimado",
        [source("Termo de Referência com especificações técnicas do material.")],
        {"document_type": "termo_referencia", "table_heavy": False, "has_annex": False},
        quality(),
    )
    assert status == ACTUALLY_ABSENT


def test_execution_on_demand_has_no_invented_number():
    candidate = execution_candidate(
        [source("A execução contratual ocorrerá sob demanda, mediante Ordem de Serviço.")]
    )
    assert candidate and candidate["execution_type"] == ON_DEMAND
    assert candidate["value"] == "sob demanda"


def test_execution_according_to_each_entity_demand_is_on_demand():
    candidate = execution_candidate(
        [source("O início da prestação dos serviços ocorrerá de acordo com as demandas de cada município consorciado.")],
        include_delivery=False,
    )
    assert candidate and candidate["execution_type"] == ON_DEMAND
    assert candidate["deadline_type"] == "EXECUTION"


def test_delivery_after_order_of_service_keeps_condition():
    candidate = execution_candidate(
        [source("O prazo de entrega será de 10 (dez) dias após a Ordem de Serviço.")]
    )
    assert candidate and candidate["execution_type"] == DELIVERY_DEADLINE
    assert "Ordem de Serviço" in candidate["evidence_text"]


def test_delivery_is_not_promoted_to_execution_in_strict_mode():
    sources = [source("O prazo de entrega dos bens é de 10 dias úteis.")]
    assert execution_candidate(sources)
    assert execution_candidate(sources, include_delivery=False) is None


def test_delivery_with_installation_and_ate_is_typed_as_delivery():
    candidate = execution_candidate(
        [source("O prazo para entrega e instalação dos equipamentos será de até 10 (dez) dias, contados do recebimento da Ordem de Compra.")]
    )
    assert candidate and candidate["execution_type"] == DELIVERY_DEADLINE
    assert candidate["deadline_type"] == "DELIVERY"
    assert execution_candidate(
        [source("O prazo para entrega e instalação dos equipamentos será de até 10 (dez) dias.")],
        include_delivery=False,
    ) is None


def test_contract_term_alone_is_not_execution():
    assert execution_candidate(
        [source("A vigência contratual será de 12 meses, prorrogável nos termos legais.")]
    ) is None


def test_execution_can_equal_term_only_when_explicit():
    candidate = execution_candidate(
        [source("O prazo de execução será de 12 meses, coincidente com a vigência contratual.")]
    )
    assert candidate and candidate["execution_type"] == EXECUTION_EQUALS_CONTRACT_TERM


def test_auction_execution_is_not_applicable():
    status, _ = _absence_decision(
        "prazo_execucao",
        [source("Leilão para alienação de bens móveis.")],
        {"document_type": "edital_leilao", "table_heavy": False, "has_annex": False},
        quality(),
    )
    assert status == NOT_APPLICABLE


def test_actually_absent_is_not_reported_as_pipeline_error():
    decision = decision_payload(
        field="criterio_julgamento",
        internal_status=ACTUALLY_ABSENT,
        reason="varredura integral",
    )
    assert decision["failure_stage"] is None
    assert decision["final_status"] == "NOT_FOUND"


def test_unresolved_is_preserved_when_related_vocabulary_is_ambiguous():
    status, _ = _absence_decision(
        "criterio_julgamento",
        [source("O critério de julgamento observará as regras do anexo, sem definição literal.")],
        {"document_type": "edital_pregao", "table_heavy": False, "has_annex": False},
        quality(),
    )
    assert status == UNRESOLVED


def test_qualifier_removal_is_detected():
    evidence = "Somente para Sociedades Limitadas: autorização por 3/4 do capital social;"
    assert missing_critical_qualifiers(evidence, "Autorização por 3/4 do capital social")


def test_auction_criterion_is_major_bid():
    parsed = criterion_from_sources(
        [source("EDITAL DE LEILÃO - CRITÉRIO DE JULGAMENTO: MAIOR LANCE")]
    )
    assert parsed and parsed[1] == "Maior lance"


def test_minimum_lot_bid_is_typed_as_reference_not_global_sum():
    candidate = estimated_value_candidate(
        [source("VALOR TOTAL DOS ITEM: R$ 2.321.000,00 LANCE MÍNIMO R$ 2.321.000,00")]
    )
    assert candidate and candidate["value_type"] == REFERENCE_VALUE
    assert candidate["value"] == "R$ 2.321.000,00"


def test_money_display_removes_only_trailing_ocr_decimal_zero():
    candidate = estimated_value_candidate(
        [source("O valor estimado da contratação é de R$ 200.000,000.")]
    )
    assert candidate
    assert value_answer(candidate) == "Valor global estimado: R$ 200.000,00."


def test_budget_total_is_extracted_from_readable_table_text():
    candidate = estimated_value_candidate(
        [source("PLANILHA ORÇAMENTÁRIA VALOR TOTAL:] R$ 874.905,54")]
    )
    assert candidate and candidate["value_type"] == BUDGET_VALUE
    assert candidate["value"] == "R$ 874.905,54"


def test_proposal_letter_validity_without_da_proposta_is_supported():
    parsed = proposal_validity_from_sources(
        [source('A “Carta Proposta” e o requerimento terão validade de 60 (sessenta) dias, contados da entrega.')]
    )
    assert parsed and parsed[1]["duration"] == 60
    assert parsed[1]["type"] == "PROPOSAL_VALIDITY"


def test_academic_header_identifies_responsible_unit():
    parsed = organization_from_sources(
        [source("GOVERNO DO ESTADO DA BAHIA\nUNIVERSIDADES DO ESTADO DA BAHIA - UNEB\nDEPARTAMENTO DE CIÊNCIAS HUMANAS - DCH IV/JACOBINA")]
    )
    assert parsed and "UNIVERSIDADES DO ESTADO DA BAHIA" in parsed[1]
    assert "DCH IV/JACOBINA" in parsed[1]


def test_auction_registration_documents_are_habilitation_requirements():
    parsed = generic_habilitation_from_sources(
        [source("DO CADASTRAMENTO PARA EFETUAR LANCES. Na fase de habilitação: 1. Certidão Negativa de Débitos relativos aos tributos federais e à dívida ativa da União;")]
    )
    assert parsed and "Certidão Negativa" in parsed[1]


def test_formal_modality_wins_over_incidental_credentialing_term():
    profile = classify_document_profile(
        [source("EDITAL - PREGÃO ELETRÔNICO Nº 105/2026. O contratado deverá manter seu credenciamento cadastral.")]
    )
    assert profile["document_type"] == "edital_pregao"
    assert profile["formal_modality"] == "pregao_eletronico"


def test_concorrencia_wins_over_pregao_in_url_and_justification_is_coherent():
    profile = classify_document_profile(
        [source("CONCORRÊNCIA ELETRÔNICA 003/2026. Local: pregaoonline.com.br. Objeto: execução de obra de pavimentação. Justificativa: executar obra de pavimentação urbana.")]
    )
    assert profile["document_type"] == "edital_concorrencia"
    assert profile["object_nature"] == "obra_engenharia"
    assert profile["justification_consistent"] is True


def test_reference_title_is_document_type_with_dispensa_as_modality_context():
    profile = classify_document_profile(
        [source("TERMO DE REFERÊNCIA. A presente Dispensa de Licitação tem por objeto adquirir material de consumo. Justificativa: aquisição de insumos médicos.")]
    )
    assert profile["document_type"] == "termo_referencia"
    assert profile["formal_modality"] == "dispensa_licitacao"
    assert profile["object_nature"] == "bens"


def test_service_with_parts_supply_remains_service_by_object_clause():
    profile = classify_document_profile(
        [source("EDITAL N.º 157/2026 – PREGÃO ELETRÔNICO. OBJETO: Prestação de serviços de manutenção preventiva e corretiva, com fornecimento de peças.")]
    )
    assert profile["document_type"] == "edital_pregao"
    assert profile["object_nature"] == "servicos"


def test_goods_object_is_not_changed_by_incidental_works_vocabulary():
    profile = classify_document_profile(
        [source("PREGÃO ELETRÔNICO EDITAL Nº 056/2026. OBJETO: aquisição de equipamentos para viaturas. Aplicam-se as normas de obras e serviços.")]
    )
    assert profile["document_type"] == "edital_pregao"
    assert profile["object_nature"] == "bens"


def test_reference_document_may_really_omit_modality():
    status, _ = _absence_decision(
        "modalidade",
        [source("TERMO DE REFERÊNCIA - especificações técnicas do material")],
        {"document_type": "termo_referencia", "table_heavy": False, "has_annex": False},
        quality(),
    )
    assert status == ACTUALLY_ABSENT


def test_validated_current_is_separate_and_has_105_entries():
    current = load_validated_current()
    assert current["golden_count"] == 46
    assert sum(len(row["found_fields"]) for row in current["documents"]) == 105


def test_variable_decision_has_context_dependent_external_status():
    decision = decision_payload(
        field="valor_estimado",
        internal_status=FIELD_VARIABLE_BY_ITEM,
        reason="por lote",
    )
    assert decision["final_status"] == "CONTEXT_DEPENDENT"


def test_batch_parity_compares_internal_status_document_and_evidence():
    base = {
        "answered": True,
        "final_status": "FOUND",
        "internal_status": "FOUND",
        "document_id": "doc-1",
        "field": "objeto",
        "evidence": {"chunk_id": "c1"},
    }
    assert compare_batch_individual({"objeto": base}, {"objeto": dict(base)}) == []
    changed = {**base, "evidence": {"chunk_id": "c2"}}
    assert compare_batch_individual({"objeto": base}, {"objeto": changed})[0]["code"] == "BATCH_INDIVIDUAL_DIVERGENCE"

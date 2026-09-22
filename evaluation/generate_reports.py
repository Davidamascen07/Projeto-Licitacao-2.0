from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.metrics import aggregate_rows, hallucination_rate, numeric_summary, values_equivalent  # noqa: E402
from services.storage_utils import atomic_write_json, load_json, utc_now  # noqa: E402

RESULTS_DIR = ROOT / "evaluation" / "results"
FIGURES_DIR = ROOT / "docs" / "figs"
SELECTED_CONFIG_PATH = RESULTS_DIR / "selected_config.json"


def _assert_split(rows: list[dict[str, Any]], expected: str) -> None:
    found = {row.get("split") for row in rows}
    if rows and found != {expected}:
        raise ValueError(f"Resultados misturam splits: esperado {expected}, encontrado {sorted(found)}")


def error_analysis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    counts: Counter[str] = Counter()
    for row in rows:
        categories: list[str] = []
        if not row.get("answered"):
            categories.append("campo_ausente_ou_nao_extraido")
        if not row.get("sources") and row.get("approach") == "rag":
            categories.append("erro_recuperacao")
        if row.get("answered") and not (row.get("evidence") or {}).get("evidence_valid"):
            categories.append("resposta_sem_evidencia_valida")
        if any(source.get("document_id") != row.get("document_id") for source in row.get("sources", [])):
            categories.append("mistura_entre_documentos")
        reference = row.get("reference") or {}
        if reference.get("validated_by_human") and row.get("answered") and not values_equivalent(row.get("value"), reference.get("value")):
            categories.append("divergencia_textual_referencia")
        if row.get("ragas_error") not in {None, "skipped"}:
            categories.append("falha_avaliacao_ragas")
        for category in categories:
            counts[category] += 1
            if len(examples[category]) < 5:
                evidence = row.get("evidence") or {}
                examples[category].append(
                    {
                        "document_id": row.get("document_id"),
                        "filename": row.get("filename"),
                        "field": row.get("field"),
                        "approach": row.get("approach"),
                        "config_id": row.get("config_id"),
                        "value": row.get("value"),
                        "reference_value": reference.get("value"),
                        "page": evidence.get("pages"),
                        "evidence_text": evidence.get("text"),
                        "validation_error": evidence.get("validation_error"),
                    }
                )
    return {"generated_at": utc_now(), "counts": dict(counts), "examples": dict(examples)}


def hypothesis_report(rows: list[dict[str, Any]], selected_config_id: str) -> dict[str, Any]:
    relevant = [
        row
        for row in rows
        if row.get("split") == "test"
        and row.get("approach") == "rag"
        and row.get("config_id") == selected_config_id
    ]
    faithfulness = numeric_summary(row.get("faithfulness") for row in relevant)
    correctness = numeric_summary(row.get("answer_correctness") for row in relevant)
    hallucination = hallucination_rate(relevant)
    thresholds = {"faithfulness": 0.85, "answer_correctness": 0.80, "hallucination_rate": 0.10}
    if faithfulness["count"] == 0 or correctness["count"] == 0 or hallucination["hallucination_rate"] is None:
        conclusion = "inconclusiva"
    else:
        checks = [
            faithfulness["mean"] >= thresholds["faithfulness"],
            correctness["mean"] >= thresholds["answer_correctness"],
            hallucination["hallucination_rate"] <= thresholds["hallucination_rate"],
        ]
        conclusion = "confirmada" if all(checks) else "parcialmente_confirmada" if any(checks) else "rejeitada"
    ragas_errors = [row for row in relevant if row.get("ragas_error") not in {None, "skipped"}]
    return {
        "generated_at": utc_now(),
        "scope": "test split; selected RAG configuration only",
        "selected_config_id": selected_config_id,
        "sample_rows": len(relevant),
        "thresholds": thresholds,
        "observed": {"faithfulness": faithfulness, "answer_correctness": correctness, **hallucination},
        "ragas_error_count": len(ragas_errors),
        "conclusion": conclusion,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _flat_summary(rows: list[dict[str, Any]], groups: tuple[str, ...]) -> list[dict[str, Any]]:
    output = []
    for item in aggregate_rows(rows, groups):
        flat = {key: value for key, value in item.items() if not isinstance(value, dict)}
        for key, value in item.items():
            if isinstance(value, dict):
                for subkey, subvalue in value.items():
                    flat[f"{key}_{subkey}"] = subvalue
        output.append(flat)
    return output


def generate_plots(
    development_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    selected_config_id: str,
    figures_dir: Path = FIGURES_DIR,
) -> list[str]:
    import matplotlib.pyplot as plt

    figures_dir.mkdir(parents=True, exist_ok=True)
    generated: list[str] = []
    final_rows = [
        row
        for row in test_rows
        if row.get("approach") != "rag" or row.get("config_id") == selected_config_id
    ]
    labels = ["regex", "llm_no_retrieval", "rag"]
    grouped = {label: [row for row in final_rows if row.get("approach") == label] for label in labels}

    faith = [numeric_summary(row.get("faithfulness") for row in grouped[label])["mean"] or 0 for label in labels]
    correct = [numeric_summary(row.get("answer_correctness") for row in grouped[label])["mean"] or 0 for label in labels]
    x = list(range(len(labels)))
    width = 0.35
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.bar([value - width / 2 for value in x], faith, width, label="Faithfulness")
    ax.bar([value + width / 2 for value in x], correct, width, label="Answer Correctness")
    ax.set_xticks(x, labels, rotation=12)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Média no teste")
    ax.legend()
    fig.tight_layout()
    target = figures_dir / "metricas_finais_teste.png"
    fig.savefig(target, dpi=180)
    plt.close(fig)
    generated.append(str(target))

    measures = {
        "alucinacao_final_teste.png": (
            [hallucination_rate(grouped[label])["hallucination_rate"] or 0 for label in labels],
            "Taxa de alucinação",
        ),
        "custo_final_teste.png": (
            [numeric_summary((row.get("usage") or {}).get("estimated_cost") for row in grouped[label])["mean"] or 0 for label in labels],
            "Custo médio por campo (USD)",
        ),
        "latencia_final_teste.png": (
            [numeric_summary((row.get("metrics") or {}).get("total_ms") for row in grouped[label])["mean"] or 0 for label in labels],
            "Latência média por campo (ms)",
        ),
    }
    for filename, (values, ylabel) in measures.items():
        fig, ax = plt.subplots(figsize=(8, 4.8))
        ax.bar(labels, values)
        ax.set_ylabel(ylabel)
        fig.tight_layout()
        target = figures_dir / filename
        fig.savefig(target, dpi=180)
        plt.close(fig)
        generated.append(str(target))

    dev_rag = [row for row in development_rows if row.get("approach") == "rag"]
    dev_summary = aggregate_rows(dev_rag, ("config_id",))
    config_labels = [item["config_id"] for item in dev_summary]
    config_correct = [item["answer_correctness"]["mean"] or 0 for item in dev_summary]
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.bar(config_labels, config_correct)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Answer Correctness - desenvolvimento")
    ax.tick_params(axis="x", rotation=65)
    fig.tight_layout()
    target = figures_dir / "configuracoes_desenvolvimento.png"
    fig.savefig(target, dpi=180)
    plt.close(fig)
    generated.append(str(target))
    return generated


def write_limitations(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Limitações\n\n"
        "- A amostra possui 10 editais e não garante representatividade nacional.\n"
        "- Os 18 PDFs foram fornecidos manualmente; proveniência e URL não foram inventadas.\n"
        "- A qualidade depende do texto extraído e pode ser afetada por OCR, digitalização e anexos.\n"
        "- Geração e avaliação dependem de modelo externo, disponibilidade e limites de taxa.\n"
        "- Os resultados são restritos a valor, modalidade e prazo.\n"
        "- A avaliação usa uma única divisão 7/3 e não substitui validação externa.\n"
        "- Custos do avaliador RAGAS podem não estar disponíveis no retorno de uso da biblioteca; essa lacuna deve ser relatada.\n"
        "- O sistema apoia triagem e não substitui análise jurídica ou profissional.\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera relatórios separados de desenvolvimento e teste.")
    parser.add_argument("--development-results", default=str(RESULTS_DIR / "development" / "raw_results.json"))
    parser.add_argument("--test-results", default=str(RESULTS_DIR / "test" / "raw_results.json"))
    parser.add_argument("--selected-config", default=str(SELECTED_CONFIG_PATH))
    args = parser.parse_args()
    development_rows = load_json(args.development_results, [])
    test_rows = load_json(args.test_results, [])
    selected = load_json(args.selected_config, {})
    selected_id = selected.get("selected_config_id")
    if not development_rows or not test_rows or not selected_id:
        print("Resultados reais completos e configuração selecionada são obrigatórios; nada foi fabricado.")
        return 2
    _assert_split(development_rows, "development")
    _assert_split(test_rows, "test")

    final_test_rows = [
        row for row in test_rows if row.get("approach") != "rag" or row.get("config_id") == selected_id
    ]
    dev_comparison = _flat_summary(
        [row for row in development_rows if row.get("approach") == "rag"], ("config_id",)
    )
    test_comparison = _flat_summary(final_test_rows, ("approach", "config_id"))
    _write_csv(RESULTS_DIR / "development_configuration_comparison.csv", dev_comparison)
    _write_csv(RESULTS_DIR / "test_final_comparison.csv", test_comparison)
    atomic_write_json(RESULTS_DIR / "error_analysis.json", error_analysis(final_test_rows))
    atomic_write_json(RESULTS_DIR / "hypothesis_report.json", hypothesis_report(test_rows, selected_id))
    atomic_write_json(
        RESULTS_DIR / "final_comparison.json",
        {"generated_at": utc_now(), "selected_config_id": selected_id, "summary": aggregate_rows(final_test_rows, ("approach", "config_id"))},
    )
    write_limitations(ROOT / "docs" / "limitations.md")
    generated = generate_plots(development_rows, test_rows, selected_id)
    print(json.dumps({"plots": generated, "selected_config_id": selected_id}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

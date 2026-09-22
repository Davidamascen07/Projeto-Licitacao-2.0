# Resultados experimentais

Experimento original: 22/07/2026.

Reavaliação cirúrgica: 07/08/2026.

## Protocolo congelado

- Benchmark: 10 editais, 7 em desenvolvimento e 3 em teste.
- Ground truth: 30 referências humanas para valor estimado, modalidade e prazo/validade da proposta.
- Modelo: `openai/gpt-oss-120b` via Groq.
- Configurações: chunk 300/500/800, overlap 50/80 e top-k 3/5.
- Configuração selecionada: `chunk500_overlap50_topk3`.
- Seleção realizada exclusivamente nas 294 linhas de desenvolvimento.
- Artefatos originais preservados; a reavaliação foi gravada em diretório separado.

## Reavaliação RAG de 07/08/2026

Escopo: uma configuração × 3 documentos × 3 campos, somente abordagem RAG.

| Métrica | 22/07/2026 | 07/08/2026 | Variação |
|---|---:|---:|---:|
| Respostas | 2/9 | 3/9 | +1 |
| Cobertura | 22,22% | 33,33% | +11,11 p.p. |
| Faithfulness | 1,0000 (n=2) | 1,0000 (n=3) | 0 |
| Answer Correctness | 0,8469 (n=2) | 0,9578 (n=3) | +0,1109 |
| `unsupported_claim_rate` | 0% | 0% | 0 |
| `reference_mismatch_rate` | 50% | 66,67% | +16,67 p.p. |

As médias RAGAS são condicionais às respostas produzidas. A amostra efetiva aumentou de 2 para 3, mas continua pequena.

## Respostas avaliadas

| Documento | Campo | Resposta | Referência | Faithfulness | Correctness |
|---|---|---|---|---:|---:|
| `edital609.pdf` | modalidade | Leilão | leilão eletrônico | 1,0000 | 0,9429 |
| `EDITAL_DE_CREDENCIAMENTO_004.2025_assinado.pdf` | modalidade | Procedimento: Credenciamento. | credenciamento | 1,0000 | 0,9304 |
| `EDITAL_CC006.pdf` | modalidade | Concorrência eletrônica | concorrência eletrônica | 1,0000 | 1,0000 |

Os seis campos restantes não foram respondidos: três prazos e três valores. No credenciamento, a referência humana de valor era nula; nos outros dois documentos, os valores existiam na referência.

## Definição atual das métricas

`unsupported_claim_rate` mede afirmações factuais sem suporte:

- evidência inválida: fração sem suporte igual a 1;
- evidência válida e Faithfulness disponível: `1 - Faithfulness`.

`reference_mismatch_rate` mede respostas não literalmente equivalentes ao gabarito. A métrica `hallucination_rate` foi mantida por compatibilidade, mas agora é alias de `unsupported_claim_rate`.

Consequentemente, `Leilão` × `leilão eletrônico` e `Procedimento: Credenciamento` × `credenciamento` contam como mismatch, mas não como alucinação factual, porque possuem evidência válida e Faithfulness 1,0.

## Custos e desempenho da reavaliação

- Geração: 6.601 tokens, sendo 5.926 de entrada e 675 de saída.
- Custo teórico: US$ 0,00129390.
- Latência acumulada: 214,65 s.
- Latência média: 23,85 s por pergunta.

O plano utilizado é gratuito; o custo é uma equivalência on-demand, não uma cobrança observada.

## Interpretação

- Faithfulness >= 0,85: meta atingida.
- Answer Correctness >= 0,80: meta atingida.
- Alucinação factual <= 10%: meta atingida.
- Cobertura: ainda insuficiente.

A hipótese é confirmada somente neste pequeno recorte segundo a definição corrigida. A fórmula foi modificada após observar o teste; portanto, deve ser congelada e validada em novo holdout antes de uma conclusão científica definitiva.

## Relação com o pipeline de produção

Esta avaliação usa a configuração experimental congelada. A auditoria de 171 decisões usa o pipeline híbrido atual, com taxonomia e fallbacks adicionais. Os números respondem a perguntas diferentes e não devem ser combinados em uma única média.

## Artefatos

- `evaluation/results/rerun_current_2026-08-07_test/global_summary.json`
- `evaluation/results/rerun_current_2026-08-07_test/comparison_report.md`
- `evaluation/results/rerun_current_2026-08-07_test/raw_results.json`
- `evaluation/results/rerun_current_2026-08-07_test/hypothesis_report.json`

As figuras existentes em `docs/figs/` registram o experimento original de 22/07/2026 e devem ser tratadas como históricas.

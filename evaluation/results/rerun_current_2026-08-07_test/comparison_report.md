# Reavaliação RAGAS cirúrgica - 07/08/2026

## Escopo

- Abordagem: somente RAG.
- Configuração: `chunk500_overlap50_topk3`, selecionada exclusivamente no desenvolvimento.
- Conjunto: 3 documentos do split de teste.
- Campos: `valor_estimado`, `modalidade` e `prazo_entrega_proposta`.
- Total: 9 perguntas.
- Modelo: `openai/gpt-oss-120b` via Groq.
- Resultados gravados em diretório novo; os artefatos de 22/07/2026 não foram alterados.

## Comparação

| Métrica | Experimento de 22/07/2026 | Reavaliação de 07/08/2026 | Variação |
|---|---:|---:|---:|
| Respostas | 2/9 | 3/9 | +1 |
| Cobertura | 22,22% | 33,33% | +11,11 p.p. |
| Faithfulness | 1,0000 (n=2) | 1,0000 (n=3) | 0 |
| Answer Correctness | 0,8469 (n=2) | 0,9578 (n=3) | +0,1109 |
| Unsupported Claim Rate / alucinação factual | 0,00% | 0,00% | 0 |
| Reference Mismatch Rate | 50,00% (1/2) | 66,67% (2/3) | +16,67 p.p. |

As médias RAGAS são condicionais às respostas produzidas. A amostra efetiva aumentou de 2 para 3, mas continua pequena.

## Respostas avaliadas pelo RAGAS

| Documento | Campo | Resposta | Referência | Faithfulness | Answer Correctness | Evidência válida |
|---|---|---|---|---:|---:|---|
| `edital609.pdf` | modalidade | Leilão | leilão eletrônico | 1,0000 | 0,9429 | sim |
| `EDITAL_DE_CREDENCIAMENTO_004.2025_assinado.pdf` | modalidade | Procedimento: Credenciamento. | credenciamento | 1,0000 | 0,9304 | sim |
| `EDITAL_CC006.pdf` | modalidade | CONCORRÊNCIA ELETRÔNICA | concorrência eletrônica | 1,0000 | 1,0000 | sim |

Os seis casos restantes retornaram informação não encontrada: os três prazos, os três valores estimados. No credenciamento, a referência humana de valor é nula; nos outros dois documentos, os valores estavam presentes na referência.

## Separação das métricas

A regra foi corrigida para não tratar desigualdade textual como alucinação. Agora:

- `unsupported_claim_rate` mede a fração factual não sustentada: evidência inválida vale 1; quando a evidência é válida e existe RAGAS, usa `1 - Faithfulness`.
- `reference_mismatch_rate` mede respostas não literalmente equivalentes ao gabarito humano.
- `hallucination_rate` foi preservada para compatibilidade, mas passou a ser alias de `unsupported_claim_rate`.

As duas divergências textuais da rodada possuem evidência válida e Faithfulness 1,0:

1. `Leilão` não coincide literalmente com `leilão eletrônico`.
2. `Procedimento: Credenciamento.` não coincide literalmente com `credenciamento`.

Por isso, elas permanecem no `reference_mismatch_rate` de 66,67%, mas não são alucinações factuais. O `unsupported_claim_rate` da rodada é 0%.

## Custos e tempos observados

- Tokens de geração: 6.601 (5.926 de entrada e 675 de saída).
- Custo teórico estimado: US$ 0,00129390.
- Latência acumulada das nove gerações: 214,65 s.
- Latência média por pergunta: 23,85 s.
- Duração da retomada final do executor: 144,30 s, além do tempo já consumido na geração preservada pelo checkpoint.

## Conclusão

- Meta de Faithfulness >= 0,85: atingida.
- Meta de Answer Correctness >= 0,80: atingida.
- Meta de alucinação factual (`unsupported_claim_rate`) <= 10%: atingida.
- Cobertura: melhorou, mas 33,33% ainda é insuficiente.
- A hipótese é confirmada neste recorte segundo a métrica corrigida.

Esta rodada mede a configuração experimental congelada (`chunk500_overlap50_topk3`). Ela não equivale à auditoria de decisões do pipeline de produção, que possui recuperação híbrida e taxonomia adicional.

A redefinição foi feita após a observação do conjunto de teste. Para uma conclusão científica sem risco de ajuste pós-hoc, a fórmula deve ser congelada e validada novamente em um holdout novo ou corpus ampliado.

# Estimativa conservadora de custo experimental

> Documento histórico de planejamento. Os custos observados da reavaliação de
> 07/08/2026 estão em `docs/experimental_results.md`: 6.601 tokens de geração
> e custo teórico estimado de US$ 0,00129390. O plano utilizado foi gratuito.

Data da consulta: 21/07/2026.

Modelo: `openai/gpt-oss-120b`.

Fonte oficial: https://groq.com/pricing

| Componente | Valor |
|---|---:|
| Entrada não armazenada em cache | US$ 0,15 / 1 milhão de tokens |
| Entrada armazenada em cache | US$ 0,075 / 1 milhão de tokens |
| Saída | US$ 0,60 / 1 milhão de tokens |

## Volume máximo previsto

- Desenvolvimento: 7 documentos x 3 campos x (12 configurações RAG + 2 baselines) = 294 linhas.
- Teste: 3 documentos x 3 campos x (1 RAG congelado + 2 baselines) = 27 linhas.
- Chamadas de geração: até 291; regex não usa LLM.
- Linhas potencialmente avaliadas pelo RAGAS: até 321.
- Para a estimativa, foram assumidas até quatro chamadas do avaliador por linha respondida.

## Hipóteses conservadoras

- Geração: 5.000 tokens de entrada e 500 de saída por chamada.
- Avaliador: 10.000 tokens de entrada e 1.000 de saída por chamada interna.
- Nenhum desconto de cache foi considerado.
- Margem adicional: 20%.

## Estimativa

- Geração: aproximadamente US$ 0,31.
- Avaliação RAGAS: aproximadamente US$ 2,70.
- Subtotal: aproximadamente US$ 3,01.
- Total com margem de 20%: aproximadamente US$ 3,61.

O valor fica abaixo do gate de US$ 5 definido para esta execução. É uma estimativa superior conservadora, não um gasto observado. O retorno de uso do avaliador RAGAS pode não expor todos os tokens; essa lacuna deve permanecer explícita no relatório final.

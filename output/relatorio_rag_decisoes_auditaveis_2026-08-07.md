# Relatório da rodada incremental — RAG orientado a decisões auditáveis

Data da auditoria: **07/08/2026**  
Corpus: **19 documentos × 9 campos = 171 decisões**

## 1. Estado inicial da rodada

A rodada partiu de **46 casos GOLDEN**, **105/171 campos consolidados como FOUND (61,40%)**, zero regressões golden, 12/12 controles individuais e divergência batch/individual igual a zero. A arquitetura, os embeddings e o índice persistido foram preservados.

## 2. Classificação dos 66 campos restantes

| Estado interno | Quantidade |
|---|---:|
| `FOUND` | 34 |
| `FIELD_CONFIDENTIAL` | 1 |
| `NOT_APPLICABLE` | 18 |
| `ACTUALLY_ABSENT` | 9 |
| `FIELD_VARIABLE_BY_ITEM` | 4 |
| **Total** | **66** |

Os 66 casos deixaram de ser um bloco genérico de `NOT_FOUND`: cada decisão agora registra origem, top-10, parser, fallback, evidência/validação, etapa de falha e motivo final.

## 3. Matriz geral das 171 decisões

| Estado interno | Quantidade |
|---|---:|
| `FOUND` | 139 |
| `FIELD_CONFIDENTIAL` | 1 |
| `NOT_APPLICABLE` | 18 |
| `ACTUALLY_ABSENT` | 9 |
| `FIELD_PRESENT_RETRIEVAL_MISS` | 0 |
| `FIELD_PRESENT_RANKING_MISS` | 0 |
| `FIELD_PRESENT_SECTION_EXPANSION_MISS` | 0 |
| `FIELD_PRESENT_CONTEXT_TRUNCATION` | 0 |
| `FIELD_PRESENT_PARSER_MISS` | 0 |
| `FIELD_PRESENT_VALIDATION_MISS` | 0 |
| `FIELD_PRESENT_IN_TABLE` | 0 |
| `FIELD_PRESENT_IN_ANNEX` | 0 |
| `FIELD_VARIABLE_BY_ITEM` | 4 |
| `DOCUMENT_TEXT_INSUFFICIENT` | 0 |
| `UNRESOLVED` | 0 |
| **Total** | **171** |

A matriz inclui `FIELD_CONFIDENTIAL` e `FIELD_VARIABLE_BY_ITEM` explicitamente, evitando ocultar esses estados dentro de `FOUND` ou `NOT_FOUND`.

## 4. Taxa FOUND

**140/171 = 81,87%**. O total inclui 139 `FOUND` literais e 1 valor confidencial, que externamente é uma resposta encontrada.

## 5. Taxa de decisão correta

**167/171 = 97,66%**. Fórmula aplicada: FOUND correto + FIELD_CONFIDENTIAL + NOT_APPLICABLE correto + ACTUALLY_ABSENT correto. Os quatro casos variáveis por item permanecem fora da fórmula estrita solicitada, embora sejam decisões contextuais úteis e não falsos FOUND.

## 6. Falsos negativos reais

Foram identificados **0** falsos negativos/falhas reais: 0 caso em tabela e 0 nas demais etapas. Não houve promoção artificial desses casos para aumentar cobertura.

## 7. Falsos positivos

**0 falsos positivos identificados** na rodada. A contagem significa que nenhum candidato auditado foi mantido após evidência cruzada, generalização de qualificador ou confusão entre total, item, vigência, assinatura e execução. Ela não substitui futura revisão humana dos candidatos.

## 8. NOT_APPLICABLE corretos

**18** decisões, principalmente critérios competitivos em credenciamentos, validade de proposta em leilões e ausência de prazo único de execução em credenciamentos/alienações.

## 9. ACTUALLY_ABSENT corretos

**9** decisões após varredura integral da camada textual e sem indício estrutural suficiente do campo.

## 10. UNRESOLVED

**0** decisões. Nesses casos há vocabulário relacionado, mas não existe candidato com sujeito, número, unidade, condição e escopo seguros; a precisão foi priorizada.

## 11. Auditoria de valor estimado — 14 casos

| Documento | Classificação final | Valor/resposta | Páginas | Motivo |
|---|---|---|---|---|
| 1123420260129-Termo_1.pdf | `FIELD_VARIABLE_BY_ITEM` | O documento não apresenta um único valor global; os valores variam por item, lote ou tabela. | 9-12 | Novo candidato local validado nas três fontes de produção. |
| 34-26+-+Orientador+Social+e+servico+tecnico+assistencial+-+PE+29… | `FOUND` | Valor global estimado: R$ 137.400,00. | 1-2 | Novo candidato local validado nas três fontes de produção. |
| 874745.pdf | `FOUND` | Valor de referência: R$ 2.268.550,51. | 1-2 | Novo candidato local validado nas três fontes de produção. |
| 885062.pdf | `FOUND` | Valor global estimado: R$ 7.979,52. | 1-3 | Novo candidato local validado nas três fontes de produção. |
| documento.pdf | `FIELD_VARIABLE_BY_ITEM` | O documento não apresenta um único valor global; os valores variam por item, lote ou tabela. | 1-2 | Novo candidato local validado nas três fontes de produção. |
| Edital+102150-+149+-+2026+assinado.pdf | `FIELD_CONFIDENTIAL` | Valor estimado sigiloso. | 1-3 | Novo candidato local validado nas três fontes de produção. |
| Edital+Credenciamento_OCS-PSA+01-2024.pdf | `FIELD_VARIABLE_BY_ITEM` | O documento não apresenta um único valor global; os valores variam por item, lote ou tabela. | 62-64 | Os valores estão distribuídos por item, lote ou tabela; não foi calculado total artificial. |
| Edital+de+Credenciamento+n+001.2026.pdf | `FOUND` | Valor global estimado: R$ 200.000,00. | 5-7 | Novo candidato local validado nas três fontes de produção. |
| Edital+e+anexos.pdf | `FOUND` | Valor de referência: R$ 449.141,00. | 1-2 | Novo candidato local validado nas três fontes de produção. |
| Edital.pdf | `FOUND` | Valor global estimado: R$650.000,00. | 69-70 | Novo candidato local validado nas três fontes de produção. |
| edital609.pdf | `FOUND` | Valor de referência: R$ 2.321.000,00. | 10-11 | Novo candidato local validado nas três fontes de produção. |
| edital610.pdf | `FOUND` | Valor de referência: R$ 29.195.378,31. | 10-12 | Novo candidato local validado nas três fontes de produção. |
| EDITAL_CC006.pdf | `FOUND` | Orçamento estimado: R$ 874.905,54. | 47-50 | Novo candidato local validado nas três fontes de produção. |
| EDITAL_DE_CREDENCIAMENTO_004.2025_assinado.pdf | `FIELD_VARIABLE_BY_ITEM` | O documento não apresenta um único valor global; os valores variam por item, lote ou tabela. | 11-12 | Os valores estão distribuídos por item, lote ou tabela; não foi calculado total artificial. |

Total auditado nesta prioridade: **14**.

A tipagem separa valor global, máximo, referencial, orçamentário, por lote/item, compromisso estimativo, sigiloso e variável. Nenhum total foi somado automaticamente.

## 12. Auditoria de prazo de execução — 15 casos

| Documento | Classificação final | Valor/resposta | Páginas | Motivo |
|---|---|---|---|---|
| 02---Edital-Pregao-Eletronico.pdf | `FOUND` | A execução ocorre sob demanda, conforme a necessidade e a Ordem de Serviço; não há prazo numérico único. | 15-17 | Novo candidato local validado nas três fontes de produção. |
| 1123420260129-Termo_1.pdf | `NOT_APPLICABLE` | O documento não estabelece prazo de execução. Como prazo distinto, prazo de entrega do objeto: 30 dias. | 8-9 | A aquisição possui prazo de entrega física, não prazo de execução; os conceitos foram mantidos separados. |
| 34-26+-+Orientador+Social+e+servico+tecnico+assistencial+-+PE+29… | `FOUND` | Prazo de execução: 12 (doze) meses. | 16-17 | Novo candidato local validado nas três fontes de produção. |
| 874745.pdf | `FOUND` | Prazo de execução: 150 (cento e cinquenta) dias. | 29-31 | Novo candidato local validado nas três fontes de produção. |
| 885062.pdf | `FOUND` | Prazo de execução: 12 (doze) meses, expressamente vinculado à vigência contratual. | 31-32 | Novo candidato local validado nas três fontes de produção. |
| documento.pdf | `NOT_APPLICABLE` | — | — | O credenciamento não estabelece prazo único de execução após a varredura integral. |
| Edital+102150-+149+-+2026+assinado.pdf | `NOT_APPLICABLE` | O documento não estabelece prazo de execução. Como prazo distinto, prazo de entrega do objeto: 10 (dez) dias úteis. | 28-29 | A aquisição possui prazo de entrega física, não prazo de execução; os conceitos foram mantidos separados. |
| Edital+Credenciamento_OCS-PSA+01-2024.pdf | `NOT_APPLICABLE` | — | — | O credenciamento não estabelece prazo único de execução após a varredura integral. |
| Edital+de+Credenciamento+n+001.2026.pdf | `FOUND` | A execução ocorre ao longo da vigência contratual; o trecho não fixa prazo numérico independente. | 5-7 | Novo candidato local validado nas três fontes de produção. |
| Edital+e+anexos.pdf | `NOT_APPLICABLE` | — | — | Leilão de alienação não possui execução contratual do objeto a contratar. |
| Edital.pdf | `NOT_APPLICABLE` | — | — | O credenciamento não estabelece prazo único de execução após a varredura integral. |
| edital609.pdf | `NOT_APPLICABLE` | — | — | Leilão de alienação não possui execução contratual do objeto a contratar. |
| edital610.pdf | `NOT_APPLICABLE` | — | — | Leilão de alienação não possui execução contratual do objeto a contratar. |
| EDITAL_CC006.pdf | `FOUND` | Cronograma de execução: início em 5 (cinco) dias; conclusão em 180 (cento e oitenta) dias. | 2-3 | Novo candidato local validado nas três fontes de produção. |
| EDITAL_DE_CREDENCIAMENTO_004.2025_assinado.pdf | `NOT_APPLICABLE` | — | — | O credenciamento não estabelece prazo único de execução após a varredura integral. |

Total auditado nesta prioridade: **15**.

A ontologia continuou separando validade da proposta, entrega, execução, vigência contratual, assinatura, pagamento, recurso, impugnação e outros prazos. Vigência só foi aceita como execução quando a própria frase vinculou literalmente os conceitos.

## 13. Resultado por campo

| Campo | FOUND* | NOT_APPLICABLE | ACTUALLY_ABSENT | Falhas reais | Variável/contextual | UNRESOLVED | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| `objeto` | 19 | 0 | 0 | 0 | 0 | 0 | 19 |
| `modalidade` | 19 | 0 | 0 | 0 | 0 | 0 | 19 |
| `valor_estimado` | 15 | 0 | 0 | 0 | 4 | 0 | 19 |
| `prazo_entrega_proposta` | 10 | 3 | 6 | 0 | 0 | 0 | 19 |
| `orgao_responsavel` | 19 | 0 | 0 | 0 | 0 | 0 | 19 |
| `uf` | 19 | 0 | 0 | 0 | 0 | 0 | 19 |
| `criterio_julgamento` | 12 | 6 | 1 | 0 | 0 | 0 | 19 |
| `prazo_execucao` | 10 | 9 | 0 | 0 | 0 | 0 | 19 |
| `requisitos_habilitacao` | 17 | 0 | 2 | 0 | 0 | 0 | 19 |

*Nota:* `FOUND` inclui `FIELD_CONFIDENTIAL`, pois externamente esse estado é uma resposta encontrada.

## 14. Resultado por documento

| Documento | FOUND* | N/A | Ausente | Falhas | Variável | Não resolvido | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| 01.Edital_credenciamento_01_2024.pdf | 8 | 1 | 0 | 0 | 0 | 0 | 9 |
| 02---Edital-Pregao-Eletronico.pdf | 9 | 0 | 0 | 0 | 0 | 0 | 9 |
| 1123420260129-Termo_1.pdf | 4 | 1 | 3 | 0 | 1 | 0 | 9 |
| 1626Manutencaodemotoreseletricos.pdf | 9 | 0 | 0 | 0 | 0 | 0 | 9 |
| 34-26+-+Orientador+Social+e+servico+tecnico+assistencial+-+PE+29-26+-+Comprasgo… | 9 | 0 | 0 | 0 | 0 | 0 | 9 |
| 874745.pdf | 9 | 0 | 0 | 0 | 0 | 0 | 9 |
| 885062.pdf | 8 | 0 | 1 | 0 | 0 | 0 | 9 |
| documento.pdf | 5 | 2 | 1 | 0 | 1 | 0 | 9 |
| Edital+102150-+149+-+2026+assinado.pdf | 8 | 1 | 0 | 0 | 0 | 0 | 9 |
| Edital+Credenciamento_OCS-PSA+01-2024.pdf | 6 | 2 | 0 | 0 | 1 | 0 | 9 |
| Edital+de+Credenciamento+n+001.2026.pdf | 7 | 1 | 1 | 0 | 0 | 0 | 9 |
| Edital+e+anexos.pdf | 6 | 2 | 1 | 0 | 0 | 0 | 9 |
| Edital.pdf | 6 | 2 | 1 | 0 | 0 | 0 | 9 |
| edital609.pdf | 7 | 2 | 0 | 0 | 0 | 0 | 9 |
| edital610.pdf | 7 | 2 | 0 | 0 | 0 | 0 | 9 |
| EDITAL_CC006.pdf | 9 | 0 | 0 | 0 | 0 | 0 | 9 |
| EDITAL_DE_CREDENCIAMENTO_004.2025_assinado.pdf | 5 | 2 | 1 | 0 | 1 | 0 | 9 |
| PE+056-26+-+Proc.+00821-26+-+Aquisicao+equipamento+para+viaturas+-+Rep.pdf | 9 | 0 | 0 | 0 | 0 | 0 | 9 |
| PE+056-26+-+Proc.+00821-26+-+Aquisicao+equipamento+para+viaturas.pdf | 9 | 0 | 0 | 0 | 0 | 0 | 9 |

## 15. Recall@1/3/5/10

- Recall@1: **65,22%**
- Recall@3: **84,78%**
- Recall@5: **93,48%**
- Recall@10: **95,65%**

Os valores permaneceram iguais à baseline; a rodada alterou decisão, estrutura e parsers sem mascarar o recall histórico.

## 16. Regressões

**0 regressões golden**. Os **46/46** casos GOLDEN permaneceram FOUND. Os 105 casos consolidados foram mantidos separadamente dos novos candidatos.

## 17. Novos FOUND

**+35** novos FOUND externos, dos quais 1 é valor sigiloso corretamente tratado como resposta encontrada.

## 18. Ganho líquido

**+35 campos**: 105 → 140, sem regressão golden. Além disso, 27 casos passaram a ter decisão correta de não aplicabilidade/ausência, sem serem inflados como FOUND.

## 19. Testes automatizados

**157 aprovados, 0 falhas**. Foram preservados os 124 testes existentes e adicionados 33 testes para os 15 cenários de regressão pedidos, taxonomia, validação cruzada e paridade detalhada.

## 20. Paridade batch × individual

**12/12 controles corretos** e **BATCH_INDIVIDUAL_DIVERGENCE = 0**. A comparação agora cobre status externo, status interno, document_id, campo e chunk de evidência.

## 21. Performance local

- Processamento local total: **106.72 s**
- Recuperação local acumulada: **72.17 s**
- Embeddings/preparação nos 66 diagnósticos: **1.70 s**
- Busca vetorial nos 66 diagnósticos: **0.30 s**
- Reranking nos 66 diagnósticos: **4.24 s**
- Expansão de seção nos 66 diagnósticos: **13.13 s**

Foram mantidos três trechos por campo e 520 caracteres por trecho. Os excertos são centrados no match para preservar sujeito, número, unidade e qualificadores.

## 22. Espera externa Groq

**0.00 s; 0 chamadas** nesta auditoria determinística. A rota de produção conserva a chamada compartilhada em lote quando o LLM é realmente necessário; regras simples continuam locais.

## 23. Limitações restantes

- Decisões `UNRESOLVED`: **0**.
- Falhas reais de recuperação/parser/tabela/anexo: **0**.
- Quatro documentos possuem valores variáveis por item/lote e não devem receber total calculado sem solicitação explícita.
- A taxonomia de ausência usa evidência negativa após varredura textual; revisões humanas continuam recomendadas antes de decisões jurídicas ou financeiras.

## Integridade e rastreabilidade

- `vector_index.faiss`: `8DDC0E6B2ED2F06C732E408851250CE0E48CD12336C065E925C9CD086ACDB200`
- `chunks_metadata.json`: `8E840B7FA6D0557127AD1B716F18D8601A7D4FE4224685D8C371E04F258DC9BB`
- Reindexações realizadas: **0**
- OCR global realizado: **não**
- Promoção automática de candidatos para GOLDEN: **não**
- Evidência com document_id cruzado aceita: **0**

O JSON preserva o diagnóstico completo de cada decisão; o CSV oferece uma visão tabular para filtragem e revisão manual.

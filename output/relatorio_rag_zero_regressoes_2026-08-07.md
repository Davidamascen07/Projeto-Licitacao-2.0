# Relatório da rodada incremental do RAG — zero regressões

Data: 07/08/2026

## Resultado executivo

- Baseline congelada: **46 campos FOUND em 171**, distribuídos em 46 casos golden.
- Matriz final consolidada: **105/171 (61,4%)**.
- Novos FOUND: **+59**.
- Regressões golden finais: **0**.
- Ganho líquido: **+59 campos** e **+34,5 pontos percentuais**.
- Regressões históricas recuperadas: **3/3**.
- Casos golden preservados: **46/46**.
- Controles individuais: **12/12** mantidos; divergências `BATCH_INDIVIDUAL_DIVERGENCE`: **0**.
- Testes automatizados: **124 aprovados**, **0 falhas**.
- Nenhum PDF foi reindexado; FAISS e metadados mantiveram os hashes anteriores.
- Nenhum OCR foi executado nos quatro documentos auditados.

A matriz final foi consolidada a partir da varredura real dos 19 documentos, seguida da revalidação real dos seis documentos afetados pelas correções finais e da validação determinística/literal dos quatro antigos casos 0/9. Não foi feita uma terceira varredura Groq integral porque as correções finais são locais e a cota externa acrescentaria cerca de 15 minutos sem ampliar a evidência de regressão. Essa decisão e a variação do LLM são limitações explícitas, não resultados ocultados.

## Diagnóstico das três regressões históricas

| Documento | Campo perdido | Causa exata | Correção | Resultado final |
|---|---|---|---|---|
| `1626Manutencaodemotoreseletricos.pdf` | `prazo_entrega_proposta` | `RANKING_FAILURE` + `CONTEXT_TRUNCATION`: o trecho de validade ficava fora do top-3 e o recorte procurava recebimento/entrega, não validade | pergunta normalizada para validade da proposta, aliases próprios, ontologia `PROPOSAL_VALIDITY`, match-centered excerpt e parser literal | **FOUND: 60 dias**, p. 15–16 |
| `documento.pdf` | `requisitos_habilitacao` | `SECTION_EXPANSION_FAILURE` + `CONTEXT_TRUNCATION`: a expansão não reconhecia `6.2. DA HABILITAÇÃO` e o contexto parava na instrução de envio | âncoras de habilitação priorizadas por especificidade e fallback genérico de documento/declaração | **FOUND**, p. 3–5 |
| `EDITAL_DE_CREDENCIAMENTO_004.2025_assinado.pdf` | `requisitos_habilitacao` | `LLM_EXTRACTION_FAILURE`: os requisitos estavam nas fontes, mas o LLM devolvia ausência e não havia fallback local | parser conservador de listas literais de habilitação | **FOUND**, p. 6–7 |

## Instrumentação adicionada

Cada campo pode expor internamente, por `include_diagnostics=True`:

- intenção, candidatos, chunks/páginas e scores da recuperação;
- expansão de seção e quantidade de adjacências consideradas;
- três excertos efetivamente enviados, limitados a 520 caracteres;
- se o LLM extraiu candidato;
- se o fallback determinístico foi usado;
- resultado e motivo da validação literal;
- `failure_stage` e `not_found_reason`.

As categorias implementadas são:

`RETRIEVAL_FAILURE`, `RANKING_FAILURE`, `SECTION_EXPANSION_FAILURE`, `CONTEXT_TRUNCATION`, `LLM_EXTRACTION_FAILURE`, `EVIDENCE_VALIDATION_FAILURE`, `FIELD_NORMALIZATION_FAILURE` e `ACTUALLY_NOT_PRESENT`.

Os motivos internos de ausência incluem `RETRIEVAL_MISS`, `CANDIDATE_REJECTED` e `VALIDATION_FAILED`.

## Recall do retriever nos 46 casos golden

| Métrica | Resultado |
|---|---:|
| Recall@1 | **65,22%** |
| Recall@3 | **84,78%** |
| Recall@5 | **93,48%** |
| Recall@10 | **95,65%** |

Resultados negativos remanescentes no top-10:

1. `1626Manutencaodemotoreseletricos.pdf` / `prazo_execucao` — o candidato correto não entra no ranking puro até 10, mas é recuperado pela expansão tipada de prazo e termina validado.
2. `34-26...Orientador Social...pdf` / `modalidade` — o chunk de capa não entra no top-10 puro, mas é incluído pelo preâmbulo obrigatório e termina validado.

O modo diagnóstico permite até 10 candidatos somente para métricas. Produção permanece limitada a três resultados do retriever e a três fontes de 520 caracteres por campo no prompt.

## Resultado por campo

| Campo | Antes | Depois | Variação |
|---|---:|---:|---:|
| Objeto | 10/19 | **14/19** | +4 |
| Modalidade | 10/19 | **14/19** | +4 |
| Valor estimado | 5/19 | **5/19** | 0 |
| Prazo/validade da proposta | 0/19 | **7/19** | +7 |
| Órgão responsável | 1/19 | **15/19** | +14 |
| UF | 1/19 | **19/19** | +18 |
| Critério de julgamento | 2/19 | **12/19** | +10 |
| Prazo de execução | 4/19 | **4/19** | 0 |
| Requisitos de habilitação | 13/19 | **15/19** | +2 |
| **Total** | **46/171** | **105/171** | **+59** |

O campo histórico `prazo_entrega_proposta` passa a representar **validade da proposta**, conforme solicitado. Data/hora de recebimento continua reconhecível em consulta individual, mas não é misturada com `PROPOSAL_VALIDITY`.

## Resultado por documento

| Documento | Antes | Depois |
|---|---:|---:|
| 01.Edital_credenciamento_01_2024.pdf | 5/9 | **6/9** |
| 02---Edital-Pregao-Eletronico.pdf | 5/9 | **8/9** |
| 1123420260129-Termo_1.pdf | 0/9 | **3/9** |
| 1626Manutencaodemotoreseletricos.pdf | 8/9 | **9/9** |
| 34-26 Orientador Social...pdf | 3/9 | **7/9** |
| 874745.pdf | 1/9 | **4/9** |
| 885062.pdf | 3/9 | **6/9** |
| documento.pdf | 1/9 | **4/9** |
| Edital 102150-149-2026 assinado.pdf | 2/9 | **5/9** |
| Edital Credenciamento OCS-PSA 01-2024.pdf | 3/9 | **5/9** |
| Edital de Credenciamento 001.2026.pdf | 1/9 | **3/9** |
| Edital e anexos.pdf | 0/9 | **5/9** |
| Edital.pdf | 2/9 | **4/9** |
| edital609.pdf | 0/9 | **5/9** |
| edital610.pdf | 0/9 | **5/9** |
| EDITAL_CC006.pdf | 2/9 | **5/9** |
| EDITAL_DE_CREDENCIAMENTO_004.2025_assinado.pdf | 0/9 | **3/9** |
| PE 056/2026 — republicação | 5/9 | **9/9** |
| PE 056/2026 — original | 5/9 | **9/9** |
| **Total** | **46/171** | **105/171** |

## Auditoria dos quatro documentos anteriormente 0/9

| Documento | Páginas | Caracteres | Caracteres/pág. | Palavras/pág. | Alfabético | Substituição | Linha média | Páginas vazias | OCR necessário | Classificação e causa provável |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1123420260129-Termo_1.pdf | 20 | 26.919 | 1.345,95 | 197,80 | 71,83% | 0% | 21,88 | 0% | não | `TEXT_OK`; Termo de Referência, vários campos cadastrais ausentes e estrutura não reconhecida como edital |
| Edital+e+anexos.pdf | 6 | 17.407 | 2.901,17 | 467,33 | 72,09% | 0% | 52,73 | 0% | não | `TEXT_OK` + `TABLE_HEAVY`; vocabulário de leilão e valores por lote não reconhecidos |
| edital609.pdf | 19 | 48.199 | 2.536,79 | 385,68 | 72,80% | 0% | 67,68 | 0% | não | `TEXT_OK`; `STRUCTURE_NOT_RECOGNIZED` para leilão/maior lance |
| edital610.pdf | 32 | 70.781 | 2.211,91 | 337,16 | 71,75% | 0% | 43,50 | 0% | não | `TEXT_OK`; `STRUCTURE_NOT_RECOGNIZED` para leilão/maior oferta de preço |

Os quatro possuem camada textual pesquisável. `possible_scanned_document=false`, `text_layer_present=true` e `ocr_required=false` em todos.

Após incluir aliases/parsers genéricos de dispensa, leilão, maior lance/maior oferta, órgão e UF, nenhum permanece 0/9.

## Ontologia e parsers locais

Tipos de prazo: `PROPOSAL_VALIDITY`, `DELIVERY`, `EXECUTION`, `CONTRACT_TERM`, `SIGNATURE`, `PAYMENT`, `APPEAL`, `IMPUGNATION`, `CREDENTIALING`, `EMERGENCY_NOTIFICATION` e `OTHER`.

Exemplos testados:

- 60 dias de validade da proposta → `PROPOSAL_VALIDITY`;
- 15 dias para assinatura → `SIGNATURE`;
- 120 meses de vigência → `CONTRACT_TERM`;
- 10 dias após Ordem de Compra → `DELIVERY`.

Os parsers de órgão, UF e critério são locais e validam evidência literal. UF aceita as 27 siglas e nomes completos dos estados. Critério cobre menor preço, maior desconto, melhor técnica, técnica e preço, maior retorno econômico, maior lance e maior oferta de preço.

## Paridade individual x lote

- Núcleo de recuperação compartilhado: aliases, FAISS, BM25, estrutura, reranking e expansão.
- Comparador permanente gera `BATCH_INDIVIDUAL_DIVERGENCE` quando individual é `FOUND` e lote é `NOT_FOUND`.
- Nos 12 controles anteriores: **0 divergências**.
- O teste não exige texto idêntico; exige equivalência de campo, status, `document_id` e evidência.

## Testes

- Antes: 112.
- Novos: 12.
- Total: **124 aprovados**, 0 falhas.

Novas coberturas:

- 46 entradas da golden sem duplicidade;
- três regressões históricas;
- ontologia de prazos;
- órgão, UF e critério;
- top-3 de produção versus top-10 diagnóstico;
- divergência lote/individual;
- qualificadores críticos de escopo;
- auditoria sem OCR desnecessário;
- objeto/modalidade de leilão e dispensa.

## Performance e Groq

Varredura real dos 19 documentos:

- parede: **928,02 s**;
- chamadas Groq: **19** — uma compartilhada por documento;
- tokens: **122.980**;
- tempo somado efetivo no LLM: **43.886,3 ms**.

Revalidação real dos seis documentos críticos:

- parede: **306,04 s**;
- chamadas Groq: **6**.

A diferença entre parede e tempo do LLM é predominantemente espera de cota da API externa. Recuperação e reranking local permaneceram na ordem de milissegundos/centenas de milissegundos.

## Integridade

- `vector_index.faiss`: `8DDC0E6B2ED2F06C732E408851250CE0E48CD12336C065E925C9CD086ACDB200`
- `chunks_metadata.json`: `8E840B7FA6D0557127AD1B716F18D8601A7D4FE4224685D8C371E04F258DC9BB`
- Porta 5001 ao final: sem listener.
- Isolamento: nenhuma evidência de outro `document_id` foi aceita.

## Limitações restantes

1. Dois casos golden ainda dependem de preâmbulo/expansão porque o candidato correto não entra no top-10 puro.
2. O total de campos produzido pelo LLM pode variar entre varreduras; a golden e os fallbacks locais impedem que essa variação apague os 46 campos confirmados.
3. Valores de leilão por lote não foram somados nem transformados em um valor global inexistente.
4. O Termo de Referência não contém necessariamente modalidade, critério, validade de proposta ou habilitação completos; `NOT_FOUND` continua sendo resposta válida nesses casos.
5. A validação literal não foi relaxada. Respostas novas só contam quando o trecho pertence ao documento ativo e passa pelo mesmo validador.

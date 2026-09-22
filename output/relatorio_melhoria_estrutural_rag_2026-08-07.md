# Relatório da melhoria estrutural do RAG — 07/08/2026

## Resultado executivo

A rodada foi concluída de forma incremental, sem reconstruir o índice FAISS e sem alterar os metadados persistidos existentes.

- Extração em lote antes: **28/171 (16,4%)**.
- Extração em lote depois: **46/171 (26,9%)**.
- Ganho: **+18 campos** e **+10,5 pontos percentuais**.
- Matriz individual consolidada: **12/12 consultas esperadas** após corrigir os três casos antes falhos (objeto do credenciamento, valor sigiloso do PE 056/2026 e prazo de entrega de 10 dias do PE 056/2026).
- Testes automatizados: **112 aprovados**, nenhuma falha.
- Índice e metadados: hashes SHA-256 preservados.

## Mapeamento do pipeline

1. `pdf_service.py`: extração de texto por página.
2. `chunking.py`: divisão com overlap e gravação de metadados estruturais.
3. `document_structure.py`: reconhecimento de títulos, numeração, subseções, sumário e herança de seção.
4. `vector_store.py`: embeddings `all-MiniLM-L6-v2`, persistência e busca FAISS.
5. `retrieval.py`: intenção, aliases, busca densa, BM25, correspondência exata, boosts estruturais e reranking.
6. `retrieval_pipeline.py`: núcleo único de recuperação para consulta individual e lote.
7. `evidence_bundle.py`: expansão limitada da seção e de chunks adjacentes.
8. `evidence.py`: validação literal e isolamento obrigatório pelo `document_id`.
9. `agent_service.py`: resposta individual, regras determinísticas e validação por afirmação.
10. `extraction_service.py`: extração em lote com fontes separadas por campo e uma chamada compartilhada ao LLM.

## Melhorias implementadas

### Estrutura documental

- Reconhecimento de títulos como `DO OBJETO`, `DOS RECURSOS FINANCEIROS`, `DA HABILITAÇÃO`, `DO PRAZO E DO LOCAL DE ENTREGA DO OBJETO` e seções equivalentes.
- Metadados novos: `section_headings`, `section_number`, `subsection_number`, `section_title`, `section_type` e `section_inherited`.
- Detecção de sequências densas de títulos para reduzir falso positivo de sumário.
- Enriquecimento em memória para índices antigos, sem exigir reindexação.
- Boost forte para título formal com conteúdo de campo próximo; um título isolado no sumário recebe peso reduzido.

### Recuperação híbrida

- Expansão de aliases para objeto, modalidade, valor sigiloso, execução e Ordem de Compra.
- Ranking combinado: FAISS + BM25 + correspondência exata + estrutura + RRF + proximidade título/conteúdo.
- `Objeto da licitação?` passou a colocar o chunk formal `2. DO OBJETO / 2.1` no topo mesmo com a busca densa desativada.
- Expansão de evidência passou a incluir objeto, valor, modalidade e critério, além dos pacotes já existentes para prazo, habilitação e pontos de atenção.

### Resposta e evidência

- Objeto formal extraído do item numerado e resumido sem terminar no meio de uma referência legal.
- Valor confidencial reconhecido também pela redação “o valor estimado ... possuirá caráter sigiloso”.
- Prazo de entrega reconhecido pela relação completa: `10 (dez) dias` + `recebimento da Ordem de Compra`.
- Credenciamento e Inexigibilidade agora são duas afirmações validadas separadamente, cada uma com seu próprio chunk e página.
- Prazos de assinatura e vigência não são mais tratados como prazo de entrega.
- Regras societárias preservam o sujeito; quando a frase cruza chunks, o escopo é herdado do chunk imediatamente anterior.

### Extração em lote

- Consulta individual e lote usam o mesmo núcleo de busca, reranking e expansão.
- Cada campo recebe fontes próprias; o LLM não recebe mais um contexto único misturado.
- As fontes completas permanecem disponíveis para validação local.
- Apenas os excertos enviados à Groq foram limitados a três fontes de 520 caracteres por campo.
- O payload caiu de aproximadamente 14 mil tokens (erro HTTP 413) para menos do limite de 8 mil tokens, preservando uma chamada compartilhada.

### Operação e diagnóstico

- `RAG_DEBUG_RETRIEVAL=true` habilita logs opcionais de intenção, expansão, candidatos, páginas, seção e scores antes/depois do reranking.
- Rotação de chaves Groq preservada, sem registrar os valores secretos.

## Regressões nos PDFs de referência

### `01.Edital_credenciamento_01_2024.pdf`

| Consulta | Resultado atual | Evidência principal | Avaliação |
|---|---|---|---|
| Objeto | Credenciamento de OCS e PSA para serviços complementares de saúde | p. 4–6, `2. DO OBJETO / 2.1` | Aprovado |
| Modalidade | Credenciamento + Inexigibilidade | p. 5–6 e p. 13–14, duas afirmações independentes | Aprovado |
| Valor | Valor de OCS com escopo preservado; PSA sem valor global numérico no mesmo trecho | seção de recursos financeiros | Aprovado |
| Prazo de entrega | Não há prazo único; execução nos contratos; 15 dias e 120 meses apresentados separadamente | p. 13–14 | Aprovado |
| Pontos de atenção | `Sociedades Limitadas: Quórum mínimo para deliberações` | p. 6–7 | Aprovado |

### `PE+056-26+-+Proc.+00821-26+-+Aquisicao+equipamento+para+viaturas.pdf`

| Consulta | Resultado atual | Evidência principal | Avaliação |
|---|---|---|---|
| Objeto | Aquisição e instalação de equipamentos e acessórios para adaptação de viaturas | p. 23+, `1. Do Objeto / 1.1` | Aprovado |
| Modalidade | Pregão Eletrônico | capa/p. 1 | Aprovado |
| Valor | Sigiloso | p. 22–24, item 14.9 | Aprovado |
| Prazo | Até 10 dias após o recebimento da Ordem de Compra | p. 17–19, item 9.1 | Aprovado |

## Medição em lote nos 19 documentos

| Documento | Campos validados | Total |
|---|---:|---:|
| 01.Edital_credenciamento_01_2024.pdf | 5 | 9 |
| 02---Edital-Pregao-Eletronico.pdf | 5 | 9 |
| 1123420260129-Termo_1.pdf | 0 | 9 |
| 1626Manutencaodemotoreseletricos.pdf | 8 | 9 |
| 34-26 Orientador Social...pdf | 3 | 9 |
| 874745.pdf | 1 | 9 |
| 885062.pdf | 3 | 9 |
| documento.pdf | 1 | 9 |
| Edital 102150-149-2026 assinado.pdf | 2 | 9 |
| Edital Credenciamento OCS-PSA 01-2024.pdf | 3 | 9 |
| Edital de Credenciamento 001.2026.pdf | 1 | 9 |
| Edital e anexos.pdf | 0 | 9 |
| Edital.pdf | 2 | 9 |
| edital609.pdf | 0 | 9 |
| edital610.pdf | 0 | 9 |
| EDITAL_CC006.pdf | 2 | 9 |
| EDITAL_DE_CREDENCIAMENTO_004.2025_assinado.pdf | 0 | 9 |
| PE 056/2026 — republicação | 5 | 9 |
| PE 056/2026 — original | 5 | 9 |
| **Total** | **46** | **171** |

As 19 requisições terminaram com HTTP 200 e zero erro de endpoint. Ocorreram respostas 429 durante a execução, absorvidas pela rotação de chaves. O gargalo de aproximadamente 49 segundos entre alguns documentos foi a cota da Groq, não a recuperação local.

## Desempenho observado na interface

- Objeto do credenciamento: recuperação local na ordem de centenas de milissegundos; resposta total observada de 4,4 s.
- Modalidade composta: total de 862 ms, com duas evidências separadas.
- Valor sigiloso do PE 056/2026: total de 1,1 s.
- Prazo de 10 dias do PE 056/2026: total de 1,8 s.
- A expansão estrutural adiciona dezenas a poucas centenas de milissegundos, mantendo somente 2 a 5 fontes finais.

## Limitações restantes

- A taxa global de lote ainda é conservadora (26,9%): documentos com OCR ruim, tabelas fragmentadas, anexos muito extensos ou campos realmente ausentes continuam retornando `NOT_FOUND`.
- `órgão responsável`, `UF`, `critério de julgamento` e prazo da proposta ainda variam muito de forma entre os editais; são os próximos melhores candidatos para aliases e parsers estruturais genéricos.
- Documentos com 0/9 precisam de auditoria individual para distinguir texto mal extraído de informação realmente ausente.
- A avaliação mede “campo com evidência literal validada”, não apenas resposta semanticamente plausível; por isso privilegia precisão e rastreabilidade em vez de cobertura agressiva.

## Integridade

- `vector_index.faiss`: `8DDC0E6B2ED2F06C732E408851250CE0E48CD12336C065E925C9CD086ACDB200`
- `chunks_metadata.json`: `8E840B7FA6D0557127AD1B716F18D8601A7D4FE4224685D8C371E04F258DC9BB`
- Nenhum PDF foi reindexado e nenhum documento de outro `document_id` foi aceito como evidência.

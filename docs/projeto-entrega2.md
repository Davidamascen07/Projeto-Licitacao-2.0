# Agente Autônomo para Análise de Editais de Licitação

## Entrega 2 — relatório consolidado

Relatório original: 22/07/2026.

Atualização técnica: 07/08/2026.

## Equipe

| Integrante | Papel principal | Contribuição consolidada |
|---|---|---|
| Danielle Magalhães Ballester | Liderança, documentação e apresentação | Coordenação, narrativa e consolidação documental |
| Carol Anely Miranda Guzman | Dados | Organização da amostra e apoio à qualidade dos dados |
| André Joás Lima de Araújo | Engenharia e modelagem | Pipeline RAG, extração, indexação e agente |
| David Damasceno da Frota | Avaliação | Benchmark, revisão humana, métricas e análise de erros |
| Raylson Silva de Lima | Reprodutibilidade | Ambiente, testes e execução ponta a ponta |

## Resumo executivo

Foi construído um MVP de análise de editais com Flask, PyMuPDF, OCR Tesseract, MiniLM, FAISS, recuperação híbrida, extração estruturada, evidência literal e um FunctionAgent do LlamaIndex. A aplicação possui 19 PDFs e 1.064 chunks/vetores.

O benchmark experimental permanece congelado com 10 editais, 30 referências humanas e divisão fixa de 7 documentos para desenvolvimento e 3 para teste. A configuração `chunk500_overlap50_topk3` foi escolhida exclusivamente no desenvolvimento antes do teste original.

Em 07/08/2026 foram produzidos dois resultados complementares:

1. A auditoria do pipeline atual de produção examinou 19 documentos × 9 campos, totalizando 171 decisões. Foram obtidas 140 respostas externas encontradas, 167 decisões estritamente corretas, 0 casos não resolvidos e 0 regressões nos 46 casos GOLDEN.
2. A reavaliação RAGAS da configuração experimental congelada respondeu 3/9 campos, com cobertura de 33,33%, Faithfulness 1,0000, Answer Correctness 0,9578 e taxa factual de afirmações sem suporte de 0%.

## Arquitetura

Fluxo principal:

```text
PDF -> validação -> PyMuPDF/OCR -> chunks -> MiniLM -> FAISS
    -> recuperação híbrida isolada por documento
    -> extração estruturada -> validação literal -> interface/agente
```

A busca híbrida combina similaridade densa, BM25, correspondência de campo/título, estrutura e expansão de seção. Toda evidência deve pertencer ao `document_id` ativo.

## Dados e benchmark

- Corpus operacional: 19 PDFs e 1.064 chunks/vetores.
- Matriz de produção: 19 documentos × 9 campos = 171 decisões.
- Benchmark congelado: 10 editais.
- Desenvolvimento/teste: 7/3 documentos.
- Referências humanas: 30 para valor, modalidade e prazo/validade da proposta.
- PDFs fornecidos manualmente; nenhuma origem PNCP foi inventada.

## Resultado da auditoria do pipeline atual

| Indicador | Resultado |
|---|---:|
| Respostas externas encontradas | 140/171 — 81,87% |
| Decisões estritamente corretas | 167/171 — 97,66% |
| Casos GOLDEN preservados | 46/46 |
| Regressões GOLDEN | 0 |
| `UNRESOLVED` | 0 |
| Falsos positivos identificados | 0 |
| Evidências cruzadas entre documentos | 0 |
| Recall@1 / @3 / @5 / @10 | 65,22% / 84,78% / 93,48% / 95,65% |

Os quatro casos de valor variável por item/lote permanecem fora da fórmula estrita. O sistema não soma valores nem cria um total global inexistente.

## Resultado experimental RAGAS

| Métrica | Teste original de 22/07 | Reavaliação de 07/08 |
|---|---:|---:|
| Respostas | 2/9 | 3/9 |
| Cobertura | 22,22% | 33,33% |
| Faithfulness | 1,0000 | 1,0000 |
| Answer Correctness | 0,8469 | 0,9578 |
| `unsupported_claim_rate` | 0% | 0% |
| `reference_mismatch_rate` | 50% | 66,67% |

O indicador histórico de 50% antes chamado de “alucinação” era, na prática, divergência textual de referência. A regra atual separa:

- `unsupported_claim_rate`: afirmações factuais sem suporte documental;
- `reference_mismatch_rate`: resposta não literalmente equivalente ao gabarito.

Exemplos como `Leilão` × `leilão eletrônico` e `Procedimento: Credenciamento` × `credenciamento` possuem evidência válida e Faithfulness 1,0; portanto, não são alucinações factuais.

## Ontologia e decisões importantes

- `DELIVERY` e `EXECUTION` são conceitos distintos.
- Validade da proposta, assinatura, pagamento, vigência e recurso não são aceitos como prazo de entrega/execução.
- Vigência só representa execução quando o próprio trecho relaciona literalmente os conceitos.
- Credenciamentos e leilões podem produzir `NOT_APPLICABLE` em campos competitivos ou prazos que não se aplicam ao objeto.
- Valores sigilosos e valores variáveis por item possuem estados próprios.

## Qualidade de software

Em 07/08/2026, após a limpeza do projeto e a auditoria das dependências:

- 160 testes aprovados;
- 6 avisos de bibliotecas externas/depreciações;
- `requirements.txt` contém todas as importações externas diretas auditadas;
- `.gitignore` cobre ambientes virtuais, caches, logs, temporários, uploads e índices locais;
- a execução recomendada passou a usar `.venv`.

## Limitações

1. A reavaliação RAGAS tem apenas 3 documentos, 9 perguntas e 3 respostas avaliadas.
2. A cobertura de 33,33% ainda é insuficiente para uma conclusão ampla.
3. A métrica de alucinação foi corrigida após observar o teste; ela deve ser congelada e revalidada em novo holdout.
4. A auditoria de produção e o experimento congelado usam pipelines e objetivos diferentes e não devem ser comparados como se fossem a mesma avaliação.
5. O sistema não substitui revisão jurídica, técnica ou financeira.

## Conclusão

O projeto possui uma baseline técnica forte: alta precisão decisória na auditoria do pipeline atual, evidência literal, isolamento documental, ausência de regressões GOLDEN e suíte automatizada extensa. O próximo ciclo científico deve ampliar a cobertura, congelar previamente as métricas e avaliar o pipeline híbrido em um corpus novo.

## Reprodução com `.venv`

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m pytest -q tests
python app.py
```

## Artefatos

- `output/relatorio_rag_decisoes_auditaveis_2026-08-07.md`
- `output/decision_audit_2026-08-07.json`
- `evaluation/results/rerun_current_2026-08-07_test/`
- `output/presentation/Agente_Autonomo_Analise_Editais.pptx`

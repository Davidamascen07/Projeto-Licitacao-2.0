# Relatório de implementação

Atualizado em 07/08/2026.

## Situação atual

O MVP está implementado e executável em ambiente virtual Python. A aplicação contém 19 PDFs, 1.064 chunks/vetores, recuperação híbrida, validação literal e isolamento obrigatório por `document_id`.

O experimento original permanece preservado. A configuração `chunk500_overlap50_topk3` foi selecionada no desenvolvimento, congelada por hash e testada sem sobrescrever os resultados. A nova reavaliação RAGAS foi salva em `evaluation/results/rerun_current_2026-08-07_test/`.

## Componentes implementados

- Aplicação Flask e interface de upload/consulta.
- Validação de PDF, limite de tamanho, SHA-256 e duplicidade.
- Extração PyMuPDF e fallback OCR com Tesseract.
- Chunking, MiniLM, FAISS e persistência incremental.
- Recuperação densa, BM25, sinais estruturais, reranking e expansão de seção.
- Busca e evidência isoladas pelo documento ativo.
- Extração dos nove campos auditáveis.
- Taxonomia de `FOUND`, confidencial, variável, não aplicável e ausente.
- Ontologia de prazos, incluindo `DELIVERY`, `EXECUTION`, `CONTRACT_TERM`, `SIGNATURE` e `PROPOSAL_VALIDITY`.
- FunctionAgent do LlamaIndex.
- Benchmark, baselines, RAGAS, checkpoints, custos e análise de erros.
- Cliente opcional do PNCP.
- Rotação entre chaves Groq configuradas no `.env`.

## Estado verificado

| Item | Estado atual |
|---|---:|
| PDFs disponíveis/indexados | 19 |
| Chunks/vetores | 1.064 |
| Campos por documento | 9 |
| Decisões auditadas | 171 |
| Respostas externas encontradas | 140/171 |
| Decisões estritamente corretas | 167/171 |
| GOLDEN preservados | 46/46 |
| Casos `UNRESOLVED` | 0 |
| Divergência batch × individual | 0 |
| Testes automatizados | 160 aprovados |

## Melhorias recentes

1. Distinção entre prazo de entrega e prazo de execução.
2. Validação de coerência entre justificativa, tipo de documento e modalidade.
3. Tratamento de campos presentes em tabelas.
4. Auditoria manual dos casos anteriormente não resolvidos.
5. Fallbacks determinísticos conservadores para campos com evidência literal.
6. Separação entre alucinação factual e divergência textual da referência.
7. Documentação, dependências e ambiente virtual atualizados.

## Ambiente oficial

O fluxo recomendado usa `.venv`:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Depois da configuração:

```powershell
python scripts/prepare_embedding_model.py --offline-check
python -m pytest -q tests
python app.py
```

## Resultado científico atual

A reavaliação da configuração experimental congelada obteve cobertura 33,33%, Faithfulness 1,0000, Answer Correctness 0,9578 e `unsupported_claim_rate` 0%. O `reference_mismatch_rate` de 66,67% representa divergências textuais com evidência válida.

A hipótese é confirmada somente nesse recorte segundo a métrica corrigida. Como a fórmula foi ajustada após a observação do teste, a confirmação definitiva depende de um novo holdout.

## Próximos passos

1. Congelar a definição das métricas antes de nova avaliação.
2. Criar um holdout não consultado.
3. Ampliar o benchmark e diversificar modalidades/documentos.
4. Avaliar o pipeline híbrido de produção com o mesmo protocolo RAGAS.
5. Melhorar a cobertura sem relaxar a validação literal.

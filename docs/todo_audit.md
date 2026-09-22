# Auditoria de pendências

Atualizado em 07/08/2026.

## Concluído

- 19 PDFs e 1.064 chunks/vetores disponíveis.
- Benchmark de 10 editais com split fixo 7/3.
- 30 referências humanas validadas.
- Experimento original preservado e configuração congelada por hash.
- Reavaliação RAG salva em diretório separado.
- Métrica de alucinação factual separada de mismatch textual.
- Recuperação híbrida com isolamento por `document_id`.
- Distinção `DELIVERY` × `EXECUTION`.
- Coerência entre justificativa, documento e modalidade.
- Caso de campo em tabela resolvido.
- Casos anteriormente `UNRESOLVED` auditados; estado atual igual a 0.
- 46/46 casos GOLDEN preservados.
- Auditoria das 171 decisões concluída.
- `requirements.txt`, `.env.example`, `.gitignore` e documentação atualizados.
- Execução oficial documentada com `.venv`.
- 160 testes aprovados.
- Apresentação em `output/presentation/Agente_Autonomo_Analise_Editais.pptx`.

## Próxima rodada científica

- Congelar formalmente `unsupported_claim_rate` e `reference_mismatch_rate`.
- Criar um novo holdout ainda não consultado.
- Ampliar o benchmark e incluir mais modalidades e estruturas documentais.
- Avaliar o pipeline híbrido atual com RAGAS.
- Usar cobertura como critério primário junto com fidelidade e correção.
- Regenerar gráficos finais depois da nova avaliação.

## Pendências de governança

- Confirmar contribuições individuais em `docs/contributions.md` com cada integrante.
- Registrar URL, órgão e data de coleta em novas aquisições oficiais.
- Repetir o teste online do PNCP quando o endpoint estiver disponível.

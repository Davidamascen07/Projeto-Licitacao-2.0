# Limitações

Atualizado em 07/08/2026.

## Dados e validade externa

- O corpus operacional contém 19 PDFs fornecidos manualmente e não garante representatividade nacional.
- A origem dos PDFs não foi atribuída retroativamente ao PNCP ou Compras.gov.br.
- OCR, digitalização, anexos e tabelas podem reduzir a qualidade do texto extraído.
- A avaliação experimental usa uma única divisão 7/3.

## Avaliação

- A reavaliação RAGAS contém 3 documentos, 9 perguntas e somente 3 respostas avaliadas.
- A cobertura experimental de 33,33% é baixa.
- As médias de Faithfulness e Answer Correctness são condicionais às respostas existentes.
- A métrica de alucinação factual foi corrigida após a observação do teste; a nova definição precisa ser congelada antes de novo holdout.
- `reference_mismatch_rate` não mede alucinação e não deve ser interpretada como falta de suporte factual.
- O pipeline experimental congelado não é idêntico ao pipeline híbrido atual de produção.

## Operação

- Geração e avaliação dependem de serviço externo, disponibilidade, chaves e limites de taxa.
- O MiniLM deve existir no cache local quando `EMBEDDING_OFFLINE=true`.
- Quatro documentos possuem valores variáveis por item/lote; o sistema não calcula total artificial.
- Estados `NOT_APPLICABLE` e `ACTUALLY_ABSENT` dependem de evidência negativa e continuam recomendando revisão humana em decisões sensíveis.
- Tokens internos do avaliador RAGAS podem não possuir telemetria consolidada.

## Uso responsável

O sistema apoia triagem e auditoria documental. Ele não substitui análise jurídica, técnica, financeira nem a leitura integral do edital e de seus anexos.

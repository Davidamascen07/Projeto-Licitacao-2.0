# Recuperação híbrida da aplicação

Atualizado em 07/08/2026.

## Visão geral

A consulta operacional usa uma camada híbrida sobre o índice FAISS. Ela combina candidatos densos, lexicais e estruturais, remove duplicidades, aplica reranking local e envia ao modelo somente as fontes de maior prioridade.

Pontuação-base:

```text
0,40 × similaridade densa
+ 0,25 × BM25 normalizado
+ 0,25 × correspondência exata de campo/título
+ 0,10 × posição e estrutura do documento
```

As regras estruturais funcionam com os metadados antigos. Novos chunks também recebem `document_part`, `section`, `heading` e `is_preamble`.

## Isolamento e custo

- `document_id` é obrigatório.
- Não existe fallback para busca global.
- Candidatos ampliados são processados localmente.
- O PDF completo não é enviado ao modelo.
- Evidência de outro documento é rejeitada.
- Consultas em lote compartilham uma chamada remota quando o LLM é necessário; regras simples permanecem locais.

## Intenções e estrutura

Consultas como `Objeto?`, `Qual é o objeto?` e `O que está sendo contratado?` recebem aliases e reforço para títulos como `DO OBJETO`.

O retriever usa expansão específica para modalidade, valor, habilitação e prazos. Seções e preâmbulos podem inserir candidatos que não aparecem no ranking denso puro, sem alterar o limite final de fontes.

## Ontologia de prazos

Os tipos reconhecidos incluem:

- `PROPOSAL_VALIDITY`;
- `DELIVERY`;
- `EXECUTION`;
- `CONTRACT_TERM`;
- `SIGNATURE`;
- `PAYMENT`;
- `APPEAL`;
- `IMPUGNATION`;
- `CREDENTIALING`;
- `OTHER`.

`DELIVERY` e `EXECUTION` são mantidos separados. Uma aquisição pode ter entrega física e não ter prazo de execução. Um serviço pode ocorrer sob demanda ou durante a vigência sem possuir prazo único de entrega.

Vigência só é aceita como execução quando o próprio trecho relaciona literalmente os conceitos. Prazos de assinatura, pagamento, recurso ou validade não são promovidos como entrega/execução.

## Coerência do documento

A validação considera a natureza do documento e da contratação:

- credenciamento pode estar associado à inexigibilidade e não a uma modalidade competitiva comum;
- leilão usa maior lance/maior oferta, e não menor preço;
- termo de referência pode não conter modalidade ou habilitação completas;
- justificativa e resposta precisam ser coerentes com o tipo/modalidade identificado.

## Tabelas, valores e ausência

Campos em tabelas recebem tratamento específico. Valor global, máximo, de referência, orçamentário, sigiloso e variável por item/lote são estados diferentes.

Quando não existe um total global, o sistema responde que o valor varia por item/lote em vez de somar valores. `NOT_APPLICABLE`, `ACTUALLY_ABSENT` e `FIELD_VARIABLE_BY_ITEM` não são convertidos artificialmente em `FOUND`.

## Métricas atuais

Na auditoria de 171 decisões:

- Recall@1: 65,22%;
- Recall@3: 84,78%;
- Recall@5: 93,48%;
- Recall@10: 95,65%;
- respostas externas encontradas: 140/171;
- decisões estritamente corretas: 167/171;
- casos não resolvidos: 0;
- regressões GOLDEN: 0.

## Relação com o experimento

O resultado histórico usa `chunk500_overlap50_topk3`. O pipeline híbrido atual é posterior e inclui taxonomia, expansão e fallbacks adicionais. Ele deve ser avaliado em novo protocolo, com métricas congeladas e holdout não consultado, sem sobrescrever o teste histórico.

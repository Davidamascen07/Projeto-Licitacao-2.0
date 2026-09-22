# Perguntas e respostas para apresentação e banca

Atualizado em 07/08/2026.

## Visão geral do projeto

### 1. Qual problema o projeto busca resolver?

O projeto reduz o esforço necessário para localizar informações críticas em editais extensos e fragmentados. Ele permite consultar campos como objeto, modalidade, valor e prazos, apresentando documento, páginas e evidência literal para auditoria.

### 2. O projeto é apenas um chatbot para PDFs?

Não. O diferencial é o pipeline de recuperação e validação. O sistema indexa os documentos, recupera trechos por intenção, estrutura a resposta e verifica se existe evidência literal no documento ativo antes de apresentá-la.

### 3. Qual é o objetivo principal do MVP?

Demonstrar que um agente baseado em RAG pode apoiar a análise de editais com respostas rastreáveis, reduzindo invenções factuais e permitindo que o usuário confira a fonte utilizada.

### 4. Quais informações o sistema consegue analisar?

A auditoria atual trabalha com nove campos: objeto, modalidade, valor estimado, validade/prazo da proposta, órgão responsável, UF, critério de julgamento, prazo de execução e requisitos de habilitação.

### 5. Quantos documentos existem atualmente no sistema?

A aplicação possui 19 PDFs e 1.064 chunks/vetores no índice FAISS. O benchmark experimental é menor e contém 10 editais, divididos em 7 documentos para desenvolvimento e 3 para teste.

## Arquitetura e funcionamento

### 6. O que significa RAG?

RAG significa Retrieval-Augmented Generation, ou geração aumentada por recuperação. Antes de responder, o sistema busca no documento trechos relevantes e os fornece ao modelo de linguagem como contexto.

### 7. Como funciona o fluxo completo?

O fluxo é: validação do PDF, extração de texto com PyMuPDF ou OCR, divisão em chunks, geração de embeddings MiniLM, indexação FAISS, recuperação híbrida, extração estruturada, validação literal e exibição da resposta com suas fontes.

### 8. Por que utilizar FAISS?

FAISS oferece busca vetorial rápida e local. Ele permite comparar o embedding da pergunta com os embeddings dos trechos sem enviar o PDF completo para um serviço externo.

### 9. O que é recuperação híbrida?

É a combinação de vários sinais de busca. O sistema usa similaridade densa do FAISS, BM25 lexical, correspondência de campo ou título, posição no documento e expansão de seção. Isso melhora casos em que somente a busca semântica não encontra o trecho correto.

### 10. Por que não usar somente busca por palavras-chave?

Palavras isoladas são ambíguas. Por exemplo, `prazo` pode significar entrega, execução, pagamento, assinatura, recurso ou vigência. A recuperação híbrida considera intenção, contexto e estrutura do documento.

### 11. Qual modelo de embeddings foi utilizado?

Foi utilizado o `all-MiniLM-L6-v2`. Ele foi escolhido por ser leve, rápido em CPU e adequado ao MVP. Uma limitação é não ser especializado em português jurídico; comparar com um modelo multilíngue é um próximo passo possível.

### 12. O modelo de linguagem recebe o PDF inteiro?

Não. O sistema envia somente os trechos mais relevantes. Isso reduz custo, latência e risco de ultrapassar limites de contexto.

### 13. Quando o OCR é utilizado?

O OCR com Tesseract é um fallback para documentos sem camada textual adequada. PDFs que já possuem texto pesquisável são processados diretamente pelo PyMuPDF, evitando OCR desnecessário.

### 14. Como o sistema evita misturar dois editais?

Toda busca exige um `document_id`. O retriever não possui fallback global, e a validação rejeita evidências de outro documento. Na auditoria atual, nenhuma evidência cruzada foi aceita.

### 15. O que é o FunctionAgent do LlamaIndex?

É a camada de orquestração que disponibiliza a busca documental como ferramenta do agente. Nos experimentos controlados, o núcleo RAG foi avaliado diretamente para manter chamadas e configurações comparáveis.

## Recuperação, interpretação e evidência

### 16. O que acontece quando o trecho correto não está entre os primeiros resultados?

O sistema pode aplicar aliases, reforço de título, preâmbulo obrigatório e expansão de seção. Essas estratégias recuperam trechos estruturais importantes sem permitir busca em outro documento.

### 17. Como o sistema trata a seção “DO OBJETO”?

Perguntas como `Objeto?`, `Qual é o objeto?` e `O que está sendo contratado?` são normalizadas para a mesma intenção. Títulos como `DO OBJETO` e expressões como `objeto deste edital` recebem prioridade adicional.

### 18. Por que prazo de entrega e prazo de execução precisam ser separados?

Porque representam eventos diferentes. Entrega normalmente se aplica ao fornecimento de bens, enquanto execução pode representar prestação de serviço, obra ou atividade sob demanda. O sistema não deve responder prazo de assinatura, pagamento ou vigência como se fosse entrega.

### 19. Um prazo de vigência pode ser usado como prazo de execução?

Somente quando o próprio texto relaciona literalmente execução e vigência. Caso contrário, os conceitos permanecem separados para evitar uma inferência indevida.

### 20. Como o sistema responde quando um campo não se aplica?

Ele pode retornar `NOT_APPLICABLE` com uma justificativa. Por exemplo, um credenciamento para serviços pode não possuir prazo único de entrega, e um leilão pode não possuir prazo de execução contratual do objeto.

### 21. Qual é a diferença entre campo ausente e campo não aplicável?

`ACTUALLY_ABSENT` significa que o campo seria pertinente, mas não foi encontrado após a varredura. `NOT_APPLICABLE` significa que o campo não faz sentido para aquela natureza de documento ou contratação.

### 22. Como valores por item ou lote são tratados?

O sistema usa o estado `FIELD_VARIABLE_BY_ITEM`. Ele informa que não existe um único valor global e não soma automaticamente os itens, pois isso poderia criar um total que o edital não declarou.

### 23. Como um valor sigiloso é tratado?

O estado `FIELD_CONFIDENTIAL` registra que o valor existe, mas foi declarado sigiloso. Externamente, isso é uma resposta encontrada, sem inventar um número.

### 24. O que torna uma evidência válida?

A evidência precisa pertencer ao documento ativo, estar associada ao campo consultado e sustentar literalmente a afirmação. Número, unidade, sujeito, condição e escopo precisam ser coerentes.

## Avaliação e métricas

### 25. Qual foi o resultado da auditoria do pipeline atual?

Foram auditadas 171 decisões, correspondentes a 19 documentos e 9 campos. O sistema obteve 140 respostas externas encontradas, 167 decisões estritamente corretas, 0 casos não resolvidos e 0 regressões nos 46 casos GOLDEN.

### 26. O que significa 97,66% de decisões corretas?

Significa que 167 das 171 decisões foram classificadas corretamente segundo a fórmula estrita da auditoria. Os quatro casos restantes eram valores variáveis por item ou lote, que são respostas contextuais úteis, mas ficaram fora da fórmula solicitada.

### 27. O que são casos GOLDEN?

São casos previamente confirmados e usados como proteção contra regressão. Depois das melhorias, os 46 casos GOLDEN continuaram corretos: 46/46 preservados.

### 28. Quais foram os resultados da reavaliação RAGAS?

Na configuração experimental congelada, o RAG respondeu 3 de 9 perguntas. A cobertura foi 33,33%, Faithfulness 1,0000, Answer Correctness 0,9578, taxa de afirmações sem suporte de 0% e mismatch textual de 66,67%.

### 29. Por que a cobertura de 33,33% ainda é considerada baixa?

Porque somente três perguntas receberam resposta. As médias de fidelidade e correção são calculadas sobre essas três respostas e, portanto, não demonstram desempenho suficiente no conjunto inteiro.

### 30. Se a cobertura é baixa, por que a Faithfulness é 1,0?

Faithfulness mede se as respostas produzidas são sustentadas pelo contexto. Ela não mede quantas perguntas foram respondidas. O sistema pode ser muito fiel quando responde e, ao mesmo tempo, deixar muitas perguntas sem resposta.

### 31. Qual é a diferença entre Faithfulness e Answer Correctness?

Faithfulness verifica suporte no contexto recuperado. Answer Correctness compara a resposta com a referência humana, considerando proximidade factual e semântica.

### 32. Por que a métrica antiga de alucinação foi corrigida?

A regra antiga confundia diferença textual com alucinação factual. Respostas como `Leilão` em relação a `leilão eletrônico` estavam sustentadas pela evidência, mas eram marcadas como problema por não serem literalmente iguais ao gabarito.

### 33. O que é `unsupported_claim_rate`?

É a taxa de afirmações factuais sem suporte documental. Essa é a métrica usada atualmente para representar alucinação factual.

### 34. O que é `reference_mismatch_rate`?

É a taxa de respostas que não são literalmente equivalentes à referência humana. Um mismatch pode indicar resposta incompleta ou diferença de normalização, mas não significa automaticamente que houve invenção.

### 35. Por que o mismatch foi 66,67% se a Faithfulness foi 1,0?

Duas das três respostas tinham formulação diferente da referência, mas estavam sustentadas pelo documento. Foram os casos `Leilão` × `leilão eletrônico` e `Procedimento: Credenciamento` × `credenciamento`.

### 36. A hipótese do projeto foi confirmada?

Segundo a métrica corrigida, as três metas foram atingidas no pequeno recorte reavaliado. Entretanto, a correção ocorreu após observar o teste e a cobertura permaneceu baixa. Por rigor científico, a confirmação deve ser considerada provisória até a validação em um novo holdout.

### 37. A auditoria de 171 decisões e a avaliação RAGAS medem a mesma coisa?

Não. A auditoria avalia decisões do pipeline híbrido atual em nove campos e usa validações determinísticas e literais. A avaliação RAGAS usa a configuração experimental congelada em três campos e três documentos. Os resultados são complementares, mas não podem ser combinados como uma única métrica.

### 38. Quais foram os valores de recall do retriever?

Na auditoria dos casos GOLDEN, Recall@1 foi 65,22%, Recall@3 84,78%, Recall@5 93,48% e Recall@10 95,65%.

### 39. Por que não maximizar apenas o Recall@10?

Recuperar muitos trechos pode aumentar ruído, custo e risco de confusão. O sistema usa mais candidatos localmente para diagnóstico e reranking, mas limita as fontes finais enviadas ao modelo.

## Metodologia e rigor científico

### 40. Como foi evitado vazamento entre desenvolvimento e teste?

A configuração foi selecionada somente no split de desenvolvimento e congelada por hash antes do teste original. Os artefatos antigos foram preservados e a reavaliação foi salva em outro diretório.

### 41. Por que a configuração experimental não foi substituída pelo pipeline atual?

Substituí-la invalidaria a comparação histórica. O pipeline híbrido atual é uma nova versão e precisa de um novo protocolo, métricas congeladas e um conjunto de teste ainda não consultado.

### 42. Qual é o principal risco metodológico atual?

O principal risco é o tamanho reduzido da amostra, combinado com a correção pós-hoc da métrica de alucinação. A solução é congelar a nova definição e validá-la em um holdout novo e maior.

### 43. Por que não afirmar que o projeto possui 0% de alucinação em geral?

Porque o 0% foi observado somente nas três respostas da reavaliação. Ele não permite generalizar para todos os documentos, perguntas e versões do pipeline.

### 44. Os PDFs vieram do PNCP?

Não existe evidência para atribuir os PDFs atuais ao PNCP. Eles foram fornecidos manualmente. O projeto possui um conector opcional para o PNCP, mas mantém downloads oficiais separados do benchmark.

## Implementação, custo e operação

### 45. Por que usar a Groq?

A Groq disponibilizou o modelo usado no experimento com baixa latência de inferência e plano gratuito. O projeto também registra tokens, tempo e custo teórico para tornar a execução auditável.

### 46. Qual foi o custo da reavaliação?

A reavaliação utilizou 6.601 tokens de geração e teve custo teórico estimado de US$ 0,00129390. Como foi usado o plano gratuito, isso não representa cobrança observada.

### 47. Por que algumas consultas demoram vários segundos?

O processamento local é rápido, mas a chamada ao modelo pode sofrer espera preventiva ou limite de taxa do plano gratuito. A interface separa os tempos de embedding, FAISS, reranking, recuperação, espera externa e LLM.

### 48. O que acontece se uma chave da Groq atingir o limite?

O `.env` aceita uma chave principal e chaves alternativas. O sistema pode usar a configuração de contingência sem expor as chaves na interface ou no repositório.

### 49. Como o projeto deve ser instalado?

O fluxo atual usa uma `.venv`: criar com `py -m venv .venv`, ativar com `.\.venv\Scripts\Activate.ps1` e instalar com `python -m pip install -r requirements.txt`.

### 50. Quantos testes automatizados existem?

A última execução completa terminou com 160 testes aprovados e 6 avisos de bibliotecas externas ou depreciações.

### 51. O sistema está pronto para produção?

Ele está pronto como MVP e baseline técnica para testes ampliados. Para produção real ainda seriam necessários autenticação, controle de acesso, observabilidade, política de retenção, gestão segura de segredos, monitoramento, avaliação contínua e revisão jurídica.

### 52. Como o sistema trata segurança e privacidade?

Os PDFs e o índice ficam localmente, e o PDF completo não é enviado ao modelo. As chaves ficam no `.env`, que é ignorado pelo Git. Em produção ainda seria necessário definir criptografia, permissões, retenção e auditoria de acesso.

## Demonstração e perguntas críticas

### 53. O que fazer se o sistema responder “informação não encontrada” durante a apresentação?

Explique que a recusa é preferível a inventar uma resposta. Depois, confira as fontes recuperadas e classifique se o caso representa ausência real, campo não aplicável ou falha de recuperação.

### 54. E se o professor encontrar a informação manualmente no PDF?

Reconheça como falha de recuperação ou validação, registre documento, página e trecho e transforme o caso em teste de regressão. Esse processo já foi usado nas rodadas anteriores para melhorar objeto, modalidade, valores e prazos.

### 55. Como demonstrar que a resposta não veio de outro PDF?

Mostre o edital ativo, o nome da fonte, as páginas e a evidência. O backend também valida que todos os chunks possuem o mesmo `document_id` da consulta.

### 56. Qual exemplo mostra a importância da interpretação semântica?

O exemplo de prazo é o mais claro: 15 dias para assinatura de contrato e 120 meses de vigência não são prazo de entrega. O sistema precisa identificar o evento associado ao número, e não somente encontrar a palavra `prazo`.

### 57. Qual foi a melhoria mais importante do projeto?

A mudança de uma busca genérica para decisões auditáveis com taxonomia. O sistema passou a distinguir encontrado, sigiloso, variável, não aplicável e ausente, além de separar os diferentes tipos de prazo.

### 58. Qual é a principal contribuição acadêmica?

A principal contribuição é demonstrar, com artefatos reproduzíveis, que a avaliação de RAG precisa considerar simultaneamente suporte factual, correção, cobertura, isolamento documental e taxonomia de ausência. Uma única média não descreve adequadamente o comportamento do sistema.

### 59. Qual é o próximo passo prioritário?

Congelar as métricas corrigidas, criar um novo holdout e avaliar o pipeline híbrido atual em um corpus maior. A meta é elevar cobertura sem relaxar evidência literal ou aumentar falsos positivos.

### 60. Se fosse possível melhorar apenas uma parte, qual seria?

A recuperação dos campos ainda não respondidos. Faithfulness já foi alta nas respostas existentes; portanto, o maior ganho virá de aumentar cobertura com reforço de seção, tabelas, anexos e consultas específicas por intenção.

## Resposta final sugerida para encerramento

> O projeto demonstrou que é possível analisar editais com respostas auditáveis e evidência literal. O pipeline atual apresentou alta precisão decisória e zero regressões nos casos confirmados, enquanto a avaliação experimental mostrou fidelidade elevada, mas cobertura ainda limitada. Por isso, consideramos o sistema uma baseline técnica forte, pronta para uma avaliação maior, e não uma substituição da análise profissional.

## Referências internas

- `README.md`
- `docs/projeto-entrega2.md`
- `docs/implementation_report.md`
- `docs/experimental_results.md`
- `docs/hybrid_retrieval.md`
- `docs/limitations.md`
- `output/relatorio_rag_decisoes_auditaveis_2026-08-07.md`
- `evaluation/results/rerun_current_2026-08-07_test/comparison_report.md`
- `output/presentation/Agente_Autonomo_Analise_Editais.pptx`

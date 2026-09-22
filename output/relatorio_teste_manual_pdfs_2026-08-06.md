# Relatório de teste manual dos PDFs indexados

Data: 2026-08-06  
Servidor de teste: `http://127.0.0.1:5001`  
Processo isolado: PID 23852  
Índice: 19 documentos, 1.064 trechos e 1.064 vetores; armazenamento consistente.  
Chaves Groq reconhecidas: 4 (valores omitidos).

## Critério

- **Passou**: resposta sustentada por evidência do documento ativo.
- **Não aplicável**: resposta correta para campo incompatível com a natureza do objeto.
- **Falhou**: informação existente no PDF, mas não encontrada/validada pelo agente.
- **Sem confirmação**: o extrator não validou o campo e ele não foi conferido individualmente neste ciclo.

## Extração em lote pela interface

Foram selecionados individualmente os 19 documentos e acionado o botão **Extrair campos principais**. Em todas as execuções, o documento selecionado permaneceu igual ao documento das evidências.

| Documento | Campos validados | Resultado |
|---|---:|---|
| 01.Edital_credenciamento_01_2024.pdf | 2/9 | Parcial: modalidade e habilitação |
| 02---Edital-Pregao-Eletronico.pdf | 2/9 | Parcial: critério e habilitação |
| 1123420260129-Termo_1.pdf | 0/9 | Sem campos validados |
| 1626Manutencaodemotoreseletricos.pdf | 9/9 | Passou integralmente |
| 34-26+-+Orientador+Social+e+servico+tecnico+assistencial+-+PE+29-26+-+Comprasgov+__-26.pdf | 1/9 | Parcial: habilitação |
| 874745.pdf | 1/9 | Parcial: habilitação |
| 885062.pdf | 1/9 | Parcial: habilitação |
| documento.pdf | 2/9 | Parcial: modalidade e habilitação |
| Edital+102150-+149+-+2026+assinado.pdf | 1/9 | Parcial: habilitação |
| Edital+Credenciamento_OCS-PSA+01-2024.pdf | 2/9 | Parcial: modalidade e habilitação |
| Edital+de+Credenciamento+n+001.2026.pdf | 1/9 | Parcial: habilitação |
| Edital+e+anexos.pdf | 0/9 | Sem campos validados |
| Edital.pdf | 1/9 | Parcial: habilitação |
| edital609.pdf | 0/9 | Sem campos validados |
| edital610.pdf | 0/9 | Sem campos validados |
| EDITAL_CC006.pdf | 2/9 | Parcial: objeto e habilitação |
| EDITAL_DE_CREDENCIAMENTO_004.2025_assinado.pdf | 1/9 | Parcial: habilitação |
| PE+056-26+-+Proc.+00821-26+-+Aquisicao+equipamento+para+viaturas.pdf | 1/9 | Parcial: habilitação |
| PE+056-26+-+Proc.+00821-26+-+Aquisicao+equipamento+para+viaturas+-+Rep.pdf | 1/9 | Parcial: habilitação |

Total: 28 campos validados em 171 tentativas (16,4%). Um documento passou integralmente, 14 tiveram resultado parcial e quatro não validaram nenhum campo.

### Resultado por campo

| Campo | Validados |
|---|---:|
| Objeto | 2/19 |
| Modalidade | 4/19 |
| Valor estimado | 1/19 |
| Prazo da proposta | 1/19 |
| Órgão responsável | 1/19 |
| UF | 1/19 |
| Critério de julgamento | 2/19 |
| Prazo de execução | 1/19 |
| Requisitos de habilitação | 15/19 |

## Consultas individuais de controle

Foram executadas 12 perguntas pela interface em três documentos. Resultado: 7 `FOUND`, 2 `NOT_APPLICABLE` corretos e 3 falhas reais.

| Documento | Pergunta | Status | Páginas principais | Avaliação |
|---|---|---|---|---|
| 02---Edital-Pregao-Eletronico.pdf | Objeto | FOUND | 1-4 | Passou |
| 02---Edital-Pregao-Eletronico.pdf | Modalidade | FOUND | 1-4 | Passou: Pregão Eletrônico |
| 02---Edital-Pregao-Eletronico.pdf | Valor estimado | FOUND | 1-4 | Passou: R$ 128.068.464,63 |
| 02---Edital-Pregao-Eletronico.pdf | Prazo de entrega | NOT_APPLICABLE | 43-48 | Passou: não há prazo único; execução por ordens de serviço |
| 01.Edital_credenciamento_01_2024.pdf | Objeto | NOT_FOUND | recuperou 8-10 | **Falhou**: o objeto está visível na capa e na página 3 |
| 01.Edital_credenciamento_01_2024.pdf | Modalidade | FOUND | 13-14 | Passou: Credenciamento/Inexigibilidade |
| 01.Edital_credenciamento_01_2024.pdf | Valor estimado | FOUND | 12-13 | Passou: R$ 950.000,00 para OCS; PSA sem valor global no trecho |
| 01.Edital_credenciamento_01_2024.pdf | Prazo de entrega | NOT_APPLICABLE | 12-14 | Passou: contratos; 15 dias para assinatura e 120 meses de vigência separados |
| PE+056-26+-+Proc.+00821-26+-+Aquisicao+equipamento+para+viaturas.pdf | Objeto | FOUND | 23-25 | Passou |
| PE+056-26+-+Proc.+00821-26+-+Aquisicao+equipamento+para+viaturas.pdf | Modalidade | FOUND | 1-3 | Passou: Pregão Eletrônico |
| PE+056-26+-+Proc.+00821-26+-+Aquisicao+equipamento+para+viaturas.pdf | Valor estimado | NOT_FOUND | recuperou 21-24 | **Falhou**: a página 22 informa que o valor estimado é sigiloso |
| PE+056-26+-+Proc.+00821-26+-+Aquisicao+equipamento+para+viaturas.pdf | Prazo de entrega | NOT_FOUND | recuperou 17-19 e 25-26 | **Falhou**: páginas 18 e 25 fixam até 10 dias após a Ordem de Compra |

## Diagnóstico

1. O isolamento por `document_id` passou em 100% das interações observadas.
2. O índice está carregado e consistente.
3. A consulta individual é significativamente melhor que a extração em lote.
4. O extrator em lote apresenta falsos negativos generalizados, especialmente em objeto, modalidade, valor e prazos.
5. Persistem três falsos negativos confirmados nas consultas individuais: objeto do credenciamento; valor sigiloso e prazo de 10 dias do pregão de equipamentos.

## Upgrade das chaves

O cliente Groq agora:

- usa a chave ativa como principal;
- reconhece chaves de contingência em `GROQCLOUD_API_KEYS`, variáveis numeradas ou comentários formados somente por `# gsk_...`;
- elimina duplicatas;
- alterna somente em erros de autenticação, cota ou limite;
- nunca registra os valores das chaves.

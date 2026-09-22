# Decisões de arquitetura e fonte dos dados

Data original: 22/07/2026.

Atualização: 07/08/2026.

## PNCP e Compras.gov.br

O PDF-base inclui como objetivo específico coletar editais e metadados pelas APIs oficiais. Por isso, foi implementado um conector de leitura para o PNCP:

- `services/pncp_service.py`: consulta de contratações por publicação, listagem e download de documentos;
- `scripts/collect_pncp.py`: interface de linha de comando;
- validação de data, CNPJ, página, assinatura PDF e limite de 50 MB;
- retries para falhas temporárias;
- registro de URL oficial, data de recuperação, identificadores PNCP, SHA-256 e metadados do documento;
- armazenamento separado em `data/pncp_downloads`, sem contaminar o benchmark congelado.

Exemplos:

Os exemplos pressupõem a `.venv` ativada:

```powershell
.\.venv\Scripts\Activate.ps1
python scripts/collect_pncp.py search --start 20260701 --end 20260702 --modality 6 --page 1 --uf CE
python scripts/collect_pncp.py download --cnpj 12345678000199 --year 2026 --sequence 7
```

Os 19 PDFs atualmente disponíveis foram fornecidos manualmente pelo usuário. Sua origem não será retroativamente atribuída ao PNCP/Compras.gov.br. A consulta real de fumaça feita em 22/07/2026 expirou após as retentativas da API; assim, a integração está implementada e testada com respostas simuladas, mas a coleta online ainda precisa ser confirmada quando o serviço estiver disponível.

Fontes oficiais consultadas:

- API PNCP Consulta: https://pncp.gov.br/api/consulta/swagger-ui/index.html
- Manual de Integração PNCP: https://pncp.gov.br/manual/pt-br/latest/singlehtml/index.html
- Dados Abertos PNCP: https://www.gov.br/pncp/pt-br/acesso-a-informacao/dados-abertos

## FunctionAgent

Foi implementado um `FunctionAgent` real em `services/agent_workflow.py`. Sua ferramenta de busca exige `document_id`, limita `top_k` e rejeita resultados de outros editais.

Para preservar reprodutibilidade, os experimentos comparam diretamente o núcleo de extração usado como ferramenta. O loop do agente não participa do ajuste das 12 configurações, pois acrescentaria decisões de orquestração e chamadas diferentes entre configurações.

- Aplicação: agente disponível para orquestração de consultas.
- Avaliação: núcleo RAG/extrator comparado de forma controlada aos baselines.

## Recuperação híbrida e isolamento

O pipeline operacional atual combina FAISS, BM25, sinais de título/seção, preâmbulo e expansão de seções. `document_id` é obrigatório em todas as rotas de recuperação, e qualquer evidência pertencente a outro documento é rejeitada.

A auditoria atual confirmou 0 evidências cruzadas em 171 decisões e paridade entre consulta individual e extração em lote nos controles permanentes.

## Decisão sobre métricas

Alucinação factual passou a significar afirmação sem suporte documental, registrada como `unsupported_claim_rate`. Divergência textual em relação ao gabarito é registrada separadamente como `reference_mismatch_rate`.

Essa separação evita classificar respostas sustentadas, como `Leilão` em relação a `leilão eletrônico`, como invenções factuais.

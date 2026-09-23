# Sugestões de Arquitetura e Stack — Para Discussão

**Data**: 23 de setembro de 2026
**Status**: 🟡 Rascunho para debate — **nada aqui está decidido**
**Objetivo**: Servir de ponto de partida para a reunião de definição de arquitetura, não como recomendação fechada.

---

## Aviso Importante

Este documento **não é uma decisão de arquitetura**. É uma lista de opções e trade-offs para a equipe discutir em reunião. Pontos que precisam ficar claros antes de qualquer escolha virar definitiva:

- O projeto está em fase de ideação/pré-incubação — **não há orçamento definido** para infraestrutura paga.
- Nenhuma decisão de provedor de nuvem (AWS, GCP, Azure, ou nenhum) foi tomada.
- A prioridade agora é conseguir prototipar e validar a ideia com a PoC, não montar infraestrutura de produção.

Qualquer sugestão de custo abaixo é apenas para dar noção de ordem de grandeza — **não é orçamento aprovado**.

---

## O Que Já Existe no Projeto Atual (v1)

Antes de discutir stack novo, vale mapear o que já está funcionando e pode ser reaproveitado:

- Pipeline de extração de requisitos com embeddings (Mini LM) + reranker, desenvolvido por André
- Aplicação backend em Python (`app.py`)
- Base de 50 editais já coletada e estruturada (baseline)

**Pergunta para reunião**: reaproveitar esse código como base do repositório novo, ou é reescrita do zero? Isso muda drasticamente a estimativa de esforço.

---

## Coleta de Editais — Decisão Já Tomada: Coleta Própria

Diferente do que constava na reunião de 22/09 (uso da API de terceiros "Busca Editais"), a equipe decidiu **não depender de API de terceiros** para a coleta de editais. Isso evita:
- Dependência de disponibilidade/mudanças de um serviço externo fora do nosso controle
- Limitações de uso, custo ou throttling impostos por terceiros
- Risco de o diferencial do produto (confiabilidade auditável) depender de uma caixa-preta externa

**O que precisa ser definido em reunião**: como será essa coleta própria — via scraping direto do compras.gov.br, via API pública do PNCP (Portal Nacional de Contratações Públicas, que já tem conector opcional implementado no projeto v1 em `scripts/collect_pncp.py`), ou uma combinação dos dois. O projeto v1 já tem um ponto de partida técnico para isso — vale avaliar antes de decidir reescrever.

---

## Opções de Frontend (Para Debate)

| Opção                                                                           | Quando faz sentido                                            | Trade-off                                                                      |
| --------------------------------------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| **Sem frontend dedicado ainda** (testar via API/Postman/notebook com a PoC) | Se o objetivo imediato é só validar a ideia com uma pessoa  | Não dá pra "mostrar" um produto, mas é o caminho mais rápido para feedback |
| **React + TypeScript**                                                      | Se já quisermos algo demonstrável                           | Curva de aprendizado maior, mas ecossistema amplo                              |
| **Vue 3**                                                                   | Alternativa mais simples que React                            | Comunidade menor                                                               |
| Framework combinado (ex: Next.js)                                                 | Só faz sentido quando já houver clareza de produto e escala | Prematuro nesta fase                                                           |

---

## Opções de Backend (Para Debate)

| Opção                                                               | Quando faz sentido                                 | Trade-off                                                                                            |
| --------------------------------------------------------------------- | -------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| **Manter Python/FastAPI** (reaproveitando `app.py` existente) | Já há código e experiência da equipe em Python | Não é o mais performático, mas é o caminho de menor atrito                                       |
| **Node.js/Express**                                             | Se decidirem unificar linguagem com o frontend     | Perderia o pipeline de ML já pronto em Python (teria que portar ou manter serviço Python separado) |
| Outro                                                                 | —                                                 | Avaliar apenas se houver razão concreta                                                             |

**Observação**: como o pipeline de IA (embeddings, reranker) já está em Python, manter o backend em Python evita ter dois serviços em linguagens diferentes logo de início.

---

## Banco de Dados (Para Debate)

| Opção                                          | Observação                                                                                            |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| **SQLite** (para prototipagem local)       | Zero custo, zero setup — provavelmente suficiente para a fase de PoC                                   |
| **PostgreSQL**                             | Faz sentido quando o projeto sair da fase de protótipo e precisar de múltiplos usuários simultâneos |
| Vector store dedicado (Pinecone, Weaviate, etc.) | Prematuro agora —`pgvector` ou até busca em memória resolvem na fase de protótipo                 |

**Sugestão para discussão**: começar com SQLite (ou os arquivos/estrutura de dados que já existem no projeto v1) para não gastar tempo com infraestrutura antes de validar a ideia.

---

## Hospedagem / Infraestrutura

**Não decidir agora.** Rodar localmente (ou em ambiente de desenvolvimento simples) é suficiente para:

- Desenvolver o MVP
- Testar com a PoC
- Validar a proposta de valor

Decisões sobre nuvem (AWS, GCP, Azure, ou serviços gratuitos tipo Railway/Render free tier) devem ser tomadas **quando houver clareza de recursos financeiros**, na fase de incubação da startup — não antes.

---

## Autenticação, Email, Notificações

Estes itens (mencionados na reunião — alertas por email, validação de elegibilidade) só devem ser especificados tecnicamente depois que o escopo do MVP estiver fechado (ver [Próximos Passos — Definições](./Proximos-Passos-Definicoes.md)). Não há decisão de ferramenta ainda.

---

## Perguntas Abertas Para a Reunião de Arquitetura

1. Reaproveitamos o backend/pipeline atual ou começamos do zero no repositório novo?
2. O MVP precisa de interface visual ou testamos primeiro via API/scripts com a PoC?
3. Qual o volume de dados/usuários esperado na fase de validação (isso muda a escolha de banco)?
4. Quem na equipe tem mais familiaridade com qual stack (isso pesa tanto quanto "a melhor tecnologia")?
5. Quando (se) teremos clareza sobre orçamento para decidir hospedagem?
6. Coleta própria: scraping do compras.gov.br, API do PNCP, ou os dois? Reaproveitamos `scripts/collect_pncp.py` do projeto v1?

---

## Como Formalizar a Decisão

Depois que a equipe decidir em reunião, a decisão deve ser registrada como um change no OpenSpec (`openspec new change definir-stack-mvp`), não apenas ficar arquivada aqui. Isso mantém rastreabilidade de por que cada escolha foi feita.

---

*Este documento é um ponto de partida para discussão, não uma recomendação fechada.*
*Última atualização: 23/09/2026*

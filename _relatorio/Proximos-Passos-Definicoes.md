# Próximos Passos — Definições Pendentes

**Data**: 23 de setembro de 2026
**Status**: Rascunho para discussão em reunião
**Baseado em**: Reunião de 22/09/2026 (17:14 GMT-03:00)

---

## Objetivo Deste Documento

Este documento **não toma decisões**. Ele organiza as perguntas que a equipe precisa responder antes de começar a implementar qualquer coisa no repositório novo. Nada aqui é definitivo — é um checklist de definição a ser resolvido em reunião.

---

## O Que Já Foi Decidido (na reunião de 22/09)

- Foco do projeto em licitações da área de **saúde**
- Agregação de valor via resumos automatizados e alertas, com **coleta própria de editais** (sem depender da API de terceiros "Busca Editais" — ver nota abaixo)
- Estratégia de diferenciação por **confiabilidade auditável** + **nicho** (setorial/geográfico), em vez de competir em volume de funcionalidades
- Adoção do **OpenSpec** como framework de documentação (SDD)
- Criação de um novo repositório Git (`Projeto-Licitacao-2.0`) — feito

## O Que Ainda NÃO Foi Decidido

Isto precisa ser resolvido antes de qualquer linha de código:

### 1. Escopo do MVP

- [ ] Quais das ideias discutidas (busca, resumo, checklist, alertas, validador de elegibilidade) entram na primeira entrega?
- [ ] O que fica para depois?
- [ ] Existe uma entrega mínima que já pode ser testada com a conhecida da prefeitura (PoC mencionada na reunião)?

### 2. Arquitetura e Stack Técnico

- [ ] Frontend, backend, banco de dados — nada foi decidido ainda. Ver sugestões para debate em [`Sugestoes-Arquitetura-Stack.md`](./Sugestoes-Arquitetura-Stack.md).
- [ ] Reaproveitar componentes do projeto atual (`app.py`, pipeline de embeddings/reranker do André) ou reescrever do zero?
- [ ] Onde hospedar (se e quando hospedar)? Isso depende de recursos financeiros que **ainda não existem** — ver seção de recursos abaixo.
- [ ] Como será a coleta própria de editais (scraping/integração direta com compras.gov.br e/ou PNCP)? Decidido: **não usaremos a API de terceiros "Busca Editais"**, para não criar dependência externa — mas o desenho técnico dessa coleta própria ainda precisa ser definido.

### 3. Recursos e Orçamento

- [ ] O projeto está em fase de **pré-incubação/ideação**. Não há orçamento confirmado.
- [ ] Decisões de infraestrutura paga (cloud, serviços de email transacional, APIs de LLM pagas) devem esperar a fase de incubação, quando houver clareza sobre recursos disponíveis.
- [ ] Até lá, priorizar alternativas gratuitas/locais para prototipagem.

### 4. Prova de Conceito (PoC)

- [ ] Confirmar disponibilidade da conhecida de Danielle (atua em compras públicas na prefeitura)
- [ ] Definir o que exatamente será testado com ela (precisa do MVP definido primeiro)
- [ ] Definir prazo realista — depende de quando o MVP estiver pronto, não o contrário

### 5. Modelo de Negócio

- [ ] A reunião mencionou três eixos de diferenciação (confiabilidade auditável, modelo B2B via distribuidores, nicho geográfico/setorial) — nenhum foi aprofundado ainda
- [ ] Precisa de pesquisa de mercado antes de comprometer arquitetura a um modelo específico (ex: multi-tenant para distribuidores vs. single-tenant SaaS)

---

## Pesquisa Individual Antes de Cada Reunião (Equipe Remota)

Como a equipe é remota e participativa, nenhuma reunião de definição deve começar "do zero" — cada tema de pauta deve virar uma **task de pesquisa individual assíncrona** antes, para que todos cheguem com sugestões concretas em vez de opiniões improvisadas na hora.

**Formato sugerido de task de pesquisa** (uma por pessoa ou por dupla, conforme o tema):

```
Título: [PESQUISA] Tema — Nome de quem pesquisa
Prazo: até X dias antes da reunião
Entregável: 3-5 bullets no canal/issue com:
  - O que você encontrou/pensou
  - Prós e contras da sua sugestão
  - 1 pergunta em aberto que ficou
```

### Exemplo Aplicado à Reunião de Escopo do MVP

Antes de marcar a reunião de definição de escopo (item 1 da lista acima), criar tasks assíncronas do tipo:

| Task                                              | Quem pesquisa               | Pergunta a responder                                                                                                   |
| ------------------------------------------------- | --------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| [PESQUISA] MVP individual — sua proposta         | Cada membro da equipe       | Se você tivesse que escolher só 1-2 features para uma primeira entrega testável com a PoC, quais seriam e por quê? |
| [PESQUISA] Concorrência (Reclame Aqui)           | Danielle (já em andamento) | Quais reclamações mais comuns e o que isso sugere para o nosso MVP?                                                  |
| [PESQUISA] Viabilidade técnica do pipeline atual | Andre                       | O que do pipeline existente já resolve parte do MVP sem trabalho extra?                                               |
| [PESQUISA] Coleta própria de editais             | A definir                   | Formas de obter dados de compras.gov.br/PNCP sem depender de API de terceiros — viabilidade e esforço estimado       |

Cada pessoa chega na reunião com sua sugestão de MVP já pensada (mesmo que depois a equipe convirja para outra coisa) — a reunião serve para **comparar e decidir entre propostas já elaboradas**, não para gerar ideias do zero em tempo real.

Essa lógica se aplica a qualquer reunião de definição futura (arquitetura, modelo de negócio, etc.): antes de marcar, perguntar "que pesquisa individual prepara melhor essa conversa?"

---

## Ordem Sugerida de Resolução

Não dá para definir arquitetura sem saber o escopo do MVP, e não dá para estimar prazo/PoC sem saber a arquitetura. Sugestão de sequência para a próxima reunião:

```
1. Fechar escopo do MVP (o que testar com a PoC)
        ↓
2. Discutir arquitetura/stack (usar Sugestoes-Arquitetura-Stack.md como ponto de partida)
        ↓
3. Estimar esforço e prazo realista (com quem está disponível e quanto tempo por semana)
        ↓
4. Confirmar PoC (pessoa, data, o que validar)
        ↓
5. Criar as specs no OpenSpec para o que for aprovado
        ↓
6. Só então começar a implementar
```

---

## O Que Já Está Pronto Para Uso Imediato

Independente das decisões acima, já é possível:

- ✅ Usar o **OpenSpec** (`openspec/`) para documentar o que já existe no projeto (o pipeline de embeddings/reranker do André, a integração atual com compras.gov.br, etc.) — ver [Governança OpenSpec](./Governanca-OpenSpec.md)
- ✅ Registrar, como specs, as ideias discutidas na reunião — mesmo sem estarem aprovadas, ficam documentadas como "Proposta" para discussão
- ✅ Organizar as pendências acima como issues no GitHub, uma por tópico

---

## Ações Imediatas (Sem Depender de Reunião)

| Ação                                                                                                   | Responsável | Observação                                                   |
| -------------------------------------------------------------------------------------------------------- | ------------ | -------------------------------------------------------------- |
| Documentar arquitetura atual do projeto v1 (app.py, pipeline) em spec OpenSpec                           | Danielle     | Serve de base para decidir o que reaproveitar                  |
| Criar issues no GitHub para cada pendência listada acima                                                | A definir    | Facilita discussão assíncrona antes da reunião              |
| Criar tasks de pesquisa individual (ex: "MVP individual") antes de marcar a reunião de escopo           | A definir    | Ver seção "Pesquisa Individual Antes de Cada Reunião" acima |
| Danielle: sondar disponibilidade da PoC (sem compromisso de data ainda)                                  | Danielle     | Só confirma data depois do MVP definido                       |
| Agendar reunião de definição de escopo + arquitetura (só depois das pesquisas individuais entregues) | A definir    | Pauta: itens 1 e 2 deste documento                             |

---

## Notas

Este documento deve ser atualizado conforme as pendências forem resolvidas em reunião. Quando uma decisão for tomada, ela deve virar um change em `openspec/changes/` (via `openspec new change <nome>`), não apenas uma anotação aqui.

---

*Última atualização: 23/09/2026*

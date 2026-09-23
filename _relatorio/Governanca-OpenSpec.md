# Governança do Projeto — Uso do OpenSpec

**Data**: 23 de setembro de 2026
**Status**: Proposta de processo — para validação da equipe
**Aplica-se a**: `Projeto-Licitacao-2.0` a partir de agora
**Ferramenta**: [OpenSpec CLI](https://github.com/Fission-AI/OpenSpec) (`@fission-ai/openspec`) — instalado e inicializado neste repositório em `openspec/`

---

## Objetivo

Definir como o projeto será conduzido a partir de agora usando o **OpenSpec CLI** como framework de SDD (Spec-Driven Development), conforme decidido na reunião de 22/09/2026. Este documento é a regra de convivência do time em torno de documentação e mudanças — não trata de arquitetura ou escopo (ver os outros dois relatórios desta pasta).

---

## Regra Central

> **Toda feature nova, mudança significativa de comportamento, ou decisão de arquitetura vira um "change" no OpenSpec antes de virar código.**

Isso vale mesmo para mudanças pequenas quando alteram comportamento visível (endpoint, fluxo de usuário, modelo de dado). Não vale para: correções de bug óbvias, refatoração interna sem mudança de comportamento, ajustes de formatação/lint (para essas, `skip_specs: true` no metadado do change).

---

## Estrutura Real Criada Pelo CLI

```
openspec/
├── config.yaml           ← Configuração (schema: spec-driven, idioma: pt-BR)
├── specs/                 ← Especificações APROVADAS (fonte de verdade atual do sistema)
└── changes/
    ├── <nome-da-mudança>/    ← Mudança em andamento
    │   ├── .openspec.yaml    ← Metadados (schema, data de criação)
    │   ├── proposal.md       ← Por que a mudança, o que muda, quais capacidades afeta
    │   ├── design.md         ← Detalhes técnicos de como implementar
    │   ├── tasks.md          ← Lista de tarefas de implementação
    │   └── specs/             ← Deltas de spec (o que muda nas specs existentes/novas)
    └── archive/               ← Mudanças já concluídas e mescladas em specs/
```

Também foi criada integração com Claude Code em `.claude/skills/` e `.claude/commands/opsx/` — comandos de slash prontos para usar dentro do Claude Code.

---

## Fluxo de Trabalho (Comandos Reais)

```
1. Ideia/necessidade identificada
        ↓
   (opcional) /opsx:explore — discutir/esclarecer antes de formalizar
        ↓
2. /opsx:propose "sua ideia"
   (cria o change e gera proposal.md + deltas de spec em um passo só)
        ↓
3. Revisar/ajustar os artefatos gerados (proposal.md, design.md, tasks.md)
   → /opsx:update se precisar revisar depois de feedback
        ↓
4. Abrir PR só com a pasta do change (sem código) para revisão do time
        ↓
5. Discussão/ajustes no PR
        ↓
6. Aprovado → /opsx:apply
   (implementa o código seguindo tasks.md, em branch própria)
        ↓
7. PR de código é revisado contra os critérios definidos no change
        ↓
8. Merge → /opsx:sync (mescla deltas nas specs principais) → /opsx:archive
   (arquiva o change em openspec/changes/archive/)
```

*Todos os comandos acima são do Claude (`/opsx:*`). Quem preferir o terminal puro usa os equivalentes do CLI — ver tabela de referência abaixo.*

### Comandos do Dia a Dia — Via Claude (Forma Que a Equipe Vai Usar)

Na prática, a equipe não vai digitar os comandos do CLI diretamente — vai usar os comandos de slash dentro do Claude (Claude Code ou qualquer IDE com Claude integrado, ex: VSCode, Cursor). Esses comandos já chamam o CLI por trás e guiam o preenchimento dos artefatos:

| Comando (dentro do Claude) | Equivalente no fluxo | O que faz |
| --- | --- | --- |
| `/opsx:explore` | (antes de `new change`) | Modo de pensar/discutir a ideia antes de formalizar — não implementa nada, só ajuda a esclarecer requisitos. Útil para debater um problema antes de virar proposta |
| `/opsx:propose "sua ideia"` | `openspec new change` + preencher `proposal.md` | Cria o change e já gera `proposal.md` (e os deltas de spec, se aplicável) em um passo só. **É o comando principal para começar algo novo** |
| `/opsx:update` | editar `proposal.md`/`design.md`/`tasks.md` manualmente | Revisa artefatos de planejamento já existentes, mantendo tudo coerente. Nunca mexe em código |
| `/opsx:apply` | implementar seguindo `tasks.md` | Implementa as tarefas do change (a parte de código de fato, depois que a proposta foi aprovada) |
| `/opsx:sync` | mesclar deltas manualmente | Sincroniza os deltas de spec do change para as specs principais (`openspec/specs/`) de forma inteligente |
| `/opsx:archive` | `openspec archive <nome>` | Arquiva o change concluído e mescla as specs definitivamente |

**Funciona igual em outras IDEs com Claude**: esses comandos (`.claude/commands/opsx/`) não são exclusivos do terminal Claude Code — funcionam da mesma forma em qualquer editor com integração Claude (VSCode, JetBrains, etc.), já que o que muda é só onde o Claude roda, não o comando em si. Se alguém do time preferir outra ferramenta de IA (Cursor, por exemplo), o OpenSpec também tem integração própria — nesse caso, rodar `openspec init --tools cursor` (ou o tool correspondente) gera os comandos equivalentes para aquela ferramenta.

### Comandos do CLI (Referência Técnica)

Caso alguém prefira rodar direto no terminal, sem passar pelo Claude:

| Comando | O que faz |
| --- | --- |
| `openspec new change <nome>` | Cria uma nova proposta de mudança |
| `openspec status --change <nome>` | Mostra o progresso dos artefatos (proposal, specs, design, tasks) |
| `openspec instructions <artefato> --change <nome>` | Gera instruções guiadas para preencher cada artefato |
| `openspec validate --change <nome>` | Valida se a proposta está completa |
| `openspec list` | Lista mudanças em andamento |
| `openspec list --specs` | Lista as specs já aprovadas (inventário de capacidades do sistema) |
| `openspec show <nome>` | Mostra o conteúdo de uma mudança ou spec |
| `openspec archive <nome>` | Arquiva um change concluído e mescla as specs |
| `openspec view` | Dashboard interativo de specs e mudanças |

---

## Papéis (Provisório)

Como a equipe ainda é pequena e os papéis não foram formalmente atribuídos em reunião, esta seção é uma sugestão a confirmar:

| Responsabilidade                                      | Sugestão | Confirmar em reunião? |
| ----------------------------------------------------- | --------- | ---------------------- |
| Aprovar changes de produto/escopo                     | Danielle  | Sim                    |
| Aprovar changes técnicos/arquitetura                 | David     | Sim                    |
| Validar viabilidade de changes envolvendo IA/ML       | Andre     | Sim                    |
| Manter`openspec/config.yaml` e convenções do time | A definir | Sim                    |

---

## O Que Precisa Virar Change Já (Documentar o Existente)

Antes de qualquer feature nova, o mais importante agora é **documentar o que já existe** no projeto v1, para servir de base de decisão (reaproveitar ou não). Sugestão de primeiros changes:

- [ ] `/opsx:propose "documentar o estado atual do projeto v1"` — descrição do que já existe hoje: pipeline de embeddings/reranker, integração atual com compras.gov.br/PNCP (incluindo `scripts/collect_pncp.py`), estrutura do `app.py`, baseline de 50 editais. Pode usar `skip_specs: true` se for só documentação, sem propor mudança de comportamento.
- [ ] `/opsx:propose "registrar as ideias discutidas na reuniao de 22/09"` — registrar as ideias discutidas em 22/09 (resumo automático, checklist de habilitação, validador de elegibilidade, alertas) como propostas não aprovadas, para servirem de matéria-prima da próxima reunião de escopo

Esses dois changes não exigem decisão de arquitetura nem orçamento — são só documentação do que já existe e do que foi discutido.

---

## Convenções

### Nomenclatura de Changes

- kebab-case, verbo + objeto: `adicionar-autenticacao-jwt`, `documentar-estado-atual`
- Nomes de capacidades/specs seguem o inventário do projeto (`openspec list --specs`) — reaproveitar nome existente em vez de criar quase-duplicata

### Branches

```
feature/<nome-do-change>
```

### Commits e PRs

Todo commit relacionado a um change referencia a pasta:

```
feat: descrição curta

Change: openspec/changes/<nome-do-change>/
```

### Ciclo de Vida de um Change

```
Criado (/opsx:propose) → Em progresso (proposal/specs/design/tasks, ajustado via /opsx:update)
   → Revisado (PR) → Implementado (/opsx:apply) → Arquivado (/opsx:sync + /opsx:archive)
```

---

## O Que Este Processo Evita

- Código escrito sem alinhamento prévio sobre o que deveria fazer
- Decisões de arquitetura tomadas informalmente em conversa e esquecidas
- Retrabalho por falta de critérios de aceite claros
- Perda de contexto de "por que fizemos assim" quando alguém novo entra no time

## O Que Este Processo NÃO É

- Não é burocracia para travar decisões rápidas e óbvias
- Não substitui a reunião de definição de escopo/arquitetura — vem depois dela
- Não exige change para tudo (ver exceções na "Regra Central" acima — `skip_specs: true` cobre documentação pura)

---

## Próxima Ação

1. Validar este processo de governança com o time (concordam com o fluxo? Com os papéis sugeridos?)
2. Rodar `/opsx:propose "documentar o estado atual do projeto v1"` e `/opsx:propose "registrar as ideias discutidas na reuniao de 22/09"`
3. Só depois seguir para a reunião de definição de escopo e arquitetura (ver [Próximos Passos](./Proximos-Passos-Definicoes.md))

---

*Este documento deve ser revisado sempre que o processo mostrar atrito na prática.*
*Última atualização: 23/09/2026*

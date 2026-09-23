# Governança do Projeto — Uso do OpenSpec

**Data**: 23 de setembro de 2026
**Status**: Proposta de processo — para validação da equipe
**Aplica-se a**: `Projeto-Licitacao-2.0` a partir de agora
**Ferramenta**: [OpenSpec CLI](https://github.com/Fission-AI/OpenSpec) (`@fission-ai/openspec`) — instalado e inicializado neste repositório em `openspec/`

> **Nunca usou OpenSpec?** Comece por [`Guia-OpenSpec-Iniciantes.md`](./Guia-OpenSpec-Iniciantes.md) — tem instalação e primeiros comandos passo a passo. Este documento aqui é sobre o *processo* do time (regras, papéis, convenção de PR), não um tutorial de ferramenta.

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
   (implementa o código seguindo tasks.md, na branch feature/<nome>)
        ↓
7. /opsx:sync + /opsx:archive (ainda na mesma branch, antes do PR)
   → git push imediatamente após o archive, para não deixar só local
        ↓
8. Abrir PR de código (contém: código + specs/ atualizado + change arquivado)
        ↓
9. PR de código é revisado contra os critérios definidos no change
        ↓
10. Merge → main fica com tudo consistente de uma vez
```

*Todos os comandos acima são do Claude (`/opsx:*`). Quem preferir o terminal puro usa os equivalentes do CLI — ver tabela de referência abaixo.*

### Exemplo Completo — Do Zero até o Merge

Digamos que alguém do time quer propor um validador de elegibilidade. Assim ficaria na prática:

**1. Discussão informal (antes de qualquer artefato)**

No Slack ou numa call, a pessoa comenta a ideia. Se for algo que ainda precisa ser pensado (não só documentado), pode abrir o Claude e rodar:

```
/opsx:explore
"Estou pensando em um validador de elegibilidade — o usuário responde
3 perguntas e o sistema diz se vale a pena se candidatar ao edital.
Faz sentido? O que estou esquecendo?"
```

Isso só conversa/pensa junto — **não cria nenhum arquivo ainda**. Serve pra amadurecer a ideia antes de formalizar.

**2. Formalizar a proposta**

Quando a ideia já está clara, roda:

```
/opsx:propose "validador de elegibilidade: usuário responde 3 perguntas
(atua em saúde? está no estado do edital? pode fornecer o produto?) e
o sistema retorna se pode ou não se candidatar"
```

Isso cria a pasta `openspec/changes/adicionar-validador-elegibilidade/` com `proposal.md`, `design.md`, `tasks.md` e os deltas de spec — **tudo em markdown, zero código**.

**3. Abrir o PR de proposta**

```bash
git checkout -b proposta/validador-elegibilidade
git add openspec/changes/adicionar-validador-elegibilidade/
git commit -m "proposta: validador de elegibilidade"
git push origin proposta/validador-elegibilidade
```

Título do PR: **`[PROPOSTA] Validador de elegibilidade`**

Nesse PR, o time comenta só sobre a ideia: "as 3 perguntas são suficientes?", "e se a empresa atuar em mais de um estado?", "o critério de aceite cobre o caso X?". Ninguém está revisando código, porque não existe código ainda.

**4. Ajustes (se necessário)**

Se o time pedir mudanças na proposta, quem criou roda `/opsx:update` para ajustar `proposal.md`/`design.md`/`tasks.md` e atualiza o mesmo PR (não cria um novo).

**5. Aprovado → implementação**

Só depois do PR de proposta ser aprovado e mergeado (ou aprovado sem merge, dependendo do fluxo que o time escolher — ver convenção abaixo), alguém roda:

```
/opsx:apply --change adicionar-validador-elegibilidade
```

Isso implementa o código na branch `feature/validador-elegibilidade`, seguindo o `tasks.md` já aprovado.

**6. Sincronizar as specs — ainda dentro da mesma branch, antes de abrir o PR**

Importante: `/opsx:sync` e `/opsx:archive` rodam **antes** de abrir o PR de código, na mesma branch `feature/validador-elegibilidade` — não depois do merge, direto na `main`. Isso evita que a atualização final das specs fique sem revisão de ninguém.

```
/opsx:sync --change adicionar-validador-elegibilidade
/opsx:archive adicionar-validador-elegibilidade
```

Isso atualiza `openspec/specs/` com a spec definitiva e move a pasta do change para `openspec/changes/archive/`. Tudo isso entra no mesmo commit/branch do código.

**Assim que arquivar, já envie a branch para o GitHub** — não deixe o `archive` só local. Evita perder trabalho e deixa o PR pronto pra abrir na hora:

```bash
git add .
git commit -m "feat: validador de elegibilidade

Change: openspec/changes/archive/<data>-adicionar-validador-elegibilidade/"
git push origin feature/validador-elegibilidade
```

**7. Abrir o PR de código**

Título do PR: **`[CÓDIGO] Validador de elegibilidade`** (referenciando o PR/change de proposta)

Esse PR contém, de uma vez: o código novo, os testes, a spec final atualizada e o change arquivado. O time revisa código e a consistência da spec junto — não fica nenhum passo solto sem review.

**8. Merge final**

Depois do PR de código aprovado, o merge deixa `main` com tudo consistente de uma vez: código, specs atualizadas e histórico do change arquivado.

### Comandos do Dia a Dia — Via Claude (Forma Que a Equipe Vai Usar)

Na prática, a equipe não vai digitar os comandos do CLI diretamente — vai usar os comandos de slash dentro do Claude (Claude Code ou qualquer IDE com Claude integrado, ex: VSCode, Cursor). Esses comandos já chamam o CLI por trás e guiam o preenchimento dos artefatos:

| Comando (dentro do Claude)    | Equivalente no fluxo                                         | O que faz                                                                                                                                                              |
| ----------------------------- | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/opsx:explore`             | (antes de`new change`)                                     | Modo de pensar/discutir a ideia antes de formalizar — não implementa nada, só ajuda a esclarecer requisitos. Útil para debater um problema antes de virar proposta |
| `/opsx:propose "sua ideia"` | `openspec new change` + preencher `proposal.md`          | Cria o change e já gera`proposal.md` (e os deltas de spec, se aplicável) em um passo só. **É o comando principal para começar algo novo**                 |
| `/opsx:update`              | editar`proposal.md`/`design.md`/`tasks.md` manualmente | Revisa artefatos de planejamento já existentes, mantendo tudo coerente. Nunca mexe em código                                                                         |
| `/opsx:apply`               | implementar seguindo`tasks.md`                             | Implementa as tarefas do change (a parte de código de fato, depois que a proposta foi aprovada)                                                                       |
| `/opsx:sync`                | mesclar deltas manualmente                                   | Sincroniza os deltas de spec do change para as specs principais (`openspec/specs/`) de forma inteligente                                                             |
| `/opsx:archive`             | `openspec archive <nome>`                                  | Arquiva o change concluído e mescla as specs definitivamente                                                                                                          |

**Funciona igual em outras IDEs com Claude**: esses comandos (`.claude/commands/opsx/`) não são exclusivos do terminal Claude Code — funcionam da mesma forma em qualquer editor com integração Claude (VSCode, JetBrains, etc.), já que o que muda é só onde o Claude roda, não o comando em si. Se alguém do time preferir outra ferramenta de IA (Cursor, por exemplo), o OpenSpec também tem integração própria — nesse caso, rodar `openspec init --tools cursor` (ou o tool correspondente) gera os comandos equivalentes para aquela ferramenta.

### Comandos do CLI (Referência Técnica)

Caso alguém prefira rodar direto no terminal, sem passar pelo Claude:

| Comando                                              | O que faz                                                            |
| ---------------------------------------------------- | -------------------------------------------------------------------- |
| `openspec new change <nome>`                       | Cria uma nova proposta de mudança                                   |
| `openspec status --change <nome>`                  | Mostra o progresso dos artefatos (proposal, specs, design, tasks)    |
| `openspec instructions <artefato> --change <nome>` | Gera instruções guiadas para preencher cada artefato               |
| `openspec validate --change <nome>`                | Valida se a proposta está completa                                  |
| `openspec list`                                    | Lista mudanças em andamento                                         |
| `openspec list --specs`                            | Lista as specs já aprovadas (inventário de capacidades do sistema) |
| `openspec show <nome>`                             | Mostra o conteúdo de uma mudança ou spec                           |
| `openspec archive <nome>`                          | Arquiva um change concluído e mescla as specs                       |
| `openspec view`                                    | Dashboard interativo de specs e mudanças                            |

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

### Branches — Prefixo Diferencia Proposta de Código

Como cada change gera **dois PRs separados** (um só com os documentos da proposta, outro com o código), o prefixo da branch já identifica qual é qual:

| Tipo de PR | Prefixo da branch | Exemplo | Contém |
|---|---|---|---|
| Proposta (documentos) | `proposta/<nome-do-change>` | `proposta/validador-elegibilidade` | Só `openspec/changes/<nome>/` (markdown) |
| Código (implementação) | `feature/<nome-do-change>` | `feature/validador-elegibilidade` | Código (services/, tests/, etc.) **+** `openspec/specs/` atualizado (via `/opsx:sync`) **+** o change movido para `openspec/changes/archive/` (via `/opsx:archive`) |

**Só duas branches, não três**: a atualização final de `openspec/specs/` não vira uma branch/PR à parte — ela viaja dentro da branch `feature/` (rodando `/opsx:sync` + `/opsx:archive` *antes* de abrir o PR de código, não depois do merge). Assim a spec definitiva é revisada junto com o código, no mesmo PR, e nada é escrito direto na `main` sem passar por review.

### Título do PR

| Tipo de PR | Título | Exemplo |
|---|---|---|
| Proposta | `[PROPOSTA] <descrição curta>` | `[PROPOSTA] Validador de elegibilidade` |
| Código | `[CÓDIGO] <descrição curta>` | `[CÓDIGO] Validador de elegibilidade` |

Isso deixa visível na lista de PRs do GitHub, de relance, qual é discussão de ideia e qual é revisão de implementação — sem precisar abrir cada um para saber.

**Opcional, se o time quiser mais organização**: criar labels no GitHub (`proposta` e `código`) e aplicar em cada PR, além do prefixo no título. Facilita filtrar (`is:pr label:proposta is:open` mostra só propostas em aberto, por exemplo).

### Commits e PRs

Todo commit relacionado a um change referencia a pasta:

```
# No PR de proposta
proposta: descrição curta

Change: openspec/changes/<nome-do-change>/

# No PR de código
feat: descrição curta

Change: openspec/changes/<nome-do-change>/
Proposta: #<numero-do-pr-de-proposta>
Closes #<numero-da-issue>
```

O `Closes #<numero>` fecha automaticamente a Issue de rastreamento quando o PR é mergeado.

### Ciclo de Vida de um Change

```
Criado (/opsx:propose) → Em progresso (proposal/specs/design/tasks, ajustado via /opsx:update)
   → Revisado (PR) → Implementado (/opsx:apply) → Arquivado (/opsx:sync + /opsx:archive)
```

---

## Rastreamento no GitHub Issues

A pasta do change em `openspec/changes/<nome>/` continua sendo a **fonte de verdade** (conteúdo completo da proposta). A Issue no GitHub é só uma **vitrine de rastreamento** — não duplica o conteúdo, só linka e resume, para dar visibilidade de status sem precisar abrir o repositório toda vez.

### Quando criar a Issue

Junto com o PR de proposta (depois de rodar `/opsx:propose`). Uma Issue por change.

### Como criar

Use o template já configurado no repositório: **GitHub → Issues → New Issue → "Change (OpenSpec)"** (`.github/ISSUE_TEMPLATE/change.md`). Ele já vem com os campos certos: nome do change, link pro `proposal.md`, resumo e um checklist pra copiar do `tasks.md`.

### Labels — Espelham o Ciclo de Vida do Change

| Label | Quando aplicar |
|---|---|
| `proposta` | Change criado, PR de proposta aberto (label padrão do template) |
| `em-revisao` | Time discutindo a proposta no PR |
| `aprovada` | Proposta aceita, aguardando implementação |
| `em-desenvolvimento` | `/opsx:apply` em andamento |
| `implementada` | PR de código mergeado, change arquivado |

Quem move a Issue de label é quem está com a "posse" daquele change no momento (proponente move pra `em-revisao` ao abrir o PR; quem aprova move pra `aprovada`; quem implementa move pra `em-desenvolvimento`, depois `implementada` ao mergear).

### Checklist de Tarefas

Copie os itens de `tasks.md` para o corpo da Issue como checklist markdown (`- [ ]`). Isso permite acompanhar progresso de implementação direto na lista de Issues do GitHub, sem precisar abrir a branch. Se `tasks.md` mudar (via `/opsx:update`), atualize a checklist da Issue também — evita as duas fontes ficarem dessincronizadas.

### Quadro Kanban (GitHub Projects)

Existe um Project no repositório com colunas espelhando os labels acima, pra visão geral do time (útil sendo remoto — dá pra ver o status de tudo sem perguntar no chat). Arraste o card conforme o label muda, ou automatize a movimentação por label nas configurações do Project.

### Fechamento da Issue

A Issue é fechada automaticamente quando o **PR de código** é mergeado, se a descrição do PR contiver `Closes #<numero-da-issue>` (convenção padrão do GitHub).

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

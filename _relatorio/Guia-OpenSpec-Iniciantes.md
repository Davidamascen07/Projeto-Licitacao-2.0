# Guia OpenSpec para Quem Nunca Usou

**Objetivo**: te deixar pronto pra usar o OpenSpec neste projeto, do zero, mesmo que seja sua primeira vez ouvindo falar disso.

**Não precisa ler isso tudo de uma vez** — a Parte 1 já te deixa funcionando. As demais partes você consulta quando precisar.

---

## Parte 1 — Deixar Sua Máquina Pronta

### Passo 1: Verificar se você tem Node.js instalado

Abra o terminal e rode:

```bash
node --version
```

- Se aparecer algo como `v20.19.0` ou mais novo → você já tem, pule pro Passo 2.
- Se der erro ("comando não encontrado") → instale o Node.js em [nodejs.org](https://nodejs.org) (baixe a versão LTS) e rode o comando de novo pra confirmar.

### Passo 2: Clonar o repositório (se ainda não tiver)

```bash
git clone https://github.com/Davidamascen07/Projeto-Licitacao-2.0.git
cd Projeto-Licitacao-2.0
```

### Passo 3: Confirmar que o OpenSpec já está configurado

O projeto **já tem o OpenSpec inicializado** — você não precisa rodar `init` de novo. Só confirme que a pasta existe:

```bash
ls openspec/
```

Deve aparecer:

```
config.yaml
specs/
changes/
```

Se aparecer isso, está tudo pronto. **Pule direto pra Parte 2.**

> Se você não tiver o pacote instalado ainda e quiser rodar comandos do CLI direto no terminal (não pelo Claude), não precisa instalar nada de forma permanente — o `npx` baixa e roda na hora:
> ```bash
> npx @fission-ai/openspec@latest --version
> ```
> Isso funciona sem instalação prévia. Só demora um pouco mais na primeira vez.

---

## Parte 2 — Como Usar no Dia a Dia (Recomendado: Via Claude)

Você **não precisa decorar comandos de terminal**. O jeito mais simples é usar os comandos de slash dentro do Claude (Claude Code, ou qualquer editor com Claude integrado — VSCode, Cursor, etc.).

### O comando que você mais vai usar: `/opsx:propose`

Toda vez que você tiver uma ideia de feature ou mudança, abra o Claude dentro do projeto e digite:

```
/opsx:propose "descreva sua ideia aqui em linguagem natural"
```

**Exemplo real**:

```
/opsx:propose "quero adicionar um endpoint que retorna o status de
processamento de um edital, para o frontend poder mostrar uma barra
de progresso"
```

O Claude vai:
1. Criar uma pasta em `openspec/changes/<nome-da-mudanca>/`
2. Escrever um `proposal.md` explicando o porquê
3. Gerar os arquivos de spec necessários

**Você não precisa escrever nada manualmente** — o Claude preenche tudo, você só revisa e ajusta se algo estiver errado.

### Se você ainda não tem certeza da ideia

Antes de propor formalmente, você pode só conversar:

```
/opsx:explore
"Tenho uma ideia meio vaga de X, o que vocês acham? Faz sentido?"
```

Isso não cria nenhum arquivo — é só uma conversa para amadurecer o pensamento.

### Depois que a proposta for aprovada pelo time

Quem for implementar roda:

```
/opsx:apply
```

O Claude implementa o código seguindo o plano (`tasks.md`) que já foi aprovado.

### Quando terminar a implementação

```
/opsx:sync
/opsx:archive
```

Isso atualiza a documentação oficial do projeto (`openspec/specs/`) e arquiva a mudança como concluída.

**Fluxo completo, resumido**:

```
/opsx:explore  (opcional, se ainda tiver dúvida)
      ↓
/opsx:propose "sua ideia"
      ↓
(revisão do time no PR)
      ↓
/opsx:apply
      ↓
/opsx:sync  →  /opsx:archive
      ↓
git push + abrir PR de código
```

Para o passo a passo completo com exemplo de PR, nomes de branch e revisão do time, veja [`Governanca-OpenSpec.md`](./Governanca-OpenSpec.md).

---

## Parte 3 — Comandos Direto no Terminal (Se Preferir)

Se você não quiser passar pelo Claude e preferir digitar comandos você mesmo:

| O que você quer fazer | Comando |
|---|---|
| Criar uma nova proposta | `npx @fission-ai/openspec@latest new change <nome-em-kebab-case>` |
| Ver o progresso de uma mudança | `npx @fission-ai/openspec@latest status --change <nome>` |
| Ver instruções de como preencher um artefato | `npx @fission-ai/openspec@latest instructions proposal --change <nome>` |
| Checar se a proposta está completa | `npx @fission-ai/openspec@latest validate --change <nome>` |
| Ver todas as mudanças em andamento | `npx @fission-ai/openspec@latest list` |
| Ver as specs já aprovadas (o que o sistema já faz hoje) | `npx @fission-ai/openspec@latest list --specs` |
| Ver o conteúdo de uma mudança ou spec | `npx @fission-ai/openspec@latest show <nome>` |
| Arquivar uma mudança concluída | `npx @fission-ai/openspec@latest archive <nome>` |
| Abrir um painel visual (dashboard) | `npx @fission-ai/openspec@latest view` |

**Dica**: depois de rodar `npx @fission-ai/openspec@latest` a primeira vez, ele fica em cache e os próximos comandos rodam mais rápido.

**Nomes de mudanças**: use kebab-case (tudo minúsculo, separado por hífen), descrevendo a ação. Exemplos: `adicionar-endpoint-status-edital`, `corrigir-timeout-busca`.

---

## Parte 4 — Perguntas Comuns

### "Preciso instalar o OpenSpec globalmente na minha máquina?"

Não. O `npx` já baixa e roda a versão certa automaticamente. Só o Node.js precisa estar instalado.

### "E se eu esquecer os comandos?"

Peça ajuda pro Claude: digite `/opsx:` no chat e vai aparecer a lista de comandos disponíveis com descrição. Ou rode `npx @fission-ai/openspec@latest --help` no terminal.

### "Posso usar em outra IDE além de VSCode?"

Sim. Se você usa Cursor, JetBrains, ou outra ferramenta com IA integrada, os comandos `/opsx:*` funcionam igual — o que muda é só onde o Claude roda, não o comando em si.

### "O que acontece se eu esquecer de rodar `/opsx:propose` antes de codificar?"

Nada quebra tecnicamente, mas você perde o registro de "por que" essa mudança foi feita — e pula a etapa de revisão do time antes de escrever código. A ideia é habituar o time a sempre propor antes de implementar (ver regra central em [`Governanca-OpenSpec.md`](./Governanca-OpenSpec.md)).

### "Onde ficam as specs que já existem no sistema hoje?"

Em `openspec/specs/`. Rode `npx @fission-ai/openspec@latest list --specs` para ver o inventário, ou peça pro Claude: "quais capacidades já existem no projeto?"

### "Tenho um erro estranho, o que fazer?"

Rode `npx @fission-ai/openspec@latest doctor` — ele diagnostica problemas comuns de configuração e sugere correções.

---

## Parte 5 — Onde Aprender Mais

- **Documentação oficial**: [github.com/Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec)
- **Como o time usa neste projeto** (regras, papéis, convenção de PR): [`Governanca-OpenSpec.md`](./Governanca-OpenSpec.md)
- **O que ainda está em definição** (não use OpenSpec pra travar decisão que ainda não foi tomada em reunião): [`Proximos-Passos-Definicoes.md`](./Proximos-Passos-Definicoes.md)

---

*Dúvidas que não estão aqui? Pergunte no canal do time — e se for uma pergunta que outras pessoas provavelmente também terão, peça pra alguém adicionar a resposta neste guia.*

*Última atualização: 23/09/2026*

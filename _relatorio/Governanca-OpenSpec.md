# Governança do Projeto — Uso do OpenSpec

**Data**: 23 de setembro de 2026
**Status**: Proposta de processo — para validação da equipe
**Aplica-se a**: `Projeto-Licitacao-2.0` a partir de agora

---

## Objetivo

Definir como o projeto será conduzido a partir de agora usando **OpenSpec** como framework de SDD (Spec-Driven Development), conforme decidido na reunião de 22/09/2026. Este documento é a regra de convivência do time em torno de documentação e mudanças — não trata de arquitetura ou escopo (ver os outros dois relatórios desta pasta).

---

## Regra Central

> **Toda feature nova, mudança significativa de comportamento, ou decisão de arquitetura passa por uma spec no OpenSpec antes de virar código.**

Isso vale mesmo para mudanças pequenas quando alteram comportamento visível (endpoint, fluxo de usuário, modelo de dado). Não vale para: correções de bug óbvias, refatoração interna sem mudança de comportamento, ajustes de formatação/lint.

---

## Fluxo de Trabalho

```
1. Ideia/necessidade identificada
        ↓
2. Criar spec em .openspec/specs/ (a partir do TEMPLATE-spec.md)
   Status inicial: "Proposta"
        ↓
3. Abrir PR só com a spec (sem código) para revisão do time
        ↓
4. Discussão/ajustes no PR
        ↓
5. Spec aprovada → status muda para "Aprovada"
   → Cria-se issue no GitHub referenciando a spec
        ↓
6. Implementação em branch própria, referenciando a issue/spec
        ↓
7. PR de código é revisado contra os critérios de aceite da spec
        ↓
8. Merge → spec muda para "Implementada"
```

---

## Papéis (Provisório)

Como a equipe ainda é pequena e os papéis não foram formalmente atribuídos em reunião, esta seção é uma sugestão a confirmar:

| Responsabilidade | Sugestão | Confirmar em reunião? |
|---|---|---|
| Aprovar specs de produto/escopo | Danielle | Sim |
| Aprovar specs técnicas/arquitetura | DAVID | Sim |
| Validar viabilidade de specs envolvendo IA/ML | Andre | Sim |
| Manter o `.openspec/` organizado (templates, numeração) | A definir | Sim |

---

## O Que Precisa Virar Spec Já (Documentar o Existente)

Antes de qualquer feature nova, o mais importante agora é **documentar o que já existe** no projeto v1, para servir de base de decisão (reaproveitar ou não). Sugestão de specs iniciais, todas com status "Proposta" até revisão:

- [ ] `ARCH-000-estado-atual.md` (em `architecture/`): descrição do que já existe hoje — pipeline de embeddings/reranker, integração atual com compras.gov.br/PNCP (incluindo `scripts/collect_pncp.py`), estrutura do `app.py`, baseline de 50 editais
- [ ] `FEATURE-000-ideias-da-reuniao.md` (em `specs/`): registrar as ideias discutidas em 22/09 (resumo automático, checklist de habilitação, validador de elegibilidade, alertas) como propostas não aprovadas, para servirem de matéria-prima da próxima reunião de escopo

Essas duas specs não exigem decisão de arquitetura nem orçamento — são só documentação do que já existe e do que foi discutido.

---

## Convenções

### Nomenclatura

- Specs de feature: `FEATURE-XXX-slug-descritivo.md`
- Decisões de arquitetura: `ARCH-XXX-slug-descritivo.md`
- Numeração sequencial, sem pular números, sem reaproveitar números de specs descartadas

### Branches

```
feature/FEATURE-XXX-slug-descritivo
```

### Commits e PRs

Todo commit relacionado a uma spec referencia o número:

```
feat: [FEATURE-XXX] descrição curta

Spec: .openspec/specs/FEATURE-XXX-slug.md
```

### Status de uma Spec

```
Proposta → Em Revisão → Aprovada → Em Desenvolvimento → Implementada
```

Uma spec pode ser **rejeitada** ou **arquivada** em qualquer etapa — isso também deve ficar registrado (não apagar o arquivo, mudar o status e explicar o motivo).

---

## O Que Este Processo Evita

- Código escrito sem alinhamento prévio sobre o que deveria fazer
- Decisões de arquitetura tomadas informalmente em conversa e esquecidas
- Retrabalho por falta de critérios de aceite claros
- Perda de contexto de "por que fizemos assim" quando alguém novo entra no time

## O Que Este Processo NÃO É

- Não é burocracia para travar decisões rápidas e óbvias
- Não substitui a reunião de definição de escopo/arquitetura — vem depois dela
- Não exige spec para tudo (ver exceções na "Regra Central" acima)

---

## Próxima Ação

1. Validar este processo de governança com o time (concordam com o fluxo? Com os papéis sugeridos?)
2. Criar as duas specs de documentação do existente (`ARCH-000` e `FEATURE-000`)
3. Só depois seguir para a reunião de definição de escopo e arquitetura (ver [Próximos Passos](./Proximos-Passos-Definicoes.md))

---

*Este documento deve ser revisado sempre que o processo mostrar atrito na prática.*
*Última atualização: 23/09/2026*

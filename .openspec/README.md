# 📐 OpenSpec SDD Framework

**Projeto-Licitação 2.0** usa o framework **OpenSpec** para documentação de especificações de software e decisões arquiteturais.

---

## 🎯 O que é OpenSpec?

OpenSpec é um framework estruturado para documentar **requisitos, fluxos de usuário, especificações técnicas e critérios de aceite** de forma padronizada e rastreável.

**Objetivos**:
- ✅ **Clareza**: Toda feature tem uma especificação única e aprovada
- ✅ **Rastreabilidade**: Cada feature é vinculada a issue + PR + commit
- ✅ **Qualidade**: Critérios de aceite = menos bugs + mais testes
- ✅ **Documentação viva**: Specs atualizadas conforme projeto evolui

---

## 📂 Estrutura

```
.openspec/
├── openspec.yaml          # Configuração central
├── README.md              # Este arquivo
├── specs/                 # Especificações de features
│   ├── TEMPLATE-spec.md   # Template para novas specs
│   ├── FEATURE-001-auth.md
│   ├── FEATURE-002-search-editals.md
│   ├── FEATURE-003-summarize.md
│   └── ...
└── architecture/          # Decisões arquiteturais
    ├── ARCH-001-frontend-stack.md
    ├── ARCH-002-backend-stack.md
    └── ...
```

---

## 🚀 Como Criar uma Spec

### Passo 1: Clonar o Template

```bash
cp specs/TEMPLATE-spec.md specs/FEATURE-XXX-nome-descritivo.md
```

Substitua `XXX` pelo próximo número sequencial.

### Passo 2: Preencher Seções Obrigatórias

| Seção | Obrigatório | Descrição |
|-------|------------|-----------|
| **Resumo Executivo** | ✅ | 1 frase resumindo problema + solução |
| **Descrição** | ✅ | Problema, solução e benefícios |
| **Requisitos Funcionais (RF)** | ✅ | O que o sistema deve fazer |
| **Requisitos Não-Funcionais (RNF)** | ✅ | Performance, escalabilidade, etc |
| **Fluxos de Usuário** | ✅ | Passo-a-passo de como usuário usa |
| **Endpoints API / UI Mockups** | ✅ | Especificação técnica detalhada |
| **Critérios de Aceite** | ✅ | Como validar que está pronto |
| **Estimativa** | ✅ | Esforço em T-shirt (XS, S, M, L, XL) |
| **Dependências** | ✅ | Outras features que bloqueiam |
| **Riscos** | ✅ | Possíveis problemas + mitigation |

### Passo 3: Submeter para Revisão

```bash
git checkout -b feature/FEATURE-XXX-slug-descritivo
git add .openspec/specs/FEATURE-XXX-nome.md
git commit -m "docs: [FEATURE-XXX] Adicionar especificação"
git push origin feature/FEATURE-XXX-slug-descritivo
```

Abra um **Pull Request** com o título:
```
docs: [FEATURE-XXX] Descrição da feature

Veja .openspec/specs/FEATURE-XXX-nome.md para detalhes completos.
```

### Passo 4: Código & Implementação

Após aprovação da spec (status = "Aprovada"):

1. Crie uma **issue GitHub** referenciando a spec:
   ```
   Título: [FEATURE-XXX] Nome
   Descrição: https://github.com/.../blob/dev/.openspec/specs/FEATURE-XXX.md
   ```

2. Crie branch de implementação:
   ```bash
   git checkout -b feature/FEATURE-XXX-implementacao
   ```

3. No commit, referencie a issue:
   ```bash
   git commit -m "feat: [FEATURE-XXX] Implementar função X
   
   Relacionado: #123 (issue)
   Spec: .openspec/specs/FEATURE-XXX-nome.md
   "
   ```

4. No PR (Pull Request):
   ```
   Título: feat: [FEATURE-XXX] Descrição concisa
   
   ## Descrição
   Implementa [FEATURE-XXX] conforme spec em `.openspec/specs/FEATURE-XXX-nome.md`
   
   ## Validação
   - Passa todos os critérios de aceite (veja spec)
   - Testes: 80%+ de cobertura
   - Code review aprovado
   
   Closes #123
   ```

---

## 📋 Checklist: Spec Pronta para Dev

Antes de mudar status para "Aprovada", garantir:

- [ ] **Resumo executivo** é claro (1 frase)?
- [ ] **Todos os RFs estão listados** (tabelados)?
- [ ] **Requisitos não-funcionais cobrem**: performance, escalabilidade, segurança?
- [ ] **Fluxos de usuário são passo-a-passo** (não genéricos)?
- [ ] **Endpoints API estão completos**: request + response + erros?
- [ ] **Database schema definido** (SQL ou diagrama)?
- [ ] **Critérios de aceite são testáveis** (não vagos)?
- [ ] **Dependências estão claras** (bloqueantes ou paralelo)?
- [ ] **Riscos e mitigações identificados**?
- [ ] **Estimativa é realista** (consultar dev)?
- [ ] **Link para issue no GitHub**?

---

## 🔄 Status de Uma Spec

```
Proposta
   ↓
Em Revisão (code review, feedback)
   ↓
Aprovada (pode começar dev)
   ↓
Em Desenvolvimento
   ↓
Implementada (code merged)
   ↓
Deployed (em produção)
```

---

## 📊 Exemplo: Spec Preenchida

Veja [TEMPLATE-spec.md](./specs/TEMPLATE-spec.md) para um exemplo completo com todas as seções.

**Highlights:**
- ✅ Requisitos bem estruturados (RF, RNF, RSE, RUS)
- ✅ Fluxos de usuário descritivos
- ✅ API completa (request/response/erros)
- ✅ Critérios de aceite testáveis
- ✅ Estimativa realista

---

## 🎯 Integração com GitHub

### Issue Template

Toda issue deve referenciar a spec:

```markdown
## Descrição
[FEATURE-XXX]: [Breve descrição]

Veja especificação em: `.openspec/specs/FEATURE-XXX-nome.md`

## Critérios de Aceite
- [ ] CA-1: ...
- [ ] CA-2: ...
- [ ] CA-3: ...

(Copiar de `.openspec/specs/FEATURE-XXX-nome.md`)
```

### Branch Naming

```
feature/FEATURE-001-autenticacao-jwt
feature/FEATURE-002-busca-editais
feature/FEATURE-003-resumo-automatico
```

### Commit Messages

```bash
git commit -m "feat: [FEATURE-001] Implementar login JWT

Spec: .openspec/specs/FEATURE-001-autenticacao-jwt.md
Related: #123
"
```

---

## 🔒 Versionamento de Specs

Quando uma spec muda **durante desenvolvimento**:

1. **Atualize o arquivo** (`.openspec/specs/FEATURE-XXX.md`)
2. **Documente a mudança** (seção "Histórico")
3. **Notifique a equipe** (comentário no PR)

Exemplo de histórico:

```markdown
## 💬 Comentários & Histórico

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-09-23 | Danielle | Spec inicial |
| 2026-09-25 | Andre | Removido RNF-2 (não crítico para MVP) |
| 2026-10-01 | DAVID | Adicionado RSE-3 (rate limiting) |
```

---

## 🚀 Próximas Specs (Roadmap)

Com base no MVP (veja `_relatorio/MVP-Definition.md`), as próximas specs a criar:

- [ ] **FEATURE-001**: Autenticação JWT
- [ ] **FEATURE-002**: Busca de Editais
- [ ] **FEATURE-003**: Resumo + Checklist
- [ ] **FEATURE-004**: Validador de Elegibilidade
- [ ] **ARCH-001**: Decisão Frontend Stack
- [ ] **ARCH-002**: Decisão Backend Stack

---

## 📞 Perguntas Frequentes

### P: Posso simplificar a spec?
**R**: Não. Cada seção serve um propósito. Mesmo que pareça óbvio, documentar evita ambiguidades.

### P: E se a feature for muito simples?
**R**: Use XS ou S de esforço. Mas mesmo features simples precisam de critérios de aceite claros.

### P: Posso pular a seção de Riscos?
**R**: Não. Riscos ajudam a priorizar e planejar mitigações. Até features "fáceis" têm riscos.

### P: E se a spec mudar durante dev?
**R**: Atualize o arquivo + documente no histórico. Comunique mudanças significativas ao time.

### P: Quem aprova a spec?
**R**: Tech Lead (DAVID) + Product Manager (Danielle). Deve ter consenso.

---

## 📚 Referências

- **OpenSpec Site**: https://openspec.dev (se existir)
- **Exemplo real**: Veja `specs/TEMPLATE-spec.md`
- **RFC 2119**: https://tools.ietf.org/html/rfc2119 (keywords: MUST, SHOULD, etc)

---

## 🛠️ Ferramentas Úteis

Para editar specs no IDE:

**VSCode Extensions**:
- Markdown All in One
- markdownlint
- Markdown Preview Enhanced

**Validar sintaxe**:
```bash
# Verificar se YAML é válido
python -c "import yaml; yaml.safe_load(open('.openspec/openspec.yaml'))"
```

---

## 📝 Manutenção

**OpenSpec é mantido por**: DAVID DAMASCENO  
**Última atualização**: 2026-09-23  
**Próxima revisão**: Quando primeira spec for aprovada

---

*Framework OpenSpec — Documentação viva para qualidade e rastreabilidade.*

# RIPD — Relatório de Impacto à Proteção de Dados Pessoais

**Organização:** JSTechStore Brasil  
**Responsável:** Encarregado de Dados (DPO)  
**Versão:** 1.0  
**Data de elaboração:** 2026-07-22  
**Base legal principal:** Lei Geral de Proteção de Dados Pessoais — LGPD (Lei nº 13.709/2018)

---

## 1. Identificação do Tratamento

| Campo | Descrição |
|-------|-----------|
| **Nome do tratamento** | Plataforma de Engenharia de Dados JSTechStore — Análise de Negócio |
| **Finalidade** | Análise de desempenho comercial, logístico, financeiro e de marketing para tomada de decisão gerencial |
| **Controlador** | JSTechStore Brasil Ltda. |
| **Operador de dados** | Equipe interna de Engenharia de Dados; Supabase Inc. (base PostgreSQL em nuvem) |
| **DPO** | A designar conforme Art. 41 LGPD |

---

## 2. Categorias de Dados Tratados

> **Nota importante sobre dados desta plataforma:**  
> Os dados desta plataforma são **100% sintéticos** (gerados por `scripts/generate_data.py` usando a biblioteca Faker pt_BR). Não há dados pessoais reais de titulares humanos identificáveis. Esta seção descreve o tratamento *como se* fosse um ambiente de produção real, para fins de conformidade e preparação do RIPD de produção.

### 2.1 Dados de Clientes

| Dado | Categoria LGPD | Finalidade |
|------|---------------|-----------|
| CPF (pseudonimizado como `cpf_hash`) | Pessoal — identificador direto | Deduplicação omnichannel, unicidade do cliente |
| Nome completo | Pessoal | Identificação em relatórios CRM |
| E-mail | Pessoal — contato | Comunicação de marketing, confirmação de pedidos |
| Telefone | Pessoal — contato | Atendimento ao cliente |
| Endereço (CEP, cidade, UF) | Pessoal — localização | Logística de entrega, segmentação regional |
| Data de nascimento | Pessoal | Segmentação etária, validação de maioridade |
| Histórico de compras | Pessoal — comportamental | LTV, segmentação RFM, análise de coorte |
| Pontos fidelidade | Pessoal — financeiro | Programa TechPoints |

### 2.2 Dados de Colaboradores (RH)

| Dado | Categoria LGPD | Finalidade |
|------|---------------|-----------|
| Nome do vendedor | Pessoal | Relatórios de performance, comissões |
| Metas e comissões | Pessoal — financeiro | Dashboard Comercial — performance por vendedor |
| Loja e turno | Pessoal — profissional | Alocação de resultados por unidade |

### 2.3 Dados que NÃO são tratados nesta plataforma

- Dados sensíveis (Art. 5, II LGPD): origem racial/étnica, convicção religiosa, saúde, biometria
- Dados de crianças e adolescentes (Art. 14 LGPD)
- Dados de localização em tempo real

---

## 3. Base Legal

| Tratamento | Base Legal LGPD | Artigo |
|-----------|----------------|--------|
| Histórico de compras para análise de negócio | Legítimo interesse do controlador | Art. 7, IX |
| CPF para unicidade e controle de fraudes | Cumprimento de obrigação legal (NF-e, Nota Fiscal) | Art. 7, II |
| E-mail para marketing | Consentimento (opt-in no cadastro) | Art. 7, I |
| Dados de colaboradores | Execução de contrato de trabalho | Art. 7, V |
| Pseudonimização para análise de dados | Legítimo interesse + medida de segurança | Art. 7, IX + Art. 46 |

---

## 4. Fluxo de Dados (Data Flow)

```
[Titular / Cliente]
        │ compra em loja física ou e-commerce
        ▼
[Supabase PostgreSQL — Cloud]
  • Schema: clientes, vendas, financeiro, logistica, rh, marketing
  • Dados pessoais: nome, e-mail, cpf, telefone, endereço
        │
        │ Ingestão incremental (Python + psycopg2)
        │ Pseudonimização: CPF → SHA-256 HMAC antes de gravar
        ▼
[Bronze — Parquet Local]
  • SEM dados pessoais diretos (CPF, e-mail, telefone em texto claro)
  • CPF substituído por cpf_hash (HMAC-SHA256)
  • Nome, e-mail, telefone: não replicados no Bronze
        │
        │ dbt transformations
        ▼
[Silver + Gold — DuckDB Local]
  • Dados analíticos: cpf_hash, comportamento de compra, métricas
  • SEM PII direta identificável
        │
        │ Power BI ODBC (leitura)
        ▼
[Power BI Service — Dashboards]
  • Relatórios agregados (sem linha-a-linha de clientes)
  • Acesso restrito por workspace e permissão de visualização
```

### 4.1 Retenção de dados

| Camada | Retenção | Justificativa |
|--------|----------|---------------|
| Supabase (fonte) | Indeterminado (sistema OLTP ativo) | Operação do negócio |
| Bronze (Parquet) | 3 anos de histórico + janela incremental | Análise de tendências |
| Gold (DuckDB) | 3 anos | Conformidade com prazo de prescrição fiscal (Art. 195 CTN) |
| Power BI | Espelho do Gold; refresh diário | Consumo gerencial |

---

## 5. Medidas de Segurança Implementadas

### 5.1 Pseudonimização

- **Técnica:** HMAC-SHA256 aplicado ao CPF antes de gravar no Bronze
- **Implementação:** `quality/lgpd/pseudonimizacao.py`
- **Chave:** `LGPD_HMAC_SALT` — armazenada apenas em variável de ambiente; nunca em código ou repositório
- **Reversibilidade:** Irreversível sem a chave secreta — garante pseudonimização técnica (Art. 5, XI LGPD)

### 5.2 Controle de Acesso

| Sistema | Controle |
|---------|----------|
| Supabase | Autenticação PostgreSQL por usuário; conexão via SSL |
| Bronze/Silver/Gold (local) | Acesso restrito ao sistema de arquivos da máquina de dados |
| Power BI Service | Workspace com permissões explícitas; MFA na conta organizacional |
| GitHub | Repositório privado; secrets do GitHub Actions para credenciais |

### 5.3 Dados em Trânsito e em Repouso

| Item | Medida |
|------|--------|
| Supabase → máquina local | TLS 1.3 (conexão PostgreSQL via SSL) |
| Arquivos Bronze/Gold (local) | Disco do servidor de dados; sem criptografia em repouso nesta fase |
| `.env` com credenciais | Nunca commitado; protegido por `.gitignore` |
| GitHub Actions secrets | Armazenados como encrypted secrets no repositório |

### 5.4 Direito de Exclusão (Art. 18, VI LGPD)

- **Implementação:** `quality/lgpd/exclusao_titular.py`
- **Modo dry-run:** identifica e lista todos os registros do titular sem excluir
- **Modo execute:** exclui/anonimiza registros em Supabase, Bronze e Gold referentes ao `cpf_hash`
- **Prazo de resposta:** ≤ 15 dias úteis após solicitação (Art. 18 § 3 LGPD)
- **Registro:** cada exclusão deve ser registrada em log de auditoria (a implementar)

---

## 6. Análise de Riscos

| Risco | Probabilidade | Impacto | Medida de mitigação |
|-------|--------------|---------|---------------------|
| Vazamento de credenciais Supabase | Média | Alto | Rotação periódica; nunca commitar `.env`; uso de GitHub Secrets |
| Exposição do `LGPD_HMAC_SALT` | Baixa | Alto | Variável de ambiente apenas; rotação anual planejada |
| Acesso indevido ao Gold DuckDB | Baixa | Médio | Controle de acesso ao filesystem; sem exposição em rede |
| Re-identificação via `cpf_hash` | Muito Baixa | Alto | Salt secreto torna força bruta inviável |
| Backup não criptografado | Média | Médio | Política de backup documentada em `docs/arquitetura/estrategia_backup_gold.md` |
| Solicitação de exclusão não atendida | Baixa | Alto | Script automatizado + processo definido + prazo 15 dias |

---

## 7. Direitos dos Titulares

Conforme Art. 18 LGPD, os titulares têm direito a:

| Direito | Como exercer | Responsável |
|---------|-------------|------------|
| Confirmação de tratamento | Contato com DPO | DPO |
| Acesso aos dados | Relatório de dados por `cpf_hash` via script | Equipe de Dados |
| Correção de dados inexatos | Atualização em Supabase + re-run do pipeline | Equipe de Dados |
| Eliminação de dados | `quality/lgpd/exclusao_titular.py --execute` | Equipe de Dados |
| Portabilidade | Exportação CSV dos dados do titular | A implementar |
| Revogação de consentimento (marketing) | Opt-out no sistema CRM | CRM / Marketing |
| Oposição ao tratamento | Avaliação pelo DPO | DPO |

---

## 8. Compartilhamento com Terceiros

| Terceiro | Dados compartilhados | Finalidade | Garantias |
|---------|---------------------|-----------|-----------|
| Supabase Inc. (EUA) | Todos os dados da fonte | Hospedagem do banco OLTP | Data Processing Agreement (DPA) disponível; adequação GDPR via SCCs |
| Microsoft (Power BI Service) | Dados agregados Gold (sem PII direta) | Visualização gerencial | DPA Microsoft; ISO 27001; adequação LGPD |
| GitHub Inc. | Código-fonte; secrets criptografados | CI/CD e versionamento | DPA GitHub; sem dados pessoais no repositório |

**Transferência internacional:** Supabase está em `us-east-1` (AWS). A transferência ocorre com base no Art. 33, II LGPD (adequação às normas de proteção de dados aplicáveis) e no DPA disponibilizado pela Supabase.

---

## 9. Revisões e Aprovações

| Versão | Data | Responsável | Alteração |
|--------|------|------------|-----------|
| 1.0 | 2026-07-22 | Equipe de Dados | Elaboração inicial |

**Próxima revisão:** 2027-01-22 (semestral) ou quando houver mudança significativa no fluxo de dados.

---

## 10. Contatos

| Papel | Contato |
|-------|---------|
| Encarregado de Dados (DPO) | A designar — Art. 41 LGPD |
| Responsável técnico | Equipe de Engenharia de Dados |
| Canal de atendimento LGPD | privacidade@jstechstore.com.br (a criar) |

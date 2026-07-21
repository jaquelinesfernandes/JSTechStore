# Contas e Acessos — JSTechStore Brasil Data Engineering

**Atualizado em:** 2026-07-21

Este documento lista **todas as plataformas** que o projeto usa, o que precisa ser
configurado em cada uma, e onde cada credencial é consumida.

---

## Resumo Rápido — O que preciso antes de começar?

| Plataforma | Obrigatório para | Status |
|------------|-----------------|--------|
| **Supabase** | Banco de dados fonte (OLTP) | Criar conta + projeto |
| **GitHub** | Repositório + CI/CD (Actions) | Já existente |
| **GitHub Secrets** | Pipeline diário sem expor credenciais | Configurar 1 secret |
| **Python 3.12+** | Scripts de geração + ingestão + qualidade | Instalar localmente |
| **dbt Core** | Transformações Silver/Gold | Instalar via pip |
| **DuckDB** | Camada Gold + consultas | Instalar via pip |
| **Power BI Pro/PPU** | Dashboards executivos | Licença necessária |
| **DuckDB ODBC Driver** | Conexão Power BI ↔ DuckDB local | Instalar no Windows |
| **On-premises Data Gateway** | Refresh automático no Power BI Service | Instalar no Windows |

---

## 1. Supabase (PostgreSQL Cloud)

**O que é:** Banco de dados fonte que simula o OLTP da JSTechStore.  
**Plano:** Free tier (500 MB de banco — suficiente para os dados sintéticos).

### Criar conta e projeto

1. Acesse [supabase.com](https://supabase.com) → **Start your project** → cadastro gratuito
2. Criar novo projeto:
   - Nome: `jstechstore`
   - Senha do banco: gerar uma senha forte (anotar no gerenciador de senhas)
   - Região: `South America (São Paulo)` — menor latência para o Brasil
3. Aguardar provisionamento (~2 min)

### Obter a connection string

```
Supabase Dashboard → Project → Settings → Database → Connection string → URI
```

Formato:
```
postgresql://postgres:<SUA_SENHA>@<PROJECT_REF>.supabase.co:5432/postgres
```

### Configurar schemas e índices

```bash
# Após criar o projeto, rodar o script de setup (cria schemas, tabelas e índices em updated_at)
python scripts/setup_supabase.py   # a ser criado na Fase 1
```

### Onde esta credencial é usada

| Onde | Variável |
|------|----------|
| `.env` local | `SUPABASE_DB_URL` |
| GitHub Actions Secret | `SUPABASE_DB_URL` |
| `ingestion/connectors/postgres/extract.py` | `os.environ["SUPABASE_DB_URL"]` |
| `quality/reconciliation/reconcile_gold_vs_source.py` | `os.environ["SUPABASE_DB_URL"]` |

---

## 2. GitHub — Repository Secrets

**O que é:** Variáveis secretas injetadas nos workflows do GitHub Actions sem expor valores nos logs.

### Acessar configuração

```
GitHub → Repositório JSTechStore → Settings → Secrets and variables → Actions → New repository secret
```

### Secret a configurar

| Secret | Valor | Usado em |
|--------|-------|----------|
| `SUPABASE_DB_URL` | Connection string do Supabase (seção 1) | `daily_pipeline.yml` steps 1, 2, 6 |

### Configurar via GitHub CLI (após autenticar)

```powershell
# Setar SUPABASE_DB_URL
gh secret set SUPABASE_DB_URL --body "postgresql://postgres:SENHA@xxxx.supabase.co:5432/postgres"

# Verificar secrets configurados
gh secret list
```

---

## 4. Ambiente Local Python

### Instalar Python 3.12

Download: [python.org/downloads](https://python.org/downloads)  
Verificar: `python --version` → deve retornar `Python 3.12.x`

### Criar ambiente virtual e instalar dependências

```bash
# Na raiz do projeto
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

# Instalar dependências
pip install -r requirements.txt
```

> `requirements.txt` será criado na Fase 1 com: `psycopg2-binary`, `sqlalchemy`,
> `pandas`, `pyarrow`, `dbt-duckdb`, `duckdb`, `faker`, `python-dotenv`, `ruff`, `pytest`

### Carregar variáveis do .env

```bash
# Copiar template e preencher
cp .env.example .env
# Editar .env com os valores reais (Supabase URL + LGPD salt)
```

---

## 5. Power BI

### Licença necessária

| Licença | Limite de dataset | Refreshes/dia | Adequação |
|---------|------------------|---------------|-----------|
| **Pro** | 1 GB | 8× | OK até Ano 2 |
| **Premium Per User (PPU)** | 100 GB | 48× | Recomendado a partir do Ano 3 |

Adquirir em: **Microsoft 365 Admin Center** ou **powerbi.microsoft.com**

### Conta de serviço (recomendado)

Criar uma conta organizacional dedicada (ex: `dados@jstechstore.com.br`) para:
- Publicar datasets e relatórios
- Registrar o On-premises Data Gateway
- Configurar scheduled refresh

Usar conta pessoal funciona, mas cria dependência de pessoa física.

---

## 6. DuckDB ODBC Driver (Windows local)

**Para que:** Permite que o Power BI Desktop leia o arquivo `jstechstore.duckdb` via ODBC.

### Instalar

1. Download em: [duckdb.org/docs/api/odbc/windows](https://duckdb.org/docs/api/odbc/windows)
2. Escolher versão **64-bit** compatível com a versão do dbt-duckdb em `requirements.txt`
3. Executar o instalador `.msi` como administrador

### Criar System DSN

```powershell
# Executar como administrador
Add-OdbcDsn `
    -Name "JSTechStoreGold" `
    -DriverName "DuckDB Driver" `
    -DsnType "System" `
    -SetPropertyValue @(
        "Database=C:\caminho\absoluto\data\gold\jstechstore.duckdb",
        "access_mode=READ_ONLY"
    )
```

Guia completo: `docs/arquitetura/powerbi_gateway_setup.md`

---

## 7. On-premises Data Gateway

**Para que:** Permite que o Power BI Service (nuvem) acesse o DuckDB local para scheduled refresh.

### Instalar

1. Power BI Service → Configurações → Gerenciar gateways → **Baixar gateway**
2. Executar `GatewayInstall.exe` → selecionar **On-premises data gateway** (padrão)
3. Login com a conta Power BI da equipe
4. Nome do gateway: `JSTechStore-GW`
5. **Salvar a Recovery Key** no gerenciador de senhas

### Verificar que está rodando

```powershell
Get-Service -Name "PBIEgwService" | Select-Object Name, Status, StartType
# Status: Running | StartType: Automatic
```

---

## 8. Checklist de Setup Inicial

Execute na ordem para garantir que tudo está funcional antes da Fase 1:

```
[ ] 1. Criar conta Supabase + projeto "jstechstore" (região São Paulo)
[ ] 2. Copiar connection string do Supabase
[ ] 3. Copiar .env.example → .env e preencher SUPABASE_DB_URL
[ ] 4. Instalar Python 3.12 e criar ambiente virtual (.venv)
[ ] 5. pip install -r requirements.txt
[ ] 6. Configurar GitHub Secret: SUPABASE_DB_URL
[ ] 7. Instalar DuckDB ODBC Driver 64-bit e criar System DSN "JSTechStoreGold"
[ ] 8. Instalar On-premises Data Gateway e registrar como "JSTechStore-GW"
[ ] 9. Verificar Power BI Pro/PPU disponível na conta de serviço
```

---

## 9. Tabela Consolidada de Credenciais

| Credencial | Sensível | Onde fica | Nunca colocar em |
|-----------|----------|-----------|-----------------|
| `SUPABASE_DB_URL` | Sim (contém senha) | `.env` + GitHub Secret | Código, PR, Slack, `.env.example` |
| `DUCKDB_PATH` | Não | `.env` (opcional) | — |
| `BRONZE_PATH` | Não | `.env` (opcional) | — |
| `SILVER_PATH` | Não | `.env` (opcional) | — |
| `GOLD_BACKUP_DIR` | Não | `.env` (opcional) | — |
| DSN `JSTechStoreGold` | Não | Windows ODBC (System DSN) | — |
| Gateway Recovery Key | Sim | Gerenciador de senhas | — |
| Senha Supabase (DB) | Sim | Gerenciador de senhas | — |

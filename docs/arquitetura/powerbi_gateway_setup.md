# Power BI + DuckDB Local — Conexão via On-premises Data Gateway

**Versão:** 1.0  
**Data:** 2026-07-21

---

## 1. Visão Geral da Arquitetura

```
┌─────────────────────────────────┐
│  Máquina Local (Windows)        │
│                                 │
│  data/gold/jstechstore.duckdb   │
│         ↕  ODBC                 │
│  DuckDB ODBC Driver             │
│         ↕  DSN "JSTechStoreGold"│
│  On-premises Data Gateway       │
│         ↕  HTTPS (443)          │
└──────────────┬──────────────────┘
               │ internet
┌──────────────▼──────────────────┐
│  Power BI Service (nuvem)       │
│  Dataset → Scheduled Refresh    │
│  6 Dashboards Executivos        │
└─────────────────────────────────┘
```

**Premissas:**
- A máquina local com o DuckDB deve ficar **ligada e com internet** durante o horário de refresh
- O Gateway deve rodar como serviço Windows (não como app de usuário)
- Refresh agendado: 1×/dia após o pipeline GitHub Actions concluir (~05:00 BRT)

---

## 2. Pré-requisitos

| Item | Versão mínima | Observação |
|------|--------------|-----------|
| Windows | 10 / Server 2016 | 64-bit obrigatório |
| .NET | 4.8 | Já incluído no Windows 10+ |
| DuckDB ODBC Driver | ≥ 1.1.0 | Arquivo `.msi` no site oficial |
| On-premises Data Gateway | Atualizar mensalmente | Auto-update disponível |
| Power BI Desktop | Atualização de setembro/2025 ou posterior | Para conexão ODBC 64-bit |
| Conta Power BI | Pro ou PPU | Necessária para publicar no Service |

---

## 3. Passo 1 — Instalar o DuckDB ODBC Driver

### 3.1 Download

Baixar o instalador MSI em:
```
https://duckdb.org/docs/api/odbc/windows
```
Escolher a versão **64-bit** correspondente à versão do DuckDB usada no projeto
(verificar em `requirements.txt`).

### 3.2 Instalação

```powershell
# Executar o instalador (requer privilégios de administrador)
.\duckdb_odbc_setup_amd64.msi

# Verificar registro do driver após instalação
Get-OdbcDriver -Name "DuckDB Driver*"
# Deve retornar: Name = "DuckDB Driver", Platform = 64-bit
```

### 3.3 Criar o DSN (Data Source Name)

```powershell
# Criar DSN de sistema (visível para todos os usuários e para o Gateway)
Add-OdbcDsn `
    -Name "JSTechStoreGold" `
    -DriverName "DuckDB Driver" `
    -DsnType "System" `
    -SetPropertyValue @(
        "Database=C:\caminho\absoluto\para\data\gold\jstechstore.duckdb",
        "access_mode=READ_ONLY"
    )

# Verificar DSN criado
Get-OdbcDsn -Name "JSTechStoreGold" -DsnType System
```

> **Importante:** Use o caminho **absoluto** do arquivo `.duckdb`. O Gateway roda como
> serviço e não tem acesso a caminhos relativos ou mapeamentos de drive de usuário.

### 3.4 Testar a conexão ODBC

```powershell
# Teste rápido via PowerShell
$conn = New-Object System.Data.Odbc.OdbcConnection("DSN=JSTechStoreGold")
$conn.Open()
$cmd = $conn.CreateCommand()
$cmd.CommandText = "SELECT COUNT(*) FROM fato_venda"
Write-Host "fato_venda rows: $($cmd.ExecuteScalar())"
$conn.Close()
```

---

## 4. Passo 2 — Instalar o On-premises Data Gateway

### 4.1 Download e instalação

1. Acessar: **Power BI Service** → Configurações (⚙️) → Gerenciar gateways → Baixar gateway
2. Executar o instalador `GatewayInstall.exe`
3. Selecionar **On-premises data gateway** (modo padrão — não o personal)
4. Fazer login com a conta Power BI (organizacional)
5. Registrar o gateway: escolher nome descritivo (ex: `JSTechStore-GW`)
6. Anotar a **Recovery Key** gerada — necessária para restaurar o gateway em outra máquina

### 4.2 Configurar o gateway como serviço Windows automático

```powershell
# Verificar que o serviço está rodando
Get-Service -Name "PBIEgwService"
# Status deve ser: Running
# StartType deve ser: Automatic

# Se não estiver automático:
Set-Service -Name "PBIEgwService" -StartupType Automatic
```

### 4.3 Verificar status no Power BI Service

- Acessar: Power BI Service → Configurações → Gerenciar gateways
- O gateway deve aparecer com status **Online** (ícone verde)

---

## 5. Passo 3 — Adicionar fonte de dados ODBC ao Gateway

No Power BI Service:

1. Configurações → Gerenciar gateways → selecionar `JSTechStore-GW`
2. Clicar em **Adicionar fonte de dados**
3. Configurar:
   - **Nome da fonte:** `JSTechStoreGold_ODBC`
   - **Tipo:** ODBC
   - **String de conexão:** `DSN=JSTechStoreGold`
   - **Método de autenticação:** Windows (conta do serviço do Gateway)
4. Clicar em **Adicionar** → Status deve mostrar **Conexão bem-sucedida**

---

## 6. Passo 4 — Criar conexão no Power BI Desktop

### 6.1 Conexão ODBC

1. Abrir Power BI Desktop
2. **Obter Dados** → pesquisar **ODBC** → Conectar
3. Selecionar DSN `JSTechStoreGold`
4. Autenticação: **Windows** ou **Padrão** (sem credenciais, pois é READ_ONLY)
5. No navegador, selecionar as tabelas Gold:
   - Todas as `dim_*`
   - Todas as `fato_*`

### 6.2 Configurar parâmetros de Incremental Refresh (fato_venda)

Na Power Query, antes de publicar, criar os parâmetros M:

```m
// Parâmetro RangeStart
#"RangeStart" = #datetime(2024, 1, 1, 0, 0, 0) meta [IsParameterQuery=true, Type="DateTime", IsParameterQueryRequired=true]

// Parâmetro RangeEnd
#"RangeEnd" = #datetime(2026, 12, 31, 23, 59, 59) meta [IsParameterQuery=true, Type="DateTime", IsParameterQueryRequired=true]
```

Na query de `fato_venda`, adicionar filtro:

```m
// Filtro por RangeStart e RangeEnd (Incremental Refresh)
#"Filtro por data" = Table.SelectRows(
    fato_venda_source,
    each [data_pedido] >= RangeStart and [data_pedido] < RangeEnd
)
```

### 6.3 Configurar Incremental Refresh no Power BI Desktop

1. Clicar com botão direito em `fato_venda` → **Atualização incremental**
2. Ativar a opção
3. Configurar:
   - Arquivar linhas com mais de: **2 anos**
   - Atualizar linhas dos últimos: **3 dias**
4. Aplicar

---

## 7. Passo 5 — Publicar e configurar refresh no Power BI Service

### 7.1 Publicar o dataset

1. Power BI Desktop → **Publicar** → selecionar workspace
2. Aguardar publicação concluir

### 7.2 Associar o gateway ao dataset

1. Power BI Service → Dataset → **Configurações**
2. **Conexão do gateway:** selecionar `JSTechStore-GW`
3. Mapear a fonte de dados:
   - Fonte: `JSTechStoreGold_ODBC` (criada no Passo 3)
4. Salvar

### 7.3 Configurar refresh agendado

1. Dataset → Configurações → **Atualização agendada**
2. Ativar: **Sim**
3. Frequência: **Diária**
4. Horário: **05:30 BRT** (depois do pipeline GitHub Actions completar ~05:00)
5. Fuso horário: **(UTC-03:00) Brasília**
6. Endereço de e-mail para notificação de falha: email da equipe
7. Salvar

---

## 8. Verificação pós-configuração

```powershell
# Verificar que o arquivo DuckDB existe e está acessível
Test-Path "C:\caminho\para\data\gold\jstechstore.duckdb"

# Verificar que o Gateway está online
Get-Service -Name "PBIEgwService" | Select-Object Status, StartType

# Verificar que o DSN está registrado como System DSN
Get-OdbcDsn -Name "JSTechStoreGold" -DsnType System
```

No Power BI Service, após o primeiro refresh bem-sucedido:

- Dataset → Histórico de atualizações → Status: **Êxito**
- Dashboards devem mostrar dados de D-1

---

## 9. Troubleshooting

| Sintoma | Causa provável | Solução |
|---------|---------------|---------|
| Gateway aparece offline | Máquina desligada ou sem internet | Manter máquina ligada 24/7 ou usar horário de refresh compatível |
| Erro "DSN not found" no gateway | DSN criado como User DSN, não System | Recriar como System DSN via `Add-OdbcDsn -DsnType System` |
| Erro "Architecture mismatch" | Driver ODBC 32-bit com Power BI 64-bit | Reinstalar driver 64-bit |
| Refresh demora >30min | DuckDB sendo consultado enquanto pipeline grava | Agendar refresh 1h após pipeline |
| Incremental Refresh não funciona | Parâmetros RangeStart/RangeEnd ausentes ou com tipo errado | Garantir tipo `DateTime` (não Date) nos parâmetros M |
| `fato_venda` retorna dados errados após rollback | Cache do Incremental Refresh desatualizado | Power BI Service → Dataset → Atualização completa (1×) |

---

## 10. Limitações e Considerações

| Limitação | Impacto | Mitigação |
|-----------|---------|-----------|
| Máquina deve ficar ligada | Indisponibilidade se desligar | Gateway rodando como serviço Windows automático + configurar BIOS para wake-on-LAN |
| Gateway atrelado à conta PBI | Se conta expirar, refresh para | Usar conta de serviço organizacional (não pessoal) |
| DuckDB aberto no Desktop bloqueia escrita pelo dbt | Pipeline pode falhar | Fechar Power BI Desktop antes do horário do pipeline |
| Dataset limite 1 GB (Power BI Pro) | Gold deve manter ≤ 900 MB | Incremental Refresh em fato_venda + agregar Gold anualmente |
| Gateway não suporta DuckDB nativo | Requer driver ODBC intermediário | Driver oficial DuckDB ODBC — atualizar junto com versão do DuckDB |

---

## 11. Alternativa sem Gateway — Exportação Parquet

Se a manutenção do Gateway for inviável (ex: máquina nem sempre disponível), uma
alternativa é exportar o Gold como arquivos Parquet e ler no Power BI Desktop sem
conexão ao vivo:

```bash
# Exportar Gold como Parquet (roda no final do pipeline)
python scripts/export_gold_parquet.py

# Power BI Desktop lê os .parquet diretamente (sem gateway)
# Limitação: refresh manual no Desktop + republish no Service
```

Esta alternativa elimina o Gateway mas exige republicação manual do `.pbix` após cada
exportação, perdendo o refresh automático agendado.

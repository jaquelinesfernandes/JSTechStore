# Estratégia de Backup — Camada Gold (DuckDB)

**Versão:** 1.0  
**Data:** 2026-07-21  
**Responsável:** Engenharia de Dados

---

## 1. Contexto e Problema

A camada Gold (`data/gold/jstechstore.duckdb`, ~700 MB) é o ponto de consumo de todos os 6 dashboards Power BI. Por ser um arquivo binário local, qualquer perda de disco exigiria regeneração completa do DW — processo que pode levar horas e depende do Supabase estar acessível.

**Riscos identificados sem backup:**

| Risco | Impacto | Probabilidade |
|-------|---------|--------------|
| Perda de disco local | Perda total do Gold; rebuild de horas | Baixa |
| Arquivo `.duckdb` corrompido por falha de I/O | Inacessibilidade imediata dos dashboards | Baixa |
| `dbt run --full-refresh` acidental em produção | Reprocessamento desnecessário de 3 anos | Média |
| Rollback necessário após modelo Gold com bug | Sem backup = sem rollback | Média |

---

## 2. Objetivos

| Métrica | Meta |
|---------|------|
| **RPO** (Recovery Point Objective) | ≤ 24 horas — no máximo 1 dia de dados perdido |
| **RTO** (Recovery Time Objective) | ≤ 30 minutos — restauração do último backup funcional |
| Retenção local | 7 dias corridos |
| Retenção no GitHub Artifacts | 30 dias corridos |

---

## 3. Arquitetura de Backup em Três Camadas

```
┌──────────────────────────────────────────────────────────────────┐
│  CAMADA 1 — Backup diário comprimido (local)                     │
│  data/backups/gold/jstechstore_YYYYMMDD_HHMMSS.duckdb.gz        │
│  Retenção: 7 dias · Rotação automática pelo script               │
└──────────────────────────────┬───────────────────────────────────┘
                               │ upload automático via Actions
┌──────────────────────────────▼───────────────────────────────────┐
│  CAMADA 2 — GitHub Actions Artifact                              │
│  Artifact: gold-backup-<run_id>                                  │
│  Retenção: 30 dias · Acessível pelo GitHub UI / CLI              │
└──────────────────────────────┬───────────────────────────────────┘
                               │ fallback último recurso
┌──────────────────────────────▼───────────────────────────────────┐
│  CAMADA 3 — Reconstrução pelo Bronze + dbt                       │
│  Bronze Parquet (data/bronze/) + dbt run --full-refresh          │
│  Garante recuperação mesmo sem backup do .duckdb                 │
└──────────────────────────────────────────────────────────────────┘
```

### Por que três camadas?

- **Camada 1** cobre falhas acidentais do dia a dia (arquivo corrompido, rollback de modelo) com restauração em segundos.
- **Camada 2** cobre perda total de disco local — o arquivo existe no GitHub por até 30 dias, acessível de qualquer máquina.
- **Camada 3** garante recuperabilidade total mesmo que backups 1 e 2 falhem: o Bronze Parquet pode sempre reconstruir o Gold via `dbt run --full-refresh`.

---

## 4. Script de Backup

**Localização:** `scripts/backup_gold.py`

### Comportamento padrão (execução diária pelo GitHub Actions)

```bash
python scripts/backup_gold.py --keep-days 7
```

1. Lê `DUCKDB_PATH` (padrão: `data/gold/jstechstore.duckdb`)
2. Comprime com gzip nível 6 → `data/backups/gold/jstechstore_YYYYMMDD_HHMMSS.duckdb.gz`
3. Aplica rotação: exclui backups além dos últimos 7
4. Grava entrada de auditoria em `data/backups/gold/backup_log.jsonl`
5. Imprime `BACKUP_FILE=<caminho>` para o GitHub Actions capturar

### Parâmetros disponíveis

| Parâmetro | Padrão | Descrição |
|-----------|--------|-----------|
| `--duckdb-path` | `$DUCKDB_PATH` | Caminho do arquivo Gold |
| `--backup-dir` | `$GOLD_BACKUP_DIR` | Diretório de destino dos backups |
| `--keep-days` | `7` | Quantidade de backups locais a manter |
| `--export-parquet` | — | Exporta tabelas como Parquet portável (via `EXPORT DATABASE`) |
| `--dry-run` | — | Simula execução sem gravar nada |

### Teste em dry-run

```bash
python scripts/backup_gold.py --dry-run
```

### Exportação Parquet portável (fallback manual)

```bash
python scripts/backup_gold.py --export-parquet
# Cria: data/backups/gold/parquet_YYYYMMDD_HHMMSS/ com arquivos .parquet por tabela
```

Útil quando o arquivo `.duckdb.gz` está corrompido: os Parquets permitem reconstruir
o DuckDB com `dbt run --full-refresh` apontando para os arquivos exportados.

---

## 5. Integração com GitHub Actions

O backup é o **Step 5** do workflow `daily_pipeline.yml`, executado **após** `dbt test --select gold` ser aprovado. Isso garante que apenas versões validadas são arquivadas.

```
Cron 04:00 UTC
  │
  ├── Step 1: generate_daily.py
  ├── Step 2: ingestão Bronze (psycopg2)
  ├── Step 3: dbt run (incremental)
  ├── Step 4: dbt test --select gold  ← gate de qualidade
  └── Step 5: backup_gold.py + upload artifact  ← só roda se Step 4 passar
```

O artifact gerado fica disponível em:

```
GitHub → Repositório → Actions → [run] → Artifacts → gold-backup-<run_id>
```

---

## 6. Log de Auditoria

Cada execução grava uma linha JSON em `data/backups/gold/backup_log.jsonl`:

```json
{
  "timestamp": "2026-07-21T04:12:33+00:00",
  "source_path": "data/gold/jstechstore.duckdb",
  "backup_file": "data/backups/gold/jstechstore_20260721_041233.duckdb.gz",
  "source_size_bytes": 734003200,
  "backup_size_bytes": 198451200,
  "compression_ratio": 0.270,
  "keep_days": 7,
  "rotated_files": ["jstechstore_20260714_040812.duckdb.gz"],
  "export_parquet": false,
  "duration_seconds": 18.4,
  "dry_run": false
}
```

Para inspecionar o histórico:

```bash
# Últimos 5 backups
tail -5 data/backups/gold/backup_log.jsonl | python -m json.tool

# Listar backups locais disponíveis
ls -lh data/backups/gold/*.duckdb.gz
```

---

## 7. Procedimento de Restauração

### Cenário A — Restaurar do backup local (mais rápido, RTO ~1 min)

```bash
# 1. Listar backups disponíveis (mais recente primeiro)
ls -lt data/backups/gold/*.duckdb.gz | head -5

# 2. Parar qualquer processo usando o DuckDB
# (garantir que nenhuma conexão dbt/Python está ativa)

# 3. Mover o arquivo corrompido para quarentena
mv data/gold/jstechstore.duckdb data/gold/jstechstore.duckdb.corrupted

# 4. Descompactar o backup escolhido
gunzip -c data/backups/gold/jstechstore_YYYYMMDD_HHMMSS.duckdb.gz \
    > data/gold/jstechstore.duckdb

# 5. Validar integridade
python -c "
import duckdb
con = duckdb.connect('data/gold/jstechstore.duckdb', read_only=True)
count = con.execute('SELECT COUNT(*) FROM fato_venda').fetchone()[0]
print(f'fato_venda: {count:,} linhas — OK')
con.close()
"

# 6. Executar dbt run incremental para atualizar até D-1
cd transformation/dbt_project && dbt run
```

---

### Cenário B — Restaurar do GitHub Actions Artifact (disco perdido, RTO ~15 min)

```bash
# 1. Instalar GitHub CLI se necessário
# https://cli.github.com/

# 2. Autenticar
gh auth login

# 3. Listar artifacts disponíveis (mais recentes primeiro)
gh run list --workflow=daily_pipeline.yml --limit 10

# 4. Baixar o artifact do run mais recente com sucesso
gh run download <RUN_ID> --name gold-backup-<RUN_ID> --dir /tmp/gold_restore/

# 5. Descompactar
gunzip -c /tmp/gold_restore/jstechstore_*.duckdb.gz \
    > data/gold/jstechstore.duckdb

# 6. Validar e atualizar (igual ao Cenário A, steps 5 e 6)
```

---

### Cenário C — Reconstrução completa pelo Bronze (último recurso, RTO ~2–4 horas)

Usar quando backups locais e artifacts estão indisponíveis.

```bash
# Pré-requisito: Bronze Parquet em data/bronze/ intacto
# O Supabase pode ser usado para ingestão full se o Bronze também foi perdido

# 1. Apagar DuckDB corrompido
rm -f data/gold/jstechstore.duckdb

# 2. Reconstruir Gold a partir do Bronze Parquet (3 anos de histórico)
cd transformation/dbt_project
dbt run --full-refresh      # processa Silver + Gold do zero

# 3. Validar
dbt test --select gold

# Tempo estimado: 2–4 horas dependendo do hardware
```

---

## 8. Retenção e Armazenamento

| Camada | Local | Retenção | Tamanho estimado por arquivo |
|--------|-------|----------|------------------------------|
| Local | `data/backups/gold/*.duckdb.gz` | 7 dias | ~180–220 MB |
| GitHub Artifact | GitHub Actions Artifacts | 30 dias | ~180–220 MB |
| Bronze Parquet | `data/bronze/` | 3 anos (política Bronze) | — |

**Consumo total estimado (camada local):**
- 7 arquivos × ~200 MB = ~1,4 GB em `data/backups/`

---

## 9. Variáveis de Ambiente

Adicionar ao `.env.example`:

```bash
# Backup Gold
GOLD_BACKUP_DIR=data/backups/gold
```

O `DUCKDB_PATH` já existe no `.env.example`.

---

## 10. O que NÃO é Backup

- **Os arquivos Bronze Parquet** (`data/bronze/`) servem como fonte de reconstituição (Cenário C), não como backup do Gold em si. Restaurar o Gold a partir deles requer `dbt run --full-refresh`.
- **O arquivo `.duckdb` em produção** não deve ser versionado no Git (está no `.gitignore`) — apenas os `.duckdb.gz` de backup ficam em `data/backups/gold/`.
- **Watermarks** (`data/bronze/.watermarks/*.json`) devem ser commitados no Git após cada execução bem-sucedida, pois controlam a ingestão incremental.

---

## 11. Checklist de Verificação Mensal

- [ ] Executar `python scripts/backup_gold.py --dry-run` e confirmar que o caminho está correto
- [ ] Verificar que o GitHub Actions está uploading o artifact em cada run diário (Actions → Artifacts)
- [ ] Confirmar que `backup_log.jsonl` está sendo gravado com entradas recentes
- [ ] Testar o Cenário A de restauração em ambiente de desenvolvimento (copiar DuckDB atual, restaurar backup do dia anterior, validar com `dbt test`)
- [ ] Verificar que `data/backups/gold/` não está excedendo o espaço disponível em disco

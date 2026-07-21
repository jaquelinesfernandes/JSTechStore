"""
Extrator incremental Supabase → Bronze Parquet.

Estratégia de atomicidade do watermark:
  1. Extrai dados WHERE updated_at > watermark
  2. Aplica pseudonimização LGPD nos campos PII
  3. Grava em arquivo temporário (.tmp_<uuid>.parquet) dentro da partição de destino
  4. Renomeia temp → arquivo final (operação atômica no mesmo filesystem)
  5. Atualiza o watermark SOMENTE após rename bem-sucedido

Se o processo falhar nos steps 1–4, o watermark não é atualizado e a próxima
execução reprocessa o mesmo intervalo (idempotência garantida pelo dbt unique_key).

Uso:
    python -m ingestion.connectors.postgres.extract --mode full
    python -m ingestion.connectors.postgres.extract --mode incremental
    python -m ingestion.connectors.postgres.extract --mode incremental --table vendas.pedidos
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor

from ingestion.connectors.postgres.config import TABLES, TABLES_BY_NAME, TableConfig
from quality.lgpd.pseudonimizacao import pseudonimizar_dataframe

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

BRONZE_PATH = Path(os.getenv("BRONZE_PATH", "data/bronze"))
WATERMARKS_DIR = BRONZE_PATH / ".watermarks"
EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)


# ──────────────────────────────────────────────────────────────────────────────
# Watermark helpers
# ──────────────────────────────────────────────────────────────────────────────

def read_watermark(table: TableConfig) -> datetime:
    path = WATERMARKS_DIR / f"{table.watermark_key}.json"
    if not path.exists():
        return EPOCH
    data = json.loads(path.read_text(encoding="utf-8"))
    return datetime.fromisoformat(data["last_updated_at"])


def write_watermark(table: TableConfig, value: datetime) -> None:
    WATERMARKS_DIR.mkdir(parents=True, exist_ok=True)
    path = WATERMARKS_DIR / f"{table.watermark_key}.json"
    tmp = path.with_suffix(f".tmp_{uuid4().hex}.json")
    tmp.write_text(
        json.dumps({"last_updated_at": value.isoformat(), "updated_at_utc": datetime.now(timezone.utc).isoformat()},
                   indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)  # atômico no mesmo filesystem


# ──────────────────────────────────────────────────────────────────────────────
# Parquet helpers
# ──────────────────────────────────────────────────────────────────────────────

def parquet_partition_dir(table: TableConfig, dt: datetime) -> Path:
    return (
        BRONZE_PATH
        / table.schema
        / table.table
        / f"year={dt.year}"
        / f"month={dt.month:02d}"
        / f"day={dt.day:02d}"
    )


def write_parquet_atomic(df: pd.DataFrame, table: TableConfig, ingested_at: datetime) -> Path:
    """Grava DataFrame em Parquet com rename atômico. Retorna path do arquivo final."""
    dest_dir = parquet_partition_dir(table, ingested_at)
    dest_dir.mkdir(parents=True, exist_ok=True)

    final_path = dest_dir / f"batch_{ingested_at.strftime('%H%M%S')}.parquet"
    tmp_path = dest_dir / f".tmp_{uuid4().hex}.parquet"

    df["_source_schema"] = table.schema
    df["_source_table"] = table.table
    df["_ingested_at"] = ingested_at.isoformat()
    df["_row_count_batch"] = len(df)

    df.to_parquet(tmp_path, index=False, engine="pyarrow", compression="snappy")
    tmp_path.replace(final_path)
    return final_path


# ──────────────────────────────────────────────────────────────────────────────
# Extraction
# ──────────────────────────────────────────────────────────────────────────────

def get_connection() -> psycopg2.extensions.connection:
    db_url = os.environ["SUPABASE_DB_URL"]
    return psycopg2.connect(db_url, cursor_factory=RealDictCursor)


def extract_table(
    conn: psycopg2.extensions.connection,
    table: TableConfig,
    watermark: datetime,
    batch_size: int = 50_000,
) -> pd.DataFrame:
    """Extrai registros novos/alterados desde watermark em batches."""
    query = f"""
        SELECT *
        FROM {table.full_name}
        WHERE {table.watermark_col} > %(watermark)s
        ORDER BY {table.watermark_col} ASC
    """
    chunks: list[pd.DataFrame] = []
    with conn.cursor() as cur:
        cur.execute(query, {"watermark": watermark})
        while True:
            rows = cur.fetchmany(batch_size)
            if not rows:
                break
            chunks.append(pd.DataFrame(rows))

    return pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()


def process_table(
    conn: psycopg2.extensions.connection,
    table: TableConfig,
    mode: str,
    ingested_at: datetime,
) -> dict:
    """Processa uma tabela completa: extrai → pseudonimiza → grava → atualiza watermark."""
    watermark = EPOCH if mode == "full" else read_watermark(table)

    log.info(f"[{table.full_name}] modo={mode} watermark={watermark.isoformat()}")

    df = extract_table(conn, table, watermark)
    rows = len(df)

    if rows == 0:
        log.info(f"[{table.full_name}] Nenhum registro novo — skip")
        return {"table": table.full_name, "rows_extracted": 0, "status": "skip"}

    if table.pii_cols:
        df = pseudonimizar_dataframe(df, list(table.pii_cols))

    final_path = write_parquet_atomic(df, table, ingested_at)

    # Watermark atualizado SOMENTE após escrita bem-sucedida
    new_watermark = df[table.watermark_col].max()
    if hasattr(new_watermark, "to_pydatetime"):
        new_watermark = new_watermark.to_pydatetime()
    if new_watermark.tzinfo is None:
        new_watermark = new_watermark.replace(tzinfo=timezone.utc)
    write_watermark(table, new_watermark)

    log.info(f"[{table.full_name}] {rows:,} linhas → {final_path.name} | novo watermark: {new_watermark.isoformat()}")
    return {
        "table": table.full_name,
        "rows_extracted": rows,
        "new_watermark": new_watermark.isoformat(),
        "parquet_path": str(final_path),
        "status": "ok",
    }


# ──────────────────────────────────────────────────────────────────────────────
# CLI entrypoint
# ──────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extrator incremental Supabase → Bronze Parquet")
    p.add_argument("--mode", choices=["full", "incremental"], required=True)
    p.add_argument("--table", help="Processar apenas esta tabela (ex: vendas.pedidos)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    ingested_at = datetime.now(timezone.utc)

    targets = (
        [TABLES_BY_NAME[args.table]]
        if args.table
        else list(TABLES)
    )

    if args.table and args.table not in TABLES_BY_NAME:
        log.error(f"Tabela desconhecida: {args.table}. Disponíveis: {list(TABLES_BY_NAME)}")
        return 1

    results: list[dict] = []
    errors: list[str] = []

    conn = get_connection()
    try:
        for table in targets:
            try:
                result = process_table(conn, table, args.mode, ingested_at)
                results.append(result)
            except Exception as exc:
                log.error(f"[{table.full_name}] ERRO: {exc}", exc_info=True)
                errors.append(table.full_name)
    finally:
        conn.close()

    total_rows = sum(r.get("rows_extracted", 0) for r in results)
    ok_count = sum(1 for r in results if r["status"] in ("ok", "skip"))

    log.info(f"=== Ingestão concluída | {ok_count}/{len(targets)} tabelas OK | {total_rows:,} linhas extraídas ===")

    if errors:
        log.error(f"Tabelas com erro: {errors}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

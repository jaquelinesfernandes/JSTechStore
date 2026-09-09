#!/usr/bin/env python3
"""
Export Gold DuckDB tables to Parquet files for Power BI consumption.

Runs after `dbt run` to produce fresh Parquet files that Power BI reads
directly — eliminates ODBC dependency and file-locking issues.

Usage:
    python scripts/export_gold_parquet.py
    python scripts/export_gold_parquet.py --output-dir data/gold_export
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import duckdb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

GOLD_TABLES = [
    # Dimensões
    "dim_campanha",
    "dim_canal_venda",
    "dim_cliente",
    "dim_fornecedor",
    "dim_loja",
    "dim_modalidade_entrega",
    "dim_produto",
    "dim_tempo",
    "dim_transportadora",
    "dim_vendedor",
    # Fatos
    "fato_venda",
    "fato_entrega",
    "fato_estoque",
    "fato_financeiro",
    "fato_orcamento",
    "fato_cliente_interacao",
]


def export_table(con: duckdb.DuckDBPyConnection, table: str, output_dir: Path) -> dict:
    """Export one table to Parquet. Returns stats dict."""
    t0 = time.time()
    output = output_dir / f"{table}.parquet"

    con.execute(
        f"COPY {table} TO '{output.as_posix()}' (FORMAT PARQUET, COMPRESSION SNAPPY)"
    )

    count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    size_mb = output.stat().st_size / (1024 * 1024)
    elapsed = time.time() - t0

    return {"table": table, "rows": count, "size_mb": size_mb, "seconds": elapsed}


def main():
    parser = argparse.ArgumentParser(description="Export Gold DuckDB → Parquet")
    parser.add_argument(
        "--db",
        default=os.getenv("DUCKDB_PATH", "data/gold/jstechstore.duckdb"),
        help="Caminho do arquivo DuckDB (default: DUCKDB_PATH env ou data/gold/jstechstore.duckdb)",
    )
    parser.add_argument(
        "--output-dir",
        default=os.getenv("GOLD_EXPORT_PATH", "data/gold_export"),
        help="Diretório de saída dos Parquet (default: data/gold_export)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    output_dir = Path(args.output_dir)

    if not db_path.exists():
        log.error("DuckDB não encontrado: %s", db_path)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    log.info("Exportando %d tabelas Gold → %s", len(GOLD_TABLES), output_dir)
    log.info("Fonte: %s (%.1f MB)", db_path, db_path.stat().st_size / (1024 * 1024))

    con = duckdb.connect(str(db_path), read_only=True)

    results = []
    errors = []
    total_rows = 0

    for table in GOLD_TABLES:
        try:
            stats = export_table(con, table, output_dir)
            results.append(stats)
            total_rows += stats["rows"]
            log.info(
                "  ✅ %-30s %9s linhas  %5.1f MB  %.1fs",
                table,
                f"{stats['rows']:,}",
                stats["size_mb"],
                stats["seconds"],
            )
        except Exception as exc:
            errors.append((table, str(exc)))
            log.error("  ❌ %-30s ERRO: %s", table, exc)

    con.close()

    # Resumo
    total_size = sum(r["size_mb"] for r in results)
    log.info(
        "\n✅ Exportação concluída: %d/%d tabelas | %s linhas totais | %.1f MB",
        len(results),
        len(GOLD_TABLES),
        f"{total_rows:,}",
        total_size,
    )

    if errors:
        log.error("Tabelas com erro: %s", [e[0] for e in errors])
        sys.exit(1)


if __name__ == "__main__":
    main()

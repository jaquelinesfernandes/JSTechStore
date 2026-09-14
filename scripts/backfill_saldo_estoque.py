#!/usr/bin/env python3
"""
Backfill de snapshots diários de saldo_estoque.

Problema resolvido:
  O generate_daily.py (modo parquet) gera movimentacoes de estoque mas nunca
  atualiza saldo_estoque. Resultado: fato_estoque fica com apenas 1 snapshot
  (2025-07-21 — a carga inicial) em vez de uma série temporal diária.

Solução:
  1. Lê o saldo inicial do Bronze (2025-07-21).
  2. Agrega todas as movimentacoes por (id_produto, id_loja, data) via DuckDB.
  3. Itera dia a dia aplicando movimentos e reabastecimento aleatório (seed fixo).
  4. Escreve UM Parquet Bronze com todos os snapshots históricos.
  5. O dbt incremental vai carregar tudo na próxima execução.

Uso:
    python scripts/backfill_saldo_estoque.py                         # 2025-07-22 → hoje
    python scripts/backfill_saldo_estoque.py --start 2025-07-22 --end 2026-07-20
    python scripts/backfill_saldo_estoque.py --dry-run               # sem escrita

Após rodar:
    cd transformation/dbt_project
    dbt run --select stg_estoque__saldo_estoque fato_estoque --full-refresh
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pandas as pd
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT))

from ingestion.connectors.postgres.config import TABLES_BY_NAME  # noqa: E402
from ingestion.connectors.postgres.extract import write_parquet_atomic  # noqa: E402

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

BRONZE_PATH = _PROJECT_ROOT / "data" / "bronze"


def _parquet_glob(schema: str, table: str) -> list[str]:
    """Retorna lista de Parquets reais (sem stubs) de uma tabela Bronze."""
    return sorted(
        str(f)
        for f in (BRONZE_PATH / schema / table).rglob("*.parquet")
        if "stub_empty" not in f.name
    )


def load_initial_saldo() -> pd.DataFrame:
    """Carrega o snapshot mais recente de saldo_estoque do Bronze."""
    files = _parquet_glob("estoque", "saldo_estoque")
    if not files:
        raise FileNotFoundError(
            "Nenhum Parquet de saldo_estoque encontrado em data/bronze/estoque/saldo_estoque/. "
            "Execute a ingestão completa primeiro."
        )

    df = duckdb.connect().execute(
        f"""
        SELECT id_saldo, id_produto, id_loja,
               qtd_disponivel, qtd_reservada, qtd_minima,
               CAST(dt_ultima_atualizacao AS DATE) AS dt_ultima_atualizacao,
               updated_at
        FROM read_parquet({files!r}, union_by_name := true)
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY id_produto, id_loja
            ORDER BY updated_at DESC
        ) = 1
        """
    ).df()
    return df


def load_all_movs() -> pd.DataFrame:
    """Agrega movimentacoes de estoque por (id_produto, id_loja, data)."""
    files = _parquet_glob("estoque", "movimentacoes")
    if not files:
        log.warning("Nenhum Parquet de movimentacoes encontrado — backfill sem movimentos.")
        return pd.DataFrame(columns=["id_produto", "id_loja", "dt", "qtd_net"])

    df = duckdb.connect().execute(
        f"""
        SELECT
            CAST(id_produto AS INTEGER)           AS id_produto,
            CAST(id_loja    AS INTEGER)           AS id_loja,
            CAST(dt_movimentacao AS DATE)         AS dt,
            SUM(CAST(qtd AS DOUBLE))              AS qtd_net
        FROM read_parquet({files!r}, union_by_name := true)
        WHERE tipo_mov IS NOT NULL
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3
        """
    ).df()
    return df


def run_backfill(
    start_date: date,
    end_date: date,
    dry_run: bool = False,
) -> int:
    """
    Gera snapshots diários de saldo_estoque de start_date a end_date.
    Retorna o número de dias processados.
    """

    # ── 1. Saldo inicial ──────────────────────────────────────────────────────
    df_saldo_inicial = load_initial_saldo()
    saldo_ref_date = df_saldo_inicial["dt_ultima_atualizacao"].iloc[0]
    log.info(
        f"Saldo inicial carregado: {len(df_saldo_inicial):,} linhas "
        f"(ref: {saldo_ref_date})"
    )

    # Converte para dict mutável: (id_produto, id_loja) → {qtd_disponivel, ...}
    saldo_map: dict[tuple[int, int], dict] = {
        (int(r["id_produto"]), int(r["id_loja"])): {
            "id_saldo":       int(r["id_saldo"]),
            "qtd_disponivel": int(r["qtd_disponivel"]),
            "qtd_reservada":  int(r["qtd_reservada"]),
            "qtd_minima":     int(r["qtd_minima"]),
        }
        for _, r in df_saldo_inicial.iterrows()
    }

    # ── 2. Movimentações agregadas por dia ────────────────────────────────────
    df_movs = load_all_movs()
    log.info(f"Movimentações carregadas: {len(df_movs):,} linhas")

    # Indexa por (id_produto, id_loja, dt) para lookup O(1)
    movs_index: dict[tuple[int, int, date], float] = {}
    for _, r in df_movs.iterrows():
        key = (int(r["id_produto"]), int(r["id_loja"]), r["dt"].date() if hasattr(r["dt"], "date") else r["dt"])
        movs_index[key] = float(r["qtd_net"])

    # ── 3. Itera dia a dia ────────────────────────────────────────────────────
    all_snapshot_rows: list[dict] = []
    ingested_at = datetime.now(timezone.utc)
    current_date = start_date
    days_count = 0

    log.info(f"Iniciando backfill: {start_date} → {end_date}")

    while current_date <= end_date:
        # Semente determinística por dia (reprodutível)
        rng = random.Random(int(current_date.strftime("%Y%m%d")) + 42)

        for (id_prod, id_loja), s in saldo_map.items():
            qtd_mov = movs_index.get((id_prod, id_loja, current_date), 0.0)
            saida   = abs(qtd_mov) if qtd_mov < 0 else 0.0
            entrada = qtd_mov      if qtd_mov > 0 else 0.0

            # Reabastecimento: automático quando critico, aleatório (~8%) no resto
            restocking = 0
            estoque_pos_saida = s["qtd_disponivel"] - int(saida) + int(entrada)
            if estoque_pos_saida < s["qtd_minima"]:
                # Abastece para 2× o mínimo + variação
                restocking = s["qtd_minima"] * 2 + rng.randint(5, 30)
            elif rng.random() < 0.08:
                restocking = rng.randint(5, 25)

            nova_qtd = max(0, estoque_pos_saida + restocking)
            s["qtd_disponivel"] = nova_qtd  # atualiza para o próximo dia

            all_snapshot_rows.append({
                "id_saldo":             s["id_saldo"],
                "id_produto":           id_prod,
                "id_loja":              id_loja,
                "qtd_disponivel":       nova_qtd,
                "qtd_reservada":        s["qtd_reservada"],
                "qtd_minima":           s["qtd_minima"],
                "dt_ultima_atualizacao": current_date,
                "updated_at":           ingested_at,
            })

        days_count += 1
        if days_count % 30 == 0 or current_date == end_date:
            log.info(
                f"  Processado até {current_date} "
                f"({days_count} dias, {len(all_snapshot_rows):,} linhas acumuladas)"
            )

        current_date += timedelta(days=1)

    # ── 4. Escreve Parquet Bronze ─────────────────────────────────────────────
    if dry_run:
        log.info(
            f"[DRY-RUN] Seriam escritas {len(all_snapshot_rows):,} linhas "
            f"({days_count} snapshots × {len(saldo_map)} produto/loja)."
        )
        return days_count

    df_out = pd.DataFrame(all_snapshot_rows)
    df_out["dt_ultima_atualizacao"] = pd.to_datetime(df_out["dt_ultima_atualizacao"])
    df_out["updated_at"] = pd.to_datetime(df_out["updated_at"], utc=True)

    table_cfg = TABLES_BY_NAME["estoque.saldo_estoque"]
    parquet_path = write_parquet_atomic(df_out, table_cfg, ingested_at)

    log.info(
        f"✅ Backfill concluído: {days_count} dias | "
        f"{len(all_snapshot_rows):,} linhas → {parquet_path}"
    )
    log.info("")
    log.info("Próximo passo — reconstruir staging e fato:")
    log.info("  cd transformation/dbt_project")
    log.info("  dbt run --select stg_estoque__saldo_estoque fato_estoque --full-refresh")

    return days_count


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Backfill de snapshots diários de saldo_estoque no Bronze Parquet."
    )
    p.add_argument(
        "--start",
        default="2025-07-22",
        help="Data inicial do backfill (padrão: 2025-07-22 = dia após carga inicial)",
    )
    p.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="Data final do backfill (padrão: hoje)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula sem escrever nenhum arquivo.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    start = date.fromisoformat(args.start)
    end   = date.fromisoformat(args.end)

    if start > end:
        log.error(f"--start ({start}) > --end ({end}). Inverter as datas.")
        return 1

    run_backfill(start, end, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())

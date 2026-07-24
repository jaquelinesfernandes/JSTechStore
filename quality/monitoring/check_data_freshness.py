"""
Monitora frescor de dados nas camadas Bronze e Gold.

Verifica:
  1. Bronze — cada tabela tem partição Parquet do dia atual (ou D-1 em janela aceitável)
  2. Gold   — tabelas fato têm MAX(sk_tempo) >= D-1 (YYYYMMDD)
  3. Batch size — número de linhas ingeridas está dentro de faixa esperada por tabela

Retorna exit 0 se tudo OK, exit 1 se qualquer verificação falhar.
Usado como step no GitHub Actions após dbt run.

Uso:
    python quality/monitoring/check_data_freshness.py
    python quality/monitoring/check_data_freshness.py --tolerance-hours 26
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

BRONZE_PATH = Path(os.getenv("BRONZE_PATH", "data/bronze"))
DUCKDB_PATH = Path(os.getenv("DUCKDB_PATH", "data/gold/jstechstore.duckdb"))

# Tabelas críticas do Bronze que devem ter dados diários
BRONZE_CRITICAL_TABLES: tuple[tuple[str, str], ...] = (
    ("vendas", "pedidos"),
    ("vendas", "itens_pedido"),
    ("clientes", "clientes"),
    ("estoque", "saldo_estoque"),
    ("logistica", "entregas"),
    ("financeiro", "lancamentos"),
    ("web_analytics", "sessoes"),
)

# Fato tables do Gold com janela esperada de sk_tempo
GOLD_FACT_TABLES: tuple[str, ...] = (
    "fato_venda",
    "fato_estoque",
    "fato_entrega",
    "fato_financeiro",
    "fato_cliente_interacao",
    "fato_orcamento",
)

# Faixa esperada de linhas diárias por tabela (min, max) — calibrar conforme volumetria
EXPECTED_DAILY_ROWS: dict[str, tuple[int, int]] = {
    "vendas.pedidos": (1_500, 3_000),
    "vendas.itens_pedido": (5_000, 10_000),
    "clientes.clientes": (0, 500),
    "estoque.saldo_estoque": (0, 5_000),
    "logistica.entregas": (1_000, 3_500),
    "financeiro.lancamentos": (2_000, 8_000),
    "web_analytics.sessoes": (3_000, 15_000),
    "web_analytics.eventos_carrinho": (5_000, 30_000),
}


def check_bronze_freshness(tolerance_hours: int) -> list[str]:
    """Verifica se as tabelas críticas do Bronze têm Parquet recente."""
    errors: list[str] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=tolerance_hours)
    today = datetime.now(timezone.utc)

    for schema, table in BRONZE_CRITICAL_TABLES:
        base = BRONZE_PATH / schema / table
        if not base.exists():
            errors.append(f"BRONZE [{schema}.{table}] Diretório não encontrado: {base}")
            continue

        # Procura o Parquet mais recente nas últimas tolerance_hours
        latest_file: Path | None = None
        latest_mtime: float = 0.0
        for parquet in base.rglob("*.parquet"):
            mtime = parquet.stat().st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_file = parquet

        if latest_file is None:
            errors.append(
                f"BRONZE [{schema}.{table}] Nenhum arquivo Parquet encontrado"
            )
            continue

        file_dt = datetime.fromtimestamp(latest_mtime, tz=timezone.utc)
        age_hours = (today - file_dt).total_seconds() / 3600

        if file_dt < cutoff:
            errors.append(
                f"BRONZE [{schema}.{table}] Parquet desatualizado: "
                f"último arquivo tem {age_hours:.1f}h (tolerância: {tolerance_hours}h) — {latest_file}"
            )
        else:
            log.info(
                f"BRONZE [{schema}.{table}] OK — {age_hours:.1f}h atrás ({latest_file.name})"
            )

    return errors


def check_gold_freshness(tolerance_hours: int) -> list[str]:
    """Verifica se tabelas fato do Gold têm dados de D-1 no máximo."""
    errors: list[str] = []

    try:
        import duckdb
    except ImportError:
        errors.append("GOLD Pacote 'duckdb' não instalado — verificação Gold ignorada")
        return errors

    if not DUCKDB_PATH.exists():
        errors.append(f"GOLD Arquivo não encontrado: {DUCKDB_PATH}")
        return errors

    expected_min_sk = int(
        (datetime.now(timezone.utc) - timedelta(hours=tolerance_hours)).strftime(
            "%Y%m%d"
        )
    )

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        for fact in GOLD_FACT_TABLES:
            try:
                # sk_tempo no formato YYYYMMDD
                sk_col = "sk_tempo_pedido" if fact == "fato_entrega" else "sk_tempo"
                result = con.execute(f"SELECT MAX({sk_col}) FROM {fact}").fetchone()
                max_sk = result[0] if result else None

                if max_sk is None:
                    errors.append(f"GOLD [{fact}] Tabela vazia")
                elif max_sk < expected_min_sk:
                    errors.append(
                        f"GOLD [{fact}] Desatualizada: MAX({sk_col})={max_sk} "
                        f"< esperado={expected_min_sk}"
                    )
                else:
                    log.info(f"GOLD [{fact}] OK — MAX({sk_col})={max_sk}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"GOLD [{fact}] Erro ao consultar: {exc}")
    finally:
        con.close()

    return errors


def check_bronze_batch_size() -> list[str]:
    """Verifica se o volume de linhas do último batch está na faixa esperada."""
    warnings: list[str] = []
    today = datetime.now(timezone.utc)
    date_path = f"year={today.year}/month={today.month:02d}/day={today.day:02d}"

    for full_name, (min_rows, max_rows) in EXPECTED_DAILY_ROWS.items():
        schema, table = full_name.split(".")
        partition = BRONZE_PATH / schema / table / date_path

        if not partition.exists():
            warnings.append(
                f"BATCH [{full_name}] Partição de hoje não encontrada: {partition}"
            )
            continue

        try:
            import pyarrow.parquet as pq

            total = sum(
                pq.read_metadata(f).num_rows
                for f in partition.glob("*.parquet")
                if not f.name.startswith(".tmp")
            )
        except ImportError:
            # Fallback: conta via pandas (mais lento)
            import pandas as pd

            frames = [
                pd.read_parquet(f)
                for f in partition.glob("*.parquet")
                if not f.name.startswith(".tmp")
            ]
            total = sum(len(f) for f in frames) if frames else 0

        if total < min_rows:
            warnings.append(
                f"BATCH [{full_name}] Volume abaixo do esperado: {total:,} linhas (mín: {min_rows:,})"
            )
        elif total > max_rows:
            warnings.append(
                f"BATCH [{full_name}] Volume acima do esperado: {total:,} linhas (máx: {max_rows:,}) — verifique duplicatas"
            )
        else:
            log.info(f"BATCH [{full_name}] OK — {total:,} linhas")

    return warnings


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Verificação de frescor de dados Bronze e Gold"
    )
    p.add_argument(
        "--tolerance-hours",
        type=int,
        default=26,
        help="Horas máximas de defasagem aceitas (padrão: 26h = D-1 + margem)",
    )
    p.add_argument(
        "--skip-batch-size",
        action="store_true",
        help="Ignora verificação de volume de batch",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    all_errors: list[str] = []

    log.info(f"=== Verificação de Frescor | tolerância={args.tolerance_hours}h ===")

    bronze_errors = check_bronze_freshness(args.tolerance_hours)
    gold_errors = check_gold_freshness(args.tolerance_hours)
    all_errors.extend(bronze_errors + gold_errors)

    if not args.skip_batch_size:
        batch_warnings = check_bronze_batch_size()
        if batch_warnings:
            for w in batch_warnings:
                log.warning(w)
            # Avisos de volume não falham o pipeline, apenas alertam
            log.warning(
                f"{len(batch_warnings)} aviso(s) de volume — revisar manualmente"
            )

    if all_errors:
        log.error(f"\n{'=' * 60}")
        log.error(f"FALHA — {len(all_errors)} erro(s) de frescor:")
        for err in all_errors:
            log.error(f"  ✗ {err}")
        log.error("=" * 60)
        return 1

    log.info("=== Todas as verificações de frescor passaram ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

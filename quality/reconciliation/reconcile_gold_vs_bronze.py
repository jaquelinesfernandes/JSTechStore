"""
Reconciliação Gold (DuckDB) vs. Bronze Parquet.

Substitui reconcile_gold_vs_source.py na arquitetura Parquet-first
(generate_daily --output parquet): compara os 6 fatos do Gold contra os
arquivos Bronze Parquet usando DuckDB para ambos os lados — sem depender do
banco Neon/Supabase.

Fatos cobertos:
  fato_venda             → frescor (max data) vs Bronze vendas/pedidos
  fato_estoque           → contagem snapshot  vs Bronze estoque/saldo_estoque
  fato_entrega           → contagem + flags    vs Bronze logistica/entregas
  fato_financeiro        → contagem + soma     vs Bronze financeiro/lancamentos
  fato_cliente_interacao → contagem sessões    vs Bronze web_analytics/sessoes
  fato_orcamento         → contagem + soma     vs Bronze financeiro/orcamentos

Lógica Bronze:
  Cada tabela é lida com read_parquet(..., union_by_name := true) e deduplicada
  via ROW_NUMBER OVER (PARTITION BY <pk> ORDER BY updated_at DESC) — exatamente
  a mesma lógica dos modelos dbt de staging.  Arquivos stub (stub_empty.parquet)
  são ignorados automaticamente pelo filtro IS NOT NULL na PK.

Uso:
    python quality/reconciliation/reconcile_gold_vs_bronze.py
    python quality/reconciliation/reconcile_gold_vs_bronze.py --table fato_entrega
    python quality/reconciliation/reconcile_gold_vs_bronze.py --tolerance 0.005

Retorna exit 0 se tudo OK, exit 1 se qualquer check exceder a tolerância.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

DUCKDB_PATH = Path(os.getenv("DUCKDB_PATH", "data/gold/jstechstore.duckdb"))
BRONZE_PATH = Path(os.getenv("BRONZE_PATH", "data/bronze"))
DEFAULT_TOLERANCE = 0.001   # 0,1%
LOG_DIR = Path("quality/reconciliation/logs")

# Placeholder substituído em runtime pelo caminho Bronze real (POSIX).
_B = "{bronze_path}"


# ─────────────────────────────────────────────────────────────────────────────
# Dataclass de check
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ReconciliationCheck:
    name: str
    gold_query: str          # SQL contra gold_db (alias ATTACH)
    bronze_query: str        # SQL com read_parquet(); {bronze_path} é substituído
    metric_label: str
    tolerance: float = DEFAULT_TOLERANCE


# ─────────────────────────────────────────────────────────────────────────────
# Checks
# ─────────────────────────────────────────────────────────────────────────────

CHECKS: tuple[ReconciliationCheck, ...] = (

    # ── fato_venda ────────────────────────────────────────────────────────────
    # Janela incremental do dbt = últimos 3 dias, por isso verificamos frescor
    # via MAX(data) em vez de contagem acumulada.
    ReconciliationCheck(
        name="fato_venda.max_data",
        gold_query="""
            SELECT CAST(STRFTIME(MAX(dt_pedido_data), '%Y%m%d') AS INTEGER)
            FROM gold_db.fato_venda
            WHERE fl_venda_valida = TRUE
        """,
        bronze_query=f"""
            SELECT CAST(STRFTIME(MAX(CAST(dt_pedido AS DATE)), '%Y%m%d') AS INTEGER)
            FROM (
                SELECT dt_pedido, status,
                       ROW_NUMBER() OVER (
                           PARTITION BY id_pedido ORDER BY updated_at DESC
                       ) AS _rn
                FROM read_parquet(
                    '{_B}/vendas/pedidos/**/*.parquet',
                    union_by_name := true
                )
                WHERE id_pedido IS NOT NULL
            )
            WHERE _rn = 1
              AND status NOT IN ('cancelado', 'devolvido')
        """,
        metric_label="data máxima de pedido (YYYYMMDD) — Gold deve ter dados de hoje",
        tolerance=0.0,
    ),

    # ── fato_estoque ──────────────────────────────────────────────────────────
    # Snapshot atual: compara Gold (sk_tempo=MAX) vs Bronze SOMENTE do batch
    # mais recente (_ingested_at=MAX). Bronze acumula batches históricos com
    # id_produto de ranges diferentes (Supabase original + Parquet-mode IDs);
    # sem o filtro por _ingested_at o dedup retornaria todos os pares únicos
    # de TODOS os batches, inflando a contagem vs. o snapshot atual do Gold.
    ReconciliationCheck(
        name="fato_estoque.count",
        gold_query="""
            SELECT COUNT(*)
            FROM gold_db.fato_estoque
            WHERE sk_tempo = (SELECT MAX(sk_tempo) FROM gold_db.fato_estoque)
        """,
        bronze_query=f"""
            SELECT COUNT(*) FROM (
                SELECT id_produto, id_loja, qtd_disponivel,
                       ROW_NUMBER() OVER (
                           PARTITION BY id_produto, id_loja
                           ORDER BY updated_at DESC
                       ) AS _rn
                FROM read_parquet(
                    '{_B}/estoque/saldo_estoque/**/*.parquet',
                    union_by_name := true
                )
                WHERE _ingested_at::DATE = (
                    SELECT MAX(_ingested_at::DATE)
                    FROM read_parquet(
                        '{_B}/estoque/saldo_estoque/**/*.parquet',
                        union_by_name := true
                    )
                    WHERE id_produto IS NOT NULL
                )
                  AND id_produto IS NOT NULL
                  AND id_loja IS NOT NULL
            )
            WHERE _rn = 1
              AND CAST(qtd_disponivel AS INTEGER) >= 0
        """,
        metric_label="linhas fato_estoque (snapshot batch mais recente por produto × loja)",
        tolerance=0.0,
    ),

    # ── fato_entrega ──────────────────────────────────────────────────────────
    ReconciliationCheck(
        name="fato_entrega.count",
        gold_query="""
            SELECT COUNT(*)
            FROM gold_db.fato_entrega
            WHERE dt_postagem >= CURRENT_DATE - INTERVAL '2 days'
        """,
        bronze_query=f"""
            SELECT COUNT(*) FROM (
                SELECT id_entrega, dt_postagem
                FROM (
                    SELECT id_entrega, dt_postagem,
                           ROW_NUMBER() OVER (
                               PARTITION BY id_entrega ORDER BY updated_at DESC
                           ) AS _rn
                    FROM read_parquet(
                        '{_B}/logistica/entregas/**/*.parquet',
                        union_by_name := true
                    )
                )
                WHERE _rn = 1 AND id_entrega IS NOT NULL
            )
            WHERE CAST(dt_postagem AS DATE) >= CURRENT_DATE - INTERVAL '2 days'
        """,
        metric_label="linhas fato_entrega (últimos 2 dias)",
        tolerance=0.0,
    ),

    # ── fato_financeiro ───────────────────────────────────────────────────────
    ReconciliationCheck(
        name="fato_financeiro.count",
        gold_query="""
            SELECT COUNT(*)
            FROM gold_db.fato_financeiro
            WHERE dt_lancamento >= CURRENT_DATE - INTERVAL '2 days'
        """,
        bronze_query=f"""
            SELECT COUNT(*) FROM (
                SELECT id_lancamento, dt_lancamento
                FROM (
                    SELECT id_lancamento, dt_lancamento,
                           ROW_NUMBER() OVER (
                               PARTITION BY id_lancamento ORDER BY updated_at DESC
                           ) AS _rn
                    FROM read_parquet(
                        '{_B}/financeiro/lancamentos/**/*.parquet',
                        union_by_name := true
                    )
                )
                WHERE _rn = 1 AND id_lancamento IS NOT NULL
            )
            WHERE CAST(dt_lancamento AS DATE) >= CURRENT_DATE - INTERVAL '2 days'
        """,
        metric_label="linhas fato_financeiro (últimos 2 dias)",
        tolerance=0.0,
    ),

    ReconciliationCheck(
        name="fato_financeiro.valor",
        gold_query="""
            SELECT ROUND(SUM(valor), 2)
            FROM gold_db.fato_financeiro
            WHERE dt_lancamento >= CURRENT_DATE - INTERVAL '2 days'
        """,
        bronze_query=f"""
            SELECT ROUND(SUM(CAST(valor AS DOUBLE)), 2) FROM (
                SELECT id_lancamento, dt_lancamento, valor
                FROM (
                    SELECT id_lancamento, dt_lancamento, valor,
                           ROW_NUMBER() OVER (
                               PARTITION BY id_lancamento ORDER BY updated_at DESC
                           ) AS _rn
                    FROM read_parquet(
                        '{_B}/financeiro/lancamentos/**/*.parquet',
                        union_by_name := true
                    )
                )
                WHERE _rn = 1 AND id_lancamento IS NOT NULL
            )
            WHERE CAST(dt_lancamento AS DATE) >= CURRENT_DATE - INTERVAL '2 days'
        """,
        metric_label="soma valor lançamentos financeiros (últimos 2 dias, BRL)",
    ),

    # ── fato_cliente_interacao ────────────────────────────────────────────────
    ReconciliationCheck(
        name="fato_cliente_interacao.count_sessoes",
        gold_query="""
            SELECT COUNT(*)
            FROM gold_db.fato_cliente_interacao
            WHERE dt_sessao >= CURRENT_DATE - INTERVAL '2 days'
        """,
        bronze_query=f"""
            SELECT COUNT(*) FROM (
                SELECT id_sessao, dt_inicio
                FROM (
                    SELECT id_sessao, dt_inicio,
                           ROW_NUMBER() OVER (
                               PARTITION BY id_sessao ORDER BY updated_at DESC
                           ) AS _rn
                    FROM read_parquet(
                        '{_B}/web_analytics/sessoes/**/*.parquet',
                        union_by_name := true
                    )
                )
                WHERE _rn = 1 AND id_sessao IS NOT NULL
            )
            WHERE CAST(dt_inicio AS DATE) >= CURRENT_DATE - INTERVAL '2 days'
        """,
        metric_label="sessões em fato_cliente_interacao (últimos 2 dias)",
        tolerance=0.0,
    ),

    # ── fato_orcamento ────────────────────────────────────────────────────────
    # Tabela estática (metas por mês × loja × canal) — compara full table.
    ReconciliationCheck(
        name="fato_orcamento.count",
        gold_query="SELECT COUNT(*) FROM gold_db.fato_orcamento",
        bronze_query=f"""
            SELECT COUNT(*) FROM (
                SELECT id_orcamento
                FROM (
                    SELECT id_orcamento,
                           ROW_NUMBER() OVER (
                               PARTITION BY id_orcamento ORDER BY updated_at DESC
                           ) AS _rn
                    FROM read_parquet(
                        '{_B}/financeiro/orcamentos/**/*.parquet',
                        union_by_name := true
                    )
                )
                WHERE _rn = 1 AND id_orcamento IS NOT NULL
            )
        """,
        metric_label="linhas fato_orcamento (full table)",
        tolerance=0.0,
    ),

    ReconciliationCheck(
        name="fato_orcamento.receita_meta",
        gold_query="SELECT ROUND(SUM(valor_meta_receita), 2) FROM gold_db.fato_orcamento",
        bronze_query=f"""
            SELECT ROUND(SUM(CAST(valor_meta_receita AS DOUBLE)), 2) FROM (
                SELECT id_orcamento, valor_meta_receita
                FROM (
                    SELECT id_orcamento, valor_meta_receita,
                           ROW_NUMBER() OVER (
                               PARTITION BY id_orcamento ORDER BY updated_at DESC
                           ) AS _rn
                    FROM read_parquet(
                        '{_B}/financeiro/orcamentos/**/*.parquet',
                        union_by_name := true
                    )
                )
                WHERE _rn = 1 AND id_orcamento IS NOT NULL
            )
        """,
        metric_label="soma receita meta orçada (BRL)",
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Funções auxiliares
# ─────────────────────────────────────────────────────────────────────────────

def deviation(gold_val: float | None, bronze_val: float | None) -> float:
    """Desvio relativo |gold − bronze| / |bronze|."""
    if bronze_val is None or bronze_val == 0:
        return 0.0 if gold_val in (None, 0) else float("inf")
    if gold_val is None:
        return float("inf")
    return abs(gold_val - bronze_val) / abs(bronze_val)


def run_check(
    check: ReconciliationCheck,
    con,
    bronze_path_posix: str,
) -> dict:
    bronze_q = check.bronze_query.replace("{bronze_path}", bronze_path_posix)

    try:
        gold_val = con.execute(check.gold_query).fetchone()[0]
    except Exception as exc:
        raise RuntimeError(f"Gold query falhou: {exc}\nSQL:\n{check.gold_query}") from exc

    try:
        bronze_val = con.execute(bronze_q).fetchone()[0]
    except Exception as exc:
        raise RuntimeError(
            f"Bronze query falhou: {exc}\nSQL:\n{bronze_q}"
        ) from exc

    dev = deviation(
        float(gold_val) if gold_val is not None else None,
        float(bronze_val) if bronze_val is not None else None,
    )
    passed = dev <= check.tolerance

    log.log(
        logging.INFO if passed else logging.ERROR,
        "[%s] %s | Gold=%s | Bronze=%s | desvio=%.4f%% | tolerância=%.4f%%",
        check.name,
        "OK" if passed else "FALHA",
        gold_val,
        bronze_val,
        dev * 100,
        check.tolerance * 100,
    )

    return {
        "check": check.name,
        "metric": check.metric_label,
        "gold_value": gold_val,
        "bronze_value": bronze_val,
        "deviation_pct": round(dev * 100, 6),
        "tolerance_pct": round(check.tolerance * 100, 4),
        "passed": passed,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Reconciliação Gold vs. Bronze Parquet para todas as tabelas fato"
    )
    p.add_argument(
        "--table",
        help="Filtrar por prefixo de check (ex: fato_venda, fato_entrega)",
    )
    p.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE,
        help="Tolerância de desvio relativo (padrão: 0.001 = 0,1%%)",
    )
    p.add_argument(
        "--output",
        type=Path,
        help="Salvar resultado JSON em arquivo específico",
    )
    return p.parse_args()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()

    try:
        import duckdb
    except ImportError:
        log.error("duckdb não instalado — execute: pip install duckdb")
        return 1

    # ── Pré-condições ─────────────────────────────────────────────────────────
    if not DUCKDB_PATH.exists():
        log.error("Gold DuckDB não encontrado: %s", DUCKDB_PATH)
        return 1

    if not BRONZE_PATH.is_dir():
        log.error("Diretório Bronze não encontrado: %s", BRONZE_PATH)
        return 1

    # ── Seleciona checks ──────────────────────────────────────────────────────
    checks = [c for c in CHECKS if not args.table or c.name.startswith(args.table)]
    if not checks:
        log.error("Nenhum check encontrado para --table=%s", args.table)
        return 1

    # Override tolerância global
    if args.tolerance != DEFAULT_TOLERANCE:
        checks = [
            ReconciliationCheck(
                name=c.name,
                gold_query=c.gold_query,
                bronze_query=c.bronze_query,
                metric_label=c.metric_label,
                tolerance=args.tolerance,
            )
            for c in checks
        ]

    log.info(
        "=== Reconciliação Gold vs. Bronze Parquet | %d check(s) ===",
        len(checks),
    )
    log.info("Gold  : %s", DUCKDB_PATH)
    log.info("Bronze: %s", BRONZE_PATH)

    # ── Conexão única — DuckDB in-memory com Gold ATTACHed ───────────────────
    bronze_path_posix = BRONZE_PATH.as_posix()
    con = duckdb.connect()
    try:
        con.execute(f"ATTACH '{DUCKDB_PATH.as_posix()}' AS gold_db (READ_ONLY)")
    except Exception as exc:
        log.error("Não foi possível abrir Gold DuckDB: %s", exc)
        con.close()
        return 1

    # ── Executa checks ────────────────────────────────────────────────────────
    results: list[dict] = []
    try:
        for check in checks:
            try:
                result = run_check(check, con, bronze_path_posix)
                results.append(result)
            except Exception as exc:
                log.exception("[%s] Erro ao executar check: %s", check.name, exc)
                results.append({
                    "check": check.name,
                    "passed": False,
                    "error": str(exc),
                })
    finally:
        con.close()

    # ── Relatório ─────────────────────────────────────────────────────────────
    failures = [r for r in results if not r.get("passed", False)]

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "Bronze Parquet",
        "total_checks": len(results),
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "results": results,
    }

    output_path = (
        args.output
        or LOG_DIR / f"reconciliation_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    log.info("Relatório salvo: %s", output_path)

    if failures:
        log.error("\n=== RECONCILIAÇÃO FALHOU — %d check(s) ===", len(failures))
        for f in failures:
            log.error("  ✗ %s: desvio=%s%%", f["check"], f.get("deviation_pct", "?"))
        return 1

    log.info("=== Reconciliação OK — %d check(s) passaram ===", len(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())

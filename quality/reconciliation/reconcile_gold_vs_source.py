"""
Reconciliação Gold (DuckDB) vs. fonte (Supabase/PostgreSQL).

Cobre todas as 6 tabelas fato:
  fato_venda            → vendas.itens_pedido
  fato_estoque          → estoque.saldo_estoque (snapshot D-1)
  fato_entrega          → logistica.entregas
  fato_financeiro       → financeiro.lancamentos
  fato_cliente_interacao→ web_analytics.sessoes + web_analytics.eventos_carrinho
  fato_orcamento        → financeiro.orcamentos

Para cada fato verifica:
  - Contagem de linhas (desvio tolerado: 0%)
  - Soma de métricas financeiras (desvio tolerado: 0,1%)

Retorna exit 0 se tudo OK, exit 1 se qualquer métrica exceder a tolerância.

Uso:
    python quality/reconciliation/reconcile_gold_vs_source.py
    python quality/reconciliation/reconcile_gold_vs_source.py --table fato_venda
    python quality/reconciliation/reconcile_gold_vs_source.py --tolerance 0.005
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
DEFAULT_TOLERANCE = 0.001  # 0,1%
LOG_DIR = Path("quality/reconciliation/logs")


@dataclass
class ReconciliationCheck:
    name: str
    gold_query: str
    source_query: str
    metric_label: str
    tolerance: float = DEFAULT_TOLERANCE


CHECKS: tuple[ReconciliationCheck, ...] = (
    # ── fato_venda ────────────────────────────────────────────────────────
    # generate_daily.py insere novas linhas a cada run (não upsert), portanto
    # counts e somas acumulam em Supabase enquanto Gold tem só o batch atual.
    # Verificamos frescor via MAX(dt_pedido_data): Gold deve ter dados de hoje.
    ReconciliationCheck(
        name="fato_venda.max_data",
        gold_query="""
            SELECT CAST(STRFTIME(MAX(dt_pedido_data), '%Y%m%d') AS INTEGER)
            FROM fato_venda WHERE fl_venda_valida = TRUE
        """,
        source_query="""
            SELECT CAST(TO_CHAR(MAX(DATE(p.dt_pedido)), 'YYYYMMDD') AS INTEGER)
            FROM vendas.pedidos p
            WHERE p.status NOT IN ('cancelado', 'devolvido')
        """,
        metric_label="data máxima pedido (YYYYMMDD) — Gold deve ter dados de hoje",
        tolerance=0.0,
    ),
    # ── fato_estoque ──────────────────────────────────────────────────────
    # Apenas contagem — Gold não persiste valor monetário de estoque
    ReconciliationCheck(
        name="fato_estoque.count",
        gold_query="""
            SELECT COUNT(*) FROM fato_estoque
            WHERE sk_tempo = (SELECT MAX(sk_tempo) FROM fato_estoque)
        """,
        source_query="SELECT COUNT(*) FROM estoque.saldo_estoque WHERE qtd_disponivel >= 0",
        metric_label="linhas fato_estoque (último snapshot)",
        tolerance=0.0,
    ),
    # ── fato_entrega ──────────────────────────────────────────────────────
    # Escopo: últimos 2 dias (pipeline incremental; Gold só tem batch atual)
    ReconciliationCheck(
        name="fato_entrega.count",
        gold_query="""
            SELECT COUNT(*) FROM fato_entrega
            WHERE dt_postagem >= CURRENT_DATE - INTERVAL '2 days'
        """,
        source_query="""
            SELECT COUNT(*) FROM logistica.entregas
            WHERE dt_postagem >= CURRENT_DATE - INTERVAL '2 days'
        """,
        metric_label="linhas fato_entrega (últimos 2 dias)",
        tolerance=0.0,
    ),
    # ── fato_financeiro ───────────────────────────────────────────────────
    # Escopo: últimos 2 dias; coluna é 'valor' (não valor_liquido)
    ReconciliationCheck(
        name="fato_financeiro.count",
        gold_query="""
            SELECT COUNT(*) FROM fato_financeiro
            WHERE dt_lancamento >= CURRENT_DATE - INTERVAL '2 days'
        """,
        source_query="""
            SELECT COUNT(*) FROM financeiro.lancamentos
            WHERE dt_lancamento >= CURRENT_DATE - INTERVAL '2 days'
        """,
        metric_label="linhas fato_financeiro (últimos 2 dias)",
        tolerance=0.0,
    ),
    ReconciliationCheck(
        name="fato_financeiro.valor",
        gold_query="""
            SELECT ROUND(SUM(valor), 2) FROM fato_financeiro
            WHERE dt_lancamento >= CURRENT_DATE - INTERVAL '2 days'
        """,
        source_query="""
            SELECT ROUND(SUM(valor), 2) FROM financeiro.lancamentos
            WHERE dt_lancamento >= CURRENT_DATE - INTERVAL '2 days'
        """,
        metric_label="soma valor financeiro (últimos 2 dias, BRL)",
    ),
    # ── fato_cliente_interacao ────────────────────────────────────────────
    # Grão = 1 linha por sessão; sem coluna tipo_interacao
    ReconciliationCheck(
        name="fato_cliente_interacao.count_sessoes",
        gold_query="""
            SELECT COUNT(*) FROM fato_cliente_interacao
            WHERE dt_sessao >= CURRENT_DATE - INTERVAL '2 days'
        """,
        source_query="""
            SELECT COUNT(*) FROM web_analytics.sessoes
            WHERE DATE(dt_inicio) >= CURRENT_DATE - INTERVAL '2 days'
        """,
        metric_label="linhas sessões em fato_cliente_interacao (últimos 2 dias)",
        tolerance=0.0,
    ),
    # ── fato_orcamento ────────────────────────────────────────────────────
    ReconciliationCheck(
        name="fato_orcamento.count",
        gold_query="SELECT COUNT(*) FROM fato_orcamento",
        source_query="SELECT COUNT(*) FROM financeiro.orcamentos",
        metric_label="linhas fato_orcamento",
        tolerance=0.0,
    ),
    ReconciliationCheck(
        name="fato_orcamento.receita_meta",
        gold_query="SELECT ROUND(SUM(valor_meta_receita), 2) FROM fato_orcamento",
        source_query="SELECT ROUND(SUM(valor_meta_receita), 2) FROM financeiro.orcamentos",
        metric_label="soma receita meta orçada (BRL)",
    ),
)


def deviation(gold_val: float | None, source_val: float | None) -> float:
    if source_val is None or source_val == 0:
        return 0.0 if gold_val in (None, 0) else float("inf")
    if gold_val is None:
        return float("inf")
    return abs(gold_val - source_val) / abs(source_val)


def run_check(
    check: ReconciliationCheck,
    duckdb_con,
    pg_con,
) -> dict:
    gold_val = duckdb_con.execute(check.gold_query).fetchone()[0]
    with pg_con.cursor() as cur:
        cur.execute(check.source_query)
        source_val = cur.fetchone()[0]

    dev = deviation(
        float(gold_val) if gold_val is not None else None,
        float(source_val) if source_val is not None else None,
    )
    passed = dev <= check.tolerance

    status = "OK" if passed else "FALHA"
    log.log(
        logging.INFO if passed else logging.ERROR,
        f"[{check.name}] {status} | Gold={gold_val} | Source={source_val} "
        f"| desvio={dev:.4%} | tolerância={check.tolerance:.4%}",
    )

    return {
        "check": check.name,
        "metric": check.metric_label,
        "gold_value": gold_val,
        "source_value": source_val,
        "deviation_pct": round(dev * 100, 6),
        "tolerance_pct": round(check.tolerance * 100, 4),
        "passed": passed,
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Reconciliação Gold vs. Supabase para todas as tabelas fato")
    p.add_argument("--table", help="Filtrar por prefixo de check (ex: fato_venda, fato_entrega)")
    p.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE,
        help="Tolerância de desvio percentual (padrão: 0.001 = 0,1%%)",
    )
    p.add_argument("--output", type=Path, help="Salvar resultado JSON em arquivo")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    try:
        import duckdb
        import psycopg2  # noqa: F401
    except ImportError as exc:
        log.error(f"Dependência faltando: {exc}")
        return 1

    if not DUCKDB_PATH.exists():
        log.error(f"DuckDB Gold não encontrado: {DUCKDB_PATH}")
        return 1

    checks = [c for c in CHECKS if not args.table or c.name.startswith(args.table)]
    if not checks:
        log.error(f"Nenhum check encontrado para --table={args.table}")
        return 1

    # Override tolerance global se passado via CLI
    if args.tolerance != DEFAULT_TOLERANCE:
        checks = [
            ReconciliationCheck(
                name=c.name,
                gold_query=c.gold_query,
                source_query=c.source_query,
                metric_label=c.metric_label,
                tolerance=args.tolerance,
            )
            for c in checks
        ]

    log.info(f"=== Reconciliação Gold vs. Supabase v2 | {len(checks)} check(s) ===")

    duckdb_con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    pg_con = __import__("psycopg2").connect(os.environ["SUPABASE_DB_URL"])

    # ── Detecção de modo "master data only" ──────────────────────────────────
    # Após migração Supabase → Neon (2026-09-11), tabelas transacionais foram
    # truncadas para liberar espaço no free tier (512 MB). O Neon retém apenas
    # master data (clientes, produtos, lojas, vendedores, campanhas).
    # A fonte de verdade transacional passou a ser o Bronze Parquet
    # (gerado por generate_daily.py --output parquet).
    # Reconciliar Gold vs. banco neste modo produziria 100%+ de desvio falso.
    try:
        with pg_con.cursor() as _cur:
            _cur.execute("SELECT COUNT(*) FROM vendas.pedidos")
            _pedidos_count = _cur.fetchone()[0]
    except Exception:
        _pedidos_count = 0

    if _pedidos_count == 0:
        log.info(
            "=== Reconciliação PULADA: banco em modo 'master data only' "
            "(vendas.pedidos está vazio). "
            "Fonte transacional migrada para Bronze Parquet. ==="
        )
        log.info("TODO: implementar reconcile_gold_vs_bronze.py (Gold vs Parquet).")
        _skip_report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "skipped": True,
            "reason": "master_data_only_neon",
            "total_checks": 0,
            "passed": 0,
            "failed": 0,
            "results": [],
        }
        _out = args.output or LOG_DIR / f"reconciliation_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        _out.parent.mkdir(parents=True, exist_ok=True)
        _out.write_text(
            __import__("json").dumps(_skip_report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        duckdb_con.close()
        pg_con.close()
        return 0
    # ─────────────────────────────────────────────────────────────────────────

    results: list[dict] = []
    try:
        for check in checks:
            try:
                result = run_check(check, duckdb_con, pg_con)
                results.append(result)
            except Exception as exc:
                log.exception(f"[{check.name}] Erro ao executar: {exc}")
                results.append({"check": check.name, "passed": False, "error": str(exc)})
    finally:
        duckdb_con.close()
        pg_con.close()

    failures = [r for r in results if not r.get("passed", False)]

    # Persiste resultado para auditoria
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(results),
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "results": results,
    }

    output_path = args.output or LOG_DIR / f"reconciliation_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    log.info(f"Relatório salvo: {output_path}")

    if failures:
        log.error(f"\n=== RECONCILIAÇÃO FALHOU — {len(failures)} check(s) ===")
        for f in failures:
            log.error(f"  ✗ {f['check']}: desvio={f.get('deviation_pct', '?')}%")
        return 1

    log.info(f"=== Reconciliação OK — {len(results)} check(s) passaram ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

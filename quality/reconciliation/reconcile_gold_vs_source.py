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
    ReconciliationCheck(
        name="fato_venda.count",
        gold_query="SELECT COUNT(*) FROM fato_venda WHERE fl_troca_devolucao = FALSE",
        source_query="""
            SELECT COUNT(*) FROM vendas.itens_pedido ip
            JOIN vendas.pedidos p ON p.id_pedido = ip.id_pedido
            WHERE p.status NOT IN ('cancelado')
        """,
        metric_label="linhas fato_venda",
        tolerance=0.0,  # contagem deve ser exata
    ),
    ReconciliationCheck(
        name="fato_venda.valor_liquido",
        gold_query="SELECT ROUND(SUM(valor_liquido_item), 2) FROM fato_venda WHERE fl_troca_devolucao = FALSE",
        source_query="""
            SELECT ROUND(SUM(ip.valor_liquido_item), 2)
            FROM vendas.itens_pedido ip
            JOIN vendas.pedidos p ON p.id_pedido = ip.id_pedido
            WHERE p.status NOT IN ('cancelado')
        """,
        metric_label="soma valor_liquido_item (BRL)",
    ),
    ReconciliationCheck(
        name="fato_venda.margem_bruta",
        gold_query="SELECT ROUND(SUM(margem_bruta_item), 2) FROM fato_venda WHERE fl_troca_devolucao = FALSE",
        source_query="""
            SELECT ROUND(SUM(ip.valor_liquido_item - (ip.qtd_vendida * ip.custo_unitario)), 2)
            FROM vendas.itens_pedido ip
            JOIN vendas.pedidos p ON p.id_pedido = ip.id_pedido
            WHERE p.status NOT IN ('cancelado')
        """,
        metric_label="soma margem_bruta_item (BRL)",
    ),
    # ── fato_estoque ──────────────────────────────────────────────────────
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
    ReconciliationCheck(
        name="fato_estoque.valor_total",
        gold_query="""
            SELECT ROUND(SUM(valor_estoque_brl), 2) FROM fato_estoque
            WHERE sk_tempo = (SELECT MAX(sk_tempo) FROM fato_estoque)
        """,
        source_query="""
            SELECT ROUND(SUM(qtd_disponivel * custo_medio_unitario), 2)
            FROM estoque.saldo_estoque
            WHERE qtd_disponivel >= 0
        """,
        metric_label="valor total estoque (BRL)",
    ),
    # ── fato_entrega ──────────────────────────────────────────────────────
    ReconciliationCheck(
        name="fato_entrega.count",
        gold_query="SELECT COUNT(*) FROM fato_entrega",
        source_query="SELECT COUNT(*) FROM logistica.entregas",
        metric_label="linhas fato_entrega",
        tolerance=0.0,
    ),
    ReconciliationCheck(
        name="fato_entrega.custo_frete",
        gold_query="SELECT ROUND(SUM(custo_frete), 2) FROM fato_entrega",
        source_query="SELECT ROUND(SUM(custo_frete), 2) FROM logistica.entregas",
        metric_label="soma custo_frete (BRL)",
    ),
    # ── fato_financeiro ───────────────────────────────────────────────────
    ReconciliationCheck(
        name="fato_financeiro.count",
        gold_query="SELECT COUNT(*) FROM fato_financeiro",
        source_query="SELECT COUNT(*) FROM financeiro.lancamentos",
        metric_label="linhas fato_financeiro",
        tolerance=0.0,
    ),
    ReconciliationCheck(
        name="fato_financeiro.valor_liquido",
        gold_query="SELECT ROUND(SUM(valor_liquido), 2) FROM fato_financeiro",
        source_query="SELECT ROUND(SUM(valor_liquido), 2) FROM financeiro.lancamentos",
        metric_label="soma valor_liquido financeiro (BRL)",
    ),
    ReconciliationCheck(
        name="fato_financeiro.margem_bruta",
        gold_query="SELECT ROUND(SUM(margem_bruta), 2) FROM fato_financeiro WHERE tipo_lancamento = 'venda'",
        source_query="""
            SELECT ROUND(SUM(valor_liquido - cmv), 2)
            FROM financeiro.lancamentos
            WHERE tipo_lancamento = 'venda'
        """,
        metric_label="soma margem_bruta financeira (BRL)",
    ),
    # ── fato_cliente_interacao ────────────────────────────────────────────
    ReconciliationCheck(
        name="fato_cliente_interacao.count_sessoes",
        gold_query="""
            SELECT COUNT(*) FROM fato_cliente_interacao
            WHERE tipo_interacao IN ('visita_site', 'abandono_carrinho')
        """,
        source_query="SELECT COUNT(*) FROM web_analytics.sessoes",
        metric_label="linhas sessões em fato_cliente_interacao",
        tolerance=0.0,
    ),
    ReconciliationCheck(
        name="fato_cliente_interacao.count_eventos",
        gold_query="""
            SELECT COUNT(*) FROM fato_cliente_interacao
            WHERE tipo_interacao NOT IN ('visita_site', 'abandono_carrinho', 'compra', 'devolucao')
        """,
        source_query="""
            SELECT COUNT(*) FROM web_analytics.eventos_carrinho
            WHERE tipo_evento NOT IN ('purchase')
        """,
        metric_label="linhas eventos carrinho em fato_cliente_interacao",
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
        name="fato_orcamento.receita_orcada",
        gold_query="SELECT ROUND(SUM(receita_orcada_brl), 2) FROM fato_orcamento",
        source_query="SELECT ROUND(SUM(valor_receita_orcado), 2) FROM financeiro.orcamentos",
        metric_label="soma receita orçada (BRL)",
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
    p.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE,
                   help="Tolerância de desvio percentual (padrão: 0.001 = 0,1%%)")
    p.add_argument("--output", type=Path, help="Salvar resultado JSON em arquivo")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    try:
        import duckdb
        import psycopg2
    except ImportError as exc:
        log.error(f"Dependência faltando: {exc}")
        return 1

    if not DUCKDB_PATH.exists():
        log.error(f"DuckDB Gold não encontrado: {DUCKDB_PATH}")
        return 1

    checks = [
        c for c in CHECKS
        if not args.table or c.name.startswith(args.table)
    ]
    if not checks:
        log.error(f"Nenhum check encontrado para --table={args.table}")
        return 1

    # Override tolerance global se passado via CLI
    if args.tolerance != DEFAULT_TOLERANCE:
        checks = [ReconciliationCheck(
            name=c.name, gold_query=c.gold_query, source_query=c.source_query,
            metric_label=c.metric_label, tolerance=args.tolerance
        ) for c in checks]

    log.info(f"=== Reconciliação Gold vs. Supabase | {len(checks)} check(s) ===")

    duckdb_con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    pg_con = __import__("psycopg2").connect(os.environ["SUPABASE_DB_URL"])

    results: list[dict] = []
    try:
        for check in checks:
            try:
                result = run_check(check, duckdb_con, pg_con)
                results.append(result)
            except Exception as exc:
                log.error(f"[{check.name}] Erro ao executar: {exc}", exc_info=True)
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

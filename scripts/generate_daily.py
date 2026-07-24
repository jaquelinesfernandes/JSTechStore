#!/usr/bin/env python3
"""
Gerador de dados diários incrementais — JSTechStore Brasil.

Adiciona um dia de transações ao Supabase. Usado pelo pipeline GitHub Actions
para simular o OLTP diário antes da ingestão Bronze.

Pressupõe que os dados mestres já foram criados por generate_data.py.

Uso:
    python scripts/generate_daily.py --date today
    python scripts/generate_daily.py --date 2026-07-21
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# Adiciona o diretório scripts/ ao path para importar generate_data como módulo
sys.path.insert(0, str(Path(__file__).parent))
from faker import Faker  # noqa: E402
from generate_data import connect, gen_daily  # noqa: E402

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)


def load_context(conn) -> dict:
    """Carrega IDs dos dados mestres do Supabase para o contexto de geração."""
    ctx: dict = {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT p.id_produto, p.preco_venda, p.custo_unitario FROM produtos.precos p JOIN produtos.produtos pr ON pr.id_produto = p.id_produto WHERE pr.ativo = TRUE AND p.dt_vigencia_fim IS NULL"
        )
        ctx["produtos"] = [{"id": r[0], "preco": float(r[1]), "custo": float(r[2])} for r in cur.fetchall()]

        cur.execute("SELECT id_cliente FROM clientes.clientes WHERE ativo = TRUE")
        ctx["cliente_ids"] = [r[0] for r in cur.fetchall()]

        cur.execute("SELECT codigo, id_loja FROM rh.lojas")
        ctx["loja_ids"] = {r[0]: r[1] for r in cur.fetchall()}

        cur.execute("SELECT id_vendedor, id_loja FROM rh.vendedores WHERE ativo = TRUE")
        vend_by_loja: dict[int, list[int]] = {}
        for vid, lid in cur.fetchall():
            vend_by_loja.setdefault(lid, []).append(vid)
        ctx["vend_by_loja"] = vend_by_loja

        cur.execute("SELECT id_campanha, dt_inicio, dt_fim, tipo FROM marketing.campanhas WHERE ativo = TRUE")
        ctx["campanhas"] = [{"id": r[0], "dt_inicio": r[1], "dt_fim": r[2], "tipo": r[3]} for r in cur.fetchall()]

        cur.execute(
            "SELECT codigo, id_modalidade, id_transportadora, prazo_dias, frete_base FROM logistica.modalidades"
        )
        ctx["modalidades"] = {
            r[0]: {"id": r[1], "id_trans": r[2], "prazo": r[3], "frete": float(r[4])} for r in cur.fetchall()
        }
        ctx["trans_ids_by_modal"] = {k: v["id_trans"] for k, v in ctx["modalidades"].items()}

    if not ctx["produtos"]:
        log.error("Nenhum produto encontrado. Execute generate_data.py primeiro.")
        sys.exit(1)
    if not ctx["cliente_ids"]:
        log.error("Nenhum cliente encontrado. Execute generate_data.py primeiro.")
        sys.exit(1)

    log.info(
        f"Contexto carregado: {len(ctx['produtos'])} produtos, "
        f"{len(ctx['cliente_ids']):,} clientes, "
        f"{len(ctx['loja_ids'])} lojas"
    )
    return ctx


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Gerador de dados diários JSTechStore → Supabase")
    p.add_argument("--date", required=True, help="Data a gerar: 'today' ou YYYY-MM-DD")
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Semente fixa (default: derivada da data)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    target_date = datetime.now(tz=timezone.utc).date() if args.date == "today" else date.fromisoformat(args.date)

    # Semente derivada da data para resultados reprodutíveis por dia
    seed = args.seed if args.seed is not None else int(target_date.strftime("%Y%m%d"))
    rng = random.Random(seed)
    Faker.seed(seed)

    log.info(f"Gerando dados para {target_date} | seed={seed}")

    conn = connect()
    try:
        ctx = load_context(conn)
        gen_daily(conn, target_date, ctx, rng)
    except Exception:
        log.exception("Erro durante geração de dados diários.")
        return 1
    finally:
        conn.close()

    log.info(f"=== Dados do dia {target_date} gerados com sucesso! ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

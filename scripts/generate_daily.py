#!/usr/bin/env python3
"""
Gerador de dados diários incrementais — JSTechStore Brasil.

Adiciona um dia de transações ao Supabase. Usado pelo pipeline GitHub Actions
para simular o OLTP diário antes da ingestão Bronze.

Pressupõe que os dados mestres já foram criados por generate_data.py.

Uso:
    python scripts/generate_daily.py --date today
    python scripts/generate_daily.py --date 2026-07-21
    python scripts/generate_daily.py --date today --refresh-context  # força re-leitura do Supabase
"""

from __future__ import annotations

import argparse
import json
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

# Cache local: evita 5+ full table scans no Supabase por execução
_CONTEXT_CACHE_PATH = Path(__file__).parent.parent / "data" / ".context_cache.json"
_CONTEXT_CACHE_MAX_AGE_HOURS = 23  # renova uma vez por dia


def _serialize_ctx(ctx: dict) -> dict:
    """Converte datas para string antes de salvar em JSON."""
    result = {}
    for k, v in ctx.items():
        if isinstance(v, list):
            result[k] = [
                {kk: (vv.isoformat() if hasattr(vv, "isoformat") else vv) for kk, vv in item.items()}
                if isinstance(item, dict)
                else item
                for item in v
            ]
        elif isinstance(v, dict):
            result[k] = {
                dk: ({dkk: (dvv.isoformat() if hasattr(dvv, "isoformat") else dvv) for dkk, dvv in dv.items()} if isinstance(dv, dict) else dv)
                for dk, dv in v.items()
            }
        else:
            result[k] = v
    return result


def _load_context_from_cache() -> dict | None:
    if not _CONTEXT_CACHE_PATH.exists():
        return None
    try:
        raw = json.loads(_CONTEXT_CACHE_PATH.read_text(encoding="utf-8"))
        cached_at = datetime.fromisoformat(raw.pop("_cached_at"))
        age_hours = (datetime.now(timezone.utc) - cached_at).total_seconds() / 3600
        if age_hours > _CONTEXT_CACHE_MAX_AGE_HOURS:
            log.info(f"Cache de contexto expirado ({age_hours:.1f}h > {_CONTEXT_CACHE_MAX_AGE_HOURS}h) — re-lendo Supabase")
            return None
        log.info(f"Contexto carregado do cache local ({age_hours:.1f}h de idade) — IO Supabase economizado")
        return raw
    except Exception as exc:
        log.warning(f"Cache de contexto inválido ({exc}) — re-lendo Supabase")
        return None


def _save_context_to_cache(ctx: dict) -> None:
    _CONTEXT_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = _serialize_ctx(ctx)
    payload["_cached_at"] = datetime.now(timezone.utc).isoformat()
    _CONTEXT_CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"Contexto salvo em cache local: {_CONTEXT_CACHE_PATH}")


def load_context(conn, refresh: bool = False) -> dict:
    """Carrega IDs dos dados mestres. Usa cache local para reduzir Disk IO no Supabase."""
    if not refresh:
        cached = _load_context_from_cache()
        if cached is not None:
            return cached

    log.info("Carregando contexto do Supabase...")
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

    _save_context_to_cache(ctx)
    return ctx


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Gerador de dados diários JSTechStore → Supabase")
    p.add_argument("--date", required=True, help="Data a gerar: 'today' ou YYYY-MM-DD")
    p.add_argument("--seed", type=int, default=None, help="Semente fixa (default: derivada da data)")
    p.add_argument("--refresh-context", action="store_true", help="Força re-leitura do contexto do Supabase (ignora cache)")
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
        ctx = load_context(conn, refresh=args.refresh_context)
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

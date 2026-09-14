#!/usr/bin/env python3
"""
Gerador de dados diários incrementais — JSTechStore Brasil.

Dois modos de saída:
  --output supabase  (padrão legado) — insere no banco configurado em SUPABASE_DB_URL
  --output parquet   (recomendado)   — escreve direto no Bronze Parquet sem banco

O modo parquet é a solução definitiva para o Disk IO Budget do Supabase/Neon:
  - IDs gerenciados localmente em data/bronze/.sequences.json
  - Contexto carregado do cache JSON em vez de queries ao banco
  - dbt pipeline inalterado — lê Bronze Parquet normalmente

Uso:
    python scripts/generate_daily.py --date today --output parquet
    python scripts/generate_daily.py --date 2026-07-21 --output parquet
    python scripts/generate_daily.py --date today --output supabase  # legado
    python scripts/generate_daily.py --date today --refresh-context  # força re-leitura do banco
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

# Garante que tanto scripts/ (para generate_data) quanto a raiz do projeto
# (para o pacote ingestion.*) estejam no sys.path — necessário ao rodar o
# script diretamente (python scripts/generate_daily.py) sem PYTHONPATH.
_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))                   # raiz → ingestion.*
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))       # scripts/ → generate_data
import pandas as pd  # noqa: E402
from faker import Faker  # noqa: E402
from generate_data import (  # noqa: E402
    CANAIS,
    CANAIS_PESOS,
    METODOS_PAGAMENTO,
    MOTIVOS_DEVOLUCAO,
    connect,
    gen_daily,
    rand_ts,
    round2,
    seasonality_factor,
)

# Importados aqui (nível de módulo) para garantir resolução enquanto sys.path
# já está configurado — evita ambiguidade de escopo ao importar de dentro de função.
from ingestion.connectors.postgres.config import TABLES_BY_NAME  # noqa: E402
from ingestion.connectors.postgres.extract import write_parquet_atomic  # noqa: E402

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

# Cache local: evita 5+ full table scans no Supabase por execução
_CONTEXT_CACHE_PATH = Path(__file__).parent.parent / "data" / ".context_cache.json"
_CONTEXT_CACHE_MAX_AGE_HOURS = 23  # renova uma vez por dia

# Sequências locais para geração direta em Parquet (modo --output parquet)
# IDs começam em 10_000_000 — acima de qualquer SERIAL do Supabase após 3 anos (~3M max)
_SEQUENCES_PATH = Path(__file__).parent.parent / "data" / "bronze" / ".sequences.json"
_SEQ_START = 10_000_000


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
                dk: (
                    {dkk: (dvv.isoformat() if hasattr(dvv, "isoformat") else dvv) for dkk, dvv in dv.items()}
                    if isinstance(dv, dict)
                    else dv
                )
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
            log.info(
                f"Cache de contexto expirado ({age_hours:.1f}h > {_CONTEXT_CACHE_MAX_AGE_HOURS}h) — re-lendo Supabase"
            )
            return None
        log.info(f"Contexto carregado do cache local ({age_hours:.1f}h de idade) — IO Supabase economizado")
        return raw
    except Exception as exc:  # noqa: BLE001
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


# ─────────────────────────────────────────────────────────────────────────────
# Sequências locais — geração de IDs sem banco de dados
# ─────────────────────────────────────────────────────────────────────────────


def _deserialize_ctx(ctx: dict) -> dict:
    """Reconverte tipos do contexto após deserialização JSON (cache → Python)."""
    # Datas das campanhas: string ISO → date
    for c in ctx.get("campanhas", []):
        if isinstance(c.get("dt_inicio"), str):
            c["dt_inicio"] = date.fromisoformat(c["dt_inicio"])
        if isinstance(c.get("dt_fim"), str):
            c["dt_fim"] = date.fromisoformat(c["dt_fim"])
    # vend_by_loja: JSON serializa chaves int como string → restaurar int
    if ctx.get("vend_by_loja"):
        ctx["vend_by_loja"] = {int(k): v for k, v in ctx["vend_by_loja"].items()}
    return ctx


def _load_seqs() -> dict[str, int]:
    if not _SEQUENCES_PATH.exists():
        return {}
    return json.loads(_SEQUENCES_PATH.read_text(encoding="utf-8"))


def _save_seqs(seqs: dict[str, int]) -> None:
    _SEQUENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SEQUENCES_PATH.write_text(json.dumps(seqs, indent=2, ensure_ascii=False), encoding="utf-8")


def _alloc(seqs: dict, key: str, n: int) -> list[int]:
    """Aloca n IDs sequenciais para a chave dada e avança o contador."""
    start = seqs.get(key, _SEQ_START)
    seqs[key] = start + n
    return list(range(start, start + n))


# ─────────────────────────────────────────────────────────────────────────────
# Geração diária direta em Bronze Parquet (sem banco de dados)
# ─────────────────────────────────────────────────────────────────────────────

_BRONZE_PATH = Path(__file__).parent.parent / "data" / "bronze"


def _gen_saldo_estoque_snapshot(
    target_date: date,
    movs_rows: list[dict],
    rng: random.Random,
    ingested_at: datetime,
) -> list[dict]:
    """
    Gera snapshot diário de saldo_estoque aplicando as movimentações do dia.

    Lê o saldo mais recente do Bronze, aplica as saídas do dia (já computadas
    em movs_rows), gera reabastecimento quando necessário e retorna as linhas
    prontas para escrita em Parquet.

    Retorna lista vazia se não houver Parquet de saldo no Bronze (sem erro).
    """
    import glob as _glob

    # Encontra todos os Parquets reais de saldo_estoque (exclui stubs)
    parquet_files = sorted(
        f for f in _glob.glob(
            str(_BRONZE_PATH / "estoque" / "saldo_estoque" / "**" / "*.parquet"),
            recursive=True,
        )
        if "stub_empty" not in f
    )
    if not parquet_files:
        log.warning("saldo_estoque: nenhum Parquet Bronze encontrado — snapshot ignorado.")
        return []

    try:
        import duckdb as _duckdb
        df_saldo = _duckdb.connect().execute(
            f"""
            SELECT id_saldo, id_produto, id_loja,
                   qtd_disponivel, qtd_reservada, qtd_minima
            FROM read_parquet({parquet_files!r}, union_by_name := true)
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY id_produto, id_loja
                ORDER BY updated_at DESC
            ) = 1
            """
        ).df()
    except Exception as exc:
        log.warning(f"saldo_estoque: erro ao ler Bronze ({exc}) — snapshot ignorado.")
        return []

    # Agrega movimentações do dia por (id_produto, id_loja)
    movs_agg: dict[tuple[int, int], float] = {}
    for mov in movs_rows:
        key = (int(mov["id_produto"]), int(mov["id_loja"]))
        movs_agg[key] = movs_agg.get(key, 0.0) + float(mov["qtd"])

    snapshot_rows: list[dict] = []
    for _, r in df_saldo.iterrows():
        id_prod, id_loja = int(r["id_produto"]), int(r["id_loja"])
        qtd_disp  = int(r["qtd_disponivel"])
        qtd_min   = int(r["qtd_minima"])

        mov_net   = movs_agg.get((id_prod, id_loja), 0.0)
        saida     = abs(mov_net) if mov_net < 0 else 0.0
        entrada   = mov_net      if mov_net > 0 else 0.0

        pos_mov   = qtd_disp - int(saida) + int(entrada)
        restocking = 0
        if pos_mov < qtd_min:
            # Repõe automático: deixa 2× o mínimo com variação
            restocking = qtd_min * 2 + rng.randint(5, 30)
        elif rng.random() < 0.08:
            # ~8% de chance de reabastecimento de rotina
            restocking = rng.randint(5, 25)

        nova_qtd = max(0, pos_mov + restocking)

        snapshot_rows.append({
            "id_saldo":              int(r["id_saldo"]),
            "id_produto":            id_prod,
            "id_loja":               id_loja,
            "qtd_disponivel":        nova_qtd,
            "qtd_reservada":         int(r["qtd_reservada"]),
            "qtd_minima":            qtd_min,
            "dt_ultima_atualizacao": target_date,
            "updated_at":            ingested_at,
        })

    log.info(f"  [saldo_estoque] snapshot de {len(snapshot_rows)} linhas gerado para {target_date}")
    return snapshot_rows


def gen_daily_to_parquet(target_date: date, ctx: dict, rng: random.Random) -> None:
    """
    Replica a lógica de gen_daily() escrevendo direto em Bronze Parquet.

    IDs são alocados localmente via _SEQUENCES_PATH (persistido entre runs).
    O contexto (produtos, clientes, lojas) é lido do cache JSON — sem queries.
    Saída idêntica à do extrator Bronze: write_parquet_atomic() com metadados.
    """
    from datetime import timedelta

    ingested_at = datetime.now(timezone.utc)
    seqs = _load_seqs()

    produtos = ctx["produtos"]
    cliente_ids = ctx["cliente_ids"]
    loja_ids = ctx["loja_ids"]
    vend_by_loja = ctx["vend_by_loja"]
    campanhas = ctx["campanhas"]
    modalidades = ctx["modalidades"]

    lojas_fisicas_ids = [v for k, v in loja_ids.items() if k not in ("ECOM", "CD01")]
    id_loja_ecom = loja_ids.get("ECOM")
    id_loja_cd = loja_ids.get("CD01")

    campanhas_ativas = [c for c in campanhas if c["dt_inicio"] <= target_date <= c["dt_fim"]]
    id_campanha_ativa = campanhas_ativas[0]["id"] if campanhas_ativas else None

    n_orders = max(50, int(2000 * seasonality_factor(target_date, rng)))
    ped_ids = _alloc(seqs, "vendas__pedidos", n_orders)
    now_dt = rand_ts(target_date, rng)

    pedidos_rows: list[dict] = []
    itens_rows: list[dict] = []
    entregas_rows: list[dict] = []
    movs_rows: list[dict] = []
    lancamentos_rows: list[dict] = []
    parcelas_rows: list[dict] = []
    contas_rec_rows: list[dict] = []
    comissoes_rows: list[dict] = []
    sessoes_rows: list[dict] = []
    dev_rows: list[dict] = []
    lead_rows: list[dict] = []
    attr_rows: list[dict] = []

    for id_ped in ped_ids:
        canal = rng.choices(CANAIS, weights=CANAIS_PESOS, k=1)[0]
        is_online = canal != "loja_fisica"
        id_loja = id_loja_ecom if is_online else rng.choice(lojas_fisicas_ids)
        id_cliente = rng.choice(cliente_ids)
        dt_ped = rand_ts(target_date, rng)

        rand_status = rng.random()
        if rand_status < 0.03:
            status = "cancelado"
        elif rand_status < 0.05:
            status = "devolvido"
        else:
            status = (
                "entregue"
                if (datetime.now(tz=timezone.utc).date() - target_date).days > 7
                else rng.choice(["confirmado", "enviado", "entregue"])
            )

        n_itens = rng.choices([1, 2, 3, 4, 5, 6], weights=[30, 28, 20, 12, 7, 3], k=1)[0]
        prods_escolhidos = rng.sample(produtos, min(n_itens, len(produtos)))

        valor_bruto, valor_desconto = 0.0, 0.0
        itens_temp = []
        for prod in prods_escolhidos:
            qtd = rng.choices([1, 2, 3], weights=[70, 20, 10], k=1)[0]
            preco = prod["preco"] * (1 + rng.uniform(-0.05, 0.05))
            custo = prod["custo"]
            desc_pct = rng.uniform(0, 0.15) if canal.startswith("marketplace") else rng.uniform(0, 0.08)
            desconto = round2(preco * qtd * desc_pct)
            liq_item = round2(preco * qtd - desconto)
            valor_bruto += round2(preco * qtd)
            valor_desconto += desconto
            itens_temp.append({
                "id_produto": prod["id"],
                "qtd_vendida": qtd,
                "preco_unitario": round2(preco),
                "custo_unitario": round2(custo),
                "desconto_item": desconto,
                "valor_liquido_item": liq_item,
                "updated_at": dt_ped,
            })

        frete = 0.0 if not is_online or rng.random() < 0.3 else round2(rng.uniform(8, 35))
        valor_liquido = round2(valor_bruto - valor_desconto + frete)
        parcelas_n = rng.choices([1, 2, 3, 6, 10, 12], weights=[35, 15, 15, 15, 10, 10], k=1)[0]

        pedidos_rows.append({
            "id_pedido": id_ped,
            "id_cliente": id_cliente,
            "id_loja": id_loja,
            "canal_venda": canal,
            "status": status,
            "dt_pedido": dt_ped,
            "dt_confirmacao": dt_ped if status != "cancelado" else None,
            "dt_cancelamento": dt_ped if status == "cancelado" else None,
            "valor_bruto": round2(valor_bruto),
            "valor_desconto": round2(valor_desconto),
            "valor_frete": frete,
            "valor_liquido": valor_liquido,
            "parcelas": parcelas_n,
            "metodo_pagamento": rng.choice(METODOS_PAGAMENTO),
            "cupom": f"CUPOM{rng.randint(100, 999)}" if rng.random() < 0.1 else None,
            "id_campanha": id_campanha_ativa if rng.random() < 0.3 else None,
            "created_at": dt_ped,
            "updated_at": dt_ped,
        })

        # Itens
        for it in itens_temp:
            itens_rows.append({"id_item_pedido": _alloc(seqs, "vendas__itens_pedido", 1)[0],
                                "id_pedido": id_ped, **it})

        # Entrega
        if status != "cancelado" and canal != "loja_fisica":
            modal_key = "ML_ENV" if canal.startswith("marketplace_ml") else rng.choice(
                ["SEDEX", "PAC", "JADLOG_E", "JADLOG_E2", "ML_ENV"])
            modal = modalidades[modal_key]
            dt_post = target_date + timedelta(days=1)
            dt_prom = dt_post + timedelta(days=modal["prazo"] + rng.randint(-1, 2))
            entregue = status == "entregue"
            dt_ef = dt_prom + timedelta(days=rng.randint(-1, 3)) if entregue else None
            entregas_rows.append({
                "id_entrega": _alloc(seqs, "logistica__entregas", 1)[0],
                "id_pedido": id_ped,
                "id_transportadora": modal["id_trans"],
                "id_modalidade": modal["id"],
                "id_loja_origem": id_loja_ecom or id_loja,
                "codigo_rastreio": f"BR{rng.randint(100000000, 999999999)}BR",
                "dt_postagem": dt_post,
                "dt_promessa": dt_prom,
                "dt_efetiva": dt_ef,
                "fl_sla_atendido": (dt_ef <= dt_prom) if dt_ef else None,
                "status": "entregue" if entregue else "em_transito",
                "updated_at": dt_ped,
            })

        # Movimentações estoque
        if status != "cancelado":
            id_loja_estoque = id_loja if id_loja != id_loja_ecom else id_loja_cd
            for it in itens_temp:
                movs_rows.append({
                    "id_movimentacao": _alloc(seqs, "estoque__movimentacoes", 1)[0],
                    "id_produto": it["id_produto"],
                    "id_loja": id_loja_estoque,
                    "tipo_mov": "saida",
                    "qtd": -it["qtd_vendida"],
                    "dt_movimentacao": dt_ped,
                    "id_pedido": id_ped,
                    "custo_unitario": it["custo_unitario"],
                    "observacao": f"Venda pedido #{id_ped}",
                    "updated_at": dt_ped,
                })

        # Financeiro
        if status != "cancelado":
            id_lanc = _alloc(seqs, "financeiro__lancamentos", 1)[0]
            lancamentos_rows.append({
                "id_lancamento": id_lanc,
                "id_pedido": id_ped,
                "id_loja": id_loja,
                "tipo": "receita",
                "valor": valor_liquido,
                "dt_lancamento": target_date,
                "dt_competencia": target_date,
                "descricao": f"Venda pedido #{id_ped} via {canal}",
                "updated_at": dt_ped,
            })
            val_parc = round2(valor_liquido / parcelas_n)
            for n in range(1, parcelas_n + 1):
                dt_venc = target_date + timedelta(days=30 * n)
                dt_pag = dt_venc - timedelta(days=rng.randint(0, 5)) if rng.random() < 0.75 else None
                parcelas_rows.append({
                    "id_parcela": _alloc(seqs, "financeiro__parcelas", 1)[0],
                    "id_lancamento": id_lanc,
                    "numero_parcela": n,
                    "valor_parcela": val_parc,
                    "dt_vencimento": dt_venc,
                    "dt_pagamento": dt_pag,
                    "status": "pago" if dt_pag else "pendente",
                    "updated_at": now_dt,
                })
            dt_venc_cr = target_date + timedelta(days=rng.randint(1, parcelas_n * 30))
            dt_pag_cr = dt_venc_cr - timedelta(days=rng.randint(0, 3)) if status == "entregue" else None
            contas_rec_rows.append({
                "id_conta": _alloc(seqs, "financeiro__contas_receber", 1)[0],
                "id_pedido": id_ped,
                "valor_original": valor_liquido,
                "valor_pago": valor_liquido if dt_pag_cr else 0,
                "dt_vencimento": dt_venc_cr,
                "dt_pagamento": dt_pag_cr,
                "status": "pago" if dt_pag_cr else "pendente",
                "updated_at": dt_ped,
            })

        # Comissão
        if canal == "loja_fisica" and status != "cancelado":
            vendedores = vend_by_loja.get(id_loja, [])
            if vendedores:
                pct = rng.uniform(0.012, 0.025)
                comissoes_rows.append({
                    "id_comissao": _alloc(seqs, "rh__comissoes", 1)[0],
                    "id_vendedor": rng.choice(vendedores),
                    "id_pedido": id_ped,
                    "valor_venda": valor_liquido,
                    "percentual_comissao": round2(pct),
                    "valor_comissao": round2(valor_liquido * pct),
                    "dt_competencia": target_date,
                    "status": "pendente",
                    "updated_at": dt_ped,
                })

        # Web analytics — sessão convertida
        if canal != "loja_fisica":
            dt_ini = dt_ped - timedelta(minutes=rng.randint(5, 40))
            sessoes_rows.append({
                "id_sessao": _alloc(seqs, "web_analytics__sessoes", 1)[0],
                "id_cliente": id_cliente,
                "canal_origem": canal if "marketplace" not in canal else "marketplace",
                "device_type": rng.choice(["desktop", "mobile", "mobile", "tablet"]),
                "dt_inicio": dt_ini,
                "dt_fim": dt_ped + timedelta(minutes=rng.randint(1, 15)),
                "paginas_visitadas": rng.randint(3, 20),
                "converteu": status != "cancelado",
                "id_pedido": id_ped if status != "cancelado" else None,
                "updated_at": dt_ped,
            })

        # Devoluções
        if status == "devolvido" and itens_temp:
            item = rng.choice(itens_temp)
            dev_rows.append({
                "id_devolucao": _alloc(seqs, "vendas__devolucoes", 1)[0],
                "id_pedido": id_ped,
                "id_produto": item["id_produto"],
                "dt_devolucao": target_date + timedelta(days=rng.randint(5, 30)),
                "motivo": rng.choice(MOTIVOS_DEVOLUCAO),
                "qtd_devolvida": item["qtd_vendida"],
                "valor_devolvido": item["valor_liquido_item"],
                "status": "aprovada",
                "updated_at": now_dt,
            })

    # Sessões sem conversão (~7× online orders)
    n_online = sum(1 for p in pedidos_rows if p["canal_venda"] != "loja_fisica")
    for _ in range(n_online * 7):
        dt_ini = rand_ts(target_date, rng)
        sessoes_rows.append({
            "id_sessao": _alloc(seqs, "web_analytics__sessoes", 1)[0],
            "id_cliente": rng.choice(cliente_ids) if rng.random() < 0.4 else None,
            "canal_origem": rng.choice(["organico", "search", "social", "email", "direto"]),
            "device_type": rng.choice(["desktop", "mobile", "mobile", "tablet"]),
            "dt_inicio": dt_ini,
            "dt_fim": dt_ini + timedelta(minutes=rng.randint(1, 30)),
            "paginas_visitadas": rng.randint(1, 8),
            "converteu": False,
            "id_pedido": None,
            "updated_at": dt_ini,
        })

    # Eventos de carrinho (sessões convertidas)
    eventos_rows: list[dict] = []
    for sess in sessoes_rows:
        if not sess["converteu"]:
            continue
        prods_ev = rng.sample(produtos, min(rng.randint(1, 4), len(produtos)))
        for prod in prods_ev:
            eventos_rows.append({
                "id_evento": _alloc(seqs, "web_analytics__eventos_carrinho", 1)[0],
                "id_sessao": sess["id_sessao"],
                "id_produto": prod["id"],
                "tipo_evento": "add_to_cart",
                "dt_evento": sess["dt_inicio"],
                "qtd": 1,
                "preco_na_epoca": prod["preco"],
                "updated_at": sess["updated_at"],
            })
        eventos_rows.append({
            "id_evento": _alloc(seqs, "web_analytics__eventos_carrinho", 1)[0],
            "id_sessao": sess["id_sessao"],
            "id_produto": rng.choice(prods_ev)["id"],
            "tipo_evento": "purchase",
            "dt_evento": sess["dt_fim"],
            "qtd": 1,
            "preco_na_epoca": rng.choice(prods_ev)["preco"],
            "updated_at": sess["updated_at"],
        })

    # Leads + atribuição de campanha
    if campanhas_ativas:
        for _ in range(rng.randint(50, 300)):
            camp = rng.choice(campanhas_ativas)
            lead_rows.append({
                "id_lead": _alloc(seqs, "marketing__leads", 1)[0],
                "id_campanha": camp["id"],
                "id_cliente": rng.choice(cliente_ids) if rng.random() < 0.5 else None,
                "canal": rng.choice(["email", "social", "search", "display"]),
                "dt_lead": target_date,
                "convertido": rng.random() < 0.05,
                "updated_at": now_dt,
            })
        for ped in pedidos_rows:
            if ped.get("id_campanha") and ped["status"] != "cancelado":
                attr_rows.append({
                    "id_atribuicao": _alloc(seqs, "marketing__atribuicao", 1)[0],
                    "id_pedido": ped["id_pedido"],
                    "id_campanha": ped["id_campanha"],
                    "canal_atribuicao": ped["canal_venda"],
                    "tipo_atribuicao": "last_click",
                    "peso": 1.0,
                    "updated_at": now_dt,
                })

    # Persiste sequências ANTES de escrever Parquet (atômico em caso de falha parcial)
    _save_seqs(seqs)

    # ── Snapshot diário de saldo_estoque ─────────────────────────────────────
    saldo_rows = _gen_saldo_estoque_snapshot(target_date, movs_rows, rng, ingested_at)

    # ── Escreve em Parquet ────────────────────────────────────────────────────
    batches = [
        ("vendas.pedidos",                  pedidos_rows),
        ("vendas.itens_pedido",             itens_rows),
        ("vendas.devolucoes",               dev_rows),
        ("logistica.entregas",              entregas_rows),
        ("estoque.movimentacoes",           movs_rows),
        ("estoque.saldo_estoque",           saldo_rows),
        ("financeiro.lancamentos",          lancamentos_rows),
        ("financeiro.parcelas",             parcelas_rows),
        ("financeiro.contas_receber",       contas_rec_rows),
        ("rh.comissoes",                    comissoes_rows),
        ("web_analytics.sessoes",           sessoes_rows),
        ("web_analytics.eventos_carrinho",  eventos_rows),
        ("marketing.leads",                 lead_rows),
        ("marketing.atribuicao",            attr_rows),
    ]

    total = 0
    for table_name, rows in batches:
        if not rows:
            continue
        df = pd.DataFrame(rows)
        path = write_parquet_atomic(df, TABLES_BY_NAME[table_name], ingested_at)
        total += len(rows)
        log.info(f"  [{table_name}] {len(rows):,} linhas → {path.name}")

    log.info(f"=== gen_daily_to_parquet: {total:,} linhas | {target_date} ===")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Gerador de dados diários JSTechStore → Supabase")
    p.add_argument("--date", required=True, help="Data a gerar: 'today' ou YYYY-MM-DD")
    p.add_argument("--seed", type=int, default=None, help="Semente fixa (default: derivada da data)")
    p.add_argument(
        "--refresh-context", action="store_true", help="Força re-leitura do contexto do Supabase (ignora cache)"
    )
    p.add_argument(
        "--output",
        choices=["supabase", "parquet"],
        default="parquet",
        help="Destino da geração: 'parquet' (recomendado, zero IO banco) ou 'supabase' (legado)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    target_date = datetime.now(tz=timezone.utc).date() if args.date == "today" else date.fromisoformat(args.date)

    # Semente derivada da data para resultados reprodutíveis por dia
    seed = args.seed if args.seed is not None else int(target_date.strftime("%Y%m%d"))
    rng = random.Random(seed)
    Faker.seed(seed)

    log.info(f"Gerando dados para {target_date} | seed={seed} | output={args.output}")

    if args.output == "parquet":
        # Modo recomendado: zero IO banco, IDs locais, escreve direto em Bronze Parquet
        conn = connect()
        try:
            ctx = load_context(conn, refresh=args.refresh_context)
            ctx = _deserialize_ctx(ctx)
        except Exception:
            log.exception("Erro ao carregar contexto do banco.")
            return 1
        finally:
            conn.close()

        try:
            gen_daily_to_parquet(target_date, ctx, rng)
        except Exception:
            log.exception("Erro durante geração de dados diários para Parquet.")
            return 1
    else:
        # Modo legado: INSERT direto no Supabase / Neon (master data only)
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

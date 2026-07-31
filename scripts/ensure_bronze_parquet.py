"""
Cria Parquet stubs vazios para tabelas Bronze ausentes no GitHub Actions.

Roda ANTES do `dbt run`. Garante que read_parquet() nunca falhe com
"No files found" para tabelas estáticas que não existem no runner GHA.
O stub tem 0 linhas e o schema correto — dbt processa normalmente e
retorna 0 atualizações para o Gold (dados existentes preservados).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BRONZE_PATH = Path(os.getenv("BRONZE_PATH", "data/bronze"))

# Colunas que cada stg_ model referencia via SELECT *
# Inclui colunas de metadados adicionadas pelo extractor
_META = ["_source_schema", "_source_table", "_ingested_at", "_row_count_batch"]

STATIC_TABLES: dict[str, list[str]] = {
    "clientes/clientes": [
        "id_cliente", "cpf", "email", "telefone", "primeiro_nome", "nome_completo",
        "cep", "cidade", "uf", "data_cadastro", "canal_origem", "nivel_fidelidade",
        "ativo", "created_at", "updated_at",
    ],
    "clientes/enderecos": [
        "id_endereco", "id_cliente", "logradouro", "numero", "complemento",
        "bairro", "cep", "cidade", "uf", "tipo", "updated_at",
    ],
    "clientes/techpoints": [
        "id_techpoints", "id_cliente", "pontos_acumulados", "pontos_resgatados",
        "saldo_pontos", "nivel_fidelidade", "updated_at",
    ],
    "estoque/saldo_estoque": [
        "id_saldo", "id_produto", "id_loja", "qtd_disponivel", "qtd_reservada",
        "qtd_minima", "dt_ultima_atualizacao", "updated_at",
    ],
    "financeiro/orcamentos": [
        "id_orcamento", "id_loja", "canal_venda", "ano", "mes",
        "valor_meta_receita", "valor_meta_margem", "qtd_meta_pedidos", "updated_at",
    ],
    "logistica/modalidades": [
        "id_modalidade", "id_transportadora", "nome", "codigo",
        "prazo_dias", "frete_base", "tipo", "updated_at",
    ],
    "logistica/transportadoras": [
        "id_transportadora", "nome", "cnpj", "prazo_dias_min", "prazo_dias_max",
        "ativo", "updated_at",
    ],
    "marketing/campanhas": [
        "id_campanha", "nome", "tipo", "canal", "dt_inicio", "dt_fim",
        "orcamento", "objetivo", "ativo", "updated_at",
    ],
    "produtos/categorias": ["id_categoria", "nome", "subcategoria", "updated_at"],
    "produtos/fornecedores": [
        "id_fornecedor", "nome_fornecedor", "cnpj", "categoria_principal",
        "pais_origem", "prazo_entrega_dias", "ativo", "updated_at",
    ],
    "produtos/precos": [
        "id_preco", "id_produto", "preco_venda", "custo_unitario",
        "dt_vigencia_inicio", "dt_vigencia_fim", "updated_at",
    ],
    "produtos/produtos": [
        "id_produto", "id_categoria", "id_fornecedor", "sku", "nome", "marca",
        "peso_kg", "ativo", "created_at", "updated_at",
    ],
    "rh/lojas": [
        "id_loja", "codigo", "nome_loja", "tipo_loja", "regiao", "cidade",
        "uf", "gerente", "capacidade_m2", "dt_abertura", "ativo", "updated_at",
    ],
    "rh/metas": [
        "id_meta", "id_vendedor", "ano", "mes", "meta_valor",
        "meta_qtd_pedidos", "updated_at",
    ],
    "rh/vendedores": [
        "id_vendedor", "id_loja", "nome", "cpf", "email", "cargo",
        "data_admissao", "ativo", "updated_at",
    ],
}


def _has_parquet(table_path: Path) -> bool:
    return table_path.exists() and any(table_path.rglob("*.parquet"))


def create_stub(schema_table: str, columns: list[str]) -> None:
    table_dir = BRONZE_PATH / schema_table
    if _has_parquet(table_dir):
        log.info(f"[{schema_table}] Parquet existe — nenhuma ação necessária")
        return

    now = datetime.now(timezone.utc)
    dest = table_dir / f"year={now.year}" / f"month={now.month:02d}" / f"day={now.day:02d}"
    dest.mkdir(parents=True, exist_ok=True)

    stub_path = dest / "stub_empty.parquet"
    df = pd.DataFrame(columns=columns + _META)
    df.to_parquet(stub_path, index=False, engine="pyarrow", compression="snappy")
    log.info(f"[{schema_table}] Stub criado: {stub_path}")


def main() -> None:
    log.info(f"Bronze path: {BRONZE_PATH.resolve()}")
    created = 0
    for schema_table, cols in STATIC_TABLES.items():
        table_dir = BRONZE_PATH / schema_table
        if not _has_parquet(table_dir):
            create_stub(schema_table, cols)
            created += 1
    log.info(f"=== ensure_bronze_parquet: {created}/{len(STATIC_TABLES)} stubs criados ===")


if __name__ == "__main__":
    main()

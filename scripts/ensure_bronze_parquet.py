"""
Garante que todas as tabelas Bronze esperadas têm pelo menos um arquivo Parquet
antes do dbt run. Para tabelas ausentes, cria stubs vazios com o schema correto.

Roda com `if: always()` no pipeline, imediatamente antes do dbt run.
Sai com código 1 se alguma tabela ainda estiver ausente após a tentativa de stub —
isso falha o pipeline ANTES do dbt com mensagem clara, evitando erros obscuros de
"No files found" dentro do dbt.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

BRONZE_PATH = Path(os.getenv("BRONZE_PATH", "data/bronze"))
GITHUB_STEP_SUMMARY = Path(os.getenv("GITHUB_STEP_SUMMARY", "/dev/null"))

_META = ["_source_schema", "_source_table", "_ingested_at", "_row_count_batch"]

# Todas as tabelas estáticas/de lookup que não recebem dados diários do generate_daily.py.
# Cada entrada mapeia "schema/table" → lista de colunas (sem _META).
STATIC_TABLES: dict[str, list[str]] = {
    "clientes/clientes": [
        "id_cliente",
        "cpf",
        "email",
        "telefone",
        "primeiro_nome",
        "nome_completo",
        "cep",
        "cidade",
        "uf",
        "data_cadastro",
        "canal_origem",
        "nivel_fidelidade",
        "ativo",
        "created_at",
        "updated_at",
    ],
    "clientes/enderecos": [
        "id_endereco",
        "id_cliente",
        "logradouro",
        "numero",
        "complemento",
        "bairro",
        "cep",
        "cidade",
        "uf",
        "tipo",
        "updated_at",
    ],
    "clientes/techpoints": [
        "id_techpoints",
        "id_cliente",
        "pontos_acumulados",
        "pontos_resgatados",
        "saldo_pontos",
        "nivel_fidelidade",
        "updated_at",
    ],
    "estoque/saldo_estoque": [
        "id_saldo",
        "id_produto",
        "id_loja",
        "qtd_disponivel",
        "qtd_reservada",
        "qtd_minima",
        "dt_ultima_atualizacao",
        "updated_at",
    ],
    "financeiro/orcamentos": [
        "id_orcamento",
        "id_loja",
        "canal_venda",
        "ano",
        "mes",
        "valor_meta_receita",
        "valor_meta_margem",
        "qtd_meta_pedidos",
        "updated_at",
    ],
    "logistica/modalidades": [
        "id_modalidade",
        "id_transportadora",
        "nome",
        "codigo",
        "prazo_dias",
        "frete_base",
        "tipo",
        "updated_at",
    ],
    "logistica/transportadoras": [
        "id_transportadora",
        "nome",
        "cnpj",
        "prazo_dias_min",
        "prazo_dias_max",
        "ativo",
        "updated_at",
    ],
    "marketing/campanhas": [
        "id_campanha",
        "nome",
        "tipo",
        "canal",
        "dt_inicio",
        "dt_fim",
        "orcamento",
        "objetivo",
        "ativo",
        "updated_at",
    ],
    "produtos/categorias": ["id_categoria", "nome", "subcategoria", "updated_at"],
    "produtos/fornecedores": [
        "id_fornecedor",
        "nome_fornecedor",
        "cnpj",
        "categoria_principal",
        "pais_origem",
        "prazo_entrega_dias",
        "ativo",
        "updated_at",
    ],
    "produtos/precos": [
        "id_preco",
        "id_produto",
        "preco_venda",
        "custo_unitario",
        "dt_vigencia_inicio",
        "dt_vigencia_fim",
        "updated_at",
    ],
    "produtos/produtos": [
        "id_produto",
        "id_categoria",
        "id_fornecedor",
        "sku",
        "nome",
        "marca",
        "peso_kg",
        "ativo",
        "created_at",
        "updated_at",
    ],
    "rh/lojas": [
        "id_loja",
        "codigo",
        "nome_loja",
        "tipo_loja",
        "regiao",
        "cidade",
        "uf",
        "gerente",
        "capacidade_m2",
        "dt_abertura",
        "ativo",
        "updated_at",
    ],
    "rh/metas": [
        "id_meta",
        "id_vendedor",
        "ano",
        "mes",
        "meta_valor",
        "meta_qtd_pedidos",
        "updated_at",
    ],
    "rh/vendedores": [
        "id_vendedor",
        "id_loja",
        "nome",
        "cpf",
        "email",
        "cargo",
        "data_admissao",
        "ativo",
        "updated_at",
    ],
}


def _has_parquet(table_path: Path) -> bool:
    return table_path.exists() and any(table_path.rglob("*.parquet"))


def _create_stub(schema_table: str, columns: list[str]) -> Path:
    now = datetime.now(timezone.utc)
    dest = BRONZE_PATH / schema_table / f"year={now.year}" / f"month={now.month:02d}" / f"day={now.day:02d}"
    dest.mkdir(parents=True, exist_ok=True)
    stub_path = dest / "stub_empty.parquet"
    df = pd.DataFrame(columns=columns + _META)
    df.to_parquet(stub_path, index=False, engine="pyarrow", compression="snappy")
    return stub_path


def _write_summary(rows: list[tuple[str, str, str]]) -> None:
    """Escreve tabela de status no GitHub Actions Step Summary."""
    if not GITHUB_STEP_SUMMARY.name or GITHUB_STEP_SUMMARY.name == "/dev/null":
        return
    lines = [
        "## Bronze Parquet — pré-dbt validate\n",
        "| Tabela | Status | Detalhe |\n",
        "|--------|--------|---------|\n",
    ]
    for table, status, detail in rows:
        lines.append(f"| `{table}` | {status} | {detail} |\n")
    try:
        with GITHUB_STEP_SUMMARY.open("a", encoding="utf-8") as f:
            f.writelines(lines)
    except OSError:
        pass


def main() -> int:
    log.info(f"=== ensure_bronze_parquet | Bronze: {BRONZE_PATH.resolve()} ===")

    summary_rows: list[tuple[str, str, str]] = []
    stubs_created: list[str] = []
    already_ok: list[str] = []
    failures: list[str] = []

    # Fase 1 — criar stubs para tabelas sem Parquet
    for schema_table, cols in STATIC_TABLES.items():
        table_dir = BRONZE_PATH / schema_table
        if _has_parquet(table_dir):
            already_ok.append(schema_table)
        else:
            try:
                stub_path = _create_stub(schema_table, cols)
                stubs_created.append(schema_table)
                log.info(f"[STUB] {schema_table} → {stub_path}")
            except Exception as exc:  # noqa: BLE001
                failures.append(schema_table)
                log.error(f"[ERRO] {schema_table} — falha ao criar stub: {exc}")

    # Fase 2 — validação pós-stub: confirma que TODOS têm Parquet agora
    log.info("--- Validação pós-stub ---")
    still_missing: list[str] = []
    for schema_table in STATIC_TABLES:
        table_dir = BRONZE_PATH / schema_table
        if _has_parquet(table_dir):
            files = list(table_dir.rglob("*.parquet"))
            if schema_table in stubs_created:
                status, detail = "🟡 STUB", f"{len(files)} stub(s) vazio(s)"
                log.info(f"[OK-STUB] {schema_table} — {detail}")
            else:
                status, detail = "✅ OK", f"{len(files)} arquivo(s) real(is)"
                log.info(f"[OK] {schema_table} — {detail}")
            summary_rows.append((schema_table, status, detail))
        else:
            still_missing.append(schema_table)
            status, detail = "❌ AUSENTE", "sem Parquet após tentativa de stub"
            log.error(f"[MISSING] {schema_table} — {detail}")
            summary_rows.append((schema_table, status, detail))

    # Relatório
    log.info(
        f"=== Resultado: {len(already_ok)} OK | {len(stubs_created)} stubs criados | {len(still_missing)} ausentes ==="
    )
    _write_summary(summary_rows)

    if still_missing:
        log.error("FALHA — as seguintes tabelas ainda não têm Parquet:")
        for t in still_missing:
            log.error(f"  ✗ {BRONZE_PATH / t}/**/*.parquet")
        log.error("Verifique: permissão de escrita no runner, espaço em disco, ou erro acima.")
        return 1

    log.info("Todas as tabelas estáticas têm Parquet — dbt pode prosseguir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

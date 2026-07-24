"""
Mapeamento de todas as tabelas Supabase para ingestão Bronze.

Cada entrada define:
  - schema / table: localização no PostgreSQL
  - watermark_col: coluna de controle incremental (sempre updated_at)
  - natural_key: coluna(s) que identificam unicamente o registro (usada pelo dbt)

Nota: todos os dados são sintéticos (gerados por Faker com locale pt_BR).
CPF, e-mail e telefone são fictícios por natureza — nenhuma pseudonimização
adicional é aplicada na ingestão.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TableConfig:
    schema: str
    table: str
    watermark_col: str = "updated_at"
    natural_key: tuple[str, ...] = field(default_factory=tuple)

    @property
    def full_name(self) -> str:
        return f"{self.schema}.{self.table}"

    @property
    def watermark_key(self) -> str:
        return f"{self.schema}__{self.table}"


TABLES: tuple[TableConfig, ...] = (
    # ── vendas ────────────────────────────────────────────────────────────
    TableConfig(schema="vendas", table="pedidos", natural_key=("id_pedido",)),
    TableConfig(schema="vendas", table="itens_pedido", natural_key=("id_item_pedido",)),
    TableConfig(schema="vendas", table="devolucoes", natural_key=("id_devolucao",)),
    # ── clientes ──────────────────────────────────────────────────────────
    TableConfig(schema="clientes", table="clientes", natural_key=("id_cliente",)),
    TableConfig(schema="clientes", table="enderecos", natural_key=("id_endereco",)),
    TableConfig(schema="clientes", table="techpoints", natural_key=("id_techpoints",)),
    # ── produtos ──────────────────────────────────────────────────────────
    TableConfig(schema="produtos", table="produtos", natural_key=("id_produto",)),
    TableConfig(schema="produtos", table="categorias", natural_key=("id_categoria",)),
    TableConfig(schema="produtos", table="fornecedores", natural_key=("id_fornecedor",)),
    TableConfig(
        schema="produtos",
        table="precos",
        natural_key=("id_produto", "dt_vigencia_inicio"),
    ),
    # ── estoque ───────────────────────────────────────────────────────────
    TableConfig(schema="estoque", table="saldo_estoque", natural_key=("id_produto", "id_loja")),
    TableConfig(schema="estoque", table="movimentacoes", natural_key=("id_movimentacao",)),
    # ── logistica ─────────────────────────────────────────────────────────
    TableConfig(schema="logistica", table="entregas", natural_key=("id_entrega",)),
    TableConfig(schema="logistica", table="transportadoras", natural_key=("id_transportadora",)),
    TableConfig(schema="logistica", table="modalidades", natural_key=("id_modalidade",)),
    # ── financeiro ────────────────────────────────────────────────────────
    TableConfig(schema="financeiro", table="lancamentos", natural_key=("id_lancamento",)),
    TableConfig(schema="financeiro", table="parcelas", natural_key=("id_parcela",)),
    TableConfig(schema="financeiro", table="contas_receber", natural_key=("id_conta",)),
    TableConfig(schema="financeiro", table="orcamentos", natural_key=("id_orcamento",)),
    # ── marketing ─────────────────────────────────────────────────────────
    TableConfig(schema="marketing", table="campanhas", natural_key=("id_campanha",)),
    TableConfig(schema="marketing", table="leads", natural_key=("id_lead",)),
    TableConfig(schema="marketing", table="atribuicao", natural_key=("id_atribuicao",)),
    # ── rh ────────────────────────────────────────────────────────────────
    TableConfig(schema="rh", table="lojas", natural_key=("id_loja",)),
    TableConfig(schema="rh", table="vendedores", natural_key=("id_vendedor",)),
    TableConfig(schema="rh", table="metas", natural_key=("id_meta",)),
    TableConfig(schema="rh", table="comissoes", natural_key=("id_comissao",)),
    # ── web_analytics ─────────────────────────────────────────────────────
    TableConfig(schema="web_analytics", table="sessoes", natural_key=("id_sessao",)),
    TableConfig(schema="web_analytics", table="eventos_carrinho", natural_key=("id_evento",)),
)

# Índice por nome completo para lookup O(1)
TABLES_BY_NAME: dict[str, TableConfig] = {t.full_name: t for t in TABLES}

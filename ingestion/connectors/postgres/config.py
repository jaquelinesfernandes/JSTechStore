"""
Mapeamento de todas as tabelas Supabase para ingestão Bronze.

Cada entrada define:
  - schema / table: localização no PostgreSQL
  - watermark_col: coluna de controle incremental (sempre updated_at)
  - pii_cols: colunas que recebem HMAC-SHA256 antes da escrita no Parquet
  - natural_key: coluna(s) que identificam unicamente o registro (usada pelo dbt)
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TableConfig:
    schema: str
    table: str
    watermark_col: str = "updated_at"
    pii_cols: tuple[str, ...] = field(default_factory=tuple)
    natural_key: tuple[str, ...] = field(default_factory=tuple)

    @property
    def full_name(self) -> str:
        return f"{self.schema}.{self.table}"

    @property
    def watermark_key(self) -> str:
        return f"{self.schema}__{self.table}"


TABLES: tuple[TableConfig, ...] = (
    # ── vendas ────────────────────────────────────────────────────────────
    TableConfig(
        schema="vendas", table="pedidos",
        pii_cols=(),
        natural_key=("id_pedido",),
    ),
    TableConfig(
        schema="vendas", table="itens_pedido",
        natural_key=("id_item_pedido",),
    ),
    TableConfig(
        schema="vendas", table="devolucoes",
        natural_key=("id_devolucao",),
    ),
    # ── clientes ──────────────────────────────────────────────────────────
    TableConfig(
        schema="clientes", table="clientes",
        pii_cols=("cpf", "email", "telefone"),
        natural_key=("id_cliente",),
    ),
    TableConfig(
        schema="clientes", table="enderecos",
        pii_cols=("logradouro", "complemento"),
        natural_key=("id_endereco",),
    ),
    TableConfig(
        schema="clientes", table="techpoints",
        natural_key=("id_techpoints",),
    ),
    # ── produtos ──────────────────────────────────────────────────────────
    TableConfig(
        schema="produtos", table="produtos",
        natural_key=("id_produto",),
    ),
    TableConfig(
        schema="produtos", table="categorias",
        natural_key=("id_categoria",),
    ),
    TableConfig(
        schema="produtos", table="fornecedores",
        pii_cols=("cnpj",),
        natural_key=("id_fornecedor",),
    ),
    TableConfig(
        schema="produtos", table="precos",
        natural_key=("id_produto", "dt_vigencia_inicio"),
    ),
    # ── estoque ───────────────────────────────────────────────────────────
    TableConfig(
        schema="estoque", table="saldo_estoque",
        natural_key=("id_produto", "id_loja"),
    ),
    TableConfig(
        schema="estoque", table="movimentacoes",
        natural_key=("id_movimentacao",),
    ),
    # ── logistica ─────────────────────────────────────────────────────────
    TableConfig(
        schema="logistica", table="entregas",
        natural_key=("id_entrega",),
    ),
    TableConfig(
        schema="logistica", table="transportadoras",
        pii_cols=("cnpj",),
        natural_key=("id_transportadora",),
    ),
    TableConfig(
        schema="logistica", table="modalidades",
        natural_key=("id_modalidade",),
    ),
    # ── financeiro ────────────────────────────────────────────────────────
    TableConfig(
        schema="financeiro", table="lancamentos",
        natural_key=("id_lancamento",),
    ),
    TableConfig(
        schema="financeiro", table="parcelas",
        natural_key=("id_parcela",),
    ),
    TableConfig(
        schema="financeiro", table="contas_receber",
        natural_key=("id_conta",),
    ),
    TableConfig(
        schema="financeiro", table="orcamentos",
        natural_key=("id_orcamento",),
    ),
    # ── marketing ─────────────────────────────────────────────────────────
    TableConfig(
        schema="marketing", table="campanhas",
        natural_key=("id_campanha",),
    ),
    TableConfig(
        schema="marketing", table="leads",
        pii_cols=("email", "telefone"),
        natural_key=("id_lead",),
    ),
    TableConfig(
        schema="marketing", table="atribuicao",
        natural_key=("id_atribuicao",),
    ),
    # ── rh ────────────────────────────────────────────────────────────────
    TableConfig(
        schema="rh", table="vendedores",
        pii_cols=("cpf",),
        natural_key=("id_vendedor",),
    ),
    TableConfig(
        schema="rh", table="metas",
        natural_key=("id_meta",),
    ),
    TableConfig(
        schema="rh", table="comissoes",
        natural_key=("id_comissao",),
    ),
    # ── web_analytics ─────────────────────────────────────────────────────
    # Fonte de fato_cliente_interacao: sessões e eventos de carrinho
    TableConfig(
        schema="web_analytics", table="sessoes",
        natural_key=("id_sessao",),
    ),
    TableConfig(
        schema="web_analytics", table="eventos_carrinho",
        natural_key=("id_evento",),
    ),
)

# Índice por nome completo para lookup O(1)
TABLES_BY_NAME: dict[str, TableConfig] = {t.full_name: t for t in TABLES}

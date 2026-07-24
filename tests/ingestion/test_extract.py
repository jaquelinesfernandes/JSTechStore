"""
Testes unitários para o extrator Bronze.

Cobrem:
- Leitura/escrita de watermarks (filesystem mockado)
- Configuração de tabelas (TableConfig)
- Lógica de particionamento de diretório Parquet
- Não requerem conexão com Supabase
"""

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from ingestion.connectors.postgres.config import TABLES, TABLES_BY_NAME, TableConfig

# ── TableConfig ────────────────────────────────────────────────────────────────


class TestTableConfig:
    def test_full_name(self):
        cfg = TableConfig(schema="vendas", table="pedidos", natural_key=("id_pedido",))
        assert cfg.full_name == "vendas.pedidos"

    def test_watermark_key(self):
        cfg = TableConfig(schema="clientes", table="clientes", natural_key=("id_cliente",))
        assert cfg.watermark_key == "clientes__clientes"

    def test_default_watermark_col(self):
        cfg = TableConfig(schema="vendas", table="pedidos", natural_key=("id_pedido",))
        assert cfg.watermark_col == "updated_at"

    def test_frozen(self):
        cfg = TableConfig(schema="vendas", table="pedidos", natural_key=("id_pedido",))
        with pytest.raises((AttributeError, TypeError)):
            cfg.schema = "outro"  # type: ignore[misc]


class TestTablesRegistry:
    def test_28_tables(self):
        assert len(TABLES) == 28

    def test_all_schemas_present(self):
        schemas = {t.schema for t in TABLES}
        expected = {
            "vendas",
            "clientes",
            "produtos",
            "estoque",
            "logistica",
            "financeiro",
            "marketing",
            "rh",
            "web_analytics",
        }
        assert schemas == expected

    def test_tables_by_name_lookup(self):
        assert "vendas.pedidos" in TABLES_BY_NAME
        assert TABLES_BY_NAME["vendas.pedidos"].natural_key == ("id_pedido",)

    def test_no_duplicate_tables(self):
        full_names = [t.full_name for t in TABLES]
        assert len(full_names) == len(set(full_names))

    def test_all_have_natural_key(self):
        for t in TABLES:
            assert len(t.natural_key) >= 1, f"{t.full_name} sem natural_key"


# ── Watermark helpers ─────────────────────────────────────────────────────────


class TestWatermark:
    def test_read_watermark_missing_returns_epoch(self, tmp_path):
        from ingestion.connectors.postgres import extract as ext

        cfg = TableConfig(schema="vendas", table="pedidos", natural_key=("id_pedido",))
        with patch.object(ext, "WATERMARKS_DIR", tmp_path):
            result = ext.read_watermark(cfg)
        assert result == ext.EPOCH

    def test_write_and_read_watermark_roundtrip(self, tmp_path):
        from ingestion.connectors.postgres import extract as ext

        cfg = TableConfig(schema="vendas", table="pedidos", natural_key=("id_pedido",))
        ts = datetime(2026, 4, 21, 12, 0, 0, tzinfo=timezone.utc)

        with patch.object(ext, "WATERMARKS_DIR", tmp_path):
            ext.write_watermark(cfg, ts)
            result = ext.read_watermark(cfg)

        assert result == ts

    def test_watermark_file_format(self, tmp_path):
        from ingestion.connectors.postgres import extract as ext

        cfg = TableConfig(schema="clientes", table="clientes", natural_key=("id_cliente",))
        ts = datetime(2026, 7, 20, 22, 59, 43, tzinfo=timezone.utc)

        with patch.object(ext, "WATERMARKS_DIR", tmp_path):
            ext.write_watermark(cfg, ts)
            wm_file = tmp_path / "clientes__clientes.json"
            data = json.loads(wm_file.read_text(encoding="utf-8"))

        assert "last_updated_at" in data
        assert "updated_at_utc" in data
        assert data["last_updated_at"] == ts.isoformat()

    def test_watermark_atomic_write_no_tmp_left(self, tmp_path):
        from ingestion.connectors.postgres import extract as ext

        cfg = TableConfig(schema="vendas", table="pedidos", natural_key=("id_pedido",))
        ts = datetime(2026, 7, 20, tzinfo=timezone.utc)

        with patch.object(ext, "WATERMARKS_DIR", tmp_path):
            ext.write_watermark(cfg, ts)

        tmp_files = list(tmp_path.glob(".tmp_*.json"))
        assert tmp_files == [], "Arquivos temporários não foram removidos"


# ── Partição Parquet ──────────────────────────────────────────────────────────


class TestParquetPartition:
    def test_partition_path_structure(self, tmp_path):
        from ingestion.connectors.postgres import extract as ext

        cfg = TableConfig(schema="vendas", table="pedidos", natural_key=("id_pedido",))
        dt = datetime(2026, 4, 21, tzinfo=timezone.utc)

        with patch.object(ext, "BRONZE_PATH", tmp_path):
            result = ext.parquet_partition_dir(cfg, dt)

        assert result == tmp_path / "vendas" / "pedidos" / "year=2026" / "month=04" / "day=21"

    def test_partition_month_zero_padded(self, tmp_path):
        from ingestion.connectors.postgres import extract as ext

        cfg = TableConfig(schema="estoque", table="saldo_estoque", natural_key=("id_saldo",))
        dt = datetime(2026, 5, 3, tzinfo=timezone.utc)

        with patch.object(ext, "BRONZE_PATH", tmp_path):
            result = ext.parquet_partition_dir(cfg, dt)

        assert "month=05" in str(result)
        assert "day=03" in str(result)

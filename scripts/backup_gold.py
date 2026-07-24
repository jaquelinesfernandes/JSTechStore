"""
Backup da camada Gold (DuckDB) com compressão gzip, rotação local e log de auditoria.

Uso:
    python scripts/backup_gold.py
    python scripts/backup_gold.py --keep-days 14
    python scripts/backup_gold.py --export-parquet
    python scripts/backup_gold.py --dry-run
"""

import argparse
import gzip
import json
import logging
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

DUCKDB_PATH = Path(os.getenv("DUCKDB_PATH", "data/gold/jstechstore.duckdb"))
BACKUP_DIR = Path(os.getenv("GOLD_BACKUP_DIR", "data/backups/gold"))
LOG_FILE = BACKUP_DIR / "backup_log.jsonl"
DEFAULT_KEEP_DAYS = 7


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backup da camada Gold (DuckDB)")
    p.add_argument("--duckdb-path", type=Path, default=DUCKDB_PATH)
    p.add_argument("--backup-dir", type=Path, default=BACKUP_DIR)
    p.add_argument(
        "--keep-days",
        type=int,
        default=DEFAULT_KEEP_DAYS,
        help="Quantidade de backups diários a manter (padrão: 7)",
    )
    p.add_argument(
        "--export-parquet",
        action="store_true",
        help="Exporta tabelas Gold como Parquet portável (fallback de recuperação)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula execução sem gravar nenhum arquivo",
    )
    return p.parse_args()


def compress_duckdb(source: Path, dest: Path, dry_run: bool = False) -> int:
    """Cria cópia gzip do arquivo DuckDB. Retorna tamanho do arquivo comprimido em bytes."""
    log.info(f"Comprimindo {source} → {dest}")
    if dry_run:
        log.info("[dry-run] Compressão ignorada")
        return 0
    with open(source, "rb") as f_in, gzip.open(dest, "wb", compresslevel=6) as f_out:
        shutil.copyfileobj(f_in, f_out)
    size = dest.stat().st_size
    log.info(f"Backup criado: {dest.name} ({size / 1_048_576:.1f} MB)")
    return size


def rotate_local_backups(backup_dir: Path, keep_days: int, dry_run: bool = False) -> list[Path]:
    """Remove os backups mais antigos, mantendo apenas os últimos keep_days."""
    backups = sorted(backup_dir.glob("jstechstore_*.duckdb.gz"))
    to_remove = backups[:-keep_days] if len(backups) > keep_days else []
    for old_file in to_remove:
        log.info(f"Removendo backup expirado: {old_file.name}")
        if not dry_run:
            old_file.unlink()
    if not to_remove:
        log.info(f"Rotação: {len(backups)} backup(s) mantido(s) — nenhum expirado")
    return to_remove


def export_as_parquet(source: Path, export_dir: Path, dry_run: bool = False) -> None:
    """Exporta todas as tabelas Gold como Parquet usando EXPORT DATABASE do DuckDB.

    Gera arquivos portáveis que permitem reconstruir o .duckdb sem depender do binário.
    Útil como fallback quando o arquivo .duckdb.gz está corrompido.
    """
    try:
        import duckdb
    except ImportError:
        log.warning("Pacote 'duckdb' não instalado — exportação Parquet ignorada")
        return

    log.info(f"Exportando tabelas Gold como Parquet em {export_dir}")
    if dry_run:
        log.info("[dry-run] Exportação Parquet ignorada")
        return

    export_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(source), read_only=True)
    try:
        con.execute(f"EXPORT DATABASE '{export_dir}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        log.info(f"Exportação Parquet concluída: {export_dir}")
    finally:
        con.close()


def write_audit_log(log_file: Path, entry: dict, dry_run: bool = False) -> None:
    if dry_run:
        return
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def main() -> int:
    args = parse_args()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    started_at = datetime.now(timezone.utc)

    source = args.duckdb_path
    if not source.exists():
        log.error(f"Arquivo DuckDB não encontrado: {source}")
        log.error("Execute 'dbt run --full-refresh' para criar a camada Gold antes do backup.")
        return 1

    backup_dir = args.backup_dir
    if not args.dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)

    source_size = source.stat().st_size
    dest = backup_dir / f"jstechstore_{ts}.duckdb.gz"

    log.info(f"=== Backup Gold iniciado | ts={ts} ===")
    log.info(f"Fonte : {source} ({source_size / 1_048_576:.1f} MB)")
    log.info(f"Destino: {dest}")

    backup_size = compress_duckdb(source, dest, dry_run=args.dry_run)
    removed = rotate_local_backups(backup_dir, args.keep_days, dry_run=args.dry_run)

    if args.export_parquet:
        parquet_dir = backup_dir / f"parquet_{ts}"
        export_as_parquet(source, parquet_dir, dry_run=args.dry_run)

    ratio = round(backup_size / source_size, 3) if source_size and backup_size else 0
    duration = (datetime.now(timezone.utc) - started_at).total_seconds()

    entry = {
        "timestamp": started_at.isoformat(),
        "source_path": str(source),
        "backup_file": str(dest),
        "source_size_bytes": source_size,
        "backup_size_bytes": backup_size,
        "compression_ratio": ratio,
        "keep_days": args.keep_days,
        "rotated_files": [f.name for f in removed],
        "export_parquet": args.export_parquet,
        "duration_seconds": round(duration, 2),
        "dry_run": args.dry_run,
    }
    write_audit_log(LOG_FILE, entry, dry_run=args.dry_run)

    log.info(f"Taxa de compressão : {ratio:.1%}")
    log.info(f"Duração            : {duration:.1f}s")
    log.info("=== Backup Gold concluído com sucesso ===")

    # Variável de saída para o GitHub Actions capturar o caminho do arquivo
    if not args.dry_run:
        print(f"BACKUP_FILE={dest}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

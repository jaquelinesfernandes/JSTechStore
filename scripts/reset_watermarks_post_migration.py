#!/usr/bin/env python3
"""
Reset de watermarks após migração Supabase → Neon.tech.

Quando generate_data.py é executado num banco novo (Neon), todos os registros
recebem updated_at ≈ NOW() — não as datas históricas originais. Isso faria o
extract.py re-extrair os 3 anos inteiros na primeira execução incremental,
duplicando dados que já existem no Bronze Parquet.

Este script avança todos os watermarks para o momento atual, garantindo que
a próxima extração incremental capture apenas dados novos (gerados após a
carga inicial no Neon), sem re-processar o histórico já presente no Bronze.

Deve ser executado UMA VEZ, imediatamente após generate_data.py terminar
no Neon e ANTES da primeira execução do daily_pipeline.

Uso:
    python scripts/reset_watermarks_post_migration.py
    python scripts/reset_watermarks_post_migration.py --dry-run
    python scripts/reset_watermarks_post_migration.py --to 2026-09-11T20:00:00+00:00
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

WATERMARKS_DIR = Path(__file__).parent.parent / "data" / "bronze" / ".watermarks"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Avança watermarks após carga inicial no banco Neon"
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra o que seria alterado sem gravar nada",
    )
    p.add_argument(
        "--to",
        default=None,
        help="Timestamp ISO para onde avançar (default: agora). Ex: 2026-09-11T20:00:00+00:00",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if not WATERMARKS_DIR.exists():
        log.error(f"Diretório de watermarks não encontrado: {WATERMARKS_DIR}")
        log.error("Execute o pipeline pelo menos uma vez antes de rodar este script.")
        return 1

    target_ts: datetime
    if args.to:
        try:
            target_ts = datetime.fromisoformat(args.to)
            if target_ts.tzinfo is None:
                target_ts = target_ts.replace(tzinfo=timezone.utc)
        except ValueError:
            log.error(f"Timestamp inválido: {args.to}. Use formato ISO: YYYY-MM-DDTHH:MM:SS+00:00")
            return 1
    else:
        target_ts = datetime.now(timezone.utc)

    files = sorted(WATERMARKS_DIR.glob("*.json"))
    if not files:
        log.warning("Nenhum arquivo de watermark encontrado em %s", WATERMARKS_DIR)
        return 0

    ts_str = target_ts.isoformat()
    log.info(f"Avançando {len(files)} watermarks para: {ts_str}")
    if args.dry_run:
        log.info("*** DRY RUN — nenhum arquivo será alterado ***")

    for wf in files:
        try:
            current = json.loads(wf.read_text(encoding="utf-8"))
            old_ts = current.get("last_updated_at", "(não definido)")
            log.info(f"  {wf.name}: {old_ts} → {ts_str}")

            if not args.dry_run:
                current["last_updated_at"] = ts_str
                current["last_checked_at"] = ts_str
                current["_migrated_at"] = datetime.now(timezone.utc).isoformat()
                current["_migration_note"] = "Avançado após carga inicial Supabase→Neon"
                wf.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            log.error(f"  ERRO em {wf.name}: {exc}")
            return 1

    if args.dry_run:
        log.info("Dry run concluído. Nenhum arquivo alterado.")
    else:
        log.info(f"✓ {len(files)} watermarks atualizados com sucesso.")
        log.info("Próxima execução de extract.py --mode incremental capturará apenas dados novos.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

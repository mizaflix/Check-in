#!/usr/bin/env python3
"""Cria um ZIP da pasta de fotos locais do CheckKids."""
from datetime import datetime
from pathlib import Path
import os
import shutil
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

folder = Path(os.getenv("UPLOAD_FOLDER") or (Path(__file__).resolve().parent / "static" / "uploads")).expanduser().resolve()
if not folder.is_dir():
    print(f"Pasta de uploads não encontrada: {folder}", file=sys.stderr)
    raise SystemExit(2)
backup_dir = Path(__file__).resolve().parent / "backups"
backup_dir.mkdir(parents=True, exist_ok=True)
base = backup_dir / f"checkkids_uploads_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
archive = shutil.make_archive(str(base), "zip", root_dir=folder)
print(f"Backup das fotos concluído: {archive} ({Path(archive).stat().st_size} bytes)")

#!/usr/bin/env python3
"""Gera dump PostgreSQL custom format a partir de DATABASE_URL no ambiente/.env."""
from datetime import datetime
from pathlib import Path
import os
import shutil
import subprocess
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

url = (os.getenv("DATABASE_URL") or "").strip()
if not url or not url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
    print("ERRO: DATABASE_URL PostgreSQL não encontrada. Configure-a no .env ou no ambiente.", file=sys.stderr)
    raise SystemExit(2)

pg_dump = shutil.which("pg_dump")
if not pg_dump:
    print("ERRO: pg_dump não encontrado. Instale as ferramentas cliente do PostgreSQL e adicione a pasta bin ao PATH.", file=sys.stderr)
    raise SystemExit(2)

# pg_dump aceita a URL de conexão padrão postgresql://; normaliza o esquema SQLAlchemy.
url = url.replace("postgresql+psycopg://", "postgresql://", 1).replace("postgres://", "postgresql://", 1)
backup_dir = Path(__file__).resolve().parent / "backups"
backup_dir.mkdir(parents=True, exist_ok=True)
output = backup_dir / f"checkkids_{datetime.now().strftime('%Y%m%d_%H%M%S')}.dump"
cmd = [pg_dump, "--format=custom", "--no-owner", "--no-acl", "--verbose", "--file", str(output), "--dbname", url]
print(f"Gerando dump PostgreSQL em: {output}")
result = subprocess.run(cmd, check=False)
if result.returncode != 0:
    output.unlink(missing_ok=True)
    print("ERRO: pg_dump não conseguiu concluir o backup. Confira a conexão e as permissões.", file=sys.stderr)
    raise SystemExit(result.returncode)
print(f"Backup concluído: {output} ({output.stat().st_size} bytes)")

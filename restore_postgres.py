#!/usr/bin/env python3
"""Restaura dump custom do PostgreSQL em DATABASE_URL do ambiente/.env."""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("dump", help="Caminho para o arquivo .dump")
parser.add_argument("--confirm-empty-database", action="store_true", help="Confirma que o banco de destino está vazio e pode ser restaurado")
args = parser.parse_args()
if not args.confirm_empty_database:
    parser.error("Antes de restaurar, crie um banco vazio e informe --confirm-empty-database.")
url = (os.getenv("DATABASE_URL") or "").strip()
if not url or not url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
    print("ERRO: DATABASE_URL PostgreSQL de destino não encontrada.", file=sys.stderr)
    raise SystemExit(2)
pg_restore = shutil.which("pg_restore")
if not pg_restore:
    print("ERRO: pg_restore não encontrado. Instale as ferramentas cliente do PostgreSQL.", file=sys.stderr)
    raise SystemExit(2)
dump = Path(args.dump).expanduser().resolve()
if not dump.is_file():
    print(f"ERRO: arquivo não encontrado: {dump}", file=sys.stderr)
    raise SystemExit(2)
url = url.replace("postgresql+psycopg://", "postgresql://", 1).replace("postgres://", "postgresql://", 1)
cmd = [pg_restore, "--clean", "--if-exists", "--exit-on-error", "--no-owner", "--no-acl", "--verbose", "--dbname", url, str(dump)]
result = subprocess.run(cmd, check=False)
if result.returncode:
    print("A restauração terminou com erro. Confira os logs do pg_restore.", file=sys.stderr)
    raise SystemExit(result.returncode)
print("Restauração concluída.")

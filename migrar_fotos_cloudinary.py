"""Migra fotos locais do CheckKids para Cloudinary e atualiza as referências no banco.

Execute depois de configurar CLOUDINARY_URL e DATABASE_URL no ambiente.
Arquivos ausentes são ignorados e informados; nenhum registro é apagado.
"""
from pathlib import Path
import os
import uuid

os.environ.setdefault('CHECKKIDS_SKIP_INIT', '1')

import cloudinary
import cloudinary.uploader

import app as checkkids


def main():
    if not os.getenv('CLOUDINARY_URL'):
        raise SystemExit('Configure CLOUDINARY_URL antes de executar a migração.')

    cloudinary.config(secure=True)
    base = Path(checkkids.app.config['UPLOAD_FOLDER'])
    cache = {}
    atualizados = 0
    ausentes = []

    with checkkids.app.app_context():
        registros = []
        for model, field in (
            (checkkids.Usuario, 'foto_perfil'),
            (checkkids.Responsavel, 'foto_url'),
            (checkkids.Crianca, 'foto_url'),
        ):
            registros.extend((obj, field) for obj in model.query.all())

        for obj, field in registros:
            valor = getattr(obj, field, None)
            if not valor or valor == 'default.png' or str(valor).startswith(('cloudinary:', 'http://', 'https://')):
                continue

            nome = Path(str(valor)).name
            caminho = base / nome
            if not caminho.is_file():
                ausentes.append(nome)
                continue

            if nome not in cache:
                resultado = cloudinary.uploader.upload(
                    str(caminho),
                    folder='checkkids/migradas',
                    public_id=f"{Path(nome).stem}_{uuid.uuid4().hex[:8]}",
                    resource_type='image',
                    overwrite=False,
                    transformation=[
                        {'width': 1200, 'height': 1200, 'crop': 'limit'},
                        {'quality': 'auto', 'fetch_format': 'auto'}
                    ]
                )
                cache[nome] = f"cloudinary:{resultado['public_id']}"

            setattr(obj, field, cache[nome])
            atualizados += 1

        checkkids.db.session.commit()

    print(f'Referências atualizadas: {atualizados}')
    print(f'Arquivos enviados: {len(cache)}')
    if ausentes:
        print('Arquivos locais não encontrados (não foram alterados):')
        for nome in sorted(set(ausentes)):
            print(f' - {nome}')


if __name__ == '__main__':
    main()

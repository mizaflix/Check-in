# Configurar armazenamento permanente de fotos no CheckKids

O sistema aceita duas opções. A recomendada para o CheckKids no Render é Cloudinary.

## Opção A — Cloudinary (recomendada)

1. Crie/acesse sua conta em https://cloudinary.com/.
2. No painel, abra **Settings > API Keys** e copie o valor completo de `CLOUDINARY_URL`.
3. No Render, abra o serviço CheckKids > **Environment**.
4. Adicione a variável `CLOUDINARY_URL` com o valor copiado. Não coloque esse valor no GitHub.
5. Salve e faça um novo deploy.
6. Teste alterando a foto em **Configurações > Minha conta** e cadastrando uma foto de criança.

O aplicativo grava no banco uma referência `cloudinary:<public_id>`, e as imagens são entregues pelo endereço seguro do Cloudinary. Não é necessário criar coluna nova no PostgreSQL.

## Opção B — Persistent Disk do Render

Esta opção exige um plano do Render que permita anexar Persistent Disk.

1. No serviço do CheckKids, abra **Disks** e adicione um disco com mount path `/var/data`.
2. Em **Environment**, adicione `UPLOAD_FOLDER=/var/data/uploads`.
3. Salve e faça o deploy.

O diretório informado em `UPLOAD_FOLDER` deve estar dentro do mount path do disco. Só os arquivos gravados dentro do disco são preservados entre reinicializações e deploys.

## Fotos antigas

Se as fotos antigas ainda existirem no seu computador em `static/uploads`, faça primeiro um backup da pasta. Depois, com `DATABASE_URL` apontando para o banco correto e `CLOUDINARY_URL` configurado no `.env` local, execute:

```powershell
python migrar_fotos_cloudinary.py
```

O script tenta enviar os arquivos locais encontrados e atualizar as referências em `Usuario.foto_perfil`, `Responsavel.foto_url` e `Crianca.foto_url`. Fotos cujo arquivo local não existe serão listadas e não serão apagadas do banco. Se o Render já apagou o arquivo original e não existe cópia local, será necessário enviar novamente a foto pelo perfil/cadastro.

## Segurança

- Nunca envie `.env` para o GitHub ou em um ZIP compartilhado.
- Use variáveis de ambiente no Render para credenciais.
- O limite de upload configurado é de 8 MB por requisição.

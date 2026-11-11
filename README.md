# CheckKids

Sistema web Flask para gerenciamento de responsáveis, crianças, turmas, check-in/check-out, escala e notificações.

## Principais recursos desta versão

- Painel administrativo com gerenciamento de usuários.
- Escala geral integrada ao layout administrativo.
- Atualização automática da contagem de crianças na tela do QR Code, sem recriar o QR.
- Reabertura de check-in para receber alunos que chegarem depois.
- Foto de perfil de responsáveis, professores e crianças.
- Notificações internas e integração opcional com WhatsApp via Evolution API.

## Fotos: armazenamento local

O Cloudinary foi removido do código e das dependências. As novas fotos são salvas localmente em `static/uploads/` por padrão. O banco guarda apenas o nome do arquivo.

No Docker Compose, o diretório `/app/static/uploads` é montado no volume persistente `uploads`. Não apague esse volume ao atualizar o container. Consulte `CONFIGURAR_FOTOS.md` para migrar imagens de outro computador/servidor.

Se a VPS usar um caminho diferente, configure `UPLOAD_FOLDER` no ambiente com um caminho absoluto e persistente.

## Configuração

1. Crie um arquivo `.env` baseado em `.env.example` (ou configure as mesmas variáveis no `stack.env` do Portainer).
2. Configure `DATABASE_URL` para o PostgreSQL que será utilizado e defina uma `SECRET_KEY` forte.
3. Instale as dependências com `pip install -r requirements.txt`.
4. Para executar diretamente, use `gunicorn --bind 0.0.0.0:8000 --workers 4 --timeout 120 app:app`.

O `docker-compose.yml` usa a imagem publicada pelo GitHub Actions em `ghcr.io/mizaflix/check-in:latest`. Ao enviar commits para a branch `main`, o workflow `.github/workflows/deploy.yml` constrói a imagem e aciona o webhook do Portainer.

## WhatsApp (Evolution API)

Configure no `.env` ou `stack.env`:

```env
EVOLUTION_API_URL=https://seu-dominio-da-evolution
EVOLUTION_API_KEY=sua-chave
EVOLUTION_INSTANCE=nome-da-instancia
```

O alerta interno do CheckKids continua disponível mesmo quando a Evolution API não está configurada. O envio externo depende do consentimento do responsável salvo no sistema.

## Backup e migração do banco

O repositório inclui `backup_postgres.py` e `restore_postgres.py` para gerar e restaurar um dump PostgreSQL em formato custom (`.dump`). É necessário ter `pg_dump` e `pg_restore` instalados e `DATABASE_URL` configurada no `.env` ou no ambiente.

Gerar backup:

```bash
python backup_postgres.py
```

O arquivo será gravado em `backups/`. Para fazer também o backup das imagens locais, execute `python backup_uploads.py` (o ZIP das fotos também ficará em `backups/`). Para restaurar em um banco novo e vazio:

```bash
python restore_postgres.py backups/ARQUIVO.dump --confirm-empty-database
```

**O ZIP do projeto não contém o `.env` nem a conexão do banco de produção.** Portanto, o dump real do Neon/PostgreSQL deve ser gerado no ambiente que possui a `DATABASE_URL` correta. Um dump do PostgreSQL não inclui as fotos: faça também backup de `static/uploads/` (ou do volume Docker `uploads`) e restaure os arquivos mantendo os nomes.

Leia `BACKUP_E_MIGRACAO.md` antes de migrar o banco para a VPS. A pasta `instance/` é criada automaticamente; bancos SQLite locais não são distribuídos dentro deste ZIP para evitar substituir acidentalmente o banco em uso.

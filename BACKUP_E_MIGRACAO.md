# Backup e migração do CheckKids para uma VPS

## 1. Gerar o dump real do PostgreSQL atual

O ZIP de código não contém `.env` nem credenciais do banco. No computador/servidor que ainda tem a conexão atual do banco (por exemplo, Neon), mantenha seu `.env` privado na pasta do projeto e confira se `DATABASE_URL` aponta para a base correta.

Instale as ferramentas cliente do PostgreSQL (`pg_dump` e `pg_restore`). Depois execute:

```bash
python backup_postgres.py
```

O script lê `DATABASE_URL` do ambiente ou do `.env` e cria `backups/checkkids_AAAAMMDD_HHMMSS.dump` em formato custom. Faça também o ZIP da pasta de fotos com `python backup_uploads.py`. Não compartilhe os arquivos publicamente: eles podem conter dados pessoais e hashes de senha.

## 2. Preparar o PostgreSQL da VPS

1. Instale PostgreSQL na VPS ou crie um servidor PostgreSQL acessível pela VPS.
2. Crie um banco vazio e um usuário com permissões para criar tabelas e inserir registros.
3. Na VPS, configure `DATABASE_URL` para o banco de destino no `.env`/`stack.env`.
4. Copie o arquivo `.dump` para a VPS.
5. Instale `pg_restore` e execute, apontando para o dump correto:

```bash
python restore_postgres.py backups/checkkids_AAAAMMDD_HHMMSS.dump --confirm-empty-database
```

O script exige a confirmação explícita de que o banco de destino está vazio. Ele limpa objetos com os mesmos nomes antes de restaurar. Não use essa opção contra uma base com dados que precisam ser preservados.

## 3. Levar as fotos para a VPS

O banco mantém referências aos nomes das fotos, mas o dump PostgreSQL não inclui arquivos do filesystem. Antes de desligar o servidor antigo, copie a pasta inteira `static/uploads/` para a VPS mantendo os nomes dos arquivos.

Exemplo com SCP, executado na máquina antiga:

```bash
scp -r static/uploads usuario@IP_DA_VPS:/caminho/do/Check-in/static/
```

Ajuste usuário, IP e caminho. Alternativamente, rode `python backup_uploads.py` e transfira o ZIP criado em `backups/`. Se o CheckKids roda em Docker, os arquivos extraídos devem ficar no volume montado em `/app/static/uploads`. Não remova o volume `uploads` durante atualizações.

## 4. Conferência depois da migração

- Entre com uma conta já existente.
- Confira responsáveis, crianças, turmas, escala e histórico.
- Abra algumas fotos de crianças e responsáveis.
- Faça um cadastro de teste com uma imagem e confirme que o arquivo apareceu em `static/uploads/` (ou no volume configurado).
- Confira se o volume de uploads tem backup independente do PostgreSQL.

## 5. Sobre os bancos SQLite que vieram dentro do ZIP enviado

O arquivo recebido tinha `instance/banco.db` e `instance/checkkids.db`. Eles foram copiados para um pacote de backup local separado, mas não há como confirmar que sejam a base PostgreSQL de produção usada pelo Render/Neon. Para migrar os dados atuais do Neon, gere o `.dump` com a `DATABASE_URL` real conforme a etapa 1.

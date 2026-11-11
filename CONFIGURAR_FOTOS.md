# Fotos locais no CheckKids (VPS)

O CheckKids voltou a salvar todas as novas fotos diretamente no filesystem. Por padrão, os arquivos ficam em:

```text
static/uploads/
```

O banco armazena somente o nome do arquivo, por exemplo `crianca_a1b2c3.jpg`. A rota `/uploads/<nome>` entrega a imagem ao navegador.

## Executando diretamente na VPS

1. Garanta que o usuário que executa o Gunicorn tenha permissão de escrita em `static/uploads`.
2. Crie a pasta, caso ainda não exista:

   ```bash
   mkdir -p static/uploads
   ```

3. Se preferir guardar os uploads fora da pasta do código, configure no `.env` um caminho absoluto persistente:

   ```env
   UPLOAD_FOLDER=/opt/checkkids/uploads
   ```

4. Reinicie o serviço do CheckKids.

## Executando com Docker Compose / Portainer

O `docker-compose.yml` configura `UPLOAD_FOLDER=/app/static/uploads` e monta o volume nomeado `uploads` nesse caminho. Assim, as fotos permanecem no volume mesmo quando o container é recriado ou atualizado.

Para conferir o nome real do volume no servidor:

```bash
docker volume ls
```

Não remova o volume `uploads` ao atualizar o container. Remover o volume apaga as fotos armazenadas nele.

## Migrar fotos que já estão no computador antigo

Antes de desligar o computador/servidor antigo, copie todo o conteúdo de `static/uploads/` para a mesma pasta na VPS (ou para o diretório configurado em `UPLOAD_FOLDER`). Faça a cópia mantendo os nomes originais dos arquivos, pois o banco guarda esses nomes.

Exemplo de cópia via SCP executado no computador antigo:

```bash
scp -r static/uploads usuario@IP_DA_VPS:/opt/checkkids/static/
```

Ajuste o usuário, IP e caminho conforme sua VPS. Se usar Docker Compose, copie os arquivos para o volume persistente antes de colocar o sistema em produção.

## Limite e formatos

- Limite configurado: 8 MB por requisição.
- Formatos aceitos: JPG, JPEG, PNG, GIF e WEBP.
- Novos arquivos recebem nomes únicos para evitar sobrescrever fotos anteriores.

## Importante sobre fotos da fase Cloudinary

Registros antigos que tenham o identificador `cloudinary:<public_id>` não contêm um arquivo local. O sistema mostra o avatar padrão para esses registros até que a foto seja reenviada ou copiada manualmente para `static/uploads` e o campo correspondente no banco seja atualizado para o nome local do arquivo.

O ZIP do projeto não inclui credenciais `.env` nem bancos de dados de produção. Faça backup separado do banco e da pasta `static/uploads`.

# Atualização CheckKids — responsáveis e foto da criança

## O que foi corrigido

- O painel familiar agora mostra todos os responsáveis cadastrados na conta.
- Cada responsável é apresentado usando os dados do próprio registro: nome, foto, vínculo e telefone.
- Cadastrar um responsável adicional não altera mais a foto do titular da conta.
- A edição de uma conta pelo painel administrativo sincroniza apenas o primeiro responsável (principal), sem sobrescrever os dados dos responsáveis adicionais.
- O perfil da criança permite ao responsável da conta ou a um administrador enviar uma nova foto.
- A troca da foto da criança altera somente `Crianca.foto_url`; nome, nascimento, turma, check-ins e demais dados não são modificados.

## Arquivos alterados

- `app.py`
- `templates/dashboard.html`
- `templates/detalhes_crianca.html`

## Atualização em uma instalação que já está em uso

1. Faça backup do banco de dados.
2. Faça backup da pasta `static/uploads` (ou da pasta definida em `UPLOAD_FOLDER`).
3. Atualize os arquivos do projeto com os arquivos deste pacote.
4. Preserve o `.env` atual e não substitua a pasta de uploads da instalação.
5. Reinicie o serviço Flask/Gunicorn ou o container da aplicação.

**Não é necessária migração de banco de dados.** O pacote não inclui `.env`, banco de dados nem fotos já enviadas pelos usuários.

## Como trocar a foto da criança

Na conta familiar, abra **Ver perfil** na criança desejada, selecione a nova imagem na área **Alterar foto da criança** e clique em **Salvar nova foto**. São aceitos JPG, PNG, GIF e WEBP, até 8 MB.

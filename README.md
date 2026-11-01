# CheckKids

## Integração Twilio WhatsApp

O botão **Chamar Responsável** mantém a notificação interna e, quando houver consentimento do responsável e as credenciais do Twilio estiverem configuradas, envia também um alerta por WhatsApp.

### Variáveis do Render

Em **Web Service > Environment** configure:

```text
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
TWILIO_WHATSAPP_CONTENT_SID=...
```

Para produção, use um WhatsApp Sender registrado no Twilio. O `TWILIO_WHATSAPP_CONTENT_SID` é o SID de um template aprovado e usa as variáveis `{{1}}` = nome da criança e `{{2}}` = nome da sala.

### Consentimento

Os formulários de cadastro de responsável agora possuem uma opção explícita para autorizar mensagens pelo WhatsApp. Sem o consentimento, o alerta interno continua funcionando e nenhum WhatsApp é enviado.

### Banco existente

A aplicação verifica a tabela `responsavel` durante a inicialização e cria a coluna `whatsapp_opt_in` quando ela ainda não existir. Também existe o arquivo `migrar_twilio.sql` para executar manualmente no PostgreSQL do Render, caso desejado.

### Sandbox

Para testes, a Twilio oferece um ambiente de WhatsApp. Cada destinatário precisa aderir ao Sandbox. Fora da janela de atendimento iniciada pelo usuário, o WhatsApp exige um template aprovado; por isso, para produção, configure `TWILIO_WHATSAPP_CONTENT_SID`.

## Atualizações de administração e check-in

Esta versão também inclui:

- Painel administrativo redesenhado, com indicadores gerais e atalhos para a escala e os usuários.
- Gerenciamento administrativo de contas: criar usuários, pesquisar/filtrar, editar nome/e-mail/telefone, alterar perfil e redefinir senha.
- Exclusão protegida: não permite excluir a própria conta, o último administrador ou contas que ainda tenham vínculo com crianças, responsáveis, notificações ou escalas.
- Contador de presentes na tela do QR atualizado automaticamente a cada 5 segundos. A atualização consulta somente a contagem e não recria nem altera o conteúdo do QR Code.
- Ação **Reabrir Check-in** no painel do professor quando a turma está em andamento. Ela volta a aceitar novas entradas usando o mesmo QR Code da turma.

### Publicação

As novas telas e rotas não exigem uma nova coluna no banco de dados. Faça o deploy do código atualizado normalmente no Render. O arquivo `.env`, os bancos locais e as fotos enviadas por usuários não fazem parte do pacote de código; mantenha as variáveis de ambiente e os dados reais somente no ambiente correto.
## Fotos de perfil e armazenamento permanente

O sistema agora aceita Cloudinary para armazenar fotos de responsáveis, crianças e professores. Configure `CLOUDINARY_URL` no ambiente local e no Render (Environment). O valor pode ser copiado da área **API Keys** do painel Cloudinary. O código grava no PostgreSQL apenas uma referência curta `cloudinary:<public_id>`, e gera a URL de exibição quando necessário.

Para o Render, não deixe uploads no filesystem temporário: sem Cloudinary, conecte um **Persistent Disk** ao serviço e configure `UPLOAD_FOLDER=/var/data/uploads` com o mount path `/var/data`. O caminho é configurável por variável de ambiente.

No computador local, quando `CLOUDINARY_URL` não estiver configurado, as imagens continuam sendo salvas em `static/uploads`.

A página **Minha conta** permite atualizar a foto do responsável. A escala geral do administrador utiliza agora a mesma barra lateral e a identidade visual do painel administrativo.


Se ainda existirem cópias das fotos antigas no diretório local `static/uploads`, depois de configurar `DATABASE_URL` e `CLOUDINARY_URL` no `.env`, execute `python migrar_fotos_cloudinary.py`. O script envia os arquivos encontrados e atualiza as referências correspondentes no banco. Arquivos que não existirem localmente são apenas listados, sem apagar registros.

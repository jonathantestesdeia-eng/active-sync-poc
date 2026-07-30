# Infraestrutura de armazenamento no Google Drive

## Estado atual

O backup automático está disponível, mas permanece desabilitado por padrão.
`GOOGLE_DRIVE_ENABLED=false` mantém o comportamento histórico sem criar cliente,
pastas ou uploads.

Quando habilitado, o Google Drive continua fora do fluxo crítico. O pipeline
conclui download, extração, leitura, transformação e persistência SQLite. O
histórico é finalizado como `SUCESSO` e somente depois o ZIP validado é enviado
em uma tarefa de backup independente.

## Decisão de autenticação

Para uma conta Google pessoal, o método recomendado é OAuth 2.0 de usuário com
acesso offline. O JSON do tipo `authorized_user` contém o refresh token usado
pelo serviço no Render, sem exigir login interativo a cada execução.

Service Account é suportada pela infraestrutura, mas é recomendada somente
quando a pasta está em um Shared Drive do Google Workspace ou existe uma
política administrativa adequada. Uma Service Account não é a conta pessoal do
usuário e não deve ser tratada como proprietária dos arquivos do My Drive.

O escopo preparado é:

```text
https://www.googleapis.com/auth/drive.file
```

Ele limita o acesso aos arquivos criados ou explicitamente disponibilizados
para a aplicação.

## Biblioteca

A implementação usa as bibliotecas oficiais:

- `google-api-python-client`, para Drive API v3;
- `google-auth`, para credenciais OAuth e Service Account.

O cliente é criado de forma lazy: construir a configuração ou o adapter não
realiza acesso de rede.

## Contrato

`active_sync.storage.FileStorage` define a porta independente do provedor.
`GoogleDriveStorage` é o adapter do Google Drive e `DisabledFileStorage` impede
uso acidental quando a funcionalidade está desligada. `BestEffortDriveBackup`
coordena a organização e o envio sem propagar falhas para a sincronização.

## Ponto de integração

O ZIP é registrado internamente após sua validação, mas o upload ocorre somente
depois da conclusão funcional de toda a sincronização:

```text
Download em arquivo .part
        ↓
Validação da assinatura e estrutura ZIP
        ↓
Renomeação atômica para o ZIP definitivo
        ↓
Extração local
        ↓
Leitura do Excel
        ↓
Transformação
        ↓
Persistência SQLite
        ↓
Histórico finalizado como SUCESSO
        ↓
Backup assíncrono do ZIP no Google Drive
```

O backup envia somente o ZIP original. Excel, arquivos `.part`, SQLite e logs
não são enviados. Falha de autenticação, rede, token, pasta ou API é registrada
como `sync_backup_failed`, com `non_critical=true`, sem alterar o status, desfazer
o banco ou retornar erro ao usuário.

## Organização

Sob a pasta pai configurada por `GOOGLE_DRIVE_FOLDER_ID`, o serviço cria ou
reutiliza:

```text
Active Sync/
└── AAAA/
    └── MM/
        └── relatório.zip
```

Ano e mês usam `America/Sao_Paulo` na data de conclusão da sincronização.

## Variáveis

```dotenv
GOOGLE_DRIVE_ENABLED=false
GOOGLE_DRIVE_FOLDER_ID=

# Escolha somente uma fonte:
GOOGLE_APPLICATION_CREDENTIALS=
GOOGLE_DRIVE_CREDENTIALS_JSON=
```

- `GOOGLE_DRIVE_ENABLED`: chave geral, desabilitada por padrão.
- `GOOGLE_DRIVE_FOLDER_ID`: ID da pasta de destino, não a URL completa.
- `GOOGLE_APPLICATION_CREDENTIALS`: caminho para JSON `authorized_user` ou
  `service_account`. No Render, pode apontar para um Secret File.
- `GOOGLE_DRIVE_CREDENTIALS_JSON`: alternativa para armazenar o JSON completo
  como variável secreta do ambiente.

Nunca configure simultaneamente as duas fontes de credenciais. Nunca grave o
JSON real no repositório, `.env.example`, logs ou mensagens de erro.

## Ativação

Para ativar o backup:

1. criar ou selecionar a pasta de destino;
2. produzir a credencial OAuth offline ou configurar um Shared Drive;
3. cadastrar os segredos no Render;
4. manter `GOOGLE_DRIVE_FOLDER_ID` como a pasta pai ou usar `root`;
5. habilitar `GOOGLE_DRIVE_ENABLED=true`.

O upload não substitui o SQLite nem passa a integrar o critério de sucesso da
sincronização.

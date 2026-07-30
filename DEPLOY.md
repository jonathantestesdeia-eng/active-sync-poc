# Deploy do Active Sync

## Render — homologação gratuita

O projeto expõe a aplicação FastAPI em `active_sync.api.app:app`. O CLI
permanece disponível em `main.py`; a publicação HTTP reutiliza o mesmo pipeline.

O `render.yaml` da raiz configura uma homologação gratuita da integração
SuperTrack (Netlify) → Active Sync API (Render):

- Web Service Python;
- plano gratuito (`free`);
- Python 3.12 pela `.python-version`;
- uma única instância;
- health check em `GET /health`;
- Uvicorn em `0.0.0.0` e na porta fornecida por `PORT`;
- SQLite e arquivos operacionais temporários em `/tmp/active-sync`;
- nenhum disco persistente ou serviço pago.

Comandos equivalentes para configuração manual:

```text
Build Command: pip install -r requirements.txt
Start Command: uvicorn active_sync.api.app:app --host 0.0.0.0 --port ${PORT:-8000}
```

O Render fornece `PORT` automaticamente. A expansão `${PORT:-8000}` mantém
`8000` como padrão quando a variável não estiver definida.

Esta configuração é exclusiva para homologação. O filesystem do serviço
gratuito do Render é efêmero. O SQLite e os arquivos baixados podem ser
perdidos em restart, redeploy, substituição da instância ou spin-down.

Para produção, mantenha a implementação SQLite existente e contrate um disco
persistente, ou configure futuramente um banco externo homologado. A
configuração gratuita não deve ser utilizada como base histórica definitiva.

No primeiro Blueprint, informe no painel do Render os valores marcados com
`sync: false`:

- `ACTIVE_SYNC_API_KEY`;
- `ACTIVE_SYNC_BUILD_DATE`;
- `ACTIVE_USER`;
- `ACTIVE_PASSWORD`;
- `ACTIVE_COMPANY_ID`;
- `ACTIVE_BRANCH_ID`;
- `ACTIVE_USER_CODE`, quando aplicável.

Nunca grave esses valores no `render.yaml`.

Rotas simplificadas:

- `GET /health`;
- `GET /tracking/{notaFiscal}`;
- `POST /sync` — sincronização incremental;
- `GET /status`.

As rotas operacionais existentes, como `POST /sync/run`,
`POST /sync/run-period` e `GET /sync/status`, foram preservadas.

## Pre-requisitos

- Python 3.12 ou superior;
- diretorio persistente e gravavel para o SQLite;
- proxy HTTPS ou rede privada;
- segredo compartilhado apenas com a Function server-side do SuperTrack.

## Producao

Configure pelo gerenciador de segredos do ambiente:

```dotenv
APP_ENV=production
ACTIVE_SYNC_API_KEY=<segredo-com-boa-entropia>
ACTIVE_SYNC_ALLOWED_ORIGINS=https://supertrack.example.com
ACTIVE_SYNC_DATABASE_PATH=C:/active-sync/data/active_sync.sqlite3
ACTIVE_SYNC_VERSION=0.2.0
ACTIVE_SYNC_BUILD_DATE=2026-07-22T19:00:00Z
ACTIVE_SYNC_SCHEDULE=08:00,12:00,18:00
ACTIVE_SYNC_FULL_START_DATE=2026-01-01
ACTIVE_SYNC_INITIAL_LOAD_MODE=current_month
ACTIVE_SYNC_INCREMENTAL_LOOKBACK_DAYS=7
ACTIVE_SYNC_RECOVERY_LOOKBACK_DAYS=14
ACTIVE_SYNC_WORK_DIR=C:/active-sync/runtime
ACTIVE_SYNC_CLIENT_REGISTER_PATH=C:/active-sync/config/cadastro-clientes.xlsx
ACTIVE_SYNC_CLIENT_REGISTER_SHEET=Planilha1
```

Nunca use `*` em CORS e nunca use prefixo `VITE_` para a API Key.

### Google Drive (backup opcional)

Enquanto `GOOGLE_DRIVE_ENABLED=false`, não configure pasta nem credenciais e o
serviço continua exatamente com o comportamento atual.

Para ativar no Render, prefira OAuth 2.0 de usuário para uma conta Google
pessoal. Armazene o JSON `authorized_user` como segredo em
`GOOGLE_DRIVE_CREDENTIALS_JSON` ou como Secret File apontado por
`GOOGLE_APPLICATION_CREDENTIALS`. Nunca use as duas opções simultaneamente.

```dotenv
GOOGLE_DRIVE_ENABLED=false
GOOGLE_DRIVE_FOLDER_ID=
GOOGLE_APPLICATION_CREDENTIALS=
GOOGLE_DRIVE_CREDENTIALS_JSON=
```

Consulte `docs/GOOGLE_DRIVE_STORAGE.md`. Nenhuma dessas variáveis utiliza
prefixo `VITE_`, pois credenciais e operações do Drive pertencem exclusivamente
ao serviço Python.

`GOOGLE_DRIVE_FOLDER_ID` representa a pasta pai onde será criada ou reutilizada
a estrutura `Active Sync/AAAA/MM`. Depois que o SQLite e o histórico forem
finalizados como sucesso, somente o ZIP validado é enviado em background.
Falhas do Drive não bloqueiam novas sincronizações nem alteram o histórico.

## Validacao

```powershell
python -m pytest -q
python -m uvicorn active_sync.api.app:app --host 127.0.0.1 --port 8000
curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:8000/health/database
curl.exe -H "X-API-Key: <segredo>" http://127.0.0.1:8000/performance?limit=1
```

Configure explicitamente o domínio operacional:

```dotenv
ACTIVE_SYNC_PROFILE=supertrack
```

Use `performance` somente em execuções da visão analítica. O perfil é
registrado em `sync_execution`. Validação operacional:

```powershell
curl.exe -H "X-API-Key: <segredo>" http://127.0.0.1:8000/tracking/1015048
```

## SuperTrack / Netlify

Variaveis privadas da Function:

```dotenv
APP_ENV=production
ACTIVE_SYNC_BASE_URL=https://active-sync.example.com
ACTIVE_SYNC_API_KEY=<o-mesmo-segredo>
ACTIVE_SYNC_TIMEOUT=10000
ALLOWED_ORIGIN=https://supertrack.example.com
```

Variaveis publicas do Vite:

```dotenv
VITE_ACTIVE_SYNC_PROXY_URL=/.netlify/functions/active-sync-proxy
VITE_ACTIVE_SYNC_TIMEOUT=10000
```

A Function `active-sync-proxy` encaminha a chave no servidor. A chave nunca
deve chegar ao JavaScript do navegador.

## Operacao

- rotacione a API Key simultaneamente nos dois servicos;
- monitore logs JSON por `request_id`;
- use `/health` para processo e `/health/database` para dependencia;
- mantenha backup do SQLite fora do diretorio servido;
- corrija qualquer variavel indicada antes de reiniciar um startup com falha.

## Agendador e concorrência

`ACTIVE_SYNC_SCHEDULE` usa horários locais no formato `HH:MM`, separados por
vírgula. Deixe vazio para desabilitar o agendador interno. Em produção, execute
uma única instância do processo enquanto o bloqueio for local ao processo; isso
garante que dois workers não iniciem sincronizações simultâneas. A API continua
retornando 409 para solicitações concorrentes na instância ativa.

O diretório de trabalho deve ser persistente, gravável e externo ao código
servido. O cadastro auxiliar, quando utilizado pela regra já homologada, é
informado por caminho absoluto. Monitore `sync_execution` e `/sync/status` para
falhas operacionais.

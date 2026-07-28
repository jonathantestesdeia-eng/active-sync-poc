# Active Sync API

Primeira API REST oficial do Active Sync, implementada com FastAPI na Sprint 15.

## Consulta operacional do SuperTrack

`GET /tracking/{nota_fiscal}` consulta a visão operacional independente de
Performance Entrega e retorna todos os movimentos não cancelados:

```json
{
  "success": true,
  "notaFiscal": "1015048",
  "total": 1,
  "movimentos": [
    {
      "movementId": "02561910000100|1|28340|1015048",
      "notaFiscal": "1015048",
      "cte": "28340",
      "serieCte": "1",
      "tipoCte": "DEVOLUCAO",
      "transportadora": "ATIVA",
      "destinatario": "SUPERMED",
      "situacao": "DEVOLVIDA"
    }
  ]
}
```

Sem movimentos, o endpoint retorna `404`. O contrato de
`/performance/{nota_fiscal}` permanece inalterado.
Consumidores externos, incluindo o SuperTrack, devem utilizar somente esta
fronteira HTTP.

## Arquitetura

```text
SuperTrack
    |
    v
FastAPI / Schemas Pydantic
    |
    v
Services
    |
    v
Repository
    |
    v
Persistence / SQLite
```

Rotas não instanciam dependências e não conhecem SQL, SQLite, Repository ou
Persistence. Elas recebem `PerformanceService` e `DashboardService` pelo sistema
de injeção do FastAPI.

## Inicialização

Instale as dependências:

```powershell
python -m pip install -r requirements.txt
```

Inicie o serviço a partir da raiz do projeto:

```powershell
python -m uvicorn active_sync.api.app:app --host 127.0.0.1 --port 8000
```

A documentação interativa ficará disponível em `/docs` e o contrato OpenAPI em
`/openapi.json`.

Por padrão, a API utiliza `data/active_sync.sqlite3`. O caminho pode ser definido
pela variável `ACTIVE_SYNC_DATABASE_PATH`.

## Injeção de dependências

`dependencies.py` é o composition root da aplicação:

```text
get_database()
    -> get_performance_repository()
        -> get_performance_service()
        -> get_dashboard_service()
```

Uma conexão é aberta por requisição, a migração idempotente é validada e a
conexão é fechada ao final. O composition root é o único ponto da API que conhece
as classes concretas das camadas inferiores. As rotas recebem somente Services.

Nos testes, `dependency_overrides` substitui os Services sem banco ou servidor.

## Rotas

### `GET /health`

Resposta `200`:

```json
{
  "status": "ok",
  "database": "ok",
  "api": "ok",
  "storage": "ok",
  "version": "0.3.0",
  "timestamp": "2026-07-23T14:00:00Z"
}
```

O health não consulta dados do negócio.

### `GET /system/status`

Retorna saúde geral, banco, perfil ativo, total consolidado de registros,
última sincronização, versão, ambiente e tempo de atividade em segundos.

### `GET /statistics`

Retorna total de movimentos, devoluções, cancelamentos auditados, primeira e
última sincronização, quantidade de execuções e falhas, tempo desde a última
execução e durações média, máxima e mínima.

### Histórico operacional

- `GET /sync/history?limit=100&offset=0`
- `GET /sync/history/{id}`

O histórico é ordenado da execução mais recente para a mais antiga. O detalhe
inclui período, arquivos, modo, contagens, resumo, erros, warnings, mensagens e
`reprocess_of_id`.

### `POST /sync/reprocess`

Informe exatamente uma das formas:

```json
{"start_date": "2026-07-01", "end_date": "2026-07-07"}
```

```json
{"file": "Conhecimento-CTe.xlsx"}
```

```json
{"sync_id": 42}
```

Arquivos devem existir em `ACTIVE_SYNC_WORK_DIR/imports`. A resposta é `202` e
possui o mesmo contrato dos demais endpoints de início de sincronização. O
bloqueio de concorrência retorna `409`.

### `GET /performance`

Parâmetros opcionais:

| Parâmetro | Tipo | Regra |
|---|---|---|
| `transportadora` | string | Correspondência exata. |
| `uf_destino` | string | Correspondência exata. |
| `cidade_destino` | string | Correspondência exata. |
| `prazo` | string | Correspondência exata. |
| `situacao` | string | Correspondência exata. |
| `periodo_inicio` | date | Data inicial de Saída, ISO `YYYY-MM-DD`. |
| `periodo_fim` | date | Data final de Saída, ISO `YYYY-MM-DD`. |
| `limit` | integer | De 1 a 1000; padrão 100. |
| `offset` | integer | Maior ou igual a zero. |
| `order_by` | string | Coluna homologada; padrão `Nota Fiscal`. |
| `descending` | boolean | Ordem decrescente; padrão `false`. |

Exemplo:

```http
GET /performance?transportadora=TRANS%20A&uf_destino=SP&limit=50&offset=0
```

A resposta `200` é uma lista de `PerformanceResponse`, com as 22 propriedades do
contrato em nomes JSON `snake_case`.

### `GET /performance/{nota_fiscal}`

Retorna uma lista porque Nota Fiscal ainda não é uma chave única homologada.
Quando não existe ocorrência, retorna `404`:

```json
{"detail": "Nota Fiscal não encontrada."}
```

### `GET /dashboard`

Resposta `200`:

```json
{
  "total_registros": 100,
  "total_atrasadas": 10,
  "total_em_aberto": 20,
  "total_entregues": 65,
  "total_devolvidas": 5,
  "percentual_atraso": 10.0,
  "percentual_entregues": 65.0,
  "percentual_devolvidas": 5.0
}
```

### Categorias do dashboard

- `GET /dashboard/transportadoras`
- `GET /dashboard/ufs`
- `GET /dashboard/cidades`

Resposta:

```json
[
  {"label": "SP", "count": 70},
  {"label": "MG", "count": 30}
]
```

## Schemas Pydantic

| Schema | Uso |
|---|---|
| `HealthResponse` | Disponibilidade do processo HTTP. |
| `PerformanceResponse` | Registro público com 22 campos. |
| `DashboardResponse` | Totais e percentuais consolidados. |
| `CategoryResponse` | Categoria e quantidade. |
| `ErrorResponse` | Mensagem pública segura. |

Entidades retornadas pelos Services são convertidas antes da resposta. Cursores,
linhas SQLite e objetos internos nunca são serializados diretamente.

## Códigos HTTP e erros

| Código | Situação |
|---:|---|
| `200` | Consulta concluída. |
| `404` | Nota Fiscal inexistente. |
| `422` | Parâmetros HTTP ou consulta inválidos. |
| `503` | Services indisponíveis ou falha interna de consulta. |

`ServiceError` e `DashboardError` são convertidos em respostas públicas sem a
mensagem interna. Um `InvalidQueryError` encapsulado pelo Service resulta em
`422`. Tracebacks e causas internas não são retornados ao cliente.

## Dependências de execução

- FastAPI;
- Pydantic;
- Uvicorn;
- HTTPX para testes HTTP.

## Segurança e ambientes (Sprint 17)

As rotas de dados são privadas e exigem `X-API-Key`. A comparação da chave usa
tempo constante e o backend pode ser substituído por JWT sem alterar as rotas.

Rotas públicas: `/health`, `/health/database`, `/health/version`, `/info` e a
documentação OpenAPI. Credencial ausente ou inválida retorna `401`. Origens fora
de `ACTIVE_SYNC_ALLOWED_ORIGINS` recebem `403`.

`/health/database` valida a conexão SQLite. `/health/version` retorna versão e
data de build. `/info` retorna versão, ambiente, build e banco utilizado.

Erros seguem um contrato único:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Parametros da requisicao invalidos",
    "request_id": "uuid"
  }
}
```

O header `X-Request-ID` é preservado ou gerado pela API. Logs são JSON nos
níveis INFO, WARNING, ERROR e DEBUG; DEBUG e traceback ficam restritos a
`development`.

| Variável | Finalidade |
|---|---|
| `APP_ENV` | `development`, `test` ou `production`. |
| `ACTIVE_SYNC_API_KEY` | Credencial privada, mínimo 16 caracteres. |
| `ACTIVE_SYNC_ALLOWED_ORIGINS` | Origens HTTP/HTTPS separadas por vírgula; `*` é proibido. |
| `ACTIVE_SYNC_DATABASE_PATH` | Caminho do SQLite. |
| `ACTIVE_SYNC_VERSION` | Versão publicada. |
| `ACTIVE_SYNC_BUILD_DATE` | Data do build; obrigatória em produção. |

O startup falha imediatamente se uma configuração obrigatória estiver ausente
ou inválida.

## Operação da base (Sprint 18)

Todas as rotas abaixo são privadas e exigem `X-API-Key`.

### Iniciar sincronização

`POST /sync/run`

```json
{"mode": "INCREMENTAL"}
```

`mode` aceita `INCREMENTAL` ou `FULL`. Para um intervalo explícito, use
`POST /sync/run-period`:

```json
{"start_date": "2026-07-01", "end_date": "2026-07-22"}
```

Resposta HTTP 202:

```json
{
  "status": "INICIADA",
  "request_id": "uuid",
  "started_at": "2026-07-22T10:00:00+00:00",
  "sync_type": "PERIODO"
}
```

Datas inválidas, invertidas ou futuras retornam 422. Se houver execução ativa,
a API retorna HTTP 409 com a mensagem `Já existe uma sincronização em execução.`

### Acompanhamento

- `GET /sync/status`: execução atual, última execução, próxima agenda, duração,
  quantidade processada e status final.
- `GET /sync/history?limit=100&offset=0`: histórico paginado.
- `GET /sync/history/{id}`: detalhes e contagens de uma execução.

O histórico é persistido em `sync_execution`. Além dos campos originais, cada
item informa:

- `start_date` e `end_date`;
- `source_files`;
- `records_cancelled`;
- `profile`.

As quantidades representam o UPSERT sobre a base histórica única. Um registro
ausente no relatório atual não é contado como cancelado nem removido.

O cabeçalho opcional `X-User` identifica o operador; quando ausente, a origem
usa o identificador padrão da integração. O agendador registra origem
`AGENDADA`, e solicitações HTTP registram `MANUAL`.

## Configuração administrativa do scheduler

Os endpoints privados abaixo são aditivos:

- `GET /scheduler/config`: restaura a configuração persistida.
- `PUT /scheduler/config`: ativa, desativa ou altera o horário diário.

```json
{
  "enabled": true,
  "time": "06:30"
}
```

A resposta inclui `frequency: "DAILY"`, o fuso fixo
`America/Sao_Paulo`, `updated_at` e `next_scheduled_at`. Quando ativado, o
horário é obrigatório e deve usar `HH:mm`. O scheduler inicia sempre o modo
`INCREMENTAL`; `PERIODO` e `FULL` permanecem exclusivamente manuais.

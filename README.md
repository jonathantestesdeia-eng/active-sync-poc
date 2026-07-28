# Active Sync POC

## Publicação HTTP

O mesmo motor utilizado pelo CLI é exposto pela aplicação FastAPI
`active_sync.api.app:app`. Para executar localmente com a mesma interface do
Render:

```powershell
python -m uvicorn active_sync.api.app:app --host 0.0.0.0 --port 8000
```

Em produção, o `render.yaml` utiliza a variável `PORT` fornecida pela
plataforma. Consulte [`DEPLOY.md`](DEPLOY.md) para variáveis, disco persistente
e comandos.

## Perfis de processamento

O Active Sync separa a visão operacional do SuperTrack da visão analítica de
Performance Entrega. Use `ACTIVE_SYNC_PROFILE=supertrack` para preservar todos
os CT-es não cancelados e consultar `GET /tracking/{nota_fiscal}`. O perfil
`performance` mantém as regras históricas e grava em `performance_entrega`.
Consulte [`docs/SUPERTRACK_PROFILE.md`](docs/SUPERTRACK_PROFILE.md).

## Base histórica consolidada

Cada relatório do Active é uma atualização parcial da mesma base
`supertrack_movements`. INCREMENTAL, PERÍODO e FULL fazem UPSERT pela chave
transportador + série CT-e + CT-e + NF. Registros antigos não são apagados
quando deixam de aparecer em um relatório; apenas cancelamentos explícitos do
Active removem a chave correspondente.

Configure uma janela deslizante com
`ACTIVE_SYNC_INCREMENTAL_LOOKBACK_DAYS=7` (ou outro período adequado).
Sobreposições e reprocessamentos são idempotentes. A auditoria fica em
`sync_execution`, com período, arquivos, contagens, duração, status e perfil.

## Operação e observabilidade

A Sprint 20 adiciona uma camada somente operacional, sem alterar Transformer,
Repository, Services, UPSERT ou os perfis homologados. A tela **Atualização da
Base** apresenta última e próxima execução, status, tempo, movimentos,
inseridos, atualizados, ignorados e cancelados.

Endpoints operacionais:

- `GET /health`: API, banco, storage, versão e timestamp;
- `GET /system/status`: perfil, volume consolidado, uptime e última execução;
- `GET /statistics`: volumes e métricas agregadas de sincronização;
- `GET /sync/history` e `GET /sync/history/{id}`: auditoria paginada e detalhe;
- `POST /sync/reprocess`: período, arquivo controlado ou Sync ID.

Arquivos para reprocessamento devem ser colocados em
`ACTIVE_SYNC_WORK_DIR/imports`. O endpoint aceita somente `.xlsx` resolvido
dentro desse diretório. Reprocessamentos usam o mesmo pipeline e mantêm a
idempotência da base histórica.

Os logs HTTP e de sincronização são JSON estruturado. Toda execução possui
`request_id`, métricas, arquivo, modo, status e erro. A interface
`SyncNotifier` prepara eventos de conclusão, falha, arquivo inválido e banco
indisponível sem enviar mensagens externas nesta Sprint.

## Execucao segura por ambiente

A API carrega `.env`, depois `.env.<APP_ENV>`, e por ultimo as variaveis do
processo. A precedencia e: processo > arquivo do ambiente > arquivo base.

Copie o exemplo correspondente e defina uma API Key com no minimo 16
caracteres:

```powershell
Copy-Item .env.development.example .env.development
python -m uvicorn active_sync.api.app:app --host 127.0.0.1 --port 8000
```

As rotas `/health`, `/health/database`, `/health/version` e `/info` são
públicas. Status, estatísticas, sincronização, Performance e dashboard exigem
o header `X-API-Key`. Consulte
`API.md` para o contrato e `DEPLOY.md` para producao.

Prova de conceito local em Python para autenticar no Active OnSupply, solicitar um relatório de Conhecimento/CT-e, acompanhar o processamento, baixar e validar o ZIP, extrair o Excel e inspecionar os dados sem depender do Microsoft Excel.

## O que o projeto faz

1. Lê configurações do `.env`.
2. Autentica e valida o cookie `sessionID`.
3. Seleciona empresa, filial e perfil.
4. Valida a sessão operacional em uma rota protegida.
5. Confirma um intervalo de emissão de até 7 dias.
6. Solicita `Conhecimento - CTe` no formato “Planilha Excel com Nota Fiscal”.
7. Consulta a grade assíncrona em intervalo moderado.
8. Identifica a linha correta por nome, formato, usuário e horário.
9. Baixa o ZIP por streaming, sem sobrescrever arquivos existentes.
10. Valida tamanho, assinatura e estrutura ZIP.
11. Extrai em pasta exclusiva, impedindo path traversal e links simbólicos.
12. Localiza um único `.xlsx` e o lê com `pandas`/`openpyxl`, usando `dtype=str`.
13. Exibe planilhas, registros, colunas e cinco linhas com dados sensíveis mascarados.

O serviço não usa Power Query, VBA ou COM. A aplicação operacional persiste em
SQLite, possui scheduler interno configurável e integra-se ao SuperTrack
exclusivamente pela API e pelo proxy server-side.

## Pré-requisitos

- Windows 11;
- Python 3.10 ou superior;
- acesso autorizado ao Active OnSupply.

## Instalação no PowerShell

```powershell
cd "C:\Users\SUPERMED\OneDrive\Documentos\Prova de conceito\active-sync-poc"
py -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Crie o `.env` apenas se ele ainda não existir:

```powershell
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
}
```

Nunca execute novamente `copy .env.example .env` depois de preencher credenciais, pois isso sobrescreve o arquivo.

## Configuração

Preencha no `.env`, no mínimo:

```dotenv
ACTIVE_USER=
ACTIVE_PASSWORD=
ACTIVE_COMPANY_ID=
ACTIVE_BRANCH_ID=
ACTIVE_ACCESS_TYPE=C
ACTIVE_IS_DESTINATARIO=false
```

`ACTIVE_USER_CODE` deve permanecer vazio no fluxo atual. O JavaScript da tela copia a senha para o campo oculto `_code`; o programa reproduz essa chamada sem registrar o valor.

| Variável | Padrão | Finalidade |
|---|---|---|
| `ACTIVE_BASE_URL` | `https://activeonsupply.com.br` | Endereço base. |
| `ACTIVE_USER` | — | Usuário obrigatório. |
| `ACTIVE_PASSWORD` | — | Senha obrigatória. |
| `ACTIVE_USER_CODE` | vazio | Substituição opcional de `_code`. |
| `ACTIVE_COMPANY_ID` | — | Valor interno obrigatório da empresa. |
| `ACTIVE_BRANCH_ID` | — | Valor interno obrigatório da filial. |
| `ACTIVE_ACCESS_TYPE` | `C` | Perfil; `C` corresponde a CONTRATANTE. |
| `ACTIVE_IS_DESTINATARIO` | `false` | Indicador usado por `LogingCompany`. |
| `ACTIVE_FORMULARIO_ID` | `118` | Formulário Conhecimento/CT-e. |
| `ACTIVE_REPORT_CODE` | `118` | Código do relatório. |
| `ACTIVE_REPORT_NAME` | `Conhecimento - CTe` | Nome do relatório. |
| `ACTIVE_REPORT_FORMAT` | `Excel__NotaFiscal` | Formato interno, com dois sublinhados. |
| `ACTIVE_DATE_FROM` | vazio | Data inicial opcional, `DD/MM/AAAA`. |
| `ACTIVE_DATE_TO` | vazio | Data final opcional, `DD/MM/AAAA`. |
| `ACTIVE_POLL_INTERVAL_SECONDS` | `10` | Intervalo entre consultas. |
| `ACTIVE_REPORT_TIMEOUT_SECONDS` | `900` | Timeout total do polling. Pode ser ampliado para `1800`. |
| `ACTIVE_HTTP_TIMEOUT_SECONDS` | `60` | Timeout individual de HTTP. |
| `ACTIVE_REPORT_TIME_TOLERANCE_SECONDS` | `120` | Tolerância para relógio da grade. |

Para descobrir os valores internos sem gerar relatório:

```powershell
python main.py --discover-contexts
```

Se houver múltiplas empresas:

```powershell
python main.py --discover-contexts --company-id VALOR_INTERNO
```

## Execução

Validar somente login, contexto e sessão:

```powershell
python main.py --login-only
```

Executar o fluxo completo com confirmação manual:

```powershell
python main.py --date-from 21/07/2026 --date-to 21/07/2026
```

O relatório só é criado depois de digitar `SIM`. Para uma execução previamente revisada:

```powershell
python main.py --date-from 21/07/2026 --date-to 21/07/2026 --yes
```

Sem datas na CLI ou no `.env`, o programa usa somente a data atual. Intervalos maiores que 7 dias são recusados nesta POC.

Retomar um relatório existente sem criar outro:

```powershell
python main.py --poll-report-id ID_DA_GRADE
```

Esse modo acompanha o ID, baixa o ZIP quando disponível, extrai e lê o Excel. `--keep-files` preserva temporários em caso de erro.

## Testes offline

```powershell
python -m pytest -q
```

Os testes usam respostas e arquivos artificiais. Eles não acessam o Active nem utilizam o `.env` real.

## Estrutura

```text
active-sync-poc/
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── main.py
├── active_sync/
│   ├── __init__.py
│   ├── auth.py
│   ├── client.py
│   ├── config.py
│   ├── downloader.py
│   ├── excel_reader.py
│   ├── exceptions.py
│   ├── extractor.py
│   ├── logger.py
│   ├── report_grid.py
│   ├── reports.py
│   └── transformer/
│       ├── __init__.py
│       ├── columns.py
│       ├── comparator.py
│       ├── exporter.py
│       ├── mapping.py
│       ├── normalization.py
│       ├── reconciliation.py
│       ├── returns.py
│       ├── schema.py
│       ├── situation.py
│       ├── snapshot_validator.py
│       ├── transforms.py
│       └── validator.py
├── downloads/
├── extraidos/
├── logs/
└── tests/
    └── fixtures/
```

A visão arquitetural completa, incluindo pipeline, responsabilidades e dependências, está em `docs/ARCHITECTURE.md`.

## Logs e dados sensíveis

Os logs ficam em `logs/active-sync-AAAAMMDD.log`. Senha, cookie, URL completa de download e cabeçalhos sensíveis não são registrados. A prévia mascara documentos, chaves, protocolos, partes, usuários, endereços e sequências longas de identificadores.

Erros comuns:

- variável ausente: revise o `.env`;
- retorno à tela de login: contexto não aceito ou fluxo alterado;
- relatório em processamento: aguarde ou retome pelo ID;
- erro de processamento: não repita automaticamente;
- múltiplos candidatos: analise os IDs mostrados;
- timeout: o ID é preservado e pode ser retomado;
- ZIP inválido: o arquivo final não é criado;
- mais de um Excel: a execução para sem escolher silenciosamente;
- `.xls`: exige tratamento adicional e não instala dependências antigas automaticamente.

## Limpeza dos testes

Feche qualquer programa que esteja usando os arquivos e remova apenas as pastas de saída do projeto:

```powershell
Remove-Item -LiteralPath .\downloads -Recurse -Force
Remove-Item -LiteralPath .\extraidos -Recurse -Force
Remove-Item -LiteralPath .\logs -Recurse -Force
```

Elas serão recriadas quando necessárias. Esses comandos não removem o `.env`.

## Limitações e segurança

- O fluxo depende de endpoints observados e pode mudar sem aviso.
- O Active permite apenas um processamento concorrente em determinados contextos.
- O serviço pode demorar e pode enfileirar um relatório mesmo retornando `Internal Server Error`; por isso a grade é consultada antes de qualquer repetição.
- O formato interno atual é `Excel__NotaFiscal`; `Excel_NotaFiscal` causa erro.
- A POC deve ser executada manualmente com intervalos pequenos.
- Não há retries agressivos, múltiplos relatórios simultâneos ou tentativa de contornar CAPTCHA.

> Este projeto reproduz chamadas observadas na interface web do Active OnSupply e não utiliza uma API pública oficialmente documentada. Antes de uso contínuo em produção, validar autorização e limites com a área responsável e/ou fornecedor.

## Sprint Transformer — layout Performance Entrega

A camada `active_sync.transformer` transforma um `DataFrame` bruto sem depender da origem do arquivo. O contrato final entrega exatamente 22 colunas, preserva a ordem oficial e não contém colunas provisoriamente preenchidas com `None`.

Uso em Python:

```python
from pathlib import Path
import pandas as pd

from active_sync.transformer import export_validation_excel, transform_dataframe

bruto = pd.read_excel("relatorio_active.xlsx", dtype=str, engine="openpyxl")
tratado = transform_dataframe(bruto)
export_validation_excel(tratado, Path("performance_validacao.xlsx"))
```

Mapeamentos, contrato de colunas, normalizadores, validação e exportação estão separados em `active_sync/transformer/`. Nesta sprint não há filtros, deduplicação, indicadores, índices ou cálculos de prazo/situação.

Mapeamentos e regras implementados: `CNPJ`, `Destinatário`, `Cidade Origem`, `Cidade Destino`, `UF Destino`, `Nota Fiscal`, `Valor Frete`, `Saída`, `Previsão`, `Entrega`, `Transportadora` (origem `Transportador`), `Código cliente`, `Prazo`, `Data`, `Ano`, `Prazo2`, `Data3`, `Ano4`, `Tipo CTe`, `Flag Devolução NF`, `CTe Devolução` e `Situação` (origem lógica `Situação Active`).

`Data3` copia `Data` e `Ano4` copia `Ano`, conforme igualdade integral nas 1.076 linhas da referência. A regra de devolução está implementada, mas aguarda um caso real positivo. A referência `teste.junho.xlsx` não possui `Situação`, portanto essa regra é validada pela consulta oficial e por testes sintéticos.

O contrato persistente está em `active_sync/transformer/schema.py` e sua documentação gerada em `docs/SCHEMA.md`. Ele fornece metadados e DDL para SQLite/PostgreSQL sem abrir conexões ou acessar bancos.

## Sprint 2 — equivalência com o Power Query

O comparador mede estrutura, equivalência por coluna e divergências célula a célula. Quando os arquivos estiverem em ordens diferentes, o alinhamento deve ser solicitado explicitamente por uma chave:

```python
import pandas as pd

from active_sync.transformer import compare_dataframes, write_comparison_report

resultado_python = pd.read_excel("performance_validacao.xlsx")
resultado_powerquery = pd.read_excel("teste.junho.xlsx")

relatorio = compare_dataframes(
    resultado_python,
    resultado_powerquery,
    key_columns=["Nota Fiscal"],
)
write_comparison_report(relatorio, "docs/equivalencia_detalhada.txt")
```

O relatório diferencia equivalência de valores, divergências estruturais, cobertura de campos preenchidos e equivalência restrita às linhas temporalmente comparáveis. Isso evita considerar como validada uma coluna que coincide apenas porque está vazia nos dois arquivos ou penalizar uma regra correta por snapshots comprovadamente diferentes. O histórico e a medição atual ficam em `docs/EQUIVALENCIA.md`.

## Sprint 3 — reconciliação do dataset

A reconciliação deve ocorrer sobre o DataFrame bruto, antes de `transform_dataframe`:

```python
import pandas as pd

from active_sync.transformer import reconcile_datasets, transform_dataframe

bruto = pd.read_excel("relatorio_active.xlsx", dtype=object)
referencia = pd.read_excel("teste.junho.xlsx", sheet_name="Performance Entrega")

bruto_reconciliado, relatorio = reconcile_datasets(bruto, referencia)
tratado = transform_dataframe(bruto_reconciliado)

assert relatorio.is_reconciled
```

As regras são inferidas das notas efetivamente mantidas pela referência e aplicadas sem listas fixas de Nota Fiscal ou CTe. A evidência completa fica em `docs/RECONCILIACAO.md`.

## Sprint 4 — CNPJ

`build_cnpj()` extrai o prefixo numérico de `Destinatário`, remove a formatação e reproduz a remoção de zeros iniciais observada no Power Query. O retorno permanece textual.

```python
from active_sync.transformer import build_cnpj

cnpj = build_cnpj(bruto["Destinatário"])
```

Na base reconciliada, a regra atingiu 1.076 de 1.076 valores iguais ao Power Query. Nenhuma outra coluna de negócio foi alterada nesta sprint.

## Sprint 18 — operação e agendamento

A API reutiliza um único pipeline operacional para os modos `INCREMENTAL`,
`PERIODO` e `FULL`. Execuções manuais e agendadas são serializadas por um
coordenador: uma segunda solicitação durante uma execução recebe HTTP 409.

O agendamento diário aceita múltiplos horários em `ACTIVE_SYNC_SCHEDULE`,
separados por vírgula. Cada execução registra início, fim, duração, origem,
usuário, contagens e erro na tabela `sync_execution` do mesmo banco configurado,
sem modificar Repository, Services ou as regras homologadas do transformador.
As cargas usam a Nota Fiscal como identidade do dataset reconciliado: registros
novos são inseridos, valores alterados são atualizados e linhas idênticas são
ignoradas, com contagens separadas no histórico.

Rotas privadas: `POST /sync/run`, `POST /sync/run-period`, `GET /sync/status`,
`GET /sync/history` e `GET /sync/history/{id}`. Consulte `API.md` e `DEPLOY.md`
para contratos e configuração.

## Agendamento administrado pelo SuperTrack

O SuperTrack restaura e salva a configuração diária pelos endpoints aditivos
`GET /scheduler/config` e `PUT /scheduler/config`. A configuração fica
persistida na tabela singleton `scheduler_configuration` e sobrevive à
reinicialização do processo. `ACTIVE_SYNC_SCHEDULE` é usado somente para
inicializar a configuração na primeira execução.

O fuso é fixo em `America/Sao_Paulo`. Alterações acordam o scheduler e atualizam
imediatamente `GET /sync/status.next_scheduled_at`. Toda execução automática
continua obrigatoriamente no modo `INCREMENTAL`; salvar não dispara uma
sincronização.

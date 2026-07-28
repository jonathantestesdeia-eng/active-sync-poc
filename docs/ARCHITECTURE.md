# Arquitetura do Active Sync POC

## Perfis operacionais e analíticos

O composition root seleciona uma estratégia centralizada a partir de
`ACTIVE_SYNC_PROFILE`. `SuperTrackProfile` produz e persiste a visão ampla em
`supertrack_movements`; `PerformanceProfile` mantém o Transformer, a
reconciliação e `performance_entrega` homologados. Não existem condicionais de
domínio espalhadas pelas camadas.

O fluxo de consulta operacional é
`Excel bruto → SuperTrackProfile → supertrack_movements → SuperTrackRepository
→ SuperTrackService → GET /tracking/{nf}`. A identidade persistente é
`transportador_id + serie_cte + cte + nota_fiscal`.

## Base histórica consolidada

O relatório Active é tratado como delta parcial, nunca como representação
completa da operação. A persistência executa UPSERT em lote na mesma
`supertrack_movements`. A ausência de uma chave em INCREMENTAL, PERÍODO ou
FULL não altera o registro histórico.

```text
Janela atual ──► normalização ──► chaves compostas
                                      │
                 ┌────────────────────┼────────────────────┐
                 ▼                    ▼                    ▼
              INSERT               UPDATE              IGNORE
             chave nova       valores alterados     mesma versão
                 └────────────────────┼────────────────────┘
                                      ▼
                         Base histórica única
```

As chaves existentes são carregadas em lotes e as gravações usam
`executemany`. Cancelamentos são tombstones explícitos do Active e removem
somente a identidade operacional correspondente. A auditoria de cada execução
é persistida em `sync_execution`.

Atualizado em 22/07/2026 durante a Sprint 15.

## Visão geral

O projeto possui seis áreas desacopladas:

1. sincronização com o Active OnSupply, responsável por autenticar, solicitar, acompanhar, baixar, validar e extrair o relatório;
2. transformação de dados, responsável por reconciliar o universo de registros e reproduzir o resultado funcional do Power Query;
3. persistência, responsável por armazenar o contrato final no SQLite sem introduzir regras de negócio;
4. repository, responsável por todas as consultas de leitura parametrizadas;
5. services, responsável por coordenar consultas e produzir indicadores para consumidores externos;
6. API, responsável por expor os Services em contratos HTTP validados.

A camada `active_sync.transformer` recebe DataFrames e não depende de HTTP, sessão do Active, arquivos ZIP, banco de dados, interface gráfica ou API do SuperTrack.

## Pipeline completo

```text
Configuração e credenciais
        │
        ▼
Autenticação e seleção de contexto
        │
        ▼
Solicitação e acompanhamento do relatório
        │
        ▼
Download e validação do ZIP
        │
        ▼
Extração e leitura do Excel bruto
        │
        ▼
Snapshot Validator ──► diagnóstico de compatibilidade temporal
        │
        ▼
Dataset Reconciliation ──► universo de registros equivalente
        │
        ▼
Transformer ──► DataFrame no contrato Performance Entrega
        │
        ├──► Validator
        ├──► Comparator
        ├──► Excel opcional de validação
        └──► Persistence ──► SQLite / performance_entrega
                                  │
                                  ▼
                              Repository
                                  │
                                  ▼
                               Services
                                  │
                                  ▼
                                FastAPI
```

O Snapshot Validator é não destrutivo: ele diagnostica os arquivos, mas não remove linhas nem altera datas. A reconciliação ocorre sobre o bruto antes da transformação. O comparador recebe os resultados finais e separa equivalência global de equivalência temporalmente comparável.

## Módulos de sincronização

| Módulo | Responsabilidade |
|---|---|
| `config.py` | Carregar e validar configurações do ambiente. |
| `auth.py` | Autenticar e obter a sessão inicial. |
| `client.py` | Manter a sessão HTTP e selecionar o contexto operacional. |
| `reports.py` | Preparar e solicitar relatórios. |
| `report_grid.py` | Interpretar a grade assíncrona e localizar solicitações. |
| `downloader.py` | Baixar e validar arquivos ZIP sem sobrescrita silenciosa. |
| `extractor.py` | Extrair arquivos com proteção contra caminhos inseguros. |
| `excel_reader.py` | Localizar e ler o Excel extraído. |
| `logger.py` | Configurar logs sem exposição de dados sensíveis. |
| `exceptions.py` | Exceções específicas dos fluxos do projeto. |

## Módulos do transformer

| Módulo | Responsabilidade |
|---|---|
| `columns.py` | Contrato imutável de colunas, ordem e categorias de tipo. |
| `mapping.py` | Nomes de origem, mapeamentos e constantes de regras comprovadas. |
| `normalization.py` | Normalização reutilizável de nulos, textos, identificadores, datas e números. |
| `returns.py` | Regra oficial de devolução: sinais por linha, agrupamento por Nota Fiscal, Flag, CTe agregado e Tipo CTe. |
| `schema.py` | Fonte única do contrato final, classificações, tipos pandas/SQL, nulabilidade, origem, dependências e DDL declarativo. |
| `situation.py` | Regra temporal de `Situação Active`, com data de referência injetável para testes determinísticos. |
| `transforms.py` | Funções públicas de negócio e composição do DataFrame tratado. |
| `validator.py` | Validação estrutural da entrada e da saída. |
| `snapshot_validator.py` | Diagnóstico não destrutivo da compatibilidade temporal. |
| `reconciliation.py` | Inferência e aplicação das regras que definem o universo de registros. |
| `comparator.py` | Comparação estrutural e funcional, global e temporalmente comparável. |
| `exporter.py` | Exportação opcional do Excel de validação. |
| `__init__.py` | Superfície pública estável da camada. |

## Módulos de persistência

| Módulo | Responsabilidade |
|---|---|
| `database.py` | Gerenciar conexão, SQL, transações, commit e rollback. |
| `migrations.py` | Criar e validar a tabela por meio exclusivo de `transformer.schema`. |
| `writer.py` | Persistir o DataFrame de modo atômico e idempotente. |
| `exceptions.py` | Expor erros específicos de conexão, migração e persistência. |
| `__init__.py` | Superfície pública da camada. |

A persistência não é importada pelo Transformer e não depende de arquivos ou
componentes de comparação. Sua única dependência interna permitida é
`transformer.schema`, usada para obter nomes, ordem, tipos, nulabilidade e DDL.

## Módulos do Repository

| Módulo | Responsabilidade |
|---|---|
| `models.py` | Representar registros e filtros derivados do contrato oficial. |
| `performance_repository.py` | Concentrar consultas, filtros, paginação e ordenação seguras. |
| `exceptions.py` | Traduzir falhas e rejeitar consultas inválidas. |
| `__init__.py` | Superfície pública da camada. |

O Repository usa o `DatabaseManager` para executar leituras e não abre conexões
diretamente. Ele depende apenas da API da Persistence, dos próprios modelos e de
`transformer.schema`. Persistence e Transformer não conhecem o Repository.

## Módulos dos Services

| Módulo | Responsabilidade |
|---|---|
| `performance_service.py` | Coordenar consultas e expor DTO de filtros para consumidores. |
| `dashboard_service.py` | Calcular contagens, percentuais e distribuições. |
| `exceptions.py` | Impedir que erros internos atravessem a fronteira de aplicação. |
| `__init__.py` | Superfície pública da camada. |

Services importa apenas a API pública de Repository. Não conhece banco,
Persistence, Transformer, DataFrames ou SQL. Repository, Persistence e
Transformer não possuem dependência reversa para Services.

## Módulos da API

| Módulo | Responsabilidade |
|---|---|
| `app.py` | Criar e configurar a aplicação FastAPI. |
| `dependencies.py` | Compor DatabaseManager, Repository e Services por requisição. |
| `routes.py` | Expor rotas que consomem somente Services. |
| `schemas.py` | Validar e serializar contratos HTTP Pydantic. |
| `exceptions.py` | Traduzir erros de aplicação em respostas HTTP seguras. |
| `__init__.py` | Superfície pública da aplicação. |

`dependencies.py` funciona como composition root exigido pela injeção. Fora
desse ponto de montagem, a API depende apenas dos Services. Nenhuma camada
inferior importa a API e nenhuma rota contém SQL ou acessa banco diretamente.

## Fluxo de dados do transformer

1. O Excel bruto é lido como DataFrame preservando identificadores.
2. O Snapshot Validator alinha os dados por Nota Fiscal e registra evidências de `Saída`, `Previsão` e `Entrega`.
3. A reconciliação aplica somente regras justificadas pelos dados e entrega o mesmo multiconjunto de registros da referência.
4. `transform_dataframe()` percorre o contrato de saída e delega cada regra às funções públicas específicas.
5. O validador confirma nomes, ordem, duplicidades e tipos.
6. O comparador alinha por chave, normaliza valores de acordo com o tipo e produz métricas e divergências auditáveis.
7. O exportador pode gerar `performance_validacao.xlsx` sem participar das regras de negócio.

O contrato final contém 22 colunas. `Data3` reutiliza diretamente `Data`, `Ano4` reutiliza diretamente `Ano` e `Situação` permanece após `Ano4` como campo adicional preparado para rastreamento e persistência.

## Fluxo da devolução

Na consulta M, `ARUJA` e `CAMBUI` participam primeiro do cálculo da devolução. As linhas só são removidas em uma etapa posterior de `Table.SelectRows()`, depois do sinal, do agrupamento, da Flag e do CTe Devolução. Isso permite que essas linhas contribuam para a classificação da Nota Fiscal antes da exclusão do resultado final.

```text
Tipo + Observacao + Trecho ──► maiúsculas ──► contém DEVOLU? ──► Flag Texto
Cidade Destino ──► trim + maiúsculas ──► ARUJA/CAMBUI? ────────► Flag Destino
                                     │
                                     ▼
                  Flag Texto OU Flag Destino
                                     │
                                     ▼
                         CTe Devolução Candidato
                                     │
                                     ▼
                Agrupamento por Nota Fiscal
                ├── CT-es distintos da Nota
                ├── qualquer Flag Destino
                ├── qualquer Flag Texto
                └── CT-es candidatos distintos, na ordem
                                     │
                                     ▼
 Flag NF = Texto OU (mais de um CTe E Destino)
                ├── Tipo CTe = DEVOLUCAO
                ├── CTe Devolução = CT-es candidatos agregados
                └── Prazo = DEVOLVIDA
                                     │
                                     ▼
       Table.SelectRows remove Cidade Destino ARUJA/CAMBUI
```

Se a Flag for falsa, `Tipo CTe` conserva `Tipo`, `CTe Devolução` fica nulo e Prazo segue a classificação temporal. A precedência de Prazo é: devolução; Entrega ausente; Previsão ausente; Entrega até a Previsão; Entrega após a Previsão.

## Fluxo de Situação

`build_situacao()` reproduz a coluna `Situação Active` da consulta M. `Hoje` corresponde à data civil de `DateTime.LocalNow()` capturada na atualização; a função aceita essa data explicitamente nos testes.

```text
Flag Devolução NF = true ──► DEVOLVIDA
senão, Entrega preenchida ──► ENTREGUE
senão, Previsão ausente ────► SEM PREVISÃO
senão, Previsão < Hoje ─────► ATRASADA
senão, Previsão = Hoje ─────► PREVISTA PARA HOJE
senão ──────────────────────► EM ABERTO
```

## Princípios arquiteturais

- **DataFrame como contrato:** as regras não dependem de um caminho de arquivo específico.
- **Nomes centralizados:** colunas e constantes não ficam espalhadas pelo projeto.
- **Funções pequenas e puras:** cada regra recebe séries ou tabelas explícitas e devolve novo resultado.
- **Validação antes de comparação:** incompatibilidade de snapshot é diagnosticada antes da equivalência funcional.
- **Ausência de correções artificiais:** datas, registros e identificadores não são apagados para elevar percentuais.
- **Dependências explícitas:** o cadastro de clientes é fornecido ao transformador, não localizado internamente.
- **Evidência antes de regra:** nenhuma regra de negócio é implementada sem casos que permitam confirmá-la e refutar alternativas.
- **Compatibilidade pública:** utilitários podem ser reorganizados internamente sem quebrar as funções já expostas.

## Dependências entre componentes

```text
columns ───────────────┐
mapping ───────────────┤
normalization ─────────┼──► returns ───────► transforms ───► validator
normalization ─────────┼──► situation ─────► transforms
                       │
normalization ─────────┼──► comparator ───► snapshot_validator
                       │
reconciliation ────────┘

transformer/__init__ ──► superfície pública
exporter ──────────────► validator + contrato de colunas
schema ────────────────► columns + SCHEMA.md + DDL declarativo
```

`normalization.py` foi criado na Sprint 8.1 para remover a duplicação da normalização de nulos e impedir que o comparador dependa do módulo de regras de negócio apenas para converter valores.

## Resultado da revisão arquitetural

- a normalização de nulos duplicada entre transformador e Snapshot Validator foi consolidada;
- o comparador passou a depender diretamente do módulo de normalização;
- as assinaturas públicas existentes foram preservadas;
- as funções de negócio protegidas permaneceram inalteradas;
- responsabilidades de contrato, normalização, regra, validação, comparação e exportação ficaram explicitamente documentadas;
- 104 testes confirmaram ausência de mudança funcional.

Ainda existem normalizações privadas específicas em reconciliação, comparação e Snapshot Validator. Elas possuem semânticas próprias de alinhamento ou apresentação e não foram unificadas nesta revisão para evitar mudança comportamental indireta.

## Camada operacional e observabilidade — Sprint 20

```text
Scheduler / API / Reprocessamento
              │
              ▼
       SyncCoordinator
        │            │
        │            ├──► logs JSON + request_id
        │            ├──► SyncNotifier
        │            └──► sync_execution
        ▼
OperationalSyncPipeline único
        │
        └──► perfis e UPSERT homologados (inalterados)

OperationalObservability
        ├──► health de API, SQLite e storage
        ├──► status, uptime e perfil
        └──► estatísticas agregadas
```

`OperationalObservability` é somente leitura. Ele não utiliza Transformer,
Repository ou Services de negócio. O health executa apenas `SELECT 1` e verifica
o diretório operacional; não lê movimentos.

`SyncReprocessor` aceita exatamente um seletor:

- período: inicia o modo `PERIODO`;
- arquivo: aceita `.xlsx` apenas dentro de `runtime/imports`;
- Sync ID: reutiliza o arquivo armazenado quando disponível, senão o período
  auditado, e mantém o vínculo `reprocess_of_id`.

Em todos os casos a execução converge para `SyncCoordinator` e
`OperationalSyncPipeline`. Não existe pipeline alternativo nem lógica de
persistência duplicada.

`sync_execution` armazena período, arquivos, tempos, contagens, mensagem de
erro, warnings, mensagens operacionais e vínculo do reprocessamento. A leitura
é paginada e ordenada por ID decrescente.

`SyncNotifier` é uma porta interna preparada para e-mail, webhook ou
mensageria. Nesta Sprint, `LoggingSyncNotifier` registra somente eventos de
conclusão, falha e arquivo inválido.

## Limites atuais

- o par de arquivos disponível permanece classificado como `TEMPORAL_MISMATCH`;
- `Situação` está implementada a partir de `Situação Active`; o arquivo tratado disponível não contém essa coluna e termina em `Ano4`, impedindo equivalência direta;
- `Data3` e `Ano4` estão implementadas e atingem 100,00% nas linhas temporalmente comparáveis;
- a regra da Sprint 9 foi implementada a partir da consulta M oficial, mas sua validação funcional positiva requer um par bruto/tratado com ao menos uma devolução;
- SQLite, PostgreSQL, API e interface continuam fora desta fase.

## Preparação para persistência

`schema.py` não importa drivers nem abre conexões. Ele descreve cada coluna com nome, tipo pandas, tipo SQLite, tipo PostgreSQL, nulabilidade, descrição, origem, regra, dependências e classificação de implementação.

```text
TRANSFORMER_SCHEMA
        ├──► columns.py ──► ordem e categorias de dtype
        ├──► SCHEMA.md ───► documentação gerada
        ├──► sqlite_ddl() ─► CREATE TABLE declarativo
        └──► postgresql_ddl() ─► CREATE TABLE declarativo
```

Datas serão serializadas em ISO no SQLite e persistidas como `DATE` no PostgreSQL. Identificadores permanecem `TEXT`; booleanos usam `INTEGER` no SQLite e `BOOLEAN` no PostgreSQL. A criação de conexões, migrações e repositórios pertence à próxima fase.

## Revisão arquitetural da Sprint 11

- `columns.py` passou a derivar ordem e categorias de tipo do contrato único, eliminando listas paralelas.
- O ramo provisório para colunas sem origem foi removido de `transforms.py`.
- O import não utilizado `preserve_identifier` foi removido.
- `Data3` e `Ano4` copiam resultados já calculados, evitando duplicação das regras homologadas.
- Não foram alterados Snapshot Validator, Comparator, Dataset Reconciliation, `returns.py`, `situation.py` ou as funções protegidas.
- A inspeção de imports e a suíte completa não identificaram ciclos ou regressões.

## Revisão arquitetural da Sprint 10

A nova regra foi isolada em `situation.py`, em vez de ampliar o módulo de composição. O módulo depende somente de `mapping.py` e `normalization.py`; `transforms.py` apenas orquestra a chamada e `__init__.py` mantém a superfície pública. Não foram encontradas dependências circulares.

As normalizações privadas do comparador, Snapshot Validator e reconciliação continuam intencionalmente separadas porque possuem semânticas diferentes. Uma consolidação adicional aumentaria o risco de alterar regras homologadas. Nenhuma outra refatoração foi necessária nesta Sprint.

## Configuração dinâmica do scheduler

`SchedulerConfigurationStore` mantém uma única configuração diária no banco
operacional. `SchedulerConfigurationService` é a fronteira usada pela API e
comunica alterações ao `SyncScheduler` por evento, sem reiniciar o processo e
sem duplicar o pipeline.

```text
SuperTrack
    -> GET/PUT /scheduler/config
    -> SchedulerConfigurationService
    -> scheduler_configuration
    -> SyncScheduler.update_schedule()
    -> SyncCoordinator(INCREMENTAL, origem AGENDADA)
```

O coordenador existente continua impedindo concorrência. Não há caminho
agendado para `PERIODO` ou `FULL`. `ACTIVE_SYNC_SCHEDULE` atua apenas como
valor inicial quando ainda não existe configuração persistida.

O SuperTrack mantém separação entre rascunho e configuração persistida. O card
e o resumo operacional formatam, sem recalcular, `next_scheduled_at` e
`updated_at` retornados pelo Active Sync. Falha na consulta invalida a
apresentação anterior e produz o estado `Indisponível`.

## Camada visual de normalização de rastreamento

O SuperTrack passa a utilizar uma camada de normalização de eventos, desacoplando completamente a interface das nomenclaturas específicas de cada transportadora.

Essa camada pertence exclusivamente ao frontend do SuperTrack e é executada
depois do contrato homologado dos providers:

```text
Provider
   -> rastreamento original
   -> trackingEventNormalizer
   -> contrato visual comum
   -> resumo amigável + linha do tempo
```

O contrato visual contém `status_original`, `status_normalizado`, `unit_code`,
`unit_name`, `city`, `state`, `description_original`, `display_title` e
`display_subtitle`. Os dados originais são preservados; os valores normalizados
servem apenas à apresentação.

Não há alteração em Active Sync, APIs, providers, Scheduler, banco, UPSERT,
histórico ou regras de negócio. A tradução de unidade só ocorre quando há
mapeamento seguro. O histórico é ordenado do evento mais recente para o mais
antigo e exibido como lista semântica, mantendo a descrição original para
auditoria.

## Módulo 3 — Arquitetura de Tracking Providers

O SuperTrack não seleciona parsers nem interpreta respostas específicas de
transportadoras. Toda consulta atravessa o registro de providers e termina no
`Tracking Contract 1.0`.

```text
SuperTrack
    |
    v
/.netlify/functions/track
    |
    v
Provider Registry <----- catálogo de aliases
    |
    +--> AtivaTrackingProvider
    |       consultar -> parseSswTracking -> normalizar -> validar
    |
    +--> ProviderTragetta
    |       API Solística -> parseTragettaTracking -> normalizar -> validar
    |
    +--> FunctionTrackingProvider
            MINUANO / VIA MINAS
            consultar legado -> normalizar -> validar
    |
    v
Tracking Contract 1.0
    |
    v
Apresentação comum + timeline
```

### Ciclo obrigatório

`TrackingProvider.execute()` orquestra quatro responsabilidades:

1. `consultar(request)` acessa a fonte externa;
2. `parse(response, request)` extrai os dados sem regras visuais;
3. `normalizar(parsed, request)` cria o modelo canônico;
4. `validar(tracking)` impede uma resposta incompleta de chegar à interface.

O `FunctionTrackingProvider` oferece transição segura para conectores
funcionais já homologados. Ele não constitui um segundo contrato: sua saída é
normalizada e validada exatamente pela mesma fronteira. Novos providers devem
estender `TrackingProvider`.

### Contrato único

O objeto `tracking` possui:

- `transportadora`, `notaFiscal`, `pedido` e `previsaoEntrega`;
- `statusOriginal`, `statusNormalizado`, `displayTitle` e `displaySubtitle`;
- `cidade`, `uf`, `unidade` e `codigoUnidade`;
- `eventos`, sempre como lista.

Cada evento contém `dataHora`, `statusOriginal`, `statusNormalizado`,
`descricaoOriginal`, `cidade`, `uf`, `unidade`, `codigoUnidade` e
`tipoEvento`.

Campos originais são preservados para auditoria. Campos normalizados são
gerados por `trackingNormalizer`, não pelo parser. A fronteira mantém aliases
legados apenas por compatibilidade aditiva; o frontend usa prioritariamente o
contrato canônico.

### Dependências

```text
parser da transportadora
        -> provider
        -> trackingNormalizer
        -> trackingContract
        -> handler HTTP
        -> SuperTrack
```

O catálogo compartilhado define suporte e aliases. O registro server-side
define a implementação executável. Assim, cadastrar um provider novo não exige
alterar componentes React nem o serviço de apresentação.

### Provider TRAGETTA

`ProviderTragetta` comprova que o contrato não depende do SSW. O provider usa a
API JSON já homologada do portal Solística e separa suas etapas:

```text
consultar
    -> getTragettaToken
    -> GET filtro por NF
    -> hidratação dos candidatos
    -> seleção por CT-e/tipo
    -> GET detalhes
    -> GET rastreamento

parse
    -> parseTragettaTracking
    -> campos originais + todos os eventos

normalizar
    -> trackingNormalizer
    -> statusNormalizado + displayTitle + displaySubtitle

validar
    -> Tracking Contract 1.0
```

O parser não conhece componentes React nem textos visuais. A seleção segura
entre conhecimento normal e devolução permanece na consulta porque determina
qual recurso remoto será buscado. O normalizador comum é o único responsável
pela apresentação canônica.

O registry armazena diretamente a instância de `ProviderTragetta`; não existe
mais `FunctionTrackingProvider` para essa transportadora. MINUANO e VIA MINAS
continuam temporariamente sob adapter. Essa troca é interna e não altera
endpoint, aliases ou estrutura HTTP.

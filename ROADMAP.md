# Roadmap Active Sync → SuperTrack

Atualizado em 22/07/2026.

## Fase 0 — POC de sincronização ✅

Concluída: autenticação, contexto operacional, solicitação, acompanhamento, download, extração e leitura do relatório Active.

## Fase 1 — Transformador Python

- Sprint 1 — Estrutura do transformador ✅
- Sprint 2 — Comparador de equivalência ✅
- Sprint 3 — Dataset Reconciliation ✅
- Sprint 4 — Primeira regra de negócio: CNPJ ✅
- Sprint 5 — Destinatário e Código Cliente ✅
- Sprint 6 — Transportadora e Entrega ✅ (conclusão técnica)
- Sprint 7 — Data e Ano ✅ (conclusão técnica)
- Sprint 8 — Prazo e Prazo2 ✅ (conclusão técnica)
- Sprint 9 — Flag Devolução NF e CTe Devolução 🟡 (implementação concluída; validação funcional pendente)
- Sprint 10 — Correções da Sprint 9.1 e regra Situação ✅
- Sprint 11 — Consolidação do Transformer e contrato persistente ✅
- Revisão arquitetural da Sprint 8.1 ✅

## Fase 2 — Persistence, Repository e Services

- Sprint 12 — SQLite, migrações e persistência idempotente ✅
- Sprint 13 — Repository, filtros e paginação ✅
- Sprint 14 — Services e indicadores do dashboard ✅

### Conclusão da Sprint 12

- Criada a camada `active_sync.persistence`, desacoplada das regras de negócio.
- `DatabaseManager` controla conexão, SQL, transações, commit e rollback.
- `MigrationManager` cria e valida `performance_entrega` diretamente pelo schema oficial.
- `persist_dataframe()` valida o contrato e converte datas, booleanos, nulos e escalares pandas para SQLite.
- A idempotência usa identidade integral e comparação nula-segura, sem exclusão destrutiva.
- Testes cobrem criação, migração, drift, tipos, nulos, rollback, contrato, dependências e carga repetida.

### Conclusão da Sprint 13

- Criados `PerformanceEntrega`, `PerformanceFilters` e `PerformanceRepository`.
- O modelo deriva nomes, ordem e aliases das 22 colunas de `schema.py`.
- Implementadas consultas por NF, transportadora, período, atraso, aberto e devolução.
- A listagem permite filtros combináveis, ordenação segura, `LIMIT` e `OFFSET` parametrizados.
- Valores externos nunca são concatenados ao SQL e a ordenação usa allowlist do schema.
- Repository lê pelo `DatabaseManager`; Persistence e Transformer não dependem dele.

### Conclusão da Sprint 14

- Criados `PerformanceService`, `DashboardService`, `PerformanceQuery` e `CategoryCount`.
- PerformanceService coordena exclusivamente os métodos públicos da Repository.
- DashboardService disponibiliza totais, percentuais e distribuições para o SuperTrack.
- Bases vazias retornam percentuais iguais a zero e não causam divisão por zero.
- Services não contém SQL nem importa SQLite, Persistence, Transformer, pandas ou Excel.
- Erros da Repository são traduzidos para exceções estáveis dos Services.

### Descobertas da Sprint 3

- O Excel bruto contém 1.106 registros e todos vieram do Active.
- O Power Query contém 1.076 registros.
- Antes da reconciliação existiam 30 ocorrências somente no Python e nenhuma somente no Power Query.
- Os tipos mantidos pela referência foram inferidos dos dados: `ENTREGA NORMAL` e `REENTREGA`.
- Registros sem `Saída` são removidos.
- Registros em que Destinatário e Tomador representam a mesma parte são removidos.
- Registros faturados sem aprovação financeira são removidos.
- Após aplicar as regras inferidas, o Python contém 1.076 registros e o multiconjunto de Notas Fiscais é idêntico ao Power Query.
- Nenhuma regra de Prazo, Prazo2, Situação, CNPJ, Código Cliente, Data ou Ano foi implementada.

Evidências detalhadas: `docs/RECONCILIACAO.md`.

### Descobertas da Sprint 4

- O CNPJ vem do prefixo numérico da coluna bruta `Destinatário`.
- Pontuação e texto descritivo são removidos.
- O Power Query remove zeros à esquerda em 194 registros; o Python reproduz essa normalização e mantém o resultado como texto.
- Os 1.076 valores de CNPJ foram preenchidos e atingiram 100,00% de equivalência.
- Redespacho, Consignatário, Remetente e Tomador foram descartados como origem do CNPJ.
- Nenhuma outra regra de negócio foi implementada.

Evidências detalhadas: `docs/EQUIVALENCIA.md`.

### Descobertas da Sprint 5

- `Destinatário` é a segunda parte da coluna bruta homônima após a divisão pelo delimitador `-`; a terceira parte é descartada, exatamente como no Power Query.
- Os 1.076 valores de Destinatário atingiram 100,00% de equivalência.
- `Código cliente` não existe no relatório bruto do Active.
- O código vem de um `LeftOuter Join` entre o CNPJ transformado e `Cnpj2` da aba `Planilha1` em `Base clientes.xlsx`.
- A base analisada possui 7.494 CNPJs únicos e nenhuma duplicidade de chave.
- Foram reproduzidos 1.013 códigos preenchidos e 63 nulos; as 1.076 linhas atingiram 100,00% de equivalência.
- As colunas comprovadas nas sprints anteriores permaneceram com 100,00% de equivalência.
- Nenhuma outra regra de negócio foi implementada.

Evidências detalhadas: `docs/EQUIVALENCIA.md`.

### Encerramento técnico da Sprint 6

- `build_transportadora()` foi implementada com o mapeamento ordenado usado pelo Power Query.
- Transportadora atingiu 1.076 de 1.076 linhas, com 100,00% de equivalência.
- `build_entrega()` foi implementada como conversão segura da coluna bruta `Entrega`, sem regra de negócio adicional.
- Os 621 valores de Entrega preenchidos no Power Query coincidem exatamente com o bruto.
- Existem 160 entregas preenchidas somente no arquivo bruto atual; não há datas preenchidas somente no Power Query nem datas diferentes entre os dois lados.
- A diferença foi identificada como temporal: os arquivos comparados representam snapshots distintos.
- Entrega atingiu 916 de 1.076 linhas, ou 85,13%.
- O Snapshot Validator foi implementado e integrado ao início do comparador.
- Os arquivos atuais foram classificados como `TEMPORAL_MISMATCH` com base no conteúdo alinhado.
- O modo estrito está disponível por `require_compatible_snapshot=True` e usa `IncompatibleSnapshotError`.
- O Snapshot Validator, o comparador e a reconciliação foram revalidados sem alterações artificiais nos dados.
- Foram aprovados 94 testes e não houve regressão nas colunas já concluídas.
- A Sprint foi encerrada tecnicamente: `build_transportadora()` e `build_entrega()` reproduzem o Power Query. A certificação temporal com este par de arquivos permanece impedida pelo `TEMPORAL_MISMATCH`, sem afetar a correção da implementação.

Evidências detalhadas: `docs/EQUIVALENCIA.md`.

### Descobertas da Sprint 7

- `Data` e `Ano` são derivadas exclusivamente da coluna bruta `Entrega`.
- `Data` contém o nome do mês em português e minúsculo, determinado por tabela interna e independente do locale do sistema.
- `Ano` contém o ano como inteiro anulável, sem produzir valores como `2026.0`.
- Nulos e datas inválidas em `Entrega` produzem nulos simultaneamente nas duas colunas.
- `Entrega`, `Saída`, `Previsão`, `Emissão`, `Data Inclusão` e todas as demais colunas temporais disponíveis foram comparadas; somente `Entrega` reproduz simultaneamente valores e padrão de preenchimento do Power Query.
- Com os snapshots atuais, `Data` e `Ano` atingiram 916 de 1.076 linhas, ou 85,13% global.
- Nas 916 linhas temporalmente comparáveis, ambas atingiram 100,00%; as 160 linhas excluídas são exatamente o `TEMPORAL_MISMATCH` já comprovado em `Entrega`.
- O comparador agora apresenta equivalência global e equivalência restrita às linhas temporalmente comparáveis, sem alterar o Snapshot Validator.
- Foram aprovados 94 testes e não houve regressão.

Evidências detalhadas: `docs/EQUIVALENCIA.md`.

### Encerramento definitivo da Sprint 7

- `build_data()` e `build_ano()` foram revalidadas sem alterações.
- Data e Ano permaneceram em 100,00% nas 916 linhas temporalmente comparáveis.
- A independência de locale, a coerência de preenchimento e a preservação da arquitetura foram confirmadas.
- A suíte completa continuou sem regressões.

### Descobertas da Sprint 8

- O bruto não contém `Prazo`, `Prazo2`, `Situação` ou `Status`; Prazo e Prazo2 são calculados com `Entrega` e `Previsão`.
- Sem Entrega, o resultado é `SEM INFORMAÇÃO DE ENTREGA`.
- Entrega anterior ou igual à Previsão produz `ENTREGUE NO PRAZO`.
- Entrega posterior à Previsão produz `ENTREGUE COM ATRASO`.
- Prazo e Prazo2 são iguais em 1.076 de 1.076 linhas e utilizam a mesma regra comprovada.
- Ambos atingiram 85,13% global e 100,00% nas 916 linhas temporalmente comparáveis.
- As 160 diferenças globais são derivadas exclusivamente do `TEMPORAL_MISMATCH` já comprovado em Entrega.
- Foram aprovados 104 testes, sem regressão e sem alteração das funções protegidas.

Evidências detalhadas: `docs/EQUIVALENCIA.md`.

### Encerramento definitivo da Sprint 8

- Prazo e Prazo2 foram revalidados em 100,00% nas 916 linhas temporalmente comparáveis.
- Snapshot Validator, comparador e reconciliação foram reexecutados.
- O status dos arquivos permanece corretamente em `TEMPORAL_MISMATCH`.
- Nenhuma data, linha ou função protegida foi alterada.

### Investigação da Sprint 9

- A referência possui 1.076 Flags iguais a `False`, nenhum caso `True` e 1.076 CTe Devolução nulos.
- As 1.076 Notas Fiscais são distintas e nenhuma possui mais de um CTe no conjunto reconciliado.
- Não há textos de devolução, retornos, cancelamentos ou outros casos positivos que permitam diferenciar hipóteses.
- Uma regra que sempre devolvesse `False`/nulo atingiria equivalência trivial e foi descartada como artificial.
- A Sprint 9 aguarda a consulta M correspondente ou um par bruto/tratado com devolução confirmada.

### Consolidação da Sprint 9.1

- A consulta M oficial passou a ser a fonte única da regra de devolução.
- Foram implementadas `build_flag_devolucao_nf()`, `build_cte_devolucao()` e a atualização condicional de `Tipo CTe`.
- `Tipo`, `Observacao` e `Trecho` são concatenados, convertidos para maiúsculas e pesquisados pelo token `DEVOLU`.
- `ARUJA` e `CAMBUI` participam do sinal de devolução e são removidas por `Table.SelectRows()` somente depois do agrupamento, da Flag e do CTe Devolução.
- Os CT-es candidatos são consolidados por Nota Fiscal, sem nulos, sem repetição e na ordem de origem.
- A Flag reproduz `Tem Texto Devolução OR (Qtd Conhecimentos NF > 1 AND Tem Destino Devolução)`.
- `build_prazo()` agora prioriza `DEVOLVIDA` e diferencia ausência de Entrega de ausência de Previsão.
- A base real manteve 1.076 Flags falsas e 1.076 CTe Devolução nulos, com 100,00% de equivalência nessas duas colunas.
- A suíte completa aprovou 114 testes. O comparador registrou 84,91% global e 87,83% nas 916 linhas temporalmente comparáveis.
- A implementação está concluída. A validação funcional positiva permanece pendente porque os arquivos reais disponíveis não possuem nenhuma devolução marcada.

### Conclusão da Sprint 10

- A documentação da Sprint 9.1 foi corrigida para registrar a exclusão posterior de `ARUJA` e `CAMBUI`, sem alterar as funções protegidas.
- Não foi encontrada outra origem para `Prazo2`. A consulta oficial cria apenas Prazo; `Prazo2` permanece uma duplicação comprovada empiricamente no arquivo tratado.
- A consulta M cria `Situação Active` com precedência explícita: `DEVOLVIDA`, `ENTREGUE`, `SEM PREVISÃO`, `ATRASADA`, `PREVISTA PARA HOJE` e `EM ABERTO`.
- `build_situacao()` foi implementada e integrada à coluna contratual `Situação`.
- A data de comparação corresponde à data civil da atualização e pode ser injetada nos testes.
- O arquivo `teste.junho.xlsx` não possui `Situação`; suas seis colunas finais são `Prazo`, `Data`, `Ano`, `Prazo2`, `Data3` e `Ano4`. Por isso, a equivalência direta de Situação é estruturalmente indisponível nessa referência.
- Foram aprovados 118 testes. O comparador permaneceu em 84,91% global e 87,83% nas 916 linhas temporalmente comparáveis, sem regressão nas colunas comuns.
- A revisão arquitetural isolou a regra em `situation.py`, não encontrou ciclos e não justificou outras mudanças de baixo risco.

### Conclusão da Sprint 11

- O contrato final passou de 21 para 22 colunas, incorporando `Ano4` e mantendo `Situação` após as colunas da referência Performance Entrega.
- `Data3 = Data` e `Ano4 = Ano` em 1.076 de 1.076 linhas da referência, sem divergências.
- `Data3` foi corrigida de tipo provisório de data para texto de mês; `Ano4` usa inteiro anulável `Int64`.
- Nenhuma coluna permanece sem origem ou preenchimento provisório.
- `schema.py` tornou-se a fonte única de ordem, tipos pandas, tipos SQLite/PostgreSQL, nulabilidade, origem, regra, dependências e classificação.
- `SCHEMA.md` e os DDLs declarativos são gerados automaticamente, sem acesso a banco.
- Foram aprovados 124 testes.
- A equivalência passou para 90,72% global e 95,45% nas 916 linhas temporalmente comparáveis.
- Data3 e Ano4 atingiram 85,13% global e 100,00% comparável; as 160 diferenças são o `TEMPORAL_MISMATCH` já comprovado.
- A revisão removeu o ramo provisório e um import não utilizado, sem modificar regras homologadas.

### Revisão arquitetural da Sprint 8.1

- Criado `normalization.py` para utilitários compartilhados.
- Removida a duplicação da normalização de nulos no Snapshot Validator.
- Reduzido o acoplamento do comparador com o módulo de regras de negócio.
- Criado `docs/ARCHITECTURE.md` com pipeline, responsabilidades e dependências.
- 104 testes aprovados sem mudança funcional.

## Fase 3 — API ✅

- Sprint 15 — API REST FastAPI ✅

### Conclusão da Sprint 15

- Criada a primeira API HTTP oficial do Active Sync com FastAPI e Pydantic.
- Implementadas rotas de saúde, performance, Nota Fiscal e dashboard.
- As rotas recebem exclusivamente Services pela injeção de dependências.
- O composition root cria e encerra a conexão por requisição e valida a migração.
- Entidades internas são convertidas para schemas públicos antes da resposta.
- Erros de aplicação são traduzidos para HTTP 422/503 sem traceback.
- A API possui teste de integração com a cadeia real até um SQLite temporário.

## Fase 4 — SuperTrack

- Sprint 16 — Primeira integração oficial com o SuperTrack ✅
- Sprint 17 — Segurança, configuração e prontidão para produção ✅
- Sprint 18 — Operação da base e agendamento de sincronizações ✅
- Refatoração de domínios — SuperTrack separado de Performance Entrega ✅

### Separação SuperTrack × Performance

- Perfil centralizado por `ACTIVE_SYNC_PROFILE`, registrado nos logs e histórico.
- `performance_entrega` e suas regras homologadas foram preservadas.
- Nova tabela `supertrack_movements`, com chave por transportador, série CT-e,
  CT-e e Nota Fiscal.
- Nova API `/tracking/{nota_fiscal}` retorna zero, um ou múltiplos movimentos.
- NF 1015048 validada como devolução e NF 1022769 validada no SSW.
- Snapshot real: 1.651 movimentos e 36 devoluções preservados.
- Sprint 19 — Base histórica consolidada e UPSERT em lote ✅

### Conclusão da Sprint 19

- Todos os relatórios são deltas da mesma `supertrack_movements`.
- Ausência em INCREMENTAL, PERÍODO ou FULL nunca remove movimento.
- Cancelamento depende exclusivamente do campo explícito do Active.
- Metadados `first_seen_at`, `last_seen_at`, `last_sync_id`, `updated_at` e
  `created_at` adicionados pela migração `003_historical_consolidation`.
- UPSERT consulta e grava registros em lote, preparado para grandes volumes.
- Auditoria consolidada na tabela `sync_execution`.
- Reprocessamento real: 1.651 movimentos ignorados por serem idênticos, zero
  inseridos, zero atualizados e zero removidos por ausência.

- Sprint 20 — Observabilidade e operação do Active Sync ✅

### Conclusão da Sprint 20

- Dashboard operacional ampliado com última/próxima execução, tempo e todas as
  contagens da sincronização.
- `GET /health` verifica API, banco e storage sem consultar dados de negócio.
- `GET /system/status` expõe perfil, registros, uptime, versão, ambiente e
  última execução.
- `GET /statistics` consolida movimentos, devoluções, cancelamentos, falhas e
  tempos mínimo, médio e máximo.
- Histórico paginado e detalhe usam `sync_execution`, incluindo resumo,
  warnings, mensagens, arquivos e vínculo de reprocessamento.
- `POST /sync/reprocess` reutiliza o pipeline único por período, arquivo
  controlado ou Sync ID.
- Logs de execução são estruturados e correlacionados por `request_id`.
- `SyncNotifier` prepara alertas futuros sem e-mail ou dependência externa.
- 204 testes Python e 241 testes SuperTrack aprovados; lint e build aprovados.
- Nenhuma regra de negócio, UPSERT, perfil ou integração de rastreamento foi
  alterada.

### Conclusão da Sprint 17

- ambientes development, test e production centralizados e validados;
- API Key server-side com estrutura substituível por JWT;
- CORS restritivo, logs JSON, request ID e erros padronizados;
- health checks de processo, banco e versão, além de `/info`;
- proxy Netlify impede exposição da API Key no bundle Vite;
- Repository, Services e regras de negócio permaneceram inalterados.

### Conclusão da Sprint 18

- pipeline operacional único para `INCREMENTAL`, `PERIODO` e `FULL`;
- merge idempotente por Nota Fiscal, distinguindo inseridos, atualizados e ignorados;
- execução manual e por período, com validação e proteção HTTP 409;
- agendador interno configurável por ambiente e com múltiplos horários;
- histórico persistente e endpoints de status e detalhes;
- módulos de atualização, relatórios armazenados e histórico no SuperTrack;
- Repository, Services e regras de negócio permaneceram inalterados.

### Feature — Agendamento automático administrado pelo SuperTrack ✅

- configuração diária persistente, com ativação, desativação e horário;
- endpoints aditivos `GET/PUT /scheduler/config`;
- fuso fixo `America/Sao_Paulo`;
- atualização dinâmica da próxima execução sem reiniciar o serviço;
- execução automática restrita ao modo `INCREMENTAL`;
- contratos homologados, Repository, Services e regras de negócio preservados;
- 207 testes Active Sync e 252 testes SuperTrack aprovados; lint e build
  aprovados.

### Feature final — Polimento do agendamento automático ✅

- card de próxima atualização ligado exclusivamente ao valor do Active Sync;
- resumo com status, frequência, horário, próxima execução e última alteração;
- rascunho local persistido somente ao salvar;
- estado `Salvando...`, bloqueio de clique duplicado e mensagens acessíveis;
- estados indisponível, executando, desativado e não agendado padronizados;
- timezone apresentado como `America/Sao_Paulo`, sem deslocamento UTC fixo;
- execução automática permanece exclusivamente `INCREMENTAL`.

### Feature final — Nova experiência da consulta de rastreamento ✅

- criada camada de normalização exclusivamente no frontend do SuperTrack;
- contratos HTTP, providers, Active Sync, banco, UPSERT e histórico preservados;
- status técnicos convertidos em títulos e subtítulos amigáveis sem perder o
  valor original;
- códigos de unidade traduzidos somente por mapeamentos seguros;
- histórico convertido de tabela técnica para linha do tempo semântica;
- movimento mais recente destacado e detalhes redundantes removidos;
- interface responsiva e acessível para desktop, notebook, tablet e celular;
- 257 testes SuperTrack aprovados, além de lint e build de produção.

O SuperTrack passa a utilizar uma camada de normalização de eventos, desacoplando completamente a interface das nomenclaturas específicas de cada transportadora.

### Correção pontual — Parser ATIVA/SSW ✅

- consulta encaminhada ao parser para seleção estruturada;
- todas as linhas válidas do HTML passam a ser analisadas;
- correspondência exata feita exclusivamente pelo campo Nota Fiscal;
- Pedido deixou de ser aceito como substituto da NF;
- múltiplas linhas da mesma NF são preservadas internamente em `matches`;
- caso real NF 1023373 validado como Pedido 1038612, chegada em
  São João de Meriti/RJ em 22/07/2026 às 05:50;
- Active Sync, interface, banco, UPSERT, scheduler, normalização visual e demais
  providers permaneceram inalterados.

## Módulo 3 — Tracking Providers

### Fundação da arquitetura dos providers ✅

- criado o contrato único `Tracking Contract 1.0`, validado na fronteira das
  Functions;
- criada a base `TrackingProvider`, com ciclo obrigatório `consultar`, `parse`,
  `normalizar` e `validar`;
- provider ATIVA migrado para a base sem alteração funcional do parser SSW;
- catálogo e registro centralizados eliminam a seleção de transportadora da
  interface;
- TRAGETTA, MINUANO e VIA MINAS atravessam o mesmo contrato por adaptador de
  compatibilidade, preservando seus endpoints;
- normalização de status, eventos, unidade e apresentação foi separada do
  parser;
- interface passou a consumir os campos canônicos sem conhecer regras da
  ATIVA;
- aliases legados foram mantidos de forma aditiva para não quebrar contratos
  homologados;
- 272 testes SuperTrack aprovados, sem falhas.

### Provider TRAGETTA — primeiro provider não-SSW ✅

- adapter de compatibilidade substituído por `ProviderTragetta`, derivado
  diretamente de `TrackingProvider`;
- consulta existente da API JSON Solística preservada com autenticação,
  timeout, métricas, cache e renovação única de token;
- parser isolado extrai payloads e todos os eventos sem produzir textos
  visuais;
- normalização e validação utilizam exatamente o `Tracking Contract 1.0`;
- aliases TRAGETTA, SOLISTICA, SOLÍSTICA e FL BRASIL preservados no registry;
- respostas e aliases legados mantidos de forma aditiva;
- provider ATIVA e parser SSW permaneceram inalterados;
- 277 testes SuperTrack, lint e build de produção aprovados.

### Alertas operacionais — entrega em atraso ✅

- criada camada pura `trackingAlertEngine`, independente de providers, parsers,
  Active Sync, banco e interface;
- engine retorna `alerts[]`, preparada para múltiplos alertas futuros;
- alerta de atraso exige previsão válida e vencida, sem entrega concluída;
- status de entrega usam o contrato normalizado e o tipo canônico do evento;
- previsão e confirmação de entrega da base consolidada são usadas como
  fallback seguro;
- card amarelo responsivo inserido imediatamente abaixo do card principal;
- timeline e Tracking Contract 1.0 permaneceram inalterados;
- 288 testes SuperTrack, lint e build de produção aprovados.

## Fase 5 — Produção ⏳

# Equivalência com o Power Query

Este documento registra a evolução da equivalência funcional entre o transformador Python e o arquivo tratado pelo Power Query. O Power Query é usado somente como referência de resultado.

## Arquivos de referência

- Entrada bruta: `Conhecimento - CTe_21072026_152324.xlsx`.
- Saída tratada: `teste.junho.xlsx`, aba `Performance Entrega`.

Os arquivos originais permanecem fora do projeto e não são alterados.

## Critério de comparação

O módulo `active_sync.transformer.comparator` compara:

- quantidade de linhas e colunas;
- nomes e ordem das colunas;
- valores por coluna e posição da linha;
- nulos, textos, datas, números e identificadores normalizados.

Espaços laterais ou repetidos e diferenças de capitalização não geram divergência. `None`, `NaN`, `NaT` e strings vazias são equivalentes. Identificadores continuam textuais, portanto `00123` é diferente de `123`.

## Resultado da primeira medição

A comparação foi executada alinhando explicitamente as linhas pela coluna `Nota Fiscal`. Isso foi necessário porque os dois arquivos possuem ordens diferentes. Nenhuma linha foi removida silenciosamente.

- 1.106 registros no arquivo bruto;
- 1.076 registros no arquivo tratado;
- 109 colunas no bruto e 21 no tratado;
- 1.076 registros associados por `Nota Fiscal`;
- 30 registros presentes somente no resultado Python;
- 3 ocorrências adicionais de chaves duplicadas no Python, associadas pela ordem de aparição;
- última coluna do contrato Python: `Situação`;
- última coluna observada no Power Query: `Ano4`.

Equivalência geral dos valores: **49,43%**.

Total de divergências célula a célula: **12.304**.

O relatório completo foi gravado em `docs/equivalencia_detalhada.txt`. Os valores abaixo usam como denominador 1.106 linhas, incluindo as 30 linhas excedentes do Python.

| Coluna | Iguais | Diferentes | Equivalência | Preenchidos Python | Preenchidos Power Query | Situação |
|---|---:|---:|---:|---:|---:|---|
| CNPJ | 0 | 1.106 | 0,00% | 0 | 1.076 | Regra pendente |
| Destinatário | 0 | 1.106 | 0,00% | 1.105 | 1.076 | Regra pendente |
| Cidade Origem | 1.076 | 30 | 97,29% | 1.106 | 1.076 | 100% nas linhas associadas |
| Cidade Destino | 1.076 | 30 | 97,29% | 1.106 | 1.076 | 100% nas linhas associadas |
| UF Destino | 1.076 | 30 | 97,29% | 1.106 | 1.076 | 100% nas linhas associadas |
| Nota Fiscal | 1.076 | 30 | 97,29% | 1.106 | 1.076 | 100% nas linhas associadas |
| Valor Frete | 1.076 | 30 | 97,29% | 1.106 | 1.076 | 100% nas linhas associadas |
| Saída | 1.076 | 30 | 97,29% | 1.089 | 1.076 | 100% nas linhas associadas |
| Previsão | 1.076 | 30 | 97,29% | 1.089 | 1.076 | 100% nas linhas associadas |
| Entrega | 916 | 190 | 82,82% | 789 | 621 | Regra/normalização pendente |
| Transportadora | 0 | 1.106 | 0,00% | 1.106 | 1.076 | Regra pendente |
| Flag Devolução NF | 0 | 1.106 | 0,00% | 0 | 1.076 | Regra pendente |
| Tipo CTe | 1.076 | 30 | 97,29% | 1.106 | 1.076 | 100% nas linhas associadas |
| CTe Devolução | 1.076 | 30 | 97,29% | 0 | 0 | Inconclusivo: referência vazia |
| Código cliente | 63 | 1.043 | 5,70% | 0 | 1.013 | Regra pendente |
| Prazo | 0 | 1.106 | 0,00% | 0 | 1.076 | Regra textual pendente |
| Data | 455 | 651 | 41,14% | 0 | 621 | Regra de mês pendente |
| Ano | 455 | 651 | 41,14% | 0 | 621 | Regra pendente |
| Prazo2 | 0 | 1.106 | 0,00% | 0 | 1.076 | Regra textual pendente |
| Data3 | 455 | 651 | 41,14% | 0 | 621 | Regra de mês pendente |
| Ano4 | 0 | 1.106 | 0,00% | 0 | 621 | Não existe no contrato Python |
| Situação | 0 | 1.106 | 0,00% | 0 | 0 | Não existe no arquivo Power Query |

### Leitura correta dos percentuais

As colunas Cidade Origem, Cidade Destino, UF Destino, Nota Fiscal, Valor Frete, Saída, Previsão e Tipo CTe são idênticas nas 1.076 notas associadas. Elas não atingem 100% no conjunto completo exclusivamente por causa das 30 linhas excedentes.

CTe Devolução coincide porque está vazia nos dois lados e não pode ser considerada uma regra validada. No arquivo real, `Prazo` e `Prazo2` são textos de situação; `Data` e `Data3` são nomes de mês; `Ano` e `Ano4` são anos numéricos. Essa estrutura diverge dos tipos provisórios definidos na Sprint 1 e precisa ser confirmada antes da implementação das regras.

O percentual posicional, sem alinhamento por Nota Fiscal, foi 36,19%. Ele não representa equivalência funcional porque os arquivos estão ordenados de maneira diferente.

## Regras implementadas na Sprint 2

Nenhuma regra de transformação foi alterada. A Sprint 2 ficou restrita ao comparador, à cobertura dos dados e ao relatório de divergências, conforme definido no escopo.

## Regras e decisões pendentes

1. Confirmar se a coluna final correta é `Ano4` ou `Situação`.
2. Identificar a regra que elimina ou mantém as 30 linhas excedentes.
3. Seguir com Destinatário e as demais colunas, uma por vez.

## Sprint 4 — regra CNPJ

### Origem

A coluna é construída exclusivamente a partir de `Destinatário`, no Excel bruto reconciliado. O identificador utilizado é o prefixo anterior a ` - `.

### Regra implementada

1. Normalizar nulos e espaços externos.
2. Selecionar o conteúdo anterior ao primeiro separador ` - `.
3. Manter somente dígitos.
4. Remover zeros à esquerda, reproduzindo o Power Query.
5. Retornar o resultado como texto; ausência ou prefixo sem dígitos retorna `None`.

Embora identificadores normalmente devam preservar zeros iniciais, a referência comprovou sua remoção em 194 das 1.076 linhas. O Python reproduz esse comportamento deliberadamente para manter equivalência funcional.

### Validação

| Métrica | Resultado |
|---|---:|
| Registros comparados | 1.076 |
| CNPJ preenchido no Python | 1.076 |
| CNPJ preenchido no Power Query | 1.076 |
| Registros iguais | 1.076 |
| Registros diferentes | 0 |
| Equivalência | **100,00%** |

### Hipóteses descartadas

- `Redespacho` com fallback para `Destinatário`: 1.058 de 1.076 coincidências.
- `Consignatário`, `Redespacho` e `Destinatário` em prioridade: 534 de 1.076 coincidências.
- `Remetente`: nenhuma coincidência.
- `Tomador`: nenhuma coincidência.
- `Destinatário` sem normalizar zeros iniciais: 882 de 1.076 coincidências.

Nenhuma outra coluna foi implementada nesta sprint. `Flag Devolução NF`, `CTe Devolução`, `Código cliente`, `Prazo`, `Data`, `Ano`, `Prazo2`, `Data3` e `Situação` continuam provisoriamente nulas.

## Sprint 5 — Destinatário e Código Cliente

### Destinatário

#### Origem e regra

A origem é a coluna `Destinatário` do Excel bruto. A consulta Power Query usa `Table.SplitColumn` com o delimitador `-`, cria três partes e conserva somente a segunda como nome do destinatário:

1. a primeira parte alimenta `CNPJ`;
2. a segunda parte alimenta `Destinatário`;
3. a terceira parte é descartada;
4. espaços externos e valores vazios são normalizados.

Essa regra preserva acentos e demais caracteres especiais existentes na segunda parte. Quando o separador não existe ou a segunda parte está vazia, o resultado é `None`.

#### Hipóteses descartadas

- Copiar diretamente a coluna bruta: nenhuma das 1.076 linhas coincidiu.
- Dividir apenas pelo separador com espaços (`" - "`) e conservar todo o restante: 1.008 de 1.076 coincidências.
- Conservar partes posteriores ao segundo hífen: 68 divergências, justamente nos nomes com sufixos como unidade, filial ou tipo societário.

### Código Cliente

#### Origem e regra

O Código Cliente não existe entre as 109 colunas do relatório bruto do Active. A origem comprovada é a aba `Planilha1` de `Base clientes.xlsx`, a mesma tabela chamada `Planilha1` pela consulta Power Query.

A regra é um `LeftOuter Join`:

- chave do relatório: `CNPJ` já transformado;
- chave cadastral: `Cnpj2`;
- valor retornado: `Código cliente`.

O cadastro analisado possui 7.494 linhas, 7.494 CNPJs distintos e nenhuma chave duplicada. CNPJ e código são normalizados como texto para impedir a produção de valores como `123.0`; códigos originalmente textuais mantêm zeros à esquerda. CNPJs sem correspondência retornam `None`, como no Power Query. O caminho da planilha não foi fixado no código: o cadastro é uma dependência explícita de `transform_dataframe()`.

#### Hipóteses descartadas

- Origem direta em qualquer uma das 109 colunas do Active: nenhuma coluna reproduziu o resultado; os melhores resultados tiveram apenas duas coincidências acidentais.
- Uso de `Pedido` como Código Cliente: os valores não coincidem com a referência.
- Derivação matemática do CNPJ: descartada porque os códigos são identificadores internos provenientes do cadastro.

### Validação da Sprint 5

| Coluna | Preenchidos Python | Preenchidos Power Query | Iguais | Divergentes | Equivalência |
|---|---:|---:|---:|---:|---:|
| Destinatário | 1.076 | 1.076 | 1.076 | 0 | **100,00%** |
| Código cliente | 1.013 | 1.013 | 1.076 | 0 | **100,00%** |

As 63 linhas sem Código Cliente permaneceram nulas nos dois lados. O comparador completo também manteve 100,00% nas colunas já comprovadas: CNPJ, Cidade Origem, Cidade Destino, UF Destino, Nota Fiscal, Valor Frete, Saída, Previsão e Tipo CTe.

Foram executados **66 testes**, todos aprovados. Nenhuma regra de Transportadora, Entrega, Prazo, Prazo2, Situação, Data, Ano, Data3, Ano4, Flag Devolução ou CTe Devolução foi implementada nesta sprint.

## Sprint 6 — Transportadora e Entrega

### Transportadora

#### Origem e regra

A origem é `Transportador`, no relatório bruto do Active. A consulta Power Query transforma o valor em maiúsculas, procura a primeira ocorrência da lista ordenada abaixo e retorna o nome operacional correspondente.

| Texto procurado | Resultado |
|---|---|
| ATIVA | ATIVA |
| JAMEF | JAMEF |
| EXCARGO | EXCARGO |
| MINUANO | MINUANO |
| PATRUS | PATRUS |
| POTENZA | POTENZA |
| TARGG | TARGG |
| VIA MINAS | VIAMINAS |
| FL BRASIL | TRAGETTA |
| SOLISTICA | TRAGETTA |
| PVN | PVN |
| TRAGETTA | TRAGETTA |
| BINHO | BINHO |

Valores preenchidos sem correspondência retornam `SUPERMED`. Valores ausentes permanecem nulos. O resultado é sempre textual.

Hipóteses descartadas:

- copiar diretamente `Transportador`;
- utilizar apenas o texto posterior ao CNPJ;
- normalizar somente capitalização e espaços;
- utilizar CNPJ do transportador como resultado.

Resultado: **1.076 de 1.076 linhas iguais, 100,00% de equivalência**.

### Entrega

#### Origem e regra

A origem é diretamente a coluna `Entrega` do relatório bruto. A consulta Power Query apenas converte o campo para `date`; não há substituição pela previsão, cálculo, filtro por transportadora nem limpeza condicional.

`build_entrega()` reproduz esse comportamento:

- datas válidas são convertidas para `datetime64`;
- formatos de data compatíveis são aceitos;
- vazios e nulos resultam em `NaT`;
- valores inválidos resultam em `NaT`;
- horário, quando existente, não participa da comparação de data.

#### Divergência temporal comprovada

Os arquivos disponíveis não representam o mesmo instante de atualização:

| Situação | Linhas |
|---|---:|
| Mesma data nos dois lados | 621 |
| Nulo nos dois lados | 295 |
| Data somente no bruto atual | 160 |
| Data somente no Power Query | 0 |
| Datas diferentes e preenchidas | 0 |

As 160 ocorrências exclusivas do bruto concentram-se em entregas registradas entre 16/07/2026 e 21/07/2026. A consulta Power Query comprovadamente não contém uma regra que apague essas datas. Portanto, criar um filtro para removê-las reproduziria apenas um snapshot antigo e introduziria uma regra inexistente.

Hipóteses descartadas:

- substituir Entrega por Previsão ou Data Inclusão;
- remover datas por transportadora, cancelamento ou tipo de CTe;
- limitar pela própria data de entrega;
- considerar as 160 ocorrências como erro de conversão: todas são datas válidas;
- apagar as datas por Nota Fiscal: isso seria hardcode e não existe no Power Query.

Resultado com os arquivos atuais: **916 de 1.076 linhas iguais, 85,13% de equivalência**. Para validar 100%, é necessário o Excel bruto usado na mesma atualização que produziu `teste.junho.xlsx`.

### Testes e regressões da Sprint 6

- **74 testes aprovados**.
- Transportadora: **100,00%**.
- Entrega: **85,13%**, pendente exclusivamente por diferença de snapshot.
- CNPJ, Destinatário, Código Cliente, Cidade Origem, Cidade Destino, UF Destino, Nota Fiscal, Valor Frete, Saída, Previsão e Tipo CTe permaneceram com **100,00%**.
- Nenhuma regra de Prazo, Prazo2, Situação, Data, Ano, Data3, Ano4, Flag Devolução ou CTe Devolução foi implementada.

A implementação técnica das duas funções ficou pronta nesta etapa. O encerramento definitivo foi decidido na revisão da Sprint 6.1, após a separação explícita entre equivalência global e equivalência temporalmente comparável.

### Correção do processo de validação — Snapshot Validator

Foi criado o módulo independente `active_sync.transformer.snapshot_validator`. Antes da equivalência célula a célula, ele:

- alinha os registros por `Nota Fiscal`, preservando duplicidades por ocorrência;
- avalia `Saída`, `Previsão` e `Entrega` quando disponíveis nos dois lados;
- converte datas com segurança e ignora somente o componente de horário;
- contabiliza mínimos, máximos, preenchimentos, inválidos, exclusividades e conflitos;
- não modifica, filtra ou completa nenhum DataFrame;
- classifica o par como `COMPATIBLE`, `TEMPORAL_MISMATCH`, `INCONCLUSIVE` ou `DATA_DIVERGENCE`.

O comparador continua funcionando em modo normal e apresenta `SNAPSHOT VALIDATION` antes dos percentuais. O parâmetro `require_compatible_snapshot=True` ativa o modo estrito e gera `IncompatibleSnapshotError` para `TEMPORAL_MISMATCH` ou `INCONCLUSIVE`.

#### Classificação dos arquivos atuais

Status: **`TEMPORAL_MISMATCH`**.

| Métrica de Entrega | Resultado |
|---|---:|
| Preenchidos no bruto | 781 |
| Preenchidos na referência | 621 |
| Mesma data preenchida | 621 |
| Nulos nos dois lados | 295 |
| Somente no bruto | 160 |
| Somente na referência | 0 |
| Datas conflitantes | 0 |
| Menor data no bruto | 16/07/2026 |
| Maior data no bruto | 21/07/2026 |
| Menor data na referência | 16/07/2026 |
| Maior data na referência | 20/07/2026 |

Interpretação correta:

- equivalência medida de Entrega: **85,13%**;
- implementação técnica de `build_entrega()`: consistente com a regra direta do Power Query;
- validação final: inconclusiva com este par de arquivos por incompatibilidade temporal;
- Transportadora: **100,00%**;
- nenhuma data foi apagada, limitada, substituída ou alterada para aumentar o percentual.

`build_entrega()`, `build_transportadora()`, a reconciliação e todas as regras previamente aprovadas permaneceram inalteradas nesta correção.

Na revisão final da Sprint 6, o Snapshot Validator, o comparador, a reconciliação, `build_transportadora()` e `build_entrega()` foram reexecutados. Nenhuma regra artificial, data fixa, lista de Notas ou remoção de datas foi introduzida. A Sprint 6 foi encerrada do ponto de vista técnico: Transportadora permanece em **100,00%**, e Entrega atinge **100,00% nas 916 linhas temporalmente comparáveis**. O percentual global de Entrega continua em **85,13%** exclusivamente pelo `TEMPORAL_MISMATCH` de 160 linhas.

Foram executados **94 testes**, todos aprovados. A documentação detalhada da arquitetura e da heurística está em `docs/SNAPSHOT_VALIDATION.md`; a evidência da execução atual foi gravada em `docs/snapshot_validation.txt`.

## Sprint 7 — Data e Ano

### Origem comprovada

As duas colunas são derivadas da coluna bruta `Entrega`. A definição da consulta Power Query e a comparação empírica dos 1.076 registros reconciliados confirmam:

- `Data`: quando `Entrega` é nula, retorna nulo; caso contrário, retorna o nome do mês de `Entrega` em português do Brasil e em minúsculo;
- `Ano`: quando `Entrega` é nula, retorna nulo; caso contrário, retorna o ano de `Entrega`.

Foram testadas obrigatoriamente `Entrega`, `Saída`, `Previsão`, `Emissão` e `Data Inclusão`. `Data Atualização` não existe no relatório bruto analisado. Também foram avaliadas as demais colunas temporais encontradas: `Cancelamento`, `Ciência cancelamento`, `Autorização`, `Aprovação Financeira`, `Aprovação Fiscal`, `Saída Hora` e `Previsão Hora`.

Embora algumas colunas totalmente preenchidas coincidam com mês e ano nas 621 linhas em que a referência possui `Data` e `Ano`, elas falham nas 455 linhas que deveriam permanecer nulas. Somente `Entrega` reproduz simultaneamente os valores e o padrão de preenchimento da referência. Por isso, todas as demais hipóteses foram formalmente descartadas.

### Regra de `build_data()`

- recebe a série de `Entrega`;
- aplica conversão segura de datas, aceitando horários e preservando o índice;
- retorna `None` para nulos e valores inválidos;
- converte o número do mês por uma tabela determinística com os 12 meses em português;
- retorna sempre o mês em minúsculo, incluindo `março` com acento;
- não consulta nem altera o locale do sistema;
- tipo final: série pandas `object`, com valores textuais ou nulos.

### Regra de `build_ano()`

- recebe a mesma série de `Entrega`;
- aplica a mesma conversão segura de datas;
- retorna o ano da data válida;
- retorna `pd.NA` para nulos e valores inválidos;
- preserva o índice e mantém coerência de preenchimento com `Data`;
- tipo final: inteiro anulável pandas `Int64`, impedindo valores como `2026.0`.

### Comparação global e temporal

| Coluna | Preenchidos Python | Preenchidos Power Query | Iguais | Divergentes | Global | Comparáveis | Divergentes comparáveis | Equivalência comparável |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Transportadora | 1.076 | 1.076 | 1.076 | 0 | 100,00% | 916 | 0 | 100,00% |
| Entrega | 781 | 621 | 916 | 160 | 85,13% | 916 | 0 | 100,00% |
| Data | 781 | 621 | 916 | 160 | 85,13% | 916 | 0 | 100,00% |
| Ano | 781 | 621 | 916 | 160 | 85,13% | 916 | 0 | 100,00% |

O comparador completo apresentou **72,62% de equivalência global** e **74,19% nas linhas temporalmente comparáveis**. Esses percentuais gerais incluem colunas de regras ainda não implementadas e, portanto, não são o critério funcional de Data e Ano. Para as duas colunas desta Sprint, a equivalência temporalmente comparável é **100,00%**.

As 160 divergências restantes de `Data` e `Ano` são derivadas exatamente das 160 datas de `Entrega` presentes apenas no bruto atual. Não há divergência funcional em nenhuma linha comparável, nem mês sem ano ou ano sem mês. O Snapshot Validator não foi alterado e continua classificando corretamente o par como **`TEMPORAL_MISMATCH`**.

### Testes e regressões da Sprint 7

Foram aprovados **94 testes**, incluindo todos os meses, nulos, inválidos, horários, independência de locale, capitalização, preservação de índice, tipo `Int64`, coerência Data/Ano e integração com snapshots compatíveis e incompatíveis. Todos os testes anteriores permaneceram aprovados. `build_entrega()` e `build_transportadora()` não foram alteradas.

Status recomendado: **Sprint 7 concluída tecnicamente**. A validação temporal integral dependerá de um bruto capturado no mesmo instante da referência, mas isso não constitui uma falha da regra implementada.

### Revisão definitiva da Sprint 7

Na abertura da Sprint 7.1 foram reexecutados `build_data()`, `build_ano()`, o Snapshot Validator, o comparador, a reconciliação e toda a suíte anterior. Data e Ano permaneceram com **100,00% nas 916 linhas temporalmente comparáveis**. Não existe dependência do locale do sistema, mês sem ano, ano sem mês, regra artificial ou alteração dos dados de Entrega. A arquitetura permaneceu desacoplada e não houve regressão. Com isso, a Sprint 7 está definitivamente encerrada.

## Sprint 8 — Prazo e Prazo2

### Origem comprovada

O relatório bruto não possui colunas `Prazo`, `Prazo2`, `Situação` ou `Status`. As duas classificações são construídas pela combinação das colunas brutas `Entrega` e `Previsão`, após conversão para data civil.

No arquivo tratado, `Prazo` e `Prazo2` são idênticos nas **1.076 linhas**. O mesmo padrão de duplicação ocorre em `Data`/`Data3` e `Ano`/`Ano4`, também idênticos em todas as linhas. Isso comprova que o segundo grupo replica a mesma regra do primeiro, sem uma condição logística adicional.

### Regra completa

`build_prazo()` e `build_prazo2()` são funções públicas independentes que reutilizam um componente interno puro. Ambas aplicam a seguinte precedência:

1. `Entrega` ausente ou inválida: `SEM INFORMAÇÃO DE ENTREGA`;
2. `Entrega` e `Previsão` válidas, com `Entrega <= Previsão`: `ENTREGUE NO PRAZO`;
3. `Entrega` e `Previsão` válidas, com `Entrega > Previsão`: `ENTREGUE COM ATRASO`;
4. `Entrega` válida com `Previsão` ausente ou inválida: `SEM INFORMAÇÃO DE PREVISÃO`, conforme a precedência oficial incorporada na Sprint 9.1.

O horário é descartado antes da comparação, reproduzindo `Date.From` do Power Query. Espaços, nulos e textos inválidos são tratados pela conversão segura de datas. O índice original é preservado. O tipo final das duas colunas é textual (`object`).

### Evidência quantitativa

| Evidência | Linhas |
|---|---:|
| Entregue no prazo | 553 |
| Entregue com atraso | 68 |
| Sem informação de entrega na referência | 455 |
| Entrega anterior à previsão entre os entregues no prazo | 196 |
| Entrega exatamente na previsão entre os entregues no prazo | 357 |
| Entrega posterior à previsão entre os atrasados | 68 |
| Prazo igual a Prazo2 | 1.076 |

As 357 entregas realizadas exatamente na previsão comprovam o operador inclusivo `<=`. Todas as 68 entregas posteriores à previsão são classificadas como atraso, e nenhuma entrega anterior ou no mesmo dia é classificada como atraso.

### Hipóteses investigadas e descartadas

- **Cópia de coluna do Active:** descartada porque `Prazo`, `Prazo2`, `Situação` e `Status` não existem entre as 109 colunas brutas.
- **Situação logística textual:** descartada por ausência da coluna e porque os três resultados são explicados integralmente pelas datas.
- **Somente Entrega:** insuficiente para separar entrega no prazo de entrega com atraso.
- **Somente Previsão ou Saída:** não identifica se houve entrega nem reproduz os 455 registros sem informação.
- **Entrega comparada com Saída:** descartada; o limite observado corresponde exatamente a Previsão.
- **Data atual ou vencimento da previsão:** descartada; toda linha sem Entrega na referência permanece `SEM INFORMAÇÃO DE ENTREGA`, independentemente de a previsão estar no passado ou futuro.
- **Tipo CTe:** descartado; os mesmos resultados ocorrem em `ENTREGA NORMAL`, e as duas ocorrências de `REENTREGA` não criam regra própria.
- **Flag Devolução, cancelamento e Tipo da operação:** descartados; a referência analisada não apresenta variação capaz de explicar a classificação e a fórmula temporal já atinge 100% comparável.
- **Datas auxiliares, aprovação, emissão e inclusão:** descartadas porque não alteram nenhuma classificação e não reproduzem o limite exato observado.
- **Regra diferente para Prazo2:** descartada porque Prazo e Prazo2 coincidem em 1.076 de 1.076 registros.

### Equivalência global e temporal

| Coluna | Preenchidos Python | Preenchidos Power Query | Iguais | Divergentes | Global | Comparáveis | Divergentes comparáveis | Equivalência comparável |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Prazo | 1.076 | 1.076 | 916 | 160 | 85,13% | 916 | 0 | **100,00%** |
| Prazo2 | 1.076 | 1.076 | 916 | 160 | 85,13% | 916 | 0 | **100,00%** |

O comparador completo passou de 72,62% para **80,36% de equivalência global** e apresenta **83,28% nas linhas temporalmente comparáveis**. Esses totais ainda incluem regras fora do escopo e não implementadas.

As 160 divergências de Prazo e Prazo2 correspondem exatamente às 160 entregas presentes apenas no bruto atual. O Python classifica essas entregas com os dados mais recentes, enquanto a referência antiga mantém `SEM INFORMAÇÃO DE ENTREGA`. Não existe divergência quando os snapshots são temporalmente comparáveis; portanto, o status permanece corretamente em **`TEMPORAL_MISMATCH`**.

### Testes e impacto arquitetural

Foram aprovados **104 testes**, incluindo datas anteriores, iguais e posteriores à previsão; nulos; espaços; textos inválidos; previsão inválida; horários; preservação do índice; consistência entre Prazo e Prazo2; integração no transformador; snapshots compatíveis e incompatíveis; e todos os testes anteriores.

Nenhuma alteração foi feita em `build_transportadora()`, `build_entrega()`, `build_data()`, `build_ano()`, Snapshot Validator ou Dataset Reconciliation. Nenhuma regra de Situação, Flag Devolução, CTe Devolução, Data3 ou Ano4 foi implementada.

Status recomendado: **Sprint 8 concluída tecnicamente**. A certificação global de 100% depende somente de um bruto capturado no mesmo instante do arquivo tratado.

### Revisão definitiva da Sprint 8

Na Sprint 8.1 foram reexecutados `build_prazo()`, `build_prazo2()`, Snapshot Validator, comparador, reconciliação e a suíte completa. Prazo e Prazo2 permaneceram em **100,00% nas 916 linhas temporalmente comparáveis**, com os mesmos 160 registros excluídos pelo `TEMPORAL_MISMATCH`. Não foram criados filtros, datas foram preservadas e as funções protegidas não sofreram alterações. A Sprint 8 está definitivamente encerrada.

## Sprint 9 — Flag Devolução NF e CTe Devolução

### Evidência disponível

O arquivo tratado contém:

| Coluna | Preenchidos Python | Preenchidos Power Query | Valores observados na referência | Equivalência atual |
|---|---:|---:|---|---:|
| Flag Devolução NF | 0 | 1.076 | 1.076 valores `False`; nenhum `True` | 0,00% |
| CTe Devolução | 0 | 0 | 1.076 nulos | 100,00% aparente |

O percentual de CTe Devolução é uma coincidência entre campos vazios e **não comprova uma regra**. Da mesma forma, implementar `False` para todas as linhas faria a Flag atingir 100% sem demonstrar como uma devolução real deve ser identificada.

### Hipóteses investigadas

Foram analisados `Tipo`, `CFOP`, `Natureza`, `Operação Fiscal`, `CTe`, `Nota Fiscal`, cancelamentos, ciência do cancelamento, observações, trecho e cidade de destino, além de duplicidades e combinações entre esses campos.

Resultados do conjunto reconciliado:

- 1.076 Notas Fiscais distintas para 1.076 linhas;
- nenhuma Nota Fiscal associada a mais de um CTe;
- nenhum par Nota Fiscal/CTe duplicado;
- 1.074 registros `ENTREGA NORMAL` e 2 `REENTREGA`;
- nenhum texto contendo `DEVOLU` ou `RETORN` em Tipo, Observação, Trecho, CFOP ou Operação Fiscal;
- nenhum cancelamento preenchido;
- `Natureza` não existe no relatório bruto;
- `Operação Fiscal` está vazia nas 1.076 linhas;
- todos os valores de Flag na referência são falsos e todos os CTe Devolução são nulos.

Uma regra candidata localizada em uma consulta M de outro fluxo foi testada. Ela combina texto contendo `DEVOLU`, destinos específicos e múltiplos conhecimentos por Nota Fiscal. No conjunto atual todos esses sinais são ausentes, de modo que a candidata também produz somente `False` e nulos. O resultado coincide em 1.076 linhas, mas de forma trivial; não há caso positivo capaz de confirmar os critérios, a precedência ou a agregação do CTe.

### Conclusão da Sprint 9

Com os dois arquivos atuais, a origem e a regra completa de `Flag Devolução NF` e `CTe Devolução` são **inconclusivas**. Implementar funções que sempre retornem `False` e `None`, ou adotar a regra de outro fluxo sem casos positivos, violaria as restrições contra hardcodes e regras artificiais.

Por esse motivo, `build_flag_devolucao_nf()` e `build_cte_devolucao()` não foram criadas. Para desbloquear a Sprint 9 é necessário pelo menos um dos itens:

1. a consulta M da planilha `Performance Entrega` que cria as duas colunas; ou
2. um Excel bruto e sua saída Power Query correspondente contendo ao menos uma devolução confirmada, preferencialmente com duplicidades de Nota/CTe quando essa situação fizer parte da regra.

Status recomendado: **Sprint 9 pendente por insuficiência de evidência**, sem introdução de comportamento não comprovado.

## Sprint 9.1 — Consolidação da regra oficial de devolução

### Fonte e implementação

A consulta M oficial recebida substituiu as hipóteses da investigação anterior e passou a ser a única fonte da regra. A implementação foi isolada em `active_sync/transformer/returns.py` e integrada pelo `transform_dataframe()` sem alterar Snapshot Validator, Comparator, Dataset Reconciliation, `build_transportadora()`, `build_entrega()`, `build_data()` ou `build_ano()`.

A ordem reproduzida é:

1. concatenar `Tipo`, `Observacao` e `Trecho`, removendo nulos, converter o texto para maiúsculas e procurar `DEVOLU`;
2. normalizar `Cidade Destino` com trim e maiúsculas e marcar exatamente `ARUJA` ou `CAMBUI` como destino de devolução;
3. considerar o `CTe` candidato quando houver sinal textual ou de destino;
4. agrupar por `Nota Fiscal`, contar CT-es distintos não nulos, calcular qualquer sinal textual, qualquer sinal de destino e concatenar CT-es candidatos distintos com `", "`, preservando a ordem da origem;
5. definir `Flag Devolução NF = Tem Texto Devolução OR (Qtd Conhecimentos NF > 1 AND Tem Destino Devolução)`;
6. substituir `Tipo CTe` por `DEVOLUCAO` somente quando a Flag for verdadeira;
7. preencher `CTe Devolução` com a agregação da Nota somente quando a Flag for verdadeira; caso contrário, manter nulo.

`ARUJA` e `CAMBUI` são incluídas primeiro na comparação que cria `Destino Devolução`, participam do CTe candidato, do agrupamento por Nota Fiscal, da Flag e do CTe Devolução. Somente depois a consulta executa `Table.SelectRows()` e remove essas cidades do resultado final. A ordem é relevante: excluí-las antes impediria que contribuíssem para a classificação das demais linhas da mesma Nota Fiscal.

### Regra final de Prazo

`build_prazo()` passou a aplicar exatamente esta precedência:

1. Flag de devolução verdadeira: `DEVOLVIDA`;
2. Entrega ausente ou inválida: `SEM INFORMAÇÃO DE ENTREGA`;
3. Previsão ausente ou inválida: `SEM INFORMAÇÃO DE PREVISÃO`;
4. Entrega menor ou igual à Previsão: `ENTREGUE NO PRAZO`;
5. Entrega maior que a Previsão: `ENTREGUE COM ATRASO`.

Não foi encontrada outra origem para `Prazo2`. A consulta oficial cria apenas Prazo. Entre todas as consultas M disponibilizadas, nenhuma contém uma criação, renomeação ou transformação literal de `Prazo2`. A implementação existente permanece baseada na equivalência empírica já comprovada: `Prazo2` é idêntico a `Prazo` nas 1.076 linhas do arquivo tratado anterior. A consulta de rastreamento analisada separadamente cria `Situação Active`, não `Prazo2`.

### Testes sintéticos

Os testes cobrem texto com e sem `DEVOLU`, sinais em cada um dos três campos textuais, destinos `ARUJA` e `CAMBUI`, um único CTe, múltiplos CT-es com e sem sinal, repetição do mesmo CTe, agrupamento por Nota Fiscal, remoção de nulos, distinção e ordem na concatenação, Flags verdadeira e falsa, atualização de Tipo CTe, CTe Devolução, precedência de Prazo e preservação do índice. A suíte completa encerrou com **114 testes aprovados**.

### Validação com os arquivos reais

| Métrica | Resultado |
|---|---:|
| Registros reconciliados | 1.076 |
| Flag Devolução NF — equivalência global | **100,00%** |
| Flag Devolução NF — equivalência comparável | **100,00%** |
| CTe Devolução — equivalência global | **100,00%** |
| CTe Devolução — equivalência comparável | **100,00%** |
| Tipo CTe — equivalência global/comparável | **100,00%** |
| Prazo — equivalência global | **85,13%** |
| Prazo — equivalência comparável | **100,00%** |
| Equivalência geral do DataFrame | **84,91%** |
| Equivalência geral nas 916 linhas comparáveis | **87,83%** |
| Linhas temporalmente excluídas | 160 |
| Snapshot | `TEMPORAL_MISMATCH` |

As divergências restantes continuam nas regras ainda pendentes e nas 160 linhas afetadas pelo snapshot de Entrega. A base real analisada contém **zero Flags verdadeiras** e **zero CTe Devolução preenchidos** em ambos os lados. Assim, ela comprova ausência de regressão e equivalência do caso negativo, mas não exercita o caminho positivo.

Status recomendado: **IMPLEMENTAÇÃO CONCLUÍDA; VALIDAÇÃO FUNCIONAL PENDENTE**. A pendência será encerrada quando um par bruto/tratado da mesma atualização contiver ao menos uma devolução real; a ausência desse caso não autoriza simplificar a regra oficial.

## Sprint 10 — Situação e correções da Sprint 9.1

### Investigação definitiva de Situação

A consulta M oficial cria a coluna textual `Situação Active`. A coluna depende de `Flag Devolução NF`, `Entrega`, `Previsão` e `Hoje`, sendo `Hoje = Date.From(DateTime.LocalNow())` no momento da atualização.

A precedência comprovada é:

1. Flag de devolução verdadeira: `DEVOLVIDA`;
2. Entrega preenchida: `ENTREGUE`;
3. Previsão ausente: `SEM PREVISÃO`;
4. Previsão anterior a Hoje: `ATRASADA`;
5. Previsão igual a Hoje: `PREVISTA PARA HOJE`;
6. Previsão posterior a Hoje: `EM ABERTO`.

`build_situacao()` foi implementada em `active_sync/transformer/situation.py`. O nome externo continua sendo `Situação`, atualmente a 22ª coluna do contrato Python; a origem lógica e documentada é `Situação Active`. A data de referência é opcionalmente injetável para testes determinísticos e, quando omitida, usa a data civil local da execução, como a consulta M.

### Limite da referência atual

O arquivo `teste.junho.xlsx`, aba `Performance Entrega`, não possui `Situação`. Suas seis colunas finais são `Prazo`, `Data`, `Ano`, `Prazo2`, `Data3` e `Ano4`. Portanto, o comparador registra 0,00% para `Situação` por coluna ausente na referência, e não por divergência entre valores calculados. A regra foi validada diretamente contra a expressão M e por testes unitários cobrindo todos os ramos.

Na execução de 22/07/2026, o resultado Python apresentou:

| Situação | Registros |
|---|---:|
| ENTREGUE | 781 |
| EM ABERTO | 160 |
| ATRASADA | 100 |
| PREVISTA PARA HOJE | 35 |
| DEVOLVIDA | 0 |
| SEM PREVISÃO | 0 |

### Validação e regressões

| Métrica | Resultado |
|---|---:|
| Registros reconciliados | 1.076 |
| Testes aprovados | **118** |
| Equivalência global | **84,91%** |
| Equivalência nas 916 linhas temporalmente comparáveis | **87,83%** |
| Linhas temporalmente excluídas | 160 |
| Snapshot | `TEMPORAL_MISMATCH` |
| Situação na referência | Ausente |

Flag Devolução NF, CTe Devolução e Tipo CTe permaneceram em 100,00%. Entrega, Prazo e Prazo2 permaneceram em 85,13% global e 100,00% nas linhas comparáveis. Snapshot Validator, Comparator, Dataset Reconciliation e todas as funções protegidas permaneceram inalterados.

### Revisão arquitetural

A regra foi isolada em `situation.py`, que depende somente de `mapping.py` e `normalization.py`. `transforms.py` atua apenas como orquestrador e `__init__.py` expõe a função pública. A inspeção de imports não identificou dependências circulares.

Não foi realizada consolidação adicional das funções privadas do comparador, Snapshot Validator ou reconciliação: elas possuem responsabilidades e semânticas próprias, e uni-las criaria risco de regressão sem benefício proporcional. Nenhuma outra melhoria arquitetural foi necessária.

Status recomendado: **Sprint 10 concluída**. A regra está implementada e testada; a certificação por equivalência direta dependerá de uma referência que contenha `Situação Active` ou sua renomeação contratual `Situação`.

## Sprint 11 — Consolidação do Transformer

### Investigação de Data3 e Ano4

As consultas M disponibilizadas não criam literalmente `Data3` ou `Ano4`. A comprovação definitiva veio do resultado Power Query: nas **1.076 linhas**, `Data3` é idêntica a `Data` e `Ano4` é idêntica a `Ano`, sem divergência nem diferença de preenchimento.

| Comparação | Iguais | Divergentes | Valores preenchidos |
|---|---:|---:|---:|
| Data3 × Data | 1.076 | 0 | 621 em cada coluna |
| Ano4 × Ano | 1.076 | 0 | 621 em cada coluna |

`Data3` contém o nome do mês em português e, portanto, seu tipo definitivo é texto `object`, não data. `Ano4` contém o ano e usa `Int64`, preservando nulos sem produzir valores decimais. A implementação copia as séries já calculadas de `Data` e `Ano`, sem executar novamente as regras homologadas.

### Auditoria completa do contrato

| Ordem | Coluna | Classificação |
|---:|---|---|
| 1 | CNPJ | IMPLEMENTADA |
| 2 | Destinatário | IMPLEMENTADA |
| 3 | Cidade Origem | IMPLEMENTADA |
| 4 | Cidade Destino | IMPLEMENTADA |
| 5 | UF Destino | IMPLEMENTADA |
| 6 | Nota Fiscal | IMPLEMENTADA |
| 7 | Valor Frete | IMPLEMENTADA |
| 8 | Saída | IMPLEMENTADA |
| 9 | Previsão | IMPLEMENTADA |
| 10 | Entrega | IMPLEMENTADA |
| 11 | Transportadora | IMPLEMENTADA |
| 12 | Flag Devolução NF | IMPLEMENTADA COM VALIDAÇÃO PENDENTE |
| 13 | Tipo CTe | IMPLEMENTADA |
| 14 | CTe Devolução | IMPLEMENTADA COM VALIDAÇÃO PENDENTE |
| 15 | Código cliente | IMPLEMENTADA |
| 16 | Prazo | IMPLEMENTADA |
| 17 | Data | IMPLEMENTADA |
| 18 | Ano | IMPLEMENTADA |
| 19 | Prazo2 | IMPLEMENTADA |
| 20 | Data3 | IMPLEMENTADA |
| 21 | Ano4 | IMPLEMENTADA |
| 22 | Situação | IMPLEMENTADA COM VALIDAÇÃO PENDENTE |

Não existem colunas classificadas como `NÃO IMPLEMENTADA` ou `FORA DO ESCOPO` dentro do contrato final. As pendências são exclusivamente de validação: devolução não possui caso real positivo e Situação não existe no arquivo tratado disponível.

### Validação final

| Métrica | Resultado |
|---|---:|
| Registros reconciliados | 1.076 |
| Colunas Python | 22 |
| Colunas na referência atual | 21 |
| Testes aprovados | **124** |
| Equivalência global | **90,72%** |
| Equivalência nas 916 linhas temporalmente comparáveis | **95,45%** |
| Linhas temporalmente excluídas | 160 |
| Snapshot | `TEMPORAL_MISMATCH` |
| Data3 — global/comparável | 85,13% / **100,00%** |
| Ano4 — global/comparável | 85,13% / **100,00%** |

A diferença estrutural restante é intencional e transparente: o contrato Python inclui `Situação`, enquanto `teste.junho.xlsx` termina em `Ano4`. Todas as colunas comuns mantiveram seus resultados anteriores; Flag Devolução NF, CTe Devolução e Tipo CTe permanecem em 100,00%.

### Contrato persistente

`active_sync/transformer/schema.py` contém o contrato oficial e gera `docs/SCHEMA.md`. Cada coluna possui tipo pandas, tipo SQLite, tipo PostgreSQL, nulabilidade, descrição, origem, regra, dependências e classificação. O módulo também gera DDL declarativo para `performance_entrega`, mas não importa drivers, não abre conexões e não executa comandos em banco.

### Refatoração controlada

`columns.py` agora deriva ordem e categorias de tipo diretamente do schema, eliminando definições paralelas. O ramo provisório para colunas sem mapeamento e o import não utilizado `preserve_identifier` foram removidos de `transforms.py`. Data3 e Ano4 reutilizam resultados existentes. Nenhuma função protegida ou componente de validação/comparação foi alterado.

Status recomendado: **Sprint 11 concluída e Transformer encerrado tecnicamente**. A camada está preparada para alimentar uma futura persistência sem acoplamento a SQLite ou PostgreSQL.

## Revisão arquitetural da Sprint 8.1

Foi criado `active_sync/transformer/normalization.py` para centralizar normalização de nulos, textos, identificadores, datas e números. A duplicação de normalização entre `transforms.py` e `snapshot_validator.py` foi removida, e o comparador deixou de depender do módulo de regras de negócio para normalizar valores.

As assinaturas públicas existentes foram preservadas e os **104 testes** continuaram aprovados. A arquitetura completa está documentada em `docs/ARCHITECTURE.md`.

## Ordem de implementação das regras

1. CNPJ
2. Destinatário
3. Cidade Origem
4. Cidade Destino
5. UF Destino
6. Transportadora
7. Nota Fiscal
8. Valor Frete
9. Saída
10. Previsão
11. Entrega
12. Data
13. Ano
14. Código cliente
15. Tipo CTe
16. Flag Devolução NF
17. CTe Devolução
18. Prazo
19. Prazo2
20. Data3
21. Ano4
22. Situação

Uma regra somente será considerada concluída quando alcançar 100% em snapshots compatíveis ou 100% nas linhas temporalmente comparáveis quando o Snapshot Validator comprovar `TEMPORAL_MISMATCH`. O percentual global permanece sempre visível e nenhuma divergência pode ser filtrada ou mascarada.

## Histórico

| Data | Etapa | Resultado |
|---|---|---|
| 21/07/2026 | Sprint 1 | Layout Python criado com 21 colunas e 38 testes aprovados. |
| 21/07/2026 | Sprint 2 | Comparador implementado; 48 testes aprovados; equivalência alinhada inicial de 49,43%. |
| 22/07/2026 | Sprint 3 | Universo reconciliado: 1.076 registros em ambos os lados e zero Notas Fiscais exclusivas. |
| 22/07/2026 | Sprint 4 | Regra CNPJ concluída: 1.076 de 1.076 valores iguais, 100,00% de equivalência e 58 testes aprovados. |
| 22/07/2026 | Sprint 5 | Destinatário e Código Cliente concluídos: 100,00% de equivalência em ambas as colunas e 66 testes aprovados. |
| 22/07/2026 | Sprint 6 | Transportadora atingiu 100,00%; Entrega ficou em 85,13% por diferença temporal entre os arquivos. Validação final pendente. |
| 22/07/2026 | Correção Sprint 6 | Snapshot Validator implementado; arquivos atuais classificados como TEMPORAL_MISMATCH; 85 testes aprovados. |
| 22/07/2026 | Sprint 6.1 | Sprint 6 encerrada tecnicamente; Data e Ano implementadas a partir de Entrega; 100,00% nas 916 linhas comparáveis e 94 testes aprovados. |
| 22/07/2026 | Sprint 7.1 | Sprint 7 encerrada; Prazo e Prazo2 implementados; 100,00% nas 916 linhas comparáveis e 104 testes aprovados. |
| 22/07/2026 | Sprint 8.1 | Sprint 8 encerrada; revisão arquitetural concluída; Sprint 9 mantida pendente por ausência de casos positivos de devolução. |
| 22/07/2026 | Sprint 9.1 | Consulta M reproduzida; regra de devolução implementada; 114 testes aprovados; validação funcional positiva pendente por ausência de casos reais. |
| 22/07/2026 | Sprint 10 | Situação Active implementada; correções documentais concluídas; 118 testes aprovados; equivalência direta de Situação indisponível na referência atual. |
| 22/07/2026 | Sprint 11 | Contrato final de 22 colunas; Data3/Ano4 concluídas; schema persistente criado; 124 testes aprovados; 95,45% comparável. |

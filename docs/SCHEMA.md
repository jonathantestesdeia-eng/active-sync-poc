# Contrato Persistente do Transformer

Este documento é gerado a partir de `active_sync.transformer.schema`.
O módulo descreve a persistência futura, mas não acessa banco de dados.

## Colunas

| Ordem | Nome | Status | pandas | SQLite | PostgreSQL | Nulo | Origem | Dependências | Descrição e regra |
|---:|---|---|---|---|---|---|---|---|---|
| 1 | CNPJ | IMPLEMENTADA | object | TEXT | TEXT | Sim | Destinatário | Destinatário | CNPJ normalizado do destinatário. Extrai o prefixo numérico e remove zeros iniciais. |
| 2 | Destinatário | IMPLEMENTADA | object | TEXT | TEXT | Sim | Destinatário | Destinatário | Nome operacional do destinatário. Conserva a segunda parte do texto separado por hífen. |
| 3 | Cidade Origem | IMPLEMENTADA | object | TEXT | TEXT | Sim | Cidade Origem | Cidade Origem | Cidade de origem do transporte. Texto normalizado diretamente da origem. |
| 4 | Cidade Destino | IMPLEMENTADA | object | TEXT | TEXT | Sim | Cidade Destino | Cidade Destino | Cidade de destino do transporte. Texto normalizado diretamente da origem. |
| 5 | UF Destino | IMPLEMENTADA | object | TEXT | TEXT | Sim | UF Destino | UF Destino | UF de destino do transporte. Texto normalizado diretamente da origem. |
| 6 | Nota Fiscal | IMPLEMENTADA | object | TEXT | TEXT | Sim | Nota Fiscal | Nota Fiscal | Identificador da Nota Fiscal. Preserva o identificador como texto. |
| 7 | Valor Frete | IMPLEMENTADA | Float64 | REAL | DOUBLE PRECISION | Sim | Valor Frete | Valor Frete | Valor total do frete. Conversão numérica segura em tipo anulável. |
| 8 | Saída | IMPLEMENTADA | datetime64[ns] | TEXT | DATE | Sim | Saída | Saída | Data civil de saída. Conversão segura para data. |
| 9 | Previsão | IMPLEMENTADA | datetime64[ns] | TEXT | DATE | Sim | Previsão | Previsão | Data civil prevista para entrega. Conversão segura para data. |
| 10 | Entrega | IMPLEMENTADA | datetime64[ns] | TEXT | DATE | Sim | Entrega | Entrega | Data civil efetiva da entrega. Conversão segura para data. |
| 11 | Transportadora | IMPLEMENTADA | object | TEXT | TEXT | Sim | Transportador | Transportador | Nome operacional normalizado da transportadora. Aplica o primeiro mapeamento textual correspondente. |
| 12 | Flag Devolução NF | IMPLEMENTADA COM VALIDAÇÃO PENDENTE | bool | INTEGER | BOOLEAN | Não | Tipo, Observacao, Trecho, Cidade Destino, CTe e Nota Fiscal | Tipo, Observacao, Trecho, Cidade Destino, CTe, Nota Fiscal | Indica devolução no nível da Nota Fiscal. Texto DEVOLU ou múltiplos CT-es com destino ARUJA/CAMBUI. |
| 13 | Tipo CTe | IMPLEMENTADA | object | TEXT | TEXT | Sim | Tipo | Tipo, Flag Devolução NF | Tipo operacional do conhecimento. Usa DEVOLUCAO quando a Flag é verdadeira; caso contrário, conserva Tipo. |
| 14 | CTe Devolução | IMPLEMENTADA COM VALIDAÇÃO PENDENTE | object | TEXT | TEXT | Sim | CTe | CTe, Nota Fiscal, Flag Devolução NF | CT-es candidatos da devolução agregados por Nota Fiscal. Concatena candidatos distintos quando a Flag é verdadeira. |
| 15 | Código cliente | IMPLEMENTADA | object | TEXT | TEXT | Sim | Base clientes.xlsx/Planilha1 | CNPJ, Cnpj2, Código cliente | Código interno do cliente. Left join entre CNPJ e Cnpj2. |
| 16 | Prazo | IMPLEMENTADA | object | TEXT | TEXT | Não | Flag Devolução NF, Entrega e Previsão | Flag Devolução NF, Entrega, Previsão | Classificação do cumprimento do prazo. Aplica a precedência oficial de devolução e datas. |
| 17 | Data | IMPLEMENTADA | object | TEXT | TEXT | Sim | Entrega | Entrega | Nome do mês da Entrega em português. Converte o mês para texto minúsculo. |
| 18 | Ano | IMPLEMENTADA | Int64 | INTEGER | INTEGER | Sim | Entrega | Entrega | Ano da Entrega. Extrai o ano como inteiro anulável. |
| 19 | Prazo2 | IMPLEMENTADA | object | TEXT | TEXT | Não | Prazo | Entrega, Previsão | Duplicação contratual da classificação Prazo. Reproduz a regra temporal homologada de Prazo. |
| 20 | Data3 | IMPLEMENTADA | object | TEXT | TEXT | Sim | Data | Data | Duplicação contratual do mês textual de Data. Copia Data sem recalcular a regra. |
| 21 | Ano4 | IMPLEMENTADA | Int64 | INTEGER | INTEGER | Sim | Ano | Ano | Duplicação contratual do ano da Entrega. Copia Ano sem recalcular a regra. |
| 22 | Situação | IMPLEMENTADA COM VALIDAÇÃO PENDENTE | object | TEXT | TEXT | Não | Flag Devolução NF, Entrega, Previsão e data da atualização | Flag Devolução NF, Entrega, Previsão, Hoje | Situação operacional criada como Situação Active. Aplica DEVOLVIDA, ENTREGUE, SEM PREVISÃO, ATRASADA, PREVISTA PARA HOJE ou EM ABERTO. |

## SQLite

```sql
CREATE TABLE "performance_entrega" (
    "CNPJ" TEXT,
    "Destinatário" TEXT,
    "Cidade Origem" TEXT,
    "Cidade Destino" TEXT,
    "UF Destino" TEXT,
    "Nota Fiscal" TEXT,
    "Valor Frete" REAL,
    "Saída" TEXT,
    "Previsão" TEXT,
    "Entrega" TEXT,
    "Transportadora" TEXT,
    "Flag Devolução NF" INTEGER NOT NULL,
    "Tipo CTe" TEXT,
    "CTe Devolução" TEXT,
    "Código cliente" TEXT,
    "Prazo" TEXT NOT NULL,
    "Data" TEXT,
    "Ano" INTEGER,
    "Prazo2" TEXT NOT NULL,
    "Data3" TEXT,
    "Ano4" INTEGER,
    "Situação" TEXT NOT NULL
);
```

## PostgreSQL

```sql
CREATE TABLE "performance_entrega" (
    "CNPJ" TEXT,
    "Destinatário" TEXT,
    "Cidade Origem" TEXT,
    "Cidade Destino" TEXT,
    "UF Destino" TEXT,
    "Nota Fiscal" TEXT,
    "Valor Frete" DOUBLE PRECISION,
    "Saída" DATE,
    "Previsão" DATE,
    "Entrega" DATE,
    "Transportadora" TEXT,
    "Flag Devolução NF" BOOLEAN NOT NULL,
    "Tipo CTe" TEXT,
    "CTe Devolução" TEXT,
    "Código cliente" TEXT,
    "Prazo" TEXT NOT NULL,
    "Data" TEXT,
    "Ano" INTEGER,
    "Prazo2" TEXT NOT NULL,
    "Data3" TEXT,
    "Ano4" INTEGER,
    "Situação" TEXT NOT NULL
);
```

## Convenções de persistência

- Datas usam ISO `YYYY-MM-DD` no SQLite e `DATE` no PostgreSQL.
- Booleanos usam `0/1` no SQLite e `BOOLEAN` no PostgreSQL.
- Identificadores permanecem textuais para preservar seu formato.
- `schema.py` não cria conexões, tabelas ou migrações.

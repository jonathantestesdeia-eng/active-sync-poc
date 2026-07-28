# Camada Repository

Implementada na Sprint 13 como interface exclusiva de leitura dos dados
persistidos em `performance_entrega`.

## Arquitetura

```text
Transformer
    |
    v
Persistence ----> SQLite
    ^                 |
    | DatabaseManager |
    |                 v
Repository <----------+
    |
    v
Services (próxima fase)
```

A Persistence continua responsável pela conexão, migrações e gravação. A
Repository concentra o SQL de leitura e acessa o SQLite somente por meio do
`DatabaseManager`. Nenhuma regra do Transformer é importada; a única referência
permitida é `transformer.schema`, usada para derivar o contrato e a lista segura
de colunas.

## Estrutura

| Módulo | Responsabilidade |
|---|---|
| `repository/models.py` | Modelo imutável e filtros de consulta. |
| `repository/performance_repository.py` | Consultas parametrizadas, paginação e ordenação. |
| `repository/exceptions.py` | Erros de Repository e consultas inválidas. |
| `repository/__init__.py` | API pública da camada. |

## PerformanceEntrega

`PerformanceEntrega` representa exatamente as 22 colunas de
`TRANSFORMER_SCHEMA`. Os nomes, a ordem e os aliases Python são gerados a partir
desse contrato; a definição não repete manualmente os campos.

```python
registro.nota_fiscal
registro.transportadora
registro["UF Destino"]
registro.as_dict()
```

O modelo é imutável. `as_dict()` devolve os nomes persistentes oficiais, enquanto
os atributos usam aliases normalizados, sem espaços ou acentos.

## Consultas disponíveis

| Método | Resultado |
|---|---|
| `listar()` | Lista geral com filtros, paginação e ordenação. |
| `buscar_por_nf()` | Todas as ocorrências de uma Nota Fiscal. |
| `buscar_por_transportadora()` | Registros de uma transportadora. |
| `buscar_por_periodo()` | Intervalo inclusivo da coluna `Saída`. |
| `buscar_atrasadas()` | Registros com Situação `ATRASADA`. |
| `buscar_em_aberto()` | Registros com Situação `EM ABERTO`. |
| `buscar_devolvidas()` | Flag de devolução verdadeira ou Situação `DEVOLVIDA`. |
| `contar()` | Quantidade total ou filtrada. |
| `existe_nf()` | Existência de uma Nota Fiscal. |

## Filtros combináveis

`PerformanceFilters` aceita:

- Transportadora;
- UF Destino;
- Cidade Destino;
- Prazo;
- Situação;
- início e fim do período de Saída.

```python
filters = PerformanceFilters(
    transportadora="TRANS A",
    uf_destino="SP",
    situacao="ATRASADA",
    periodo_inicio="2026-07-01",
    periodo_fim="2026-07-31",
)
registros = repository.listar(filters)
```

Os limites do período são inclusivos. Strings de data devem usar ISO
`YYYY-MM-DD`; também são aceitos objetos `datetime.date`.

## Paginação e ordenação

`listar()`, `buscar_por_transportadora()` e `buscar_por_periodo()` aceitam
`limit` e `offset`. A listagem também aceita `order_by` e `descending`.

```python
pagina = repository.listar(
    limit=50,
    offset=100,
    order_by="Nota Fiscal",
    descending=False,
)
```

`limit` deve ser maior que zero e `offset` não pode ser negativo. A ordenação
aceita exclusivamente nomes presentes em `TRANSFORMER_SCHEMA`.

## Construção segura das consultas

- valores externos nunca são interpolados no SQL;
- filtros, datas, NF, `LIMIT` e `OFFSET` utilizam placeholders `?`;
- nomes de ordenação são validados contra a lista imutável do schema;
- os fragmentos de filtros utilizam apenas identificadores internos conhecidos;
- filtros são combinados por `AND` sem alterar os métodos especializados;
- falhas SQLite são expostas como `RepositoryError` sem vazar detalhes internos.

A montagem dinâmica concatena somente fragmentos SQL internos e homologados.
Nenhum texto fornecido pelo chamador é concatenado à instrução.

## Boas práticas e limites

- instanciar o Repository com um `DatabaseManager` já aberto e migrado;
- não expor a conexão SQLite para Services ou API;
- usar `PerformanceFilters` em vez de criar SQL fora da camada;
- manter critérios de negócio fora da Repository;
- preservar o modelo imutável nas respostas;
- não assumir que Nota Fiscal é chave única: `buscar_por_nf()` retorna uma lista.

A identidade de atualização e eventuais índices continuam reservados para uma
migração futura. Esta Sprint implementa somente leitura e não altera Persistence
ou Transformer.

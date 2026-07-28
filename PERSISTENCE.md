# Camada de Persistência

Implementada na Sprint 12 como primeira entrega da Fase 2. Esta camada recebe
exclusivamente o DataFrame final homologado e não contém regras de negócio.

## Arquitetura

```text
Active
  |
  v
Transformer
  |
  | DataFrame no contrato oficial de 22 colunas
  v
Persistence
  |-- DatabaseManager
  |-- MigrationManager
  `-- persist_dataframe()
  |
  v
SQLite / performance_entrega
```

A direção da dependência é única: o Transformer não conhece a persistência. A
persistência importa somente `active_sync.transformer.schema`, que fornece o
contrato oficial e o DDL. Não existem dependências com Excel, Power Query,
Comparator, Snapshot Validator ou Dataset Reconciliation.

## Estrutura

| Módulo | Responsabilidade |
|---|---|
| `persistence/database.py` | Conexão, execução SQL, commit, rollback e transações. |
| `persistence/migrations.py` | Criação e validação da tabela derivada do schema. |
| `persistence/writer.py` | Validação e persistência idempotente do DataFrame. |
| `persistence/exceptions.py` | Exceções específicas da camada. |
| `persistence/__init__.py` | API pública da persistência. |

## DatabaseManager

`DatabaseManager` recebe o caminho do SQLite e pode ser utilizado como context
manager. A entrada no contexto abre a conexão e cria o diretório necessário. A
saída desfaz qualquer transação não confirmada e fecha a conexão.

O método `transaction()` inicia uma transação explícita. O bloco recebe commit
automático quando termina normalmente e rollback quando uma exceção é lançada.
Também existem métodos explícitos `commit()` e `rollback()`.

## MigrationManager

`MigrationManager.migrate()`:

1. obtém o DDL por meio de `sqlite_ddl()`;
2. transforma somente a criação em `CREATE TABLE IF NOT EXISTS`;
3. cria `performance_entrega` dentro de uma transação;
4. compara nome, ordem, tipo e nulabilidade reais com `TRANSFORMER_SCHEMA`;
5. interrompe a execução com `MigrationError` se houver drift.

Nenhuma definição das 22 colunas é duplicada na camada de persistência.

## persist_dataframe()

```python
inserted = persist_dataframe(frame, database)
```

A função exige nomes e ordem exatamente iguais ao contrato e rejeita nulos em
campos `NOT NULL`. Datas são convertidas para ISO `YYYY-MM-DD`, booleanos para
`0/1` e valores pandas/numpy para escalares aceitos pelo SQLite. O retorno é a
quantidade efetiva de linhas inseridas.

## Idempotência

A identidade utilizada nesta Sprint é o conteúdo completo da linha persistente.
Antes de cada `INSERT`, a função executa uma verificação `NOT EXISTS` gerada a
partir das 22 colunas de `TRANSFORMER_SCHEMA`. A comparação usa o operador
SQLite `IS`, que considera dois valores nulos equivalentes.

Consequências da estratégia:

- executar duas vezes a mesma carga insere zero linhas na segunda execução;
- duplicidades internas no mesmo DataFrame também são ignoradas;
- não existe `DELETE FROM` nem substituição destrutiva;
- uma alteração real em qualquer coluna é preservada como novo estado;
- nenhuma chave de negócio foi inventada antes da futura camada Repository.

O custo é uma comparação integral por linha. É adequado ao volume atual da POC.
Quando a identidade de negócio for homologada, um índice ou uma estratégia de
upsert poderá ser introduzido por migração, sem alterar o Transformer.

## Exemplo de uso

```python
from pathlib import Path

from active_sync.persistence import (
    DatabaseManager,
    MigrationManager,
    persist_dataframe,
)

with DatabaseManager(Path("data/active_sync.sqlite3")) as database:
    MigrationManager(database).migrate()
    inserted = persist_dataframe(transformed_frame, database)
```

## Garantias testadas

- criação automática do arquivo e do diretório;
- criação e repetição segura da migração;
- detecção de drift estrutural;
- tipos SQLite e valores nulos;
- commit e rollback;
- rejeição de contrato inválido;
- idempotência com nulos e duplicidades internas;
- fronteira de dependências entre Transformer e Persistence.

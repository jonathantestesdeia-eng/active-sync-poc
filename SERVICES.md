# Camada Services

Implementada na Sprint 14 como fronteira de aplicação que será consumida pela
futura API do SuperTrack.

## Arquitetura

```text
Transformer
    |
    v
Persistence
    |
    v
Repository
    |
    v
Services
    |-- PerformanceService
    `-- DashboardService
    |
    v
API (Sprint 15)
```

Services conhece exclusivamente a API pública de Repository. Não importa
SQLite, Persistence, Transformer, pandas, Excel, Comparator ou Snapshot
Validator e não contém instruções SQL.

## Estrutura

| Módulo | Responsabilidade |
|---|---|
| `services/performance_service.py` | Coordenar consultas e converter o DTO público em filtros da Repository. |
| `services/dashboard_service.py` | Calcular contagens, percentuais e distribuições. |
| `services/exceptions.py` | Expor erros estáveis da camada de aplicação. |
| `services/__init__.py` | API pública dos Services. |

## PerformanceService

Métodos disponíveis:

- `listar()`;
- `buscar_nf()`;
- `buscar_transportadora()`;
- `buscar_periodo()`;
- `buscar_atrasadas()`;
- `buscar_em_aberto()`;
- `buscar_devolvidas()`;
- `contar()`.

O serviço apenas coordena chamadas da Repository. Os resultados são modelos
imutáveis `PerformanceEntrega`, nunca cursores ou `sqlite3.Row`.

### PerformanceQuery

`PerformanceQuery` é o DTO público de filtros, paginação e ordenação. Ele evita
que a futura API precise construir ou conhecer `PerformanceFilters`.

```python
query = PerformanceQuery(
    transportadora="TRANS A",
    uf_destino="SP",
    situacao="ATRASADA",
    periodo_inicio="2026-07-01",
    periodo_fim="2026-07-31",
    limit=50,
    offset=0,
    order_by="Saída",
)
registros = performance_service.listar(query)
```

## DashboardService

### Contagens

- `total_registros()`;
- `total_atrasadas()`;
- `total_em_aberto()`;
- `total_entregues()`;
- `total_devolvidas()`.

### Percentuais

- `percentual_atraso()`;
- `percentual_entregues()`;
- `percentual_devolvidas()`.

Os percentuais são calculados sobre `total_registros`, arredondados para duas
casas decimais. Uma base vazia retorna `0.0`, evitando divisão por zero.

### Distribuições

- `transportadoras()`;
- `ufs()`;
- `cidades()`.

Esses métodos retornam tuplas imutáveis de `CategoryCount(label, count)`,
ordenadas por quantidade decrescente e depois pelo nome. Valores nulos ou vazios
são ignorados e espaços externos são removidos.

```python
for item in dashboard_service.transportadoras():
    print(item.label, item.count)
```

## Exceções

`PerformanceService` converte `RepositoryError` em `ServiceError`.
`DashboardService` converte a mesma fronteira em `DashboardError`. Assim,
detalhes do banco ou da Repository não atravessam os Services.

## Fluxo de utilização

```python
from active_sync.services import DashboardService, PerformanceService

performance_service = PerformanceService(repository)
dashboard_service = DashboardService(repository)

registros = performance_service.buscar_nf("NF-001")
total = dashboard_service.total_registros()
atraso = dashboard_service.percentual_atraso()
```

Na Sprint 15, a API deverá receber instâncias desses serviços e não poderá
acessar Repository, Persistence ou SQLite diretamente.

## Garantias arquiteturais

- nenhuma instrução SQL nos Services;
- nenhuma importação de SQLite, pandas, Excel, Persistence ou Transformer;
- Repository não conhece Services;
- respostas não expõem cursores ou linhas SQLite;
- DTOs são imutáveis;
- não existem dependências circulares.

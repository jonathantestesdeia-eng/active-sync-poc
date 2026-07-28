# Perfil operacional do SuperTrack

Atualizado em 23/07/2026.

## Separação dos domínios

`ACTIVE_SYNC_PROFILE` seleciona uma única estratégia no início da aplicação:

- `supertrack` (padrão): preserva todos os movimentos não cancelados;
- `performance`: mantém a reconciliação homologada de Performance Entrega.

O perfil Performance continua usando `performance_entrega`, com a allowlist
`ENTREGA NORMAL`/`REENTREGA`, exigência de saída, exclusão de destinatário
igual ao tomador e validação financeira. Essas regras não são executadas pelo
perfil SuperTrack.

O perfil SuperTrack usa a tabela independente `supertrack_movements`. Apenas
registros com `Cancelamento` contendo uma data ou indicador explícito
(`1`, `true`, `s`, `sim`, `cancelado`, `cancelada`) são removidos. Observações
não são usadas para inferir cancelamento.

## Identidade operacional

A chave escolhida é
`(transportador_id, serie_cte, cte, nota_fiscal)`. Todos esses campos existem
na exportação real. Uma NF com CT-es diferentes mantém todos os movimentos e
reprocessar o mesmo arquivo é idempotente.

## Migração e rollback

A migração `002_supertrack_movements` é aditiva, registrada em
`schema_migrations`, e não altera `performance_entrega`.

Backup local criado antes da aplicação:
`data/backups/active_sync_pre_supertrack_20260723.sqlite3`.

Para rollback, interrompa a API, preserve a base atual para diagnóstico e
restaure essa cópia. Para reprocessar um arquivo na visão operacional:

```powershell
python scripts/import_supertrack_snapshot.py <excel-bruto> `
  --database data/active_sync.sqlite3 --full
```

## Validação real

O snapshot `Conhecimento - CTe_23072026_083302.xlsx` produziu:

- 1.652 registros lidos;
- 1 cancelamento removido;
- 1.651 movimentos preservados;
- 36 devoluções preservadas.

A NF `1015048` foi localizada com CT-e `28340`, tipo `DEVOLUCAO`,
transportadora `ATIVA`, destinatário `SUPERMED` e observação preservada.
As NFs `1020846` e `1022005` possuem dois movimentos na base e não foram
colapsadas.

## Sprint 19 — base histórica consolidada

`supertrack_movements` é uma base única de movimentos logísticos. Cada Excel
baixado é somente uma atualização parcial; o arquivo não cria banco, tabela ou
snapshot permanente próprio.

Todos os modos usam a mesma política:

1. consultar as chaves existentes em lote;
2. inserir chaves novas;
3. atualizar valores alterados;
4. atualizar `last_seen_at` e `last_sync_id` nas chaves reencontradas;
5. preservar movimentos que não vieram no arquivo;
6. excluir somente chaves que o próprio Active marcou como canceladas.

Isso também se aplica ao modo `FULL`: “completa” define o intervalo solicitado,
não autoriza apagar movimentos ausentes.

Os metadados técnicos são:

- `first_seen_at`: primeira aparição;
- `last_seen_at`: sincronização mais recente em que apareceu;
- `last_sync_id`: request ID dessa sincronização;
- `created_at`: criação do registro;
- `updated_at`: última alteração nos dados do movimento.

A migração `003_historical_consolidation` adiciona esses campos sem reconstruir
nem apagar a tabela. O backup anterior à Sprint 19 está em
`data/backups/active_sync_pre_sprint19_20260723.sqlite3`.

### Janela deslizante

`ACTIVE_SYNC_INCREMENTAL_LOOKBACK_DAYS` controla a sobreposição automática.
Usar 7 ou 15 dias apenas reencontra e atualiza as mesmas chaves; não gera
duplicidade. Reprocessar qualquer período tem a mesma semântica de UPSERT.

### Auditoria

`sync_execution` registra período, modo, arquivos, perfil, início, fim,
duração, status, mensagem e quantidades lidas, inseridas, atualizadas,
ignoradas e canceladas. Os registros anteriores de `sync_history` são copiados
de forma idempotente durante a inicialização.

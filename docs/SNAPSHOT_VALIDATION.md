# Snapshot Validation

## Objetivo

O Snapshot Validator identifica se o DataFrame transformado e a referência Power Query representam o mesmo momento operacional antes da leitura dos percentuais de equivalência.

Ele não altera os DataFrames, não remove linhas, não preenche valores e não apaga datas. Sua função é separar divergências temporais de possíveis divergências de transformação.

## Arquitetura

O módulo `active_sync.transformer.snapshot_validator` permanece independente das regras de transformação. O comparador o executa antes da comparação célula a célula e inclui o diagnóstico no início do relatório.

Fluxo:

```text
DataFrame Python + Power Query
            │
            ▼
   Snapshot Validator
            │
            ├── classificação temporal
            └── evidências por coluna
            │
            ▼
       Comparador normal
```

As colunas temporais iniciais são `Saída`, `Previsão` e `Entrega`. `Data` e `Data3` não são avaliadas porque, na referência atual, representam nomes de mês.

## Alinhamento

- Chave padrão: `Nota Fiscal`.
- Duplicidades são associadas pela ordem de aparição.
- Valores de chave nulos não são associados artificialmente.
- Linhas exclusivas permanecem na análise como preenchimento de apenas um lado.
- Horários são ignorados; compara-se a parte da data.

## Classificações

### `COMPATIBLE`

Não existem diferenças temporais relevantes nas colunas comparáveis.

### `TEMPORAL_MISMATCH`

Os preenchimentos adicionais seguem uma única direção — somente no bruto ou somente na referência — e não existem datas conflitantes quando os dois lados estão preenchidos. Esse padrão representa enriquecimento posterior de um snapshot, não substituição de datas.

### `INCONCLUSIVE`

Não há evidência suficiente para determinar a relação temporal. Exemplos: preenchimentos exclusivos nos dois lados, colunas apontando para direções opostas, chaves ausentes ou valores de data inválidos.

### `DATA_DIVERGENCE`

O mesmo registro possui datas preenchidas e diferentes nos dois arquivos. Essa situação deve ser investigada como diferença de dados ou regra, e não é automaticamente atribuída ao snapshot.

## Heurística

A evidência principal é baseada no conteúdo:

1. alinhamento por Nota Fiscal e ocorrência;
2. comparação segura das datas;
3. identificação de preenchimentos exclusivos e conflitos;
4. classificação temporal apenas quando a direção dos preenchimentos é consistente e não há conflito de datas preenchidas.

Como evidência auxiliar, o módulo calcula a proporção de datas exclusivas posteriores à maior data do outro arquivo. A constante nomeada `NEARLY_ALL_LATER_RATIO` vale 90%: esse nível reduz o risco de interpretar poucos outliers como tendência temporal. Essa proporção não substitui a evidência principal de preenchimento unidirecional.

## Valores inválidos e colunas ausentes

- Datas inválidas são convertidas com segurança para ausência comparável e contabilizadas separadamente.
- A presença de valores inválidos torna a classificação inconclusiva.
- Colunas ausentes geram aviso e as demais colunas comuns continuam sendo avaliadas.
- Se a chave de alinhamento estiver ausente, o resultado é `INCONCLUSIVE`.

## Modos de execução

### Modo normal

O comparador registra o diagnóstico e continua calculando a equivalência:

```python
report = compare_dataframes(
    df_python,
    df_powerquery,
    key_columns=["Nota Fiscal"],
)
```

### Modo estrito

O parâmetro equivalente a `--require-compatible-snapshot` é `require_compatible_snapshot=True`. Como o CLI atual não possui um comando de comparação, a opção foi disponibilizada na API do comparador:

```python
report = compare_dataframes(
    df_python,
    df_powerquery,
    key_columns=["Nota Fiscal"],
    require_compatible_snapshot=True,
)
```

Os estados `TEMPORAL_MISMATCH` e `INCONCLUSIVE` geram `IncompatibleSnapshotError`, uma exceção específica e controlada. `DATA_DIVERGENCE` permanece disponível para investigação funcional.

## Arquivos atuais

- Bruto: `Conhecimento - CTe_21072026_152324.xlsx`.
- Referência: `teste.junho.xlsx`, aba `Performance Entrega`.
- Classificação: **`TEMPORAL_MISMATCH`**.

### Evidência de Entrega

| Métrica | Bruto | Referência |
|---|---:|---:|
| Valores preenchidos | 781 | 621 |
| Menor data | 16/07/2026 | 16/07/2026 |
| Maior data | 21/07/2026 | 20/07/2026 |

| Comparação alinhada | Quantidade |
|---|---:|
| Mesma data preenchida | 621 |
| Nulo nos dois lados | 295 |
| Somente no bruto | 160 |
| Somente na referência | 0 |
| Datas conflitantes | 0 |

A equivalência medida de Entrega continua em **85,13%**. A implementação técnica permanece consistente com a regra identificada, mas a validação final é inconclusiva com este par de snapshots.

## Limitações

- O validador não determina a hora exata de geração de um arquivo.
- Metadados e nomes de arquivos são apenas evidências auxiliares.
- A classificação não substitui a análise funcional quando há datas conflitantes.
- `TEMPORAL_MISMATCH` não significa que um arquivo esteja incorreto; significa que o par não é adequado para certificar equivalência temporal.

## Relatórios

- Diagnóstico da execução atual: `docs/snapshot_validation.txt`.
- Comparação completa com Snapshot Validation no início: `docs/equivalencia_detalhada.txt`.

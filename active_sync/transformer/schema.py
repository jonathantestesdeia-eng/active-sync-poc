"""Contrato persistente e independente de banco do Transformer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import re
from typing import Final


class ColumnStatus(StrEnum):
    """Classificações permitidas na auditoria do contrato final."""

    IMPLEMENTED = "IMPLEMENTADA"
    PENDING_VALIDATION = "IMPLEMENTADA COM VALIDAÇÃO PENDENTE"
    NOT_IMPLEMENTED = "NÃO IMPLEMENTADA"
    OUT_OF_SCOPE = "FORA DO ESCOPO"


@dataclass(frozen=True, slots=True)
class ColumnSchema:
    """Metadados de uma coluna do DataFrame e da persistência futura."""

    name: str
    pandas_dtype: str
    sqlite_type: str
    postgresql_type: str
    nullable: bool
    description: str
    source: str
    rule: str
    dependencies: tuple[str, ...]
    status: ColumnStatus


def _text(
    name: str,
    description: str,
    source: str,
    rule: str,
    dependencies: tuple[str, ...],
    status: ColumnStatus = ColumnStatus.IMPLEMENTED,
    *,
    nullable: bool = True,
) -> ColumnSchema:
    return ColumnSchema(
        name=name,
        pandas_dtype="object",
        sqlite_type="TEXT",
        postgresql_type="TEXT",
        nullable=nullable,
        description=description,
        source=source,
        rule=rule,
        dependencies=dependencies,
        status=status,
    )


TRANSFORMER_SCHEMA: Final[tuple[ColumnSchema, ...]] = (
    _text("CNPJ", "CNPJ normalizado do destinatário.", "Destinatário", "Extrai o prefixo numérico e remove zeros iniciais.", ("Destinatário",)),
    _text("Destinatário", "Nome operacional do destinatário.", "Destinatário", "Conserva a segunda parte do texto separado por hífen.", ("Destinatário",)),
    _text("Cidade Origem", "Cidade de origem do transporte.", "Cidade Origem", "Texto normalizado diretamente da origem.", ("Cidade Origem",)),
    _text("Cidade Destino", "Cidade de destino do transporte.", "Cidade Destino", "Texto normalizado diretamente da origem.", ("Cidade Destino",)),
    _text("UF Destino", "UF de destino do transporte.", "UF Destino", "Texto normalizado diretamente da origem.", ("UF Destino",)),
    _text("Nota Fiscal", "Identificador da Nota Fiscal.", "Nota Fiscal", "Preserva o identificador como texto.", ("Nota Fiscal",)),
    ColumnSchema("Valor Frete", "Float64", "REAL", "DOUBLE PRECISION", True, "Valor total do frete.", "Valor Frete", "Conversão numérica segura em tipo anulável.", ("Valor Frete",), ColumnStatus.IMPLEMENTED),
    ColumnSchema("Saída", "datetime64[ns]", "TEXT", "DATE", True, "Data civil de saída.", "Saída", "Conversão segura para data.", ("Saída",), ColumnStatus.IMPLEMENTED),
    ColumnSchema("Previsão", "datetime64[ns]", "TEXT", "DATE", True, "Data civil prevista para entrega.", "Previsão", "Conversão segura para data.", ("Previsão",), ColumnStatus.IMPLEMENTED),
    ColumnSchema("Entrega", "datetime64[ns]", "TEXT", "DATE", True, "Data civil efetiva da entrega.", "Entrega", "Conversão segura para data.", ("Entrega",), ColumnStatus.IMPLEMENTED),
    _text("Transportadora", "Nome operacional normalizado da transportadora.", "Transportador", "Aplica o primeiro mapeamento textual correspondente.", ("Transportador",)),
    ColumnSchema("Flag Devolução NF", "bool", "INTEGER", "BOOLEAN", False, "Indica devolução no nível da Nota Fiscal.", "Tipo, Observacao, Trecho, Cidade Destino, CTe e Nota Fiscal", "Texto DEVOLU ou múltiplos CT-es com destino ARUJA/CAMBUI.", ("Tipo", "Observacao", "Trecho", "Cidade Destino", "CTe", "Nota Fiscal"), ColumnStatus.PENDING_VALIDATION),
    _text("Tipo CTe", "Tipo operacional do conhecimento.", "Tipo", "Usa DEVOLUCAO quando a Flag é verdadeira; caso contrário, conserva Tipo.", ("Tipo", "Flag Devolução NF")),
    _text("CTe Devolução", "CT-es candidatos da devolução agregados por Nota Fiscal.", "CTe", "Concatena candidatos distintos quando a Flag é verdadeira.", ("CTe", "Nota Fiscal", "Flag Devolução NF"), ColumnStatus.PENDING_VALIDATION),
    _text("Código cliente", "Código interno do cliente.", "Base clientes.xlsx/Planilha1", "Left join entre CNPJ e Cnpj2.", ("CNPJ", "Cnpj2", "Código cliente")),
    _text("Prazo", "Classificação do cumprimento do prazo.", "Flag Devolução NF, Entrega e Previsão", "Aplica a precedência oficial de devolução e datas.", ("Flag Devolução NF", "Entrega", "Previsão"), nullable=False),
    _text("Data", "Nome do mês da Entrega em português.", "Entrega", "Converte o mês para texto minúsculo.", ("Entrega",)),
    ColumnSchema("Ano", "Int64", "INTEGER", "INTEGER", True, "Ano da Entrega.", "Entrega", "Extrai o ano como inteiro anulável.", ("Entrega",), ColumnStatus.IMPLEMENTED),
    _text("Prazo2", "Duplicação contratual da classificação Prazo.", "Prazo", "Reproduz a regra temporal homologada de Prazo.", ("Entrega", "Previsão"), nullable=False),
    _text("Data3", "Duplicação contratual do mês textual de Data.", "Data", "Copia Data sem recalcular a regra.", ("Data",)),
    ColumnSchema("Ano4", "Int64", "INTEGER", "INTEGER", True, "Duplicação contratual do ano da Entrega.", "Ano", "Copia Ano sem recalcular a regra.", ("Ano",), ColumnStatus.IMPLEMENTED),
    _text("Situação", "Situação operacional criada como Situação Active.", "Flag Devolução NF, Entrega, Previsão e data da atualização", "Aplica DEVOLVIDA, ENTREGUE, SEM PREVISÃO, ATRASADA, PREVISTA PARA HOJE ou EM ABERTO.", ("Flag Devolução NF", "Entrega", "Previsão", "Hoje"), ColumnStatus.PENDING_VALIDATION, nullable=False),
)


def _validate_table_name(table_name: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name) is None:
        raise ValueError(f"Nome de tabela inválido: {table_name!r}")
    return table_name


def _ddl(table_name: str, dialect: str) -> str:
    table = _validate_table_name(table_name)
    type_attribute = "sqlite_type" if dialect == "sqlite" else "postgresql_type"
    definitions = []
    for column in TRANSFORMER_SCHEMA:
        nullability = "" if column.nullable else " NOT NULL"
        definitions.append(
            f'    "{column.name}" {getattr(column, type_attribute)}{nullability}'
        )
    return f'CREATE TABLE "{table}" (\n' + ",\n".join(definitions) + "\n);"


def sqlite_ddl(table_name: str = "performance_entrega") -> str:
    """Retorna o DDL SQLite sem executar qualquer acesso a banco."""
    return _ddl(table_name, "sqlite")


def postgresql_ddl(table_name: str = "performance_entrega") -> str:
    """Retorna o DDL PostgreSQL sem executar qualquer acesso a banco."""
    return _ddl(table_name, "postgresql")


def schema_markdown() -> str:
    """Gera a documentação Markdown diretamente do contrato oficial."""
    lines = [
        "# Contrato Persistente do Transformer",
        "",
        "Este documento é gerado a partir de `active_sync.transformer.schema`.",
        "O módulo descreve a persistência futura, mas não acessa banco de dados.",
        "",
        "## Colunas",
        "",
        "| Ordem | Nome | Status | pandas | SQLite | PostgreSQL | Nulo | Origem | Dependências | Descrição e regra |",
        "|---:|---|---|---|---|---|---|---|---|---|",
    ]
    for order, column in enumerate(TRANSFORMER_SCHEMA, start=1):
        dependencies = ", ".join(column.dependencies)
        description = f"{column.description} {column.rule}"
        lines.append(
            f"| {order} | {column.name} | {column.status.value} | "
            f"{column.pandas_dtype} | {column.sqlite_type} | "
            f"{column.postgresql_type} | {'Sim' if column.nullable else 'Não'} | "
            f"{column.source} | {dependencies} | {description} |"
        )
    lines.extend(
        [
            "",
            "## SQLite",
            "",
            "```sql",
            sqlite_ddl(),
            "```",
            "",
            "## PostgreSQL",
            "",
            "```sql",
            postgresql_ddl(),
            "```",
            "",
            "## Convenções de persistência",
            "",
            "- Datas usam ISO `YYYY-MM-DD` no SQLite e `DATE` no PostgreSQL.",
            "- Booleanos usam `0/1` no SQLite e `BOOLEAN` no PostgreSQL.",
            "- Identificadores permanecem textuais para preservar seu formato.",
            "- `schema.py` não cria conexões, tabelas ou migrações.",
            "",
        ]
    )
    return "\n".join(lines)


def write_schema_markdown(output_path: str | Path = Path("docs/SCHEMA.md")) -> Path:
    """Grava a documentação gerada de forma atômica."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(schema_markdown(), encoding="utf-8")
    temporary.replace(destination)
    return destination

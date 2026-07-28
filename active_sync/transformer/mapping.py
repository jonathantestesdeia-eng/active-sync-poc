"""Mapeamento central entre o Excel bruto e o layout tratado."""

from typing import Final


# Colunas da tabela cadastral usada pelo Power Query no merge de clientes.
CLIENT_LOOKUP_CNPJ_COLUMN: Final[str] = "Cnpj2"
CLIENT_LOOKUP_CODE_COLUMN: Final[str] = "Código cliente"

# Ordem relevante: o Power Query utiliza a primeira correspondência encontrada.
TRANSPORTADORA_MAPPING: Final[tuple[tuple[str, str], ...]] = (
    ("ATIVA", "ATIVA"),
    ("JAMEF", "JAMEF"),
    ("EXCARGO", "EXCARGO"),
    ("MINUANO", "MINUANO"),
    ("PATRUS", "PATRUS"),
    ("POTENZA", "POTENZA"),
    ("TARGG", "TARGG"),
    ("VIA MINAS", "VIAMINAS"),
    ("FL BRASIL", "TRAGETTA"),
    ("SOLISTICA", "TRAGETTA"),
    ("PVN", "PVN"),
    ("TRAGETTA", "TRAGETTA"),
    ("BINHO", "BINHO"),
)
DEFAULT_TRANSPORTADORA: Final[str] = "SUPERMED"

# Entradas e resultados comprovados da classificação de prazo do Power Query.
PRAZO_DELIVERY_COLUMN: Final[str] = "Entrega"
PRAZO_FORECAST_COLUMN: Final[str] = "Previsão"
PRAZO_WITHOUT_DELIVERY: Final[str] = "SEM INFORMAÇÃO DE ENTREGA"
PRAZO_ON_TIME: Final[str] = "ENTREGUE NO PRAZO"
PRAZO_LATE: Final[str] = "ENTREGUE COM ATRASO"
PRAZO_RETURNED: Final[str] = "DEVOLVIDA"
PRAZO_WITHOUT_FORECAST: Final[str] = "SEM INFORMAÇÃO DE PREVISÃO"

# Resultados da coluna `Situação Active` na consulta M oficial.
SITUACAO_RETURNED: Final[str] = "DEVOLVIDA"
SITUACAO_DELIVERED: Final[str] = "ENTREGUE"
SITUACAO_WITHOUT_FORECAST: Final[str] = "SEM PREVISÃO"
SITUACAO_LATE: Final[str] = "ATRASADA"
SITUACAO_DUE_TODAY: Final[str] = "PREVISTA PARA HOJE"
SITUACAO_OPEN: Final[str] = "EM ABERTO"

# Etapas e constantes transcritas da consulta M oficial de devolução.
RETURN_TYPE_COLUMN: Final[str] = "Tipo"
RETURN_OBSERVATION_COLUMN: Final[str] = "Observacao"
RETURN_ROUTE_COLUMN: Final[str] = "Trecho"
RETURN_DESTINATION_COLUMN: Final[str] = "Cidade Destino"
RETURN_CTE_COLUMN: Final[str] = "CTe"
RETURN_NOTE_COLUMN: Final[str] = "Nota Fiscal"
RETURN_TEXT_TOKEN: Final[str] = "DEVOLU"
RETURN_DESTINATION_CITIES: Final[frozenset[str]] = frozenset({"ARUJA", "CAMBUI"})
RETURN_TYPE_LABEL: Final[str] = "DEVOLUCAO"
RETURN_SOURCE_COLUMNS: Final[tuple[str, ...]] = (
    RETURN_TYPE_COLUMN,
    RETURN_OBSERVATION_COLUMN,
    RETURN_ROUTE_COLUMN,
    RETURN_DESTINATION_COLUMN,
    RETURN_CTE_COLUMN,
    RETURN_NOTE_COLUMN,
)

# Todas as colunas do contrato final possuem origem ou dependência comprovada.
COLUMN_MAPPING: Final[dict[str, str]] = {
    "CNPJ": "Destinatário",
    "Destinatário": "Destinatário",
    "Cidade Origem": "Cidade Origem",
    "Cidade Destino": "Cidade Destino",
    "UF Destino": "UF Destino",
    "Nota Fiscal": "Nota Fiscal",
    "Valor Frete": "Valor Frete",
    "Saída": "Saída",
    "Previsão": "Previsão",
    "Entrega": "Entrega",
    "Transportadora": "Transportador",
    "Flag Devolução NF": RETURN_NOTE_COLUMN,
    "Tipo CTe": "Tipo",
    "CTe Devolução": RETURN_NOTE_COLUMN,
    "Código cliente": None,
    "Prazo": PRAZO_DELIVERY_COLUMN,
    "Data": "Entrega",
    "Ano": "Entrega",
    "Prazo2": PRAZO_DELIVERY_COLUMN,
    "Data3": "Entrega",
    "Ano4": "Entrega",
    "Situação": PRAZO_DELIVERY_COLUMN,
}

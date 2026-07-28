from __future__ import annotations

import pandas as pd

from active_sync.transformer import (
    build_cte_devolucao,
    build_flag_devolucao_nf,
    build_tipo_cte,
    transform_dataframe,
)


def return_source() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Nota Fiscal": ["A", "A", "B", "C", "D", "D", "E", "E", "F"],
            "CTe": [100, 200, 300, 400, 500, 500, 600, 700, None],
            "Tipo": [
                "ENTREGA NORMAL",
                "ENTREGA NORMAL",
                "ENTREGA NORMAL",
                "ENTREGA NORMAL",
                "ENTREGA NORMAL",
                "ENTREGA NORMAL",
                "devolucao",
                "ENTREGA NORMAL",
                "ENTREGA NORMAL",
            ],
            "Observacao": [None, None, None, "Material DEVOLUCAO", None, None, None, None, "DEVOLUCAO"],
            "Trecho": ["NORMAL"] * 7 + ["rota de DEVOLUCAO", "NORMAL"],
            "Cidade Destino": [
                " ARUJA ",
                "SAO PAULO",
                "cambui",
                "RIO DE JANEIRO",
                "ARUJA",
                "SAO PAULO",
                "SAO PAULO",
                "CAMBUI",
                "SAO PAULO",
            ],
        },
        index=pd.Index([11, 22, 33, 44, 55, 66, 77, 88, 99], name="linha"),
    )


def test_flag_reproduces_text_destination_grouping_and_distinct_cte_rules() -> None:
    source = return_source()

    result = build_flag_devolucao_nf(source)

    assert result.index.equals(source.index)
    assert result.dtype == "bool"
    assert result.tolist() == [True, True, False, True, False, False, True, True, True]


def test_single_cte_to_return_destination_does_not_set_flag() -> None:
    source = return_source().loc[[33]]

    assert build_flag_devolucao_nf(source).tolist() == [False]
    assert build_cte_devolucao(source).tolist() == [None]


def test_duplicate_same_cte_does_not_count_as_multiple_knowledge_documents() -> None:
    source = return_source().loc[[55, 66]]

    assert build_flag_devolucao_nf(source).tolist() == [False, False]


def test_multiple_ctes_with_cambui_set_flag_without_text_signal() -> None:
    source = pd.DataFrame(
        {
            "Nota Fiscal": ["G", "G"],
            "CTe": ["800", "900"],
            "Tipo": ["ENTREGA NORMAL", "ENTREGA NORMAL"],
            "Observacao": [None, None],
            "Trecho": ["NORMAL", "NORMAL"],
            "Cidade Destino": ["SAO PAULO", " CAMBUI "],
        },
        index=[101, 202],
    )

    assert build_flag_devolucao_nf(source).tolist() == [True, True]
    assert build_cte_devolucao(source).tolist() == ["900", "900"]


def test_multiple_ctes_without_text_or_return_destination_keep_false_flag() -> None:
    source = pd.DataFrame(
        {
            "Nota Fiscal": ["H", "H"],
            "CTe": ["1000", "1100"],
            "Tipo": ["ENTREGA NORMAL", "REENTREGA"],
            "Observacao": [None, "SEM OCORRENCIA"],
            "Trecho": ["NORMAL", "NORMAL"],
            "Cidade Destino": ["SAO PAULO", "RIO DE JANEIRO"],
        }
    )

    assert build_flag_devolucao_nf(source).tolist() == [False, False]
    assert build_cte_devolucao(source).tolist() == [None, None]


def test_cte_return_uses_only_candidates_and_preserves_distinct_source_order() -> None:
    source = return_source()

    result = build_cte_devolucao(source)

    assert result.index.equals(source.index)
    assert result.tolist() == [
        "100",
        "100",
        None,
        "400",
        None,
        None,
        "600, 700",
        "600, 700",
        "",
    ]


def test_return_text_is_combined_from_type_observation_and_route_case_insensitively() -> None:
    source = return_source().loc[[44, 77, 88]]

    assert build_flag_devolucao_nf(source).tolist() == [True, True, True]


def test_tipo_cte_changes_only_flagged_rows_and_preserves_index() -> None:
    types = pd.Series([" ENTREGA NORMAL ", "REENTREGA", None], index=[5, 7, 9])
    flags = pd.Series([True, False, False], index=types.index)

    result = build_tipo_cte(types, flags)

    assert result.index.equals(types.index)
    assert result.tolist() == ["DEVOLUCAO", "REENTREGA", None]


def test_transformer_updates_flag_cte_type_and_prazo_in_official_order() -> None:
    source = pd.DataFrame(
        {
            "Destinatário": ["123 - CLIENTE"],
            "Cidade Origem": ["CAMPINAS"],
            "Cidade Destino": ["SAO PAULO"],
            "UF Destino": ["SP"],
            "Nota Fiscal": ["NF1"],
            "CTe": ["00045"],
            "Valor Frete": [10],
            "Saída": ["20/07/2026"],
            "Previsão": [None],
            "Entrega": [None],
            "Transportador": ["JAMEF"],
            "Tipo": ["ENTREGA NORMAL"],
            "Observacao": ["Mercadoria em devolução"],
            "Trecho": ["NORMAL"],
        },
        index=[42],
    )

    result = transform_dataframe(source)

    assert result.index.tolist() == [42]
    assert result.loc[42, "Flag Devolução NF"] == True
    assert result.loc[42, "CTe Devolução"] == "00045"
    assert result.loc[42, "Tipo CTe"] == "DEVOLUCAO"
    assert result.loc[42, "Prazo"] == "DEVOLVIDA"
    assert result.loc[42, "Prazo2"] == "SEM INFORMAÇÃO DE ENTREGA"

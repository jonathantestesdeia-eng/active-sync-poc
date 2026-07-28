from __future__ import annotations

from datetime import date

import pandas as pd

from active_sync.transformer import build_situacao, transform_dataframe


def test_build_situacao_reproduces_all_official_results_in_precedence_order() -> None:
    index = pd.Index([10, 20, 30, 40, 50, 60], name="linha")
    result = build_situacao(
        pd.Series([True, False, False, False, False, False], index=index),
        pd.Series(["20/07/2026", "21/07/2026", None, None, None, None], index=index),
        pd.Series(
            [None, None, None, "21/07/2026", "22/07/2026", "23/07/2026"],
            index=index,
        ),
        reference_date=date(2026, 7, 22),
    )

    assert result.index.equals(index)
    assert result.dtype == "object"
    assert result.tolist() == [
        "DEVOLVIDA",
        "ENTREGUE",
        "SEM PREVISÃO",
        "ATRASADA",
        "PREVISTA PARA HOJE",
        "EM ABERTO",
    ]


def test_build_situacao_prioritizes_return_over_delivery_and_forecast() -> None:
    result = build_situacao(
        pd.Series([True, True, True]),
        pd.Series(["21/07/2026", None, None]),
        pd.Series(["21/07/2026", None, "20/07/2026"]),
        reference_date=date(2026, 7, 22),
    )

    assert result.tolist() == ["DEVOLVIDA", "DEVOLVIDA", "DEVOLVIDA"]


def test_build_situacao_treats_empty_and_invalid_dates_as_absent() -> None:
    result = build_situacao(
        pd.Series([False, False]),
        pd.Series(["", "data inválida"]),
        pd.Series(["", "previsão inválida"]),
        reference_date=date(2026, 7, 22),
    )

    assert result.tolist() == ["SEM PREVISÃO", "SEM PREVISÃO"]


def test_transformer_integrates_situacao_after_return_flag() -> None:
    source = pd.DataFrame(
        {
            "Destinatário": ["123 - CLIENTE"],
            "Cidade Origem": ["CAMPINAS"],
            "Cidade Destino": ["SAO PAULO"],
            "UF Destino": ["SP"],
            "Nota Fiscal": ["NF1"],
            "CTe": ["001"],
            "Valor Frete": [10],
            "Saída": ["20/07/2026"],
            "Previsão": [None],
            "Entrega": [None],
            "Transportador": ["JAMEF"],
            "Tipo": ["ENTREGA NORMAL"],
            "Observacao": ["DEVOLUCAO"],
            "Trecho": ["NORMAL"],
        },
        index=[42],
    )

    result = transform_dataframe(source)

    assert result.loc[42, "Flag Devolução NF"] == True
    assert result.loc[42, "Situação"] == "DEVOLVIDA"

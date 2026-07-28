from __future__ import annotations

import locale
from collections.abc import Callable

import pandas as pd
import pytest

from active_sync.exceptions import TransformationValidationError
from active_sync.transformer.columns import OUTPUT_COLUMNS
from active_sync.transformer.mapping import COLUMN_MAPPING
from active_sync.transformer.transforms import (
    build_cnpj,
    build_codigo_cliente,
    build_data,
    build_destinatario,
    build_entrega,
    build_ano,
    build_prazo,
    build_prazo2,
    build_transportadora,
    safe_number_series,
    transform_dataframe,
    trim_text,
)
from active_sync.transformer.validator import (
    validate_output_dataframe,
    validate_source_dataframe,
)


def source_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Destinatário": ["  Cliente A  "],
            "CTe": [12345],
            "Cidade Origem": ["  CAMBUI "],
            "Cidade Destino": [" TUPA "],
            "UF Destino": [" SP "],
            "Nota Fiscal": ["000123"],
            "Valor Frete": ["1.234,56"],
            "Saída": ["21/07/2026"],
            "Previsão": ["29/07/2026"],
            "Entrega": [None],
            "Transportador": [" Transportadora X "],
            "Tipo": [" ENTREGA NORMAL "],
            "Observacao": [None],
            "Trecho": ["TRANSPORTE CONFORME CTE"],
        }
    )


def test_transformer_preserves_exact_layout_and_direct_mappings() -> None:
    result = transform_dataframe(source_frame())

    assert tuple(result.columns) == OUTPUT_COLUMNS
    assert result.loc[0, "Destinatário"] is None
    assert result.loc[0, "Transportadora"] == "SUPERMED"
    assert result.loc[0, "Nota Fiscal"] == "000123"
    assert result.loc[0, "Valor Frete"] == pytest.approx(1234.56)
    assert result.loc[0, "Saída"] == pd.Timestamp("2026-07-21")
    assert tuple(COLUMN_MAPPING) == OUTPUT_COLUMNS


def test_final_derived_columns_reuse_data_and_ano() -> None:
    result = transform_dataframe(source_frame())

    assert result["Data3"].tolist() == result["Data"].tolist()
    assert result["Ano4"].tolist() == result["Ano"].tolist()
    assert result["Data3"].dtype == "object"
    assert result["Ano4"].dtype == "Int64"
    assert result["Flag Devolução NF"].tolist() == [False]
    assert result["CTe Devolução"].tolist() == [None]


def test_build_cnpj_from_valid_recipient() -> None:
    result = build_cnpj(pd.Series(["11206099000441 - SUPERMED"]))

    assert result.tolist() == ["11206099000441"]


def test_build_cnpj_handles_empty_values() -> None:
    result = build_cnpj(pd.Series([None, "", "   "]))

    assert result.tolist() == [None, None, None]


def test_build_cnpj_reproduces_powerquery_leading_zero_normalization() -> None:
    result = build_cnpj(pd.Series(["02643405000173 - CLIENTE"]))

    assert result.tolist() == ["2643405000173"]


def test_build_cnpj_always_returns_text() -> None:
    result = build_cnpj(pd.Series([11206099000441]))

    assert result.dtype == "object"
    assert isinstance(result.iloc[0], str)


def test_build_cnpj_removes_formatting_from_prefix() -> None:
    result = build_cnpj(pd.Series(["11.206.099/0004-41 - SUPERMED"]))

    assert result.tolist() == ["11206099000441"]


def test_build_destinatario_from_valid_recipient() -> None:
    result = build_destinatario(pd.Series(["11206099000441 - CLÍNICA SÃO JOSÉ"]))

    assert result.tolist() == ["CLÍNICA SÃO JOSÉ"]


def test_build_destinatario_handles_empty_values() -> None:
    result = build_destinatario(pd.Series([None, "", "   ", "SEM SEPARADOR"]))

    assert result.tolist() == [None, None, None, None]


def test_build_destinatario_trims_spaces() -> None:
    result = build_destinatario(pd.Series(["123 -   CLIENTE TESTE   "]))

    assert result.tolist() == ["CLIENTE TESTE"]


def test_build_destinatario_reproduces_powerquery_third_part_removal() -> None:
    result = build_destinatario(pd.Series(["123 - CLIENTE-UNIDADE ESPECIAL"]))

    assert result.tolist() == ["CLIENTE"]


def test_build_codigo_cliente_maps_valid_cnpj_and_preserves_text() -> None:
    register = pd.DataFrame({"Cnpj2": [123], "Código cliente": ["00456"]})

    result = build_codigo_cliente(pd.Series(["123"]), register)

    assert result.tolist() == ["00456"]
    assert result.dtype == "object"


def test_build_codigo_cliente_handles_empty_and_unknown_cnpj() -> None:
    register = pd.DataFrame({"Cnpj2": [123], "Código cliente": [456]})

    result = build_codigo_cliente(pd.Series([None, "", "999"]), register)

    assert result.tolist() == [None, None, None]


def test_build_codigo_cliente_converts_numeric_code_to_text() -> None:
    register = pd.DataFrame({"Cnpj2": [123.0], "Código cliente": [456.0]})

    result = build_codigo_cliente(pd.Series([123]), register)

    assert result.tolist() == ["456"]


def test_transformer_builds_only_sprint5_columns_with_client_register() -> None:
    source = source_frame()
    source.loc[0, "Destinatário"] = "00123 - CLIENTE-UNIDADE"
    register = pd.DataFrame({"Cnpj2": [123], "Código cliente": ["0007"]})

    result = transform_dataframe(source, client_register=register)

    assert result.loc[0, "CNPJ"] == "123"
    assert result.loc[0, "Destinatário"] == "CLIENTE"
    assert result.loc[0, "Código cliente"] == "0007"
    assert result.loc[0, "Prazo"] == "SEM INFORMAÇÃO DE ENTREGA"
    assert result.loc[0, "Prazo2"] == "SEM INFORMAÇÃO DE ENTREGA"


def test_build_transportadora_maps_valid_value_case_insensitively() -> None:
    result = build_transportadora(
        pd.Series(["20147617006859 - Jamef Transportes Ltda - Osasco"])
    )

    assert result.tolist() == ["JAMEF"]


def test_build_transportadora_handles_empty_values() -> None:
    result = build_transportadora(pd.Series([None, "", "   "]))

    assert result.tolist() == [None, None, None]


def test_build_transportadora_ignores_external_spaces() -> None:
    result = build_transportadora(pd.Series(["  18233211000130 - TRAGETTA  "]))

    assert result.tolist() == ["TRAGETTA"]


def test_build_transportadora_handles_special_characters_and_default() -> None:
    result = build_transportadora(
        pd.Series(["TRANSPORTADORA NÃO MAPEADA ÇÁ", "18233211007576 - SOLISTICA"])
    )

    assert result.tolist() == ["SUPERMED", "TRAGETTA"]


def test_build_entrega_converts_valid_date() -> None:
    result = build_entrega(pd.Series(["21/07/2026"]))

    assert result.iloc[0] == pd.Timestamp("2026-07-21")
    assert pd.api.types.is_datetime64_any_dtype(result.dtype)


def test_build_entrega_handles_empty_and_null_dates() -> None:
    result = build_entrega(pd.Series([None, "", "   "]))

    assert result.isna().all()


def test_build_entrega_accepts_different_date_formats() -> None:
    result = build_entrega(
        pd.Series([pd.Timestamp("2026-07-21"), "2026-07-20", "20/07/2026"])
    )

    assert result.tolist() == [
        pd.Timestamp("2026-07-21"),
        pd.Timestamp("2026-07-20"),
        pd.Timestamp("2026-07-20"),
    ]


def test_build_entrega_coerces_invalid_date_to_nat() -> None:
    result = build_entrega(pd.Series(["data inválida"]))

    assert result.isna().all()


def test_build_data_returns_all_portuguese_months_in_lowercase() -> None:
    source = pd.Series([f"15/{month:02d}/2026" for month in range(1, 13)])

    result = build_data(source)

    assert result.tolist() == [
        "janeiro",
        "fevereiro",
        "março",
        "abril",
        "maio",
        "junho",
        "julho",
        "agosto",
        "setembro",
        "outubro",
        "novembro",
        "dezembro",
    ]


def test_build_data_handles_null_and_invalid_values() -> None:
    result = build_data(pd.Series([None, "", "data inválida"]))

    assert result.tolist() == [None, None, None]


def test_build_data_ignores_time_and_preserves_index() -> None:
    source = pd.Series(
        [pd.Timestamp("2026-07-21 23:59:59")],
        index=pd.Index([42], name="linha"),
    )

    result = build_data(source)

    assert result.tolist() == ["julho"]
    assert result.index.equals(source.index)


def test_build_data_does_not_depend_on_system_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("build_data não deve consultar o locale do sistema")

    monkeypatch.setattr(locale, "setlocale", fail_if_called)

    assert build_data(pd.Series(["21/03/2026"])).tolist() == ["março"]


def test_build_ano_returns_nullable_integer_for_valid_and_null_dates() -> None:
    result = build_ano(pd.Series(["21/07/2026", None, "data inválida"]))

    assert result.dtype == "Int64"
    assert result.iloc[0] == 2026
    assert pd.isna(result.iloc[1])
    assert pd.isna(result.iloc[2])


def test_build_ano_ignores_time_and_preserves_index() -> None:
    source = pd.Series(
        [pd.Timestamp("2025-12-31 23:59:59")],
        index=pd.Index([7], name="linha"),
    )

    result = build_ano(source)

    assert result.tolist() == [2025]
    assert result.index.equals(source.index)


def test_build_data_and_ano_always_share_the_same_coverage() -> None:
    source = pd.Series(["21/07/2026", None, "inválida", "01/01/2025"])

    data = build_data(source)
    ano = build_ano(source)

    assert data.notna().tolist() == ano.notna().tolist()
    assert list(zip(data.dropna(), ano.dropna(), strict=True)) == [
        ("julho", 2026),
        ("janeiro", 2025),
    ]


@pytest.mark.parametrize("builder", [build_prazo, build_prazo2])
def test_build_prazo_classifies_delivery_against_forecast(
    builder: Callable[[pd.Series, pd.Series], pd.Series],
) -> None:
    result = builder(
        pd.Series(["20/07/2026", "21/07/2026", "22/07/2026"]),
        pd.Series(["21/07/2026", "21/07/2026", "21/07/2026"]),
    )

    assert result.tolist() == [
        "ENTREGUE NO PRAZO",
        "ENTREGUE NO PRAZO",
        "ENTREGUE COM ATRASO",
    ]
    assert result.dtype == "object"


@pytest.mark.parametrize("builder", [build_prazo, build_prazo2])
def test_build_prazo_handles_null_empty_and_invalid_delivery(
    builder: Callable[[pd.Series, pd.Series], pd.Series],
) -> None:
    result = builder(
        pd.Series([None, "", "   ", "texto inválido"]),
        pd.Series(["21/07/2026"] * 4),
    )

    assert result.tolist() == ["SEM INFORMAÇÃO DE ENTREGA"] * 4


@pytest.mark.parametrize("builder", [build_prazo, build_prazo2])
def test_build_prazo_reports_missing_forecast_without_inventing_deadline_result(
    builder: Callable[[pd.Series, pd.Series], pd.Series],
) -> None:
    result = builder(
        pd.Series(["21/07/2026", "21/07/2026", "21/07/2026"]),
        pd.Series([None, "   ", "PREVISÃO INVÁLIDA"]),
    )

    assert result.tolist() == ["SEM INFORMAÇÃO DE PREVISÃO"] * 3


def test_build_prazo_prioritizes_return_flag_over_all_date_conditions() -> None:
    result = build_prazo(
        pd.Series([None, "21/07/2026", "23/07/2026"]),
        pd.Series([None, None, "22/07/2026"]),
        pd.Series([True, True, True]),
    )

    assert result.tolist() == ["DEVOLVIDA", "DEVOLVIDA", "DEVOLVIDA"]


@pytest.mark.parametrize("builder", [build_prazo, build_prazo2])
def test_build_prazo_ignores_time_and_accepts_spaced_date_text(
    builder: Callable[[pd.Series, pd.Series], pd.Series],
) -> None:
    result = builder(
        pd.Series([" 21/07/2026 ", pd.Timestamp("2026-07-21 23:59:59")]),
        pd.Series(["21/07/2026", pd.Timestamp("2026-07-21 00:00:00")]),
    )

    assert result.tolist() == ["ENTREGUE NO PRAZO", "ENTREGUE NO PRAZO"]


def test_build_prazo_functions_preserve_index_and_are_consistent() -> None:
    delivery = pd.Series(
        ["21/07/2026", None, "23/07/2026"],
        index=pd.Index([8, 3, 5], name="linha"),
    )
    forecast = pd.Series(
        ["22/07/2026", "22/07/2026", "22/07/2026"],
        index=delivery.index,
    )

    prazo = build_prazo(delivery, forecast)
    prazo2 = build_prazo2(delivery, forecast)

    assert prazo.index.equals(delivery.index)
    assert prazo2.index.equals(delivery.index)
    assert prazo.tolist() == prazo2.tolist()


def test_transformer_builds_both_deadline_status_columns() -> None:
    source = pd.concat([source_frame()] * 3, ignore_index=True)
    source["Entrega"] = ["28/07/2026", "29/07/2026", "30/07/2026"]

    result = transform_dataframe(source)

    assert result["Prazo"].tolist() == [
        "ENTREGUE NO PRAZO",
        "ENTREGUE NO PRAZO",
        "ENTREGUE COM ATRASO",
    ]
    assert result["Prazo2"].tolist() == result["Prazo"].tolist()


def test_reusable_normalizers() -> None:
    assert trim_text("  teste  ") == "teste"
    assert trim_text("  ") is None
    numbers = safe_number_series(pd.Series(["1.234,56", "1234.56", "inválido"]))
    assert numbers.iloc[0] == pytest.approx(1234.56)
    assert numbers.iloc[1] == pytest.approx(1234.56)
    assert pd.isna(numbers.iloc[2])


def test_missing_required_source_column_has_clear_error() -> None:
    frame = source_frame().drop(columns=["Transportador"])

    validation = validate_source_dataframe(frame)

    assert not validation.is_valid
    assert "Transportador" in validation.errors[0]
    with pytest.raises(TransformationValidationError, match="Transportador"):
        transform_dataframe(frame)


def test_output_validator_detects_wrong_order_and_duplicate_columns() -> None:
    valid = transform_dataframe(source_frame())
    wrong_order = valid.loc[:, list(reversed(OUTPUT_COLUMNS))]
    assert not validate_output_dataframe(wrong_order).is_valid

    duplicate = valid.copy()
    duplicate.columns = list(OUTPUT_COLUMNS[:-1]) + [OUTPUT_COLUMNS[-2]]
    validation = validate_output_dataframe(duplicate)
    assert not validation.is_valid
    assert any("duplicadas" in error for error in validation.errors)


def test_output_validator_detects_incompatible_text_type() -> None:
    frame = transform_dataframe(source_frame())
    frame["Destinatário"] = pd.Series([123], dtype="int64")

    validation = validate_output_dataframe(frame)

    assert not validation.is_valid
    assert any("compatível com texto" in error for error in validation.errors)

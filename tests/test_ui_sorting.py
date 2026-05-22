from __future__ import annotations

from pactuacalc.ui import sort_gru_codes, sort_ug_codes


def test_sort_ug_codes_usa_descricao_sem_trocar_codigo() -> None:
    codes = [
        {"ug": "200000", "gestao": "00001", "descricao": "Zeta"},
        {"ug": "100000", "gestao": "00001", "descricao": "Alfa"},
    ]

    sorted_codes = sort_ug_codes(codes)

    assert [item["descricao"] for item in sorted_codes] == ["Alfa", "Zeta"]
    assert [item["ug"] for item in sorted_codes] == ["100000", "200000"]


def test_sort_gru_codes_usa_numeracao_sem_trocar_descricao() -> None:
    codes = [
        {"codigo": "91710-9", "descricao": "Honorarios"},
        {"codigo": "10723-9", "descricao": "Operacoes PESA"},
        {"codigo": "13800-2", "descricao": "Diversos"},
    ]

    sorted_codes = sort_gru_codes(codes)

    assert [item["codigo"] for item in sorted_codes] == ["10723-9", "13800-2", "91710-9"]
    assert [item["descricao"] for item in sorted_codes] == ["Operacoes PESA", "Diversos", "Honorarios"]

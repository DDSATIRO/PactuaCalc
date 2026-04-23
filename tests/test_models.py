from __future__ import annotations

from datetime import date, timedelta

from geracordo.models import CaseData, Subdebito
from geracordo.parser import split_sections
from geracordo.services import consolidar_por_chave_arrecadatoria, distribuir_valor_bloqueado


def build_valid_case() -> CaseData:
    future_response = date.today() + timedelta(days=5)
    future_first = date.today() + timedelta(days=10)
    return CaseData(
        processo="0600097-06.2024.6.02.0014",
        devedor="MARCOS JOSE DIAS VIANA",
        cpf_cnpj="259.105.584-04",
        data_atualizacao=future_response.strftime("%d/%m/%Y"),
        tipo_parcela="Parcelamento comum",
        multa_percentual=10.0,
        data_limite_resposta=future_response.strftime("%d/%m/%Y"),
        data_primeira_parcela=future_first.strftime("%d/%m/%Y"),
        subdebitos=[
            Subdebito(
                tipo="principal",
                descricao="Principal",
                referencia_origem="0600097-06.2024.6.02.0014",
                valor_atualizado=1000.0,
                multa_art_523=100.0,
            )
        ],
    )


def test_case_validation_accepts_valid_data() -> None:
    case = build_valid_case()
    assert case.validate() == []


def test_case_validation_rejects_invalid_dates() -> None:
    case = build_valid_case()
    case.data_limite_resposta = (date.today() - timedelta(days=1)).strftime("%d/%m/%Y")
    errors = case.validate()
    assert any("Data limite para resposta" in item for item in errors)


def test_distribui_bloqueio_geral_proporcionalmente() -> None:
    case = build_valid_case()
    case.subdebitos.append(
        Subdebito(
            tipo="principal",
            descricao="Segundo",
            referencia_origem="0600097-06.2024.6.02.0014",
            valor_atualizado=900.0,
            multa_art_523=0.0,
        )
    )
    case.valor_bloqueado_geral = 200.0
    distribuir_valor_bloqueado(case)
    assert round(case.subdebitos[0].valor_bloqueado + case.subdebitos[1].valor_bloqueado, 2) == 200.0
    assert case.subdebitos[0].valor_bloqueado > case.subdebitos[1].valor_bloqueado


def test_consolida_itens_com_mesma_chave_arrecadatoria() -> None:
    items = [
        Subdebito(
            tipo="principal",
            descricao="A",
            referencia_origem="1",
            valor_atualizado=100.0,
            multa_art_523=10.0,
            valor_bloqueado=5.0,
            ug="123456",
            gestao="00001",
            gru_cr="12345-6",
        ),
        Subdebito(
            tipo="principal",
            descricao="B",
            referencia_origem="2",
            valor_atualizado=50.0,
            multa_art_523=5.0,
            valor_bloqueado=2.0,
            ug="123456",
            gestao="00001",
            gru_cr="12345-6",
        ),
    ]
    consolidated = consolidar_por_chave_arrecadatoria(items)
    assert len(consolidated) == 1
    assert consolidated[0].valor_atualizado == 150.0
    assert consolidated[0].multa_art_523 == 15.0
    assert consolidated[0].valor_bloqueado == 7.0


def test_split_sections_tolera_acentuacao_nas_ancoras() -> None:
    parsed = split_sections("RESUMO DO CÁLCULO\nabc\nI - PARTES\nxyz")
    assert "RESUMO DO CALCULO" in parsed.sections
    assert "I - PARTES" in parsed.sections

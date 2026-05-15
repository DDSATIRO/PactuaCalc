from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from pactuacalc.models import CaseData, ProposalSelection, Subdebito
from pactuacalc.parser import (
    _parse_tcu_lancamentos,
    _extract_tcu_saldo_debito,
    _extract_tcu_saldo_total,
    competencia_from_date,
    detect_report_type,
    distribuir_multa_nos_subdebitos,
    extract_identifier,
    parse_tcu_report,
    parse_totalizacao_details,
)
from pactuacalc.projefweb import competencia_esta_defasada
from pactuacalc.proposals import build_proposal_scenarios, create_proposal_pdf
from pactuacalc.services import merge_case_data, replace_tcu_case_data


def build_valid_case() -> CaseData:
    future_response = date.today() + timedelta(days=5)
    future_first = date.today() + timedelta(days=10)
    return CaseData(
        identificador_projef="72575cb7",
        processo="0600097-06.2024.6.02.0014",
        devedor="MARCOS JOSE DIAS VIANA",
        cpf_cnpj="259.105.584-04",
        competencia_atualizacao="03/2026",
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


def test_parser_identifica_multa_e_valor_total() -> None:
    secao = (
        "SUBTOTAL DA CONTA (I) 38.223,90\n"
        "Multa 10% - art. 523, §1o, CPC/2015. 3.822,39\n"
        "Honorarios advocaticios 10% - art. 523, §1o, CPC/2015. 3.822,39"
    )
    percentual, total = parse_totalizacao_details(secao)
    assert percentual == 10.0
    assert total == 3822.39


def test_parser_identifica_identificador_no_rodape() -> None:
    texto = "Gere novamente este calculo usando o identificador 72575cb7 - Pagina 1 de 4"
    assert extract_identifier(texto) == "72575cb7"


def test_distribui_multa_proporcionalmente_nos_principais() -> None:
    itens = [
        Subdebito(tipo="principal", descricao="A", referencia_origem="1", valor_atualizado=100.0),
        Subdebito(tipo="principal", descricao="B", referencia_origem="2", valor_atualizado=300.0),
    ]
    distribuir_multa_nos_subdebitos(itens, 40.0, 10.0)
    assert itens[0].multa_art_523 == 10.0
    assert itens[1].multa_art_523 == 30.0


def test_competencia_defasada_detecta_mes_anterior() -> None:
    assert competencia_esta_defasada("03/2026") is True


def test_build_proposal_scenarios_retorna_modalidades() -> None:
    case = build_valid_case()
    case.subdebitos[0].valor_bloqueado = 100.0
    cenarios = build_proposal_scenarios(case)
    assert len(cenarios) == 8
    assert cenarios[0].codigo == "1"
    assert cenarios[-1].codigo == "4.D"
    vista = next(cenario for cenario in cenarios if cenario.codigo == "2")
    assert vista.desconto_percentual == 50.0
    assert vista.desconto_valor == 550.0
    assert vista.valor_final == 550.0


def test_build_proposal_scenarios_aplica_proposta_salva() -> None:
    case = build_valid_case()
    case.subdebitos[0].valor_bloqueado = 100.0
    selecoes = {
        "4.A": ProposalSelection(
            entrada_percentual=25.0,
            desconto_percentual=20.0,
            parcelas=10,
        )
    }
    cenario = build_proposal_scenarios(case, selected_codes={"4.A"}, proposal_selections=selecoes)[0]
    assert cenario.entrada_minima_percentual == 25.0
    assert cenario.desconto_percentual == 20.0
    assert cenario.parcelas == 10
    assert cenario.entrada_gru == 175.0
    assert cenario.desconto_valor == 220.0
    assert cenario.saldo_remanescente == 605.0
    assert cenario.valor_parcela == 60.5


def test_entrada_opcional_em_proposta_sem_desconto_nao_cria_desconto() -> None:
    case = build_valid_case()
    selecoes = {"1": ProposalSelection(entrada_percentual=10.0, desconto_percentual=0.0, parcelas=60)}

    cenario = build_proposal_scenarios(case, selected_codes={"1"}, proposal_selections=selecoes)[0]

    assert cenario.entrada_minima_percentual == 10.0
    assert cenario.entrada_gru == 110.0
    assert cenario.desconto_percentual == 0.0
    assert cenario.desconto_valor == 0.0


def test_desconto_vista_define_faixa_pelos_principais_e_aplica_ao_total() -> None:
    case = build_valid_case()
    case.subdebitos = [
        Subdebito(
            tipo="PRINCIPAL",
            descricao="Principal",
            referencia_origem="1",
            valor_atualizado=80000.0,
        ),
        Subdebito(
            tipo="HONORÁRIOS",
            descricao="Honorarios",
            referencia_origem="2",
            valor_atualizado=20000.0,
        ),
    ]

    vista = build_proposal_scenarios(case, selected_codes={"2"})[0]

    assert vista.desconto_percentual == 30.0
    assert vista.desconto_valor == 30000.0


def test_desconto_vista_progressivo_usa_percentual_efetivo_da_base_sem_honorarios() -> None:
    case = build_valid_case()
    case.proposal_rules.calculo_vista = "progressivo"
    case.subdebitos = [
        Subdebito(
            tipo="PRINCIPAL",
            descricao="Principal",
            referencia_origem="1",
            valor_atualizado=150000.0,
        ),
        Subdebito(
            tipo="HONORÁRIOS",
            descricao="Honorarios",
            referencia_origem="2",
            valor_atualizado=50000.0,
        ),
    ]

    vista = build_proposal_scenarios(case, selected_codes={"2"})[0]

    assert vista.desconto_percentual == 32.33
    assert vista.desconto_valor == 64660.0


def test_desconto_vista_usa_total_quando_so_ha_honorarios() -> None:
    case = build_valid_case()
    case.subdebitos = [
        Subdebito(
            tipo="HONORÁRIOS",
            descricao="Honorarios",
            referencia_origem="1",
            valor_atualizado=80000.0,
        )
    ]

    vista = build_proposal_scenarios(case, selected_codes={"2"})[0]

    assert vista.desconto_percentual == 30.0
    assert vista.desconto_valor == 24000.0


def test_case_data_carrega_json_sem_propostas_selecionadas() -> None:
    case = CaseData.from_dict({"processo": "0000000-00.2026.0.00.0000"})
    assert case.propostas_selecionadas == {}


def test_create_proposal_pdf_gera_arquivo() -> None:
    case = build_valid_case()
    output_dir = Path("C:/Projetos/pactuacalc")
    output = output_dir / "teste_proposta_saida.pdf"
    pdf_path = create_proposal_pdf(case, output)
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0


def test_parser_tcu_identifica_lancamentos_do_historico() -> None:
    historico = (
        "14/05/1998 D R$ 8.910,00\n"
        "10/08/1998 D R$ 8.910,00\n"
        "22/12/1999 C R$ 5.940,00\n"
    )
    lancamentos = _parse_tcu_lancamentos(historico)
    assert len(lancamentos) == 3
    assert lancamentos[0].tipo_dc == "D"
    assert lancamentos[2].tipo_dc == "C"
    assert lancamentos[2].valor == 5940.0


def test_parser_tcu_identifica_saldo_do_debito_no_resumo() -> None:
    resumo = (
        "Saldo do débito (incluindo variação da SELIC) em 18/12/2019 R$ 343.285,71\n"
        "Saldo dos juros em 18/12/2019 + R$ 421.627,94\n"
        "Saldo total em 18/12/2019 + R$ 764.913,65\n"
    )
    assert _extract_tcu_saldo_debito(resumo) == 343285.71


def test_parser_tcu_identifica_saldo_total_no_resumo() -> None:
    resumo = (
        "Saldo do dÃ©bito (incluindo variaÃ§Ã£o da SELIC) em 18/12/2019 R$ 343.285,71\n"
        "Saldo dos juros em 18/12/2019 + R$ 421.627,94\n"
        "Saldo total em 18/12/2019 + R$ 764.913,65\n"
    )
    assert _extract_tcu_saldo_total(resumo) == 764913.65


def test_merge_case_data_acumula_relatorios_e_aponta_divergencias() -> None:
    base = build_valid_case()
    base.relatorios_anexados = ["a.pdf"]
    incoming = CaseData(
        processo="0600097-06.2024.6.02.0014",
        devedor="OUTRO NOME",
        cpf_cnpj="259.105.584-04",
        sistema_origem="tcu",
        relatorios_anexados=["b.pdf"],
    )
    merged, conflicts = merge_case_data(base, incoming)
    assert merged.sistema_origem == "misto"
    assert merged.relatorios_anexados == ["a.pdf", "b.pdf"]
    assert any(conflict.field_name == "devedor" for conflict in conflicts)


def test_replace_tcu_case_data_substitui_valor_e_preserva_campos_manuais() -> None:
    base = CaseData(
        sistema_origem="tcu",
        origem_relatorio="anterior.pdf",
        subdebitos=[
            Subdebito(
                tipo="principal",
                descricao="Debito TCU anterior",
                referencia_origem="Origem anterior",
                valor_atualizado=100.0,
                valor_bloqueado=25.0,
                ug="170001",
                gestao="00001",
                gru_cr="18888-1",
            )
        ],
        relatorios_anexados=["anterior.pdf"],
    )
    incoming = CaseData(
        sistema_origem="tcu",
        origem_relatorio="atualizado.pdf",
        devedor="JORGE",
        incluir_juros_tcu=True,
        lancamentos_tcu=[],
        relatorios_anexados=["atualizado.pdf"],
        subdebitos=[
            Subdebito(
                tipo="principal",
                descricao="Debito TCU atualizado",
                referencia_origem="Origem atualizada",
                valor_atualizado=500.0,
            )
        ],
    )

    merged, conflicts = replace_tcu_case_data(base, incoming)

    assert not conflicts
    assert len(merged.subdebitos) == 1
    assert merged.subdebitos[0].valor_atualizado == 500.0
    assert merged.subdebitos[0].descricao == "Debito TCU atualizado"
    assert merged.subdebitos[0].valor_bloqueado == 25.0
    assert merged.subdebitos[0].ug == "170001"
    assert merged.subdebitos[0].gru_cr == "18888-1"
    assert merged.relatorios_anexados == ["anterior.pdf", "atualizado.pdf"]


def test_detect_report_type_reconhece_variacao_tcu_por_ancoras() -> None:
    pdf_path = Path("C:/Projetos/pactuacalc/teste_tcu_variacao_detector.pdf")
    pdf_path.write_bytes(b"%PDF-1.4 placeholder")

    import pactuacalc.parser as parser_module

    original = parser_module.extract_text_from_pdf
    parser_module.extract_text_from_pdf = lambda _path: (
        "DEMONSTRATIVO DE DÉBITO\n"
        "Responsável (eis): JORGE ROBERTO GARZIERA\n"
        "Origem(ens) do débito: ACÓRDÃO TCU\n"
        "HISTÓRICO\n"
        "Saldo total em 16/04/2026 + R$ 1.090.555,26\n"
        "DETALHAMENTO DO CÁLCULO\n"
        "TCU-Plenário\n"
    )
    try:
        assert detect_report_type(pdf_path) == "tcu"
    finally:
        parser_module.extract_text_from_pdf = original


def test_parse_tcu_report_identifica_datas_embutidas_no_texto() -> None:
    import pactuacalc.parser as parser_module

    original = parser_module.extract_text_by_page
    parser_module.extract_text_by_page = lambda _path: [
        (
            "DEMONSTRATIVO DE DÉBITO\n"
            "Responsável (eis): JORGE ROBERTO GARZIERA\n"
            "Origem(ens) do débito: 0005025-66.2008.4.05.8300 (NUP 12345.123456/1234-12 - "
            "DATA LIMITE PARA RESPOSTA (20/04/2026) DATA DA PRIMEIRA PARCELA (30/04/2026)\n"
            "Período: 16/04/2000 a 16/04/2026\n"
            "HISTÓRICO RESUMO\n"
            "Data Evento D/C Valor\n"
            "16/04/2000 D R$ 100.000,00 Saldo do débito (incluindo variação da SELIC) em 16/04/2026 R$ 474.558,01\n"
            "Saldo dos juros em 16/04/2026 + R$ 615.997,25\n"
            "Saldo total em 16/04/2026 + R$ 1.090.555,26\n"
            "DETALHAMENTO DO CÁLCULO\n"
        )
    ]
    try:
        parsed = parse_tcu_report("dummy.pdf")
        assert parsed.data_limite_resposta == "20/04/2026"
        assert parsed.data_primeira_parcela == "30/04/2026"
        assert parsed.devedor == "JORGE ROBERTO GARZIERA"
    finally:
        parser_module.extract_text_by_page = original


def test_competencia_from_date_converte_data_em_mes_ano() -> None:
    assert competencia_from_date("16/04/2026") == "04/2026"


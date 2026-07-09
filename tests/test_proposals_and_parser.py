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
    parse_partes_section,
    parse_honorarios,
    parse_projef_report,
    parse_tcu_report,
    extract_totalizacao_section,
    parse_totalizacao_details,
)
from pactuacalc.projefweb import competencia_esta_defasada
import pactuacalc.proposals as proposals
from pactuacalc.proposal_render import PAGE_WIDTH, MARGIN_X, ProposalPdfLayout, SimplePdf
from pactuacalc.proposals import _scenario_title_modalidade, build_proposal_scenarios, create_proposal_pdf
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


def test_parser_recorta_totalizacao_com_quebra_de_pagina_antes_do_titulo() -> None:
    texto = (
        "I - PARTES\n"
        "DEBITO ELEITORAL 860.056,37\n"
        "\fII - TOTALIZAÇÃO\n"
        "SUBTOTAL DA CONTA (I) 860.056,37\n"
        "Multa 10% - art. 523, §1º, CPC/2015. 86.005,64\n"
        "Honorarios advocatícios 10% - art. 523, §1º, CPC/2015. 86.005,64\n"
        "TOTAL DA CONTA EM 05/2024 1.032.067,65"
    )

    secao = extract_totalizacao_section(texto)
    percentual, total = parse_totalizacao_details(secao)
    honorarios = parse_honorarios(secao)

    assert percentual == 10.0
    assert total == 86005.64
    assert honorarios is not None
    assert honorarios.valor_atualizado == 86005.64


def test_parser_identifica_identificador_no_rodape() -> None:
    texto = "Gere novamente este calculo usando o identificador 72575cb7 - Pagina 1 de 4"
    assert extract_identifier(texto) == "72575cb7"


def test_distribui_multa_proporcionalmente_nos_principais() -> None:
    itens = [
        Subdebito(tipo="PRINCIPAL", descricao="A", referencia_origem="1", valor_atualizado=100.0),
        Subdebito(tipo="PRINCIPAL", descricao="B", referencia_origem="2", valor_atualizado=300.0),
    ]
    distribuir_multa_nos_subdebitos(itens, 40.0, 10.0)
    assert itens[0].multa_art_523 == 10.0
    assert itens[1].multa_art_523 == 30.0


def test_distribui_multa_art_523_apenas_nos_debitos_principais() -> None:
    itens = [
        Subdebito(tipo="PRINCIPAL", descricao="Debito eleitoral", referencia_origem="1", valor_atualizado=59480.40),
        Subdebito(tipo="HONORÁRIOS", descricao="Honorarios", referencia_origem="2", valor_atualizado=5948.04),
    ]

    distribuir_multa_nos_subdebitos(itens, 5948.04, 10.0)

    assert itens[0].multa_art_523 == 5948.04
    assert itens[1].multa_art_523 == 0.0


def test_distribui_multa_art_523_inclui_honorarios_quando_subtotal_bate_com_todos() -> None:
    itens = [
        Subdebito(tipo="PRINCIPAL", descricao="Principal", referencia_origem="1", valor_atualizado=500.0),
        Subdebito(tipo="HONORÁRIOS", descricao="Honorarios iniciais", referencia_origem="2", valor_atualizado=500.0),
    ]

    distribuir_multa_nos_subdebitos(itens, 100.0, 10.0, subtotal_base=1000.0)

    assert itens[0].multa_art_523 == 50.0
    assert itens[1].multa_art_523 == 50.0


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
    assert cenario.adaptada is True


def test_entrada_opcional_em_proposta_sem_desconto_nao_cria_desconto() -> None:
    case = build_valid_case()
    selecoes = {"1": ProposalSelection(entrada_percentual=10.0, desconto_percentual=0.0, parcelas=60)}

    cenario = build_proposal_scenarios(case, selected_codes={"1"}, proposal_selections=selecoes)[0]

    assert cenario.entrada_minima_percentual == 10.0
    assert cenario.entrada_gru == 110.0
    assert cenario.desconto_percentual == 0.0
    assert cenario.desconto_valor == 0.0
    assert cenario.adaptada is True


def test_proposta_sem_alteracao_nao_fica_adaptada() -> None:
    case = build_valid_case()

    cenario = build_proposal_scenarios(case, selected_codes={"3.A"})[0]

    assert cenario.adaptada is False


def test_data_primeira_parcela_com_entrada_alterada_nao_deixa_proposta_adaptada() -> None:
    case = build_valid_case()
    case.data_primeira_parcela_com_entrada = case.data_primeira_parcela
    selecoes = {"4.A": ProposalSelection(entrada_percentual=20.0, desconto_percentual=25.0, parcelas=12)}

    cenario = build_proposal_scenarios(case, selected_codes={"4.A"}, proposal_selections=selecoes)[0]

    assert cenario.adaptada is False


def test_titulo_da_opcao_sem_entrada_muda_quando_entrada_opcional_e_informada() -> None:
    case = build_valid_case()
    selecoes = {"3.A": ProposalSelection(entrada_percentual=10.0, desconto_percentual=20.0, parcelas=12)}

    cenario = build_proposal_scenarios(case, selected_codes={"3.A"}, proposal_selections=selecoes)[0]

    assert _scenario_title_modalidade(cenario) == "PARCELADO COM ENTRADA"


def test_parcela_prefixada_usa_mes_da_primeira_parcela_sem_entrada(monkeypatch) -> None:
    monkeypatch.setattr(proposals, "get_mean_selic_12_months", lambda _data: 1.0)
    case = build_valid_case()
    case.tipo_parcela = "FIXO (PREFIXADO)"
    case.data_atualizacao = "15/05/2026"
    case.data_primeira_parcela = "01/06/2026"
    case.subdebitos = [Subdebito(tipo="PRINCIPAL", descricao="Principal", referencia_origem="1", valor_atualizado=12000.0)]

    cenario = build_proposal_scenarios(case, selected_codes={"3.A"})[0]

    assert cenario.valor_parcela == 852.0


def test_parcela_prefixada_nao_aplica_selic_quando_primeira_parcela_no_mes_atual(monkeypatch) -> None:
    monkeypatch.setattr(proposals, "get_mean_selic_12_months", lambda _data: 1.0)
    case = build_valid_case()
    case.tipo_parcela = "FIXO (PREFIXADO)"
    case.data_atualizacao = "15/05/2026"
    case.data_primeira_parcela = "31/05/2026"
    case.data_primeira_parcela_com_entrada = "31/05/2026"
    case.subdebitos = [Subdebito(tipo="PRINCIPAL", descricao="Principal", referencia_origem="1", valor_atualizado=12000.0)]

    cenario = build_proposal_scenarios(case, selected_codes={"4.A"})[0]

    assert cenario.valor_parcela == 580.25


def test_parcela_prefixada_com_entrada_usa_data_primeira_parcela_pos_entrada(monkeypatch) -> None:
    monkeypatch.setattr(proposals, "get_mean_selic_12_months", lambda _data: 1.0)
    case = build_valid_case()
    case.tipo_parcela = "FIXO (PREFIXADO)"
    case.data_atualizacao = "15/05/2026"
    case.data_primeira_parcela = "31/05/2026"
    case.data_primeira_parcela_com_entrada = "30/06/2026"
    case.subdebitos = [Subdebito(tipo="PRINCIPAL", descricao="Principal", referencia_origem="1", valor_atualizado=12000.0)]

    cenario = build_proposal_scenarios(case, selected_codes={"4.A"})[0]

    assert cenario.valor_parcela == 585.75


def test_parcela_prefixada_opcao_adaptada_usa_data_primeira_parcela(monkeypatch) -> None:
    monkeypatch.setattr(proposals, "get_mean_selic_12_months", lambda _data: 1.0)
    case = build_valid_case()
    case.tipo_parcela = "FIXO (PREFIXADO)"
    case.data_atualizacao = "15/05/2026"
    case.data_primeira_parcela = "01/06/2026"
    case.data_primeira_parcela_com_entrada = "01/07/2026"
    case.subdebitos = [Subdebito(tipo="PRINCIPAL", descricao="Principal", referencia_origem="1", valor_atualizado=12000.0)]
    selecoes = {"3.A": ProposalSelection(entrada_percentual=10.0, desconto_percentual=20.0, parcelas=10)}

    cenario = build_proposal_scenarios(case, selected_codes={"3.A"}, proposal_selections=selecoes)[0]

    assert cenario.valor_parcela == 894.6


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


def test_desconto_vista_identifica_honorarios_por_codigo_arrecadatorio() -> None:
    case = build_valid_case()
    case.subdebitos = [
        Subdebito(
            tipo="PRINCIPAL",
            descricao="Principal",
            referencia_origem="1",
            valor_atualizado=80000.0,
        ),
        Subdebito(
            tipo="PRINCIPAL",
            descricao="Outra rubrica",
            referencia_origem="2",
            valor_atualizado=20000.0,
            ug="110060",
            gru_cr="91710-9",
        ),
    ]

    vista = build_proposal_scenarios(case, selected_codes={"2"})[0]

    assert vista.desconto_percentual == 30.0
    assert vista.desconto_valor == 30000.0


def test_parser_honorarios_usa_gru_correto() -> None:
    item = parse_honorarios("Honorarios advocaticios R$ 1.234,56")

    assert item is not None
    assert item.gru_cr == "91710-9"


def test_parser_honorarios_ignora_percentual_sem_valor_monetario() -> None:
    item = parse_honorarios("Hon. adv. fixados sobre valor da causa - 7.533.810,11 x 7,00%")

    assert item is None


def test_parser_partes_ignora_percentual_e_usa_total_da_linha() -> None:
    itens = parse_partes_section(
        "Hon. adv. fixados sobre valor da causa - 7.533.810,11 x 7,00% 670.347,91 195.272,35 865.620,26",
        "0805095-78.2016.4.05.8200",
    )

    assert len(itens) == 1
    assert itens[0].valor_atualizado == 865620.26
    assert itens[0].descricao == "Hon. adv. fixados sobre valor da causa - 7.533.810,11 x 7,00%"


def test_parser_partes_ignora_linha_so_com_valor_e_percentual_na_descricao() -> None:
    itens = parse_partes_section(
        "Hon. adv. fixados sobre valor da causa - 7.533.810,11 x 7,00%",
        "0805095-78.2016.4.05.8200",
        force_tipo="HONORÁRIOS",
    )

    assert itens == []


def test_parser_partes_ignora_linha_so_com_valor_e_percentual_sem_simbolo() -> None:
    itens = parse_partes_section(
        "Hon. adv. fixados sobre valor da causa - 7.533.810,11 x 7,00",
        "0805095-78.2016.4.05.8200",
        force_tipo="HONORÁRIOS",
    )

    assert itens == []


def test_parser_sucumbencias_forca_honorarios_e_usa_total_da_linha() -> None:
    itens = parse_partes_section(
        "Hon. adv. fixados sobre valor da causa - 7.533.810,11 x 7,00% 670.347,91 195.272,35 865.620,26",
        "0805095-78.2016.4.05.8200",
        force_tipo="HONORÁRIOS",
    )

    assert len(itens) == 1
    assert itens[0].is_honorarios()
    assert itens[0].valor_atualizado == 865620.26
    assert itens[0].ug == "110060"
    assert itens[0].gru_cr == "91710-9"


def test_parse_projef_sucumbencias_com_multa_e_honorarios_da_totalizacao() -> None:
    import pactuacalc.parser as parser_module

    original = parser_module.extract_text_from_pdf
    parser_module.extract_text_from_pdf = lambda _path: (
        "RESUMO DO CÁLCULO\n"
        "Processo: 0805095-78.2016.4.05.8200\n"
        "I - SUCUMBÊNCIAS\n"
        "Descrição Principal corrigido Juros/Selic Total (R$)\n"
        "Hon. adv. fixados sobre valor da causa - 7.533.810,11 x 7,00% 670.347,91 189.708,46 860.056,37\n"
        "Total de Sucumbências -> 860.056,37\n"
        "II - TOTALIZAÇÃO\n"
        "Descrição Total (R$)\n"
        "SUBTOTAL DA CONTA (I) 860.056,37\n"
        "Multa 10% - art. 523, §1º, CPC/2015 (antigo art. 475-J, CPC/1976). 86.005,64\n"
        "Honorarios advocatícios 10% - art. 523, §1º, CPC/2015. 86.005,64\n"
        "TOTAL DA CONTA EM 05/2024 1.032.067,65\n"
        "ATUALIZADO ATÉ MAIO/2024"
    )
    try:
        case = parse_projef_report(Path("relatorio_projef.pdf"))
    finally:
        parser_module.extract_text_from_pdf = original

    assert len(case.subdebitos) == 2
    assert case.subdebitos[0].is_honorarios()
    assert case.subdebitos[0].valor_atualizado == 860056.37
    assert case.subdebitos[0].multa_art_523 == 86005.64
    assert case.subdebitos[1].is_honorarios()
    assert case.subdebitos[1].valor_atualizado == 86005.64


def test_parse_projef_sucumbencias_sem_honorarios_na_totalizacao_nao_duplica_valor_da_causa() -> None:
    import pactuacalc.parser as parser_module

    original = parser_module.extract_text_from_pdf
    parser_module.extract_text_from_pdf = lambda _path: (
        "RESUMO DO CÁLCULO\n"
        "Processo: 0805095-78.2016.4.05.8200\n"
        "I - SUCUMBÊNCIAS\n"
        "Descrição Principal corrigido Juros/Selic Total (R$)\n"
        "Hon. adv. fixados sobre valor da causa - 7.533.810,11 x 7,00% 670.347,91 195.272,35 865.620,26\n"
        "Total de Sucumbências -> 865.620,26\n"
        "II - TOTALIZAÇÃO\n"
        "Descrição Total (R$)\n"
        "SUBTOTAL DA CONTA (I) 865.620,26\n"
        "TOTAL DA CONTA EM 06/2024 865.620,26"
    )
    try:
        case = parse_projef_report(Path("relatorio_projef.pdf"))
    finally:
        parser_module.extract_text_from_pdf = original

    assert len(case.subdebitos) == 1
    assert case.subdebitos[0].is_honorarios()
    assert case.subdebitos[0].descricao == "Hon. adv. fixados sobre valor da causa - 7.533.810,11 x 7,00%"
    assert case.subdebitos[0].valor_atualizado == 865620.26
    assert case.subdebitos[0].multa_art_523 == 0.0
    assert case.multa_percentual == 0.0


def test_parse_projef_separa_sucumbencias_e_ignora_valor_certo_descritivo() -> None:
    import pactuacalc.parser as parser_module

    original = parser_module.extract_text_from_pdf
    parser_module.extract_text_from_pdf = lambda _path: (
        "RESUMO DO CÁLCULO\n"
        "Processo: 0005732-27.2009.4.05.8000\n"
        "Réu: ESPÓLIO DE JOSÉ MAURÍCIO TENÓRIO (CPF 007.542.424-04)\n"
        "I - PARTES\n"
        "Nome Principal corrigido Juros Moratórios Selic Total (R$)\n"
        "RESSARCIMENTO ERARIO 475.665,50 185.875,81 321.906,00 983.447,31\n"
        "Total Partes -> 475.665,50 185.875,81 321.906,00 983.447,31\n"
        "II - SUCUMBÊNCIAS\n"
        "Descrição Principal corrigido Juros/Selic Total (R$)\n"
        "Hon. adv. fixados sobre valor certo - 62.100,00 101.035,05 107.856,81 208.891,86\n"
        "Total de Sucumbências -> 208.891,86\n"
        "III - TOTALIZAÇÃO\n"
        "Descrição Total (R$)\n"
        "SUBTOTAL DA CONTA (I + II) 1.192.339,17\n"
        "TOTAL DA CONTA EM 01/2026 1.192.339,17\n"
        "ATUALIZADO ATÉ JANEIRO/2026\n"
        "Critérios e parâmetros do cálculo\n"
        "Honorários advocatícios (fixados sobre valor certo). Valor Certo: 62.100,00. "
        "Data da Fixação: 09/2013. Data de Início de Juros sobre os Honorários: 09/2013.\n"
        "DEMONSTRATIVO DE PARCELAS\n"
    )
    try:
        case = parse_projef_report(Path("relatorio_projef.pdf"))
    finally:
        parser_module.extract_text_from_pdf = original

    assert len(case.subdebitos) == 2
    assert case.devedor == "ESPÓLIO DE JOSÉ MAURÍCIO TENÓRIO"
    assert case.subdebitos[0].tipo == "PRINCIPAL"
    assert case.subdebitos[0].descricao == "RESSARCIMENTO ERARIO"
    assert case.subdebitos[0].valor_atualizado == 983447.31
    assert case.subdebitos[1].is_honorarios()
    assert case.subdebitos[1].descricao == "Hon. adv. fixados sobre valor certo - 62.100,00"
    assert case.subdebitos[1].valor_atualizado == 208891.86


def test_parse_projef_nao_cria_honorarios_com_base_de_calculo_dos_criterios() -> None:
    import pactuacalc.parser as parser_module

    original = parser_module.extract_text_from_pdf
    parser_module.extract_text_from_pdf = lambda _path: (
        "RESUMO DO CALCULO\n"
        "Processo: 0802410-17.2024.4.05.8201\n"
        "I - PARTES\n"
        "Nome Principal corrigido Juros Moratorios Selic Total (R$)\n"
        "Restituicao - Energia Eletrica - TRE-PB 29.081,31 0,00 22.905,73 51.987,04\n"
        "Total Partes -> 29.081,31 0,00 22.905,73 51.987,04\n"
        "II - SUCUMBENCIAS\n"
        "Descricao Principal corrigido Juros/Selic Total (R$)\n"
        "Hon. adv. fixados sobre valor da condenacao - 51.987,04 x 10,00% 2.908,13 2.290,57 5.198,70\n"
        "Total de Sucumbencias -> 5.198,70\n"
        "III - TOTALIZACAO\n"
        "Descricao Total (R$)\n"
        "SUBTOTAL DA CONTA (I + II) 57.185,74\n"
        "TOTAL DA CONTA EM 06/2026 57.185,74\n"
        "ATUALIZADO ATE JUNHO/2026\n"
        "Criterios e parametros do calculo\n"
        "Honorarios advocaticios (fixados sobre o valor da condenacao) Percentual 10,00%. "
        "Base de calculo dos honorarios de sucumbencia: R$ 51.987,04.\n"
    )
    try:
        case = parse_projef_report(Path("relatorio_projef.pdf"))
    finally:
        parser_module.extract_text_from_pdf = original

    assert len(case.subdebitos) == 2
    assert case.subdebitos[0].tipo == "PRINCIPAL"
    assert case.subdebitos[0].valor_atualizado == 51987.04
    assert case.subdebitos[1].is_honorarios()
    assert case.subdebitos[1].valor_atualizado == 5198.70


def test_parser_honorarios_ignora_base_de_calculo_textual() -> None:
    item = parse_honorarios(
        "Honorarios advocaticios (fixados sobre o valor da condenacao) Percentual 10,00%. "
        "Base de calculo dos honorarios de sucumbencia: R$ 51.987,04."
    )

    assert item is None


def test_parse_projef_partes_pode_ter_honorarios_na_base_da_multa() -> None:
    import pactuacalc.parser as parser_module

    original = parser_module.extract_text_from_pdf
    parser_module.extract_text_from_pdf = lambda _path: (
        "RESUMO DO CÁLCULO\n"
        "Processo: 0805095-78.2016.4.05.8200\n"
        "I - PARTES\n"
        "Descrição Principal corrigido Juros/Selic Total (R$)\n"
        "Débito eleitoral 500,00 0,00 500,00\n"
        "Honorarios advocatícios iniciais 500,00 0,00 500,00\n"
        "Total Partes -> 1.000,00\n"
        "II - TOTALIZAÇÃO\n"
        "SUBTOTAL DA CONTA (I) 1.000,00\n"
        "Multa 10% - art. 523, §1º, CPC/2015. 100,00\n"
        "Honorarios advocatícios 10% - art. 523, §1º, CPC/2015. 100,00"
    )
    try:
        case = parse_projef_report(Path("relatorio_projef.pdf"))
    finally:
        parser_module.extract_text_from_pdf = original

    assert len(case.subdebitos) == 3
    assert case.subdebitos[0].tipo == "PRINCIPAL"
    assert case.subdebitos[0].multa_art_523 == 50.0
    assert case.subdebitos[1].is_honorarios()
    assert case.subdebitos[1].multa_art_523 == 50.0
    assert case.subdebitos[2].is_honorarios()
    assert case.subdebitos[2].valor_atualizado == 100.0


def test_parser_nao_classifica_honorarios_em_contexto_negativo() -> None:
    item = parse_honorarios("Principal sem honorarios advocaticios R$ 1.234,56")

    assert item is None


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


def test_create_proposal_pdf_informa_bloqueio_no_parcela_pgu() -> None:
    case = build_valid_case()
    case.subdebitos[0].valor_bloqueado = 100.0
    output_dir = Path("C:/Projetos/pactuacalc")

    pdf_path = create_proposal_pdf(case, output_dir / "teste_proposta_bloqueio.pdf")

    assert b"Valores bloqueados devem ser assinalados no Parcela PGU" in pdf_path.read_bytes()


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


def test_parse_projef_competencia_usa_atualizado_ate_em_vez_da_data_de_geracao() -> None:
    import pactuacalc.parser as parser_module

    original = parser_module.extract_text_from_pdf
    parser_module.extract_text_from_pdf = lambda _path: (
        "RESUMO DO CALCULO\n"
        "Processo: 0600085-20.2024.6.15.0017\n"
        "I - PARTES\n"
        "Nome Principal corrigido Juros Moratorios Selic Total (R$)\n"
        "MULTA ELEITORAL 20.000,00 0,00 4.530,00 24.530,00\n"
        "II - TOTALIZACAO\n"
        "Descricao Total (R$)\n"
        "TOTAL DA CONTA EM 06/2026 29.436,00\n"
        "ATUALIZADO ATE JUNHO/2026\n"
        "9 de julho de 2026\n"
    )
    try:
        case = parse_projef_report(Path("relatorio_projef.pdf"))
    finally:
        parser_module.extract_text_from_pdf = original

    assert case.data_atualizacao == "09/07/2026"
    assert case.competencia_atualizacao == "06/2026"
    assert competencia_esta_defasada(case.competencia_atualizacao) is True


def test_condicoes_adicionais_longas_sao_quebradas_na_largura_util_do_pdf(tmp_path) -> None:
    layout = ProposalPdfLayout(SimplePdf())
    texto = (
        "Condicoes adicionais: SERA CONSIDERADO PROCESSO PRINCIPAL O DE N. 06000852020246150017, "
        "NO QUAL SERAO RECOLHIDAS TODAS AS PARCELAS ATE A QUITACAO INTEGRAL DA DIVIDA, "
        "NA HIPOTESE DE INADIMPLEMENTO DO ACORDO, SERAO ABATIDAS AS PARCELAS DO VALOR EXECUTADO "
        "NO PROCESSO 06003176120246150072 E NOS PROCESSOS RELACIONADOS."
    )
    largura_util = PAGE_WIDTH - (MARGIN_X * 2)
    linhas = layout.wrap(texto, largura_util, 10)

    assert len(linhas) >= 3
    assert all(layout.estimate_width(linha, 10) <= largura_util for linha in linhas)

    case = build_valid_case()
    case.condicoes_adicionais = texto
    output = tmp_path / "proposta_condicoes_longas.pdf"

    pdf_path = create_proposal_pdf(case, output)

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0


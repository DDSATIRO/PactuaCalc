from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from pactuacalc.formatting import format_currency_br, format_percent_br
from pactuacalc.models import CaseData, ProposalSelection, Subdebito, normalized_text, parse_iso_date
from pactuacalc.proposal_render import ProposalPdfLayout, SimplePdf
from pactuacalc.services import consolidar_por_chave_arrecadatoria, total_bloqueado_efetivo
from pactuacalc.selic_api import get_mean_selic_12_months
import calendar
from datetime import datetime, date

def add_months(sourcedate: date, months: int) -> date:
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _default_first_installment_after_entry(data_primeira_parcela: str) -> str:
    data_entrada_obj = parse_iso_date(data_primeira_parcela)
    if not data_entrada_obj:
        return "-"
    next_month_day = add_months(data_entrada_obj, 1)
    last_day = calendar.monthrange(next_month_day.year, next_month_day.month)[1]
    return f"{last_day:02d}/{next_month_day.month:02d}/{next_month_day.year}"


@dataclass
class ProposalRow:
    descricao: str
    ug_gestao: str
    gru_cr: str
    valor_total: float
    valor_bloqueado: float
    entrada_gru: float
    desconto: float
    saldo: float
    parcela: float


@dataclass
class ProposalScenario:
    codigo: str
    modalidade: str
    parcelas: int
    desconto_percentual: float
    desconto_valor: float
    entrada_minima_percentual: float
    entrada_gru: float
    saldo_remanescente: float
    valor_parcela: float
    valor_final: float
    observacao: str = ""
    nota_calculo_selic: str = ""
    rows: list[ProposalRow] | None = None
    adaptada: bool = False


MODALIDADES = [
    {"codigo": "1", "modalidade": "Parcelamento comum", "parcelas": 60, "desconto": 0.0, "entrada_minima": 0.0},
    {"codigo": "2", "modalidade": "Pagamento a vista", "parcelas": 1, "desconto": 0.0, "entrada_minima": 0.0},
    {"codigo": "3.A", "modalidade": "Parcelado sem entrada", "parcelas": 12, "desconto": 0.20, "entrada_minima": 0.0},
    {"codigo": "3.B", "modalidade": "Parcelado sem entrada", "parcelas": 24, "desconto": 0.15, "entrada_minima": 0.0},
    {"codigo": "4.A", "modalidade": "Com entrada", "parcelas": 12, "desconto": 0.25, "entrada_minima": 0.20},
    {"codigo": "4.B", "modalidade": "Com entrada", "parcelas": 24, "desconto": 0.20, "entrada_minima": 0.20},
    {"codigo": "4.C", "modalidade": "Com entrada", "parcelas": 36, "desconto": 0.10, "entrada_minima": 0.20},
    {"codigo": "4.D", "modalidade": "Com entrada", "parcelas": 60, "desconto": 0.05, "entrada_minima": 0.20},
]

DEFAULT_PARCELAS_BY_CODE = {item["codigo"]: item["parcelas"] for item in MODALIDADES}
OPTIONAL_ENTRY_CODES = {"1", "3.A", "3.B"}

PARCELA_LIMITES = {
    "1": (1, 60),
    "2": (1, 1),
    "3.A": (2, 12),
    "3.B": (13, 24),
    "4.A": (2, 12),
    "4.B": (13, 24),
    "4.C": (25, 36),
    "4.D": (37, 60),
}


CONDICOES_GERAIS = (
    "CONDIÇÕES GERAIS: a) o devedor deverá reconhecer a dívida objeto da ação e renunciar aos direitos sobre os quais se fundam eventuais "
    "ou futuros embargos à execução ou quaisquer outros meios de impugnação da referida dívida; b) o DESCONTO está CONDICIONADO à assinatura "
    "do termo de acordo a ser remetido ao devedor, com todas as condições do acordo; c) havendo bens sob constrições judiciais, como penhoras "
    "e bloqueios, estas serão mantidas até a confirmação da quitação integral da dívida (à vista ou parcelada); d) independentemente de cumprimento "
    "ou não da entrada ou da primeira parcela, uma vez assinado, o termo obrigará o devedor ao pagamento do valor até a data do vencimento respectivo, "
    "sob pena de aplicação da MULTA por descumprimento indicada na proposta; e) o termo não ensejará novação de dívida; f) a rescisão ou o descumprimento "
    "do termo de acordo ensejará a perda de todo o desconto concedido, quando houver, independentemente do valor recolhido ou do saldo residual da dívida, "
    "de modo que a dívida será restabelecida e os valores pagos serão abatidos de sua integralidade; g) As prestações serão ATUALIZADAS mediante o acréscimo "
    "de juros equivalentes à taxa SELIC, acumulada mensalmente, calculados a partir do mês subsequente ao da consolidação até o mês anterior ao do pagamento e "
    "de 1% (um por cento) relativamente ao mês em que o pagamento estiver sendo efetuado (Art. 2º, §3º, da Lei 9.469/97). No caso de parcelamento FIXO, a parcela "
    "será prefixada com base na média da SELIC dos últimos doze meses, conforme explicitação anterior."
)


OBSERVACOES_PROPOSTA = (
    "OBSERVAÇÕES: A presente proposta foi elaborada com base nos cálculos de atualização da dívida, conforme demonstrativos em anexo, e não vincula a UNIÃO "
    "em razão de eventual erro material na referida conta, assim como de preenchimento ou de eventual equívoco na indicação dos valores apontados neste resumo "
    "de proposta, sendo possível a sua correção a qualquer tempo. Em caso de dúvidas, o devedor deverá entrar em contato com pru5.corat-acordos@agu.gov.br, "
    "para onde deve também ser enviada a sua opção de escolha até a DATA LIMITE PARA RESPOSTA (ver quadro inicial)."
)


ATENCAO_PROPOSTA = (
    "ATENÇÃO: Os valores das parcelas constantes das opções na modalidade variável devem ser atualizados mensalmente. "
    "E, quando se trate de modalidade de parcelamento FIXO (parcela pré-fixada), os valores dessas parcelas serão RECALCULADOS no SISTEMA PARCELA PGU, "
    "com base na SELIC MÉDIA MENSAL dos últimos doze meses e podem apresentar pequenas diferenças no TERMO DE PARCELAMENTO a ser enviado ao devedor."
)

COLOR_INK = (0.08, 0.12, 0.18)
COLOR_NAVY = (0.07, 0.18, 0.31)
COLOR_SECTION_FILL = (0.94, 0.95, 0.96)
COLOR_PANEL_FILL = (0.96, 0.97, 0.98)
COLOR_ALERT_FILL = (0.98, 0.95, 0.90)
COLOR_NOTE_TEXT = (0.36, 0.29, 0.18)
COLOR_RESULT_TEXT = COLOR_NAVY
COLOR_RED_TEXT = (0.70, 0.08, 0.08)
COLOR_TABLE_HEADER = (0.93, 0.94, 0.96)
COLOR_TABLE_ALT = (0.99, 0.99, 0.99)
COLOR_TABLE_TOTAL = (0.94, 0.95, 0.94)
COLOR_OPTION_FILL = COLOR_SECTION_FILL

SCENARIO_TABLE_WIDTHS = [170, 114, 90, 78, 86, 84, 84, 88]
SELIC_NOTE_SPACING = 8.0


def _round_distribution(values: list[float], total: float) -> list[float]:
    if not values:
        return []
    distributed = [round(value, 2) for value in values]
    diff = round(total - sum(distributed), 2)
    distributed[-1] = round(distributed[-1] + diff, 2)
    return distributed


def _is_honorarios_ou_encargos(item: Subdebito) -> bool:
    texto = f"{normalized_text(item.tipo)} {normalized_text(item.descricao)}"
    return item.is_honorarios() or "ENCARGO" in texto


def _base_para_faixa_vista(items: list[Subdebito]) -> float:
    base_items = [item for item in items if not _is_honorarios_ou_encargos(item)]
    if not base_items:
        base_items = items
    return round(sum(item.valor_total for item in base_items), 2)


def _taxa_vista_percentual_unico(base_vista: float, faixas: list[dict[str, float | None]]) -> float:
    for faixa in faixas:
        limite = faixa.get("limite")
        percentual = float(faixa.get("percentual", 0.0) or 0.0)
        if limite is None or base_vista <= float(limite):
            return percentual
    return float(faixas[-1].get("percentual", 0.0) or 0.0)


def _desconto_vista_progressivo(base_desconto: float, faixas: list[dict[str, float | None]]) -> float:
    desconto = 0.0
    previous_limit = 0.0
    remaining = base_desconto
    for faixa in faixas:
        limite = faixa.get("limite")
        percentual = float(faixa.get("percentual", 0.0) or 0.0) / 100.0
        if remaining <= 0:
            break
        if limite is None:
            tranche = remaining
        else:
            upper = float(limite)
            tranche = min(max(upper - previous_limit, 0.0), remaining)
            previous_limit = upper
        desconto += tranche * percentual
        remaining -= tranche
    return round(desconto, 2)


def _taxa_vista_progressiva(base_vista: float, faixas: list[dict[str, float | None]]) -> float:
    if base_vista <= 0:
        return 0.0
    desconto_base_faixa = _desconto_vista_progressivo(base_vista, faixas)
    return round((desconto_base_faixa / base_vista) * 100, 2)


def _build_discount_bases(
    consolidated: list[Subdebito],
    incluir_bloqueio_no_desconto: bool,
) -> list[float]:
    bases: list[float] = []
    for item in consolidated:
        base = item.valor_total if incluir_bloqueio_no_desconto else max(item.valor_total - item.valor_bloqueado, 0.0)
        bases.append(base)
    return bases


def _build_scenario_rows(
    consolidated: list[Subdebito],
    desconto_total: float,
    entrada_total: float,
    parcelas: int,
    incluir_bloqueio_no_desconto: bool,
    fator_ajuste_parcela: float = 1.0,
) -> list[ProposalRow]:
    total_divida = round(sum(item.valor_total for item in consolidated), 2)
    if total_divida <= 0:
        return []

    discount_bases = _build_discount_bases(consolidated, incluir_bloqueio_no_desconto)
    total_discount_base = round(sum(discount_bases), 2)
    desconto_shares = _round_distribution(
        [((base / total_discount_base) * desconto_total) if total_discount_base > 0 else 0.0 for base in discount_bases],
        desconto_total,
    )
    entrada_shares = _round_distribution(
        [(item.valor_total / total_divida) * entrada_total for item in consolidated],
        entrada_total,
    )

    rows: list[ProposalRow] = []
    for item, desconto_item, entrada_item in zip(consolidated, desconto_shares, entrada_shares):
        saldo = round(max(item.valor_total - item.valor_bloqueado - entrada_item - desconto_item, 0.0), 2)
        parcela = round((saldo / parcelas) * fator_ajuste_parcela, 2) if parcelas else 0.0
        rows.append(
            ProposalRow(
                descricao=item.descricao,
                ug_gestao=item.ug_gestao or "-",
                gru_cr=item.gru_cr or "-",
                valor_total=item.valor_total,
                valor_bloqueado=item.valor_bloqueado,
                entrada_gru=entrada_item,
                desconto=desconto_item,
                saldo=saldo,
                parcela=parcela,
            )
        )
    return rows


def _fixed_installment_adjustment(
    case_data: CaseData,
    parcelas: int,
    entrada_gru: float,
    valor_parcela_base_pura: float,
) -> tuple[float, float, str]:
    if parcelas <= 1 or case_data.tipo_parcela != "FIXO (PREFIXADO)" or valor_parcela_base_pura <= 0:
        return round(valor_parcela_base_pura, 2), 1.0, ""

    media_selic = get_mean_selic_12_months(case_data.data_atualizacao)
    multiplicador = _initial_selic_months(case_data, entrada_gru)
    valor_com_atraso = valor_parcela_base_pura * (1 + ((media_selic / 100) * multiplicador))
    meses_ultima_parcela = multiplicador + parcelas - 1
    indice_correcao = media_selic * meses_ultima_parcela
    valor_ultima_parcela = valor_parcela_base_pura * (1 + (indice_correcao / 100))
    valor_final_prefixado = (valor_com_atraso + valor_ultima_parcela) / 2
    fator_ajuste_parcela = valor_final_prefixado / valor_parcela_base_pura

    selic_formatada = f"{media_selic:.4f}".replace(".", ",") + "%"
    indice_formatado = f"{indice_correcao:.4f}".replace(".", ",") + "%"
    obs_prefixo = (
        f"PARCELA PRÉ-FIXADA. MÉDIA SELIC ÚLTIMOS DOZE MESES: {selic_formatada}.\n"
        f"Cálculo: Parcela inicial {format_currency_br(valor_com_atraso)}; "
        f"Índice correção última parcela ({parcelas}ª) {indice_formatado}; "
        f"Valor última parcela {format_currency_br(valor_ultima_parcela)}; "
        f"Parcela fixa (média) {format_currency_br(valor_final_prefixado)}.\n"
    )
    return round(valor_final_prefixado, 2), fator_ajuste_parcela, obs_prefixo


def _effective_first_installment_date(case_data: CaseData, entrada_gru: float) -> str:
    if entrada_gru > 0:
        return case_data.data_primeira_parcela_com_entrada or _default_first_installment_after_entry(
            case_data.data_primeira_parcela
        )
    return case_data.data_primeira_parcela


def _initial_selic_months(case_data: CaseData, entrada_gru: float) -> int:
    data_atual = parse_iso_date(case_data.data_atualizacao)
    data_primeira = parse_iso_date(_effective_first_installment_date(case_data, entrada_gru))
    if not data_atual or not data_primeira:
        return 0
    m_diff = (data_primeira.year - data_atual.year) * 12 + (data_primeira.month - data_atual.month)
    return max(m_diff, 0)


def parcela_limites(codigo: str) -> tuple[int, int]:
    return PARCELA_LIMITES.get(codigo, (1, 60))


def validate_proposal_selection(
    scenario: ProposalScenario,
    selection: ProposalSelection,
) -> list[str]:
    errors: list[str] = []
    min_parcelas, max_parcelas = parcela_limites(scenario.codigo)
    if selection.parcelas is not None:
        if selection.parcelas < min_parcelas or selection.parcelas > max_parcelas:
            errors.append(f"Parcelas de {scenario.codigo} devem ficar entre {min_parcelas} e {max_parcelas}.")
        if selection.parcelas > scenario.parcelas:
            errors.append(f"Parcelas de {scenario.codigo} nao podem aumentar acima de {scenario.parcelas}.")
    if selection.entrada_percentual is not None:
        if (
            scenario.entrada_minima_percentual <= 0
            and scenario.codigo not in OPTIONAL_ENTRY_CODES
            and selection.entrada_percentual > 0
        ):
            errors.append(f"Entrada nao se aplica a proposta {scenario.codigo}.")
        if selection.entrada_percentual < scenario.entrada_minima_percentual:
            errors.append(
                f"Entrada de {scenario.codigo} nao pode ser menor que {format_percent_br(scenario.entrada_minima_percentual)}."
            )
    if selection.desconto_percentual is not None:
        if selection.desconto_percentual > scenario.desconto_percentual:
            errors.append(
                f"Desconto de {scenario.codigo} nao pode ser maior que {format_percent_br(scenario.desconto_percentual)}."
            )
        if selection.desconto_percentual < 0:
            errors.append(f"Desconto de {scenario.codigo} nao pode ser negativo.")
    return errors


def _apply_selection_to_scenario(
    scenario: ProposalScenario,
    selection: ProposalSelection,
    consolidated: list[Subdebito],
    total_divida: float,
    total_bloqueado: float,
    desconto_base: float,
    case_data: CaseData,
) -> ProposalScenario:
    parcelas = selection.parcelas if selection.parcelas is not None else scenario.parcelas
    desconto_percentual = (
        selection.desconto_percentual
        if selection.desconto_percentual is not None
        else scenario.desconto_percentual
    )
    entrada_percentual = (
        selection.entrada_percentual
        if selection.entrada_percentual is not None
        else scenario.entrada_minima_percentual
    )
    adaptada = (
        parcelas != scenario.parcelas
        or abs(desconto_percentual - scenario.desconto_percentual) > 0.0001
        or abs(entrada_percentual - scenario.entrada_minima_percentual) > 0.0001
    )
    desconto_valor = round(desconto_base * (desconto_percentual / 100.0), 2)
    alvo_entrada = round(total_divida * (entrada_percentual / 100.0), 2)
    if entrada_percentual > 0 and case_data.proposal_rules.aproveitar_bloqueio_como_entrada:
        entrada_gru = max(round(alvo_entrada - total_bloqueado, 2), 0.0)
    elif entrada_percentual > 0:
        entrada_gru = alvo_entrada
    else:
        entrada_gru = 0.0

    saldo = round(max(total_divida - total_bloqueado - entrada_gru - desconto_valor, 0.0), 2)
    valor_parcela_base_pura = saldo / parcelas if parcelas else 0.0
    valor_parcela, fator_ajuste_parcela, nota_calculo_selic = _fixed_installment_adjustment(
        case_data,
        parcelas,
        entrada_gru,
        valor_parcela_base_pura,
    )
    rows = _build_scenario_rows(
        consolidated,
        desconto_valor,
        entrada_gru,
        parcelas,
        incluir_bloqueio_no_desconto=case_data.proposal_rules.desconto_sobre_total,
        fator_ajuste_parcela=fator_ajuste_parcela,
    )
    return replace(
        scenario,
        parcelas=parcelas,
        desconto_percentual=desconto_percentual,
        desconto_valor=desconto_valor,
        entrada_minima_percentual=entrada_percentual,
        entrada_gru=entrada_gru,
        saldo_remanescente=saldo,
        valor_parcela=valor_parcela,
        valor_final=round(total_bloqueado + entrada_gru + saldo, 2),
        observacao=scenario.observacao,
        nota_calculo_selic=nota_calculo_selic or scenario.nota_calculo_selic,
        rows=rows,
        adaptada=adaptada,
    )


def build_proposal_scenarios(
    case_data: CaseData,
    selected_codes: set[str] | None = None,
    proposal_selections: dict[str, ProposalSelection] | None = None,
) -> list[ProposalScenario]:
    consolidated = consolidar_por_chave_arrecadatoria(case_data.subdebitos, case_data.descricoes_consolidadas)
    total_divida = round(sum(item.valor_total for item in consolidated), 2)
    total_bloqueado = total_bloqueado_efetivo(consolidated)
    base_vista = _base_para_faixa_vista(consolidated)
    faixas = case_data.proposal_rules.vista_faixas
    taxa_vista_unica = _taxa_vista_percentual_unico(base_vista, faixas)
    selected_codes = selected_codes or {modalidade["codigo"] for modalidade in MODALIDADES}
    proposal_selections = proposal_selections or {}

    scenarios: list[ProposalScenario] = []
    for modalidade in MODALIDADES:
        if modalidade["codigo"] not in selected_codes:
            continue
        desconto_base = round(
            sum(_build_discount_bases(consolidated, case_data.proposal_rules.desconto_sobre_total)),
            2,
        )
        if modalidade["codigo"] == "2":
            if case_data.proposal_rules.calculo_vista == "progressivo":
                desconto_percentual = _taxa_vista_progressiva(base_vista, faixas)
                desconto_valor = round(desconto_base * (desconto_percentual / 100.0), 2)
                observacao = (
                    f"Cálculo progressivo excepcional: percentual efetivo de "
                    f"{format_percent_br(desconto_percentual)} definido sobre base de faixa "
                    f"{format_currency_br(base_vista)} e aplicado sobre base geral de "
                    f"{format_currency_br(desconto_base)}."
                )
            else:
                desconto_percentual = taxa_vista_unica
                desconto_valor = round(desconto_base * (desconto_percentual / 100.0), 2)
                observacao = (
                    f"Percentual único da faixa: {format_percent_br(desconto_percentual)} "
                    f"(base de cálculo {format_currency_br(base_vista)})."
                )
        else:
            desconto_percentual = round(modalidade["desconto"] * 100, 2)
            desconto_valor = round(desconto_base * modalidade["desconto"], 2)
            observacao = ""

        alvo_entrada = round(total_divida * modalidade["entrada_minima"], 2)
        if modalidade["entrada_minima"] > 0 and case_data.proposal_rules.aproveitar_bloqueio_como_entrada:
            entrada_gru = max(round(alvo_entrada - total_bloqueado, 2), 0.0)
        elif modalidade["entrada_minima"] > 0:
            entrada_gru = alvo_entrada
        else:
            entrada_gru = 0.0

        saldo = round(max(total_divida - total_bloqueado - entrada_gru - desconto_valor, 0.0), 2)
        parcelas = modalidade["parcelas"]
        valor_parcela_base_pura = saldo / parcelas if parcelas else 0.0
        valor_parcela = round(valor_parcela_base_pura, 2)

        fator_ajuste_parcela = 1.0
        nota_calculo_selic = ""

        if parcelas > 1 and case_data.tipo_parcela == "FIXO (PREFIXADO)":
            media_selic = get_mean_selic_12_months(case_data.data_atualizacao)
            
            multiplicador = _initial_selic_months(case_data, entrada_gru)
                
            valor_com_atraso = valor_parcela_base_pura * (1 + ((media_selic / 100) * multiplicador))
            
            # Cálculo da última parcela com juros simples a partir da parcela base pura
            meses_ultima_parcela = multiplicador + parcelas - 1
            indice_correcao = media_selic * meses_ultima_parcela
            valor_ultima_parcela = valor_parcela_base_pura * (1 + (indice_correcao / 100))
            
            # A média aritmética da primeira e da última parcela
            valor_final_prefixado = (valor_com_atraso + valor_ultima_parcela) / 2
            
            fator_ajuste_parcela = valor_final_prefixado / valor_parcela_base_pura if valor_parcela_base_pura else 1.0
            valor_parcela = round(valor_final_prefixado, 2)
            
            selic_formatada = f"{media_selic:.4f}".replace(".", ",") + "%"
            indice_formatado = f"{indice_correcao:.4f}".replace(".", ",") + "%"
            
            nota_calculo_selic = (
                f"PARCELA PRÉ-FIXADA. MÉDIA SELIC ÚLTIMOS DOZE MESES: {selic_formatada}.\n"
                f"Cálculo: Parcela inicial {format_currency_br(valor_com_atraso)}; "
                f"Índice correção última parcela ({parcelas}ª) {indice_formatado}; "
                f"Valor última parcela {format_currency_br(valor_ultima_parcela)}; "
                f"Parcela Fixa (Média) {format_currency_br(valor_final_prefixado)}.\n"
            )


        rows = _build_scenario_rows(
            consolidated,
            desconto_valor,
            entrada_gru,
            parcelas,
            incluir_bloqueio_no_desconto=case_data.proposal_rules.desconto_sobre_total,
            fator_ajuste_parcela=fator_ajuste_parcela,
        )
        informacoes_bloqueio: list[str] = []
        if modalidade["entrada_minima"] > 0 and total_bloqueado > 0:
            if case_data.proposal_rules.aproveitar_bloqueio_como_entrada:
                informacoes_bloqueio.append("Valor bloqueado considerado para abatimento da entrada.")
            else:
                informacoes_bloqueio.append("Valor bloqueado desconsiderado para abatimento da entrada.")
        if (modalidade["desconto"] > 0 or modalidade["codigo"] == "2") and total_bloqueado > 0:
            if case_data.proposal_rules.desconto_sobre_total:
                informacoes_bloqueio.append("Desconto incidente também sobre o valor bloqueado.")
            else:
                informacoes_bloqueio.append("Desconto calculado apenas sobre o saldo após abatimento do valor bloqueado.")
        if informacoes_bloqueio:
            observacao = " ".join(part for part in [observacao, *informacoes_bloqueio] if part)
        scenario = ProposalScenario(
                codigo=modalidade["codigo"],
                modalidade=modalidade["modalidade"],
                parcelas=parcelas,
                desconto_percentual=desconto_percentual,
                desconto_valor=desconto_valor,
                entrada_minima_percentual=round(modalidade["entrada_minima"] * 100, 2),
                entrada_gru=entrada_gru,
                saldo_remanescente=saldo,
                valor_parcela=valor_parcela,
                valor_final=round(total_bloqueado + entrada_gru + saldo, 2),
                observacao=observacao,
                nota_calculo_selic=nota_calculo_selic,
                rows=rows,
            )
        selection = proposal_selections.get(modalidade["codigo"])
        if selection:
            if not validate_proposal_selection(scenario, selection):
                scenario = _apply_selection_to_scenario(
                    scenario,
                    selection,
                    consolidated,
                    total_divida,
                    total_bloqueado,
                    desconto_base,
                    case_data,
                )
        scenarios.append(scenario)
    return scenarios


def _render_header(layout: ProposalPdfLayout, case_data: CaseData, consolidated: list[Subdebito]) -> None:
    layout.block_title(
        "SIMULAÇÃO DE OPÇÕES DE ACORDO",
        fill=COLOR_NAVY,
        height=22,
        text_color=(1.0, 1.0, 1.0),
        stroke=COLOR_NAVY,
    )
    import getpass
    usuario_os = getpass.getuser()

    layout.key_value_grid(
        [
            ("Processo", case_data.processo),
            ("NUP", case_data.nup_requerimento or "-"),
            ("Devedor", case_data.devedor),
            ("CPF/CNPJ", case_data.cpf_cnpj),
            ("Competência", case_data.competencia_atualizacao or "-"),
            ("Atualizado em", case_data.data_atualizacao or "-"),
            ("Data Limite para Resposta", case_data.data_limite_resposta or "-", COLOR_RED_TEXT),
            ("Data da entrada/primeira parcela", case_data.data_primeira_parcela or "-", COLOR_RED_TEXT),
            ("Multa", format_percent_br(case_data.multa_percentual)),
            ("Usuario", usuario_os),
        ]
    )
    if case_data.condicoes_adicionais:
        layout.paragraph(
            f"Condições adicionais: {case_data.condicoes_adicionais}",
            size=10,
            font="F2",
            color=COLOR_RED_TEXT,
            leading=14,
        )
        layout.cursor_y -= 4
    total_geral = round(sum(item.valor_total for item in consolidated), 2)
    layout.highlighted_total("VALOR TOTAL GERAL DEVIDO", format_currency_br(total_geral))


# OBSERVACAO: quadro consolidado desativado. Pode ser reativado no futuro descomentando este bloco e a chamada em create_proposal_pdf.
# def _render_consolidated_table(layout: ProposalPdfLayout, consolidated: list[Subdebito]) -> None:
#     layout.block_title(
#         "DÍVIDA CONSOLIDADA POR CÓDIGO DE ARRECADAÇÃO",
#         fill=COLOR_SECTION_FILL,
#         text_color=COLOR_NAVY,
#         stroke=(0.62, 0.66, 0.72),
#     )
#     rows = [
#         [
#             item.descricao,
#             item.ug_gestao or "-",
#             item.gru_cr or "-",
#             format_currency_br(item.valor_atualizado),
#             format_currency_br(item.multa_art_523),
#             format_currency_br(item.valor_total),
#             format_currency_br(item.valor_bloqueado),
#         ]
#         for item in consolidated
#     ]
#     rows.append(
#         [
#             "TOTAL GERAL",
#             "",
#             "",
#             "",
#             "",
#             format_currency_br(round(sum(item.valor_total for item in consolidated), 2)),
#             format_currency_br(round(sum(item.valor_bloqueado for item in consolidated), 2)),
#         ]
#     )
#     layout.table(
#         headers=["TIPO DE DÉBITO", "UG/GESTÃO", "CR", "ATUALIZADO", "MULTA 523", "VALOR TOTAL", "BLOQ/DEP"],
#         rows=rows,
#         widths=[235, 110, 70, 105, 90, 105, 79],
#         header_fill=COLOR_TABLE_HEADER,
#         row_fill=(0.99, 0.99, 0.99),
#         alternate_row_fill=COLOR_TABLE_ALT,
#         total_fill=COLOR_TABLE_TOTAL,
#         total_row_indices={len(rows) - 1},
#     )
# 
# 
def _render_included_debts_table(layout: ProposalPdfLayout, subdebitos: list[Subdebito]) -> None:
    layout.block_title(
        "DÉBITO(S) INCLUÍDO(S) NESTA PROPOSTA",
        fill=COLOR_SECTION_FILL,
        text_color=COLOR_NAVY,
        stroke=(0.62, 0.66, 0.72),
    )
    rows = [
        [
            item.descricao,
            item.ug_gestao or "-",
            item.gru_cr or "-",
            format_currency_br(item.valor_atualizado),
            format_currency_br(item.multa_art_523),
            format_currency_br(item.valor_bloqueado),
        ]
        for item in subdebitos
    ]
    rows.append(
        [
            "TOTAL DOS SUBDÉBITOS",
            "",
            "",
            format_currency_br(round(sum(item.valor_atualizado for item in subdebitos), 2)),
            format_currency_br(round(sum(item.multa_art_523 for item in subdebitos), 2)),
            format_currency_br(round(sum(item.valor_bloqueado for item in subdebitos), 2)),
        ]
    )
    layout.table(
        headers=["DESCRIÇÃO", "UG/GESTÃO", "GRU(CR)", "VALOR ATUALIZADO", "MULTA 523", "VALOR BLOQUEADO"],
        rows=rows,
        widths=[290, 110, 75, 120, 95, 104],
        header_fill=COLOR_TABLE_HEADER,
        row_fill=(0.99, 0.99, 0.99),
        alternate_row_fill=COLOR_TABLE_ALT,
        total_fill=COLOR_TABLE_TOTAL,
        total_row_indices={len(rows) - 1},
        font_size=7.6,
        row_padding=4,
    )


def _render_deadline_callout(layout: ProposalPdfLayout, case_data: CaseData) -> None:
    data_limite = case_data.data_limite_resposta or "-"
    layout.callout(
        title="OPTE POR UMA DAS OPÇÕES DE PARCELAMENTO OFERTADAS ABAIXO OU NAS PÁGINAS SEGUINTES (se houver).",
        body="",
        fill=COLOR_ALERT_FILL,
        stroke=(0.72, 0.64, 0.52),
        bottom_prefix="RESPONDER OBRIGATORIAMENTE ATÉ ",
        bottom_accent=f"{data_limite}.",
    )


def _scenario_subtitle(case_data: CaseData, scenario: ProposalScenario, total_divida: float) -> str:
    default_parcelas = DEFAULT_PARCELAS_BY_CODE.get(scenario.codigo, scenario.parcelas)
    ajuste_parcelas = ""
    if scenario.parcelas > 1 and scenario.parcelas != default_parcelas:
        ajuste_parcelas = f" Parcelas: {scenario.parcelas}."
    if scenario.codigo == "2":
        return (
            f"Pagamento em parcela única. Desconto de {format_percent_br(scenario.desconto_percentual)} "
            f"(base de cálculo {format_currency_br(total_divida)})."
        )
    if scenario.entrada_minima_percentual > 0:
        return (
            f"{ajuste_parcelas} Entrada de {format_percent_br(scenario.entrada_minima_percentual)} sobre "
            f"{format_currency_br(total_divida)}."
        ).strip()
    return (
        f"{ajuste_parcelas} Parcelamento em até {scenario.parcelas}x. Desconto de {format_percent_br(scenario.desconto_percentual)} "
        f"(base de cálculo {format_currency_br(total_divida)})."
    ).strip()


def _scenario_title_modalidade(scenario: ProposalScenario) -> str:
    modalidade = scenario.modalidade
    if scenario.codigo in OPTIONAL_ENTRY_CODES and scenario.entrada_minima_percentual > 0:
        if scenario.codigo == "1":
            return "PARCELAMENTO COM ENTRADA"
        return modalidade.upper().replace("SEM ENTRADA", "COM ENTRADA")
    return modalidade.upper()


def _scenario_title(case_data: CaseData, scenario: ProposalScenario) -> str:
    title = f"OPÇÃO {scenario.codigo}: {_scenario_title_modalidade(scenario)}"
    if scenario.parcelas == 1:
        title += " (PARCELA ÚNICA)"
    else:
        if case_data.tipo_parcela == "FIXO (PREFIXADO)":
            tipo_str = "PRÉ-FIXADAS"
        elif "VARIAVEL" in (case_data.tipo_parcela or "").upper():
            tipo_str = "VARIÁVEIS"
        else:
            tipo_str = "FIXAS"
        title += f" ({scenario.parcelas} parcelas {tipo_str})"
    return title


def _scenario_fill(scenario: ProposalScenario) -> tuple[float, float, float]:
    return COLOR_OPTION_FILL


def _scenario_final_text(case_data: CaseData, scenario: ProposalScenario) -> str:
    if case_data.tipo_parcela == "FIXO (PREFIXADO)" and scenario.parcelas > 1:
        total_bloqueado = round(sum(row.valor_bloqueado for row in scenario.rows or []), 2)
        valor_prefixado = total_bloqueado + scenario.entrada_gru + (scenario.valor_parcela * scenario.parcelas)
        return (
            f"VALOR FINAL: {format_currency_br(scenario.valor_final)} "
            f"(valor final considerando parcelas pré-fixadas: {format_currency_br(valor_prefixado)})"
        )
    return f"VALOR FINAL: {format_currency_br(scenario.valor_final)} (valor sujeito a atualização mensal conforme condições gerais)"


def _scenario_date_text(case_data: CaseData, scenario: ProposalScenario) -> str:
    if scenario.entrada_minima_percentual > 0 and scenario.entrada_gru > 0:
        data_primeira = case_data.data_primeira_parcela or "-"
        data_segunda = (
            case_data.data_primeira_parcela_com_entrada
            or _default_first_installment_after_entry(case_data.data_primeira_parcela)
        )
        return f"Data da entrada: {data_primeira}   |   Data da primeira parcela: {data_segunda}"
    return f"Data da primeira parcela: {case_data.data_primeira_parcela or '-'}"


def _scenario_table_headers(case_data: CaseData, scenario: ProposalScenario) -> list[str]:
    if scenario.parcelas > 1:
        parcela_tipo = "Pré-fixadas" if case_data.tipo_parcela == "FIXO (PREFIXADO)" else "Variáveis"
        parcela_header = f"{scenario.parcelas} Parcelas\n{parcela_tipo}"
    else:
        parcela_header = "PARCELA"

    entrada_header = f"ENTRADA(GRU)\n({format_percent_br(scenario.entrada_minima_percentual)})"
    return [
        "TIPO DE DÉBITO",
        "UG / GRU",
        "TOTAL (+Art. 523)",
        "BLOQ/DEP",
        entrada_header,
        f"DESCONTO\n({format_percent_br(scenario.desconto_percentual)})",
        "SALDO",
        parcela_header,
    ]


def _scenario_table_rows(scenario: ProposalScenario) -> list[list[str]]:
    rows = [
        [
            row.descricao,
            f"{row.ug_gestao} / {row.gru_cr}",
            format_currency_br(row.valor_total),
            format_currency_br(row.valor_bloqueado),
            format_currency_br(row.entrada_gru),
            format_currency_br(row.desconto),
            format_currency_br(row.saldo),
            format_currency_br(row.parcela),
        ]
        for row in (scenario.rows or [])
    ]
    rows.append(
        [
            "TOTAL DA OPÇÃO",
            "",
            format_currency_br(round(sum(row.valor_total for row in scenario.rows or []), 2)),
            format_currency_br(round(sum(row.valor_bloqueado for row in scenario.rows or []), 2)),
            format_currency_br(round(sum(row.entrada_gru for row in scenario.rows or []), 2)),
            format_currency_br(round(sum(row.desconto for row in scenario.rows or []), 2)),
            format_currency_br(round(sum(row.saldo for row in scenario.rows or []), 2)),
            format_currency_br(round(sum(row.parcela for row in scenario.rows or []), 2)),
        ]
    )
    return rows


def _scenario_block_height(
    layout: ProposalPdfLayout,
    case_data: CaseData,
    scenario: ProposalScenario,
    total_divida: float,
    rows: list[list[str]],
    intro_only: bool = False,
) -> float:
    measured_rows = rows[:1] if intro_only else rows
    height = layout.block_title_height()
    if scenario.adaptada:
        height += layout.paragraph_height("* opção adaptada ao caso concreto.", size=7, leading=8)
    height += layout.paragraph_height(_scenario_final_text(case_data, scenario), size=12, leading=14)
    height += layout.paragraph_height(_scenario_subtitle(case_data, scenario, total_divida), size=9, leading=11)
    if scenario.observacao:
        height += layout.paragraph_height(scenario.observacao, size=8.6, leading=10.5)
    height += layout.paragraph_height(_scenario_date_text(case_data, scenario), size=8.8, leading=12)
    if round(sum(row.valor_bloqueado for row in scenario.rows or []), 2) > 0:
        height += layout.paragraph_height(
            "Valores bloqueados devem ser assinalados no Parcela PGU com data de aproximadamente 60 dias (mera previsão).",
            size=8.8,
            leading=12,
        )
    height += layout.table_height(
        _scenario_table_headers(case_data, scenario),
        measured_rows,
        SCENARIO_TABLE_WIDTHS,
        font_size=7.0,
        row_padding=4,
    )
    if scenario.nota_calculo_selic and not intro_only:
        height += layout.paragraph_height(scenario.nota_calculo_selic, size=6, leading=7)
        height += SELIC_NOTE_SPACING
    return height


def _render_scenario(layout: ProposalPdfLayout, case_data: CaseData, scenario: ProposalScenario, total_divida: float) -> None:
    rows = _scenario_table_rows(scenario)
    layout.ensure_block(_scenario_block_height(layout, case_data, scenario, total_divida, rows))
    layout.ensure_block(_scenario_block_height(layout, case_data, scenario, total_divida, rows, intro_only=True))

    layout.block_title(
        _scenario_title(case_data, scenario),
        fill=_scenario_fill(scenario),
        text_color=COLOR_NAVY,
        stroke=(0.54, 0.61, 0.70),
    )
    if scenario.adaptada:
        layout.paragraph(
            "* opção adaptada ao caso concreto.",
            size=7,
            font="F3",
            leading=8,
            color=COLOR_NOTE_TEXT,
        )

    layout.paragraph(
        _scenario_final_text(case_data, scenario),
        size=12,
        font="F2",
        color=COLOR_RESULT_TEXT,
        leading=14,
    )
    layout.paragraph(_scenario_subtitle(case_data, scenario, total_divida), size=9, font="F3", leading=11, color=COLOR_INK)
    if scenario.observacao:
        layout.paragraph(scenario.observacao, size=8.6, leading=10.5, color=COLOR_NOTE_TEXT)

    layout.paragraph(
        _scenario_date_text(case_data, scenario),
        size=8.8,
        font="F2",
        color=COLOR_RED_TEXT,
    )
    total_bloqueado_cenario = round(sum(row.valor_bloqueado for row in scenario.rows or []), 2)
    if total_bloqueado_cenario > 0:
        layout.paragraph(
            "Valores bloqueados devem ser assinalados no Parcela PGU com data de aproximadamente 60 dias (mera previsão).",
            size=8.8,
            font="F2",
            color=COLOR_RED_TEXT,
        )

    layout.table(
        headers=_scenario_table_headers(case_data, scenario),
        rows=rows,
        widths=SCENARIO_TABLE_WIDTHS,
        header_fill=COLOR_TABLE_HEADER,
        row_fill=(1.0, 1.0, 1.0),
        alternate_row_fill=COLOR_TABLE_ALT,
        total_fill=COLOR_TABLE_TOTAL,
        total_row_indices={len(rows) - 1},
        font_size=7.0,
        row_padding=4,
    )
    if scenario.nota_calculo_selic:
        layout.paragraph(
            scenario.nota_calculo_selic,
            size=6,
            leading=7,
            color=COLOR_NOTE_TEXT,
        )
        layout.cursor_y -= SELIC_NOTE_SPACING


def _render_titled_paragraph(
    layout: ProposalPdfLayout,
    title: str,
    text: str,
    fill: tuple[float, float, float],
    text_color: tuple[float, float, float] = COLOR_INK,
    title_color: tuple[float, float, float] = COLOR_NAVY,
    size: float = 9.2,
    leading: float = 12.4,
    font: str = "F1",
    justify: bool = True,
) -> None:
    layout.ensure_block(layout.block_title_height() + layout.paragraph_height(text, size=size, leading=leading))
    layout.block_title(title, fill=fill, text_color=title_color, stroke=(0.62, 0.68, 0.76))
    layout.paragraph(text, size=size, font=font, color=text_color, leading=leading, justify=justify)


def _render_conditions(layout: ProposalPdfLayout, case_data: CaseData) -> None:
    _render_titled_paragraph(
        layout,
        "CONDIÇÕES GERAIS",
        CONDICOES_GERAIS,
        fill=(0.96, 0.94, 0.91),
    )
    _render_titled_paragraph(
        layout,
        "OBSERVAÇÕES",
        OBSERVACOES_PROPOSTA,
        fill=COLOR_PANEL_FILL,
    )
    _render_titled_paragraph(
        layout,
        "ATENÇÃO",
        ATENCAO_PROPOSTA,
        fill=(1.0, 0.91, 0.91),
        text_color=COLOR_RED_TEXT,
        title_color=COLOR_RED_TEXT,
        size=9.4,
        leading=12.6,
        font="F2",
    )


    pass


def create_proposal_pdf(
    case_data: CaseData,
    output_path: str | Path,
    selected_codes: set[str] | None = None,
    scenarios: list[ProposalScenario] | None = None,
) -> Path:
    consolidated = consolidar_por_chave_arrecadatoria(case_data.subdebitos, case_data.descricoes_consolidadas)
    scenarios = scenarios or build_proposal_scenarios(
        case_data,
        selected_codes=selected_codes,
        proposal_selections=case_data.propostas_selecionadas,
    )
    total_divida = round(sum(item.valor_total for item in consolidated), 2)

    pdf = SimplePdf()
    layout = ProposalPdfLayout(pdf)
    _render_header(layout, case_data, consolidated)
    # Quadro consolidado desativado. Pode ser reativado no futuro junto com a funcao comentada acima.
    # _render_consolidated_table(layout, consolidated)
    _render_included_debts_table(layout, case_data.subdebitos)
    _render_deadline_callout(layout, case_data)
    for scenario in scenarios:
        _render_scenario(layout, case_data, scenario, total_divida)
    _render_conditions(layout, case_data)
    
    if case_data.tipo_parcela == "FIXO (PREFIXADO)":
        from pactuacalc.selic_api import get_last_12_selic_rates
        rates = get_last_12_selic_rates(case_data.data_atualizacao)
        if rates:
            headers = []
            valores = []
            total_val = 0.0
            for r in rates:
                item_date = parse_iso_date(r.get("data", ""))
                headers.append(item_date.strftime("%m/%y") if item_date else r.get("data", "-"))
                v = float(r.get("valor", 0.0))
                total_val += v
                valores.append(f"{v:.4f}".replace(".", ",") + "%")
            
            media = total_val / len(rates)
            headers.append("Taxa média")
            valores.append(f"{media:.4f}".replace(".", ",") + "%")
            width = 702 / len(headers)

            selic_intro = (
                "O parcelamento FIXO (pré-fixado) é calculado com base na média aritmética simples "
                "das últimas 12 taxas mensais da Selic imediatamente anteriores ao mês da atualização da dívida."
            )
            layout.ensure_block(
                layout.block_title_height()
                + layout.paragraph_height(selic_intro, size=9, leading=11)
                + layout.table_height(headers, [valores], [width for _ in headers], font_size=6, row_padding=3)
                + 8
            )
            layout.block_title(
                "MEMÓRIA DE CÁLCULO - SELIC MÉDIA (ÚLTIMOS 12 MESES)",
                fill=COLOR_SECTION_FILL,
                text_color=COLOR_NAVY,
                stroke=(0.54, 0.61, 0.70),
            )
            layout.paragraph(
                selic_intro,
                size=9,
                leading=11,
                color=COLOR_INK,
            )
            layout.cursor_y -= 8
            
            layout.table(
                headers=headers,
                rows=[valores],
                widths=[width for _ in headers],
                header_fill=COLOR_TABLE_HEADER,
                row_fill=(0.98, 0.98, 0.98),
                total_fill=COLOR_TABLE_TOTAL,
                font_size=6,
                row_padding=3,
            )
            layout.cursor_y -= SELIC_NOTE_SPACING

    target = Path(output_path)
    import datetime
    hoje = datetime.datetime.now().strftime("%d/%m/%Y")
    nup = case_data.nup_requerimento or "-"
    devedor = (case_data.devedor or "Devedor").upper()
    footer_text = f"NUP: {nup}   |   Devedor: {devedor}   |   Gerado em: {hoje}"
    
    escaped_footer = footer_text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    y_footer = 12.0
    margin_x = 24.0
    footer_commands = [
        "q",
        "BT",
        "/F1 8.00 Tf",
        "0.40 0.40 0.40 rg",
        f"1 0 0 1 {margin_x:.2f} {y_footer:.2f} Tm",
        f"({escaped_footer}) Tj",
        "ET",
        "Q"
    ]
    for page_commands in pdf.pages:
        page_commands.extend(footer_commands)

    return pdf.save(target)


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
    "para onde deve também ser enviada a sua opção de escolha até a DATA LIMITE PARA RESPOSTA (ver acima)."
)


ATENCAO_PROPOSTA = (
    "ATENÇÃO: Conforme informação do quadro ao lado, os valores das parcelas constantes das opções abaixo devem ser atualizados mensalmente. "
    "E, quando se trate de modalidade de parcelamento FIXO (parcela pré-fixada), os valores dessas parcelas serão RECALCULADOS no SISTEMA PARCELA PGU, "
    "com base na SELIC MÉDIA MENSAL dos últimos doze meses e APRESENTADOS no TERMO DE PARCELAMENTO A SER ENVIADO AO DEVEDOR."
)


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
    data_atual = parse_iso_date(case_data.data_atualizacao)
    data_primeira = parse_iso_date(case_data.data_primeira_parcela)
    if data_atual and data_primeira:
        m_diff = (data_primeira.year - data_atual.year) * 12 + (data_primeira.month - data_atual.month)
        m_diff = max(m_diff, 0)
    else:
        m_diff = 0

    multiplicador = max(m_diff, 1) if entrada_gru > 0 else max(m_diff - 1, 0)
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
    consolidated = consolidar_por_chave_arrecadatoria(case_data.subdebitos)
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
            
            data_atual = parse_iso_date(case_data.data_atualizacao)
            data_primeira = parse_iso_date(case_data.data_primeira_parcela)
            if data_atual and data_primeira:
                m_diff = (data_primeira.year - data_atual.year) * 12 + (data_primeira.month - data_atual.month)
                m_diff = max(m_diff, 0)
            else:
                m_diff = 0

            if modalidade["entrada_minima"] > 0 and entrada_gru > 0:
                multiplicador = max(m_diff, 1)
            else:
                multiplicador = max(m_diff - 1, 0)
                
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
    layout.block_title("QUADRO DEMONSTRATIVO DE OPÇÕES DE PAGAMENTO", fill=(0.90, 0.93, 0.96))
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
            ("Data Limite para Resposta", case_data.data_limite_resposta or "-", (0.76, 0.08, 0.08)),
            ("Data da entrada/primeira parcela", case_data.data_primeira_parcela or "-", (0.76, 0.08, 0.08)),
            ("Multa", format_percent_br(case_data.multa_percentual)),
            ("Usuario", usuario_os),
        ]
    )
    if case_data.condicoes_adicionais:
        layout.paragraph(
            f"Condições adicionais: {case_data.condicoes_adicionais}",
            size=10,
            font="F2",
            color=(0.76, 0.08, 0.08),
            leading=14,
        )
        layout.cursor_y -= 4
    total_geral = round(sum(item.valor_total for item in consolidated), 2)
    layout.highlighted_total("VALOR TOTAL GERAL DEVIDO", format_currency_br(total_geral))


def _render_consolidated_table(layout: ProposalPdfLayout, consolidated: list[Subdebito]) -> None:
    layout.block_title("TOTAL DEVIDO POR CODIGOS CONSOLIDADOS", fill=(0.88, 0.94, 0.88))
    rows = [
        [
            item.descricao,
            item.ug_gestao or "-",
            item.gru_cr or "-",
            format_currency_br(item.valor_atualizado),
            format_currency_br(item.multa_art_523),
            format_currency_br(item.valor_total),
            format_currency_br(item.valor_bloqueado),
        ]
        for item in consolidated
    ]
    rows.append(
        [
            "TOTAL GERAL",
            "",
            "",
            "",
            "",
            format_currency_br(round(sum(item.valor_total for item in consolidated), 2)),
            format_currency_br(round(sum(item.valor_bloqueado for item in consolidated), 2)),
        ]
    )
    layout.table(
        headers=["TIPO DE DÉBITO", "UG/GESTÃO", "CR", "ATUALIZADO", "MULTA 523", "VALOR TOTAL", "BLOQ/DEP"],
        rows=rows,
        widths=[190, 105, 65, 95, 85, 95, 85],
        header_fill=(0.86, 0.91, 0.86),
        row_fill=(0.99, 0.99, 0.99),
        total_row_indices={len(rows) - 1},
    )


def _render_deadline_callout(layout: ProposalPdfLayout, case_data: CaseData) -> None:
    data_limite = case_data.data_limite_resposta or "-"
    layout.callout(
        title="OPTE POR UMA DAS OPÇÕES DE PARCELAMENTO OFERTADAS ABAIXO.",
        body="",
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


def _render_scenario(layout: ProposalPdfLayout, case_data: CaseData, scenario: ProposalScenario, total_divida: float) -> None:
    color = (0.93, 0.95, 0.84) if scenario.codigo in {"2", "3.A", "3.B"} else (0.97, 0.93, 0.78)
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
    layout.block_title(title, fill=color)
    if scenario.adaptada:
        layout.paragraph(
            "* opção adaptada ao caso concreto.",
            size=7,
            font="F3",
            leading=8,
            color=(0.45, 0.18, 0.10),
        )

    if case_data.tipo_parcela == "FIXO (PREFIXADO)" and scenario.parcelas > 1:
        total_bloqueado = round(sum(row.valor_bloqueado for row in scenario.rows or []), 2)
        valor_prefixado = total_bloqueado + scenario.entrada_gru + (scenario.valor_parcela * scenario.parcelas)
        texto_final = f"VALOR FINAL: {format_currency_br(scenario.valor_final)} (valor final considerando parcelas pré-fixadas: {format_currency_br(valor_prefixado)})"
    else:
        texto_final = f"VALOR FINAL: {format_currency_br(scenario.valor_final)} (valor sujeito a atualização mensal conforme condições gerais)"

    layout.paragraph(
        texto_final,
        size=12,
        font="F2",
        color=(0.16, 0.24, 0.14),
        leading=14,
    )
    layout.paragraph(_scenario_subtitle(case_data, scenario, total_divida), size=9, font="F3", leading=11)
    if scenario.observacao:
        layout.paragraph(scenario.observacao, size=8.6, leading=10.5, color=(0.30, 0.20, 0.12))
    if scenario.entrada_minima_percentual > 0 and scenario.entrada_gru > 0:
        data_primeira = case_data.data_primeira_parcela or "-"
        data_segunda = (
            case_data.data_primeira_parcela_com_entrada
            or _default_first_installment_after_entry(case_data.data_primeira_parcela)
        )
        texto_data = f"Data da entrada: {data_primeira}   |   Data da primeira parcela: {data_segunda}"
    else:
        texto_data = f"Data da primeira parcela: {case_data.data_primeira_parcela or '-'}"

    layout.paragraph(
        texto_data,
        size=8.8,
        font="F2",
        color=(0.72, 0.12, 0.12),
    )
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
    
    if scenario.parcelas > 1:
        parcela_tipo = "Pré-fixadas" if case_data.tipo_parcela == "FIXO (PREFIXADO)" else "Variáveis"
        parcela_header = f"{scenario.parcelas} Parcelas\n{parcela_tipo}"
    else:
        parcela_header = "PARCELA"
    
    entrada_header = f"ENTRADA(GRU)\n({format_percent_br(scenario.entrada_minima_percentual)})"

    layout.table(
        headers=[
            "TIPO DE DÉBITO",
            "UG / GRU",
            "TOTAL (+Art. 523)",
            "BLOQ/DEP",
            entrada_header,
            f"DESCONTO\n({format_percent_br(scenario.desconto_percentual)})",
            "SALDO",
            parcela_header,
        ],
        rows=rows,
        widths=[150, 115, 95, 80, 85, 80, 80, 80],
        header_fill=(0.98, 0.98, 0.98),
        row_fill=(1.0, 1.0, 1.0),
        total_row_indices={len(rows) - 1},
        font_size=6.8,
        row_padding=3,
    )
    if scenario.nota_calculo_selic:
        layout.paragraph(
            scenario.nota_calculo_selic,
            size=6,
            leading=7,
            color=(0.30, 0.20, 0.12),
        )


def _render_conditions(layout: ProposalPdfLayout, case_data: CaseData) -> None:
    layout.block_title("CONDIÇÕES GERAIS", fill=(0.98, 0.94, 0.94))
    layout.paragraph(CONDICOES_GERAIS, size=9.2, leading=12.4, justify=True)
    layout.block_title("OBSERVAÇÕES", fill=(0.95, 0.98, 1.0))
    layout.paragraph(OBSERVACOES_PROPOSTA, size=9.2, leading=12.4, justify=True)
    layout.block_title("ATENÇÃO", fill=(1.0, 0.93, 0.93))
    layout.paragraph(
        ATENCAO_PROPOSTA,
        size=9.4,
        font="F2",
        color=(0.80, 0.05, 0.05),
        leading=12.6,
        justify=True,
    )


    pass


def create_proposal_pdf(
    case_data: CaseData,
    output_path: str | Path,
    selected_codes: set[str] | None = None,
    scenarios: list[ProposalScenario] | None = None,
) -> Path:
    consolidated = consolidar_por_chave_arrecadatoria(case_data.subdebitos)
    scenarios = scenarios or build_proposal_scenarios(
        case_data,
        selected_codes=selected_codes,
        proposal_selections=case_data.propostas_selecionadas,
    )
    total_divida = round(sum(item.valor_total for item in consolidated), 2)

    pdf = SimplePdf()
    layout = ProposalPdfLayout(pdf)
    _render_header(layout, case_data, consolidated)
    _render_consolidated_table(layout, consolidated)
    _render_deadline_callout(layout, case_data)
    for scenario in scenarios:
        _render_scenario(layout, case_data, scenario, total_divida)
    _render_conditions(layout, case_data)
    
    if case_data.tipo_parcela == "FIXO (PREFIXADO)":
        from pactuacalc.selic_api import get_last_12_selic_rates
        rates = get_last_12_selic_rates(case_data.data_atualizacao)
        if rates:
            layout.block_title("MEMÓRIA DE CÁLCULO - SELIC MÉDIA (ÚLTIMOS 12 MESES)", fill=(0.92, 0.92, 0.92))
            layout.paragraph(
                "O parcelamento FIXO (pré-fixado) é calculado com base na média aritmética simples "
                "das últimas 12 taxas mensais da Selic imediatamente anteriores ao mês da atualização da dívida.",
                size=9,
                leading=11,
                color=(0.2, 0.2, 0.2),
            )
            layout.cursor_y -= 8
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
            
            layout.table(
                headers=headers,
                rows=[valores],
                widths=[width for _ in headers],
                header_fill=(0.88, 0.88, 0.88),
                row_fill=(0.98, 0.98, 0.98),
                font_size=6,
                row_padding=3,
            )

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


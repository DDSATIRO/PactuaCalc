from __future__ import annotations

from dataclasses import dataclass

from pactuacalc.models import CaseData, Subdebito


def distribuir_valor_bloqueado(case_data: CaseData) -> None:
    total = round(case_data.valor_bloqueado_geral, 2)
    if total <= 0 or not case_data.subdebitos:
        return

    total_elegivel = round(sum(item.valor_total for item in case_data.subdebitos), 2)
    if total_elegivel <= 0:
        return

    allocated = 0.0
    for item in case_data.subdebitos[:-1]:
        proporcao = item.valor_total / total_elegivel
        bloqueado = round(total * proporcao, 2)
        item.valor_bloqueado = min(bloqueado, item.valor_total)
        allocated += item.valor_bloqueado

    last = case_data.subdebitos[-1]
    restante = round(total - allocated, 2)
    last.valor_bloqueado = min(max(restante, 0.0), last.valor_total)


def total_bloqueado_efetivo(subdebitos: list[Subdebito]) -> float:
    return round(sum(item.valor_bloqueado for item in subdebitos), 2)


def consolidar_por_chave_arrecadatoria(subdebitos: list[Subdebito]) -> list[Subdebito]:
    grouped: dict[tuple[str, str], Subdebito] = {}
    passthrough: list[Subdebito] = []

    for item in subdebitos:
        if not item.ug_gestao or not item.gru_cr:
            passthrough.append(item)
            continue
        key = (item.ug_gestao, item.gru_cr)
        if key not in grouped:
            grouped[key] = Subdebito(
                tipo=item.tipo,
                descricao=item.descricao,
                referencia_origem=item.referencia_origem,
                valor_atualizado=item.valor_atualizado,
                multa_art_523=item.multa_art_523,
                valor_bloqueado=item.valor_bloqueado,
                ug=item.ug,
                gestao=item.gestao,
                gru_cr=item.gru_cr,
                editavel_usuario=item.editavel_usuario,
            )
            continue
        grouped_item = grouped[key]
        grouped_item.valor_atualizado = round(
            grouped_item.valor_atualizado + item.valor_atualizado, 2
        )
        grouped_item.multa_art_523 = round(
            grouped_item.multa_art_523 + item.multa_art_523, 2
        )
        grouped_item.valor_bloqueado = round(
            grouped_item.valor_bloqueado + item.valor_bloqueado, 2
        )

    return passthrough + list(grouped.values())


@dataclass
class MergeConflict:
    field_name: str
    current_value: str
    incoming_value: str


def _normalize_scalar(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Sim" if value else "Nao"
    return str(value).strip()


def _merge_text_values(current_value: str, incoming_value: str) -> str:
    current_parts = [part.strip() for part in current_value.split(" | ") if part.strip()]
    incoming_parts = [part.strip() for part in incoming_value.split(" | ") if part.strip()]
    merged: list[str] = []
    for part in current_parts + incoming_parts:
        if part and part not in merged:
            merged.append(part)
    return " | ".join(merged)


def merge_case_data(base: CaseData, incoming: CaseData) -> tuple[CaseData, list[MergeConflict]]:
    conflicts: list[MergeConflict] = []
    combinable_fields = {"tipo_parcela", "observacao", "funcao_tcu", "origem_debito_tcu"}
    scalar_fields = [
        "identificador_projef",
        "processo",
        "nup_requerimento",
        "devedor",
        "cpf_cnpj",
        "competencia_atualizacao",
        "data_atualizacao",
        "tipo_parcela",
        "observacao",
        "condicoes_adicionais",
        "data_limite_resposta",
        "data_primeira_parcela",
        "origem_relatorio",
        "funcao_tcu",
        "origem_debito_tcu",
    ]

    for field_name in scalar_fields:
        current_value = _normalize_scalar(getattr(base, field_name))
        incoming_value = _normalize_scalar(getattr(incoming, field_name))
        if not current_value and incoming_value:
            setattr(base, field_name, getattr(incoming, field_name))
        elif field_name in combinable_fields and current_value and incoming_value and current_value != incoming_value:
            setattr(base, field_name, _merge_text_values(current_value, incoming_value))
        elif current_value and incoming_value and current_value != incoming_value:
            conflicts.append(
                MergeConflict(
                    field_name=field_name,
                    current_value=current_value,
                    incoming_value=incoming_value,
                )
            )

    if base.multa_percentual <= 0 and incoming.multa_percentual > 0:
        base.multa_percentual = incoming.multa_percentual
    elif base.multa_percentual > 0 and incoming.multa_percentual > 0 and base.multa_percentual != incoming.multa_percentual:
        conflicts.append(
            MergeConflict(
                field_name="multa_percentual",
                current_value=str(base.multa_percentual),
                incoming_value=str(incoming.multa_percentual),
            )
        )

    if base.valor_bloqueado_geral <= 0 and incoming.valor_bloqueado_geral > 0:
        base.valor_bloqueado_geral = incoming.valor_bloqueado_geral
    elif (
        base.valor_bloqueado_geral > 0
        and incoming.valor_bloqueado_geral > 0
        and base.valor_bloqueado_geral != incoming.valor_bloqueado_geral
    ):
        conflicts.append(
            MergeConflict(
                field_name="valor_bloqueado_geral",
                current_value=str(base.valor_bloqueado_geral),
                incoming_value=str(incoming.valor_bloqueado_geral),
            )
        )

    if not base.sistema_origem and incoming.sistema_origem:
        base.sistema_origem = incoming.sistema_origem
    elif incoming.sistema_origem and base.sistema_origem != incoming.sistema_origem:
        base.sistema_origem = "misto"

    if incoming.incluir_juros_tcu and not base.incluir_juros_tcu:
        base.incluir_juros_tcu = True

    existing_reports = set(base.relatorios_anexados)
    for origin in incoming.relatorios_anexados or [incoming.origem_relatorio]:
        if origin and origin not in existing_reports:
            base.relatorios_anexados.append(origin)
            existing_reports.add(origin)

    base.subdebitos.extend(incoming.subdebitos)
    base.lancamentos_tcu.extend(incoming.lancamentos_tcu)
    return base, conflicts


def _copy_tcu_subdebito_preserving_user_fields(
    current: Subdebito,
    incoming: Subdebito,
) -> Subdebito:
    return Subdebito(
        tipo=incoming.tipo or current.tipo,
        descricao=incoming.descricao or current.descricao,
        referencia_origem=incoming.referencia_origem or current.referencia_origem,
        valor_atualizado=incoming.valor_atualizado,
        multa_art_523=incoming.multa_art_523,
        valor_bloqueado=current.valor_bloqueado,
        ug=current.ug,
        gestao=current.gestao,
        gru_cr=current.gru_cr,
        editavel_usuario=current.editavel_usuario,
    )


def replace_tcu_case_data(base: CaseData, incoming: CaseData) -> tuple[CaseData, list[MergeConflict]]:
    conflicts: list[MergeConflict] = []
    scalar_fields = [
        "processo",
        "nup_requerimento",
        "devedor",
        "cpf_cnpj",
        "competencia_atualizacao",
        "data_atualizacao",
        "tipo_parcela",
        "observacao",
        "data_limite_resposta",
        "data_primeira_parcela",
        "origem_relatorio",
        "funcao_tcu",
        "origem_debito_tcu",
    ]

    for field_name in scalar_fields:
        incoming_value = getattr(incoming, field_name)
        if _normalize_scalar(incoming_value):
            setattr(base, field_name, incoming_value)

    if incoming.incluir_juros_tcu:
        base.incluir_juros_tcu = True
    else:
        base.incluir_juros_tcu = incoming.incluir_juros_tcu

    if incoming.sistema_origem:
        if base.sistema_origem in {"", "tcu"}:
            base.sistema_origem = incoming.sistema_origem
        elif base.sistema_origem != incoming.sistema_origem:
            base.sistema_origem = "misto"

    existing_reports = set(base.relatorios_anexados)
    for origin in incoming.relatorios_anexados or [incoming.origem_relatorio]:
        if origin and origin not in existing_reports:
            base.relatorios_anexados.append(origin)
            existing_reports.add(origin)

    base.lancamentos_tcu = list(incoming.lancamentos_tcu)

    if incoming.subdebitos:
        replacement = incoming.subdebitos[0]
        if base.subdebitos:
            base.subdebitos[0] = _copy_tcu_subdebito_preserving_user_fields(
                base.subdebitos[0],
                replacement,
            )
        else:
            base.subdebitos = [replacement]

    return base, conflicts


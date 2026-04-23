from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
from pathlib import Path
import unicodedata

import pdfplumber

from geracordo.models import CaseData, Subdebito, TcuLancamento, parse_iso_date


SECTION_PATTERNS = {
    "RESUMO DO CALCULO": [r"RESUMO DO C.LCULO"],
    "I - PARTES": [r"I - PARTES"],
    "II - TOTALIZACAO": [r"II - TOTALIZA..O", r"II - TOTALIZACAO"],
    "OBSERVACOES DIGITADAS PELO USUARIO": [
        r"OBSERVA..ES DIGITADAS PELO USU.RIO",
        r"OBSERVACOES DIGITADAS PELO USUARIO",
    ],
    "DEMONSTRATIVO DE PARCELAS": [r"DEMONSTRATIVO DE PARCELAS"],
}

IDENTIFICADOR_RE = re.compile(
    r"(?:identificador\s+do\s+c[aá]lculo|id(?:entificador)?\s+do\s+c[aá]lculo)[^\w]?([a-z0-9-]{6,})",
    re.IGNORECASE,
)
PROCESSO_RE = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")
NUP_RE = re.compile(r"\d{5}\.\d{6}/\d{4}-\d{2}")
CPF_CNPJ_RE = re.compile(
    r"\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"
)
COMPETENCIA_RE = re.compile(r"\b(0[1-9]|1[0-2])/\d{4}\b")
DATE_RE = re.compile(r"\b([0-3]\d/[0-1]\d/\d{4})\b")
MONEY_RE = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")
IDENTIFICADOR_FOOTER_RE = re.compile(
    r"IDENTIFICADOR\s+([A-Z0-9-]{6,})",
    flags=re.IGNORECASE,
)
TEXTUAL_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+DE\s+([A-ZÇÃÁÉÊÍÓÔÕÚ]+)\s+DE\s+(\d{4})\b",
    flags=re.IGNORECASE,
)
PT_BR_MONTHS = {
    "JANEIRO": 1,
    "FEVEREIRO": 2,
    "MARCO": 3,
    "MARÇO": 3,
    "ABRIL": 4,
    "MAIO": 5,
    "JUNHO": 6,
    "JULHO": 7,
    "AGOSTO": 8,
    "SETEMBRO": 9,
    "OUTUBRO": 10,
    "NOVEMBRO": 11,
    "DEZEMBRO": 12,
}
TCU_HISTORY_ROW_RE = re.compile(
    r"(\d{2}/\d{2}/\d{4})\s+([DC])\s+(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*,\d{2})",
    flags=re.IGNORECASE,
)


@dataclass
class ParsedSections:
    raw_text: str
    sections: dict[str, str]


def normalize_anchor_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).upper()


def denormalize_month(month_name: str) -> int | None:
    normalized = normalize_anchor_text(month_name)
    return PT_BR_MONTHS.get(normalized)


def extract_text_from_pdf(path: str | Path) -> str:
    chunks: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            if text:
                chunks.append(text)
    return "\n".join(chunks)


def extract_text_by_page(path: str | Path) -> list[str]:
    chunks: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            chunks.append(text)
    return chunks


def split_sections(text: str) -> ParsedSections:
    positions: list[tuple[int, str]] = []
    normalized_text = normalize_anchor_text(text)
    for canonical_title, patterns in SECTION_PATTERNS.items():
        matches = [
            re.search(pattern, normalized_text, flags=re.IGNORECASE)
            for pattern in patterns
        ]
        indexes = [match.start() for match in matches if match]
        if indexes:
            positions.append((min(indexes), canonical_title))
    positions.sort()

    sections: dict[str, str] = {}
    for idx, (start, title) in enumerate(positions):
        end = positions[idx + 1][0] if idx + 1 < len(positions) else len(text)
        sections[title.upper()] = text[start:end].strip()
    return ParsedSections(raw_text=text, sections=sections)


def parse_brl_money(value: str) -> float:
    cleaned = value.strip().replace(".", "").replace(",", ".")
    try:
        return float(Decimal(cleaned))
    except (InvalidOperation, ValueError):
        return 0.0


def find_label_value(text: str, labels: list[str]) -> str:
    for label in labels:
        match = re.search(rf"{label}\s*[:\-]?\s*(.+)", text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def extract_identifier(text: str) -> str:
    raw_match = IDENTIFICADOR_RE.search(text)
    if raw_match:
        return raw_match.group(1)

    normalized_text = normalize_anchor_text(text)
    footer_match = IDENTIFICADOR_FOOTER_RE.search(normalized_text)
    if footer_match:
        return footer_match.group(1).lower()
    return ""


def extract_report_date(text: str) -> str:
    date_match = DATE_RE.search(text)
    if date_match:
        return date_match.group(1)

    normalized_text = normalize_anchor_text(text)
    textual_match = TEXTUAL_DATE_RE.search(normalized_text)
    if not textual_match:
        return ""

    day = int(textual_match.group(1))
    month = denormalize_month(textual_match.group(2))
    year = int(textual_match.group(3))
    if not month:
        return ""
    return datetime(year, month, day).strftime("%d/%m/%Y")


def competencia_from_date(value: str) -> str:
    parsed = parse_iso_date(value)
    if not parsed:
        return ""
    return parsed.strftime("%m/%Y")


def extract_date_from_observacoes(observacoes: str, labels: list[str]) -> str:
    lowered = observacoes.lower()
    for label in labels:
        index = lowered.find(label.lower())
        if index < 0:
            continue
        snippet = observacoes[index : index + 120]
        match = DATE_RE.search(snippet)
        if match:
            return match.group(1)
    return ""


def infer_tipo_parcela(text: str) -> str:
    normalized = normalize_anchor_text(text)
    if "FIXO" in normalized or "PREFIXADO" in normalized:
        return "FIXO (PREFIXADO)"
    return "VARIAVEL (POS-FIXADO)"


def parse_partes_section(section_text: str, processo: str) -> list[Subdebito]:
    subdebitos: list[Subdebito] = []
    lines = [line.strip() for line in section_text.splitlines() if line.strip()]
    for line in lines:
        normalized_line = normalize_anchor_text(line)
        if (
            "TOTAL PARTES" in normalized_line
            or "PRINCIPAL CORRIGIDO" in normalized_line
            or "JUROS MORATORIOS" in normalized_line
            or "TOTAL (R$)" in normalized_line
        ):
            continue
        money_matches = MONEY_RE.findall(line)
        if not money_matches:
            continue
        description = MONEY_RE.sub("", line).strip(" -\t")
        value = parse_brl_money(money_matches[-1])
        if value <= 0:
            continue
        subdebitos.append(
            Subdebito(
                tipo="principal",
                descricao=description or "Subdebito principal",
                referencia_origem=processo or description or "",
                valor_atualizado=value,
            )
        )
    return subdebitos


def parse_honorarios(section_text: str) -> Subdebito | None:
    if "honor" not in section_text.lower():
        return None
    lines = [line.strip() for line in section_text.splitlines() if line.strip()]
    for line in lines:
        if "honor" not in line.lower():
            continue
        money_matches = MONEY_RE.findall(line)
        if not money_matches:
            continue
        return Subdebito(
            tipo="honorarios",
            descricao="Honorarios advocaticios",
            referencia_origem="Honorarios",
            valor_atualizado=parse_brl_money(money_matches[-1]),
            ug="110060",
            gestao="00001",
            gru_cr="91719-9",
        )
    return None


def parse_totalizacao_details(section_text: str) -> tuple[float, float]:
    subtotal = 0.0
    multa_total = 0.0
    multa_percentual = 0.0

    for line in [line.strip() for line in section_text.splitlines() if line.strip()]:
        normalized_line = normalize_anchor_text(line)
        money_matches = MONEY_RE.findall(line)
        line_total = parse_brl_money(money_matches[-1]) if money_matches else 0.0

        if "SUBTOTAL DA CONTA" in normalized_line:
            subtotal = line_total
        if "MULTA" in normalized_line and "523" in normalized_line:
            multa_total = line_total
            percentual_match = re.search(r"(\d{1,2})\s*%", normalized_line)
            if percentual_match:
                multa_percentual = float(percentual_match.group(1))

    if multa_total > 0 and subtotal > 0 and multa_percentual == 0.0:
        multa_percentual = round((multa_total / subtotal) * 100, 2)
    return multa_percentual, multa_total


def distribuir_multa_nos_subdebitos(subdebitos: list[Subdebito], multa_total: float, multa_percentual: float) -> None:
    principais = [item for item in subdebitos if item.tipo == "principal"]
    if not principais:
        return

    if multa_total > 0:
        base_total = round(sum(item.valor_atualizado for item in principais), 2)
        if base_total <= 0:
            return
        acumulado = 0.0
        for item in principais[:-1]:
            proporcao = item.valor_atualizado / base_total
            item.multa_art_523 = round(multa_total * proporcao, 2)
            acumulado += item.multa_art_523
        principais[-1].multa_art_523 = round(multa_total - acumulado, 2)
        return

    if multa_percentual > 0:
        for item in principais:
            item.multa_art_523 = round(item.valor_atualizado * (multa_percentual / 100), 2)


def parse_projef_report(path: str | Path) -> CaseData:
    source_path = str(Path(path))
    raw_text = extract_text_from_pdf(source_path)
    parsed = split_sections(raw_text)
    resumo = parsed.sections.get("RESUMO DO CALCULO", parsed.raw_text)
    partes = parsed.sections.get("I - PARTES", "")
    totalizacao = parsed.sections.get("II - TOTALIZACAO", "")
    observacoes = parsed.sections.get("OBSERVACOES DIGITADAS PELO USUARIO", "")

    identificador = extract_identifier(parsed.raw_text)

    processo_match = PROCESSO_RE.search(parsed.raw_text)
    nup_match = NUP_RE.search(parsed.raw_text)
    cpf_cnpj_match = CPF_CNPJ_RE.search(parsed.raw_text)
    competencia_match = COMPETENCIA_RE.search(parsed.raw_text)

    devedor = find_label_value(parsed.raw_text, [r"r[ée]u", r"devedor"])
    if devedor:
        devedor = devedor.split("CPF")[0].split("CNPJ")[0].strip(" -")

    report_date = extract_report_date(parsed.raw_text)
    competencia_atualizacao = competencia_from_date(report_date)
    multa_percentual, multa_total = parse_totalizacao_details(totalizacao)
    if multa_percentual <= 0:
        multa_percentual = 10.0
    subdebitos = parse_partes_section(partes, processo_match.group(0) if processo_match else "")
    distribuir_multa_nos_subdebitos(subdebitos, multa_total, multa_percentual)
    honorarios = parse_honorarios(totalizacao)
    if honorarios:
        subdebitos.append(honorarios)

    return CaseData(
        identificador_projef=identificador,
        processo=processo_match.group(0) if processo_match else (nup_match.group(0) if nup_match else ""),
        nup_requerimento=nup_match.group(0) if nup_match else "",
        devedor=devedor,
        cpf_cnpj=cpf_cnpj_match.group(0) if cpf_cnpj_match else "",
        competencia_atualizacao=competencia_atualizacao or (competencia_match.group(0) if competencia_match else ""),
        data_atualizacao=report_date,
        tipo_parcela=infer_tipo_parcela(parsed.raw_text),
        multa_percentual=multa_percentual,
        observacao=observacoes,
        data_limite_resposta=extract_date_from_observacoes(
            observacoes,
            ["data limite para resposta", "prazo para resposta"],
        ),
        data_primeira_parcela=extract_date_from_observacoes(
            observacoes,
            ["entrada", "primeira parcela"],
        ),
        origem_relatorio=source_path,
        sistema_origem="projef",
        relatorios_anexados=[source_path],
        subdebitos=subdebitos,
    )


def detect_report_type(path: str | Path) -> str:
    raw_text = extract_text_from_pdf(path)
    normalized = normalize_anchor_text(raw_text)
    if "PROJEF WEB" in normalized or "RESUMO DO CALCULO" in normalized:
        return "projef"
    tcu_signals = [
        "TRIBUNAL DE CONTAS DA UNIAO",
        "DEMONSTRATIVO DE DEBITO",
        "HISTORICO",
        "DETALHAMENTO DO CALCULO",
        "RESPONSAVEL (EIS)",
        "ORIGEM(ENS) DO DEBITO",
        "SALDO TOTAL",
        "TCU-PLENARIO",
    ]
    tcu_score = sum(1 for signal in tcu_signals if signal in normalized)
    if (
        ("HISTORICO" in normalized and "DETALHAMENTO DO CALCULO" in normalized and tcu_score >= 4)
        or ("DEMONSTRATIVO DE DEBITO" in normalized and "SALDO TOTAL" in normalized and tcu_score >= 3)
        or ("TRIBUNAL DE CONTAS DA UNIAO" in normalized and "HISTORICO" in normalized)
    ):
        return "tcu"
    raise ValueError("Nao consegui identificar se o PDF pertence ao ProjefWeb ou ao TCU.")


def _extract_tcu_header_value(text: str, label: str) -> str:
    pattern = re.compile(rf"{label}\s*[:\-]?\s*(.+)", flags=re.IGNORECASE)
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _extract_tcu_header_value_normalized(text: str, label: str) -> str:
    target = normalize_anchor_text(label)
    for line in text.splitlines():
        normalized_line = normalize_anchor_text(line)
        if target not in normalized_line:
            continue
        parts = line.split(":", 1)
        if len(parts) == 2:
            return parts[1].strip()
    return ""


def _extract_tcu_historico_chunks(page_texts: list[str]) -> str:
    collected: list[str] = []
    capturing = False
    for page_text in page_texts:
        if not page_text:
            continue
        normalized = normalize_anchor_text(page_text)
        if not capturing and "HISTORICO" in normalized:
            capturing = True
            start_idx = normalized.find("HISTORICO")
            page_text = page_text[start_idx:]
        if not capturing:
            continue
        normalized_page = normalize_anchor_text(page_text)
        end_idx = normalized_page.find("DETALHAMENTO DO CALCULO")
        if end_idx >= 0:
            collected.append(page_text[:end_idx])
            break
        collected.append(page_text)
    return "\n".join(collected)


def _parse_tcu_lancamentos(historico_text: str) -> list[TcuLancamento]:
    lancamentos: list[TcuLancamento] = []
    seen: set[tuple[str, str, float]] = set()
    for data_evento, tipo_dc, valor_texto in TCU_HISTORY_ROW_RE.findall(historico_text):
        valor = parse_brl_money(valor_texto)
        key = (data_evento, tipo_dc.upper(), valor)
        if key in seen:
            continue
        seen.add(key)
        lancamentos.append(
            TcuLancamento(
                data_evento=data_evento,
                tipo_dc=tipo_dc.upper(),
                valor=valor,
            )
        )
    return lancamentos


def _extract_tcu_resumo(raw_text: str) -> str:
    normalized = normalize_anchor_text(raw_text)
    resumo_idx = normalized.find("RESUMO")
    if resumo_idx < 0:
        return raw_text
    end_idx = normalized.find("DETALHAMENTO DO CALCULO", resumo_idx)
    if end_idx < 0:
        end_idx = len(raw_text)
    return raw_text[resumo_idx:end_idx]


def _extract_tcu_saldo_debito(resumo_text: str) -> float:
    for line in resumo_text.splitlines():
        normalized_line = normalize_anchor_text(line)
        if "SALDO DO DEBITO" not in normalized_line:
            continue
        money_matches = MONEY_RE.findall(line)
        if money_matches:
            return parse_brl_money(money_matches[-1])
    return 0.0


def _extract_tcu_saldo_total(resumo_text: str) -> float:
    for line in resumo_text.splitlines():
        normalized_line = normalize_anchor_text(line)
        if "SALDO TOTAL" not in normalized_line:
            continue
        money_matches = MONEY_RE.findall(line)
        if money_matches:
            return parse_brl_money(money_matches[-1])
    return 0.0


def _infer_tcu_subdebito_tipo(origem_debito: str) -> str:
    normalized = normalize_anchor_text(origem_debito)
    if "HONORAR" in normalized:
        return "honorarios"
    return "principal"


def parse_tcu_report(path: str | Path) -> CaseData:
    source_path = str(Path(path))
    page_texts = extract_text_by_page(source_path)
    raw_text = "\n".join(page_texts)
    historico_text = _extract_tcu_historico_chunks(page_texts)
    lancamentos = _parse_tcu_lancamentos(historico_text)
    resumo_text = _extract_tcu_resumo(raw_text)
    incluir_juros = any(
        token in normalize_anchor_text(resumo_text) for token in ["JUROS", "SELIC", "SALDO DOS JUROS"]
    )
    processo_match = PROCESSO_RE.search(raw_text)
    nup_match = NUP_RE.search(raw_text)
    cpf_cnpj_match = CPF_CNPJ_RE.search(raw_text)

    responsavel = _extract_tcu_header_value(raw_text, r"Respons[aÃ¡]vel \(eis\)")
    funcao = _extract_tcu_header_value(raw_text, r"Fun[cÃ§][aÃ£]o \(oes\)")
    origem_debito = _extract_tcu_header_value(raw_text, r"Origem\(ens\) do d[eÃ©]bito")
    periodo = _extract_tcu_header_value(raw_text, r"Per[iÃ­]odo")
    data_atualizacao = ""
    if periodo:
        dates = DATE_RE.findall(periodo)
        if len(dates) >= 2:
            data_atualizacao = dates[-1]

    origem_composta = " | ".join(
        part
        for part in [
            processo_match.group(0) if processo_match else "",
            nup_match.group(0) if nup_match else "",
            origem_debito,
            f"Data limite: {extract_date_from_observacoes(raw_text, ['data limite para resposta'])}"
            if extract_date_from_observacoes(raw_text, ["data limite para resposta"])
            else "",
            f"Entrada/1a parcela: {extract_date_from_observacoes(raw_text, ['data da entrada', 'primeira parcela'])}"
            if extract_date_from_observacoes(raw_text, ["data da entrada", "primeira parcela"])
            else "",
        ]
        if part
    )

    return CaseData(
        processo=processo_match.group(0) if processo_match else "",
        nup_requerimento=nup_match.group(0) if nup_match else "",
        devedor=responsavel,
        cpf_cnpj=cpf_cnpj_match.group(0) if cpf_cnpj_match else "",
        data_atualizacao=data_atualizacao,
        tipo_parcela="Debito TCU",
        observacao=origem_debito,
        data_limite_resposta=extract_date_from_observacoes(
            raw_text,
            ["data limite para resposta", "prazo para resposta"],
        ),
        data_primeira_parcela=extract_date_from_observacoes(
            raw_text,
            ["data da entrada", "primeira parcela"],
        ),
        origem_relatorio=source_path,
        sistema_origem="tcu",
        funcao_tcu=funcao,
        origem_debito_tcu=origem_composta or origem_debito,
        incluir_juros_tcu=incluir_juros,
        lancamentos_tcu=lancamentos,
        relatorios_anexados=[source_path],
    )


def parse_tcu_report(path: str | Path) -> CaseData:
    source_path = str(Path(path))
    page_texts = extract_text_by_page(source_path)
    raw_text = "\n".join(page_texts)
    historico_text = _extract_tcu_historico_chunks(page_texts)
    lancamentos = _parse_tcu_lancamentos(historico_text)
    resumo_text = _extract_tcu_resumo(raw_text)
    incluir_juros = any(
        token in normalize_anchor_text(resumo_text)
        for token in ["JUROS", "SELIC", "SALDO DOS JUROS"]
    )
    processo_match = PROCESSO_RE.search(raw_text)
    nup_match = NUP_RE.search(raw_text)
    cpf_cnpj_match = CPF_CNPJ_RE.search(raw_text)

    responsavel = _extract_tcu_header_value_normalized(raw_text, "Responsavel")
    funcao = _extract_tcu_header_value_normalized(raw_text, "Funcao")
    origem_debito = _extract_tcu_header_value_normalized(raw_text, "Origem")
    periodo = _extract_tcu_header_value_normalized(raw_text, "Periodo")
    data_atualizacao = ""
    if periodo:
        dates = DATE_RE.findall(periodo)
        if len(dates) >= 2:
            data_atualizacao = dates[-1]

    competencia_atualizacao = competencia_from_date(data_atualizacao)
    saldo_debito = _extract_tcu_saldo_total(resumo_text) or _extract_tcu_saldo_debito(resumo_text)
    subdebito_tipo = _infer_tcu_subdebito_tipo(origem_debito)
    devedor = responsavel
    if responsavel:
        devedor = CPF_CNPJ_RE.sub("", responsavel).strip(" -")

    origem_composta = " | ".join(
        part
        for part in [
            processo_match.group(0) if processo_match else "",
            nup_match.group(0) if nup_match else "",
            origem_debito,
            f"Data limite: {extract_date_from_observacoes(raw_text, ['data limite para resposta'])}"
            if extract_date_from_observacoes(raw_text, ["data limite para resposta"])
            else "",
            f"Entrada/1a parcela: {extract_date_from_observacoes(raw_text, ['data da entrada', 'primeira parcela'])}"
            if extract_date_from_observacoes(raw_text, ["data da entrada", "primeira parcela"])
            else "",
        ]
        if part
    )

    subdebitos: list[Subdebito] = []
    if saldo_debito > 0:
        subdebitos.append(
            Subdebito(
                tipo=subdebito_tipo,
                descricao=origem_debito or "Debito TCU",
                referencia_origem=origem_composta or origem_debito or "TCU",
                valor_atualizado=saldo_debito,
            )
        )

    return CaseData(
        processo=processo_match.group(0) if processo_match else "",
        nup_requerimento=nup_match.group(0) if nup_match else "",
        devedor=devedor,
        cpf_cnpj=cpf_cnpj_match.group(0) if cpf_cnpj_match else "",
        competencia_atualizacao=competencia_atualizacao,
        data_atualizacao=data_atualizacao,
        tipo_parcela=infer_tipo_parcela(raw_text),
        multa_percentual=10.0,
        observacao=origem_debito,
        data_limite_resposta=extract_date_from_observacoes(
            raw_text,
            ["data limite para resposta", "prazo para resposta"],
        ),
        data_primeira_parcela=extract_date_from_observacoes(
            raw_text,
            ["data da entrada", "primeira parcela"],
        ),
        origem_relatorio=source_path,
        sistema_origem="tcu",
        funcao_tcu=funcao,
        origem_debito_tcu=origem_composta or origem_debito,
        incluir_juros_tcu=incluir_juros,
        lancamentos_tcu=lancamentos,
        relatorios_anexados=[source_path],
        subdebitos=subdebitos,
    )

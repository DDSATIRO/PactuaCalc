from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
import json
import re
from pathlib import Path


CNJ_PATTERN = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")
NUP_PATTERN = re.compile(r"\d{5}\.\d{6}/\d{4}-\d{2}")
UG_GESTAO_PATTERN = re.compile(r"^\d{6}/\d{5}$")
GRU_CR_PATTERN = re.compile(r"^\d{5}-\d$")
CPF_CNPJ_PATTERN = re.compile(
    r"^(?:\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})$"
)


def parse_iso_date(value: str) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


@dataclass
class ProposalRules:
    desconto_sobre_total: bool = True
    aproveitar_bloqueio_como_entrada: bool = True
    calculo_vista: str = "percentual_unico"
    vista_faixas: list[dict[str, float | None]] = field(
        default_factory=lambda: [
            {"limite": 5000.0, "percentual": 20.0},
            {"limite": 10000.0, "percentual": 25.0},
            {"limite": 20000.0, "percentual": 30.0},
            {"limite": None, "percentual": 35.0},
        ]
    )


@dataclass
class Subdebito:
    tipo: str
    descricao: str
    referencia_origem: str
    valor_atualizado: float
    multa_art_523: float = 0.0
    valor_bloqueado: float = 0.0
    ug: str = ""
    gestao: str = "00001"
    gru_cr: str = ""
    editavel_usuario: bool = True

    @property
    def ug_gestao(self) -> str:
        if self.ug and self.gestao:
            return f"{self.ug}/{self.gestao}"
        return ""

    @property
    def valor_total(self) -> float:
        return round(self.valor_atualizado + self.multa_art_523, 2)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.tipo not in {"PRINCIPAL", "HONORÁRIOS", "MULTA (exceto art. 523)"}:
            errors.append("Subdebito com tipo invalido.")
        if self.valor_atualizado < 0:
            errors.append("Valor atualizado do subdebito nao pode ser negativo.")
        if self.multa_art_523 < 0:
            errors.append("Multa do subdebito nao pode ser negativa.")
        if self.valor_bloqueado < 0:
            errors.append("Valor bloqueado do subdebito nao pode ser negativo.")
        if self.valor_bloqueado > self.valor_total:
            errors.append("Valor bloqueado do subdebito nao pode exceder o valor total.")
        if self.ug_gestao and not UG_GESTAO_PATTERN.match(self.ug_gestao):
            errors.append("UG/Gestao deve respeitar o formato 999999/99999.")
        if self.gru_cr and not GRU_CR_PATTERN.match(self.gru_cr):
            errors.append("GRU(CR) deve respeitar o formato 99999-9.")
        return errors


@dataclass
class TcuLancamento:
    data_evento: str
    valor: float
    tipo_dc: str = "D"

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not parse_iso_date(self.data_evento):
            errors.append("Data do lancamento TCU invalida.")
        if self.tipo_dc not in {"D", "C"}:
            errors.append("Tipo do lancamento TCU deve ser D ou C.")
        if self.valor < 0:
            errors.append("Valor do lancamento TCU nao pode ser negativo.")
        return errors


@dataclass
class CaseData:
    identificador_projef: str = ""
    processo: str = ""
    nup_requerimento: str = ""
    devedor: str = ""
    cpf_cnpj: str = ""
    competencia_atualizacao: str = ""
    data_atualizacao: str = ""
    tipo_parcela: str = "VARIAVEL (POS-FIXADO)"
    multa_percentual: float = 10.0
    observacao: str = ""
    condicoes_adicionais: str = ""
    data_limite_resposta: str = ""
    data_primeira_parcela: str = ""
    valor_bloqueado_geral: float = 0.0
    origem_relatorio: str = ""
    sistema_origem: str = "projef"
    funcao_tcu: str = ""
    origem_debito_tcu: str = ""
    incluir_juros_tcu: bool = False
    lancamentos_tcu: list[TcuLancamento] = field(default_factory=list)
    relatorios_anexados: list[str] = field(default_factory=list)
    proposal_rules: ProposalRules = field(default_factory=ProposalRules)
    subdebitos: list[Subdebito] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["regras_proposta"] = payload.pop("proposal_rules")
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> "CaseData":
        rules_data = data.get("regras_proposta") or data.get("proposal_rules") or {}
        subdebitos = [Subdebito(**item) for item in data.get("subdebitos", [])]
        lancamentos_tcu = [
            TcuLancamento(**item) for item in data.get("lancamentos_tcu", [])
        ]
        return cls(
            identificador_projef=data.get("identificador_projef", ""),
            processo=data.get("processo", ""),
            nup_requerimento=data.get("nup_requerimento", ""),
            devedor=data.get("devedor", ""),
            cpf_cnpj=data.get("cpf_cnpj", ""),
            competencia_atualizacao=data.get("competencia_atualizacao", ""),
            data_atualizacao=data.get("data_atualizacao", ""),
            tipo_parcela=data.get("tipo_parcela", ""),
            multa_percentual=float(data.get("multa_percentual", 0.0) or 0.0),
            observacao=data.get("observacao", ""),
            condicoes_adicionais=data.get("condicoes_adicionais", ""),
            data_limite_resposta=data.get("data_limite_resposta", ""),
            data_primeira_parcela=data.get("data_primeira_parcela", ""),
            valor_bloqueado_geral=float(data.get("valor_bloqueado_geral", 0.0) or 0.0),
            origem_relatorio=data.get("origem_relatorio", ""),
            sistema_origem=data.get("sistema_origem", "projef"),
            funcao_tcu=data.get("funcao_tcu", ""),
            origem_debito_tcu=data.get("origem_debito_tcu", ""),
            incluir_juros_tcu=bool(data.get("incluir_juros_tcu", False)),
            lancamentos_tcu=lancamentos_tcu,
            relatorios_anexados=list(data.get("relatorios_anexados", [])),
            proposal_rules=ProposalRules(**rules_data),
            subdebitos=subdebitos,
        )

    def save_json(self, path: str | Path) -> None:
        target = Path(path)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load_json(cls, path: str | Path) -> "CaseData":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(payload)

    def validate(self, strict_proposal: bool | None = None) -> list[str]:
        errors: list[str] = []
        today = date.today()
        if strict_proposal is None:
            strict_proposal = bool(self.subdebitos)

        if strict_proposal:
            if not self.processo:
                errors.append("Processo e obrigatorio.")
            elif not (CNJ_PATTERN.fullmatch(self.processo) or NUP_PATTERN.fullmatch(self.processo)):
                errors.append("Processo deve respeitar formato CNJ ou NUP.")
            if not self.nup_requerimento:
                errors.append("NUP do requerimento e obrigatorio.")
            elif not NUP_PATTERN.fullmatch(self.nup_requerimento):
                errors.append("NUP do requerimento deve respeitar o padrao administrativo.")
            if not self.devedor:
                errors.append("Devedor e obrigatorio.")
            if not self.cpf_cnpj:
                errors.append("CPF/CNPJ e obrigatorio.")
            elif not CPF_CNPJ_PATTERN.fullmatch(self.cpf_cnpj):
                errors.append("CPF/CNPJ deve estar em formato valido.")
            if not self.data_atualizacao:
                errors.append("Data de atualizacao e obrigatoria.")
            elif not parse_iso_date(self.data_atualizacao):
                errors.append("Data de atualizacao deve estar em formato YYYY-MM-DD ou DD/MM/YYYY.")
            if not self.tipo_parcela:
                errors.append("Tipo de parcela e obrigatorio.")
            if self.multa_percentual < 0:
                errors.append("Multa (%) nao pode ser negativa.")
            if self.multa_percentual > 20.0:
                errors.append("Multa (%) nao pode exceder o limite maximo de 20,00.")
            if not self.data_limite_resposta:
                errors.append("Data limite para resposta e obrigatoria.")
            if not self.data_primeira_parcela:
                errors.append("Data da entrada/primeira parcela e obrigatoria.")
        else:
            if self.processo and not (
                CNJ_PATTERN.fullmatch(self.processo) or NUP_PATTERN.fullmatch(self.processo)
            ):
                errors.append("Processo deve respeitar formato CNJ ou NUP.")
            if self.cpf_cnpj and not CPF_CNPJ_PATTERN.fullmatch(self.cpf_cnpj):
                errors.append("CPF/CNPJ deve estar em formato valido.")
            if self.data_atualizacao and not parse_iso_date(self.data_atualizacao):
                errors.append("Data de atualizacao deve estar em formato YYYY-MM-DD ou DD/MM/YYYY.")
            if self.multa_percentual < 0:
                errors.append("Multa (%) nao pode ser negativa.")
            if self.multa_percentual > 20.0:
                errors.append("Multa (%) nao pode exceder o limite maximo de 20,00.")

        data_limite = parse_iso_date(self.data_limite_resposta)
        data_primeira = parse_iso_date(self.data_primeira_parcela)
        if self.data_limite_resposta and not data_limite:
            errors.append("Data limite para resposta invalida.")
        if self.data_primeira_parcela and not data_primeira:
            errors.append("Data da entrada/primeira parcela invalida.")
        if data_limite and data_limite < today:
            errors.append("Data limite para resposta nao pode ser anterior a data corrente.")
        if data_primeira and data_primeira < today:
            errors.append("Data da entrada/primeira parcela nao pode ser anterior a data corrente.")
        if data_limite and data_primeira and data_limite > data_primeira:
            errors.append("Data limite para resposta nao pode ser posterior a data da entrada/primeira parcela.")

        if self.valor_bloqueado_geral < 0:
            errors.append("Valor bloqueado geral nao pode ser negativo.")
        total_elegivel = round(sum(item.valor_total for item in self.subdebitos), 2)
        if self.valor_bloqueado_geral > total_elegivel:
            errors.append("Valor bloqueado geral nao pode exceder a soma elegivel dos subdebitos.")

        for index, item in enumerate(self.subdebitos, start=1):
            for error in item.validate():
                errors.append(f"Subdebito {index}: {error}")
        for index, item in enumerate(self.lancamentos_tcu, start=1):
            for error in item.validate():
                errors.append(f"Lancamento TCU {index}: {error}")
        return errors

from __future__ import annotations

from dataclasses import fields
import calendar
from datetime import date, datetime
import json
from pathlib import Path
import re
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

from pactuacalc.formatting import format_currency_br, format_decimal_br, format_percent_br, parse_decimal_input
from pactuacalc.models import CaseData, ProposalSelection, Subdebito, normalized_text, parse_iso_date
from pactuacalc.parser import detect_report_type, parse_projef_report, parse_tcu_report
from pactuacalc.projefweb import ProjefWebAutomationError, atualizar_relatorio_projef, competencia_esta_defasada
from pactuacalc.proposals import (
    MODALIDADES,
    OPTIONAL_ENTRY_CODES,
    create_proposal_pdf,
    parcela_limites,
    validate_proposal_selection,
)
from pactuacalc.services import (
    MergeConflict,
    consolidated_description_key,
    consolidar_por_chave_arrecadatoria,
    distribuir_valor_bloqueado,
    merge_case_data,
    replace_tcu_case_data,
    total_bloqueado_efetivo,
)
from pactuacalc.tcuweb import TcuAutomationError, atualizar_relatorio_tcu
from pactuacalc.version_check import APP_VERSION


CASE_FIELDS = [
    ("processo", "Processo"),
    ("devedor", "Devedor"),
    ("cpf_cnpj", "CPF/CNPJ"),
    ("nup_requerimento", "NUP do requerimento"),
    ("competencia_atualizacao", "Competencia"),
    ("data_atualizacao", "Data de atualizacao"),
    ("tipo_parcela", "Tipo de parcela"),
    ("data_limite_resposta", "Data limite resposta"),
    ("data_primeira_parcela", "Data da Entrada/Primeira Parcela"),
    ("multa_percentual", "Multa (%)"),
    ("valor_bloqueado_geral", "Valor bloqueado geral"),
]

SUBDEBIT_COLUMNS = (
    "tipo",
    "descricao",
    "ug_gestao",
    "gru_cr",
    "valor_atualizado",
    "multa_art_523",
    "valor_bloqueado",
)
FIELD_LABELS = {
    **{name: label for name, label in CASE_FIELDS},
    "funcao_tcu": "Funcao TCU",
    "origem_debito_tcu": "Origem do debito TCU",
    "multa_percentual": "Multa (%)",
    "valor_bloqueado_geral": "Valor bloqueado geral",
}

FIELD_BG = "#fff8e6"
TOP_FIELD_BG = "#ffe4e6"
MISSING_BG = "#fee2e2"
BATCH_BG = "#dedbd2"
APP_BG = "#f4f6f8"
HELP_FG = "#64748b"
RESET_DEFAULTS_FG = "#b91c1c"
RESET_DEFAULTS_DISABLED_FG = "#111827"
RESET_DEFAULTS_BUTTON_BG = "SystemButtonFace"
RESET_DEFAULTS_TEXT = "Valores Padrão alterados. Clique aqui para restaurá-los."

BUTTON_TOOLTIPS = {
    "create_from_report": "Crie a proposta a partir de um demonstrativo anterior do TCU ou do PROJEF Web.",
    "add_report": "Adicione outros relatórios TCU ou PROJEF Web ao caso atual.",
    "open_json": "Abra um arquivo com proposta salva anteriormente.",
    "save_json": "Salve a proposta atual em arquivo JSON para continuar depois.",
}

CASE_FIELD_TOOLTIPS = {
    "processo": "Indique o processo judicial. Se o caso for administrativo, informe o NUP.",
    "nup_requerimento": "Indique o NUP do requerimento administrativo.",
    "cpf_cnpj": "Inclua pontos, barra e traços. Exemplos: 000.000.000-00 ou 00.000.000/0000-00.",
    "competencia_atualizacao": "Indique o mês e o ano da proposta, no formato mm/aaaa.",
    "data_atualizacao": "Informe a data de atualização da dívida.",
    "tipo_parcela": (
        "Informe a modalidade do parcelamento: fixa (pré-fixada) ou variável (pós-fixada). "
        "Na parcela fixa, os valores são calculados aproximadamente; se houver divergência, "
        "devem prevalecer os valores do PARCELA PGU."
    ),
    "data_limite_resposta": (
        "Indique uma data limite para o devedor responder. Sugere-se conceder de 5 a 10 dias "
        "para a resposta."
    ),
    "data_primeira_parcela": (
        "Nas opções com entrada, esta será a data da entrada; a primeira parcela ficará, por padrão, "
        "no final do mês seguinte. Nas opções sem entrada, esta será a data da primeira parcela. "
        "Como orientação prática: se a resposta vencer até o dia 15, use vencimento no próprio mês "
        "do acordo; se vencer depois do dia 15, considere vencimento até o dia 10 do mês seguinte."
    ),
    "multa_percentual": "Indique o percentual de multa para eventual descumprimento futuro do acordo.",
    "valor_bloqueado_geral": (
        "Indique o valor de bloqueio judicial se quiser distribuí-lo proporcionalmente entre os "
        "subdébitos. Para desfazer uma distribuição anterior, informe zero e clique novamente em "
        "Distribuir Bloqueio; os valores distribuídos em cada subdébito serão zerados."
    ),
}

BATCH_CODES_TOOLTIP = (
    "Escolha UG/Gestão e GRU(CR) nas listas suspensas. Os códigos serão inseridos nos subdébitos "
    "selecionados; se houver mais de um subdébito com a mesma chave, eles serão consolidados no "
    "quadro de Débitos consolidados."
)

SUMMARY_TOOLTIP = (
    "Cada débito consolidado deverá corresponder a uma GRU unificada, reunindo os subdébitos "
    "com a mesma UG/Gestão e GRU(CR)."
)

SUBDEBIT_EDITOR_TOOLTIP = (
    "Selecione um subdébito na tabela para alterar ou excluir seus dados. Para adicionar um "
    "subdébito manualmente, clique em Adicionar e depois preencha os dados respectivos."
)


def sort_ug_codes(codes: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        codes,
        key=lambda item: (
            normalized_text(item.get("descricao", "")),
            item.get("ug", ""),
            item.get("gestao", ""),
        ),
    )


def sort_gru_codes(codes: list[dict[str, str]]) -> list[dict[str, str]]:
    def code_number(item: dict[str, str]) -> tuple[int, str]:
        code = item.get("codigo", "")
        digits = re.sub(r"\D", "", code)
        return int(digits or "0"), code

    return sorted(codes, key=code_number)


class HoverTooltip:
    def __init__(self, widget: tk.Widget, text: str, wraplength: int = 360) -> None:
        self.widget = widget
        self.text = text
        self.wraplength = wraplength
        self.window: tk.Toplevel | None = None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def show(self, event: tk.Event | None = None) -> None:
        if self.window or not self.text:
            return
        x = (getattr(event, "x_root", 0) or self.widget.winfo_rootx()) + 14
        y = (getattr(event, "y_root", 0) or self.widget.winfo_rooty()) + 18
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self.window,
            text=self.text,
            justify="left",
            wraplength=self.wraplength,
            bg="#fffdf4",
            fg="#1f2937",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=5,
            font=("Segoe UI", 9),
        )
        label.pack()

    def hide(self, _event: tk.Event | None = None) -> None:
        if self.window:
            self.window.destroy()
            self.window = None


class MainWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PactuaCalc")
        self.root.geometry("1280x780")
        self.root.minsize(1080, 680)
        self.root.configure(bg="#f4f6f8")
        # Icone da janela
        try:
            import sys
            _base = getattr(sys, '_MEIPASS', None) or Path(__file__).parent.parent
            _ico = Path(_base) / "PactuaCalc.ico"
            if _ico.exists():
                self.root.iconbitmap(str(_ico))
        except Exception:
            pass
        self.case_data = CaseData()
        self._saved_case_signature = ""
        self.selected_subdebito_indices: list[int] = []

        self.case_vars: dict[str, tk.StringVar] = {
            name: tk.StringVar() for name, _ in CASE_FIELDS
        }
        self.subdebito_vars: dict[str, tk.StringVar] = {
            field.name: tk.StringVar() for field in fields(Subdebito) if field.init
        }
        self.batch_vars = {
            "ug": tk.StringVar(),
            "gestao": tk.StringVar(value="00001"),
            "gru_cr": tk.StringVar(),
        }
        self.total_geral_var = tk.StringVar(value="R$ 0,00")
        self.summary_description_var = tk.StringVar()
        self.subdebito_count_var = tk.StringVar()
        self.selected_summary_key: tuple[str, str] | None = None
        self.ug_codes: list[dict[str, str]] = []
        self.gru_codes: list[dict[str, str]] = []
        self.ug_by_code: dict[str, dict[str, str]] = {}
        self.ug_display_to_code: dict[str, str] = {}
        self.gru_display_to_code: dict[str, str] = {}
        self.ug_comboboxes: list[ttk.Combobox] = []
        self.gru_comboboxes: list[ttk.Combobox] = []

        self.logo_image: tk.PhotoImage | None = None
        self._load_revenue_codes()
        self._configure_styles()
        self._build_layout()
        self.refresh_all()
        self._mark_case_clean()
        self.root.protocol("WM_DELETE_WINDOW", self.close_app)

    def _apply_case_defaults(self) -> None:
        if self.case_data.data_atualizacao and not self.case_data.competencia_atualizacao:
            parsed = parse_iso_date(self.case_data.data_atualizacao)
            if parsed:
                self.case_data.competencia_atualizacao = parsed.strftime("%m/%Y")
        if not self.case_data.tipo_parcela:
            self.case_data.tipo_parcela = "VARIAVEL (POS-FIXADO)"
        if self.case_data.multa_percentual <= 0 and not self.case_data.subdebitos:
            self.case_data.multa_percentual = 10.0

    def show_about(self) -> None:
        license_path = Path(__file__).parent.parent / "THIRD_PARTY_LICENSES.txt"
        license_text = "Arquivo de licenças não encontrado."
        if license_path.exists():
            license_text = license_path.read_text(encoding="utf-8")

        about_win = tk.Toplevel(self.root)
        about_win.title("Sobre o PactuaCalc")
        about_win.geometry("600x450")
        try:
            import sys
            _base = getattr(sys, '_MEIPASS', None) or Path(__file__).parent.parent
            _ico = Path(_base) / "PactuaCalc.ico"
            if _ico.exists():
                about_win.iconbitmap(str(_ico))
        except Exception:
            pass

        header = (
            "PactuaCalc\n\n"
            "Copyright (c) 2026 ddsatiro\n"
            "Contato: ddsatiro@gmail.com\n\n"
            "Este software e de codigo aberto (Licenca MIT).\n"
            "Licencas de terceiros:\n"
            "--------------------------------------------------\n"
        )

        txt = tk.Text(about_win, wrap="word", padx=10, pady=10)
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", header + license_text)
        txt.configure(state="disabled")

    def show_help(self) -> None:
        help_path = self._asset_path("INSTRUCOES_DE_USO.md")
        if not help_path.exists():
            help_path = Path(__file__).parent.parent / "INSTRUCOES_DE_USO.md"
        try:
            help_text = help_path.read_text(encoding="utf-8")
        except OSError:
            help_text = "Arquivo de instrucoes de uso nao encontrado."

        help_win = tk.Toplevel(self.root)
        help_win.title("Ajuda - PactuaCalc")
        help_win.geometry("860x680")
        try:
            import sys
            _base = getattr(sys, '_MEIPASS', None) or Path(__file__).parent.parent
            _ico = Path(_base) / "PactuaCalc.ico"
            if _ico.exists():
                help_win.iconbitmap(str(_ico))
        except Exception:
            pass

        frame = ttk.Frame(help_win, padding=8)
        frame.pack(fill="both", expand=True)
        text = tk.Text(frame, wrap="word", padx=12, pady=12, font=("Segoe UI", 10))
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        text.insert("1.0", help_text)
        text.configure(state="disabled")

    def _asset_path(self, filename: str) -> Path:
        try:
            import sys
            base = getattr(sys, "_MEIPASS", None) or Path(__file__).parent.parent
        except Exception:
            base = Path(__file__).parent.parent
        return Path(base) / filename

    def _load_revenue_codes(self) -> None:
        path = self._asset_path("pactuacalc/codigos_arrecadacao.json")
        if not path.exists():
            path = Path(__file__).with_name("codigos_arrecadacao.json")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {"ugs": [], "grus": []}

        self.ug_codes = sort_ug_codes(list(payload.get("ugs", [])))
        self.gru_codes = sort_gru_codes(list(payload.get("grus", [])))
        self.ug_by_code = {item["ug"]: item for item in self.ug_codes if item.get("ug")}
        self.ug_display_to_code = {
            self._ug_display(item): item["ug"] for item in self.ug_codes if item.get("ug")
        }
        self.gru_display_to_code = {
            self._gru_display(item): item["codigo"] for item in self.gru_codes if item.get("codigo")
        }

    def _ug_display(self, item: dict[str, str]) -> str:
        return f"{item.get('ug', '')}/{item.get('gestao', '')} - {item.get('descricao', '')}"

    def _gru_display(self, item: dict[str, str]) -> str:
        return f"{item.get('codigo', '')} - {item.get('descricao', '')}"

    def _filter_code_values(self, values: list[str], query: str) -> list[str]:
        terms = query.lower().replace("/", " ").replace("-", " ").split()
        if not terms:
            return values
        return [value for value in values if all(term in value.lower() for term in terms)]

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        base_bg = "#f4f6f8"
        panel_bg = "#ffffff"
        text = "#1f2937"
        muted = "#5f6b7a"
        primary = "#0f766e"
        primary_hover = "#0d625c"

        style.configure(".", font=("Segoe UI", 9))
        style.configure("App.TFrame", background=base_bg)
        style.configure("Panel.TFrame", background=panel_bg)
        style.configure("Toolbar.TFrame", background="#e8f3f1")
        style.configure("Header.TFrame", background="#e8f3f1")
        style.configure("App.TLabel", background=base_bg, foreground=text)
        style.configure("Panel.TLabel", background=panel_bg, foreground=text)
        style.configure("Muted.TLabel", background=panel_bg, foreground=muted)
        style.configure("Brand.TLabel", background="#e8f3f1", foreground="#0f172a", font=("Segoe UI", 15, "bold"))
        style.configure("Subtitle.TLabel", background="#e8f3f1", foreground="#475569", font=("Segoe UI", 8))
        style.configure("Logo.TLabel", background="#e8f3f1")
        style.configure("Status.TLabel", background="#e8f3f1", foreground="#334155")
        style.configure("Help.TLabel", background=base_bg, foreground=HELP_FG, font=("Segoe UI", 8, "bold"))
        style.configure("TLabel", background=base_bg, foreground=text)
        style.configure("TLabelframe", background=base_bg, bordercolor="#d7dee8", relief="solid")
        style.configure("TLabelframe.Label", background=base_bg, foreground="#1f2937", font=("Segoe UI", 9, "bold"))
        style.configure("TEntry", fieldbackground=FIELD_BG, bordercolor="#cbd5e1", lightcolor="#cbd5e1", darkcolor="#cbd5e1", padding=2)
        style.configure("TCombobox", fieldbackground=FIELD_BG, background=FIELD_BG, bordercolor="#cbd5e1", arrowsize=13, padding=2)
        style.configure("Pink.TCombobox", fieldbackground=TOP_FIELD_BG, background=TOP_FIELD_BG, bordercolor="#cbd5e1", arrowsize=13, padding=2)
        style.map("Pink.TCombobox", fieldbackground=[("readonly", TOP_FIELD_BG)], selectbackground=[("readonly", TOP_FIELD_BG)])
        style.configure("Treeview", rowheight=24, bordercolor="#d7dee8", fieldbackground="#ffffff", background="#ffffff", foreground=text)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#edf2f7", foreground="#334155")
        style.configure("TButton", padding=(8, 4))
        style.configure("Accent.TButton", background=primary, foreground="#ffffff", bordercolor=primary)
        style.map("Accent.TButton", background=[("active", primary_hover), ("pressed", primary_hover)])
        style.configure("Success.TButton", background="#15803d", foreground="#ffffff", bordercolor="#15803d", font=("Segoe UI", 10, "bold"), padding=(12, 7))
        style.map("Success.TButton", background=[("active", "#166534"), ("pressed", "#166534")])
        style.configure("Soft.TButton", background="#fff7db", foreground="#493a12", bordercolor="#f1d98c")
        style.map("Soft.TButton", background=[("active", "#ffefb3"), ("pressed", "#ffefb3")])

    def _attach_tooltip(self, widget: tk.Widget, text: str) -> None:
        tooltip = HoverTooltip(widget, text)
        setattr(widget, "_pactuacalc_tooltip", tooltip)

    def _help_icon(self, parent: tk.Widget, text: str, background: str = APP_BG) -> tk.Label:
        icon = tk.Label(
            parent,
            text="?",
            bg=background,
            fg=HELP_FG,
            cursor="question_arrow",
            font=("Segoe UI", 8, "bold"),
            padx=2,
        )
        self._attach_tooltip(icon, text)
        return icon

    def _label_with_help(
        self,
        parent: tk.Widget,
        text: str,
        tooltip: str,
        row: int,
        column: int,
        *,
        columnspan: int = 1,
        sticky: str = "w",
        padx: int | tuple[int, int] = 4,
        pady: int | tuple[int, int] = 2,
        background: str = APP_BG,
        font: tuple[str, int] | tuple[str, int, str] | None = None,
    ) -> tk.Frame:
        frame = tk.Frame(parent, bg=background)
        tk.Label(frame, text=text, bg=background, fg="#1f2937", font=font or ("Segoe UI", 9)).pack(side="left")
        self._help_icon(frame, tooltip, background=background).pack(side="left", padx=(3, 0))
        frame.grid(row=row, column=column, columnspan=columnspan, sticky=sticky, padx=padx, pady=pady)
        return frame

    def _section_label_with_help(self, parent: tk.Widget, text: str, tooltip: str) -> tk.Frame:
        frame = tk.Frame(parent, bg=APP_BG)
        tk.Label(frame, text=text, bg=APP_BG, fg="#1f2937", font=("Segoe UI", 9, "bold")).pack(side="left")
        self._help_icon(frame, tooltip, background=APP_BG).pack(side="left", padx=(4, 0))
        return frame

    def _load_logo(self) -> tk.PhotoImage | None:
        logo_path = self._asset_path("PactuaCalc.png")
        if not logo_path.exists():
            return None
        try:
            image = tk.PhotoImage(file=str(logo_path))
            max_width = 92
            max_height = 92
            factor = max(
                1,
                int(max(image.width() / max_width, image.height() / max_height) + 0.999),
            )
            if factor > 1:
                image = image.subsample(factor, factor)
            return image
        except tk.TclError:
            return None

    def _bind_mousewheel(self, widget: tk.Widget, canvas: tk.Canvas) -> None:
        def on_mousewheel(event: tk.Event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def bind_wheel(_event: tk.Event) -> None:
            widget.bind_all("<MouseWheel>", on_mousewheel)

        def unbind_wheel(_event: tk.Event) -> None:
            widget.unbind_all("<MouseWheel>")

        widget.bind("<Enter>", bind_wheel)
        widget.bind("<Leave>", unbind_wheel)

    def _make_filter_combobox(
        self,
        parent: tk.Widget,
        variable: tk.StringVar,
        values: list[str],
        display_to_code: dict[str, str],
        width: int,
        on_selected=None,
    ) -> ttk.Combobox:
        combo = ttk.Combobox(parent, textvariable=variable, values=values, width=width, state="normal")

        def refresh_values(_event=None) -> None:
            combo.configure(values=self._filter_code_values(values, variable.get()))

        def apply_selection(_event=None) -> None:
            selected = variable.get()
            code = display_to_code.get(selected)
            if code:
                variable.set(code)
            if on_selected:
                on_selected()

        combo.bind("<KeyRelease>", refresh_values)
        combo.bind("<FocusIn>", refresh_values)
        combo.bind("<<ComboboxSelected>>", lambda event: self.root.after_idle(apply_selection))
        combo.bind("<Return>", apply_selection)
        combo.bind("<FocusOut>", apply_selection)
        return combo

    def _sync_gestao_from_subdebito_ug(self) -> None:
        ug = self.subdebito_vars["ug"].get().strip()
        item = self.ug_by_code.get(ug)
        if item:
            self.subdebito_vars["gestao"].set(item.get("gestao", "00001") or "00001")

    def _sync_gestao_from_batch_ug(self) -> None:
        ug = self.batch_vars["ug"].get().strip()
        item = self.ug_by_code.get(ug)
        if item:
            self.batch_vars["gestao"].set(item.get("gestao", "00001") or "00001")

    def _normalize_ug_value(self, value: str) -> tuple[str, str]:
        raw = value.strip()
        code = self.ug_display_to_code.get(raw, raw.split("/", 1)[0].split(" - ", 1)[0].strip())
        item = self.ug_by_code.get(code)
        if item:
            return code, item.get("gestao", "00001") or "00001"
        return code, "00001"

    def _normalize_gru_value(self, value: str) -> str:
        raw = value.strip()
        return self.gru_display_to_code.get(raw, raw.split(" - ", 1)[0].strip())

    def _build_layout(self) -> None:
        self.status_var = tk.StringVar()
        top = ttk.Frame(self.root, style="Header.TFrame", padding=(14, 2, 14, 2))
        top.pack(fill="x")
        top.columnconfigure(1, weight=1)

        self.logo_image = self._load_logo()
        if self.logo_image:
            ttk.Label(top, image=self.logo_image, style="Logo.TLabel").grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 10))

        ttk.Label(top, text="PactuaCalc", style="Brand.TLabel").grid(row=0, column=1, sticky="sw")
        ttk.Label(
            top,
            text=f"Cálculos e propostas para negociação de dívidas — Versão {APP_VERSION} (favor verificar cálculos e regras e, se for o caso, contatar o desenvolvedor)",
            style="Subtitle.TLabel",
        ).grid(row=1, column=1, sticky="nw", pady=(1, 0))

        buttons = ttk.Frame(top, style="Header.TFrame")
        buttons.grid(row=0, column=2, rowspan=2, sticky="e", padx=(18, 0))
        for col in range(7):
            buttons.columnconfigure(col, weight=0)
        create_btn = ttk.Button(
            buttons,
            text="Criar a partir de relatorio",
            command=self.create_from_any_pdf,
            style="Soft.TButton",
        )
        create_btn.grid(row=0, column=0, padx=(0, 8), sticky="e")
        self._attach_tooltip(create_btn, BUTTON_TOOLTIPS["create_from_report"])
        add_report_btn = ttk.Button(
            buttons,
            text="Adicionar relatorio",
            command=self.add_other_report,
            style="Soft.TButton",
        )
        add_report_btn.grid(row=0, column=1, padx=(0, 8), sticky="e")
        self._attach_tooltip(add_report_btn, BUTTON_TOOLTIPS["add_report"])
        open_json_btn = ttk.Button(
            buttons,
            text="Abrir Json",
            command=self.load_json,
        )
        open_json_btn.grid(row=0, column=2, padx=(0, 8), sticky="e")
        self._attach_tooltip(open_json_btn, BUTTON_TOOLTIPS["open_json"])
        save_json_btn = ttk.Button(buttons, text="Salvar Json", command=self.save_json)
        save_json_btn.grid(row=0, column=3, padx=(0, 8), sticky="e")
        self._attach_tooltip(save_json_btn, BUTTON_TOOLTIPS["save_json"])
        ttk.Button(buttons, text="Sobre", command=self.show_about).grid(row=0, column=4, padx=(0, 8), sticky="e")
        ttk.Button(buttons, text="Ajuda", command=self.show_help).grid(row=0, column=5, padx=(0, 8), sticky="e")
        ttk.Button(buttons, text="Sair", command=self.close_app).grid(row=0, column=6, sticky="e")
        ttk.Label(buttons, textvariable=self.status_var, style="Status.TLabel").grid(
            row=1, column=0, columnspan=7, sticky="e", pady=(4, 0)
        )

        main = ttk.Frame(self.root, style="App.TFrame", padding=(16, 6, 16, 16))
        main.pack(fill="both", expand=True)

        header_frame = ttk.Labelframe(main, text="Dados Gerais", padding=(8, 6))
        header_frame.pack(fill="x", side="top")
        self._build_header(header_frame)

        center = ttk.Panedwindow(main, orient=tk.HORIZONTAL)
        center.pack(fill="both", expand=True, side="top", pady=(6, 0))

        subdebito_label = tk.Frame(center, bg="#f4f6f8")
        tk.Label(
            subdebito_label,
            text="Subdébitos - Insira cada parte do débito, conforme cálculos ",
            bg="#f4f6f8",
            fg="#1f2937",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left")
        tk.Label(
            subdebito_label,
            text="(o subdébito em vermelho, é considerado honorários e terá desconto conforme subdébitos principais, salvo se exclusivo).",
            bg="#f4f6f8",
            fg="#b91c1c",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left")
        grid_frame = ttk.Labelframe(center, labelwidget=subdebito_label, padding=(8, 6))
        center.add(grid_frame, weight=4)
        self._build_subdebito_grid(grid_frame)

        edit_label = self._section_label_with_help(center, "Edicao do subdebito selecionado", SUBDEBIT_EDITOR_TOOLTIP)
        edit_frame = ttk.Labelframe(center, labelwidget=edit_label, padding=(8, 6))
        center.add(edit_frame, weight=2)
        self._build_subdebito_editor(edit_frame)

    def _update_notes_bg(self, event=None) -> None:
        self.notes_text.configure(bg=TOP_FIELD_BG)

    def _default_first_installment_after_entry(self) -> str:
        data_entrada = parse_iso_date(self.case_data.data_primeira_parcela)
        if not data_entrada:
            return ""
        month = data_entrada.month + 1
        year = data_entrada.year
        if month > 12:
            month = 1
            year += 1
        last_day = calendar.monthrange(year, month)[1]
        return f"{last_day:02d}/{month:02d}/{year}"

    def _build_header(self, parent: ttk.Labelframe) -> None:
        mandatory_fields = {
            "processo", "devedor", "cpf_cnpj", "data_atualizacao",
            "tipo_parcela", "data_limite_resposta", "data_primeira_parcela", "nup_requerimento"
        }

        field_layout = {
            "processo": {"row": 0, "col": 0, "colspan": 1},
            "devedor": {"row": 0, "col": 2, "colspan": 3},
            "cpf_cnpj": {"row": 0, "col": 6, "colspan": 1},
            "nup_requerimento": {"row": 1, "col": 0, "colspan": 1},
            "competencia_atualizacao": {"row": 1, "col": 2, "colspan": 1},
            "data_atualizacao": {"row": 1, "col": 4, "colspan": 1},
            "tipo_parcela": {"row": 1, "col": 6, "colspan": 1},
            "data_limite_resposta": {"row": 2, "col": 0, "colspan": 1},
            "data_primeira_parcela": {"row": 2, "col": 2, "colspan": 1},
            "multa_percentual": {"row": 2, "col": 4, "colspan": 1},
            "valor_bloqueado_geral": {"row": 2, "col": 6, "colspan": 1},
        }

        for field_name, label in CASE_FIELDS:
            pos = field_layout.get(field_name)
            if not pos:
                continue
            
            row = pos["row"]
            col = pos["col"]
            colspan = pos["colspan"]
            
            lbl_text = f"{label}*" if field_name in mandatory_fields else label
            tooltip = CASE_FIELD_TOOLTIPS.get(field_name)
            if tooltip:
                self._label_with_help(parent, lbl_text, tooltip, row, col)
            else:
                ttk.Label(parent, text=lbl_text).grid(row=row, column=col, sticky="w", padx=4, pady=2)
            
            if field_name == "tipo_parcela":
                entry = ttk.Combobox(
                    parent,
                    textvariable=self.case_vars[field_name],
                    values=["VARIAVEL (POS-FIXADO)", "FIXO (PREFIXADO)"],
                    state="readonly",
                    width=31,
                    style="Pink.TCombobox",
                )
            else:
                entry = tk.Entry(
                    parent,
                    textvariable=self.case_vars[field_name],
                    width=28,
                    relief="solid",
                    bd=1,
                    highlightthickness=1,
                    highlightbackground="#cbd5e1",
                    highlightcolor="#0f766e",
                    bg=TOP_FIELD_BG,
                )
            
            entry.grid(
                row=row,
                column=col + 1,
                columnspan=colspan,
                sticky="ew",
                padx=4,
                pady=2,
            )
            
            if field_name == "competencia_atualizacao":
                entry.configure(state="readonly")
                entry.configure(readonlybackground=TOP_FIELD_BG)
            
            if field_name in mandatory_fields:
                def on_change(*args, widget=entry, var=self.case_vars[field_name]):
                    if type(widget) is tk.Entry:
                        if not var.get().strip():
                            widget.configure(bg=MISSING_BG)
                        else:
                            widget.configure(bg=TOP_FIELD_BG)
                self.case_vars[field_name].trace_add("write", on_change)
                on_change()

            if field_name == "valor_bloqueado_geral":
                entry.bind("<FocusOut>", self.on_bloco_geral_focus_out)
                entry.bind("<FocusIn>", self.on_select_all_entry)
                entry.bind("<ButtonRelease-1>", self.on_select_all_entry)
                distribute_btn = ttk.Button(
                    parent,
                    text="Distribuir Bloqueio",
                    command=self.apply_general_block,
                )
                distribute_btn.grid(row=row, column=8, sticky="ew", padx=(4, 0), pady=2)
                self._attach_tooltip(distribute_btn, CASE_FIELD_TOOLTIPS["valor_bloqueado_geral"])

        for _col in range(8):
            parent.columnconfigure(_col, weight=1)
        parent.columnconfigure(3, weight=1)
        parent.columnconfigure(5, weight=1)
        parent.columnconfigure(8, weight=0)

    def _build_subdebito_grid(self, parent: ttk.Labelframe) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        canvas = tk.Canvas(parent, bg="#f4f6f8", highlightthickness=0, borderwidth=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        panel_scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        panel_scroll.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=panel_scroll.set)

        content = ttk.Frame(canvas, style="App.TFrame")
        content_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def update_scroll_region(_event: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def fit_content_width(event: tk.Event) -> None:
            canvas.itemconfigure(content_id, width=event.width)

        content.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", fit_content_width)
        self._bind_mousewheel(canvas, canvas)
        self._bind_mousewheel(content, canvas)

        parent = content
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=0)
        self.tree = ttk.Treeview(parent, columns=SUBDEBIT_COLUMNS, show="headings", height=7, selectmode="extended")
        for col in SUBDEBIT_COLUMNS:
            self.tree.heading(col, text=col.replace("_", " ").title())
            anchor = "w" if col in {"tipo", "descricao"} else "center"
            width = 130
            if col == "descricao":
                width = 300
            elif col == "ug_gestao":
                width = 150
            elif col == "gru_cr":
                width = 100
            self.tree.column(col, width=width, anchor=anchor)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.tag_configure("honorarios", foreground="#b91c1c")
        self.tree.bind("<<TreeviewSelect>>", self.on_select_subdebito)

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        ttk.Label(parent, textvariable=self.subdebito_count_var, style="Muted.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", padx=2, pady=(3, 0)
        )

        batch_frame = tk.Frame(parent, bg=BATCH_BG, padx=0, pady=6)
        batch_frame.grid(row=2, column=0, columnspan=2, sticky="ew")
        batch_frame.columnconfigure(1, weight=3)
        batch_frame.columnconfigure(5, weight=2)
        ug_values = [self._ug_display(item) for item in self.ug_codes]
        gru_values = [self._gru_display(item) for item in self.gru_codes]

        tk.Label(batch_frame, text="UG", bg=BATCH_BG).grid(row=0, column=0, padx=4, pady=2, sticky="w")
        batch_ug_combo = self._make_filter_combobox(
            batch_frame,
            self.batch_vars["ug"],
            ug_values,
            self.ug_display_to_code,
            width=64,
            on_selected=self._sync_gestao_from_batch_ug,
        )
        batch_ug_combo.grid(row=0, column=1, padx=4, pady=2, sticky="ew")
        self.ug_comboboxes.append(batch_ug_combo)
        self._attach_tooltip(batch_ug_combo, BATCH_CODES_TOOLTIP)

        tk.Label(batch_frame, text="Gestao", bg=BATCH_BG).grid(row=0, column=2, padx=4, pady=2, sticky="w")
        tk.Label(batch_frame, textvariable=self.batch_vars["gestao"], bg=BATCH_BG).grid(row=0, column=3, padx=4, pady=2, sticky="w")
        tk.Label(batch_frame, text="GRU(CR)", bg=BATCH_BG).grid(row=0, column=4, padx=4, pady=2, sticky="w")
        batch_gru_combo = self._make_filter_combobox(
            batch_frame,
            self.batch_vars["gru_cr"],
            gru_values,
            self.gru_display_to_code,
            width=24,
        )
        batch_gru_combo.grid(row=0, column=5, padx=4, pady=2, sticky="ew")
        self.gru_comboboxes.append(batch_gru_combo)
        self._attach_tooltip(batch_gru_combo, BATCH_CODES_TOOLTIP)
        apply_codes_btn = ttk.Button(batch_frame, text="Aplicar aos selecionados", command=self.apply_batch_codes)
        apply_codes_btn.grid(
            row=0,
            column=6,
            padx=8,
            pady=2,
        )
        self._attach_tooltip(apply_codes_btn, BATCH_CODES_TOOLTIP)

        self._label_with_help(
            batch_frame,
            "Selecione os codigos UG/Gestao e GRU(CR), nas listas suspensas.",
            BATCH_CODES_TOOLTIP,
            row=1,
            column=0,
            columnspan=8,
            padx=4,
            pady=(4, 0),
            background=BATCH_BG,
        )

        summary_label = self._section_label_with_help(parent, "Débitos consolidados", SUMMARY_TOOLTIP)
        summary_frame = ttk.Labelframe(parent, labelwidget=summary_label, padding=(8, 6))
        summary_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        summary_frame.columnconfigure(0, weight=1)
        self.summary_tree = ttk.Treeview(
            summary_frame,
            columns=("descricao", "ug_gestao", "gru_cr", "valor_bloqueado", "valor_total"),
            show="headings",
            height=4,
        )
        self.summary_tree.heading("descricao", text="Descricao")
        self.summary_tree.heading("ug_gestao", text="UG/Gestao")
        self.summary_tree.heading("gru_cr", text="GRU(CR)")
        self.summary_tree.heading("valor_bloqueado", text="Valor Bloqueado")
        self.summary_tree.heading("valor_total", text="Valor Total")
        self.summary_tree.column("descricao", width=280, anchor="w")
        self.summary_tree.column("ug_gestao", width=150, anchor="center")
        self.summary_tree.column("gru_cr", width=100, anchor="center")
        self.summary_tree.column("valor_bloqueado", width=140, anchor="center")
        self.summary_tree.column("valor_total", width=160, anchor="center")
        self.summary_tree.grid(row=0, column=0, sticky="nsew")
        self.summary_tree.bind("<<TreeviewSelect>>", self.on_select_summary)
        
        self.summary_tree.tag_configure("missing_code", foreground="red")
        
        summary_scroll = ttk.Scrollbar(summary_frame, orient="vertical", command=self.summary_tree.yview)
        summary_scroll.grid(row=0, column=1, sticky="ns")
        self.summary_tree.configure(yscrollcommand=summary_scroll.set)
        self.summary_tree.tag_configure("honorarios", foreground="#b91c1c")
        ttk.Label(
            summary_frame,
            text="Selecione, para alterar a Descricao Consolidada",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))
        summary_editor = ttk.Frame(summary_frame)
        summary_editor.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        summary_editor.columnconfigure(0, weight=0)
        summary_editor.columnconfigure(1, weight=1)
        ttk.Entry(summary_editor, textvariable=self.summary_description_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(
            summary_editor,
            text="Selecione o debito consolidado para alterar sua descricao",
            command=self.update_summary_description,
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        total_label = tk.Label(
            summary_frame,
            textvariable=self.total_geral_var,
            font=("Segoe UI", 15, "bold"),
            fg="#0b5d1e",
            anchor="e",
        )
        total_label.grid(row=3, column=0, columnspan=2, sticky="e", pady=(6, 0))

    def _build_subdebito_editor(self, parent: ttk.Labelframe) -> None:
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(9, weight=1)
        editable_fields = [
            ("tipo", "Tipo"),
            ("descricao", "Descricao"),
            ("valor_atualizado", "Valor atualizado"),
            ("multa_art_523", "Multa art. 523"),
            ("valor_bloqueado", "Valor bloqueado"),
            ("ug", "UG"),
            ("gestao", "Gestao"),
            ("gru_cr", "GRU(CR)"),
        ]
        ug_values = [self._ug_display(item) for item in self.ug_codes]
        gru_values = [self._gru_display(item) for item in self.gru_codes]
        for idx, (field_name, label) in enumerate(editable_fields):
            ttk.Label(parent, text=label).grid(row=idx, column=0, sticky="w", padx=4, pady=1)
            if field_name == "tipo":
                cb = ttk.Combobox(
                    parent,
                    textvariable=self.subdebito_vars[field_name],
                    width=32,
                    state="readonly",
                    values=("PRINCIPAL", "HONORÁRIOS", "MULTA (exceto art. 523)"),
                )
                cb.grid(row=idx, column=1, sticky="ew", padx=4, pady=1)
            elif field_name == "ug":
                cb = self._make_filter_combobox(
                    parent,
                    self.subdebito_vars[field_name],
                    ug_values,
                    self.ug_display_to_code,
                    width=42,
                    on_selected=self._sync_gestao_from_subdebito_ug,
                )
                cb.grid(row=idx, column=1, sticky="ew", padx=4, pady=1)
                self.ug_comboboxes.append(cb)
            elif field_name == "gestao":
                ttk.Label(parent, textvariable=self.subdebito_vars[field_name]).grid(
                    row=idx,
                    column=1,
                    sticky="w",
                    padx=4,
                    pady=1,
                )
            elif field_name == "gru_cr":
                cb = self._make_filter_combobox(
                    parent,
                    self.subdebito_vars[field_name],
                    gru_values,
                    self.gru_display_to_code,
                    width=24,
                )
                cb.grid(row=idx, column=1, sticky="ew", padx=4, pady=1)
                self.gru_comboboxes.append(cb)
            else:
                entry_width = 18 if field_name in {"valor_atualizado", "multa_art_523", "valor_bloqueado"} else 26
                tk.Entry(
                    parent,
                    textvariable=self.subdebito_vars[field_name],
                    width=entry_width,
                    bg=FIELD_BG,
                    relief="solid",
                    bd=1,
                    highlightthickness=1,
                    highlightbackground="#cbd5e1",
                    highlightcolor="#0f766e",
                ).grid(
                    row=idx,
                    column=1,
                    sticky="ew",
                    padx=4,
                    pady=1,
                )

        actions = ttk.Frame(parent)
        actions.grid(row=len(editable_fields), column=0, columnspan=2, sticky="ew", pady=(4, 3))
        for col in range(3):
            actions.columnconfigure(col, weight=1)
        ttk.Button(actions, text="Atualizar", command=self.save_subdebito_edits).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(actions, text="Adicionar", command=self.add_subdebito).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(actions, text="Excluir", command=self.remove_subdebito).grid(row=0, column=2, sticky="ew", padx=(4, 0))

        notes_frame = ttk.Labelframe(parent, text="Condicoes adicionais", padding=(6, 5))
        notes_frame.grid(row=len(editable_fields) + 1, column=0, columnspan=2, sticky="nsew", pady=(3, 6))
        notes_frame.columnconfigure(0, weight=1)
        notes_frame.rowconfigure(0, weight=1)
        self.notes_text = tk.Text(
            notes_frame,
            height=6,
            wrap="word",
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground="#cbd5e1",
            highlightcolor="#0f766e",
            bg=TOP_FIELD_BG,
            font=("Segoe UI", 9),
            padx=7,
            pady=4,
        )
        self.notes_text.grid(row=0, column=0, sticky="nsew")
        self.notes_text.bind("<KeyRelease>", self._update_notes_bg)

        ttk.Button(
            parent,
            text="GERAR OPCOES DA PROPOSTA",
            command=self.generate_proposal,
            style="Success.TButton",
        ).grid(row=len(editable_fields) + 2, column=0, columnspan=2, sticky="sew", padx=4, pady=(4, 0))


    def _case_signature(self) -> str:
        return json.dumps(self.case_data.to_dict(), ensure_ascii=False, sort_keys=True)

    def _current_case_signature(self) -> str:
        self.sync_case_from_form()
        return self._case_signature()

    def _mark_case_clean(self) -> None:
        self._saved_case_signature = self._case_signature()

    def _has_unsaved_changes(self) -> bool:
        try:
            return self._current_case_signature() != self._saved_case_signature
        except ValueError:
            return True

    def _confirm_save_unsaved_changes(self, action: str) -> bool:
        if not self._has_unsaved_changes():
            return True
        answer = messagebox.askyesnocancel(
            "Salvar alterações?",
            (
                "Há alterações não salvas no caso atual.\n\n"
                f"Deseja salvar antes de {action}?"
            ),
            parent=self.root,
        )
        if answer is None:
            return False
        if answer is False:
            return True
        return self.save_json(show_success=False)

    def close_app(self) -> None:
        if self._confirm_save_unsaved_changes("fechar o aplicativo"):
            self.root.destroy()

    def create_from_any_pdf(self) -> None:
        if not self._confirm_save_unsaved_changes("criar um novo caso a partir de relatório"):
            return
        paths = filedialog.askopenfilenames(
            title="Selecione um ou mais relatorios TCU/PROJEF Web",
            filetypes=[("Arquivos PDF", "*.pdf")],
        )
        if not paths:
            return
        self._load_case_from_pdfs(list(paths), expected_type=None)

    def add_other_report(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Selecione um ou mais relatorios TCU/PROJEF para adicionar",
            filetypes=[("Arquivos PDF", "*.pdf")],
        )
        if not paths:
            return
        self._load_case_from_pdfs(list(paths), merge_into_current=True)

    def _load_case_from_pdfs(
        self,
        paths: list[str],
        expected_type: str | None = None,
        merge_into_current: bool = False,
    ) -> None:
        first = True
        for path in paths:
            self._load_case_from_pdf(
                path,
                expected_type=expected_type,
                merge=merge_into_current or not first,
            )
            first = False

    def _parse_report_by_type(self, path: str, report_type: str) -> CaseData:
        if report_type == "projef":
            return parse_projef_report(path)
        if report_type == "tcu":
            return parse_tcu_report(path)
        raise ValueError(f"Tipo de relatorio nao suportado: {report_type}")

    def _report_requires_update(self, report_type: str, case_data: CaseData) -> bool:
        if report_type == "projef":
            return competencia_esta_defasada(case_data.competencia_atualizacao)

        if report_type != "tcu":
            return False

        parsed_date = parse_iso_date(case_data.data_atualizacao)
        if not parsed_date:
            return False
        return parsed_date.replace(day=1) < date.today().replace(day=1)

    def run_with_loading(self, title: str, message: str, target_func, *args, **kwargs):
        import time
        import threading

        loading = tk.Toplevel(self.root)
        loading.title(title)
        loading.transient(self.root)
        loading.grab_set()
        loading.resizable(False, False)
        
        loading.update_idletasks()
        width = 450
        height = 130
        x = (loading.winfo_screenwidth() - width) // 2
        y = (loading.winfo_screenheight() - height) // 2
        loading.geometry(f"{width}x{height}+{x}+{y}")

        ttk.Label(loading, text=message, wraplength=410, justify="center").pack(pady=(20, 10))
        progress = ttk.Progressbar(loading, mode="indeterminate", length=300)
        progress.pack()
        progress.start()

        result = None
        exec_error = None

        def worker():
            nonlocal result, exec_error
            try:
                result = target_func(*args, **kwargs)
            except Exception as e:
                exec_error = e

        thread = threading.Thread(target=worker)
        thread.start()

        while thread.is_alive():
            try:
                self.root.update()
            except tk.TclError:
                pass
            time.sleep(0.05)

        try:
            loading.destroy()
        except tk.TclError:
            pass

        if exec_error:
            raise exec_error
        return result

    def _maybe_update_incoming_report(self, report_type: str, incoming: CaseData) -> CaseData:
        if not self._report_requires_update(report_type, incoming):
            return incoming

        if report_type == "projef":
            should_update = messagebox.askyesno(
                "Competencia defasada",
                (
                    f"A competencia {incoming.competencia_atualizacao} esta anterior ao mes atual.\n\n"
                    "Deseja atualizar este relatorio no ProjefWeb antes de inseri-lo no caso?"
                ),
                parent=self.root,
            )
            if not should_update:
                return incoming
            updated_path = self.run_with_loading(
                "Atualizando no Projef",
                "Navegando no portal ProjefWeb em background... Aguarde.",
                atualizar_relatorio_projef,
                incoming,
            )
            
            import os
            try:
                os.startfile(updated_path)
            except Exception:
                pass

            self.status_var.set(f"Relatorio Projef atualizado e aberto automaticamente: {updated_path.name}")
            return parse_projef_report(str(updated_path))

        should_update = messagebox.askyesno(
            "Relatorio TCU defasado",
            (
                f"O relatorio TCU esta atualizado em {incoming.data_atualizacao}, anterior ao mes atual.\n\n"
                "Deseja atualizar este relatorio no TCU antes de inseri-lo no caso?"
            ),
            parent=self.root,
        )
        if not should_update:
            return incoming
        updated_path = self.run_with_loading(
            "Atualizando no TCU",
            "Navegando no portal TCU em background... Aguarde.",
            atualizar_relatorio_tcu,
            incoming,
        )
        
        import os
        try:
            os.startfile(updated_path)
        except Exception:
            pass
            
        self.status_var.set(f"Relatorio TCU atualizado e aberto automaticamente: {updated_path.name}")
        return parse_tcu_report(str(updated_path))

    def _load_case_from_pdf(self, path: str, expected_type: str | None = None, merge: bool = False) -> None:
        try:
            report_type = expected_type or detect_report_type(path)
            incoming = self._parse_report_by_type(path, report_type)
            incoming = self._maybe_update_incoming_report(report_type, incoming)
            if merge and (self.case_data.subdebitos or self.case_data.lancamentos_tcu or self.case_data.devedor):
                if incoming.subdebitos:
                    should_add_subdebito = messagebox.askyesno(
                        "Adicionar subdebito",
                        (
                            "O novo relatorio possui subdebito(s) para anexar ao caso atual.\n\n"
                            "Deseja adicionar esse novo subdebito ao caso?"
                        ),
                        parent=self.root,
                    )
                    if not should_add_subdebito:
                        self.status_var.set(
                            f"Relatorio analisado e nao anexado: {Path(path).name}"
                        )
                        return
                self.case_data, conflicts = merge_case_data(self.case_data, incoming)
                self.resolve_merge_conflicts(conflicts)
                self.status_var.set(
                    f"Relatorio adicionado: {Path(path).name} | Anexados: {len(self.case_data.relatorios_anexados)} | Subdebitos: {len(self.case_data.subdebitos)} | Lancamentos TCU: {len(self.case_data.lancamentos_tcu)}"
                )
            else:
                self.case_data = incoming
                self.clear_case_selection_state()
                self.status_var.set(
                    f"Relatorio carregado: {Path(path).name} | Tipo: {report_type.upper()} | Anexados: {len(self.case_data.relatorios_anexados)} | Lancamentos TCU: {len(self.case_data.lancamentos_tcu)}"
                )
            self.refresh_all()
            if report_type == "tcu":
                messagebox.showinfo(
                    "Relatorio TCU importado",
                    (
                        f"Relatorio TCU lido com sucesso.\n\n"
                        f"Relatorios anexados no caso: {len(self.case_data.relatorios_anexados)}"
                    ),
                )
        except Exception as exc:
            messagebox.showerror("Erro ao ler PDF", str(exc))

    def load_json(self) -> None:
        if not self._confirm_save_unsaved_changes("abrir outro JSON"):
            return
        path = filedialog.askopenfilename(
            title="Abrir rascunho anterior",
            filetypes=[("Arquivos JSON", "*.json")],
        )
        if not path:
            return
        try:
            self.case_data = CaseData.load_json(path)
            self.clear_case_selection_state()
            self.refresh_all()
            self._mark_case_clean()
            self.status_var.set(f"JSON carregado: {Path(path).name}")
        except Exception as exc:
            messagebox.showerror("Erro ao abrir JSON", str(exc))

    def _default_case_filename(self, extension: str, include_timestamp: bool) -> str:
        processo_clean = re.sub(r"[\.\-]", "", self.case_data.processo) if self.case_data.processo else "SPROC"
        devedor_clean = (self.case_data.devedor or "SDEV")[:30].strip()
        devedor_clean = re.sub(r'[\\/:*?"<>|]+', "", devedor_clean).strip() or "SDEV"
        parts = ["PROPOSTA", processo_clean, devedor_clean]
        if include_timestamp:
            parts.append(datetime.now().strftime("%d-%m-%Y_%H-%M-%S"))
        return "-".join(parts) + extension

    def save_json(self, show_success: bool = True) -> bool:
        try:
            self.sync_case_from_form()
        except ValueError:
            messagebox.showerror("Dados invalidos", "Revise os campos numericos antes de salvar.")
            return False
        errors = self.case_data.validate(strict_proposal=bool(self.case_data.subdebitos))
        if errors:
            messagebox.showwarning("Validacoes pendentes", "\n".join(errors))
            return False
        path = filedialog.asksaveasfilename(
            initialfile=self._default_case_filename(".json", include_timestamp=False),
            title="Salvar dados do caso",
            defaultextension=".json",
            filetypes=[("Arquivos JSON", "*.json")],
        )
        if not path:
            return False
        self.case_data.save_json(path)
        self._mark_case_clean()
        self.status_var.set(f"Dados salvos em {Path(path).name}")
        if show_success:
            messagebox.showinfo("Salvo", "Caso salvo com sucesso.")
        return True

    def generate_proposal(self) -> None:
        self.sync_case_from_form()
        errors = self.case_data.validate(strict_proposal=True)
        if errors:
            messagebox.showwarning("Validacoes pendentes", "\n".join(errors))
            return
            
        if self.case_data.tipo_parcela == "FIXO (PREFIXADO)":
            try:
                from pactuacalc.selic_api import update_selic_history
                self.run_with_loading(
                    "Atualizando Taxas Selic",
                    "Buscando histórico atualizado de taxas Selic no Banco Central...",
                    update_selic_history,
                )
            except Exception as e:
                messagebox.showwarning("Erro na Selic", f"Nao foi possivel atualizar a base Selic. O sistema tentará usar a base local existente.\n\nDetalhes: {e}")
            
        from pactuacalc.services import consolidar_por_chave_arrecadatoria
        consolidated = consolidar_por_chave_arrecadatoria(self.case_data.subdebitos)
        for item in consolidated:
            if not (item.ug or "").strip() or not (item.gru_cr or "").strip():
                messagebox.showerror(
                    "Campos Incompletos",
                    f"ATENCAO: O subdebito '{item.descricao}' nao possui UG/Gestao e/ou GRU(CR) preenchidos.\n\n"
                    "E obrigatorio preenche-los em TODOS os itens antes de gerar as opcoes."
                )
                return

        selected_codes = self.collect_proposal_generation_options()
        if not selected_codes:
            return

        if "2" in selected_codes and not self.collect_vista_discount_mode():
            return
             
        from pactuacalc.proposals import build_proposal_scenarios
        base_scenarios = build_proposal_scenarios(self.case_data, selected_codes=selected_codes)
        proposal_selections = self.collect_proposal_adjustments(base_scenarios)
        if proposal_selections is None:
            return
        self.case_data.propostas_selecionadas = proposal_selections
        scenarios = build_proposal_scenarios(
            self.case_data,
            selected_codes=selected_codes,
            proposal_selections=proposal_selections,
        )
        
        if not self.show_proposal_preview(scenarios):
            return

        default_name = self._default_case_filename(".pdf", include_timestamp=True)

        path = filedialog.asksaveasfilename(
            initialfile=default_name,
            title="Salvar proposta em PDF",
            defaultextension=".pdf",
            filetypes=[("Arquivos PDF", "*.pdf")],
        )
        if not path:
            return
        pdf_path = create_proposal_pdf(self.case_data, path, selected_codes=selected_codes, scenarios=scenarios)
        
        import os
        try:
            os.startfile(pdf_path)
        except Exception:
            pass

        total = total_bloqueado_efetivo(self.case_data.subdebitos)
        self.status_var.set(f"PDF gerado: {Path(pdf_path).name}")
        messagebox.showinfo(
            "Geracao de proposta",
            (
                f"Propostas geradas em PDF com {len(self.case_data.subdebitos)} subdebitos "
                f"e bloqueio efetivo de {format_currency_br(total)}."
            ),
        )

    def collect_proposal_adjustments(self, scenarios: list) -> dict[str, ProposalSelection] | None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Ajustar propostas selecionadas")
        dialog.transient(self.root)
        dialog.grab_set()
        width = 1120
        height = 460
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - width) // 2
        y = (dialog.winfo_screenheight() - height) // 2
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.resizable(True, True)
        dialog_bg = dialog.cget("bg")

        main = tk.Frame(dialog, bg=dialog_bg, padx=12, pady=12)
        main.pack(fill="both", expand=True)

        tk.Label(
            main,
            text=(
                "Ajuste somente se necessario. Entrada so pode aumentar, desconto so pode diminuir "
                "e parcelas so podem ser reduzidas dentro da faixa da proposta."
            ),
            wraplength=920,
            bg=dialog_bg,
            anchor="w",
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        tk.Label(
            main,
            text=f"{len(scenarios)} proposta(s) selecionada(s) para ajuste.",
            bg=dialog_bg,
            anchor="w",
        ).pack(anchor="w", pady=(0, 6))

        table = tk.Frame(main, bg=dialog_bg)
        table.pack(fill="x", expand=False)
        table.columnconfigure(0, minsize=240)
        for col in range(1, 8):
            table.columnconfigure(col, minsize=105)
        headers = (
            "Proposta",
            "Entrada padrao",
            "Entrada final (%)",
            "Desconto padrao",
            "Desconto final (%)",
            "Parcelas padrao",
            "Parcelas finais",
            "Faixa",
        )
        for col, header in enumerate(headers):
            tk.Label(
                table,
                text=header,
                font=("Segoe UI", 9, "bold"),
                bg=dialog_bg,
                anchor="w",
            ).grid(row=0, column=col, sticky="w", padx=4, pady=3)

        vars_by_code: dict[str, dict[str, tk.StringVar]] = {}
        scenario_by_code = {scenario.codigo: scenario for scenario in scenarios}
        entries_by_code: dict[str, dict[str, tk.Entry]] = {}
        normal_font = tkfont.Font(family="Segoe UI", size=9)
        changed_font = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        reset_button_disabled_font = tkfont.Font(family="Segoe UI", size=9)
        reset_button_enabled_font = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        reset_button: tk.Button | None = None
        default_data_primeira_com_entrada = self._default_first_installment_after_entry()
        data_primeira_com_entrada_var = tk.StringVar(
            value=self.case_data.data_primeira_parcela_com_entrada or default_data_primeira_com_entrada
        )
        data_primeira_com_entrada_entry: tk.Entry | None = None

        def _is_partial_decimal(value: str) -> bool:
            return value == "" or all(char.isdigit() or char in ",." for char in value)

        def make_decimal_validator(min_value: float, max_value: float | None = None):
            def validate(value: str) -> bool:
                if not _is_partial_decimal(value):
                    return False
                if value in {"", ",", "."}:
                    return True
                try:
                    parsed = parse_decimal_input(value)
                except ValueError:
                    return False
                if parsed < min_value:
                    digits = "".join(char for char in value if char.isdigit())
                    min_digits = str(int(min_value)) if min_value >= 1 else ""
                    return bool(min_digits) and len(digits) < len(min_digits)
                if max_value is not None and parsed > max_value:
                    return False
                return True
            return dialog.register(validate)

        def make_int_validator(min_value: int, max_value: int):
            def validate(value: str) -> bool:
                if value == "":
                    return True
                if not value.isdigit():
                    return False
                parsed = int(value)
                if parsed < min_value and len(value) < len(str(min_value)):
                    return True
                return min_value <= parsed <= max_value
            return dialog.register(validate)

        def validate_first_installment_date(value: str) -> bool:
            if value == "":
                return True
            if not all(char.isdigit() or char == "/" for char in value) or len(value) > 10:
                return False
            parsed = parse_iso_date(value)
            default_date = parse_iso_date(default_data_primeira_com_entrada)
            if parsed and default_date:
                return parsed <= default_date
            return True

        date_validator = dialog.register(validate_first_installment_date)

        for row, scenario in enumerate(scenarios, start=1):
            saved = self.case_data.propostas_selecionadas.get(scenario.codigo)
            entrada_value = scenario.entrada_minima_percentual
            desconto_value = scenario.desconto_percentual
            parcelas_value = scenario.parcelas
            if saved:
                if saved.entrada_percentual is not None:
                    entrada_value = saved.entrada_percentual
                if saved.desconto_percentual is not None:
                    desconto_value = saved.desconto_percentual
                if saved.parcelas is not None:
                    parcelas_value = saved.parcelas

            entrada_var = tk.StringVar(value=format_decimal_br(entrada_value))
            desconto_var = tk.StringVar(value=format_decimal_br(desconto_value))
            parcelas_var = tk.StringVar(value=str(parcelas_value))
            vars_by_code[scenario.codigo] = {
                "entrada": entrada_var,
                "desconto": desconto_var,
                "parcelas": parcelas_var,
            }

            min_parcelas, max_parcelas = parcela_limites(scenario.codigo)
            if scenario.codigo == "2":
                proposta_text = f"{scenario.codigo} - {scenario.modalidade} (Parcela Única)"
            else:
                proposta_text = f"{scenario.codigo} - {scenario.modalidade} (Até {scenario.parcelas} Parc.)"
            proposta_label = tk.Label(
                table,
                text=proposta_text,
                anchor="w",
                width=30,
                bg=dialog_bg,
            )
            proposta_label.grid(row=row, column=0, sticky="ew", padx=4, pady=3)
            tk.Label(
                table,
                text=format_percent_br(scenario.entrada_minima_percentual),
                bg=dialog_bg,
                anchor="e",
            ).grid(row=row, column=1, sticky="e", padx=4, pady=3)
            entrada_minima = scenario.entrada_minima_percentual if scenario.codigo not in OPTIONAL_ENTRY_CODES else 0.0
            entrada_entry = tk.Entry(
                table,
                textvariable=entrada_var,
                width=12,
                bg=FIELD_BG,
                relief="solid",
                bd=1,
                font=normal_font,
                validate="key",
                validatecommand=(make_decimal_validator(entrada_minima), "%P"),
            )
            entrada_entry.grid(row=row, column=2, sticky="ew", padx=4, pady=3)
            if scenario.codigo in OPTIONAL_ENTRY_CODES:
                tk.Label(table, text="*", fg="#b91c1c", bg=dialog_bg, font=("Segoe UI", 10, "bold")).grid(
                    row=row, column=2, sticky="e", padx=(0, 1), pady=3
                )
            elif scenario.entrada_minima_percentual <= 0:
                entrada_entry.configure(state="disabled", disabledbackground="#e5e7eb")

            tk.Label(
                table,
                text=format_percent_br(scenario.desconto_percentual),
                bg=dialog_bg,
                anchor="e",
            ).grid(row=row, column=3, sticky="e", padx=4, pady=3)
            desconto_entry = tk.Entry(
                table,
                textvariable=desconto_var,
                width=12,
                bg=FIELD_BG,
                relief="solid",
                bd=1,
                font=normal_font,
                validate="key",
                validatecommand=(make_decimal_validator(0.0, scenario.desconto_percentual), "%P"),
            )
            desconto_entry.grid(row=row, column=4, sticky="ew", padx=4, pady=3)
            if scenario.desconto_percentual <= 0:
                desconto_entry.configure(state="disabled", disabledbackground="#e5e7eb")

            tk.Label(table, text=str(scenario.parcelas), bg=dialog_bg, anchor="e").grid(row=row, column=5, sticky="e", padx=4, pady=3)
            parcelas_entry = tk.Entry(
                table,
                textvariable=parcelas_var,
                width=10,
                bg=FIELD_BG,
                relief="solid",
                bd=1,
                font=normal_font,
                validate="key",
                validatecommand=(make_int_validator(min_parcelas, scenario.parcelas), "%P"),
            )
            parcelas_entry.grid(row=row, column=6, sticky="ew", padx=4, pady=3)
            if scenario.parcelas <= 1:
                parcelas_entry.configure(state="disabled", disabledbackground="#e5e7eb")
            tk.Label(table, text=f"{min_parcelas} a {max_parcelas}", bg=dialog_bg, anchor="w").grid(row=row, column=7, sticky="w", padx=4, pady=3)
            entries_by_code[scenario.codigo] = {
                "entrada": entrada_entry,
                "desconto": desconto_entry,
                "parcelas": parcelas_entry,
            }

        tk.Label(
            main,
            text="*A entrada nessas opções não geram desconto.",
            fg="#b91c1c",
            bg=dialog_bg,
            anchor="w",
        ).pack(anchor="w", pady=(6, 0))

        date_frame = tk.Frame(main, bg=dialog_bg)
        date_frame.pack(fill="x", pady=(18, 8))
        data_entrada_label = self.case_data.data_primeira_parcela or "-"
        tk.Label(
            date_frame,
            text="Nas opções com Entrada (prevista para ",
            bg=dialog_bg,
            anchor="w",
        ).pack(side="left")
        tk.Label(
            date_frame,
            text=data_entrada_label,
            bg=dialog_bg,
            anchor="w",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left")
        tk.Label(
            date_frame,
            text="), a primeira parcela terá vencimento em:",
            bg=dialog_bg,
            anchor="w",
        ).pack(side="left", padx=(0, 8))
        data_primeira_com_entrada_entry = tk.Entry(
            date_frame,
            textvariable=data_primeira_com_entrada_var,
            width=12,
            bg=FIELD_BG,
            relief="solid",
            bd=1,
            font=normal_font,
            validate="key",
            validatecommand=(date_validator, "%P"),
        )
        data_primeira_com_entrada_entry.pack(side="left")

        result: dict[str, dict[str, ProposalSelection] | None] = {"selections": None}

        def apply_change_style(entry: tk.Entry, changed: bool) -> None:
            if str(entry.cget("state")) == "disabled":
                return
            entry.configure(fg="#b91c1c" if changed else "#111827", font=changed_font if changed else normal_font)

        def update_change_styles(*_args) -> None:
            has_changes = False
            for code, values in vars_by_code.items():
                scenario = scenario_by_code[code]
                entries = entries_by_code[code]
                entrada_editavel = scenario.entrada_minima_percentual > 0 or scenario.codigo in OPTIONAL_ENTRY_CODES
                try:
                    entrada = parse_decimal_input(values["entrada"].get()) if entrada_editavel else scenario.entrada_minima_percentual
                except ValueError:
                    entrada = None
                try:
                    desconto = parse_decimal_input(values["desconto"].get()) if scenario.desconto_percentual > 0 else scenario.desconto_percentual
                except ValueError:
                    desconto = None
                try:
                    parcelas = int(values["parcelas"].get()) if scenario.parcelas > 1 else scenario.parcelas
                except ValueError:
                    parcelas = None

                entrada_changed = entrada_editavel and (
                    abs(entrada - scenario.entrada_minima_percentual) > 0.0001
                    if entrada is not None
                    else values["entrada"].get().strip() != format_decimal_br(scenario.entrada_minima_percentual)
                )
                desconto_changed = scenario.desconto_percentual > 0 and (
                    abs(desconto - scenario.desconto_percentual) > 0.0001
                    if desconto is not None
                    else values["desconto"].get().strip() != format_decimal_br(scenario.desconto_percentual)
                )
                parcelas_changed = scenario.parcelas > 1 and (
                    parcelas != scenario.parcelas
                    if parcelas is not None
                    else values["parcelas"].get().strip() != str(scenario.parcelas)
                )

                apply_change_style(entries["entrada"], entrada_changed)
                apply_change_style(entries["desconto"], desconto_changed)
                apply_change_style(entries["parcelas"], parcelas_changed)
                has_changes = has_changes or entrada_changed or desconto_changed or parcelas_changed
            if data_primeira_com_entrada_entry is not None:
                data_primeira_com_entrada_changed = (
                    data_primeira_com_entrada_var.get().strip() != default_data_primeira_com_entrada
                )
                apply_change_style(
                    data_primeira_com_entrada_entry,
                    data_primeira_com_entrada_changed,
                )
                has_changes = has_changes or data_primeira_com_entrada_changed
            if reset_button is not None:
                if has_changes:
                    reset_button.configure(
                        state="normal",
                        fg=RESET_DEFAULTS_FG,
                        activeforeground=RESET_DEFAULTS_FG,
                        font=reset_button_enabled_font,
                    )
                else:
                    reset_button.configure(
                        state="disabled",
                        fg=RESET_DEFAULTS_DISABLED_FG,
                        activeforeground=RESET_DEFAULTS_DISABLED_FG,
                        disabledforeground=RESET_DEFAULTS_DISABLED_FG,
                        font=reset_button_disabled_font,
                    )

        for values in vars_by_code.values():
            for var in values.values():
                var.trace_add("write", update_change_styles)
        data_primeira_com_entrada_var.trace_add("write", update_change_styles)
        update_change_styles()

        def reset_to_defaults() -> None:
            for code, values in vars_by_code.items():
                scenario = scenario_by_code[code]
                values["entrada"].set(format_decimal_br(scenario.entrada_minima_percentual))
                values["desconto"].set(format_decimal_br(scenario.desconto_percentual))
                values["parcelas"].set(str(scenario.parcelas))
            data_primeira_com_entrada_var.set(default_data_primeira_com_entrada)
            update_change_styles()

        def confirm() -> None:
            selections: dict[str, ProposalSelection] = {}
            errors: list[str] = []
            for code, values in vars_by_code.items():
                scenario = scenario_by_code[code]
                try:
                    entrada_editavel = scenario.entrada_minima_percentual > 0 or scenario.codigo in OPTIONAL_ENTRY_CODES
                    entrada = parse_decimal_input(values["entrada"].get()) if entrada_editavel else 0.0
                    desconto = parse_decimal_input(values["desconto"].get()) if scenario.desconto_percentual > 0 else 0.0
                    parcelas = int(values["parcelas"].get()) if scenario.parcelas > 1 else scenario.parcelas
                except ValueError:
                    errors.append(f"Valores invalidos na proposta {code}.")
                    continue

                selection = ProposalSelection(
                    entrada_percentual=entrada,
                    desconto_percentual=desconto,
                    parcelas=parcelas,
                )
                errors.extend(validate_proposal_selection(scenario, selection))
                changed = (
                    abs(entrada - scenario.entrada_minima_percentual) > 0.0001
                    or abs(desconto - scenario.desconto_percentual) > 0.0001
                    or parcelas != scenario.parcelas
                )
                if changed:
                    selections[code] = selection

            if errors:
                messagebox.showwarning("Ajustes invalidos", "\n".join(errors), parent=dialog)
                return
            data_primeira_com_entrada = data_primeira_com_entrada_var.get().strip()
            if data_primeira_com_entrada and not parse_iso_date(data_primeira_com_entrada):
                messagebox.showwarning(
                    "Data invalida",
                    "Informe a data da primeira parcela das opcoes com entrada no formato dd/mm/aaaa.",
                    parent=dialog,
                )
                return
            data_informada = parse_iso_date(data_primeira_com_entrada) if data_primeira_com_entrada else None
            data_limite_padrao = parse_iso_date(default_data_primeira_com_entrada)
            if data_informada and data_limite_padrao and data_informada > data_limite_padrao:
                messagebox.showwarning(
                    "Data invalida",
                    (
                        "A data da primeira parcela das opcoes com entrada so pode ser antecipada.\n\n"
                        f"Informe uma data igual ou anterior a {default_data_primeira_com_entrada}."
                    ),
                    parent=dialog,
                )
                return
            self.case_data.data_primeira_parcela_com_entrada = data_primeira_com_entrada
            result["selections"] = selections
            dialog.destroy()

        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Voltar", command=dialog.destroy).pack(side="left")
        reset_button = tk.Button(
            buttons,
            text=RESET_DEFAULTS_TEXT,
            command=reset_to_defaults,
            fg=RESET_DEFAULTS_DISABLED_FG,
            activeforeground=RESET_DEFAULTS_DISABLED_FG,
            disabledforeground=RESET_DEFAULTS_DISABLED_FG,
            bg=RESET_DEFAULTS_BUTTON_BG,
            activebackground=RESET_DEFAULTS_BUTTON_BG,
            relief="raised",
            bd=1,
            padx=8,
            pady=2,
        )
        reset_button.pack(side="left", padx=(10, 0))
        update_change_styles()
        ttk.Button(buttons, text="Avancar para resumo", command=confirm).pack(side="right")

        self.root.wait_window(dialog)
        return result["selections"]

    def collect_vista_discount_mode(self) -> bool:
        dialog = tk.Toplevel(self.root)
        dialog.title("Desconto da opcao a vista")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        dialog.update_idletasks()
        width = 520
        height = 250
        x = (dialog.winfo_screenwidth() - width) // 2
        y = (dialog.winfo_screenheight() - height) // 2
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog_bg = dialog.cget("bg")

        mode_var = tk.StringVar(value=self.case_data.proposal_rules.calculo_vista or "percentual_unico")
        if mode_var.get() not in {"percentual_unico", "progressivo"}:
            mode_var.set("percentual_unico")
        result = {"confirmed": False}

        tk.Label(
            dialog,
            text="Como deve ser calculado o desconto da proposta 2 (pagamento a vista)?",
            bg=dialog_bg,
            anchor="w",
            justify="left",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=14, pady=(14, 8))

        tk.Radiobutton(
            dialog,
            text="Percentual unico por faixa (padrao)",
            variable=mode_var,
            value="percentual_unico",
            bg=dialog_bg,
            activebackground=dialog_bg,
            selectcolor=dialog_bg,
            anchor="w",
        ).pack(anchor="w", padx=18, pady=3)

        tk.Radiobutton(
            dialog,
            text="Faixa progressiva (excepcional)",
            variable=mode_var,
            value="progressivo",
            bg=dialog_bg,
            activebackground=dialog_bg,
            selectcolor=dialog_bg,
            anchor="w",
        ).pack(anchor="w", padx=18, pady=3)

        tk.Label(
            dialog,
            text=(
                "A faixa e definida sem honorarios/encargos. O percentual encontrado "
                "e aplicado sobre a base geral da opcao a vista."
            ),
            wraplength=480,
            bg=dialog_bg,
            anchor="w",
            justify="left",
        ).pack(anchor="w", padx=14, pady=(10, 0))

        def confirm() -> None:
            if mode_var.get() == "progressivo":
                if not messagebox.askokcancel(
                    "Calculo progressivo",
                    "Esta opcao e excepcional. Verifique se e possivel concede-lo, antes de prosseguir.",
                    parent=dialog,
                ):
                    return
            self.case_data.proposal_rules.calculo_vista = mode_var.get()
            result["confirmed"] = True
            dialog.destroy()

        buttons = ttk.Frame(dialog)
        buttons.pack(fill="x", padx=14, pady=14)
        ttk.Button(buttons, text="Voltar", command=dialog.destroy).pack(side="left")
        ttk.Button(buttons, text="Confirmar", command=confirm).pack(side="right")

        self.root.wait_window(dialog)
        return result["confirmed"]

    def show_proposal_preview(self, scenarios: list) -> bool:
        dialog = tk.Toplevel(self.root)
        dialog.title("Pre-visualizacao das Opcoes Geradas")
        dialog.transient(self.root)
        dialog.grab_set()
        
        dialog.update_idletasks()
        width = 900
        height = 650
        x = (dialog.winfo_screenwidth() - width) // 2
        y = (dialog.winfo_screenheight() - height) // 2
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        
        main_frame = ttk.Frame(dialog, padding=12)
        main_frame.pack(fill="both", expand=True)
        
        text = tk.Text(main_frame, wrap="word", font=("Consolas", 10))
        scroll = ttk.Scrollbar(main_frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        
        scroll.pack(side="right", fill="y")
        text.pack(side="top", fill="both", expand=True, pady=(0, 12))
        
        from pactuacalc.formatting import format_currency_br, format_percent_br
        
        for sc in scenarios:
            if sc.parcelas == 1:
                ui_title = f"[{sc.codigo}] {sc.modalidade.upper()} (PARCELA UNICA)"
            else:
                if self.case_data.tipo_parcela == "FIXO (PREFIXADO)":
                    tipo_str = "PRÉ-FIXADAS"
                elif "VARIAVEL" in (self.case_data.tipo_parcela or "").upper():
                    tipo_str = "VARIÁVEIS"
                else:
                    tipo_str = "FIXAS"
                ui_title = f"[{sc.codigo}] {sc.modalidade.upper()} ({sc.parcelas} parcelas {tipo_str})"
            
            text.insert("end", ui_title + "\n", "title")
            text.insert("end", f"  • Desconto: {format_percent_br(sc.desconto_percentual)} ({format_currency_br(sc.desconto_valor)})\n", "normal")
            text.insert("end", f"  • Entrada GRU: {format_currency_br(sc.entrada_gru)}\n", "normal")
            text.insert("end", f"  • Saldo remanescente: {format_currency_br(sc.saldo_remanescente)}\n", "normal")
            if sc.parcelas == 1:
                text.insert("end", f"  • Pagamento: Parcela Unica de {format_currency_br(sc.valor_parcela)}\n", "normal")
            else:
                text.insert("end", f"  • Parcelamento: {sc.parcelas} parcelas mensais de {format_currency_br(sc.valor_parcela)}\n", "normal")
            
            if self.case_data.tipo_parcela == "FIXO (PREFIXADO)" and sc.parcelas > 1:
                from pactuacalc.services import total_bloqueado_efetivo
                tot_bloq = total_bloqueado_efetivo(self.case_data.subdebitos)
                val_prefixado = tot_bloq + sc.entrada_gru + (sc.valor_parcela * sc.parcelas)
                text.insert("end", f"\n  ▶ VALOR FINAL: {format_currency_br(val_prefixado)} (com Parcela Pre-fixada)\n", "highlight")
            else:
                text.insert("end", f"\n  ▶ VALOR FINAL: {format_currency_br(sc.valor_final)}\n", "highlight")
                
            if sc.observacao:
                text.insert("end", f"\n  Obs: {sc.observacao}\n\n", "obs")
            else:
                text.insert("end", "\n")
            
            for r in (sc.rows or []):
                text.insert("end", f"      -> {r.descricao[:45]}...: Saldo {format_currency_br(r.saldo)}, Parcela {format_currency_br(r.parcela)}\n", "sub")
                
            text.insert("end", "\n" + "=" * 85 + "\n\n", "separator")
            
        text.tag_configure("title", font=("Segoe UI", 12, "bold"), foreground="#003399", spacing3=5)
        text.tag_configure("normal", font=("Segoe UI", 10), spacing1=2)
        text.tag_configure("highlight", font=("Segoe UI", 11, "bold"), foreground="#b30000")
        text.tag_configure("obs", font=("Segoe UI", 9, "italic"), foreground="#4d4d4d")
        text.tag_configure("sub", font=("Consolas", 9), foreground="#666666")
        text.tag_configure("separator", foreground="#cccccc")
        text.configure(state="disabled")
        
        result = [False]
        def on_generate():
            result[0] = True
            dialog.destroy()
            
        def on_back():
            dialog.destroy()
            
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(side="bottom", fill="x")
        
        ttk.Button(btn_frame, text="Voltar para Edicao", command=on_back).pack(side="left", padx=8)
        tk.Button(btn_frame, text="Gerar PDF da Proposta", command=on_generate, bg="#d9f7be", font=("Segoe UI", 10, "bold")).pack(side="right", padx=8)
        
        self.root.wait_window(dialog)
        return result[0]

    def collect_proposal_generation_options(self) -> set[str]:
        dialog = tk.Toplevel(self.root)
        dialog.title("Selecionar opcoes da proposta")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        
        dialog.update_idletasks()
        width = 380
        height = 360
        x = (dialog.winfo_screenwidth() - width) // 2
        y = (dialog.winfo_screenheight() - height) // 2
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog_bg = dialog.cget("bg")

        tk.Label(
            dialog,
            text="Selecione as opcoes que devem constar na proposta:",
            bg=dialog_bg,
            anchor="w",
        ).pack(anchor="w", padx=12, pady=(12, 8))

        vars_by_code: dict[str, tk.BooleanVar] = {}
        saved_codes = set(self.case_data.propostas_selecionadas)
        for modalidade in MODALIDADES:
            var = tk.BooleanVar(value=(modalidade["codigo"] in saved_codes) if saved_codes else True)
            vars_by_code[modalidade["codigo"]] = var
            tk.Checkbutton(
                dialog,
                text=f'{modalidade["codigo"]} - {modalidade["modalidade"]} ({modalidade["parcelas"]}x)',
                variable=var,
                bg=dialog_bg,
                activebackground=dialog_bg,
                selectcolor=dialog_bg,
                anchor="w",
            ).pack(anchor="w", padx=16, pady=2)

        result: dict[str, set[str] | None] = {"selected": None}

        def confirm() -> None:
            selected = {code for code, var in vars_by_code.items() if var.get()}
            if not selected:
                messagebox.showwarning("Selecao vazia", "Selecione ao menos uma opcao.", parent=dialog)
                return
            result["selected"] = selected
            dialog.destroy()

        ttk.Button(dialog, text="Confirmar", command=confirm).pack(pady=12)
        self.root.wait_window(dialog)

        selected_codes = result["selected"]
        if not selected_codes:
            return set()

        total_bloqueado = total_bloqueado_efetivo(self.case_data.subdebitos)
        has_entry_option = any(code.startswith("4.") for code in selected_codes)
        has_discount_option = any(
            modalidade["codigo"] in selected_codes and (modalidade["codigo"] == "2" or modalidade["desconto"] > 0)
            for modalidade in MODALIDADES
        )

        if total_bloqueado > 0 and has_entry_option:
            self.case_data.proposal_rules.aproveitar_bloqueio_como_entrada = messagebox.askyesno(
                "Entrada e bloqueio",
                "O valor bloqueado deve ser aproveitado como parte da entrada nas opcoes com entrada?",
                parent=self.root,
            )
        if total_bloqueado > 0 and has_discount_option:
            self.case_data.proposal_rules.desconto_sobre_total = messagebox.askyesno(
                "Desconto e bloqueio",
                "O desconto deve incidir tambem sobre o valor bloqueado?",
                parent=self.root,
            )
        return selected_codes

    def apply_general_block(self) -> None:
        self.sync_case_from_form()
        try:
            distribuir_valor_bloqueado(self.case_data)
        except Exception as exc:
            messagebox.showerror("Erro ao distribuir bloqueio", str(exc))
            return
        self.refresh_subdebitos()
        self.status_var.set(
            f"Bloqueio efetivo distribuido: {format_currency_br(total_bloqueado_efetivo(self.case_data.subdebitos))}"
        )

    def add_subdebito(self) -> None:
        novo = Subdebito(
            tipo="PRINCIPAL",
            descricao="Novo subdebito",
            referencia_origem=self.case_data.processo,
            valor_atualizado=0.0,
        )
        novo.normalize_honorarios()
        self.case_data.subdebitos.append(novo)
        self.refresh_subdebitos()

    def remove_subdebito(self) -> None:
        if not self.selected_subdebito_indices:
            return
        for index in sorted(self.selected_subdebito_indices, reverse=True):
            del self.case_data.subdebitos[index]
        self.selected_subdebito_indices = []
        self.refresh_subdebitos()
        self.clear_subdebito_form()

    def on_select_subdebito(self, _event: object) -> None:
        selected = self.tree.selection()
        if not selected:
            self.selected_subdebito_indices = []
            return
        self.selected_subdebito_indices = [int(item_id) for item_id in selected]
        item = self.case_data.subdebitos[self.selected_subdebito_indices[0]]
        for name, var in self.subdebito_vars.items():
            value = getattr(item, name)
            if name in {"valor_atualizado", "multa_art_523", "valor_bloqueado"}:
                var.set(format_decimal_br(float(value or 0.0)))
            else:
                var.set(str(value))

    def on_select_summary(self, _event: object) -> None:
        selected = self.summary_tree.selection()
        if not selected:
            self.selected_summary_key = None
            self.summary_description_var.set("")
            return
        values = self.summary_tree.item(selected[0], "values")
        self.selected_summary_key = (values[1], values[2])
        self.summary_description_var.set(values[0])

    def on_bloco_geral_focus_out(self, _event: object) -> None:
        try:
            value = parse_decimal_input(self.case_vars["valor_bloqueado_geral"].get())
        except ValueError:
            return
        self.case_vars["valor_bloqueado_geral"].set(format_decimal_br(value))

    def on_select_all_entry(self, event: object) -> None:
        widget = getattr(event, "widget", None)
        if widget is None:
            return
        self.root.after_idle(lambda: (widget.selection_range(0, "end"), widget.icursor("end")))

    def save_subdebito_edits(self) -> None:
        if len(self.selected_subdebito_indices) != 1:
            messagebox.showwarning("Selecao invalida", "Selecione apenas um subdebito para edicao individual.")
            return
        item = self.case_data.subdebitos[self.selected_subdebito_indices[0]]
        try:
            item.tipo = self.subdebito_vars["tipo"].get().strip()
            item.descricao = self.subdebito_vars["descricao"].get().strip()
            item.referencia_origem = self.subdebito_vars["referencia_origem"].get().strip()
            item.valor_atualizado = parse_decimal_input(self.subdebito_vars["valor_atualizado"].get())
            item.multa_art_523 = parse_decimal_input(self.subdebito_vars["multa_art_523"].get())
            item.valor_bloqueado = parse_decimal_input(self.subdebito_vars["valor_bloqueado"].get())
            item.ug, item.gestao = self._normalize_ug_value(self.subdebito_vars["ug"].get())
            item.gru_cr = self._normalize_gru_value(self.subdebito_vars["gru_cr"].get())
            item.normalize_honorarios()
        except ValueError:
            messagebox.showerror("Dados invalidos", "Valores numericos do subdebito sao invalidos.")
            return
        self.refresh_subdebitos()

    def update_summary_description(self) -> None:
        if not self.selected_summary_key:
            messagebox.showwarning("Selecao vazia", "Selecione um item do quadro de totais consolidados.")
            return
        descricao = self.summary_description_var.get().strip()
        if not descricao:
            messagebox.showwarning("Descricao vazia", "Informe uma descricao para o item consolidado.")
            return

        ug_gestao, gru_cr = self.selected_summary_key
        key = consolidated_description_key(ug_gestao, gru_cr)
        self.case_data.descricoes_consolidadas[key] = descricao
        self.refresh_summary()
        self.status_var.set("Descricao consolidada atualizada sem alterar os subdebitos relacionados.")

    def apply_batch_codes(self) -> None:
        if not self.selected_subdebito_indices:
            messagebox.showwarning("Selecao vazia", "Selecione um ou mais subdebitos na grade.")
            return

        ug, gestao = self._normalize_ug_value(self.batch_vars["ug"].get())
        gru_cr = self._normalize_gru_value(self.batch_vars["gru_cr"].get())
        self.batch_vars["ug"].set(ug)
        self.batch_vars["gestao"].set(gestao)
        self.batch_vars["gru_cr"].set(gru_cr)

        for index in self.selected_subdebito_indices:
            item = self.case_data.subdebitos[index]
            if ug:
                item.ug = ug
            if gestao:
                item.gestao = gestao
            if gru_cr:
                item.gru_cr = gru_cr
            item.normalize_honorarios()

        self.refresh_subdebitos()
        self.status_var.set(f"Codigos aplicados em {len(self.selected_subdebito_indices)} subdebito(s).")

    def resolve_merge_conflicts(self, conflicts: list[MergeConflict]) -> None:
        for conflict in conflicts:
            label = FIELD_LABELS.get(conflict.field_name, conflict.field_name.replace("_", " ").title())
            use_incoming = messagebox.askyesno(
                "Divergencia entre relatorios",
                (
                    f"Campo: {label}\n\n"
                    f"Valor atual:\n{conflict.current_value}\n\n"
                    f"Valor do novo relatorio:\n{conflict.incoming_value}\n\n"
                    "Deseja manter o valor do novo relatorio?"
                ),
                parent=self.root,
            )
            if not use_incoming:
                continue
            if conflict.field_name in {"multa_percentual", "valor_bloqueado_geral"}:
                setattr(self.case_data, conflict.field_name, parse_decimal_input(conflict.incoming_value))
            else:
                setattr(self.case_data, conflict.field_name, conflict.incoming_value)

    def sync_case_from_form(self) -> None:
        for field_name, _ in CASE_FIELDS:
            raw = self.case_vars[field_name].get().strip()
            if field_name in {"multa_percentual", "valor_bloqueado_geral"}:
                setattr(self.case_data, field_name, parse_decimal_input(raw))
            else:
                setattr(self.case_data, field_name, raw)
        self.case_data.condicoes_adicionais = self.notes_text.get("1.0", "end").strip()
        self._apply_case_defaults()

    def refresh_all(self) -> None:
        self._apply_case_defaults()
        for field_name, _ in CASE_FIELDS:
            value = getattr(self.case_data, field_name)
            if field_name == "multa_percentual":
                self.case_vars[field_name].set(format_decimal_br(float(value or 0.0)))
            elif field_name == "valor_bloqueado_geral":
                self.case_vars[field_name].set(format_decimal_br(float(value or 0.0)))
            else:
                self.case_vars[field_name].set(str(value))
        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", self.case_data.condicoes_adicionais)
        self._update_notes_bg()
        self.refresh_subdebitos()
        self.refresh_tcu_lancamentos()

    def refresh_subdebitos(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, subdebito in enumerate(self.case_data.subdebitos):
            subdebito.normalize_honorarios()
            tags = ("honorarios",) if subdebito.is_honorarios() else ()
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    subdebito.tipo,
                    subdebito.descricao,
                    subdebito.ug_gestao,
                    subdebito.gru_cr,
                    format_decimal_br(subdebito.valor_atualizado),
                    format_decimal_br(subdebito.multa_art_523),
                    format_decimal_br(subdebito.valor_bloqueado),
                ),
                tags=tags,
            )
        total = len(self.case_data.subdebitos)
        if total > 7:
            self.subdebito_count_var.set(f"Mostrando 7 de {total} subdebitos. Use a barra lateral para ver os demais.")
        else:
            self.subdebito_count_var.set(f"{total} subdebito(s).")
        self.refresh_summary()

    def clear_subdebito_form(self) -> None:
        for var in self.subdebito_vars.values():
            var.set("")

    def clear_case_selection_state(self) -> None:
        self.selected_subdebito_indices = []
        self.selected_summary_key = None
        self.clear_subdebito_form()
        self.summary_description_var.set("")

    def refresh_summary(self) -> None:
        consolidated = consolidar_por_chave_arrecadatoria(
            self.case_data.subdebitos,
            self.case_data.descricoes_consolidadas,
        )
        for item in self.summary_tree.get_children():
            self.summary_tree.delete(item)
        for index, item in enumerate(consolidated):
            item.normalize_honorarios()
            ug = item.ug_gestao or "-"
            gru = item.gru_cr or "-"
            item_id = f"{ug}|{gru}|{index}"

            tags = []
            if ug == "-" or gru == "-":
                tags.append("missing_code")
            if item.is_honorarios():
                tags.append("honorarios")

            self.summary_tree.insert(
                "",
                "end",
                iid=item_id,
                values=(
                    item.descricao,
                    ug,
                    gru,
                    format_currency_br(item.valor_bloqueado),
                    format_currency_br(item.valor_total),
                ),
                tags=tuple(tags),
            )
        if self.selected_summary_key:
            for row_id in self.summary_tree.get_children():
                values = self.summary_tree.item(row_id, "values")
                if values[1] == self.selected_summary_key[0] and values[2] == self.selected_summary_key[1]:
                    self.summary_tree.selection_set(row_id)
                    break
        total_geral = round(sum(item.valor_total for item in consolidated), 2)
        self.total_geral_var.set(f"Valor total geral: {format_currency_br(total_geral)}")

    def refresh_tcu_lancamentos(self) -> None:
        return


def launch_app() -> None:
    root = tk.Tk()
    root.state("zoomed")
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    MainWindow(root)
    root.mainloop()


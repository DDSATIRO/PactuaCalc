from __future__ import annotations

from dataclasses import fields
from datetime import date
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from geracordo.formatting import format_currency_br, format_decimal_br, parse_decimal_input
from geracordo.models import CaseData, Subdebito, parse_iso_date
from geracordo.parser import detect_report_type, parse_projef_report, parse_tcu_report
from geracordo.projefweb import ProjefWebAutomationError, atualizar_relatorio_projef, competencia_esta_defasada
from geracordo.proposals import MODALIDADES, create_proposal_pdf
from geracordo.services import (
    MergeConflict,
    consolidar_por_chave_arrecadatoria,
    distribuir_valor_bloqueado,
    merge_case_data,
    replace_tcu_case_data,
    total_bloqueado_efetivo,
)
from geracordo.tcuweb import TcuAutomationError, atualizar_relatorio_tcu


CASE_FIELDS = [
    ("processo", "Processo"),
    ("nup_requerimento", "NUP do requerimento"),
    ("devedor", "Devedor"),
    ("cpf_cnpj", "CPF/CNPJ"),
    ("competencia_atualizacao", "Competencia"),
    ("data_atualizacao", "Data de atualizacao"),
    ("tipo_parcela", "Tipo de parcela"),
    ("multa_percentual", "Multa (%)"),
    ("data_limite_resposta", "Data limite resposta"),
    ("data_primeira_parcela", "Data da Entrada/Primeira Parcela"),
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


class MainWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("GeraAcordo")
        self.root.geometry("1500x960")
        self.root.minsize(1360, 900)
        self.case_data = CaseData()
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
        self.selected_summary_key: tuple[str, str] | None = None

        self._build_layout()
        self.refresh_all()

    def _apply_case_defaults(self) -> None:
        if self.case_data.data_atualizacao and not self.case_data.competencia_atualizacao:
            parsed = parse_iso_date(self.case_data.data_atualizacao)
            if parsed:
                self.case_data.competencia_atualizacao = parsed.strftime("%m/%Y")
        if not self.case_data.tipo_parcela:
            self.case_data.tipo_parcela = "VARIAVEL (POS-FIXADO)"
        if self.case_data.multa_percentual <= 0:
            self.case_data.multa_percentual = 10.0

    def _build_layout(self) -> None:
        toolbar = ttk.Frame(self.root, padding=12)
        toolbar.pack(fill="x")

        tk.Button(
            toolbar,
            text="Criar a partir de Relatorio TCU/PROJEF",
            command=self.create_from_any_pdf,
            bg="#fff1b8",
            activebackground="#ffe58f",
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            toolbar,
            text="Adicionar outro relatorio TCU/PROJEF",
            command=self.add_other_report,
            bg="#fff1b8",
            activebackground="#ffe58f",
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            toolbar,
            text="Abrir rascunho anterior",
            command=self.load_json,
            bg="#fff1b8",
            activebackground="#ffe58f",
        ).pack(side="left", padx=(0, 8))
        ttk.Button(toolbar, text="Salvar Rascunho JSON", command=self.save_json).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(toolbar, text="Sair", command=self.root.destroy).pack(side="right")
        ttk.Button(toolbar, text="Sobre", command=self.show_about).pack(side="right", padx=(0, 8))

        self.status_var = tk.StringVar()
        ttk.Label(toolbar, textvariable=self.status_var).pack(side="right", padx=(0, 12))

    def show_about(self) -> None:
        about_text = (
            "Geracordo\n\n"
            "Copyright (c) 2026 ddsatiro\n"
            "Contato: ddsatiro@gmail.com\n\n"
            "Este software e de codigo aberto (Licenca MIT).\n"
            "Utiliza componentes de terceiros sob licencas permissivas (Apache 2.0 e MIT), "
            "como pdfplumber, playwright e requests.\n"
            "Consulte o arquivo THIRD_PARTY_LICENSES.txt para detalhes integrais."
        )
        messagebox.showinfo("Sobre o Geracordo", about_text)

        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        header_frame = ttk.Labelframe(main, text="Cabecalho do caso", padding=12)
        header_frame.pack(fill="x", side="top")
        self._build_header(header_frame)

        center = ttk.Panedwindow(main, orient=tk.HORIZONTAL)
        center.pack(fill="both", expand=True, side="top", pady=(12, 0))

        grid_frame = ttk.Labelframe(center, text="Subdebitos", padding=12)
        center.add(grid_frame, weight=3)
        self._build_subdebito_grid(grid_frame)

        edit_frame = ttk.Labelframe(center, text="Edicao do subdebito selecionado", padding=12)
        center.add(edit_frame, weight=2)
        self._build_subdebito_editor(edit_frame)

        notes_frame = ttk.Labelframe(main, text="Condicoes adicionais", padding=12)
        notes_frame.pack(fill="both", side="top", pady=(12, 0))
        self.notes_text = tk.Text(notes_frame, height=8, wrap="word")
        self.notes_text.pack(fill="both", expand=True)

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
            ttk.Label(parent, text=lbl_text).grid(row=row, column=col, sticky="w", padx=6, pady=4)
            
            if field_name == "tipo_parcela":
                entry = ttk.Combobox(
                    parent,
                    textvariable=self.case_vars[field_name],
                    values=["VARIAVEL (POS-FIXADO)", "FIXO (PREFIXADO)"],
                    state="readonly",
                    width=31,
                )
            else:
                entry = tk.Entry(parent, textvariable=self.case_vars[field_name], width=34, relief="groove")
            
            entry.grid(
                row=row,
                column=col + 1,
                columnspan=colspan,
                sticky="ew",
                padx=6,
                pady=4,
            )
            
            if field_name == "competencia_atualizacao":
                entry.configure(state="readonly")
            
            if field_name in mandatory_fields:
                def on_change(*args, widget=entry, var=self.case_vars[field_name]):
                    if type(widget) is tk.Entry:
                        if not var.get().strip():
                            widget.configure(bg="#ffcccc")
                        else:
                            widget.configure(bg="white")
                self.case_vars[field_name].trace_add("write", on_change)
                on_change()

            if field_name == "valor_bloqueado_geral":
                entry.bind("<FocusOut>", self.on_bloco_geral_focus_out)
                entry.bind("<FocusIn>", self.on_select_all_entry)
                entry.bind("<ButtonRelease-1>", self.on_select_all_entry)
                ttk.Button(
                    parent,
                    text="Distribuir Bloqueio",
                    command=self.apply_general_block,
                ).grid(row=row, column=8, sticky="ew", padx=(6, 0), pady=4)

        for _col in range(8):
            parent.columnconfigure(_col, weight=1)
        parent.columnconfigure(3, weight=1)
        parent.columnconfigure(5, weight=1)
        parent.columnconfigure(8, weight=0)

    def _build_subdebito_grid(self, parent: ttk.Labelframe) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
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
        self.tree.bind("<<TreeviewSelect>>", self.on_select_subdebito)

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        batch_frame = ttk.Frame(parent, padding=(0, 10, 0, 0))
        batch_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        ttk.Label(batch_frame, text="UG").grid(row=0, column=0, padx=4, pady=2, sticky="w")
        ttk.Entry(batch_frame, textvariable=self.batch_vars["ug"], width=10).grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(batch_frame, text="Gestao").grid(row=0, column=2, padx=4, pady=2, sticky="w")
        ttk.Entry(batch_frame, textvariable=self.batch_vars["gestao"], width=10).grid(row=0, column=3, padx=4, pady=2)
        ttk.Label(batch_frame, text="GRU(CR)").grid(row=0, column=4, padx=4, pady=2, sticky="w")
        ttk.Entry(batch_frame, textvariable=self.batch_vars["gru_cr"], width=12).grid(row=0, column=5, padx=4, pady=2)
        ttk.Button(batch_frame, text="Aplicar aos selecionados", command=self.apply_batch_codes).grid(
            row=0,
            column=6,
            padx=8,
            pady=2,
        )

        ttk.Label(
            batch_frame,
            text="Selecione um ou mais subdebitos na grade para preencher UG/Gestao e GRU(CR) de uma vez.",
        ).grid(row=1, column=0, columnspan=8, sticky="w", padx=4, pady=(4, 0))

        summary_frame = ttk.Labelframe(parent, text="Totais consolidados", padding=(10, 8))
        summary_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        summary_frame.columnconfigure(0, weight=1)
        self.summary_tree = ttk.Treeview(
            summary_frame,
            columns=("descricao", "ug_gestao", "gru_cr", "valor_bloqueado", "valor_total"),
            show="headings",
            height=7,
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
        ttk.Label(summary_frame, text="Descricao Consolidada").grid(row=1, column=0, sticky="w", pady=(8, 0))
        summary_editor = ttk.Frame(summary_frame)
        summary_editor.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        summary_editor.columnconfigure(0, weight=1)
        ttk.Entry(summary_editor, textvariable=self.summary_description_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(
            summary_editor,
            text="Atualizar descricao consolidada",
            command=self.update_summary_description,
        ).grid(row=0, column=1, padx=(8, 0))
        total_label = tk.Label(
            summary_frame,
            textvariable=self.total_geral_var,
            font=("Segoe UI", 15, "bold"),
            fg="#0b5d1e",
            anchor="e",
        )
        total_label.grid(row=3, column=0, columnspan=2, sticky="e", pady=(8, 0))

    def _build_subdebito_editor(self, parent: ttk.Labelframe) -> None:
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
        for idx, (field_name, label) in enumerate(editable_fields):
            ttk.Label(parent, text=label).grid(row=idx, column=0, sticky="w", padx=6, pady=4)
            if field_name == "tipo":
                cb = ttk.Combobox(
                    parent,
                    textvariable=self.subdebito_vars[field_name],
                    width=32,
                    state="readonly",
                    values=("PRINCIPAL", "HONORÁRIOS"),
                )
                cb.grid(row=idx, column=1, sticky="ew", padx=6, pady=4)
            else:
                ttk.Entry(parent, textvariable=self.subdebito_vars[field_name], width=34).grid(
                    row=idx,
                    column=1,
                    sticky="ew",
                    padx=6,
                    pady=4,
                )

        ttk.Button(parent, text="Atualizar subdebito", command=self.save_subdebito_edits).grid(
            row=len(editable_fields),
            column=0,
            columnspan=2,
            sticky="ew",
            padx=6,
            pady=(12, 4),
        )
        ttk.Button(parent, text="Adicionar subdebito", command=self.add_subdebito).grid(
            row=len(editable_fields) + 1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=6,
            pady=4,
        )
        ttk.Button(parent, text="Excluir subdebito", command=self.remove_subdebito).grid(
            row=len(editable_fields) + 2,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=6,
            pady=4,
        )
        ttk.Label(
            parent,
            text="Edicoes individuais de valor bloqueado prevalecem sobre o uso do valor geral.",
            wraplength=320,
        ).grid(row=len(editable_fields) + 3, column=0, columnspan=2, sticky="w", padx=6, pady=12)
        
        tk.Button(
            parent,
            text="GERAR OPÇÕES DA PROPOSTA",
            command=self.generate_proposal,
            bg="#d9f7be",
            activebackground="#b7eb8f",
            font=("Segoe UI", 12, "bold"),
            height=2,
            cursor="hand2",
        ).grid(row=len(editable_fields) + 4, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 12))
        
        parent.columnconfigure(1, weight=1)

    def create_from_any_pdf(self) -> None:
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
        path = filedialog.askopenfilename(
            title="Abrir rascunho anterior",
            filetypes=[("Arquivos JSON", "*.json")],
        )
        if not path:
            return
        try:
            self.case_data = CaseData.load_json(path)
            self.refresh_all()
            self.status_var.set(f"JSON carregado: {Path(path).name}")
        except Exception as exc:
            messagebox.showerror("Erro ao abrir JSON", str(exc))

    def save_json(self) -> None:
        self.sync_case_from_form()
        errors = self.case_data.validate(strict_proposal=bool(self.case_data.subdebitos))
        if errors:
            messagebox.showwarning("Validacoes pendentes", "\n".join(errors))
            return
        path = filedialog.asksaveasfilename(
            title="Salvar dados do caso",
            defaultextension=".json",
            filetypes=[("Arquivos JSON", "*.json")],
        )
        if not path:
            return
        self.case_data.save_json(path)
        self.status_var.set(f"Dados salvos em {Path(path).name}")
        messagebox.showinfo("Salvo", "Caso salvo com sucesso.")

    def generate_proposal(self) -> None:
        self.sync_case_from_form()
        errors = self.case_data.validate()
        if errors:
            messagebox.showwarning("Validacoes pendentes", "\n".join(errors))
            return
            
        if self.case_data.tipo_parcela == "FIXO (PREFIXADO)":
            try:
                from geracordo.selic_api import update_selic_history
                self.run_with_loading(
                    "Atualizando Taxas Selic",
                    "Buscando histórico atualizado de taxas Selic no Banco Central...",
                    update_selic_history,
                )
            except Exception as e:
                messagebox.showwarning("Erro na Selic", f"Nao foi possivel atualizar a base Selic. O sistema tentará usar a base local existente.\n\nDetalhes: {e}")
            
        from geracordo.services import consolidar_por_chave_arrecadatoria
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
            
        from geracordo.proposals import build_proposal_scenarios
        scenarios = build_proposal_scenarios(self.case_data, selected_codes=selected_codes)
        
        if not self.show_proposal_preview(scenarios):
            return

        import datetime
        import re
        processo_clean = re.sub(r'[\.\-]', '', self.case_data.processo) if self.case_data.processo else "SPROC"
        devedor_clean = (self.case_data.devedor or "SDEV")[:30].strip()
        timestamp = datetime.datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
        
        default_name = f"PROPOSTA-{processo_clean}-{devedor_clean}-{timestamp}.pdf"

        path = filedialog.asksaveasfilename(
            initialfile=default_name,
            title="Salvar proposta em PDF",
            defaultextension=".pdf",
            filetypes=[("Arquivos PDF", "*.pdf")],
        )
        if not path:
            return
        pdf_path = create_proposal_pdf(self.case_data, path, selected_codes=selected_codes)
        
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
        
        from geracordo.formatting import format_currency_br, format_percent_br
        
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
                from geracordo.services import total_bloqueado_efetivo
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

        ttk.Label(
            dialog,
            text="Selecione as opcoes que devem constar na proposta:",
        ).pack(anchor="w", padx=12, pady=(12, 8))

        vars_by_code: dict[str, tk.BooleanVar] = {}
        for modalidade in MODALIDADES:
            var = tk.BooleanVar(value=True)
            vars_by_code[modalidade["codigo"]] = var
            ttk.Checkbutton(
                dialog,
                text=f'{modalidade["codigo"]} - {modalidade["modalidade"]} ({modalidade["parcelas"]}x)',
                variable=var,
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
            item.ug = self.subdebito_vars["ug"].get().strip()
            item.gestao = self.subdebito_vars["gestao"].get().strip() or "00001"
            item.gru_cr = self.subdebito_vars["gru_cr"].get().strip()
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
        for item in self.case_data.subdebitos:
            if (item.ug_gestao or "-") == ug_gestao and (item.gru_cr or "-") == gru_cr:
                item.descricao = descricao
        self.refresh_subdebitos()

    def apply_batch_codes(self) -> None:
        if not self.selected_subdebito_indices:
            messagebox.showwarning("Selecao vazia", "Selecione um ou mais subdebitos na grade.")
            return

        ug = self.batch_vars["ug"].get().strip()
        gestao = self.batch_vars["gestao"].get().strip() or "00001"
        gru_cr = self.batch_vars["gru_cr"].get().strip()

        for index in self.selected_subdebito_indices:
            item = self.case_data.subdebitos[index]
            if ug:
                item.ug = ug
            if gestao:
                item.gestao = gestao
            if gru_cr:
                item.gru_cr = gru_cr

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
        self.refresh_subdebitos()
        self.refresh_tcu_lancamentos()

    def refresh_subdebitos(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, subdebito in enumerate(self.case_data.subdebitos):
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
            )
        self.refresh_summary()

    def clear_subdebito_form(self) -> None:
        for var in self.subdebito_vars.values():
            var.set("")

    def refresh_summary(self) -> None:
        consolidated = consolidar_por_chave_arrecadatoria(self.case_data.subdebitos)
        for item in self.summary_tree.get_children():
            self.summary_tree.delete(item)
        for index, item in enumerate(consolidated):
            ug = item.ug_gestao or "-"
            gru = item.gru_cr or "-"
            item_id = f"{ug}|{gru}|{index}"

            tags = ()
            if ug == "-" or gru == "-":
                tags = ("missing_code",)

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
                tags=tags,
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

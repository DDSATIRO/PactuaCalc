from __future__ import annotations

from datetime import date
from pathlib import Path
from time import sleep
import tkinter as tk

from geracordo.formatting import format_decimal_br
from geracordo.models import CaseData, TcuLancamento
from geracordo.projefweb import (
    _capture_pdf_from_existing_pages,
    _click_first_visible,
    pasta_preferencial_relatorios,
)


class TcuAutomationError(RuntimeError):
    pass


TCU_DEFAULT_URL = "https://divida.apps.tcu.gov.br/calculadora-debito"


def data_atual_tcu() -> str:
    today = date.today()
    return today.strftime("%d/%m/%Y")


def montar_payload_tcu(lancamentos: list[TcuLancamento]) -> str:
    linhas: list[str] = []
    for item in lancamentos:
        tipo = "Debito" if item.tipo_dc == "D" else "Credito"
        linhas.append(f"{item.data_evento};{format_decimal_br(item.valor)};{tipo}")
    return "\n".join(linhas)


def salvar_payload_tcu(lancamentos: list[TcuLancamento], target_dir: Path | None = None) -> Path:
    target_dir = target_dir or pasta_preferencial_relatorios()
    target = target_dir / f"lancamentos_tcu_{date.today().strftime('%Y%m%d')}.csv"
    target.write_text(montar_payload_tcu(lancamentos), encoding="utf-8")
    return target


def _copiar_para_area_de_transferencia(payload: str) -> None:
    clipboard = tk.Tk()
    clipboard.withdraw()
    clipboard.clipboard_clear()
    clipboard.clipboard_append(payload)
    clipboard.update()
    clipboard.destroy()


def _set_toggle(page, label: str, desired: bool) -> None:
    text_variants = [label, label.replace("Informacoes", "Informações").replace("geracao", "geração")]
    for variant in text_variants:
        try:
            toggle_root = page.locator(f"text={variant}").locator("..")
            checkbox = toggle_root.locator("input[type='checkbox']").first
            if checkbox.count():
                if desired:
                    checkbox.check(force=True)
                else:
                    checkbox.uncheck(force=True)
                return
        except Exception:
            continue

    script = """
    (label) => {
        const normalize = (value) =>
            (value || "")
                .normalize("NFD")
                .replace(/[\\u0300-\\u036f]/g, "")
                .replace(/\\s+/g, " ")
                .trim()
                .toLowerCase();
        const visible = (el) => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
        };
        const target = normalize(label);
        const labelNodes = Array.from(document.querySelectorAll("label, span, div"))
            .filter((el) => visible(el) && normalize(el.textContent).includes(target));
        const checkboxes = Array.from(document.querySelectorAll("input[type='checkbox']"))
            .filter((el) => visible(el));
        let checkboxIndex = -1;
        let bestDistance = Number.POSITIVE_INFINITY;
        for (const labelNode of labelNodes) {
            const labelRect = labelNode.getBoundingClientRect();
            for (const [index, candidate] of checkboxes.entries()) {
                const rect = candidate.getBoundingClientRect();
                const distance = Math.abs(rect.left - labelRect.left) + Math.abs(rect.top - labelRect.top);
                if (distance < bestDistance) {
                    bestDistance = distance;
                    checkboxIndex = index;
                }
            }
        }
        return checkboxIndex;
    }
    """
    index = int(page.evaluate(script, label))
    if index < 0:
        raise TcuAutomationError(f"Nao consegui localizar o botao '{label}' no site do TCU.")
    checkbox = page.locator("input[type='checkbox']").nth(index)
    try:
        if desired:
            checkbox.check(force=True)
        else:
            checkbox.uncheck(force=True)
    except Exception:
        try:
            checkbox.click(force=True)
        except Exception as exc:
            raise TcuAutomationError(f"Nao consegui acionar o botao '{label}' no site do TCU.") from exc


def _fill_input_by_label(page, label: str, value: str) -> None:
    script = """
    ({ label, value }) => {
        const normalize = (text) =>
            (text || "")
                .normalize("NFD")
                .replace(/[\\u0300-\\u036f]/g, "")
                .replace(/\\s+/g, " ")
                .trim()
                .toLowerCase();
        const visible = (el) => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
        };
        const target = normalize(label);
        const labels = Array.from(document.querySelectorAll("label"))
            .filter((el) => normalize(el.textContent).includes(target));
        for (const labelNode of labels) {
            const forId = labelNode.getAttribute("for");
            if (forId) {
                const direct = document.getElementById(forId);
                if (direct && visible(direct) && !direct.disabled) {
                    direct.focus();
                    direct.value = "";
                    direct.dispatchEvent(new Event("input", { bubbles: true }));
                    direct.value = value;
                    direct.dispatchEvent(new Event("input", { bubbles: true }));
                    direct.dispatchEvent(new Event("change", { bubbles: true }));
                    direct.dispatchEvent(new Event("blur", { bubbles: true }));
                    return true;
                }
            }
        }
        const looseLabels = Array.from(document.querySelectorAll("label, span, div"))
            .filter((el) => visible(el) && normalize(el.textContent).includes(target));
        let best = null;
        let bestDistance = Number.POSITIVE_INFINITY;
        const inputs = Array.from(document.querySelectorAll("input, textarea"))
            .filter((el) => !el.disabled && visible(el));
        for (const candidateLabel of looseLabels) {
            const labelRect = candidateLabel.getBoundingClientRect();
            for (const input of inputs) {
                const rect = input.getBoundingClientRect();
                const distance = Math.abs(rect.top - labelRect.bottom) + Math.abs(rect.left - labelRect.left);
                if (distance < bestDistance) {
                    bestDistance = distance;
                    best = input;
                }
            }
        }
        if (!best) return false;
        best.focus();
        if ("value" in best) {
            best.value = "";
            best.dispatchEvent(new Event("input", { bubbles: true }));
            best.value = value;
            best.dispatchEvent(new Event("input", { bubbles: true }));
            best.dispatchEvent(new Event("change", { bubbles: true }));
            best.dispatchEvent(new Event("blur", { bubbles: true }));
            return true;
        }
        return false;
    }
    """
    if not page.evaluate(script, {"label": label, "value": value}):
        raise TcuAutomationError(f"Nao consegui localizar o campo '{label}' no site do TCU.")


def _expand_optional_info_tcu(page) -> None:
    try:
        page.locator("input[type='checkbox']").last.check(force=True)
    except Exception:
        _set_toggle(page, "Informacoes opcionais para geracao de demonstrativo", True)
    try:
        page.locator("#responsavel").wait_for(state="visible", timeout=4000)
    except Exception as exc:
        raise TcuAutomationError(
            "Nao consegui expandir o bloco 'Informacoes opcionais para geracao de demonstrativo'."
        ) from exc


def _fill_optional_field_tcu(page, label: str, value: str) -> None:
    if not value:
        return
    try:
        page.get_by_label(label).fill(value)
        return
    except Exception:
        pass
    _fill_input_by_label(page, label, value)


def _importar_csv_tcu(page, csv_path: Path) -> bool:
    try:
        page.get_by_text("Importar", exact=True).click(timeout=3000)
        with page.expect_file_chooser(timeout=5000) as file_info:
            page.get_by_text("Somente parcelas CSV/TXT", exact=True).click(timeout=3000)
        chooser = file_info.value
        chooser.set_files(str(csv_path))
        page.wait_for_timeout(800)
        page.get_by_text("Incluir parcelas", exact=True).click(timeout=3000)
        page.wait_for_timeout(1200)
        return not page.get_by_text("Nenhuma parcela informada", exact=False).first.is_visible(timeout=1500)
    except Exception:
        return False


def _set_tipo_lancamento(page, tipo_texto: str) -> None:
    try:
        page.locator("select").first.select_option(label=tipo_texto, timeout=1500)
        return
    except Exception:
        pass

    try:
        combo = page.get_by_role("combobox").first
        combo.click(timeout=1500)
        try:
            combo.select_option(label=tipo_texto, timeout=1500)
            return
        except Exception:
            pass
    except Exception:
        pass

    dropdown_opened = page.evaluate(
        """
        (label) => {
            const normalize = (text) =>
                (text || "")
                    .normalize("NFD")
                    .replace(/[\\u0300-\\u036f]/g, "")
                    .replace(/\\s+/g, " ")
                    .trim()
                    .toLowerCase();
            const visible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
            };
            const target = normalize(label);
            const labels = Array.from(document.querySelectorAll("label, span, div"))
                .filter((el) => visible(el) && normalize(el.textContent) === target);
            const controls = Array.from(
                document.querySelectorAll("select, [role='combobox'], button, input, div")
            ).filter((el) => visible(el));
            let best = null;
            let bestDistance = Number.POSITIVE_INFINITY;
            for (const labelNode of labels) {
                const labelRect = labelNode.getBoundingClientRect();
                for (const control of controls) {
                    const rect = control.getBoundingClientRect();
                    const distance =
                        Math.abs(rect.top - labelRect.bottom) + Math.abs(rect.left - labelRect.left);
                    if (distance < bestDistance) {
                        bestDistance = distance;
                        best = control;
                    }
                }
            }
            if (!best) return false;
            best.click();
            return true;
        }
        """,
        "Tipo",
    )
    if not dropdown_opened:
        raise TcuAutomationError("Nao consegui localizar o campo 'Tipo' no site do TCU.")

    try:
        _click_first_visible(page, [tipo_texto, tipo_texto.capitalize(), tipo_texto.upper()], timeout=3000)
        return
    except Exception:
        pass

    option_selected = page.evaluate(
        """
        (value) => {
            const normalize = (text) =>
                (text || "")
                    .normalize("NFD")
                    .replace(/[\\u0300-\\u036f]/g, "")
                    .replace(/\\s+/g, " ")
                    .trim()
                    .toLowerCase();
            const visible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
            };
            const target = normalize(value);
            const match = Array.from(document.querySelectorAll("li, div, span, button"))
                .find((el) => visible(el) && normalize(el.textContent) === target);
            if (!match) return false;
            match.click();
            return true;
        }
        """,
        tipo_texto,
    )
    if not option_selected:
        raise TcuAutomationError(f"Nao consegui selecionar o tipo '{tipo_texto}' no site do TCU.")


def _add_parcelas_individualmente(page, lancamentos: list[TcuLancamento]) -> None:
    for item in lancamentos:
        _fill_input_by_label(page, "Data", item.data_evento)
        _fill_input_by_label(page, "Valor", format_decimal_br(item.valor))
        tipo_texto = "Debito" if item.tipo_dc == "D" else "Credito"
        _set_tipo_lancamento(page, tipo_texto)
        _click_first_visible(page, ["Incluir Parcela"])
        sleep(0.2)


def atualizar_relatorio_tcu(case_data: CaseData) -> Path:
    if not case_data.lancamentos_tcu:
        raise TcuAutomationError("Nao existem lancamentos TCU na memoria para este caso. Importe um relatorio TCU previamente gerado primeiro.")
    if not case_data.lancamentos_tcu:
        raise TcuAutomationError("Nao encontrei lancamentos do relatorio TCU para reenviar ao site.")

    try:
        from playwright.sync_api import TimeoutError, sync_playwright
    except Exception as exc:
        raise TcuAutomationError(f"Playwright indisponivel: {exc}") from exc

    download_dir = pasta_preferencial_relatorios()
    
    import re
    from datetime import datetime
    processo_clean = re.sub(r'[\.\-]', '', case_data.processo) if case_data.processo else "SPROC"
    devedor_clean = (case_data.devedor or "SDEV")[:30].strip()
    timestamp = datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
    
    filename = f"Demonstrativo-TCU-{processo_clean}-{devedor_clean}-{timestamp}.pdf"
    target = download_dir / filename
    
    payload = montar_payload_tcu(case_data.lancamentos_tcu)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        
        try:
            page.goto(TCU_DEFAULT_URL, wait_until="domcontentloaded")

            _fill_input_by_label(page, "Data atualizacao", data_atual_tcu())
            _set_toggle(page, "Incluir juros", case_data.incluir_juros_tcu)

            payload_file = salvar_payload_tcu(case_data.lancamentos_tcu, download_dir)
            try:
                _copiar_para_area_de_transferencia(payload)
            except Exception:
                pass
            if not _importar_csv_tcu(page, payload_file):
                raise TcuAutomationError(
                    "Nao consegui importar os lancamentos em lote pelo menu 'Importar > Somente parcelas CSV/TXT'. "
                    f"Os dados foram preparados em '{payload_file}' e tambem copiados para a area de transferencia."
                )

            _expand_optional_info_tcu(page)
            if case_data.devedor or case_data.cpf_cnpj:
                responsavel = " - ".join(part for part in [case_data.devedor, case_data.cpf_cnpj] if part)
                _fill_optional_field_tcu(page, "Responsável", responsavel)
            if case_data.funcao_tcu:
                _fill_optional_field_tcu(page, "Função", case_data.funcao_tcu)
            origem_debito = case_data.origem_debito_tcu or " | ".join(
                part
                for part in [
                    case_data.processo,
                    case_data.nup_requerimento,
                    case_data.data_limite_resposta and f"Data limite: {case_data.data_limite_resposta}",
                    case_data.data_primeira_parcela and f"Entrada/1a parcela: {case_data.data_primeira_parcela}",
                    case_data.tipo_parcela,
                ]
                if part
            )
            if origem_debito:
                _fill_optional_field_tcu(page, "Origem do débito", origem_debito)

            _click_first_visible(page, ["Calcular Saldo"])
            page.wait_for_timeout(1500)

            try:
                with page.expect_download(timeout=12000) as download_info:
                    page.get_by_text("Gerar Demonstrativo", exact=True).click()
                download = download_info.value
                target = download_dir / (download.suggested_filename or target.name)
                try:
                    download.save_as(target)
                except PermissionError:
                    import time
                    target = target.with_name(f"{target.stem}_{int(time.time())}{target.suffix}")
                    download.save_as(target)
                if not target.exists() or target.stat().st_size == 0:
                    raise TcuAutomationError(
                        f"O navegador informou download, mas o arquivo nao ficou salvo em '{target}'."
                    )
                browser.close()
                return target
            except TimeoutError as exc:
                if _capture_pdf_from_existing_pages(page.context, target):
                    browser.close()
                    return target
                try:
                    _click_first_visible(page, ["Gerar Demonstrativo PDF", "Gerar Demonstrativo"])
                    page.wait_for_timeout(2000)
                    if _capture_pdf_from_existing_pages(page.context, target):
                        browser.close()
                        return target
                except Exception:
                    pass
                raise TcuAutomationError(
                    "O demonstrativo TCU foi solicitado, mas nao consegui capturar o PDF nem por download nem por nova aba."
                ) from exc
                
        except Exception as e:
            from geracordo.projefweb import _registrar_screenshot_erro
            _registrar_screenshot_erro(page, "erro_tcu", download_dir)
            browser.close()
            raise e

from __future__ import annotations

from datetime import date
import os
from pathlib import Path
from time import sleep

from geracordo.models import CaseData


class ProjefWebAutomationError(RuntimeError):
    pass


PROJEFWEB_DEFAULT_URL = "https://www.jfrs.jus.br/projefweb/"


def competencia_esta_defasada(competencia: str) -> bool:
    try:
        month_str, year_str = competencia.split("/")
        competencia_date = date(int(year_str), int(month_str), 1)
    except Exception:
        return False
    today = date.today().replace(day=1)
    return competencia_date < today


def competencia_atual() -> str:
    today = date.today()
    return f"{today.month:02d}/{today.year}"


def data_base_para_atualizacao(case_data: CaseData) -> str:
    competencia = competencia_atual()
    if case_data.competencia_atualizacao and not competencia_esta_defasada(case_data.competencia_atualizacao):
        competencia = case_data.competencia_atualizacao
    return competencia


def pasta_preferencial_relatorios() -> Path:
    home = Path.home()
    one_drive = Path(os.environ.get("OneDrive", "")).expanduser() if os.environ.get("OneDrive") else None
    candidates = [
        home / "Downloads",
        home / "Desktop",
        home / "Area de Trabalho",
    ]
    if one_drive:
        candidates.extend(
            [
                one_drive / "Downloads",
                one_drive / "Desktop",
                one_drive / "Area de Trabalho",
            ]
        )
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            test_file = candidate / ".geracordo_write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            return candidate
        except Exception:
            continue
    raise ProjefWebAutomationError(
        "Nao consegui acessar nem a pasta Downloads nem a Area de Trabalho para salvar o relatorio."
    )


def _write_pdf_bytes(target: Path, payload: bytes) -> bool:
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return target.exists() and target.stat().st_size > 0
    except Exception:
        return False


def _click_first_visible(page, labels: list[str], timeout: int = 5000) -> None:
    for label in labels:
        candidates = [
            page.get_by_role("button", name=label),
            page.get_by_role("link", name=label),
            page.get_by_text(label, exact=True),
            page.locator(f"xpath=//input[@value='{label}']"),
            page.locator(
                "xpath=//*[self::a or self::span or self::div or self::td or self::button]"
                f"[normalize-space()='{label}']"
            ),
        ]
        for candidate in candidates:
            try:
                candidate.first.wait_for(state="visible", timeout=timeout)
                candidate.first.click(timeout=timeout)
                return
            except Exception:
                continue
    raise ProjefWebAutomationError(f"Nao consegui localizar o comando esperado: {', '.join(labels)}.")


def _click_first_locator(page, selectors: list[str], timeout: int = 5000) -> None:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=timeout)
            locator.click(timeout=timeout)
            return
        except Exception:
            continue
    raise ProjefWebAutomationError("Nao consegui localizar o elemento esperado no ProjefWeb.")


def _fill_first_visible(page, selectors: list[str], value: str, timeout: int = 5000) -> None:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=timeout)
            locator.fill("")
            locator.fill(value)
            return
        except Exception:
            continue
    raise ProjefWebAutomationError("Nao consegui localizar o campo esperado para preenchimento no ProjefWeb.")


def _overwrite_first_visible(page, selectors: list[str], value: str, timeout: int = 5000) -> None:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=timeout)
            locator.click(timeout=timeout)
            try:
                locator.press("Control+A", timeout=timeout)
            except Exception:
                pass
            locator.fill("", timeout=timeout)
            locator.type(value, delay=80, timeout=timeout)
            locator.dispatch_event("input")
            locator.dispatch_event("change")
            locator.dispatch_event("blur")
            return
        except Exception:
            continue
    raise ProjefWebAutomationError("Nao consegui sobrescrever o campo esperado no ProjefWeb.")


def _wait_for_dialog_with_text(page, text_snippet: str, timeout: int = 5000) -> None:
    dialog_candidates = [
        page.locator(
            "xpath=//*[contains(@class, 'x-window') or contains(@class, 'x-panel') or contains(@class, 'x-layer')]"
            f"[contains(normalize-space(.), '{text_snippet}')]"
        ).first,
        page.get_by_text(text_snippet, exact=False).first,
    ]
    for candidate in dialog_candidates:
        try:
            candidate.wait_for(state="visible", timeout=timeout)
            return
        except Exception:
            continue
    raise ProjefWebAutomationError(f"Nao consegui localizar a janela esperada do ProjefWeb com o texto '{text_snippet}'.")


def _click_text_via_dom(page, text_snippet: str) -> None:
    script = """
    (snippet) => {
        const normalize = (value) =>
            (value || "")
                .normalize("NFD")
                .replace(/[\\u0300-\\u036f]/g, "")
                .replace(/\\s+/g, " ")
                .trim()
                .toLowerCase();
        const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
        };
        const target = normalize(snippet);
        const elements = Array.from(document.querySelectorAll("a, span, div, td, button"));
        const exactMatch = elements.find((el) => isVisible(el) && normalize(el.textContent) === target);
        const partialMatch = elements.find((el) => isVisible(el) && normalize(el.textContent).includes(target));
        const match = exactMatch || partialMatch;
        if (!match) {
            return false;
        }
        match.click();
        return true;
    }
    """
    if not page.evaluate(script, text_snippet):
        raise ProjefWebAutomationError(f"Nao consegui clicar no texto '{text_snippet}' no ProjefWeb.")


def _text_visible_in_page(page, text_snippet: str) -> bool:
    script = """
    (snippet) => {
        const normalize = (value) =>
            (value || "")
                .normalize("NFD")
                .replace(/[\\u0300-\\u036f]/g, "")
                .replace(/\\s+/g, " ")
                .trim()
                .toLowerCase();
        const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
        };
        const target = normalize(snippet);
        return Array.from(document.querySelectorAll("body *")).some(
            (el) => isVisible(el) && normalize(el.textContent).includes(target)
        );
    }
    """
    return bool(page.evaluate(script, text_snippet))


def _click_tab_and_confirm(page, tab_text: str, expected_text: str, wait_seconds: float = 0.8) -> None:
    _click_text_via_dom(page, tab_text)
    sleep(wait_seconds)
    if not _text_visible_in_page(page, expected_text):
        raise ProjefWebAutomationError(
            f"Nao consegui confirmar a abertura da aba '{tab_text}'. O texto esperado '{expected_text}' nao ficou visivel."
        )


def _fill_input_next_to_text(page, text_snippet: str, value: str) -> None:
    script = """
    ({ snippet, value }) => {
        const normalize = (text) =>
            (text || "")
                .normalize("NFD")
                .replace(/[\\u0300-\\u036f]/g, "")
                .replace(/\\s+/g, " ")
                .trim()
                .toLowerCase();
        const target = normalize(snippet);
        const elements = Array.from(document.querySelectorAll("td, label, span, div"));
        for (const el of elements) {
            if (!normalize(el.textContent).includes(target)) {
                continue;
            }
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
            walker.currentNode = el;
            let current = el;
            while (current) {
                if (current.tagName === "INPUT" && current.type !== "hidden" && !current.disabled) {
                    current.focus();
                    current.value = "";
                    current.dispatchEvent(new Event("input", { bubbles: true }));
                    current.value = value;
                    current.dispatchEvent(new Event("input", { bubbles: true }));
                    current.dispatchEvent(new Event("change", { bubbles: true }));
                    return true;
                }
                current = walker.nextNode();
            }
            const container = el.parentElement;
            if (!container) {
                continue;
            }
            const input = container.querySelector("input:not([type='hidden']):not([disabled])");
            if (input) {
                input.focus();
                input.value = "";
                input.dispatchEvent(new Event("input", { bubbles: true }));
                input.value = value;
                input.dispatchEvent(new Event("input", { bubbles: true }));
                input.dispatchEvent(new Event("change", { bubbles: true }));
                return true;
            }
        }
        return false;
    }
    """
    if not page.evaluate(script, {"snippet": text_snippet, "value": value}):
        raise ProjefWebAutomationError(f"Nao consegui localizar o campo vinculado a '{text_snippet}' no ProjefWeb.")


def _overwrite_masked_input_next_to_text(page, text_snippet: str, value: str) -> None:
    script = """
    ({ snippet, value }) => {
        const normalize = (text) =>
            (text || "")
                .normalize("NFD")
                .replace(/[\\u0300-\\u036f]/g, "")
                .replace(/\\s+/g, " ")
                .trim()
                .toLowerCase();
        const target = normalize(snippet);
        const visible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
        };
        const candidates = Array.from(document.querySelectorAll("input"))
            .filter((input) => input.type !== "hidden" && !input.disabled && visible(input));

        const labels = Array.from(document.querySelectorAll("td, label, span, div"))
            .filter((el) => visible(el) && normalize(el.textContent).includes(target));

        let bestInput = null;
        let bestDistance = Number.POSITIVE_INFINITY;
        for (const label of labels) {
            const labelRect = label.getBoundingClientRect();
            for (const input of candidates) {
                const inputRect = input.getBoundingClientRect();
                const distance = Math.abs(inputRect.top - labelRect.top) + Math.abs(inputRect.left - labelRect.right);
                if (distance < bestDistance) {
                    bestDistance = distance;
                    bestInput = input;
                }
            }
        }

        if (!bestInput) {
            return false;
        }

        bestInput.focus();
        bestInput.select?.();
        bestInput.value = "";
        bestInput.dispatchEvent(new Event("input", { bubbles: true }));
        bestInput.value = value;
        bestInput.dispatchEvent(new Event("input", { bubbles: true }));
        bestInput.dispatchEvent(new Event("keyup", { bubbles: true }));
        bestInput.dispatchEvent(new Event("change", { bubbles: true }));
        bestInput.dispatchEvent(new Event("blur", { bubbles: true }));
        return true;
    }
    """
    if not page.evaluate(script, {"snippet": text_snippet, "value": value}):
        raise ProjefWebAutomationError(f"Nao consegui sobrescrever o campo vinculado a '{text_snippet}' no ProjefWeb.")


def _wait_for_input_value(page, selectors: list[str], expected_value: str, timeout: int = 5000) -> None:
    normalize = lambda value: (value or "").replace(" ", "").strip()
    expected = normalize(expected_value)
    end_time = page.evaluate("Date.now()") + timeout
    while page.evaluate("Date.now()") < end_time:
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                value = locator.input_value(timeout=250)
                if normalize(value) == expected:
                    return
            except Exception:
                continue
        page.wait_for_timeout(150)
    raise ProjefWebAutomationError(
        f"O campo de data-base nao refletiu o valor esperado '{expected_value}' antes de seguir."
    )


def _commit_input_value(page, selectors: list[str]) -> None:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            locator.focus(timeout=250)
            locator.dispatch_event("change")
            locator.dispatch_event("blur")
            return
        except Exception:
            continue


def _save_pdf_from_page(pdf_page, target: Path) -> bool:
    url = (pdf_page.url or "").strip()
    if url.lower().startswith("data:application/pdf"):
        try:
            header, encoded = url.split(",", 1)
            if ";base64" in header:
                import base64

                return _write_pdf_bytes(target, base64.b64decode(encoded))
        except Exception:
            return False

    if url.lower().startswith("blob:"):
        try:
            payload = pdf_page.evaluate(
                """
                async () => {
                    const response = await fetch(window.location.href);
                    const buffer = await response.arrayBuffer();
                    const bytes = Array.from(new Uint8Array(buffer));
                    return bytes;
                }
                """
            )
            if payload:
                return _write_pdf_bytes(target, bytes(payload))
        except Exception:
            return False

    if url:
        try:
            response = pdf_page.context.request.get(url)
            if response.ok:
                body = response.body()
                content_type = (response.headers.get("content-type", "") or "").lower()
                if "application/pdf" in content_type or body.startswith(b"%PDF"):
                    return _write_pdf_bytes(target, body)
        except Exception:
            pass

    try:
        embed = pdf_page.locator("embed, iframe").first
        src = embed.get_attribute("src", timeout=1500) or ""
        if src:
            if src.lower().startswith("blob:"):
                payload = pdf_page.evaluate(
                    """
                    async (blobUrl) => {
                        const response = await fetch(blobUrl);
                        const buffer = await response.arrayBuffer();
                        const bytes = Array.from(new Uint8Array(buffer));
                        return bytes;
                    }
                    """,
                    src,
                )
                if payload:
                    return _write_pdf_bytes(target, bytes(payload))
            response = pdf_page.context.request.get(src)
            if response.ok:
                body = response.body()
                content_type = (response.headers.get("content-type", "") or "").lower()
                if "application/pdf" in content_type or body.startswith(b"%PDF"):
                    return _write_pdf_bytes(target, body)
    except Exception:
        return False
    return False


def _capture_pdf_from_existing_pages(context, target: Path) -> bool:
    for candidate_page in reversed(context.pages):
        if _save_pdf_from_page(candidate_page, target):
            return True
    return False


def atualizar_relatorio_projef(case_data: CaseData) -> Path:
    if not case_data.identificador_projef:
        raise ProjefWebAutomationError("Nao foi encontrado identificador do calculo no relatorio.")

    projef_url = os.environ.get("PROJEFWEB_URL", "").strip() or PROJEFWEB_DEFAULT_URL

    try:
        from playwright.sync_api import TimeoutError, sync_playwright
    except Exception as exc:
        raise ProjefWebAutomationError(f"Playwright indisponivel: {exc}") from exc

    download_dir = pasta_preferencial_relatorios()
    target_data_base = data_base_para_atualizacao(case_data)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.goto(projef_url, wait_until="domcontentloaded")

        _click_first_visible(page, ["Abrir"])
        _wait_for_dialog_with_text(page, "Identificador")

        identificador_selectors = [
            "xpath=//*[contains(@class, 'x-window') or contains(@class, 'x-panel') or contains(@class, 'x-layer')][.//*[contains(normalize-space(.), 'Identificador')]]//input[not(@type='hidden')][1]",
            "xpath=//*[contains(normalize-space(.), 'Identificador (8 letras e algarismos)')]/following::input[1]",
            "input[name*=identificador i]",
            "input[id*=identificador i]",
            "input[placeholder*=identificador i]",
            "input[type=text]",
        ]
        _fill_first_visible(page, identificador_selectors, case_data.identificador_projef)
        _click_first_locator(
            page,
            [
                "xpath=//*[contains(@class, 'x-window') or contains(@class, 'x-panel') or contains(@class, 'x-layer')][.//*[contains(normalize-space(.), 'Identificador')]]//input[@value='OK']",
                "xpath=//*[contains(@class, 'x-window') or contains(@class, 'x-panel') or contains(@class, 'x-layer')][.//*[contains(normalize-space(.), 'Identificador')]]//*[self::button or self::span or self::div][normalize-space()='OK']",
            ],
        )

        sleep(1.5)

        _click_tab_and_confirm(page, "Correcao Monetaria", "Atualizar para")

        try:
            _overwrite_masked_input_next_to_text(page, "Atualizar para", target_data_base)
        except ProjefWebAutomationError:
            _fill_input_next_to_text(page, "Atualizar para", target_data_base)

        data_base_selectors = [
            "xpath=//*[contains(normalize-space(), 'Atualizar para')]/following::input[1]",
            "xpath=//td[contains(normalize-space(), 'Atualizar para')]/following::input[1]",
            "xpath=//label[contains(normalize-space(), 'Atualizar para')]/following::input[1]",
            "xpath=//input[contains(@value, '/20') and not(@type='hidden')]",
            "xpath=(//input[@type='text' and not(@readonly) and not(@disabled)])[last()]",
            "input[name*=atualizar i]",
            "input[id*=atualizar i]",
        ]

        _wait_for_input_value(page, data_base_selectors, target_data_base, timeout=5000)
        _commit_input_value(page, data_base_selectors)
        page.wait_for_timeout(2000)

        _click_tab_and_confirm(page, "Dados Finais", "Calcular")

        suggested_name = f"projef_{case_data.identificador_projef}.pdf"
        target = download_dir / suggested_name

        try:
            with page.expect_download(timeout=12000) as download_info:
                try:
                    _click_first_locator(
                        page,
                        [
                            "xpath=//input[@value='Calcular']",
                            "xpath=//*[self::a or self::span or self::div or self::td or self::button][normalize-space()='Calcular']",
                        ],
                    )
                except ProjefWebAutomationError:
                    _click_text_via_dom(page, "Calcular")
            download = download_info.value
            target = download_dir / (download.suggested_filename or suggested_name)
            download.save_as(target)
            if not target.exists() or target.stat().st_size == 0:
                raise ProjefWebAutomationError(
                    f"O navegador informou download, mas o arquivo nao ficou salvo em '{target}'."
                )
            browser.close()
            return target
        except TimeoutError as exc:
            if _capture_pdf_from_existing_pages(page.context, target):
                browser.close()
                return target
            try:
                with page.context.expect_page(timeout=8000) as popup_info:
                    try:
                        _click_first_locator(
                            page,
                            [
                                "xpath=//input[@value='Calcular']",
                                "xpath=//*[self::a or self::span or self::div or self::td or self::button][normalize-space()='Calcular']",
                            ],
                        )
                    except ProjefWebAutomationError:
                        _click_text_via_dom(page, "Calcular")
                pdf_page = popup_info.value
                pdf_page.wait_for_load_state("domcontentloaded", timeout=10000)
                if _save_pdf_from_page(pdf_page, target):
                    browser.close()
                    return target
            except Exception:
                pass

            browser.close()
            raise ProjefWebAutomationError(
                "O comando 'Calcular' foi acionado, mas nao consegui capturar o PDF nem por download nem por nova aba do navegador."
            ) from exc

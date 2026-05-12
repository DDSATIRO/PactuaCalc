from __future__ import annotations


def format_decimal_br(value: float, places: int = 2) -> str:
    formatted = f"{value:,.{places}f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def format_currency_br(value: float) -> str:
    return f"R$ {format_decimal_br(value, 2)}"


def format_percent_br(value: float) -> str:
    return f"{format_decimal_br(value, 2)}%"


def parse_decimal_input(value: str) -> float:
    cleaned = (value or "").strip()
    if not cleaned:
        return 0.0
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    return float(cleaned)

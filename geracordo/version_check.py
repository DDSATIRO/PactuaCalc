"""Verificacao remota de versao do Geracordo.

Ao iniciar o app, consulta o arquivo version.json hospedado no GitHub
para verificar se a versao local ainda e permitida. Se a versao local
for inferior a `min_version`, o app exibe um aviso e se recusa a abrir.

Se nao houver internet, o app abre normalmente (degradacao graciosa).
"""

from __future__ import annotations

APP_VERSION = "1.0.0"

_VERSION_URL = (
    "https://raw.githubusercontent.com/DDSATIRO/Geracordo/main/version.json"
)


def _parse_version(v: str) -> tuple[int, ...]:
    """Converte '1.2.3' em (1, 2, 3) para comparacao."""
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except Exception:
        return (0, 0, 0)


def verificar_versao() -> tuple[bool, str]:
    """Retorna (permitido, mensagem).

    - permitido=True  → app pode abrir normalmente.
    - permitido=False → app deve exibir a mensagem e encerrar.
    """
    try:
        import json
        import requests

        resp = requests.get(_VERSION_URL, timeout=5)
        resp.raise_for_status()
        data = json.loads(resp.text)

        min_version = data.get("min_version", "0.0.0")
        mensagem = data.get("mensagem", "").strip()

        if _parse_version(APP_VERSION) < _parse_version(min_version):
            if not mensagem:
                mensagem = (
                    f"Esta versao ({APP_VERSION}) esta desatualizada.\n"
                    f"A versao minima permitida e {min_version}.\n\n"
                    "Solicite a versao atualizada ao desenvolvedor."
                )
            return False, mensagem

    except Exception:
        # Sem internet ou erro de rede: permite uso normal.
        pass

    return True, ""

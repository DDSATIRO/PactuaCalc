"""Verificacao remota de versao do Geracordo.

Ao iniciar o app, consulta o arquivo version.json hospedado no GitHub
para verificar se a versao local ainda e permitida. Se a versao local
for inferior a `min_version`, o app exibe um aviso e se recusa a abrir.

Se nao houver internet, o app abre normalmente (degradacao graciosa).
"""

from __future__ import annotations

APP_VERSION = "1.0.0"

_VERSION_URL = (
    "https://raw.githubusercontent.com/DDSATIRO/PactuaCalc/main/version.json"
)


def _parse_version(v: str) -> tuple[int, ...]:
    """Converte '1.2.3' em (1, 2, 3) para comparacao."""
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except Exception:
        return (0, 0, 0)


def verificar_versao() -> tuple[bool, str, str]:
    """Retorna (permitido, mensagem_bloqueio, aviso_nova_versao).

    - permitido=True  → app pode abrir normalmente.
    - permitido=False → app deve exibir a mensagem_bloqueio e encerrar.
    - aviso_nova_versao → texto informativo (nao bloqueante) se houver
      versao mais recente disponivel. Vazio se estiver em dia.

    Regras aplicadas em ordem:
      1. Se APP_VERSION < min_version          → bloqueado (muito antigo)
      2. Se APP_VERSION em blocked_versions    → bloqueado (versao com bug)
      3. Se APP_VERSION < latest_version       → aviso gentil (nao bloqueia)
    """
    try:
        import json
        import requests

        resp = requests.get(_VERSION_URL, timeout=5)
        resp.raise_for_status()
        data = json.loads(resp.text)

        min_version = data.get("min_version", "0.0.0")
        latest_version = data.get("latest_version", "0.0.0")
        blocked_versions = data.get("blocked_versions", [])
        mensagem = data.get("mensagem", "").strip()

        # Regra 1: abaixo do piso minimo
        if _parse_version(APP_VERSION) < _parse_version(min_version):
            msg = mensagem or (
                f"Esta versao ({APP_VERSION}) e muito antiga.\n"
                f"A versao minima permitida e {min_version}.\n\n"
                "Solicite a versao atualizada ao desenvolvedor."
            )
            return False, msg, ""

        # Regra 2: versao especifica com bug (lista negra cirurgica)
        if APP_VERSION in blocked_versions:
            msg = mensagem or (
                f"A versao {APP_VERSION} foi desativada devido a um problema.\n\n"
                "Solicite a versao atualizada ao desenvolvedor."
            )
            return False, msg, ""

        # Regra 3: aviso gentil — ha versao mais nova, mas esta funciona
        aviso = ""
        if _parse_version(APP_VERSION) < _parse_version(latest_version):
            aviso = (
                f"Nova versao disponivel: {latest_version}\n"
                f"Voce esta usando: {APP_VERSION}\n\n"
                "Solicite a atualizacao ao desenvolvedor."
            )

        return True, "", aviso

    except Exception:
        # Sem internet ou erro de rede: permite uso normal.
        pass

    return True, "", ""

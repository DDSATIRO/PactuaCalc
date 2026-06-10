import json
from datetime import datetime as real_datetime

from pactuacalc import selic_api


class FixedDatetime(real_datetime):
    @classmethod
    def now(cls):
        return cls(2026, 6, 10)


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


def test_update_selic_history_replaces_recent_partial_rate(tmp_path, monkeypatch):
    cache_path = tmp_path / "selic_history.json"
    cache_path.write_text(
        json.dumps(
            [
                {"data": "01/04/2026", "valor": "1.09"},
                {"data": "01/05/2026", "valor": "0.43"},
                {"data": "01/06/2026", "valor": "0.32"},
            ]
        ),
        encoding="utf-8",
    )

    captured_params = {}

    def fake_get(_url, params, timeout):
        captured_params.update(params)
        assert timeout == 10
        return FakeResponse(
            [
                {"data": "01/05/2026", "valor": "1.07"},
                {"data": "01/06/2026", "valor": "0.32"},
            ]
        )

    monkeypatch.setattr(selic_api, "FILE_PATH", str(cache_path))
    monkeypatch.setattr(selic_api, "datetime", FixedDatetime)
    monkeypatch.setattr(selic_api.requests, "get", fake_get)

    updated = selic_api.update_selic_history()

    assert captured_params["dataInicial"] == "01/03/2026"
    assert captured_params["dataFinal"] == "10/06/2026"

    rates = {item["data"]: item["valor"] for item in updated}
    assert rates["01/04/2026"] == "1.09"
    assert rates["01/05/2026"] == "1.07"
    assert rates["01/06/2026"] == "0.32"

    saved = json.loads(cache_path.read_text(encoding="utf-8"))
    assert saved == updated

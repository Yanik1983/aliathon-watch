import importlib

from watch import config


def _reload_with(monkeypatch, value):
    monkeypatch.setenv("NTFY_SERVER", value)
    importlib.reload(config)
    return config.NTFY_SERVER


def test_empty_ntfy_server_env_falls_back_to_ntfy_sh(monkeypatch):
    # GitHub Actions sets the variable to "" when the repo variable does not exist.
    try:
        assert _reload_with(monkeypatch, "") == "https://ntfy.sh"
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_custom_ntfy_server_trailing_slash_stripped(monkeypatch):
    try:
        assert _reload_with(monkeypatch, "https://ntfy.example.org/") == "https://ntfy.example.org"
    finally:
        monkeypatch.undo()
        importlib.reload(config)

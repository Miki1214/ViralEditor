"""Tests for Control Room dev orchestration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from viral_editor import dev_runner


def test_build_api_command_includes_reload_flag() -> None:
    cmd = dev_runner.build_api_command(host="127.0.0.1", port=8765, reload=True)
    assert "--reload" in cmd
    assert "8765" in cmd


def test_require_ui_deps_missing_node_modules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(dev_runner, "WEB_DIR", web)
    monkeypatch.setattr(dev_runner.shutil, "which", lambda name: "/usr/bin/npm" if name == "npm" else None)

    with pytest.raises(dev_runner.DevStartupError, match="npm install"):
        dev_runner._require_ui_deps()


def test_run_dev_starts_api_and_ui(monkeypatch: pytest.MonkeyPatch) -> None:
    launched: list[tuple[list[str], dict[str, object]]] = []

    def fake_popen(cmd: list[str], **kwargs: object) -> MagicMock:
        launched.append((cmd, kwargs))
        proc = MagicMock()
        proc.poll.return_value = None
        proc.returncode = 0
        return proc

    monkeypatch.setattr(dev_runner, "_require_ui_deps", lambda: None)
    monkeypatch.setattr(dev_runner.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        dev_runner,
        "build_ui_command",
        lambda: ["/usr/bin/npm", "run", "dev"],
    )
    monkeypatch.setattr(dev_runner.time, "sleep", lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))

    assert dev_runner.run_dev() == 0
    assert len(launched) == 2
    assert launched[0][0][1:3] == ["-m", "uvicorn"]
    assert launched[1][0] == ["/usr/bin/npm", "run", "dev"]
    assert launched[1][1]["cwd"] == dev_runner.WEB_DIR

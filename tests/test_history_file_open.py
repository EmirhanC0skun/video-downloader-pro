from __future__ import annotations

import os

import ui.controllers.history as history_controller_module
from ui.controllers.history import HistoryControllerMixin


class _ImmediateThread:
    def __init__(self, target, daemon=False):
        self._target = target
        self.daemon = daemon

    def start(self):
        self._target()


def test_windows_media_open_uses_shell_association_without_cmd_reparsing(
    monkeypatch,
    tmp_path,
) -> None:
    media_path = tmp_path / "Film & Dizi #1.mp4"
    media_path.write_bytes(b"media")
    opened_paths: list[str] = []

    monkeypatch.setattr(history_controller_module.sys, "platform", "win32")
    monkeypatch.setattr(history_controller_module.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(
        history_controller_module.os,
        "startfile",
        lambda path: opened_paths.append(path),
        raising=False,
    )

    def reject_cmd_launch(*_args, **_kwargs):
        raise AssertionError("Windows media paths must not be reparsed by cmd.exe")

    monkeypatch.setattr(history_controller_module.subprocess, "Popen", reject_cmd_launch)

    HistoryControllerMixin._open_path_with_default_app(str(media_path))

    assert opened_paths == [os.path.normpath(str(media_path))]

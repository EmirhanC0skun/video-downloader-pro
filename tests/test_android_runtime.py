import ast
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "android_app"


def test_mobile_engine_bootstraps_core_from_android_working_directory():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import mobile_engine; "
                "assert mobile_engine.VideoDownloadEngine is not None; "
                "assert mobile_engine.resolve_film_page is not None"
            ),
        ],
        cwd=APP_DIR,
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHONPATH": ""},
    )
    assert result.returncode == 0, result.stderr


def test_quality_manifest_request_falls_back_when_curl_cffi_is_unavailable(monkeypatch):
    sys.path.insert(0, str(APP_DIR))
    try:
        from views.film_view import _request_quality_manifest
    finally:
        sys.path.remove(str(APP_DIR))

    expected_response = object()
    calls = []

    def standard_get(url, headers, timeout):
        calls.append((url, headers, timeout))
        return expected_response

    monkeypatch.setitem(sys.modules, "curl_cffi", None)
    monkeypatch.setattr(requests, "get", standard_get)

    response = _request_quality_manifest(
        "https://cdn.example/master.m3u8",
        {"Referer": "https://page.example/"},
    )

    assert response is expected_response
    assert calls == [(
        "https://cdn.example/master.m3u8",
        {"Referer": "https://page.example/"},
        12,
    )]


def test_android_lifecycle_uses_native_bridge_not_privileged_shell_commands():
    source = (APP_DIR / "mobile_engine.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_commands = {"am", "cmd", "pm", "termux-notification"}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
        ):
            continue
        constants = {
            child.value
            for child in ast.walk(node)
            if isinstance(child, ast.Constant) and isinstance(child.value, str)
        }
        assert forbidden_commands.isdisjoint(constants), ast.unparse(node)

    assert "/sys/power/wake_lock" not in source
    assert "/sys/power/wake_unlock" not in source


def test_android_manifest_permissions_follow_scoped_storage():
    config = tomllib.loads((APP_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    permissions = config["tool"]["flet"]["android"]["permission"]

    assert permissions["android.permission.INTERNET"] is True
    assert permissions["android.permission.POST_NOTIFICATIONS"] is True
    assert permissions["android.permission.FOREGROUND_SERVICE"] is True
    assert permissions["android.permission.FOREGROUND_SERVICE_DATA_SYNC"] is True
    assert permissions["android.permission.WAKE_LOCK"] is True
    assert "android.permission.MANAGE_EXTERNAL_STORAGE" not in permissions
    assert permissions["android.permission.WRITE_EXTERNAL_STORAGE"]["maxSdkVersion"] == 29


def test_android_native_service_contract_is_available():
    extension_src = APP_DIR / "extensions" / "vdpro_android_bridge" / "src"
    sys.path.insert(0, str(extension_src))
    try:
        from vdpro_android_bridge import AndroidMediaService

        expected = {
            "request_permissions",
            "start_download",
            "update_download",
            "finish_download",
            "publish_video",
            "stop_download",
        }
        assert expected.issubset(set(dir(AndroidMediaService)))
    finally:
        sys.path.remove(str(extension_src))

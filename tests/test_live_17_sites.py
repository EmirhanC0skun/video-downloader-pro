"""Opt-in field gate: 17 real resolvers and 17 bounded media downloads."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest


def _load_smoke_tool():
    path = Path(__file__).resolve().parents[1] / "tools" / "live_stream_smoke_test.py"
    spec = importlib.util.spec_from_file_location("live_stream_smoke_test_gate", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


TOOL = _load_smoke_tool()
TARGETS = TOOL.TARGETS
TARGET_IDS = [target["name"] for target in TARGETS]
LIVE_ENABLED = os.environ.get("RUN_LIVE_17") == "1"
DOWNLOAD_MIB = int(os.environ.get("LIVE_DOWNLOAD_MIB", "50"))

pytestmark = [
    pytest.mark.live17,
    pytest.mark.skipif(
        not LIVE_ENABLED,
        reason="Set RUN_LIVE_17=1 to execute real external-site checks",
    ),
]


def _diagnostic(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _resolve_with_one_fresh_retry(target):
    last_error = None
    for _attempt in range(2):
        try:
            resolved = TOOL.resolve_film_page(target["url"])
        except Exception as exc:
            last_error = exc
            continue
        if resolved and resolved.get("success"):
            return resolved
    if last_error is not None:
        raise last_error
    return resolved


def _run_with_one_resolve_retry(target, args, tmp_path):
    result = TOOL.run_target(target, args, tmp_path)
    if not result.get("resolve_ok"):
        result = TOOL.run_target(target, args, tmp_path)
    return result


@pytest.mark.parametrize("target", TARGETS, ids=TARGET_IDS)
def test_live_site_resolves_a_playable_source(target) -> None:
    resolved = _resolve_with_one_fresh_retry(target)

    assert resolved and resolved.get("success"), _diagnostic(resolved)
    assert (
        resolved.get("video_url")
        or resolved.get("video_segments")
        or resolved.get("audio_tracks")
    ), _diagnostic(resolved)


@pytest.mark.parametrize("target", TARGETS, ids=TARGET_IDS)
def test_live_site_downloads_bounded_real_media(target, tmp_path) -> None:
    args = TOOL.parse_arguments([
        "--target-mib",
        str(DOWNLOAD_MIB),
        "--primary-only",
        "--workers",
        "4",
        "--timeout",
        "30",
    ])

    result = _run_with_one_resolve_retry(target, args, tmp_path)

    assert result.get("resolve_ok"), _diagnostic(result)
    assert len(result["renditions"]) == 1, _diagnostic(result)
    assert result["renditions"][0].get("ok"), _diagnostic(result)
    assert result["renditions"][0]["downloaded_bytes"] > 0, _diagnostic(result)

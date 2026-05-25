# -*- coding: utf-8 -*-
"""tests/test_run_interactive_api.py — Flask /api/route 端點的 prep_times_min 處理。

以 stub 取代 graph 載入與 compare_algorithms，純測試 HTTP 層的驗證與參數轉發，
不觸發網路或實際路網計算。"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_interactive  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    # 避免載入真實路網
    monkeypatch.setattr(run_interactive, "get_graph_dist",
                        lambda *a, **k: (object(), object()))
    monkeypatch.setattr(run_interactive, "chinese_analysis", lambda results: "分析")
    run_interactive.app.config["TESTING"] = True
    return run_interactive.app.test_client()


def test_prep_times_forwarded_to_compare(client, monkeypatch):
    """POST 的 prep_times_min 應原樣轉發給 compare_algorithms。"""
    captured = {}

    def fake_compare(graph, dist, pickups, dropoffs, start, speed_mps, prep_times_min):
        captured["prep_times_min"] = prep_times_min
        captured["pickups"] = pickups
        return []

    monkeypatch.setattr(run_interactive, "compare_algorithms", fake_compare)
    resp = client.post("/api/route", json={
        "pickups": [[25.0, 121.0], [25.1, 121.1]],
        "dropoffs": [[25.2, 121.2], [25.3, 121.3]],
        "prep_times_min": [12, 5],
        "speed_mps": 5.0,
    })
    assert resp.status_code == 200
    assert captured["prep_times_min"] == [12, 5]


def test_prep_times_non_number_returns_400(client, monkeypatch):
    """prep_times_min 含非數字 → 400，且不呼叫 compare_algorithms。"""
    called = {"v": False}
    monkeypatch.setattr(run_interactive, "compare_algorithms",
                        lambda *a, **k: called.__setitem__("v", True) or [])
    resp = client.post("/api/route", json={
        "pickups": [[25.0, 121.0]],
        "dropoffs": [[25.2, 121.2]],
        "prep_times_min": ["abc"],
    })
    assert resp.status_code == 400
    assert called["v"] is False


def test_prep_times_omitted_ok(client, monkeypatch):
    """未提供 prep_times_min → 以 None 轉發（compare_algorithms 視為全 0）。"""
    captured = {}

    def fake_compare(graph, dist, pickups, dropoffs, start, speed_mps, prep_times_min):
        captured["prep_times_min"] = prep_times_min
        return []

    monkeypatch.setattr(run_interactive, "compare_algorithms", fake_compare)
    resp = client.post("/api/route", json={
        "pickups": [[25.0, 121.0]],
        "dropoffs": [[25.2, 121.2]],
    })
    assert resp.status_code == 200
    assert captured["prep_times_min"] is None

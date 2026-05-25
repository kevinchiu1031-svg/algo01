# -*- coding: utf-8 -*-
"""互動式外送路由規劃 Flask 伺服器。

用法：
    python scripts/run_interactive.py [--host 127.0.0.1] [--port 5000]
        [--place "Tatung University, Taipei, Taiwan"] [--dist-meters 1500]
        [--speed 5.0]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ── 讓 scripts/ 直接跑時也能 import delivery ────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flask import Flask, jsonify, render_template, request  # noqa: E402

from delivery.interactive import (  # noqa: E402
    AlgoResult,
    chinese_analysis,
    compare_algorithms,
)
from delivery.map_loader import load_graph, make_distance_matrix  # noqa: E402

# ── argparse（放 module level，供測試時 parse_args 覆寫） ────────────────────

def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="外送路由互動式規劃 Flask 伺服器")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5000)
    p.add_argument("--place", default="Taipei Main Station, Taipei, Taiwan")
    p.add_argument("--dist-meters", type=int, default=2500)
    p.add_argument("--speed", type=float, default=5.0)
    return p.parse_args(argv)


# ── Graph 懶載入（lazy loading；import 此 module 不觸發網路下載） ───────────
_GRAPH = None
_DIST = None
_CENTER_LAT = None
_CENTER_LNG = None


def _load(place: str = "Taipei Main Station, Taipei, Taiwan",
          dist_meters: int = 2500,
          speed_mps: float = 5.0):
    print(f"[INFO] 載入路網圖：{place}（半徑 {dist_meters} m）…")
    g = load_graph(place=place, dist_meters=dist_meters)
    print(f"[INFO] 節點數={g.number_of_nodes()}  邊數={g.number_of_edges()}")
    d = make_distance_matrix(g, speed_mps=speed_mps)
    return g, d


def get_graph_dist(place: str = "Taipei Main Station, Taipei, Taiwan",
                   dist_meters: int = 2500,
                   speed_mps: float = 5.0):
    """首次呼叫時載入路網圖並快取；後續呼叫直接回傳快取。"""
    global _GRAPH, _DIST, _CENTER_LAT, _CENTER_LNG
    if _GRAPH is None:
        _GRAPH, _DIST = _load(place, dist_meters, speed_mps)
        _nodes = list(_GRAPH.nodes(data=True))
        _CENTER_LAT = sum(d["y"] for _, d in _nodes) / len(_nodes)
        _CENTER_LNG = sum(d["x"] for _, d in _nodes) / len(_nodes)
    return _GRAPH, _DIST


# 在直接執行時從命令列取參數，伺服器啟動前預先暖機
if __name__ == "__main__":
    _cli_args = parse_args()

# ── Flask app ────────────────────────────────────────────────────────────────
app = Flask(
    __name__,
    template_folder=str(ROOT / "templates"),
    static_folder=str(ROOT / "static"),
)
# 讓 JSON 回應保留真實 UTF-8，不轉成 \uXXXX 跳脫
app.config["JSON_AS_ASCII"] = False
app.json.ensure_ascii = False


# ── 路由 ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    _graph, _ = get_graph_dist()
    center_lat = _CENTER_LAT
    center_lng = _CENTER_LNG
    return render_template(
        "interactive_map.html",
        center_lat=center_lat,
        center_lng=center_lng,
        zoom=16,
    )


def _is_pair(pt) -> bool:
    """回傳 True 若 pt 是包含兩個數字的 list/tuple。"""
    try:
        return (hasattr(pt, "__len__") and len(pt) == 2
                and all(isinstance(v, (int, float)) for v in pt))
    except Exception:
        return False


@app.route("/api/route", methods=["POST"])
def api_route():
    body = request.get_json(force=True, silent=True) or {}

    # ── 輸入驗證（400 Bad Request） ──────────────────────────────────────────
    start_raw = body.get("start", None)
    if start_raw is not None and not _is_pair(start_raw):
        return jsonify({"ok": False,
                        "error": "start 格式錯誤：須為 [緯度, 經度] 數字陣列"}), 400

    speed_raw = body.get("speed_mps", 5.0)
    if not isinstance(speed_raw, (int, float)):
        return jsonify({"ok": False,
                        "error": "speed_mps 格式錯誤：須為數字"}), 400

    pickups_raw  = body.get("pickups", [])
    dropoffs_raw = body.get("dropoffs", [])
    if not isinstance(pickups_raw, list) or not all(_is_pair(p) for p in pickups_raw):
        return jsonify({"ok": False,
                        "error": "pickups 格式錯誤：須為 [[緯度, 經度], ...] 陣列"}), 400
    if not isinstance(dropoffs_raw, list) or not all(_is_pair(p) for p in dropoffs_raw):
        return jsonify({"ok": False,
                        "error": "dropoffs 格式錯誤：須為 [[緯度, 經度], ...] 陣列"}), 400

    # prep_times_min：各訂單餐點製作時間（分鐘）。None 由 compare_algorithms 視為全 0。
    # 此處僅做形狀檢查（數字陣列）；長度與 0～25 範圍交由 compare_algorithms 把關。
    prep_raw = body.get("prep_times_min", None)
    if prep_raw is not None and (
        not isinstance(prep_raw, list)
        or not all(isinstance(v, (int, float)) for v in prep_raw)
    ):
        return jsonify({"ok": False,
                        "error": "prep_times_min 格式錯誤：須為數字陣列（分鐘）"}), 400

    try:
        speed_mps = float(speed_raw)

        # 取得（懶載入）路網圖
        graph, dist = get_graph_dist()

        # 轉成 tuple
        pickups  = [tuple(pt) for pt in pickups_raw]
        dropoffs = [tuple(pt) for pt in dropoffs_raw]
        start    = tuple(start_raw) if start_raw is not None else None

        results: list[AlgoResult] = compare_algorithms(
            graph, dist, pickups, dropoffs, start, speed_mps, prep_raw
        )

        analysis_text = chinese_analysis(results)

        # 取/送餐點的「可抵達馬路位置（approach）」與原始門口座標已包含在每個結果的
        # visited_stops 中（三演算法的 snap 結果相同），前端據此繪製 approach 標記與接駁虛線。
        response_data = {
            "ok": True,
            "results": [r.to_dict() for r in results],
            "analysis": analysis_text,
        }
        resp = jsonify(response_data)
        resp.headers["Content-Type"] = "application/json; charset=utf-8"
        return resp

    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": "伺服器錯誤：" + str(exc)}), 500


# ── 入口 ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # 伺服器啟動前預先暖機（eager pre-load），避免首個請求等待
    get_graph_dist(_cli_args.place, _cli_args.dist_meters, _cli_args.speed)
    url = f"http://{_cli_args.host}:{_cli_args.port}/"
    print(f"[INFO] 伺服器啟動：{url}")
    app.run(host=_cli_args.host, port=_cli_args.port, debug=False)

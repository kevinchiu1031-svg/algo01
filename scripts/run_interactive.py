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
    nearest_node,
)
from delivery.map_loader import load_graph, make_distance_matrix  # noqa: E402

# ── argparse（放 module level，供測試時 parse_args 覆寫） ────────────────────

def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="外送路由互動式規劃 Flask 伺服器")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5000)
    p.add_argument("--place", default="Tatung University, Taipei, Taiwan")
    p.add_argument("--dist-meters", type=int, default=1500)
    p.add_argument("--speed", type=float, default=5.0)
    return p.parse_args(argv)


# ── Graph 載入（module-level；供測試端直接 import 此 module） ─────────────────
def _load(place: str = "Tatung University, Taipei, Taiwan",
          dist_meters: int = 1500,
          speed_mps: float = 5.0):
    print(f"[INFO] 載入路網圖：{place}（半徑 {dist_meters} m）…")
    graph = load_graph(place=place, dist_meters=dist_meters)
    print(f"[INFO] 節點數={graph.number_of_nodes()}  邊數={graph.number_of_edges()}")
    dist = make_distance_matrix(graph, speed_mps=speed_mps)
    return graph, dist


# 在直接執行時從命令列取參數；被 import 時使用預設值（載入同一份快取）
if __name__ == "__main__":
    _cli_args = parse_args()
    graph, dist = _load(_cli_args.place, _cli_args.dist_meters, _cli_args.speed)
else:
    graph, dist = _load()

# ── 計算地圖中心 ─────────────────────────────────────────────────────────────
_nodes = list(graph.nodes(data=True))
_center_lat = sum(d["y"] for _, d in _nodes) / len(_nodes)
_center_lng = sum(d["x"] for _, d in _nodes) / len(_nodes)

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
    return render_template(
        "interactive_map.html",
        center_lat=_center_lat,
        center_lng=_center_lng,
        zoom=16,
    )


@app.route("/api/route", methods=["POST"])
def api_route():
    body = request.get_json(force=True, silent=True) or {}

    try:
        pickups_raw  = body.get("pickups", [])
        dropoffs_raw = body.get("dropoffs", [])
        start_raw    = body.get("start", None)
        speed_mps    = float(body.get("speed_mps", 5.0))

        # 轉成 tuple
        pickups  = [tuple(pt) for pt in pickups_raw]
        dropoffs = [tuple(pt) for pt in dropoffs_raw]
        start    = tuple(start_raw) if start_raw is not None else None

        results: list[AlgoResult] = compare_algorithms(
            graph, dist, pickups, dropoffs, start, speed_mps
        )

        analysis_text = chinese_analysis(results)

        # ── 計算 snapped 座標 ──────────────────────────────────────────────
        def snap_coord(lat: float, lng: float) -> list[float]:
            node = nearest_node(graph, lat, lng)
            nd = graph.nodes[node]
            return [nd["y"], nd["x"]]

        snapped_pickups  = [snap_coord(lat, lng) for lat, lng in pickups]
        snapped_dropoffs = [snap_coord(lat, lng) for lat, lng in dropoffs]

        if start is not None:
            snapped_start = snap_coord(start[0], start[1])
        else:
            # 鏡像後端預設：以第一個取餐節點作為起點
            snapped_start = snapped_pickups[0]

        response_data = {
            "ok": True,
            "results": [r.to_dict() for r in results],
            "analysis": analysis_text,
            "snapped": {
                "pickups":  snapped_pickups,
                "dropoffs": snapped_dropoffs,
                "start":    snapped_start,
            },
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
    url = f"http://{_cli_args.host}:{_cli_args.port}/"
    print(f"[INFO] 伺服器啟動：{url}")
    app.run(host=_cli_args.host, port=_cli_args.port, debug=False)

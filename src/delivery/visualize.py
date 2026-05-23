"""Folium 互動地圖輸出。"""
from pathlib import Path

import folium
import networkx as nx

from delivery.simulator import SimulationResult


def render_route_html(
    graph: nx.MultiDiGraph,
    result: SimulationResult,
    algorithm_name: str,
    out_path: Path,
) -> None:
    """畫出一個演算法的路線與 event log。

    路線：取 event_log 中 kind in {pickup, dropoff} 的點按時序連線。
    Marker：pickup=藍、dropoff=綠、accept=紫、reject=紅。
    """
    lats = [data["y"] for _, data in graph.nodes(data=True)]
    lons = [data["x"] for _, data in graph.nodes(data=True)]
    center = (sum(lats) / len(lats), sum(lons) / len(lons))

    fmap = folium.Map(location=center, zoom_start=16, tiles="OpenStreetMap")

    # Summary 卡片
    avg_ms = (
        sum(result.dispatcher_decision_ms) / len(result.dispatcher_decision_ms)
        if result.dispatcher_decision_ms else 0.0
    )
    summary_html = (
        f"<h3>{algorithm_name}</h3>"
        f"<p>Accepted: {len(result.accepted_orders)} | "
        f"Rejected: {len(result.rejected_orders)}<br>"
        f"Driver time: {result.driver_time_total:.0f}s | "
        f"Customer wait: {result.customer_wait_total:.0f}s<br>"
        f"Total cost: {result.total_cost:.0f} | "
        f"Avg decision: {avg_ms:.2f} ms</p>"
    )
    folium.Marker(
        center,
        icon=folium.DivIcon(html=(
            f'<div style="background:white;padding:6px;border:1px solid #444;'
            f'width:280px;font-family:sans-serif;font-size:12px;">'
            f'{summary_html}</div>'
        )),
    ).add_to(fmap)

    color_for = {"pickup": "blue", "dropoff": "green",
                 "accept": "purple", "reject": "red"}

    # 連線：把 pickup + dropoff 依時序連起來
    polyline_points: list[tuple[float, float]] = []
    for entry in result.event_log:
        if entry.kind in ("pickup", "dropoff") and entry.node is not None:
            data = graph.nodes[entry.node]
            polyline_points.append((data["y"], data["x"]))
    if len(polyline_points) >= 2:
        folium.PolyLine(
            polyline_points, color="darkblue", weight=3, opacity=0.7
        ).add_to(fmap)

    # 各事件 marker
    for entry in result.event_log:
        if entry.kind not in color_for or entry.node is None:
            continue
        data = graph.nodes[entry.node]
        lat, lon = data["y"], data["x"]
        folium.CircleMarker(
            (lat, lon),
            radius=6,
            color=color_for[entry.kind],
            fill=True,
            fill_opacity=0.8,
            popup=f"t={entry.timestamp:.0f}s {entry.kind}<br>{entry.detail}",
        ).add_to(fmap)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(out_path))


def render_comparison_html(
    results: dict[str, SimulationResult],
    out_path: Path,
) -> None:
    """產一個只有對照表的 HTML，不畫地圖。"""
    rows = []
    for name, r in results.items():
        avg_ms = (
            sum(r.dispatcher_decision_ms) / len(r.dispatcher_decision_ms)
            if r.dispatcher_decision_ms else 0.0
        )
        rows.append(
            f"<tr><td>{name}</td>"
            f"<td>{len(r.accepted_orders)}</td>"
            f"<td>{len(r.rejected_orders)}</td>"
            f"<td>{r.driver_time_total:.0f}</td>"
            f"<td>{r.customer_wait_total:.0f}</td>"
            f"<td>{r.total_cost:.0f}</td>"
            f"<td>{avg_ms:.2f}</td></tr>"
        )
    html = (
        "<html><head><meta charset='utf-8'><title>Comparison</title>"
        "<style>body{font-family:sans-serif;padding:24px}"
        "table{border-collapse:collapse}"
        "th,td{border:1px solid #888;padding:8px 12px}"
        "th{background:#eee}</style></head><body>"
        "<h2>Three algorithm comparison</h2>"
        "<table><thead><tr>"
        "<th>Algorithm</th><th>Accepted</th><th>Rejected</th>"
        "<th>Driver time (s)</th><th>Customer wait (s)</th>"
        "<th>Total cost</th><th>Avg decision (ms)</th>"
        "</tr></thead><tbody>"
        + "".join(rows) +
        "</tbody></table></body></html>"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

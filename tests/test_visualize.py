from pathlib import Path

import networkx as nx

from delivery.simulator import EventLogEntry, SimulationResult
from delivery.visualize import render_route_html, render_comparison_html


def _toy_geo_graph() -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    coords = {
        0: (25.0625, 121.5290),  # 大同大學周邊隨意座標
        10: (25.0635, 121.5285),
        20: (25.0620, 121.5300),
    }
    for n, (lat, lon) in coords.items():
        g.add_node(n, y=lat, x=lon)
    g.add_edge(0, 10, length=100, travel_time=20)
    g.add_edge(10, 20, length=200, travel_time=40)
    return g


def test_render_route_html_creates_file(tmp_path: Path):
    g = _toy_geo_graph()
    result = SimulationResult(
        accepted_orders=[1],
        rejected_orders=[],
        driver_time_total=60.0,
        customer_wait_total=60.0,
        total_cost=120.0,
        dispatcher_decision_ms=[1.5],
        event_log=[
            EventLogEntry(0.0, "accept", "order 1", node=0),
            EventLogEntry(20.0, "pickup", "order 1 (wait 0s)", node=10),
            EventLogEntry(60.0, "dropoff", "order 1 (cust_wait 60s)", node=20),
        ],
    )
    out = tmp_path / "route.html"
    render_route_html(
        graph=g,
        result=result,
        algorithm_name="greedy",
        out_path=out,
    )
    assert out.exists()
    assert out.stat().st_size > 0
    content = out.read_text(encoding="utf-8")
    assert "greedy" in content


def test_render_comparison_html_creates_file(tmp_path: Path):
    results = {
        "greedy": SimulationResult([1], [], 100.0, 50.0, 150.0, [1.0], []),
        "tsp_approx": SimulationResult([1], [], 90.0, 40.0, 130.0, [2.0], []),
        "dp": SimulationResult([1], [], 80.0, 30.0, 110.0, [5.0], []),
    }
    out = tmp_path / "compare.html"
    render_comparison_html(results, out_path=out)
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    for name in ("greedy", "tsp_approx", "dp"):
        assert name in content

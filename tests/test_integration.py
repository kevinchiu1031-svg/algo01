"""端到端測試：用 toy graph 跑一個 mini 模擬，三演算法都跑得通並產出 HTML。"""
from pathlib import Path

import networkx as nx
import pytest

from delivery.algorithms.dp import DpDispatcher
from delivery.algorithms.greedy import GreedyDispatcher
from delivery.algorithms.tsp_approx import TspApproxDispatcher
from delivery.map_loader import make_distance_matrix
from delivery.models import Order
from delivery.simulator import Simulator
from delivery.visualize import render_comparison_html, render_route_html


@pytest.fixture
def toy_geo_graph() -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    # 5x5 grid of nodes around 大同大學附近座標
    base_lat, base_lon = 25.0625, 121.5290
    for i in range(5):
        for j in range(5):
            n = i * 5 + j
            g.add_node(n,
                       y=base_lat + i * 0.0005,
                       x=base_lon + j * 0.0005)
    # 連邊：橫向 + 縱向
    for i in range(5):
        for j in range(5):
            n = i * 5 + j
            if j < 4:
                g.add_edge(n, n + 1, length=50.0)
                g.add_edge(n + 1, n, length=50.0)
            if i < 4:
                g.add_edge(n, n + 5, length=50.0)
                g.add_edge(n + 5, n, length=50.0)
    # 標 3 個 restaurant
    for n in (0, 12, 24):
        g.nodes[n]["amenity"] = "restaurant"
    return g


def test_end_to_end_all_three_algorithms(toy_geo_graph, tmp_path: Path):
    dist = make_distance_matrix(toy_geo_graph, speed_mps=5.0)
    # 手寫 5 張單而非用 Poisson，確保可重現
    orders = [
        Order(1, 0, 8, place_time=0.0, prep_time=10.0),
        Order(2, 12, 18, place_time=30.0, prep_time=20.0),
        Order(3, 24, 4, place_time=60.0, prep_time=15.0),
        Order(4, 0, 22, place_time=120.0, prep_time=5.0),
        Order(5, 12, 6, place_time=180.0, prep_time=30.0),
    ]
    dispatchers = [
        GreedyDispatcher(),
        TspApproxDispatcher(),
        DpDispatcher(alpha=1.0, beta=1.0),
    ]
    results = {}
    for d in dispatchers:
        sim = Simulator(
            dispatcher=d, dist=dist, order_stream=orders,
            start_node=12, end_time=3600.0, tolerance=480.0,
            alpha=1.0, beta=1.0,
        )
        result = sim.run()
        results[d.name] = result
        # 每個演算法都應該接到至少 1 單
        assert len(result.accepted_orders) >= 1
        out_path = tmp_path / f"{d.name}_route.html"
        render_route_html(toy_geo_graph, result, d.name, out_path)
        assert out_path.exists()

    comparison_path = tmp_path / "comparison.html"
    render_comparison_html(results, comparison_path)
    assert comparison_path.exists()

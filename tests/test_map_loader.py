import networkx as nx
import pytest

from delivery.map_loader import (
    extract_restaurant_nodes,
    make_distance_matrix,
    random_customer_nodes,
)


def _toy_graph() -> nx.MultiDiGraph:
    """4-node toy graph：環狀，邊權 = travel_time 秒。"""
    g = nx.MultiDiGraph()
    coords = [(0, 0), (1, 0), (1, 1), (0, 1)]
    for i, (x, y) in enumerate(coords):
        g.add_node(i, x=x, y=y)
    edges = [(0, 1), (1, 2), (2, 3), (3, 0), (1, 0), (2, 1), (3, 2), (0, 3)]
    for u, v in edges:
        g.add_edge(u, v, travel_time=10.0, length=10.0)
    return g


def test_distance_matrix_uses_dijkstra():
    g = _toy_graph()
    dist = make_distance_matrix(g, speed_mps=1.0)
    # 0 → 1 走一條邊 = 10 秒
    assert dist[(0, 1)] == pytest.approx(10.0)
    # 0 → 2 走兩條邊 = 20 秒
    assert dist[(0, 2)] == pytest.approx(20.0)
    # 自己到自己 = 0
    assert dist[(0, 0)] == 0.0


def test_random_customer_nodes_deterministic_with_seed():
    g = _toy_graph()
    a = random_customer_nodes(g, count=3, seed=42)
    b = random_customer_nodes(g, count=3, seed=42)
    assert a == b
    assert len(a) == 3
    assert all(node in g.nodes for node in a)


def test_extract_restaurant_nodes_from_attribute():
    """測試 helper 能從帶有 amenity tag 的 graph 抽出餐廳節點。"""
    g = _toy_graph()
    # 模擬 OSMnx 標註：node 1 與 node 3 標為 restaurant
    g.nodes[1]["amenity"] = "restaurant"
    g.nodes[3]["amenity"] = "fast_food"
    restaurants = extract_restaurant_nodes(g)
    assert set(restaurants) == {1, 3}

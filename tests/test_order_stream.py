import networkx as nx

from delivery.order_stream import generate_orders


def _toy_graph() -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    for i in range(10):
        g.add_node(i)
    for i in [1, 3, 5]:
        g.nodes[i]["amenity"] = "restaurant"
    return g


def test_generate_orders_deterministic_with_seed():
    g = _toy_graph()
    a = generate_orders(g, lambda_per_min=0.5, duration_seconds=600.0, seed=7)
    b = generate_orders(g, lambda_per_min=0.5, duration_seconds=600.0, seed=7)
    assert len(a) == len(b)
    for x, y in zip(a, b):
        assert x == y


def test_generate_orders_arrivals_within_duration():
    g = _toy_graph()
    orders = generate_orders(g, lambda_per_min=2.0, duration_seconds=600.0, seed=7)
    for o in orders:
        assert 0.0 <= o.place_time <= 600.0
        assert o.restaurant_node in {1, 3, 5}
        assert o.customer_node in g.nodes
        assert o.prep_time > 0


def test_generate_orders_unique_ids():
    g = _toy_graph()
    orders = generate_orders(g, lambda_per_min=2.0, duration_seconds=600.0, seed=7)
    ids = [o.id for o in orders]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)

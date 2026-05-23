from delivery.models import Order, Stop, DriverState
from delivery.algorithms.tsp_approx import TspApproxDispatcher


def test_approx_returns_valid_route(dist_factory):
    order = Order(id=1, restaurant_node=10, customer_node=20,
                  place_time=0.0, prep_time=0.0)
    state = DriverState(location_node=0, current_time=0.0, in_hand=[])
    dist = dist_factory({(0, 10): 5, (0, 20): 7, (10, 20): 3})
    disp = TspApproxDispatcher()
    decision = disp.plan(state, order, {1: order}, dist)
    assert decision.accept is True
    assert decision.new_route == [Stop(1, "pickup", 10), Stop(1, "dropoff", 20)]


def test_approx_precedence_repair(dist_factory):
    """構造一個 MST preorder 會違反 precedence 的情境，驗證修補後合法。"""
    o1 = Order(id=1, restaurant_node=10, customer_node=11, place_time=0, prep_time=0)
    o2 = Order(id=2, restaurant_node=20, customer_node=21, place_time=0, prep_time=0)
    state = DriverState(
        location_node=0, current_time=0.0,
        in_hand=[Stop(1, "pickup", 10), Stop(1, "dropoff", 11)],
    )
    dist = dist_factory({
        (0, 10): 10, (0, 11): 5, (0, 20): 100, (0, 21): 90,
        (10, 11): 8, (10, 20): 50, (10, 21): 60,
        (11, 20): 30, (11, 21): 40, (20, 21): 12,
    })
    disp = TspApproxDispatcher()
    decision = disp.plan(state, o2, {1: o1, 2: o2}, dist)
    route = decision.new_route
    for order_id in (1, 2):
        positions = [i for i, s in enumerate(route) if s.order_id == order_id]
        kinds = [route[i].kind for i in positions]
        assert kinds == ["pickup", "dropoff"]
    assert len(route) == 4


def test_approx_contains_all_stops(dist_factory):
    o1 = Order(id=1, restaurant_node=10, customer_node=11, place_time=0, prep_time=0)
    o2 = Order(id=2, restaurant_node=20, customer_node=21, place_time=0, prep_time=0)
    o3 = Order(id=3, restaurant_node=30, customer_node=31, place_time=0, prep_time=0)
    state = DriverState(
        location_node=0, current_time=0.0,
        in_hand=[Stop(1, "pickup", 10), Stop(1, "dropoff", 11)],
    )
    nodes = [0, 10, 11, 20, 21, 30, 31]
    dist = dist_factory({
        (a, b): abs(a - b) + 1
        for a in nodes for b in nodes if a != b
    })
    # 在 plan 內加入 o2、o3 → 整個 route 應含 5 個新 stops + 2 個 in_hand
    # 但 plan 一次只加一張新單；這裡先加 o2
    disp = TspApproxDispatcher()
    decision = disp.plan(state, o2, {1: o1, 2: o2}, dist)
    route = decision.new_route
    assert {(s.order_id, s.kind) for s in route} == {
        (1, "pickup"), (1, "dropoff"),
        (2, "pickup"), (2, "dropoff"),
    }

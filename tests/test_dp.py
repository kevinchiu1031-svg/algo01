import random

from delivery.models import Order, Stop, DriverState
from delivery.algorithms.dp import DpDispatcher
from delivery.algorithms.greedy import GreedyDispatcher
from delivery.algorithms.tsp_approx import TspApproxDispatcher
from delivery.metrics import cost_of_route


def test_dp_single_order(dist_factory):
    order = Order(id=1, restaurant_node=10, customer_node=20,
                  place_time=0.0, prep_time=0.0)
    state = DriverState(location_node=0, current_time=0.0, in_hand=[])
    dist = dist_factory({(0, 10): 5, (0, 20): 7, (10, 20): 3})
    disp = DpDispatcher(alpha=1.0, beta=1.0)
    decision = disp.plan(state, order, {1: order}, dist)
    assert decision.accept is True
    assert decision.new_route == [Stop(1, "pickup", 10), Stop(1, "dropoff", 20)]


def test_dp_is_oracle_vs_greedy_and_approx(dist_factory):
    """隨機產生 3 張單的小 case，DP 解 cost ≤ Greedy 與 TSP-Approx。"""
    rng = random.Random(42)
    for _ in range(5):
        nodes = list(range(7))
        # 對稱、滿足三角不等式的距離（用座標生成）
        coords = {i: (rng.uniform(0, 100), rng.uniform(0, 100)) for i in nodes}

        def euclid(a: int, b: int) -> float:
            ax, ay = coords[a]
            bx, by = coords[b]
            return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5

        dist = dist_factory({
            (a, b): euclid(a, b) for a in nodes for b in nodes if a != b
        })
        orders = {
            1: Order(1, 1, 2, place_time=0.0, prep_time=0.0),
            2: Order(2, 3, 4, place_time=0.0, prep_time=0.0),
            3: Order(3, 5, 6, place_time=0.0, prep_time=0.0),
        }
        state = DriverState(location_node=0, current_time=0.0,
                            in_hand=[
                                Stop(1, "pickup", 1),
                                Stop(1, "dropoff", 2),
                                Stop(2, "pickup", 3),
                                Stop(2, "dropoff", 4),
                            ])
        candidate = orders[3]
        dp = DpDispatcher(alpha=1.0, beta=1.0).plan(state, candidate, orders, dist)
        gr = GreedyDispatcher().plan(state, candidate, orders, dist)
        ap = TspApproxDispatcher().plan(state, candidate, orders, dist)
        c_dp, _, _ = cost_of_route(dp.new_route, state, orders, dist, 1.0, 1.0)
        c_gr, _, _ = cost_of_route(gr.new_route, state, orders, dist, 1.0, 1.0)
        c_ap, _, _ = cost_of_route(ap.new_route, state, orders, dist, 1.0, 1.0)
        assert c_dp <= c_gr + 1e-6, f"DP {c_dp} > Greedy {c_gr}"
        assert c_dp <= c_ap + 1e-6, f"DP {c_dp} > Approx {c_ap}"


def test_dp_route_respects_precedence(dist_factory):
    o1 = Order(1, 10, 11, place_time=0, prep_time=0)
    o2 = Order(2, 20, 21, place_time=0, prep_time=0)
    state = DriverState(
        location_node=0, current_time=0.0,
        in_hand=[Stop(1, "pickup", 10), Stop(1, "dropoff", 11)],
    )
    dist = dist_factory({
        (0, 10): 10, (0, 11): 5, (0, 20): 100, (0, 21): 90,
        (10, 11): 8, (10, 20): 50, (10, 21): 60,
        (11, 20): 30, (11, 21): 40, (20, 21): 12,
    })
    disp = DpDispatcher(alpha=1.0, beta=1.0)
    decision = disp.plan(state, o2, {1: o1, 2: o2}, dist)
    route = decision.new_route
    for oid in (1, 2):
        positions = [i for i, s in enumerate(route) if s.order_id == oid]
        kinds = [route[i].kind for i in positions]
        assert kinds == ["pickup", "dropoff"]


def test_dp_handles_dropoff_only_in_hand(dist_factory):
    """Simulator 完成 pickup 後，state.in_hand 只剩該單的 dropoff；
    新單進來時不應該 crash。"""
    o1 = Order(id=1, restaurant_node=10, customer_node=11, place_time=0, prep_time=0)
    o2 = Order(id=2, restaurant_node=20, customer_node=21, place_time=0, prep_time=0)
    state = DriverState(
        location_node=10,  # 已在 o1 餐廳
        current_time=100.0,
        in_hand=[Stop(1, "dropoff", 11)],  # o1 已取餐，剩送達
    )
    dist = dist_factory({
        (10, 11): 50, (10, 20): 100, (10, 21): 150,
        (11, 20): 80, (11, 21): 130, (20, 21): 60,
    })
    disp = DpDispatcher(alpha=1.0, beta=1.0)
    decision = disp.plan(state, o2, {1: o1, 2: o2}, dist)
    assert decision.accept is True
    assert len(decision.new_route) == 3  # o1 dropoff + o2 pickup + o2 dropoff
    # o2 pickup 必須在 o2 dropoff 之前
    p2 = next(i for i, s in enumerate(decision.new_route) if s.order_id == 2 and s.kind == "pickup")
    d2 = next(i for i, s in enumerate(decision.new_route) if s.order_id == 2 and s.kind == "dropoff")
    assert p2 < d2

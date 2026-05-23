from delivery.models import Order, Stop, DriverState, DistanceMatrix


def test_order_food_ready_time():
    order = Order(
        id=1,
        restaurant_node=10,
        customer_node=20,
        place_time=100.0,
        prep_time=300.0,
    )
    assert order.food_ready_time == 400.0


def test_distance_matrix_caches_lookups():
    calls: list[tuple[int, int]] = []

    def lookup(u: int, v: int) -> float:
        calls.append((u, v))
        return float(u + v)

    dist = DistanceMatrix(lookup)
    assert dist[(1, 2)] == 3.0
    assert dist[(1, 2)] == 3.0  # 第二次走 cache
    assert calls == [(1, 2)]


def test_distance_matrix_symmetric_cache():
    """(u,v) 與 (v,u) 共用 cache key（無向路網）。"""
    calls: list[tuple[int, int]] = []

    def lookup(u: int, v: int) -> float:
        calls.append((u, v))
        return 5.0

    dist = DistanceMatrix(lookup, symmetric=True)
    assert dist[(1, 2)] == 5.0
    assert dist[(2, 1)] == 5.0
    assert len(calls) == 1


def test_driver_state_in_hand_order_count():
    state = DriverState(
        location_node=0,
        current_time=0.0,
        in_hand=[
            Stop(order_id=1, kind="pickup", node=10),
            Stop(order_id=1, kind="dropoff", node=20),
            Stop(order_id=2, kind="pickup", node=30),
        ],
    )
    # 計算 in_hand 中 unique order ids
    order_ids = {s.order_id for s in state.in_hand}
    assert len(order_ids) == 2

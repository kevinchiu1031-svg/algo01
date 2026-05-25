from delivery.models import Order, Stop, DriverState
from delivery.algorithms.greedy import GreedyDispatcher
from delivery.algorithms.dp import DpDispatcher
from delivery.algorithms.tsp_approx import TspApproxDispatcher


def test_greedy_avoids_long_wait_at_restaurant(dist_factory):
    """Wait-aware：最近的取餐點餐還沒好（要等很久），較遠的取餐點餐已好，
    貪婪應先去『餐已好』的那家，避免在餐廳長時間空等。"""
    # order 1 餐廳近（10s）但備餐久（ready 在 600s）；order 2 餐廳遠（60s）但餐已好（ready 0）
    o1 = Order(id=1, restaurant_node=1, customer_node=2,
               place_time=0.0, prep_time=600.0)
    o2 = Order(id=2, restaurant_node=3, customer_node=4,
               place_time=0.0, prep_time=0.0)
    state = DriverState(location_node=0, current_time=0.0, in_hand=[
        Stop(1, "pickup", 1), Stop(1, "dropoff", 2),
    ])
    dist = dist_factory({
        (0, 1): 10, (0, 2): 70, (0, 3): 60, (0, 4): 90,
        (1, 2): 50, (1, 3): 55, (1, 4): 80,
        (2, 3): 40, (2, 4): 45, (3, 4): 50,
    })
    disp = GreedyDispatcher()
    decision = disp.plan(state, o2, {1: o1, 2: o2}, dist)
    # 第一個停靠點應是 order 2 的 pickup（餐已好），而非最近但要久等的 order 1
    assert decision.new_route[0] == Stop(2, "pickup", 3)


def test_greedy_single_new_order_no_in_hand(dist_factory):
    """空車情境：接一張新單，應排成 pickup → dropoff。"""
    order = Order(id=1, restaurant_node=10, customer_node=20,
                  place_time=0.0, prep_time=50.0)
    state = DriverState(location_node=0, current_time=100.0, in_hand=[])
    dist = dist_factory({(0, 10): 50, (10, 20): 30, (0, 20): 200})
    disp = GreedyDispatcher()
    decision = disp.plan(state, order, {1: order}, dist)
    assert decision.accept is True
    assert decision.new_route == [
        Stop(1, "pickup", 10),
        Stop(1, "dropoff", 20),
    ]


def test_greedy_respects_precedence(dist_factory):
    """已有一張單在 in_hand，新單加入；dropoff 一定排在對應 pickup 之後。"""
    o1 = Order(id=1, restaurant_node=10, customer_node=11,
               place_time=0.0, prep_time=0.0)
    o2 = Order(id=2, restaurant_node=20, customer_node=21,
               place_time=0.0, prep_time=0.0)
    state = DriverState(
        location_node=0,
        current_time=0.0,
        in_hand=[Stop(1, "pickup", 10), Stop(1, "dropoff", 11)],
    )
    # 故意把距離設成最近順序會違反 precedence 的樣子
    dist = dist_factory({
        (0, 10): 5, (0, 11): 100, (0, 20): 10, (0, 21): 3,
        (10, 11): 50, (10, 20): 20, (10, 21): 30,
        (11, 20): 15, (11, 21): 8, (20, 21): 25,
    })
    disp = GreedyDispatcher()
    decision = disp.plan(state, o2, {1: o1, 2: o2}, dist)
    assert decision.accept is True
    # 驗證 route 中每張單的 pickup 都在 dropoff 之前
    route = decision.new_route
    for order_id in (1, 2):
        positions = [i for i, s in enumerate(route) if s.order_id == order_id]
        kinds = [route[i].kind for i in positions]
        assert kinds == ["pickup", "dropoff"]


def test_greedy_returns_all_stops(dist_factory):
    """產生的 route 必須包含所有 in_hand stops + 新單的兩 stops。"""
    o1 = Order(id=1, restaurant_node=10, customer_node=11, place_time=0, prep_time=0)
    o2 = Order(id=2, restaurant_node=20, customer_node=21, place_time=0, prep_time=0)
    state = DriverState(
        location_node=0, current_time=0.0,
        in_hand=[Stop(1, "pickup", 10)],
    )
    dist = dist_factory({
        (0, 10): 5, (0, 11): 100, (0, 20): 10, (0, 21): 30,
        (10, 11): 50, (10, 20): 20, (10, 21): 30,
        (11, 20): 15, (11, 21): 8, (20, 21): 25,
    })
    disp = GreedyDispatcher()
    decision = disp.plan(state, o2, {1: o1, 2: o2}, dist)
    assert decision.accept is True
    assert len(decision.new_route) == 3  # 1 leftover + 2 new
    assert {(s.order_id, s.kind) for s in decision.new_route} == {
        (1, "pickup"), (2, "pickup"), (2, "dropoff"),
    }


def test_greedy_handles_dropoff_only_in_hand(dist_factory):
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
    disp = GreedyDispatcher()
    decision = disp.plan(state, o2, {1: o1, 2: o2}, dist)
    assert decision.accept is True
    assert len(decision.new_route) == 3  # o1 dropoff + o2 pickup + o2 dropoff
    # o2 pickup 必須在 o2 dropoff 之前
    p2 = next(i for i, s in enumerate(decision.new_route) if s.order_id == 2 and s.kind == "pickup")
    d2 = next(i for i, s in enumerate(decision.new_route) if s.order_id == 2 and s.kind == "dropoff")
    assert p2 < d2

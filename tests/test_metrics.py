from delivery.models import Order, Stop, DriverState, DistanceMatrix
from delivery.metrics import cost_of_route, route_timeline


def make_dist(table: dict[tuple[int, int], float]) -> DistanceMatrix:
    """Test helper：包一個 dict 進 DistanceMatrix。"""
    def lookup(u: int, v: int) -> float:
        return table[(u, v)]
    return DistanceMatrix(lookup)


def test_cost_of_route_simple_one_order_no_wait():
    """單一訂單，餐點早就好；driver 開 100 秒到餐廳，又 100 秒到顧客。"""
    order = Order(id=1, restaurant_node=10, customer_node=20,
                  place_time=0.0, prep_time=50.0)
    state = DriverState(location_node=0, current_time=200.0, in_hand=[])
    route = [
        Stop(order_id=1, kind="pickup", node=10),
        Stop(order_id=1, kind="dropoff", node=20),
    ]
    dist = make_dist({(0, 10): 100.0, (10, 20): 100.0})
    cost, driver_time, cust_wait = cost_of_route(
        route, state, {1: order}, dist, alpha=1.0, beta=1.0
    )
    # driver_time = 100 (drive to pickup) + 0 (no wait) + 100 (drive to dropoff) = 200
    # customer_wait = dropoff_time(400) - place_time(0) = 400
    assert driver_time == 200.0
    assert cust_wait == 400.0
    assert cost == 1.0 * 200.0 + 1.0 * 400.0


def test_cost_of_route_with_food_wait():
    """抵達餐廳時餐點還沒好，要等。"""
    order = Order(id=1, restaurant_node=10, customer_node=20,
                  place_time=0.0, prep_time=500.0)  # 餐 500 秒做好
    state = DriverState(location_node=0, current_time=0.0, in_hand=[])
    route = [
        Stop(order_id=1, kind="pickup", node=10),
        Stop(order_id=1, kind="dropoff", node=20),
    ]
    dist = make_dist({(0, 10): 100.0, (10, 20): 100.0})
    # 抵達餐廳 t=100，餐 t=500 才好，等 400 秒
    # 離開餐廳 t=500，抵達顧客 t=600
    cost, driver_time, cust_wait = cost_of_route(
        route, state, {1: order}, dist, alpha=1.0, beta=1.0
    )
    assert driver_time == 600.0  # 100 + 400 wait + 100
    assert cust_wait == 600.0    # dropoff t=600 − place_time 0


def test_route_timeline_returns_event_list():
    order = Order(id=1, restaurant_node=10, customer_node=20,
                  place_time=0.0, prep_time=50.0)
    state = DriverState(location_node=0, current_time=0.0, in_hand=[])
    route = [
        Stop(order_id=1, kind="pickup", node=10),
        Stop(order_id=1, kind="dropoff", node=20),
    ]
    dist = make_dist({(0, 10): 100.0, (10, 20): 100.0})
    timeline = route_timeline(route, state, {1: order}, dist)
    # 每個 stop 應對應一個 (arrival_time, departure_time, stop) 三元組
    assert len(timeline) == 2
    assert timeline[0].arrival_time == 100.0
    assert timeline[0].departure_time == 100.0  # 餐已好，無等待
    assert timeline[1].arrival_time == 200.0

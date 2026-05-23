from delivery.models import Order, Stop, DriverState, Decision, DistanceMatrix
from delivery.simulator import Simulator, SimulationResult


class _AlwaysAcceptGreedy:
    """Test double：永遠接，順序就用 in_hand + 新單 pickup → dropoff。"""
    name = "test-greedy"

    def plan(self, state, candidate, all_orders, dist):
        new_route = list(state.in_hand) + [
            Stop(candidate.id, "pickup", candidate.restaurant_node),
            Stop(candidate.id, "dropoff", candidate.customer_node),
        ]
        return Decision(accept=True, new_route=new_route)


def test_simulator_single_order_end_to_end(dist_factory):
    order = Order(id=1, restaurant_node=10, customer_node=20,
                  place_time=10.0, prep_time=50.0)
    dist = dist_factory({(0, 10): 100, (10, 20): 100, (0, 20): 200})
    sim = Simulator(
        dispatcher=_AlwaysAcceptGreedy(),
        dist=dist,
        order_stream=[order],
        start_node=0,
        end_time=1000.0,
        tolerance=480.0,
        alpha=1.0,
        beta=1.0,
    )
    result = sim.run()
    assert result.accepted_orders == [1]
    assert result.rejected_orders == []
    # 抵達餐廳 t=110，餐 t=60 已好，立即取走；抵達顧客 t=210
    # customer_wait = 210 − 10 = 200
    # driver_time = 210 − 10 = 200
    assert result.customer_wait_total == 200.0


def test_simulator_rejects_when_in_hand_full(dist_factory):
    """已有 3 單在手，第 4 單一律拒。"""
    orders = [
        Order(i, 10 * i, 10 * i + 1, place_time=0.0, prep_time=0.0)
        for i in range(1, 5)
    ]
    table = {}
    nodes = [0] + [n for o in orders for n in (o.restaurant_node, o.customer_node)]
    for a in nodes:
        for b in nodes:
            if a != b:
                table[(a, b)] = abs(a - b) + 1
    dist = dist_factory(table)

    sim = Simulator(
        dispatcher=_AlwaysAcceptGreedy(),
        dist=dist,
        order_stream=orders,
        start_node=0,
        end_time=10.0,  # 故意設超短，沒時間完成任何 stop
        tolerance=float("inf"),
        alpha=1.0,
        beta=1.0,
    )
    result = sim.run()
    # 前 3 單在 t=0 全進，第 4 單被 3-order cap 擋掉
    assert 1 in result.accepted_orders
    assert 2 in result.accepted_orders
    assert 3 in result.accepted_orders
    assert 4 in result.rejected_orders


def test_simulator_clock_monotonic(dist_factory):
    """事件處理過程中 clock 不能回頭。"""
    order = Order(id=1, restaurant_node=10, customer_node=20,
                  place_time=0.0, prep_time=0.0)
    dist = dist_factory({(0, 10): 10, (10, 20): 10, (0, 20): 20})
    sim = Simulator(
        dispatcher=_AlwaysAcceptGreedy(),
        dist=dist,
        order_stream=[order],
        start_node=0,
        end_time=1000.0,
        tolerance=480.0,
        alpha=1.0,
        beta=1.0,
    )
    result = sim.run()
    times = [e.timestamp for e in result.event_log]
    assert times == sorted(times)

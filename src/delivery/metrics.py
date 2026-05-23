"""成本函數與路線時間軸。"""
from dataclasses import dataclass

from delivery.models import DistanceMatrix, DriverState, Order, Stop


@dataclass(frozen=True)
class TimelineEntry:
    stop: Stop
    arrival_time: float
    departure_time: float


def route_timeline(
    route: list[Stop],
    state: DriverState,
    orders: dict[int, Order],
    dist: DistanceMatrix,
) -> list[TimelineEntry]:
    """逐站推進，回傳每站抵達 / 離開時刻。

    pickup 站若餐未好需等待，等待計入 departure_time。
    dropoff 站立即離開（arrival == departure）。
    """
    timeline: list[TimelineEntry] = []
    current_node = state.location_node
    current_time = state.current_time
    for stop in route:
        travel = dist[(current_node, stop.node)]
        arrival = current_time + travel
        if stop.kind == "pickup":
            order = orders[stop.order_id]
            departure = max(arrival, order.food_ready_time)
        else:
            departure = arrival
        timeline.append(TimelineEntry(stop, arrival, departure))
        current_node = stop.node
        current_time = departure
    return timeline


def cost_of_route(
    route: list[Stop],
    state: DriverState,
    orders: dict[int, Order],
    dist: DistanceMatrix,
    alpha: float = 1.0,
    beta: float = 1.0,
) -> tuple[float, float, float]:
    """回傳 (總加權成本, driver_time, customer_wait_sum)。

    - driver_time = 從 state.current_time 到最後一站 departure 的時間
    - customer_wait = sum of (dropoff_time - order.place_time) for each dropoff
    """
    if not route:
        return 0.0, 0.0, 0.0
    timeline = route_timeline(route, state, orders, dist)
    driver_time = timeline[-1].departure_time - state.current_time
    customer_wait = 0.0
    for entry in timeline:
        if entry.stop.kind == "dropoff":
            order = orders[entry.stop.order_id]
            customer_wait += entry.arrival_time - order.place_time
    cost = alpha * driver_time + beta * customer_wait
    return cost, driver_time, customer_wait

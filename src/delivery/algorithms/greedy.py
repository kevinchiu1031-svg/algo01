"""Greedy 最近可行鄰居（wait-aware）。CLRS Ch 15。

每步在「符合 precedence 的停靠點」中，挑選綜合成本最低者。成本 = 行駛時間
+ 餐廳等待時間 + 超過容忍門檻的等待懲罰。如此騎手會盡量先做不需空等的事，
只在「順路且等待短（≤ 容忍門檻）」時才在餐廳稍候，避免長時間乾等。
"""
from delivery.models import (
    WAIT_OVERAGE_WEIGHT,
    WAIT_TOLERANCE_S,
    Decision,
    DistanceMatrix,
    DriverState,
    Order,
    Stop,
)


class GreedyDispatcher:
    name = "greedy"

    def plan(
        self,
        state: DriverState,
        candidate: Order,
        all_orders: dict[int, Order],
        dist: DistanceMatrix,
    ) -> Decision:
        # 把 candidate 的 pickup/dropoff 加入 stops 池
        pending: list[Stop] = list(state.in_hand) + [
            Stop(candidate.id, "pickup", candidate.restaurant_node),
            Stop(candidate.id, "dropoff", candidate.customer_node),
        ]
        route = _greedy_order(
            pending, state.location_node, state.current_time, all_orders, dist
        )
        return Decision(accept=True, new_route=route)


def _greedy_order(
    stops: list[Stop],
    start_node: int,
    start_time: float,
    orders: dict[int, Order],
    dist: DistanceMatrix,
) -> list[Stop]:
    """最近可行鄰居（含等待成本）：每步挑「行駛時間＋等待＋超時懲罰」最低且符合
    precedence 的 stop，同時推進時鐘（pickup 若早到需等到餐好才離開）。

    若 stops 中某 order 只有 dropoff 沒有 pickup，代表 pickup 已被 simulator
    完成，該 order 視為已可 dropoff（pre-populate picked_up）。
    """
    remaining = list(stops)
    has_pickup = {s.order_id for s in stops if s.kind == "pickup"}
    picked_up: set[int] = {
        s.order_id for s in stops
        if s.kind == "dropoff" and s.order_id not in has_pickup
    }
    route: list[Stop] = []
    current = start_node
    current_time = start_time

    def step_cost(s: Stop) -> tuple[float, float]:
        """回傳 (選取成本, 抵達後離開時刻)。"""
        travel = dist[(current, s.node)]
        arrival = current_time + travel
        if s.kind == "pickup":
            ready = orders[s.order_id].food_ready_time
            wait = max(0.0, ready - arrival)
            departure = arrival + wait
            penalty = WAIT_OVERAGE_WEIGHT * max(0.0, wait - WAIT_TOLERANCE_S)
            return travel + wait + penalty, departure
        return travel, arrival

    while remaining:
        feasible = [
            s for s in remaining
            if s.kind == "pickup" or s.order_id in picked_up
        ]
        nxt = min(feasible, key=lambda s: step_cost(s)[0])
        _, departure = step_cost(nxt)
        route.append(nxt)
        remaining.remove(nxt)
        if nxt.kind == "pickup":
            picked_up.add(nxt.order_id)
        current = nxt.node
        current_time = departure
    return route

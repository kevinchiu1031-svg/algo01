"""Greedy 最近可行鄰居。CLRS Ch 15。"""
from delivery.models import (
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
        route = _greedy_order(pending, state.location_node, dist)
        return Decision(accept=True, new_route=route)


def _greedy_order(
    stops: list[Stop],
    start_node: int,
    dist: DistanceMatrix,
) -> list[Stop]:
    """最近可行鄰居：每步挑距離最近且符合 precedence 的 stop。

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

    while remaining:
        feasible = [
            s for s in remaining
            if s.kind == "pickup" or s.order_id in picked_up
        ]
        nxt = min(feasible, key=lambda s: dist[(current, s.node)])
        route.append(nxt)
        remaining.remove(nxt)
        if nxt.kind == "pickup":
            picked_up.add(nxt.order_id)
        current = nxt.node
    return route

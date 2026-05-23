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
    """最近可行鄰居：每步挑距離最近且符合 precedence 的 stop。"""
    remaining = list(stops)
    picked_up: set[int] = set()
    route: list[Stop] = []
    current = start_node

    while remaining:
        # feasible = 不違反 precedence 的 stops
        feasible = [
            s for s in remaining
            if s.kind == "pickup" or s.order_id in picked_up
        ]
        if not feasible:
            # 理論上不會發生（所有 dropoff 對應的 pickup 都還在 remaining 裡）
            # 防禦性：先做 pickup
            feasible = [s for s in remaining if s.kind == "pickup"]
        nxt = min(feasible, key=lambda s: dist[(current, s.node)])
        route.append(nxt)
        remaining.remove(nxt)
        if nxt.kind == "pickup":
            picked_up.add(nxt.order_id)
        current = nxt.node
    return route

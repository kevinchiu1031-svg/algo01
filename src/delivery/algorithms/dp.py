"""Held-Karp 風格 TSP DP，狀態含 elapsed_time。CLRS Ch 14。"""
from dataclasses import dataclass

from delivery.models import (
    Decision,
    DistanceMatrix,
    DriverState,
    Order,
    Stop,
)


@dataclass(frozen=True)
class _Cell:
    elapsed_time: float
    accumulated_cost: float
    prev: int  # 上一個 stop index（用於回溯）；-1 表示來自起點


class DpDispatcher:
    name = "dp"

    def __init__(self, alpha: float = 1.0, beta: float = 1.0) -> None:
        self.alpha = alpha
        self.beta = beta

    def plan(
        self,
        state: DriverState,
        candidate: Order,
        all_orders: dict[int, Order],
        dist: DistanceMatrix,
    ) -> Decision:
        stops: list[Stop] = list(state.in_hand) + [
            Stop(candidate.id, "pickup", candidate.restaurant_node),
            Stop(candidate.id, "dropoff", candidate.customer_node),
        ]
        route = _held_karp(
            stops, state, all_orders, dist, self.alpha, self.beta
        )
        return Decision(accept=True, new_route=route)


def _held_karp(
    stops: list[Stop],
    state: DriverState,
    orders: dict[int, Order],
    dist: DistanceMatrix,
    alpha: float,
    beta: float,
) -> list[Stop]:
    n = len(stops)
    if n == 0:
        return []

    # 每張單的 pickup index 與 dropoff index，用於 precedence
    pickup_idx: dict[int, int] = {}
    dropoff_idx: dict[int, int] = {}
    for i, s in enumerate(stops):
        if s.kind == "pickup":
            pickup_idx[s.order_id] = i
        else:
            dropoff_idx[s.order_id] = i

    full_mask = (1 << n) - 1
    # dp[mask][last] = _Cell（last 為最後造訪的 stop index）
    dp: dict[tuple[int, int], _Cell] = {}

    # 初始化：從起點直接到每個合法 first stop
    # pickup 一律合法；dropoff 只有在其 pickup 不在 stops 中（已被 simulator 完成）時才合法
    for i, s in enumerate(stops):
        if s.kind == "pickup":
            travel = dist[(state.location_node, s.node)]
            arrival = state.current_time + travel
            order = orders[s.order_id]
            departure = max(arrival, order.food_ready_time)
            incr = alpha * (travel + (departure - arrival))
            dp[(1 << i, i)] = _Cell(
                elapsed_time=departure - state.current_time,
                accumulated_cost=incr,
                prev=-1,
            )
        else:
            # dropoff：只有當其 pickup 不在 stops 中才允許作為 first stop
            if pickup_idx.get(s.order_id) is None:
                travel = dist[(state.location_node, s.node)]
                arrival = state.current_time + travel
                departure = arrival
                order = orders[s.order_id]
                incr = alpha * travel + beta * (arrival - order.place_time)
                dp[(1 << i, i)] = _Cell(
                    elapsed_time=departure - state.current_time,
                    accumulated_cost=incr,
                    prev=-1,
                )

    # 主迴圈：擴展 mask
    for mask in range(1, full_mask + 1):
        for last in range(n):
            if not (mask & (1 << last)):
                continue
            if (mask, last) not in dp:
                continue
            cell = dp[(mask, last)]
            for nxt in range(n):
                if mask & (1 << nxt):
                    continue
                # precedence: 若 nxt 是 dropoff，且其 pickup 也在 stops 中，
                # 則對應 pickup 必須已在 mask（若 pickup 不在 stops，代表已被
                # simulator 完成，無需檢查）
                if stops[nxt].kind == "dropoff":
                    p = pickup_idx.get(stops[nxt].order_id)
                    if p is not None and not (mask & (1 << p)):
                        continue
                travel = dist[(stops[last].node, stops[nxt].node)]
                arrival = state.current_time + cell.elapsed_time + travel
                if stops[nxt].kind == "pickup":
                    order = orders[stops[nxt].order_id]
                    departure = max(arrival, order.food_ready_time)
                    incr = alpha * (travel + (departure - arrival))
                else:
                    departure = arrival
                    order = orders[stops[nxt].order_id]
                    incr = (
                        alpha * travel
                        + beta * (arrival - order.place_time)
                    )
                new_mask = mask | (1 << nxt)
                new_cost = cell.accumulated_cost + incr
                new_elapsed = departure - state.current_time
                existing = dp.get((new_mask, nxt))
                if existing is None or new_cost < existing.accumulated_cost:
                    dp[(new_mask, nxt)] = _Cell(
                        elapsed_time=new_elapsed,
                        accumulated_cost=new_cost,
                        prev=last,
                    )

    # 取 full_mask 下最佳 last
    best_last = -1
    best_cost = float("inf")
    for last in range(n):
        cell = dp.get((full_mask, last))
        if cell is not None and cell.accumulated_cost < best_cost:
            best_cost = cell.accumulated_cost
            best_last = last
    if best_last == -1:
        raise RuntimeError("DP found no feasible route — precedence/state bug")

    # 回溯還原順序
    order_indices: list[int] = []
    mask = full_mask
    last = best_last
    while last != -1:
        order_indices.append(last)
        prev = dp[(mask, last)].prev
        mask ^= (1 << last)
        last = prev
    order_indices.reverse()
    return [stops[i] for i in order_indices]

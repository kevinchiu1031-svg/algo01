"""事件驅動模擬器。"""
from __future__ import annotations
import heapq
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from delivery.metrics import cost_of_route
from delivery.models import (
    Decision,
    DistanceMatrix,
    Dispatcher,
    DriverState,
    Order,
    Stop,
)


class EventType(Enum):
    ORDER_ARRIVED = "order_arrived"
    DRIVER_ARRIVED_PICKUP = "driver_arrived_pickup"
    DRIVER_ARRIVED_DROPOFF = "driver_arrived_dropoff"


@dataclass(order=True)
class _Event:
    timestamp: float
    seq: int                       # tiebreaker for stable ordering
    kind: EventType = field(compare=False)
    payload: Any = field(compare=False)


@dataclass
class EventLogEntry:
    timestamp: float
    kind: str
    detail: str


@dataclass
class SimulationResult:
    accepted_orders: list[int]
    rejected_orders: list[int]
    driver_time_total: float
    customer_wait_total: float
    total_cost: float
    dispatcher_decision_ms: list[float]  # 每次 plan() 的耗時，毫秒
    event_log: list[EventLogEntry]


class Simulator:
    def __init__(
        self,
        dispatcher: Dispatcher,
        dist: DistanceMatrix,
        order_stream: list[Order],
        start_node: int,
        end_time: float,
        tolerance: float = 480.0,
        alpha: float = 1.0,
        beta: float = 1.0,
    ) -> None:
        self.dispatcher = dispatcher
        self.dist = dist
        self.order_stream = order_stream
        self.start_node = start_node
        self.end_time = end_time
        self.tolerance = tolerance
        self.alpha = alpha
        self.beta = beta

    def run(self) -> SimulationResult:
        import time

        state = DriverState(
            location_node=self.start_node,
            current_time=0.0,
            in_hand=[],
        )
        all_orders: dict[int, Order] = {}
        accepted: list[int] = []
        rejected: list[int] = []
        driver_time_total = 0.0
        customer_wait_total = 0.0
        decision_ms: list[float] = []
        event_log: list[EventLogEntry] = []

        heap: list[_Event] = []
        seq = 0

        def push(ts: float, kind: EventType, payload: Any) -> None:
            nonlocal seq
            heapq.heappush(heap, _Event(ts, seq, kind, payload))
            seq += 1

        # 把所有訂單到達事件預先放入 heap
        for order in self.order_stream:
            push(order.place_time, EventType.ORDER_ARRIVED, order)

        # 已排程的「下一段移動 → 抵達某 stop」事件
        # 重規劃時把後續尚未發生的舊事件作廢
        valid_arrival_seq: int | None = None

        def schedule_next_arrival(s: DriverState) -> None:
            """為 in_hand[0] 排一個 driver_arrived_* 事件，更新 valid seq。"""
            nonlocal valid_arrival_seq
            if not s.in_hand:
                valid_arrival_seq = None
                return
            nxt_stop = s.in_hand[0]
            travel = self.dist[(s.location_node, nxt_stop.node)]
            arrival_ts = s.current_time + travel
            kind = (EventType.DRIVER_ARRIVED_PICKUP
                    if nxt_stop.kind == "pickup"
                    else EventType.DRIVER_ARRIVED_DROPOFF)
            push(arrival_ts, kind, (seq, nxt_stop))  # seq 在 push 內遞增
            # 該事件的 seq = 剛剛 push 進去的那個 = seq - 1
            valid_arrival_seq = seq - 1

        # 主迴圈
        while heap:
            evt = heapq.heappop(heap)
            if evt.timestamp > self.end_time:
                break
            # 推進 clock
            if evt.timestamp > state.current_time:
                state.current_time = evt.timestamp

            if evt.kind == EventType.ORDER_ARRIVED:
                order: Order = evt.payload
                all_orders[order.id] = order
                # 硬限制：手上已 3 單
                order_ids_in_hand = {s.order_id for s in state.in_hand}
                if len(order_ids_in_hand) >= 3:
                    rejected.append(order.id)
                    event_log.append(EventLogEntry(
                        evt.timestamp, "reject",
                        f"order {order.id} (in_hand full)"))
                    continue
                # 算當前計畫成本與加入新單後成本
                cost_without, _, _ = cost_of_route(
                    state.in_hand, state, all_orders, self.dist,
                    self.alpha, self.beta,
                )
                t0 = time.perf_counter()
                decision = self.dispatcher.plan(
                    state, order, all_orders, self.dist
                )
                decision_ms.append((time.perf_counter() - t0) * 1000.0)
                if decision.new_route is None:
                    rejected.append(order.id)
                    event_log.append(EventLogEntry(
                        evt.timestamp, "reject",
                        f"order {order.id} (dispatcher returned None)"))
                    continue
                cost_with, _, _ = cost_of_route(
                    decision.new_route, state, all_orders, self.dist,
                    self.alpha, self.beta,
                )
                if cost_with > cost_without + self.tolerance:
                    rejected.append(order.id)
                    event_log.append(EventLogEntry(
                        evt.timestamp, "reject",
                        f"order {order.id} (cost +{cost_with - cost_without:.1f}s > {self.tolerance})"))
                    continue
                # 接受：更新 in_hand，重排下一個 arrival
                state.in_hand = decision.new_route
                accepted.append(order.id)
                event_log.append(EventLogEntry(
                    evt.timestamp, "accept",
                    f"order {order.id} (route len {len(state.in_hand)})"))
                schedule_next_arrival(state)

            elif evt.kind in (EventType.DRIVER_ARRIVED_PICKUP,
                              EventType.DRIVER_ARRIVED_DROPOFF):
                evt_seq, stop = evt.payload
                # 重規劃會作廢之前 schedule 的 arrival；只認最新一個
                if evt_seq != valid_arrival_seq:
                    continue
                # 抵達 stop
                state.location_node = stop.node
                if evt.kind == EventType.DRIVER_ARRIVED_PICKUP:
                    order = all_orders[stop.order_id]
                    wait = max(0.0, order.food_ready_time - state.current_time)
                    state.current_time += wait  # 等餐
                    event_log.append(EventLogEntry(
                        evt.timestamp, "pickup",
                        f"order {stop.order_id} (wait {wait:.1f}s)"))
                else:
                    order = all_orders[stop.order_id]
                    cust_wait = state.current_time - order.place_time
                    customer_wait_total += cust_wait
                    event_log.append(EventLogEntry(
                        evt.timestamp, "dropoff",
                        f"order {stop.order_id} (cust_wait {cust_wait:.1f}s)"))
                state.in_hand = state.in_hand[1:]
                schedule_next_arrival(state)

        driver_time_total = state.current_time  # 從 t=0 起到模擬結束
        total_cost = self.alpha * driver_time_total + self.beta * customer_wait_total
        return SimulationResult(
            accepted_orders=accepted,
            rejected_orders=rejected,
            driver_time_total=driver_time_total,
            customer_wait_total=customer_wait_total,
            total_cost=total_cost,
            dispatcher_decision_ms=decision_ms,
            event_log=event_log,
        )

"""MST-based 2-approximation for TSP，加 precedence 單向修補。
CLRS Ch 35.2 + Ch 21。"""
from delivery.models import (
    Decision,
    DistanceMatrix,
    DriverState,
    Order,
    Stop,
)


class TspApproxDispatcher:
    name = "tsp_approx"

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
        preorder = _mst_preorder(stops, state.location_node, dist)
        route = _repair_precedence(preorder)
        return Decision(accept=True, new_route=route)


def _mst_preorder(
    stops: list[Stop],
    start_node: int,
    dist: DistanceMatrix,
) -> list[Stop]:
    """在 {start_node} ∪ stops 上建 MST，以 start_node 為根做 DFS preorder。"""
    # 節點集合 = start_node + 每個 stop 的 node（注意 node 可能重複，但 stop 是獨立的）
    # 把 stop 當「虛擬節點」處理，用 index 編號
    n = len(stops) + 1  # 0 = start, 1..n-1 = stops
    nodes = [start_node] + [s.node for s in stops]

    # Prim's MST: O(n^2)
    in_tree = [False] * n
    key = [float("inf")] * n
    parent = [-1] * n
    key[0] = 0.0
    for _ in range(n):
        # 選 key 最小且未加入的
        u = -1
        for i in range(n):
            if not in_tree[i] and (u == -1 or key[i] < key[u]):
                u = i
        in_tree[u] = True
        for v in range(n):
            if not in_tree[v]:
                d = dist[(nodes[u], nodes[v])]
                if d < key[v]:
                    key[v] = d
                    parent[v] = u

    # 從 parent 陣列建鄰接表
    children: list[list[int]] = [[] for _ in range(n)]
    for v in range(1, n):
        children[parent[v]].append(v)

    # DFS preorder from root (index 0)
    order_idx: list[int] = []

    def dfs(u: int) -> None:
        order_idx.append(u)
        # 子節點按 key（邊權）由小到大訪問，提升解品質
        for c in sorted(children[u], key=lambda x: key[x]):
            dfs(c)

    dfs(0)
    # 去掉 root（不是 stop），把 idx 對應回 Stop
    return [stops[i - 1] for i in order_idx if i != 0]


def _repair_precedence(preorder: list[Stop]) -> list[Stop]:
    """單向修補：從前往後掃，遇到 dropoff 但對應 pickup 還沒出現時，
    把該 pickup 從後方拉到當前位置之前。

    若某 order 只有 dropoff 沒有 pickup（pickup 已被 simulator 完成），
    直接把該 order 視為已 picked_up。"""
    result: list[Stop] = []
    remaining = list(preorder)
    has_pickup = {s.order_id for s in preorder if s.kind == "pickup"}
    picked_up: set[int] = {
        s.order_id for s in preorder
        if s.kind == "dropoff" and s.order_id not in has_pickup
    }
    while remaining:
        s = remaining.pop(0)
        if s.kind == "dropoff" and s.order_id not in picked_up:
            pickup_idx = next(
                (i for i, t in enumerate(remaining)
                 if t.order_id == s.order_id and t.kind == "pickup"),
                None,
            )
            if pickup_idx is not None:
                pickup = remaining.pop(pickup_idx)
                result.append(pickup)
                picked_up.add(pickup.order_id)
        result.append(s)
        if s.kind == "pickup":
            picked_up.add(s.order_id)
    return result

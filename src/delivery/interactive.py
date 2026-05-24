# -*- coding: utf-8 -*-
"""互動式路線規劃模組：接收使用者點選的取/送餐 lat-lng，
Snap 到路網節點，以三種演算法規劃路線並回傳結果。"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field

import networkx as nx

from delivery.algorithms.dp import DpDispatcher
from delivery.algorithms.greedy import GreedyDispatcher
from delivery.algorithms.tsp_approx import TspApproxDispatcher
from delivery.map_loader import make_distance_matrix
from delivery.models import (
    Decision,
    DistanceMatrix,
    DriverState,
    Order,
    Stop,
)

# ---------------------------------------------------------------------------
# 顯示名稱
# ---------------------------------------------------------------------------
_DISPLAY_NAMES = {
    "greedy": "Greedy（貪婪）",
    "tsp_approx": "TSP 近似（TSP Approximation）",
    "dp": "動態規劃（Dynamic Programming / DP）",
}


# ---------------------------------------------------------------------------
# 資料類別
# ---------------------------------------------------------------------------
@dataclass
class AlgoResult:
    name: str                          # "greedy" | "tsp_approx" | "dp"
    display_name: str                  # 中文顯示名稱
    success: bool
    total_distance_m: float
    total_time_s: float
    compute_ms: float
    polyline: list[tuple[float, float]]  # 依序 (lat, lng) 沿實際路網節點
    num_stops: int                     # == 2 * num_orders
    error: str | None = None

    def to_dict(self) -> dict:
        """回傳 JSON 可序列化的字典；polyline 輸出為 [[lat, lng], ...] 格式。"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "success": self.success,
            "total_distance_m": self.total_distance_m,
            "total_time_s": self.total_time_s,
            "compute_ms": self.compute_ms,
            "polyline": [list(pt) for pt in self.polyline],
            "num_stops": self.num_stops,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# 工具函式
# ---------------------------------------------------------------------------
def nearest_node(graph: nx.MultiDiGraph, lat: float, lng: float) -> int:
    """暴力搜尋最近的路網節點（不依賴 sklearn）。
    使用 cos(lat) 修正經度方向的距離比例。
    節點屬性：y = 緯度（lat），x = 經度（lng）。
    """
    cos_lat = math.cos(math.radians(lat))
    best_node: int | None = None
    best_dist_sq: float = float("inf")

    for node, data in graph.nodes(data=True):
        dlat = data["y"] - lat
        dlng = (data["x"] - lng) * cos_lat
        dist_sq = dlat * dlat + dlng * dlng
        if dist_sq < best_dist_sq:
            best_dist_sq = dist_sq
            best_node = node

    if best_node is None:
        raise ValueError("路網圖中沒有節點")
    return best_node


def plan_full_route(
    dispatcher,
    orders: list[Order],
    start_node: int,
    dist: DistanceMatrix,
) -> list[Stop]:
    """將所有訂單依序交給 dispatcher.plan，接受每次的新路線，
    最終回傳完整的 Stop 序列（長度 == 2 * len(orders)）。
    """
    state = DriverState(location_node=start_node, current_time=0.0, in_hand=[])
    all_orders: dict[int, Order] = {}
    for order in orders:
        all_orders[order.id] = order
        decision: Decision = dispatcher.plan(state, order, all_orders, dist)
        if decision.accept and decision.new_route is not None:
            state.in_hand = decision.new_route
    return state.in_hand


def route_geometry(
    graph: nx.MultiDiGraph,
    start_node: int,
    route: list[Stop],
    speed_mps: float = 5.0,
) -> tuple[list[tuple[float, float]], float, float]:
    """計算從 start_node 依序訪問 route 各停靠點的實際路網折線、總距離（公尺）
    及總行駛時間（秒）。

    對每段 (u -> v) 使用 networkx.shortest_path(weight='travel_time')，
    並取平行邊中 length 最短者計算指標。回傳
    (polyline_latlng, total_distance_m, total_time_s)。

    若某段無路徑，拋出 NetworkXNoPath（呼叫端負責 catch）。
    """
    if not route:
        # 無停靠點：只回傳起點座標
        node_data = graph.nodes[start_node]
        return ([(node_data["y"], node_data["x"])], 0.0, 0.0)

    node_sequence = [start_node] + [s.node for s in route]
    polyline: list[tuple[float, float]] = []
    total_distance_m = 0.0
    total_time_s = 0.0

    for seg_idx in range(len(node_sequence) - 1):
        u = node_sequence[seg_idx]
        v = node_sequence[seg_idx + 1]

        # 取最短路徑（以 travel_time 為權重）
        path_nodes: list[int] = nx.shortest_path(
            graph, u, v, weight="travel_time"
        )

        # 逐段累積距離與時間（取平行邊最小 length）
        for i in range(len(path_nodes) - 1):
            a, b = path_nodes[i], path_nodes[i + 1]
            edge_data_dict = graph[a][b]  # MultiDiGraph: {key: data_dict}
            # 選 length 最小的平行邊
            min_length = float("inf")
            min_travel_time = float("inf")
            for key, edata in edge_data_dict.items():
                edge_len = edata.get("length", 0.0)
                edge_tt = edata.get("travel_time", edge_len / speed_mps if edge_len > 0 else 1.0)
                if edge_len < min_length:
                    min_length = edge_len
                    min_travel_time = edge_tt
            total_distance_m += min_length
            total_time_s += min_travel_time

        # 建立折線座標（避免相鄰 segment 的連接節點重複）
        for i, node_id in enumerate(path_nodes):
            # 第一個 segment 的起點加入；之後各 segment 跳過第一個節點（已是上段終點）
            if seg_idx == 0 or i > 0:
                nd = graph.nodes[node_id]
                polyline.append((nd["y"], nd["x"]))

    return polyline, total_distance_m, total_time_s


# ---------------------------------------------------------------------------
# 主要比較函式
# ---------------------------------------------------------------------------
def compare_algorithms(
    graph: nx.MultiDiGraph,
    dist: DistanceMatrix,
    pickups: list[tuple[float, float]],
    dropoffs: list[tuple[float, float]],
    start: tuple[float, float] | None = None,
    speed_mps: float = 5.0,
) -> list[AlgoResult]:
    """接收一組取餐/送餐點（lat, lng），snap 到路網，
    分別以三種演算法規劃路線並回傳比較結果。

    參數
    ----
    pickups   : 取餐點 [(lat, lng), ...]
    dropoffs  : 送餐點 [(lat, lng), ...]，與 pickups 一一對應
    start     : 司機起點 (lat, lng)；若為 None 則以第一個取餐節點為起點
    speed_mps : 行駛速度（公尺/秒），預設 5.0

    回傳
    ----
    [AlgoResult] 共 3 筆，順序：greedy, tsp_approx, dp
    """
    if len(pickups) != len(dropoffs) or len(pickups) == 0:
        raise ValueError("取餐點與送餐點數量必須相同且至少各一個")

    # Snap 到路網節點
    orders: list[Order] = []
    for i, (pu_latlng, do_latlng) in enumerate(zip(pickups, dropoffs)):
        rest_node = nearest_node(graph, pu_latlng[0], pu_latlng[1])
        cust_node = nearest_node(graph, do_latlng[0], do_latlng[1])
        orders.append(
            Order(
                id=i + 1,
                restaurant_node=rest_node,
                customer_node=cust_node,
                place_time=0.0,
                prep_time=0.0,
            )
        )

    # 司機起點
    if start is not None:
        start_node = nearest_node(graph, start[0], start[1])
    else:
        start_node = orders[0].restaurant_node

    # 確認 make_distance_matrix 已更新 travel_time（若未更新則重跑一次）
    # 注意：若 dist 已由外部建立，edges 可能已有 travel_time；
    # 直接使用傳入的 dist，route_geometry 需要 graph edges 有 travel_time。
    # 為保險，呼叫 make_distance_matrix 更新邊屬性（不重建 dist）。
    make_distance_matrix(graph, speed_mps=speed_mps)

    # 建立三個 dispatcher
    dispatchers = [
        GreedyDispatcher(),
        TspApproxDispatcher(),
        DpDispatcher(alpha=1.0, beta=1.0),
    ]

    results: list[AlgoResult] = []

    for dispatcher in dispatchers:
        algo_name = dispatcher.name
        display_name = _DISPLAY_NAMES[algo_name]
        compute_ms = 0.0
        route: list[Stop] = []

        try:
            # 只計算規劃時間（不含 route_geometry）
            t0 = time.perf_counter()
            route = plan_full_route(dispatcher, orders, start_node, dist)
            t1 = time.perf_counter()
            compute_ms = (t1 - t0) * 1000.0

            polyline, total_dist, total_time = route_geometry(
                graph, start_node, route, speed_mps=speed_mps
            )

            results.append(
                AlgoResult(
                    name=algo_name,
                    display_name=display_name,
                    success=True,
                    total_distance_m=total_dist,
                    total_time_s=total_time,
                    compute_ms=compute_ms,
                    polyline=polyline,
                    num_stops=len(route),
                )
            )
        except Exception as exc:
            results.append(
                AlgoResult(
                    name=algo_name,
                    display_name=display_name,
                    success=False,
                    total_distance_m=0.0,
                    total_time_s=0.0,
                    compute_ms=compute_ms,
                    polyline=[],
                    num_stops=len(route),
                    error=str(exc),
                )
            )

    return results


# ---------------------------------------------------------------------------
# 中文分析文字生成
# ---------------------------------------------------------------------------
def chinese_analysis(results: list[AlgoResult]) -> str:
    """依三種演算法的結果生成繁體中文分析文字（2–4 句）。
    指出計算最快的演算法、路徑最短的演算法，及整體評語。
    若有演算法失敗，亦會提及。
    """
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    sentences: list[str] = []

    # 失敗提示
    if failed:
        names = "、".join(r.display_name for r in failed)
        sentences.append(f"{names} 在本次計算中發生錯誤，無法產生有效路線。")

    if not successful:
        sentences.append("所有演算法均未能成功規劃路線，請檢查輸入資料。")
        return "".join(sentences)

    fastest = min(successful, key=lambda r: r.compute_ms)
    shortest = min(successful, key=lambda r: r.total_distance_m)

    # 單一訂單：只有一組取/送餐點時（num_stops<=2），唯一可行路線就是「取餐→送餐」，
    # 三種演算法必然產生相同路徑，比較距離無意義，僅計算時間有差。
    max_stops = max(r.num_stops for r in successful)
    if max_stops <= 2:
        sentences.append(
            f"本次僅有單一組取餐／送餐地點，唯一可行的路線就是「先取餐再送餐」，"
            f"因此三種演算法必然產生完全相同的路徑（總距離約 "
            f"{successful[0].total_distance_m:.0f} 公尺、預估行駛時間約 "
            f"{successful[0].total_time_s:.0f} 秒），差異僅在於計算時間。"
        )
        sentences.append(
            f"其中 {fastest.display_name} 計算速度最快（耗時 {fastest.compute_ms:.2f} ms）。"
        )
        sentences.append(
            "若要比較三種演算法的路徑品質差異，請在地圖上新增多組取／送餐點"
            "（建議 2～3 組以上），演算法才會對停靠順序做出不同的最佳化決策。"
        )
        return "".join(sentences)

    # 多訂單但路徑長度幾乎相同（差距 < 0.5%）：避免誤導性地宣稱某演算法「較短」。
    longest_dist = max(r.total_distance_m for r in successful)
    if longest_dist - shortest.total_distance_m < max(1.0, 0.005 * longest_dist):
        sentences.append(
            f"本次三種演算法產生的路徑長度幾乎相同（約 "
            f"{shortest.total_distance_m:.0f} 公尺），主要差異在於計算時間；"
            f"其中 {fastest.display_name} 計算速度最快（耗時 {fastest.compute_ms:.2f} ms）。"
        )
        return "".join(sentences)

    if fastest.name == shortest.name:
        sentences.append(
            f"{fastest.display_name} 計算速度最快，且在本次案例中同時產生了最短的路徑結果，"
            f"總距離約 {fastest.total_distance_m:.0f} 公尺。"
        )
    else:
        sentences.append(
            f"{fastest.display_name} 計算速度最快（耗時 {fastest.compute_ms:.1f} ms），"
            f"適合即時排程。"
        )
        sentences.append(
            f"{shortest.display_name} 在本次案例中產生了最短路徑，"
            f"總距離約 {shortest.total_distance_m:.0f} 公尺，"
            f"但計算時間相對較長（{shortest.compute_ms:.1f} ms）。"
        )

    # 整體評語
    if len(successful) == 3:
        sentences.append(
            "整體而言，貪婪演算法適合訂單量大且要求快速回應的場景；"
            "TSP 近似演算法在路線品質與速度之間取得平衡；"
            "DP 演算法適合訂單數較少但追求最優解的情境。"
        )
    elif len(successful) > 0:
        sentences.append("建議選擇成功執行且路徑較短的演算法作為最終路線規劃依據。")

    return "".join(sentences)

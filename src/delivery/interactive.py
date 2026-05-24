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
    polyline: list[tuple[float, float]]  # 依序 (lat, lng)：沿實際道路 + 接駁到原始點位
    num_stops: int                     # == 2 * num_orders
    # 每個停靠點的驗證資訊（取餐/送餐），含原始座標、snap 節點座標、是否已被 polyline 經過
    visited_stops: list[dict] = field(default_factory=list)
    all_stops_visited: bool = True     # 是否所有取/送餐點都被路線經過
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
            "visited_stops": self.visited_stops,
            "all_stops_visited": self.all_stops_visited,
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


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """兩經緯度間的 haversine 大圓距離（公尺）。

    用於「原始點位↔最近道路節點」的接駁段距離：道路主路徑沿真實道路，
    接駁段則是從道路節點抵達使用者實際選定位置的最後一小段直線距離。
    """
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _road_path(
    graph: nx.MultiDiGraph, u: int, v: int, speed_mps: float
) -> tuple[list[tuple[float, float]], float, float]:
    """u→v 沿道路 shortest path（weight='travel_time'）的
    (座標序列[含 u 與 v 兩端], 道路距離公尺, 道路時間秒)。

    平行邊取 length 最小者。無路徑時拋出 networkx.NetworkXNoPath。
    """
    path_nodes: list[int] = nx.shortest_path(graph, u, v, weight="travel_time")
    dist_m = 0.0
    time_s = 0.0
    for i in range(len(path_nodes) - 1):
        a, b = path_nodes[i], path_nodes[i + 1]
        min_length = float("inf")
        min_travel_time = float("inf")
        for edata in graph[a][b].values():  # MultiDiGraph 平行邊
            edge_len = edata.get("length", 0.0)
            edge_tt = edata.get(
                "travel_time", edge_len / speed_mps if edge_len > 0 else 1.0
            )
            if edge_len < min_length:
                min_length = edge_len
                min_travel_time = edge_tt
        dist_m += min_length
        time_s += min_travel_time
    coords = [(graph.nodes[n]["y"], graph.nodes[n]["x"]) for n in path_nodes]
    return coords, dist_m, time_s


def route_geometry(
    graph: nx.MultiDiGraph,
    start_node: int,
    route: list[Stop],
    speed_mps: float = 5.0,
) -> tuple[list[tuple[float, float]], float, float]:
    """（純道路版）從 start_node 依序走訪 route 各停靠『節點』的道路折線與距離/時間。

    僅沿道路節點，不含使用者原始點位的接駁段。保留作為純道路幾何的可重用元件，
    並由測試驗證道路折線是否正確。實際展示路線請用 build_visited_route。
    """
    if not route:
        nd = graph.nodes[start_node]
        return ([(nd["y"], nd["x"])], 0.0, 0.0)

    node_sequence = [start_node] + [s.node for s in route]
    polyline: list[tuple[float, float]] = []
    total_distance_m = 0.0
    total_time_s = 0.0
    for seg_idx in range(len(node_sequence) - 1):
        coords, d, t = _road_path(
            graph, node_sequence[seg_idx], node_sequence[seg_idx + 1], speed_mps
        )
        total_distance_m += d
        total_time_s += t
        # 第一段加入全部座標；之後各段跳過第一個（與上段終點重複）
        polyline.extend(coords if seg_idx == 0 else coords[1:])
    return polyline, total_distance_m, total_time_s


def build_visited_route(
    graph: nx.MultiDiGraph,
    start: tuple[tuple[float, float], int],
    stops: list[tuple[tuple[float, float], int]],
    speed_mps: float = 5.0,
) -> tuple[list[tuple[float, float]], float, float, list[bool]]:
    """建立「嚴格經過每個使用者原始點位」的完整路線。

    start 與每個 stop 皆為 (原始經緯度 (lat,lng), snap 後最近道路節點)。

    完整路線結構（確保 polyline 視覺上真正經過使用者點選的位置）：
        起點原始座標 → 起點最近道路節點 → [道路 shortest path 節點序列]
        → 停靠點最近道路節點 → 停靠點原始座標
        →（下一段）由原始座標連回最近道路節點 → [道路 shortest path] → ...

    - 道路主路徑：沿真實 OSM/NetworkX 道路節點（_road_path）。
    - 接駁段：原始點位↔最近道路節點，以 haversine 直線計算並繪製，代表從道路
      節點抵達/離開使用者實際選定位置的最後一小段。總距離與時間都包含接駁段。

    回傳 (polyline, 總距離公尺, 總時間秒, 每個 stop 原始座標是否已被 polyline 經過)。
    若某兩節點間無道路路徑，拋出 networkx.NetworkXNoPath（呼叫端標記為失敗）。
    """
    eps = 1e-9
    polyline: list[tuple[float, float]] = []
    total_d = 0.0
    total_t = 0.0

    def add_point(pt: tuple[float, float]) -> None:
        # 跳過與上一點重複的座標（例如原始點位恰好等於節點座標時，避免重複點）
        if (not polyline
                or abs(polyline[-1][0] - pt[0]) > eps
                or abs(polyline[-1][1] - pt[1]) > eps):
            polyline.append(pt)

    def add_connector(a: tuple[float, float], b: tuple[float, float]) -> None:
        nonlocal total_d, total_t
        d = _haversine_m(a[0], a[1], b[0], b[1])
        total_d += d
        total_t += d / speed_mps if speed_mps > 0 else 0.0
        add_point(b)

    start_orig, start_node = start
    start_node_coord = (graph.nodes[start_node]["y"], graph.nodes[start_node]["x"])
    add_point(start_orig)                          # 起點原始座標
    add_connector(start_orig, start_node_coord)    # 接駁：起點原始 → 最近節點

    prev_node = start_node
    n = len(stops)
    for idx, (orig, node) in enumerate(stops):
        coords, d, t = _road_path(graph, prev_node, node, speed_mps)
        total_d += d
        total_t += t
        for c in coords[1:]:                       # coords[0] 為 prev_node 座標（已在折線中）
            add_point(c)
        node_coord = (graph.nodes[node]["y"], graph.nodes[node]["x"])
        add_point(node_coord)                      # 確保最近道路節點在折線中
        add_connector(node_coord, orig)            # 接駁：最近節點 → 停靠點原始座標
        if idx < n - 1:
            add_connector(orig, node_coord)        # 下一段：原始座標 → 最近節點
        prev_node = node

    # 驗證每個 stop 的原始座標確實出現在 polyline 中（容差 ~1e-7 度 ≈ 1cm）
    included: list[bool] = []
    for orig, _node in stops:
        hit = any(
            abs(p[0] - orig[0]) <= 1e-7 and abs(p[1] - orig[1]) <= 1e-7
            for p in polyline
        )
        included.append(hit)
    return polyline, total_d, total_t, included


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

    # 確保 graph 邊有 travel_time（route_geometry / _road_path 需要）
    make_distance_matrix(graph, speed_mps=speed_mps)

    # Snap 到路網節點；同時保留使用者原始點位座標（不可被節點取代）
    orders: list[Order] = []
    pickup_orig: dict[int, tuple[float, float]] = {}
    dropoff_orig: dict[int, tuple[float, float]] = {}
    for i, (pu_latlng, do_latlng) in enumerate(zip(pickups, dropoffs)):
        oid = i + 1
        pickup_orig[oid] = (pu_latlng[0], pu_latlng[1])
        dropoff_orig[oid] = (do_latlng[0], do_latlng[1])
        orders.append(
            Order(
                id=oid,
                restaurant_node=nearest_node(graph, pu_latlng[0], pu_latlng[1]),
                customer_node=nearest_node(graph, do_latlng[0], do_latlng[1]),
                place_time=0.0,
                prep_time=0.0,
            )
        )

    # 司機起點：給定則用給定原始座標；否則以第一張單的取餐點原始座標為起點
    if start is not None:
        start_node = nearest_node(graph, start[0], start[1])
        start_orig = (start[0], start[1])
    else:
        start_node = orders[0].restaurant_node
        start_orig = pickup_orig[orders[0].id]
    start_wp = (start_orig, start_node)

    def orig_of(stop: Stop) -> tuple[float, float]:
        return (pickup_orig[stop.order_id] if stop.kind == "pickup"
                else dropoff_orig[stop.order_id])

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
            # 演算法仍以 snap 後的道路節點進行排序與距離計算（核心邏輯不變）。
            # 只計算規劃時間（不含後續路線幾何）。
            t0 = time.perf_counter()
            route = plan_full_route(dispatcher, orders, start_node, dist)
            compute_ms = (time.perf_counter() - t0) * 1000.0

            # 將每個 Stop 對應回原始 pickup/dropoff 座標，組成 waypoint
            stop_wps = [(orig_of(s), s.node) for s in route]
            polyline, total_dist, total_time, included = build_visited_route(
                graph, start_wp, stop_wps, speed_mps=speed_mps
            )

            visited_stops: list[dict] = []
            for s, inc in zip(route, included):
                orig = orig_of(s)
                visited_stops.append({
                    "order_id": s.order_id,
                    "kind": s.kind,
                    "kind_zh": "取餐" if s.kind == "pickup" else "送餐",
                    "original": [orig[0], orig[1]],
                    "snapped": [graph.nodes[s.node]["y"], graph.nodes[s.node]["x"]],
                    "included_in_polyline": bool(inc),
                })

            if not all(included):
                missing = [
                    f"訂單 {vs['order_id']} 的{vs['kind_zh']}點"
                    for vs in visited_stops if not vs["included_in_polyline"]
                ]
                results.append(AlgoResult(
                    name=algo_name, display_name=display_name, success=False,
                    total_distance_m=total_dist, total_time_s=total_time,
                    compute_ms=compute_ms, polyline=polyline, num_stops=len(route),
                    visited_stops=visited_stops, all_stops_visited=False,
                    error="下列點位未被包含在路線中：" + "、".join(missing),
                ))
                continue

            results.append(AlgoResult(
                name=algo_name, display_name=display_name, success=True,
                total_distance_m=total_dist, total_time_s=total_time,
                compute_ms=compute_ms, polyline=polyline, num_stops=len(route),
                visited_stops=visited_stops, all_stops_visited=True,
            ))
        except nx.NetworkXNoPath:
            results.append(AlgoResult(
                name=algo_name, display_name=display_name, success=False,
                total_distance_m=0.0, total_time_s=0.0, compute_ms=compute_ms,
                polyline=[], num_stops=len(route), visited_stops=[],
                all_stops_visited=False,
                error="部分停靠點之間沒有可行的道路路徑，無法產生完整路線。",
            ))
        except Exception as exc:
            results.append(AlgoResult(
                name=algo_name, display_name=display_name, success=False,
                total_distance_m=0.0, total_time_s=0.0, compute_ms=compute_ms,
                polyline=[], num_stops=len(route), visited_stops=[],
                all_stops_visited=False,
                error=f"路線規劃發生錯誤：{exc}",
            ))

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

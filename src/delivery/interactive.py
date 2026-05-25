# -*- coding: utf-8 -*-
"""互動式路線規劃模組：接收使用者點選的取/送餐 lat-lng，
Snap 到路網節點，以三種演算法規劃路線並回傳結果。"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import networkx as nx

from delivery.algorithms.dp import DpDispatcher
from delivery.algorithms.greedy import GreedyDispatcher
from delivery.algorithms.tsp_approx import TspApproxDispatcher
from delivery.map_loader import make_distance_matrix
from delivery.metrics import route_timeline
from delivery.models import (
    WAIT_TOLERANCE_S,
    Decision,
    DistanceMatrix,
    DriverState,
    Order,
    Stop,
)

# 餐點製作時間允許範圍（分鐘）
PREP_TIME_MIN_MINUTES = 0.0
PREP_TIME_MAX_MINUTES = 25.0

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
    total_distance_m: float            # = 主路線距離 + 停靠接近距離
    total_time_s: float
    compute_ms: float
    polyline: list[tuple[float, float]]  # 單一連續折線 (lat, lng)：沿有向道路，經過各停靠點的「可合法抵達馬路位置」
    num_stops: int                     # == 2 * num_orders
    road_distance_m: float = 0.0       # 主路線距離（沿有向道路 shortest path）
    approach_distance_m: float = 0.0   # 停靠接近距離（馬路位置→門口的最後一小段，總和）
    # 餐點製作時間 / 騎手等待相關
    total_wait_s: float = 0.0          # 騎手在各餐廳的等待秒數總和（餐未好的空等）
    total_driver_time_s: float = 0.0   # 騎手總時間（行駛 + 等待），由 dist 矩陣推算
    exceeds_wait_tolerance: bool = False  # 是否有任一取餐點等待超過容忍門檻
    orders_info: list[dict] = field(default_factory=list)  # 各訂單 prep_time / ready 資訊
    # 每個停靠點的驗證資訊（取餐/送餐）
    visited_stops: list[dict] = field(default_factory=list)
    all_stops_visited: bool = True     # 是否所有取/送餐點都被路線確實抵達
    error: str | None = None

    def to_dict(self) -> dict:
        """回傳 JSON 可序列化的字典；polyline 輸出為 [[lat, lng], ...] 格式。"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "success": self.success,
            "total_distance_m": self.total_distance_m,
            "road_distance_m": self.road_distance_m,
            "approach_distance_m": self.approach_distance_m,
            "total_time_s": self.total_time_s,
            "compute_ms": self.compute_ms,
            "total_wait_s": self.total_wait_s,
            "total_driver_time_s": self.total_driver_time_s,
            "exceeds_wait_tolerance": self.exceeds_wait_tolerance,
            "orders_info": self.orders_info,
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


# 接駁段（馬路位置→門口）以步行/牽車的低速估算，明確區別於道路行駛速度。
WALK_SPEED_MPS = 1.2


def _project_to_segment(
    plat: float, plng: float,
    alat: float, alng: float,
    blat: float, blng: float,
) -> tuple[float, float, float]:
    """把點 P 投影到線段 A-B 上，回傳 (投影點 lat, 投影點 lng, 參數 t∈[0,1])。
    以 P 緯度的 cos 值修正經度比例，做近似平面投影（< 數公里尺度足夠精確）。
    """
    coslat = math.cos(math.radians(plat))
    ax, ay = alng * coslat, alat
    bx, by = blng * coslat, blat
    px, py = plng * coslat, plat
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom == 0.0:
        t = 0.0
    else:
        t = ((px - ax) * dx + (py - ay) * dy) / denom
        t = max(0.0, min(1.0, t))
    proj_lat = ay + t * dy
    proj_lng = (ax + t * dx) / coslat
    return proj_lat, proj_lng, t


def snap_to_edge(graph: nx.MultiDiGraph, lat: float, lng: float) -> dict:
    """把使用者點選位置 snap 到「最近的可行駛有向道路邊」，而非單一節點。

    回傳 dict：
      - approach        : (lat, lng) 投影到該道路邊上的點＝機車可合法抵達的馬路位置
      - enter_node (u)  : 該有向邊上游節點（行駛方向 u→v）
      - exit_node  (v)  : 該有向邊下游節點
      - perp_m          : 原始點到該道路邊的垂直距離（公尺）≈ 接駁距離

    機車沿 u→v 方向行駛，途中經過 approach 點，確保「靠右、不逆向」：
    抵達停靠點是沿合法行駛方向經過該道路側，而非橫跨對向車道。
    若圖中沒有邊，退回最近節點（enter==exit）。
    """
    best: tuple | None = None  # (perp_m, u, v, k, plat, plng, t)
    for u, v, k, data in graph.edges(keys=True, data=True):
        au, av = graph.nodes[u], graph.nodes[v]
        plat, plng, t = _project_to_segment(
            lat, lng, au["y"], au["x"], av["y"], av["x"]
        )
        perp = _haversine_m(lat, lng, plat, plng)
        cand = (perp, u, v, k, plat, plng, t)
        if best is None or cand[:4] < best[:4]:  # 以 (perp,u,v,k) 做穩定排序
            best = cand
    if best is None:
        n = nearest_node(graph, lat, lng)
        nd = graph.nodes[n]
        return {
            "approach": (nd["y"], nd["x"]),
            "enter_node": n, "exit_node": n,
            "perp_m": _haversine_m(lat, lng, nd["y"], nd["x"]),
            "edge_key": None, "t": 0.0,
        }
    perp, u, v, k, plat, plng, t = best
    return {
        "approach": (plat, plng),
        "enter_node": u, "exit_node": v,
        "perp_m": perp,
        "edge_key": k, "t": t,
    }


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


def _edge_curve_points(
    data: dict, u_coord: tuple[float, float], v_coord: tuple[float, float]
) -> list[tuple[float, float]] | None:
    """若邊帶有 shapely LineString geometry，回傳沿道路曲線（含兩端）的 (lat,lng) 序列。

    OSMnx geometry 的座標為 (lng, lat) 對。方向可能與 u→v 相反，故依端點對齊：
    若曲線第一點較接近 v_coord 則反轉，確保輸出由 u_coord 往 v_coord。
    無 geometry 時回傳 None（呼叫端退回直線弦）。
    """
    geom = data.get("geometry")
    coords = getattr(geom, "coords", None)
    if coords is None:
        return None
    pts = [(lat, lng) for (lng, lat) in coords]  # shapely 為 (x=lng, y=lat)
    if len(pts) < 2:
        return None
    # 對齊方向：geometry 端點未必與 u→v 同序
    d_first = _haversine_m(*pts[0], *u_coord)
    d_last = _haversine_m(*pts[-1], *u_coord)
    if d_last < d_first:
        pts = list(reversed(pts))
    return pts


def _approach_split_index(
    curve: list[tuple[float, float]], approach: tuple[float, float]
) -> int:
    """在曲線頂點序列中找到 approach 的插入位置（split index）。

    回傳 idx，使曲線頂點 curve[1:idx] 屬「u→approach」段（在 approach 之前），
    curve[idx:-1] 屬「approach→v」段。以「投影參數最接近 approach 的線段」決定切點：
    找出 approach 投影落點所在的線段，其後一個頂點即為 split index。
    """
    best_idx = len(curve) - 1
    best_d = float("inf")
    for i in range(len(curve) - 1):
        a, b = curve[i], curve[i + 1]
        plat, plng, _t = _project_to_segment(
            approach[0], approach[1], a[0], a[1], b[0], b[1]
        )
        d = _haversine_m(approach[0], approach[1], plat, plng)
        if d < best_d:
            best_d = d
            best_idx = i + 1  # approach 落在 curve[i]~curve[i+1]，分界在 i+1
    return best_idx


def _add_curve_before_approach(add_point, curve, approach) -> None:
    """加入 u→approach 段的曲線中間頂點（不含端點 u 與 approach 本身）。"""
    idx = _approach_split_index(curve, approach)
    for c in curve[1:idx]:
        add_point(c)


def _add_curve_after_approach(add_point, curve, approach) -> None:
    """加入 approach→v 段的曲線中間頂點（不含 approach 與端點 v）。"""
    idx = _approach_split_index(curve, approach)
    for c in curve[idx:-1]:
        add_point(c)


def build_visited_route(
    graph: nx.MultiDiGraph,
    start: tuple[tuple[float, float], int],
    stops: list[tuple],
    speed_mps: float = 5.0,
    walk_speed_mps: float = WALK_SPEED_MPS,
) -> dict:
    """建立「單一條連續、靠右不逆向」且確實抵達每個停靠點的路線。

    start：(起點 lat/lng, 起點道路節點)。
    每個 stop：(原始門口 lat/lng, 可抵達馬路位置 approach lat/lng, 進入節點 u, 離開節點 v,
                [edge_key], [t])。其中 edge_key 為 snap 選定的平行邊鍵；t∈[0,1] 為
                approach 在 u→v 邊上的投影參數（u 端 t=0、v 端 t=1）。後兩者為選填，
                未提供時退回以直線弦估算距離與幾何（保持 toy-graph 既有行為不變）。

    路線結構（每個停靠點）：
        ...上一站離開節點 → [有向道路 shortest path] → 進入節點 u
        → 沿該道路邊 u→approach→v 行駛（合法方向，經過可抵達的馬路位置）→ 離開節點 v ...

    - 主路線：全程沿 directed graph 的 shortest path，遵守道路方向；需要折返時會
      自然繞經可轉向路口，不會在路段中逆向或瞬移迴轉。polyline 為單一 ordered 序列，
      可重複經過同一路段，但不分裂成多條分支。
    - 邊內段（u→approach→v）：距離以該邊真實 length 依 t 切分（length*t 與 length*(1-t)），
      幾何則沿該邊的 shapely geometry 曲線描繪（無 geometry 時退回直線）；approach 點
      必定原樣出現在 polyline 中，確保 arrival_index/included 正確。
    - 接駁段：approach（馬路位置）→ 門口原始座標，屬「靠邊停車後步行/牽車」的最後幾公尺，
      不計入主路線道路距離，另計為 approach_distance（以步行速度估時）。

    回傳 dict：polyline、road_distance_m、road_time_s、approach_distance_m、
    approach_time_s、arrival_indices（各停靠點 approach 點在 polyline 的索引）、
    included（各停靠點是否被路線確實抵達）。
    無道路路徑時拋出 networkx.NetworkXNoPath（呼叫端標記為失敗）。
    """
    eps = 1e-9
    polyline: list[tuple[float, float]] = []
    road_d = 0.0
    road_t = 0.0
    approach_d = 0.0
    arrival_indices: list[int] = []

    def add_point(pt: tuple[float, float]) -> None:
        if (not polyline
                or abs(polyline[-1][0] - pt[0]) > eps
                or abs(polyline[-1][1] - pt[1]) > eps):
            polyline.append(pt)

    start_node = start[1]
    add_point((graph.nodes[start_node]["y"], graph.nodes[start_node]["x"]))

    prev_node = start_node
    for stop in stops:
        # stop 可能為 4-tuple（舊式）或 6-tuple（含 edge_key, t）
        orig, approach, enter_u, exit_v = stop[0], stop[1], stop[2], stop[3]
        edge_key = stop[4] if len(stop) > 4 else None
        t_param = stop[5] if len(stop) > 5 else None
        # 1) 由上一站沿有向道路抵達進入節點 u
        coords, d, t = _road_path(graph, prev_node, enter_u, speed_mps)
        road_d += d
        road_t += t
        for c in coords[1:]:
            add_point(c)
        # 2) 沿該道路邊 u→approach→v 行駛（合法方向），approach 為實際抵達的馬路位置
        u_coord = (graph.nodes[enter_u]["y"], graph.nodes[enter_u]["x"])
        v_coord = (graph.nodes[exit_v]["y"], graph.nodes[exit_v]["x"])

        # 取該邊資料（優先用 snap 記錄的 edge_key；否則取 length 最小的平行邊）
        edata: dict | None = None
        if enter_u != exit_v and graph.has_edge(enter_u, exit_v):
            edges = graph[enter_u][exit_v]
            if edge_key is not None and edge_key in edges:
                edata = edges[edge_key]
            else:
                edata = min(edges.values(),
                            key=lambda e: e.get("length", float("inf")))

        edge_len = edata.get("length") if edata is not None else None

        # 2a) 距離：以真實 length 依 t 切分；length 缺失時退回直線弦
        if edge_len is not None and t_param is not None:
            seg = edge_len  # length*t + length*(1-t) == length
        else:
            seg = _haversine_m(*u_coord, *approach) + _haversine_m(*approach, *v_coord)
        road_d += seg
        road_t += seg / speed_mps if speed_mps > 0 else 0.0

        # 2b) 幾何：沿邊曲線描點（u→approach、approach→v）；無 geometry 時退回直線
        curve = _edge_curve_points(edata, u_coord, v_coord) if edata is not None else None
        if curve is not None:
            # 將 approach 之前的曲線頂點加入（u→approach 段），再放入 approach 本身
            _add_curve_before_approach(add_point, curve, approach)
            add_point(approach)
            arrival_indices.append(len(polyline) - 1)
            if exit_v != enter_u:
                _add_curve_after_approach(add_point, curve, approach)
                add_point(v_coord)
        else:
            add_point(approach)
            arrival_indices.append(len(polyline) - 1)   # approach 點在 polyline 的索引
            if exit_v != enter_u:
                add_point(v_coord)
        # 3) 門口接駁段（馬路位置→原始門口）：不計入主路線，另計 approach 距離/時間
        approach_d += _haversine_m(*approach, orig[0], orig[1])
        prev_node = exit_v

    # 驗證每個停靠點的 approach（可抵達馬路位置）確實出現在 polyline 中
    included: list[bool] = []
    for stop in stops:
        approach = stop[1]
        hit = any(
            abs(p[0] - approach[0]) <= 1e-7 and abs(p[1] - approach[1]) <= 1e-7
            for p in polyline
        )
        included.append(hit)

    approach_t = approach_d / walk_speed_mps if walk_speed_mps > 0 else 0.0
    return {
        "polyline": polyline,
        "road_distance_m": road_d,
        "road_time_s": road_t,
        "approach_distance_m": approach_d,
        "approach_time_s": approach_t,
        "arrival_indices": arrival_indices,
        "included": included,
    }


# ---------------------------------------------------------------------------
# 主要比較函式
# ---------------------------------------------------------------------------
def _unreached_stops_message(visited_stops: list[dict]) -> str:
    """由 visited_stops 中 included_in_polyline 為 False 的項目，組出中文失敗訊息。

    純函式（無副作用），方便單元測試 included=False 失敗分支的訊息內容。
    """
    missing = "、".join(
        f"訂單 {vs['order_id']} 的{vs['kind_zh']}點"
        for vs in visited_stops if not vs["included_in_polyline"]
    )
    return "下列取餐/送餐點未被路線確實抵達：" + missing


def _validate_prep_times(
    prep_times_min: list[float] | None, num_orders: int
) -> list[float]:
    """檢核並回傳每筆訂單的製作時間（分鐘）。

    None → 全部視為 0（保持既有呼叫者行為不變）。長度須等於訂單數，
    每筆須落在 [0, 25] 分鐘。
    """
    if prep_times_min is None:
        return [0.0] * num_orders
    if len(prep_times_min) != num_orders:
        raise ValueError(
            f"製作時間數量（{len(prep_times_min)}）須等於訂單數（{num_orders}）"
        )
    cleaned: list[float] = []
    for p in prep_times_min:
        if not isinstance(p, (int, float)) or not (
            PREP_TIME_MIN_MINUTES <= p <= PREP_TIME_MAX_MINUTES
        ):
            raise ValueError(
                f"餐點製作時間須為 {PREP_TIME_MIN_MINUTES:.0f}～"
                f"{PREP_TIME_MAX_MINUTES:.0f} 分鐘之間的數字，收到：{p}"
            )
        cleaned.append(float(p))
    return cleaned


def compare_algorithms(
    graph: nx.MultiDiGraph,
    dist: DistanceMatrix,
    pickups: list[tuple[float, float]],
    dropoffs: list[tuple[float, float]],
    start: tuple[float, float] | None = None,
    speed_mps: float = 5.0,
    prep_times_min: list[float] | None = None,
) -> list[AlgoResult]:
    """接收一組取餐/送餐點（lat, lng），snap 到路網，
    分別以三種演算法規劃路線並回傳比較結果。

    參數
    ----
    pickups        : 取餐點 [(lat, lng), ...]
    dropoffs       : 送餐點 [(lat, lng), ...]，與 pickups 一一對應
    start          : 司機起點 (lat, lng)；若為 None 則以第一個取餐節點為起點
    speed_mps      : 行駛速度（公尺/秒），預設 5.0
    prep_times_min : 各訂單餐點製作時間（分鐘），與 pickups 一一對應；範圍 0～25。
                     None 表示全部 0（餐點立即可取，不需等待）。

    回傳
    ----
    [AlgoResult] 共 3 筆，順序：greedy, tsp_approx, dp
    """
    if len(pickups) != len(dropoffs) or len(pickups) == 0:
        raise ValueError("取餐點與送餐點數量必須相同且至少各一個")

    prep_times = _validate_prep_times(prep_times_min, len(pickups))

    # 確保 graph 邊有 travel_time（_road_path 需要）
    make_distance_matrix(graph, speed_mps=speed_mps)

    # Snap 到「最近的可行駛有向道路邊」；保留原始門口座標，並記錄可抵達的馬路位置與進/出節點
    orders: list[Order] = []
    # stop_meta[(order_id, kind)] = {"orig", "approach", "enter", "exit"}
    stop_meta: dict[tuple[int, str], dict] = {}
    for i, (pu_latlng, do_latlng) in enumerate(zip(pickups, dropoffs)):
        oid = i + 1
        sp = snap_to_edge(graph, pu_latlng[0], pu_latlng[1])
        sd = snap_to_edge(graph, do_latlng[0], do_latlng[1])
        stop_meta[(oid, "pickup")] = {
            "orig": (pu_latlng[0], pu_latlng[1]), "approach": sp["approach"],
            "enter": sp["enter_node"], "exit": sp["exit_node"],
            "edge_key": sp.get("edge_key"), "t": sp.get("t", 0.0),
        }
        stop_meta[(oid, "dropoff")] = {
            "orig": (do_latlng[0], do_latlng[1]), "approach": sd["approach"],
            "enter": sd["enter_node"], "exit": sd["exit_node"],
            "edge_key": sd.get("edge_key"), "t": sd.get("t", 0.0),
        }
        # 已知建模簡化：dispatcher 以 enter_node 的有向最短距離排序停靠點，
        # 但實際繪製的路線還包含「邊內 u→approach→v」接近段；因此演算法最佳化的
        # 成本只是所顯示 road_distance_m 的近似值（兩者排序通常一致，量值略有差距）。
        # 互動模式下所有訂單於 t=0 同時下單，餐點於 prep_time 後做好（food_ready_time）。
        prep_seconds = prep_times[i] * 60.0
        orders.append(Order(
            id=oid,
            restaurant_node=sp["enter_node"],   # 演算法以 snap 後道路節點排序/計距（核心不變）
            customer_node=sd["enter_node"],
            place_time=0.0, prep_time=prep_seconds,
        ))

    orders_by_id: dict[int, Order] = {o.id: o for o in orders}
    orders_info = [
        {
            "order_id": o.id,
            "prep_time_min": prep_times[o.id - 1],
            "ready_time_s": o.food_ready_time,
        }
        for o in orders
    ]

    # 司機起點：給定則 snap 給定座標；否則以第一張單取餐點為起點
    if start is not None:
        ss = snap_to_edge(graph, start[0], start[1])
        start_node = ss["enter_node"]
        start_latlng = (start[0], start[1])
    else:
        start_node = orders[0].restaurant_node
        start_latlng = stop_meta[(orders[0].id, "pickup")]["orig"]
    start_wp = (start_latlng, start_node)

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
            # 只量測規劃（排序）時間，不含後續路線幾何。
            t0 = time.perf_counter()
            route = plan_full_route(dispatcher, orders, start_node, dist)
            compute_ms = (time.perf_counter() - t0) * 1000.0

            metas = [stop_meta[(s.order_id, s.kind)] for s in route]
            stop_wps = [
                (m["orig"], m["approach"], m["enter"], m["exit"],
                 m["edge_key"], m["t"])
                for m in metas
            ]
            geo = build_visited_route(graph, start_wp, stop_wps, speed_mps=speed_mps)

            # 沿規劃路線推進時鐘（與 dispatcher 採用的同一 dist 矩陣），
            # 計算各取餐點的等待秒數與騎手總時間（行駛＋等待）。
            sim_state = DriverState(
                location_node=start_node, current_time=0.0, in_hand=[]
            )
            timeline = route_timeline(route, sim_state, orders_by_id, dist)
            total_wait_s = 0.0
            exceeds_tol = False
            for entry in timeline:
                if entry.stop.kind == "pickup":
                    w = entry.departure_time - entry.arrival_time
                    total_wait_s += w
                    if w > WAIT_TOLERANCE_S:
                        exceeds_tol = True
            total_driver_time_s = (
                timeline[-1].departure_time - sim_state.current_time
                if timeline else 0.0
            )

            included = geo["included"]
            arrival_idx = geo["arrival_indices"]
            visited_stops: list[dict] = []
            for s, m, inc, aidx, entry in zip(
                route, metas, included, arrival_idx, timeline
            ):
                wait_s = (entry.departure_time - entry.arrival_time
                          if s.kind == "pickup" else 0.0)
                visited_stops.append({
                    "order_id": s.order_id,
                    "stop_type": s.kind,
                    "kind_zh": "取餐" if s.kind == "pickup" else "送餐",
                    "original_latlng": [m["orig"][0], m["orig"][1]],
                    "approach_latlng": [m["approach"][0], m["approach"][1]],
                    "snapped_node": m["enter"],
                    "arrival_index_in_polyline": aidx,
                    "included_in_polyline": bool(inc),
                    "approach_distance_m": _haversine_m(
                        m["approach"][0], m["approach"][1], m["orig"][0], m["orig"][1]
                    ),
                    "arrival_time_s": entry.arrival_time,
                    "departure_time_s": entry.departure_time,
                    "wait_s": wait_s,
                })

            road_d = geo["road_distance_m"]
            appr_d = geo["approach_distance_m"]
            total_time = geo["road_time_s"] + geo["approach_time_s"]

            if not all(included):
                results.append(AlgoResult(
                    name=algo_name, display_name=display_name, success=False,
                    total_distance_m=road_d + appr_d, road_distance_m=road_d,
                    approach_distance_m=appr_d, total_time_s=total_time,
                    compute_ms=compute_ms, polyline=geo["polyline"], num_stops=len(route),
                    total_wait_s=total_wait_s, total_driver_time_s=total_driver_time_s,
                    exceeds_wait_tolerance=exceeds_tol, orders_info=orders_info,
                    visited_stops=visited_stops, all_stops_visited=False,
                    error=_unreached_stops_message(visited_stops),
                ))
                continue

            results.append(AlgoResult(
                name=algo_name, display_name=display_name, success=True,
                total_distance_m=road_d + appr_d, road_distance_m=road_d,
                approach_distance_m=appr_d, total_time_s=total_time,
                compute_ms=compute_ms, polyline=geo["polyline"], num_stops=len(route),
                total_wait_s=total_wait_s, total_driver_time_s=total_driver_time_s,
                exceeds_wait_tolerance=exceeds_tol, orders_info=orders_info,
                visited_stops=visited_stops, all_stops_visited=True,
            ))
        except nx.NetworkXNoPath:
            results.append(AlgoResult(
                name=algo_name, display_name=display_name, success=False,
                total_distance_m=0.0, total_time_s=0.0, compute_ms=compute_ms,
                polyline=[], num_stops=len(route), orders_info=orders_info,
                visited_stops=[], all_stops_visited=False,
                error="部分停靠點之間沒有可行的道路路徑（受道路方向限制），無法產生完整路線。",
            ))
        except Exception as exc:
            results.append(AlgoResult(
                name=algo_name, display_name=display_name, success=False,
                total_distance_m=0.0, total_time_s=0.0, compute_ms=compute_ms,
                polyline=[], num_stops=len(route), orders_info=orders_info,
                visited_stops=[], all_stops_visited=False,
                error=f"路線規劃發生錯誤：{exc}",
            ))

    return results


# ---------------------------------------------------------------------------
# 中文分析文字生成
# ---------------------------------------------------------------------------
def _wait_sentences(successful: list[AlgoResult]) -> list[str]:
    """產生「騎手等待成本」相關的中文分析句（多訂單情境用）。

    - 全程幾乎無等待：肯定其符合「只在前往取餐／送餐途中」的目標。
    - 否則指名等待最少的演算法及其等待秒數。
    - 若有任一演算法在餐廳等待超過容忍門檻（3 分鐘），提出警示。
    """
    tol_min = WAIT_TOLERANCE_S / 60.0
    out: list[str] = []
    least_wait = min(successful, key=lambda r: r.total_wait_s)
    most_wait = max(successful, key=lambda r: r.total_wait_s)

    if most_wait.total_wait_s < 1.0:
        out.append(
            "此規劃下騎手全程幾乎無需在餐廳空等，符合「狀態盡量只有前往取餐或前往送餐途中」的目標。"
        )
    else:
        out.append(
            f"就騎手等待成本而言，{least_wait.display_name} 在餐廳的等待最少"
            f"（約 {least_wait.total_wait_s:.0f} 秒）；演算法會盡量調整停靠順序，"
            f"先去做其他順路的事，避免在餐廳乾等。"
        )

    exceeded = [r for r in successful if r.exceeds_wait_tolerance]
    if exceeded:
        names = "、".join(r.display_name for r in exceeded)
        out.append(
            f"注意：{names} 仍有取餐點需等待超過容忍門檻（{tol_min:.0f} 分鐘），"
            f"通常代表該筆餐點製作時間過長或附近無其他順路任務可做，"
            f"建議調整該訂單的製作時間或增加可調度的訂單。"
        )
    return out


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
        sentences.extend(_wait_sentences(successful))
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

    # 取餐/送餐順序說明：演算法依實際路線成本決定，未必等於點選編號
    sentences.append(
        "取餐與送餐順序由演算法依實際路線成本動態決定（已取餐者才可送餐），"
        "因此實際停靠順序未必等於點選編號（例如較近的訂單可能先取，途中順路也可能先送）。"
    )

    # 騎手等待成本說明
    sentences.extend(_wait_sentences(successful))

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

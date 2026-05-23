"""OSMnx 圖載入、距離矩陣建立、POI / 顧客節點抽取。"""
import random
from pathlib import Path

import networkx as nx

from delivery.models import DistanceMatrix


def load_graph(
    place: str = "Tatung University, Taipei, Taiwan",
    dist_meters: int = 1500,
    network_type: str = "drive",
    cache_dir: Path | str = "data/cache",
) -> nx.MultiDiGraph:
    """從 OSMnx 拉路網，只保留最大 strongly-connected component（避免 random 顧客取到孤立節點）。"""
    import osmnx as ox  # 延遲 import，避免單元測試啟動時碰網路套件

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{place.replace(' ', '_').replace(',', '')}_{dist_meters}_{network_type}.graphml"
    if cache_file.exists():
        g = ox.load_graphml(cache_file)
    else:
        point = ox.geocode(place)
        g = ox.graph_from_point(point, dist=dist_meters, network_type=network_type)
        ox.save_graphml(g, cache_file)
    return _largest_strongly_connected(g)


def _largest_strongly_connected(g: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """取最大 strongly-connected component；保留 node attributes（含 amenity、x/y 座標）。"""
    if nx.is_strongly_connected(g):
        return g
    largest = max(nx.strongly_connected_components(g), key=len)
    return g.subgraph(largest).copy()


def make_distance_matrix(
    graph: nx.MultiDiGraph,
    speed_mps: float = 5.0,
) -> DistanceMatrix:
    """從 graph 建一個 lazy DistanceMatrix。
    邊權使用 length / speed_mps（秒）。第一次查 (u, v) 時跑一次 Dijkstra。"""
    # 為每條邊算 travel_time
    for u, v, data in graph.edges(data=True):
        if "length" in data:
            data["travel_time"] = data["length"] / speed_mps
        elif "travel_time" not in data:
            data["travel_time"] = 1.0

    def lookup(u: int, v: int) -> float:
        try:
            return nx.shortest_path_length(graph, u, v, weight="travel_time")
        except nx.NetworkXNoPath:
            return float("inf")

    return DistanceMatrix(lookup)


def extract_restaurant_nodes(graph: nx.MultiDiGraph) -> list[int]:
    """從 graph 節點屬性 amenity 抽出餐廳類節點。"""
    targets = {"restaurant", "fast_food", "cafe", "food_court"}
    return [
        n for n, data in graph.nodes(data=True)
        if data.get("amenity") in targets
    ]


def random_customer_nodes(
    graph: nx.MultiDiGraph,
    count: int,
    seed: int,
) -> list[int]:
    """從 graph 隨機抽 count 個節點當顧客位置（可重複播種）。"""
    rng = random.Random(seed)
    return rng.sample(list(graph.nodes), count)

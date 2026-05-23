"""訂單流產生器：Poisson 抵達 + 從 restaurant POI 抽餐廳 + 隨機顧客 + 隨機備餐時間。"""
import random

import networkx as nx

from delivery.map_loader import extract_restaurant_nodes
from delivery.models import Order


def generate_orders(
    graph: nx.MultiDiGraph,
    lambda_per_min: float,
    duration_seconds: float,
    seed: int,
    prep_time_min: float = 180.0,
    prep_time_max: float = 600.0,
) -> list[Order]:
    """產生一條訂單流。

    - 抵達過程：Poisson(λ per minute)，逐筆抽 exponential 間隔
    - 餐廳：從 graph 中 amenity ∈ {restaurant, fast_food, cafe} 的節點隨機抽
    - 顧客：從 graph 全部節點隨機抽
    - 備餐時間：[prep_time_min, prep_time_max] 均勻分布
    """
    rng = random.Random(seed)
    restaurants = extract_restaurant_nodes(graph)
    if not restaurants:
        # Fallback：把所有節點當潛在餐廳（在 toy graph / 沒 POI 的圖上）
        restaurants = list(graph.nodes)
    all_nodes = list(graph.nodes)

    orders: list[Order] = []
    t = 0.0
    next_id = 1
    lambda_per_sec = lambda_per_min / 60.0
    while True:
        # 下一筆訂單的到達時間 = 當前 + 指數分布間隔
        gap = rng.expovariate(lambda_per_sec)
        t += gap
        if t > duration_seconds:
            break
        restaurant = rng.choice(restaurants)
        customer = rng.choice(all_nodes)
        prep = rng.uniform(prep_time_min, prep_time_max)
        orders.append(Order(
            id=next_id,
            restaurant_node=restaurant,
            customer_node=customer,
            place_time=t,
            prep_time=prep,
        ))
        next_id += 1
    return orders

# -*- coding: utf-8 -*-
"""tests/test_interactive.py — 離線 toy-graph 測試 interactive 模組。"""
import json

import networkx as nx
import pytest

from delivery.interactive import (
    AlgoResult,
    _road_path,
    build_visited_route,
    chinese_analysis,
    compare_algorithms,
    nearest_node,
    plan_full_route,
    route_geometry,
    snap_to_edge,
)
from delivery.map_loader import make_distance_matrix
from delivery.models import Order, Stop


# ---------------------------------------------------------------------------
# Fixture：5x5 grid MultiDiGraph（與 test_integration.py 相同結構）
# ---------------------------------------------------------------------------
@pytest.fixture
def toy_graph() -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    base_lat, base_lon = 25.0625, 121.5290
    for i in range(5):
        for j in range(5):
            n = i * 5 + j
            g.add_node(n, y=base_lat + i * 0.0005, x=base_lon + j * 0.0005)
    for i in range(5):
        for j in range(5):
            n = i * 5 + j
            if j < 4:
                g.add_edge(n, n + 1, length=50.0)
                g.add_edge(n + 1, n, length=50.0)
            if i < 4:
                g.add_edge(n, n + 5, length=50.0)
                g.add_edge(n + 5, n, length=50.0)
    return g


@pytest.fixture
def toy_dist(toy_graph):
    return make_distance_matrix(toy_graph, speed_mps=5.0)


# ---------------------------------------------------------------------------
# 1. nearest_node
# ---------------------------------------------------------------------------
class TestNearestNode:
    def test_exact_match(self, toy_graph):
        """給定某節點的精確座標，應回傳該節點本身。"""
        for node_id in [0, 12, 24]:
            data = toy_graph.nodes[node_id]
            result = nearest_node(toy_graph, data["y"], data["x"])
            assert result == node_id, f"節點 {node_id} 應回傳自身"

    def test_offset_snaps_to_nearest(self, toy_graph):
        """偏移一點點應 snap 到最近節點。"""
        # 節點 0 的座標 + 極小偏移（比格點間距 0.0005 度小得多）
        n0_lat = toy_graph.nodes[0]["y"]
        n0_lng = toy_graph.nodes[0]["x"]
        result = nearest_node(toy_graph, n0_lat + 0.00001, n0_lng + 0.00001)
        assert result == 0

    def test_midpoint_snaps_to_one_of_two(self, toy_graph):
        """節點 0 與節點 1 的中點，應 snap 到 0 或 1（不是其他節點）。"""
        lat0, lng0 = toy_graph.nodes[0]["y"], toy_graph.nodes[0]["x"]
        lat1, lng1 = toy_graph.nodes[1]["y"], toy_graph.nodes[1]["x"]
        mid_lat = (lat0 + lat1) / 2
        mid_lng = (lng0 + lng1) / 2
        result = nearest_node(toy_graph, mid_lat, mid_lng)
        assert result in (0, 1)


# ---------------------------------------------------------------------------
# 2. plan_full_route
# ---------------------------------------------------------------------------
class TestPlanFullRoute:
    @pytest.mark.parametrize("algo_name,dispatcher_cls,kwargs", [
        ("greedy", "GreedyDispatcher", {}),
        ("tsp_approx", "TspApproxDispatcher", {}),
        ("dp", "DpDispatcher", {"alpha": 1.0, "beta": 1.0}),
    ])
    def test_route_length(self, toy_graph, toy_dist, algo_name, dispatcher_cls, kwargs):
        """plan_full_route 的停靠點數量應為 2 * num_orders。"""
        from delivery.algorithms.dp import DpDispatcher
        from delivery.algorithms.greedy import GreedyDispatcher
        from delivery.algorithms.tsp_approx import TspApproxDispatcher

        cls_map = {
            "GreedyDispatcher": GreedyDispatcher,
            "TspApproxDispatcher": TspApproxDispatcher,
            "DpDispatcher": DpDispatcher,
        }
        dispatcher = cls_map[dispatcher_cls](**kwargs)

        orders = [
            Order(1, 0, 8, place_time=0.0, prep_time=0.0),
            Order(2, 12, 18, place_time=0.0, prep_time=0.0),
            Order(3, 24, 4, place_time=0.0, prep_time=0.0),
        ]
        route = plan_full_route(dispatcher, orders, start_node=0, dist=toy_dist)
        assert len(route) == 2 * len(orders), (
            f"{algo_name}: 停靠點數量應為 {2 * len(orders)}，實際為 {len(route)}"
        )

    def test_pickup_before_dropoff(self, toy_graph, toy_dist):
        """每筆訂單的 pickup 應在 dropoff 之前出現。"""
        from delivery.algorithms.greedy import GreedyDispatcher

        orders = [
            Order(1, 0, 24, place_time=0.0, prep_time=0.0),
            Order(2, 6, 18, place_time=0.0, prep_time=0.0),
        ]
        dispatcher = GreedyDispatcher()
        route = plan_full_route(dispatcher, orders, start_node=0, dist=toy_dist)

        for order in orders:
            pickup_idx = next(
                i for i, s in enumerate(route)
                if s.order_id == order.id and s.kind == "pickup"
            )
            dropoff_idx = next(
                i for i, s in enumerate(route)
                if s.order_id == order.id and s.kind == "dropoff"
            )
            assert pickup_idx < dropoff_idx, (
                f"訂單 {order.id} 的 pickup ({pickup_idx}) 應在 dropoff ({dropoff_idx}) 之前"
            )


# ---------------------------------------------------------------------------
# 3. route_geometry
# ---------------------------------------------------------------------------
class TestRouteGeometry:
    def test_polyline_follows_road_nodes(self, toy_graph, toy_dist):
        """跨越多個格點的路線，折線點數應多於停靠點數（代表走實際路網）。"""
        # 節點 0 -> 停靠 node 20（需穿越 4 個節點）
        route = [
            Stop(order_id=1, kind="pickup", node=20),
            Stop(order_id=1, kind="dropoff", node=4),
        ]
        polyline, dist_m, time_s = route_geometry(
            toy_graph, start_node=0, route=route, speed_mps=5.0
        )
        # 至少有 start + stop1 + stop2 以上的點
        assert len(polyline) > len(route), (
            f"折線點數 {len(polyline)} 應多於停靠點數 {len(route)}"
        )
        assert dist_m > 0, "總距離應大於 0"
        assert time_s > 0, "總時間應大於 0"

    def test_distance_proportional_to_stops(self, toy_graph, toy_dist):
        """從節點 0 走到節點 2（2 步 x 50m）總距離應為 100m。"""
        route = [Stop(order_id=1, kind="pickup", node=1),
                 Stop(order_id=1, kind="dropoff", node=2)]
        polyline, dist_m, time_s = route_geometry(
            toy_graph, start_node=0, route=route, speed_mps=5.0
        )
        # 0->1->2：2 段，每段 50m，共 100m
        assert abs(dist_m - 100.0) < 1e-6, f"預期 100m，實際 {dist_m}"
        assert abs(time_s - 20.0) < 1e-6, f"預期 20s，實際 {time_s}"  # 100/5

    def test_no_duplicate_boundary_points(self, toy_graph, toy_dist):
        """相鄰 segment 的共用節點不應重複出現在折線中。"""
        route = [
            Stop(order_id=1, kind="pickup", node=5),
            Stop(order_id=1, kind="dropoff", node=10),
        ]
        polyline, _, _ = route_geometry(toy_graph, start_node=0, route=route, speed_mps=5.0)
        # 相鄰點不應相同
        for i in range(len(polyline) - 1):
            assert polyline[i] != polyline[i + 1], f"折線第 {i} 和 {i+1} 點重複：{polyline[i]}"


# ---------------------------------------------------------------------------
# 4. compare_algorithms
# ---------------------------------------------------------------------------
class TestCompareAlgorithms:
    def test_three_results_returned(self, toy_graph, toy_dist):
        """compare_algorithms 應回傳剛好 3 個結果，順序 greedy, tsp_approx, dp。"""
        pickups = [
            (toy_graph.nodes[0]["y"], toy_graph.nodes[0]["x"]),
            (toy_graph.nodes[12]["y"], toy_graph.nodes[12]["x"]),
            (toy_graph.nodes[24]["y"], toy_graph.nodes[24]["x"]),
        ]
        dropoffs = [
            (toy_graph.nodes[8]["y"], toy_graph.nodes[8]["x"]),
            (toy_graph.nodes[18]["y"], toy_graph.nodes[18]["x"]),
            (toy_graph.nodes[4]["y"], toy_graph.nodes[4]["x"]),
        ]
        results = compare_algorithms(
            toy_graph, toy_dist, pickups, dropoffs, speed_mps=5.0
        )
        assert len(results) == 3
        assert [r.name for r in results] == ["greedy", "tsp_approx", "dp"]

    def test_all_success(self, toy_graph, toy_dist):
        """三種演算法在有效 toy graph 上應全部成功。"""
        pickups = [
            (toy_graph.nodes[0]["y"], toy_graph.nodes[0]["x"]),
            (toy_graph.nodes[12]["y"], toy_graph.nodes[12]["x"]),
            (toy_graph.nodes[24]["y"], toy_graph.nodes[24]["x"]),
        ]
        dropoffs = [
            (toy_graph.nodes[8]["y"], toy_graph.nodes[8]["x"]),
            (toy_graph.nodes[18]["y"], toy_graph.nodes[18]["x"]),
            (toy_graph.nodes[4]["y"], toy_graph.nodes[4]["x"]),
        ]
        results = compare_algorithms(
            toy_graph, toy_dist, pickups, dropoffs, speed_mps=5.0
        )
        for r in results:
            assert r.success is True, f"{r.name} 應成功，但 error={r.error}"
            assert r.total_distance_m > 0, f"{r.name} 總距離應 > 0"
            assert r.compute_ms >= 0, f"{r.name} 計算時間應 >= 0"
            assert len(r.polyline) > 0, f"{r.name} 折線應非空"

    def test_validation_empty_raises(self, toy_graph, toy_dist):
        """空的 pickups/dropoffs 應 raise ValueError。"""
        with pytest.raises(ValueError, match="取餐點與送餐點數量必須相同且至少各一個"):
            compare_algorithms(toy_graph, toy_dist, [], [])

    def test_validation_mismatch_raises(self, toy_graph, toy_dist):
        """pickups/dropoffs 數量不符應 raise ValueError。"""
        pickups = [(25.0625, 121.5290)]
        dropoffs = [(25.0625, 121.5290), (25.063, 121.53)]
        with pytest.raises(ValueError, match="取餐點與送餐點數量必須相同且至少各一個"):
            compare_algorithms(toy_graph, toy_dist, pickups, dropoffs)

    def test_start_node_override(self, toy_graph, toy_dist):
        """指定 start 座標應改變起點（結果仍應 success）。"""
        pickups = [(toy_graph.nodes[0]["y"], toy_graph.nodes[0]["x"])]
        dropoffs = [(toy_graph.nodes[24]["y"], toy_graph.nodes[24]["x"])]
        start = (toy_graph.nodes[12]["y"], toy_graph.nodes[12]["x"])
        results = compare_algorithms(
            toy_graph, toy_dist, pickups, dropoffs, start=start, speed_mps=5.0
        )
        assert all(r.success for r in results)

    def test_num_stops_correct(self, toy_graph, toy_dist):
        """num_stops 應等於 2 * num_orders。"""
        num_orders = 3
        pickups = [
            (toy_graph.nodes[0]["y"], toy_graph.nodes[0]["x"]),
            (toy_graph.nodes[12]["y"], toy_graph.nodes[12]["x"]),
            (toy_graph.nodes[24]["y"], toy_graph.nodes[24]["x"]),
        ]
        dropoffs = [
            (toy_graph.nodes[8]["y"], toy_graph.nodes[8]["x"]),
            (toy_graph.nodes[18]["y"], toy_graph.nodes[18]["x"]),
            (toy_graph.nodes[4]["y"], toy_graph.nodes[4]["x"]),
        ]
        results = compare_algorithms(
            toy_graph, toy_dist, pickups, dropoffs, speed_mps=5.0
        )
        for r in results:
            assert r.num_stops == 2 * num_orders, (
                f"{r.name}: num_stops={r.num_stops}，預期 {2 * num_orders}"
            )


# ---------------------------------------------------------------------------
# 5. chinese_analysis
# ---------------------------------------------------------------------------
class TestChineseAnalysis:
    def _make_result(self, name, success=True, compute_ms=10.0, dist=500.0):
        return AlgoResult(
            name=name,
            display_name=f"Display-{name}",
            success=success,
            total_distance_m=dist,
            total_time_s=100.0,
            compute_ms=compute_ms,
            polyline=[(25.0, 121.0)],
            num_stops=2,
        )

    def test_returns_string(self):
        """chinese_analysis 應回傳非空字串。"""
        results = [
            self._make_result("greedy", compute_ms=5.0, dist=600.0),
            self._make_result("tsp_approx", compute_ms=10.0, dist=500.0),
            self._make_result("dp", compute_ms=50.0, dist=450.0),
        ]
        text = chinese_analysis(results)
        assert isinstance(text, str)
        assert len(text) > 0

    def test_contains_cjk(self):
        """輸出文字應包含至少一個 CJK 字元。"""
        results = [
            self._make_result("greedy", compute_ms=5.0, dist=600.0),
            self._make_result("tsp_approx", compute_ms=10.0, dist=500.0),
            self._make_result("dp", compute_ms=50.0, dist=450.0),
        ]
        text = chinese_analysis(results)
        assert any("一" <= ch <= "鿿" for ch in text), (
            f"輸出應含 CJK 字元，實際：{text!r}"
        )

    def test_handles_partial_failure(self):
        """部分演算法失敗時，輸出仍應包含 CJK 字元且提及失敗。"""
        results = [
            self._make_result("greedy", success=True, compute_ms=5.0, dist=600.0),
            AlgoResult(
                name="tsp_approx",
                display_name="TSP 近似（TSP Approximation）",
                success=False,
                total_distance_m=0.0,
                total_time_s=0.0,
                compute_ms=0.0,
                polyline=[],
                num_stops=0,
                error="測試錯誤",
            ),
            self._make_result("dp", success=True, compute_ms=50.0, dist=450.0),
        ]
        text = chinese_analysis(results)
        assert any("一" <= ch <= "鿿" for ch in text)

    def test_all_failed(self):
        """所有演算法失敗時也應回傳非空字串且含 CJK 字元。"""
        results = [
            AlgoResult(
                name=n,
                display_name=f"D-{n}",
                success=False,
                total_distance_m=0.0,
                total_time_s=0.0,
                compute_ms=0.0,
                polyline=[],
                num_stops=0,
                error="error",
            )
            for n in ("greedy", "tsp_approx", "dp")
        ]
        text = chinese_analysis(results)
        assert len(text) > 0
        assert any("一" <= ch <= "鿿" for ch in text)

    def test_single_order_explains_identical_routes(self):
        """單一訂單（num_stops<=2）：三演算法必然產生相同路線，分析文字應說明原因、
        提示使用者新增多組取/送餐點，且不得誤導性宣稱某演算法路徑較短。"""
        results = [
            self._make_result("greedy", compute_ms=0.02, dist=475.9),
            self._make_result("tsp_approx", compute_ms=0.03, dist=475.9),
            self._make_result("dp", compute_ms=0.04, dist=475.9),
        ]
        text = chinese_analysis(results)
        assert "新增" in text, f"應提示新增多組取/送餐點，實際：{text!r}"
        assert "相同" in text, f"應說明三者路徑相同，實際：{text!r}"
        assert "較佳" not in text and "最短路徑" not in text, (
            f"單一訂單不應宣稱某演算法路徑較佳/最短：{text!r}"
        )

    def test_multi_order_identifies_shortest(self):
        """多訂單且距離不同時，分析文字應提及產生最短路徑的演算法。"""
        results = [
            self._make_result("greedy", compute_ms=1.0, dist=1398.0),
            self._make_result("tsp_approx", compute_ms=0.4, dist=1272.0),
            self._make_result("dp", compute_ms=0.6, dist=1217.0),
        ]
        for r in results:
            r.num_stops = 6  # 多訂單（3 張單）
        text = chinese_analysis(results)
        assert any("一" <= ch <= "鿿" for ch in text)
        # dp 距離最短，應被指名
        assert results[2].display_name in text, (
            f"應指名最短路徑演算法 {results[2].display_name}，實際：{text!r}"
        )
        assert "新增" not in text, "多訂單不應出現單一訂單的提示語"


# ---------------------------------------------------------------------------
# 6. to_dict / JSON 序列化
# ---------------------------------------------------------------------------
class TestToDict:
    def test_json_serializable(self, toy_graph, toy_dist):
        """AlgoResult.to_dict() 應可被 json.dumps 序列化。"""
        pickups = [(toy_graph.nodes[0]["y"], toy_graph.nodes[0]["x"])]
        dropoffs = [(toy_graph.nodes[24]["y"], toy_graph.nodes[24]["x"])]
        results = compare_algorithms(
            toy_graph, toy_dist, pickups, dropoffs, speed_mps=5.0
        )
        for r in results:
            d = r.to_dict()
            serialized = json.dumps(d)
            assert isinstance(serialized, str)
            # 還原後應包含正確欄位
            parsed = json.loads(serialized)
            assert parsed["name"] == r.name
            assert isinstance(parsed["polyline"], list)
            for pt in parsed["polyline"]:
                assert len(pt) == 2  # [lat, lng]

    def test_to_dict_keys(self):
        """to_dict 應包含所有規格欄位。"""
        r = AlgoResult(
            name="greedy",
            display_name="Greedy（貪婪）",
            success=True,
            total_distance_m=300.0,
            total_time_s=60.0,
            compute_ms=1.5,
            polyline=[(25.0, 121.0), (25.001, 121.001)],
            num_stops=2,
        )
        d = r.to_dict()
        expected_keys = {
            "name", "display_name", "success", "total_distance_m",
            "road_distance_m", "approach_distance_m",
            "total_time_s", "compute_ms", "polyline", "num_stops",
            "visited_stops", "all_stops_visited", "error"
        }
        assert expected_keys == set(d.keys())

    def test_polyline_format_in_dict(self):
        """to_dict 中的 polyline 應為 [[lat, lng], ...] 格式（非 tuple）。"""
        r = AlgoResult(
            name="dp",
            display_name="動態規劃（Dynamic Programming / DP）",
            success=True,
            total_distance_m=500.0,
            total_time_s=100.0,
            compute_ms=20.0,
            polyline=[(25.0, 121.0), (25.001, 121.001)],
            num_stops=2,
        )
        d = r.to_dict()
        for pt in d["polyline"]:
            assert isinstance(pt, list), f"每個折線點應為 list，實際為 {type(pt)}"
            assert len(pt) == 2


# ---------------------------------------------------------------------------
# 7. 道路邊 snap / approach 接近點
# ---------------------------------------------------------------------------
class TestSnapToEdge:
    def _in_polyline(self, polyline, pt, tol=1e-7):
        return any(abs(p[0] - pt[0]) <= tol and abs(p[1] - pt[1]) <= tol
                   for p in polyline)

    def test_approach_near_point_not_far_node(self, toy_graph):
        """點選在某道路邊旁時，approach 應落在該邊上、貼近點選位置，
        而非遠處的十字路口節點。"""
        # 取節點 0→1 邊的中點旁、往外偏移一點點
        n0, n1 = toy_graph.nodes[0], toy_graph.nodes[1]
        mid_lat = (n0["y"] + n1["y"]) / 2
        mid_lng = (n0["x"] + n1["x"]) / 2 + 0.00006  # 垂直偏離道路一點
        snap = snap_to_edge(toy_graph, mid_lat, mid_lng)
        appr = snap["approach"]
        # approach 到點選位置的距離，應小於到任一端點（0 或 1）的距離
        d_appr = ((appr[0] - mid_lat) ** 2 + (appr[1] - mid_lng) ** 2) ** 0.5
        d_n0 = ((n0["y"] - mid_lat) ** 2 + (n0["x"] - mid_lng) ** 2) ** 0.5
        d_n1 = ((n1["y"] - mid_lat) ** 2 + (n1["x"] - mid_lng) ** 2) ** 0.5
        assert d_appr < d_n0 and d_appr < d_n1, "approach 應比端點更接近點選位置"
        assert {snap["enter_node"], snap["exit_node"]} <= set(toy_graph.nodes)
        assert snap["perp_m"] >= 0

    def test_snap_returns_directed_edge_endpoints(self, toy_graph):
        """enter_node→exit_node 必須是圖上實際存在的有向邊（保證沿合法方向行駛）。"""
        snap = snap_to_edge(toy_graph, toy_graph.nodes[6]["y"] + 0.0001,
                            toy_graph.nodes[6]["x"])
        u, v = snap["enter_node"], snap["exit_node"]
        assert toy_graph.has_edge(u, v), f"{u}->{v} 應為實際有向邊"


# ---------------------------------------------------------------------------
# 8. 有向圖：靠右、不逆向、迴轉需經路口
# ---------------------------------------------------------------------------
class TestDirected:
    def _one_way_cycle(self):
        """單行環道 0→1→2→3→0（無反向邊）。要反方向移動必須繞行整圈。"""
        g = nx.MultiDiGraph()
        coords = {0: (25.00, 121.00), 1: (25.00, 121.01),
                  2: (24.99, 121.01), 3: (24.99, 121.00)}
        for n, (la, lo) in coords.items():
            g.add_node(n, y=la, x=lo)
        for a, b in [(0, 1), (1, 2), (2, 3), (3, 0)]:
            g.add_edge(a, b, length=100.0)
        make_distance_matrix(g, speed_mps=5.0)
        return g

    def test_no_reverse_must_go_around(self):
        """1→0 沒有反向邊，最短路徑必須繞 1→2→3→0（300m），不可逆向走 1→0（100m）。"""
        g = self._one_way_cycle()
        coords, dist_m, _ = _road_path(g, 1, 0, speed_mps=5.0)
        assert dist_m == pytest.approx(300.0), f"應繞行 300m，實際 {dist_m}"
        assert len(coords) == 4, "路徑應經過 1→2→3→0 四個節點（經由路口繞行）"

    def test_polyline_only_uses_forward_edges(self):
        """build_visited_route 產生的路線，相鄰道路節點必須是合法有向邊（不逆向）。"""
        g = self._one_way_cycle()
        coord_to_node = {(d["y"], d["x"]): n for n, d in g.nodes(data=True)}
        # 起點節點 0，停靠在節點 2 附近（approach 取節點 2 座標）
        start = ((25.00, 121.00), 0)
        appr2 = (g.nodes[2]["y"], g.nodes[2]["x"])
        stops = [((24.99, 121.012), appr2, 1, 2)]  # enter=1, exit=2（合法邊 1→2）
        geo = build_visited_route(g, start, stops, speed_mps=5.0)
        # 檢查 polyline 中「位於節點上的相鄰點」皆為合法有向邊
        nodes_seq = [coord_to_node[p] for p in geo["polyline"] if p in coord_to_node]
        for a, b in zip(nodes_seq, nodes_seq[1:]):
            if a != b:
                assert g.has_edge(a, b), f"{a}->{b} 非合法有向邊（疑似逆向）"


# ---------------------------------------------------------------------------
# 9. 單一連續路線 + approach 抵達 + 停靠順序
# ---------------------------------------------------------------------------
class TestApproachRouting:
    def _in_polyline(self, polyline, pt, tol=1e-7):
        return any(abs(p[0] - pt[0]) <= tol and abs(p[1] - pt[1]) <= tol
                   for p in polyline)

    def _offset(self, toy_graph, node_ids, dlat, dlng):
        return [(toy_graph.nodes[n]["y"] + dlat, toy_graph.nodes[n]["x"] + dlng)
                for n in node_ids]

    def test_build_visited_route_reaches_approach(self, toy_graph):
        """polyline 必須確實抵達每個停靠點的 approach（可抵達馬路位置），included 全 True。"""
        sp = snap_to_edge(toy_graph, toy_graph.nodes[0]["y"] + 0.00008,
                          toy_graph.nodes[0]["x"])
        sd = snap_to_edge(toy_graph, toy_graph.nodes[24]["y"] - 0.00008,
                          toy_graph.nodes[24]["x"])
        start = ((toy_graph.nodes[0]["y"], toy_graph.nodes[0]["x"]), sp["enter_node"])
        stops = [
            ((toy_graph.nodes[0]["y"] + 0.00008, toy_graph.nodes[0]["x"]),
             sp["approach"], sp["enter_node"], sp["exit_node"]),
            ((toy_graph.nodes[24]["y"] - 0.00008, toy_graph.nodes[24]["x"]),
             sd["approach"], sd["enter_node"], sd["exit_node"]),
        ]
        geo = build_visited_route(toy_graph, start, stops, speed_mps=5.0)
        assert geo["included"] == [True, True]
        assert self._in_polyline(geo["polyline"], sp["approach"])
        assert self._in_polyline(geo["polyline"], sd["approach"])
        assert geo["road_distance_m"] > 0
        assert geo["approach_distance_m"] >= 0
        # arrival_indices 指向 polyline 中的 approach 點
        for idx, st in zip(geo["arrival_indices"], stops):
            assert geo["polyline"][idx] == st[1]

    def test_single_continuous_ordered_polyline(self, toy_graph, toy_dist):
        """每個演算法輸出單一條 ordered polyline（[ [lat,lng], ... ]），非多條分支。"""
        pickups = self._offset(toy_graph, [0, 12, 24], 0.00008, 0.00008)
        dropoffs = self._offset(toy_graph, [8, 18, 4], -0.00008, -0.00008)
        results = compare_algorithms(toy_graph, toy_dist, pickups, dropoffs, speed_mps=5.0)
        for r in results:
            assert r.success, f"{r.name}: {r.error}"
            assert isinstance(r.polyline, list) and len(r.polyline) >= 2
            for pt in r.polyline:
                assert len(pt) == 2 and all(isinstance(c, (int, float)) for c in pt)

    def test_visited_stops_fields_and_approach_reached(self, toy_graph, toy_dist):
        """visited_stops 含規格欄位，且 included_in_polyline 代表抵達 approach（非僅到路口）。"""
        pickups = self._offset(toy_graph, [0, 24], 0.00008, 0.00008)
        dropoffs = self._offset(toy_graph, [4, 20], -0.00008, -0.00008)
        results = compare_algorithms(toy_graph, toy_dist, pickups, dropoffs, speed_mps=5.0)
        for r in results:
            assert r.all_stops_visited is True
            for vs in r.visited_stops:
                for key in ("order_id", "stop_type", "original_latlng",
                            "approach_latlng", "snapped_node",
                            "arrival_index_in_polyline", "included_in_polyline",
                            "approach_distance_m"):
                    assert key in vs, f"visited_stop 缺少欄位 {key}"
                assert vs["included_in_polyline"] is True
                # polyline 在 arrival_index 處的點即為 approach（代表確實抵達該馬路位置）
                idx = vs["arrival_index_in_polyline"]
                assert list(r.polyline[idx]) == vs["approach_latlng"]

    def test_total_equals_road_plus_approach(self, toy_graph, toy_dist):
        """總距離 = 主路線距離 + 停靠接近距離。"""
        pickups = self._offset(toy_graph, [0, 12], 0.0001, 0.0001)
        dropoffs = self._offset(toy_graph, [8, 18], -0.0001, -0.0001)
        results = compare_algorithms(toy_graph, toy_dist, pickups, dropoffs, speed_mps=5.0)
        for r in results:
            assert r.total_distance_m == pytest.approx(
                r.road_distance_m + r.approach_distance_m
            )
            assert r.approach_distance_m > 0  # 點選偏離道路，必有接近距離

    def test_precedence_pickup_before_dropoff(self, toy_graph, toy_dist):
        """每張單的取餐必在送餐之前；但取餐順序不必等於訂單編號（可動態決定）。"""
        pickups = self._offset(toy_graph, [0, 12, 24], 0.00008, 0.00008)
        dropoffs = self._offset(toy_graph, [6, 8, 16], -0.00008, -0.00008)
        results = compare_algorithms(toy_graph, toy_dist, pickups, dropoffs, speed_mps=5.0)
        for r in results:
            seq = [(vs["order_id"], vs["stop_type"]) for vs in r.visited_stops]
            for oid in (1, 2, 3):
                pi = seq.index((oid, "pickup"))
                di = seq.index((oid, "dropoff"))
                assert pi < di, f"{r.name}: 訂單 {oid} 送餐不可在取餐之前"

    def test_taipei_toy_smoke(self):
        """台北市座標範圍的有向格狀路網，三演算法皆成功且所有點皆抵達。"""
        g = nx.MultiDiGraph()
        base_lat, base_lng = 25.0478, 121.5170  # 台北車站一帶
        for i in range(5):
            for j in range(5):
                n = i * 5 + j
                g.add_node(n, y=base_lat + i * 0.0006, x=base_lng + j * 0.0006)
        for i in range(5):
            for j in range(5):
                n = i * 5 + j
                if j < 4:
                    g.add_edge(n, n + 1, length=60.0)
                    g.add_edge(n + 1, n, length=60.0)
                if i < 4:
                    g.add_edge(n, n + 5, length=60.0)
                    g.add_edge(n + 5, n, length=60.0)
        dist = make_distance_matrix(g, speed_mps=5.0)
        pickups = [(g.nodes[0]["y"] + 0.0001, g.nodes[0]["x"]),
                   (g.nodes[12]["y"] + 0.0001, g.nodes[12]["x"]),
                   (g.nodes[24]["y"] + 0.0001, g.nodes[24]["x"])]
        dropoffs = [(g.nodes[8]["y"] - 0.0001, g.nodes[8]["x"]),
                    (g.nodes[18]["y"] - 0.0001, g.nodes[18]["x"]),
                    (g.nodes[4]["y"] - 0.0001, g.nodes[4]["x"])]
        results = compare_algorithms(g, dist, pickups, dropoffs, speed_mps=5.0)
        assert len(results) == 3
        for r in results:
            assert r.success, f"{r.name}: {r.error}"
            assert r.all_stops_visited is True
            assert r.num_stops == 6


# ---------------------------------------------------------------------------
# 10. 無可行道路 → 失敗（中文錯誤）
# ---------------------------------------------------------------------------
class TestUnreachable:
    def _disconnected_graph(self):
        g = nx.MultiDiGraph()
        g.add_node(0, y=25.0000, x=121.0000)
        g.add_node(1, y=25.0100, x=121.0100)
        make_distance_matrix(g, speed_mps=5.0)
        return g

    def test_build_visited_route_raises_on_unreachable(self):
        """停靠點之間無道路路徑時，build_visited_route 應拋出 NetworkXNoPath。"""
        g = self._disconnected_graph()
        with pytest.raises(nx.NetworkXNoPath):
            build_visited_route(
                g, ((25.0, 121.0), 0),
                [((25.01, 121.01), (25.01, 121.01), 1, 1)], speed_mps=5.0
            )

    def test_unreachable_marks_failure_with_chinese_error(self):
        """無可行道路時，compare_algorithms 至少一個演算法標記失敗並附中文錯誤。"""
        g = self._disconnected_graph()
        dist = make_distance_matrix(g, speed_mps=5.0)
        results = compare_algorithms(
            g, dist, [(25.0, 121.0)], [(25.01, 121.01)], speed_mps=5.0
        )
        failed = [r for r in results if not r.success]
        assert failed, "無可行道路時應至少有演算法被標記為失敗"
        for r in failed:
            assert r.all_stops_visited is False
            assert r.error and any("一" <= ch <= "鿿" for ch in r.error)

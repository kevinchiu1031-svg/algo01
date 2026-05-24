# 外送動態路由與時間成本優化 — 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立一個事件驅動的外送路由模擬器，比較三種 CLRS 演算法（DP、TSP-Approx、Greedy）在同一條動態訂單流上的時間成本表現，輸出 Folium 互動地圖與對照指標。

**Architecture:** 分層設計，純函數層（models / metrics / algorithms）與狀態機層（simulator）嚴格分離。三個演算法共用 `Dispatcher` Protocol，可插拔。距離矩陣以 lazy Dijkstra 包裝 OSMnx 圖。

**Tech Stack:** Python 3.11+, OSMnx, NetworkX, Folium, pytest

**Spec：** `docs/superpowers/specs/2026-05-24-delivery-routing-design.md`

---

## File Structure

```
ALGO_Kevin/
├─ .gitignore
├─ README.md
├─ requirements.txt
├─ pyproject.toml
├─ data/cache/.gitkeep              （OSMnx graphml 快取目錄）
├─ docs/superpowers/                （spec & plan，已存在）
├─ src/delivery/
│   ├─ __init__.py
│   ├─ models.py                    Order, Stop, DriverState, Decision, Dispatcher Protocol, DistanceMatrix
│   ├─ metrics.py                   cost_of_route, route_timeline
│   ├─ algorithms/
│   │   ├─ __init__.py
│   │   ├─ greedy.py                GreedyDispatcher
│   │   ├─ tsp_approx.py            TspApproxDispatcher（MST 2-approx + precedence 修補）
│   │   └─ dp.py                    DpDispatcher（Held-Karp 含時間追蹤）
│   ├─ map_loader.py                load_graph, make_distance_matrix
│   ├─ order_stream.py              generate_orders（Poisson）
│   ├─ simulator.py                 Simulator, EventType, SimulationResult
│   └─ visualize.py                 render_route_html, render_comparison_html
├─ tests/
│   ├─ conftest.py                  共用 fixtures（toy distance matrix 等）
│   ├─ test_models.py
│   ├─ test_metrics.py
│   ├─ test_greedy.py
│   ├─ test_tsp_approx.py
│   ├─ test_dp.py
│   ├─ test_map_loader.py
│   ├─ test_order_stream.py
│   ├─ test_simulator.py
│   └─ test_integration.py
└─ scripts/
    └─ run_experiment.py
```

**File-level 責任邊界**：

- `models.py`：純資料類別，無業務邏輯
- `metrics.py`：純函數，給定 route + state + dist 算成本
- `algorithms/*.py`：純函數搜尋邏輯，不知道時間軸或事件
- `map_loader.py`：OSMnx I/O + Dijkstra 封裝
- `simulator.py`：唯一持有 clock 與可變 state 的模組
- `visualize.py`：只讀，輸出 HTML
- `scripts/run_experiment.py`：CLI 入口，串接全部

**依賴方向**：`models` ← `metrics` ← `algorithms` ← `simulator` ← `scripts`。`visualize` 也只依賴 `models` 與 `simulator` 輸出。

---

## Task 0: Scaffolding

**Files:**

- Create: `.gitignore`

- Create: `requirements.txt`

- Create: `pyproject.toml`

- Create: `README.md`

- Create: `data/cache/.gitkeep`

- Create: `src/delivery/__init__.py`

- Create: `src/delivery/algorithms/__init__.py`

- Create: `tests/__init__.py`

- Create: `tests/conftest.py`

- [ ] **Step 1: 建立 .gitignore**

Write `.gitignore`:

```gitignore
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.venv/
venv/
.idea/
.vscode/
*.egg-info/
data/cache/*.graphml
out/
*.html
```

- [ ] **Step 2: 建立 requirements.txt**

Write `requirements.txt`:

```
osmnx>=1.9
networkx>=3.2
folium>=0.16
numpy>=1.26
pandas>=2.1
pytest>=8.0
```

- [ ] **Step 3: 建立 pyproject.toml**

Write `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "delivery"
version = "0.1.0"
requires-python = ">=3.11"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = "-v"
pythonpath = ["src"]
```

- [ ] **Step 4: 建立 README.md 骨架**

Write `README.md`:

```markdown
# 外送動態路由與時間成本優化

CLRS 演算法應用：用三種演算法（DP / TSP-Approx / Greedy）解動態外送路由問題。

## 安裝

```bash
pip install -r requirements.txt
```

## 跑實驗

```bash
python scripts/run_experiment.py --seed 42
```

輸出在 `out/` 目錄下，包含三個 HTML 地圖與對照表。

## 設計文件

`docs/superpowers/specs/2026-05-24-delivery-routing-design.md`

```
- [ ] **Step 5: 建立空 package 檔**

Write `data/cache/.gitkeep` 內容為空字串。
Write `src/delivery/__init__.py` 內容為空字串。
Write `src/delivery/algorithms/__init__.py` 內容為空字串。
Write `tests/__init__.py` 內容為空字串。
Write `tests/conftest.py`：

```python
"""共用 test fixtures。"""
```

- [ ] **Step 6: Git init 並第一次 commit**

```bash
cd F:/workspace/ALGO_Kevin
git init
git add .
git commit -m "chore: scaffold project"
```

Expected: 新 repo，初始 commit 包含所有 scaffold 檔。

---

## Task 1: Models（核心資料類別）

**Files:**

- Create: `src/delivery/models.py`

- Create: `tests/test_models.py`

- Modify: `tests/conftest.py`

- [ ] **Step 1: 寫 failing test for `Order.food_ready_time`**

Write `tests/test_models.py`:

```python
from delivery.models import Order, Stop, DriverState, DistanceMatrix


def test_order_food_ready_time():
    order = Order(
        id=1,
        restaurant_node=10,
        customer_node=20,
        place_time=100.0,
        prep_time=300.0,
    )
    assert order.food_ready_time == 400.0


def test_distance_matrix_caches_lookups():
    calls: list[tuple[int, int]] = []

    def lookup(u: int, v: int) -> float:
        calls.append((u, v))
        return float(u + v)

    dist = DistanceMatrix(lookup)
    assert dist[(1, 2)] == 3.0
    assert dist[(1, 2)] == 3.0  # 第二次走 cache
    assert calls == [(1, 2)]


def test_distance_matrix_symmetric_cache():
    """(u,v) 與 (v,u) 共用 cache key（無向路網）。"""
    calls: list[tuple[int, int]] = []

    def lookup(u: int, v: int) -> float:
        calls.append((u, v))
        return 5.0

    dist = DistanceMatrix(lookup, symmetric=True)
    assert dist[(1, 2)] == 5.0
    assert dist[(2, 1)] == 5.0
    assert len(calls) == 1


def test_driver_state_in_hand_order_count():
    state = DriverState(
        location_node=0,
        current_time=0.0,
        in_hand=[
            Stop(order_id=1, kind="pickup", node=10),
            Stop(order_id=1, kind="dropoff", node=20),
            Stop(order_id=2, kind="pickup", node=30),
        ],
    )
    # 計算 in_hand 中 unique order ids
    order_ids = {s.order_id for s in state.in_hand}
    assert len(order_ids) == 2
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `pytest tests/test_models.py -v`
Expected: `ModuleNotFoundError: No module named 'delivery.models'`

- [ ] **Step 3: 實作 models.py**

Write `src/delivery/models.py`:

```python
"""Core data types。純資料類別，無業務邏輯。"""
from dataclasses import dataclass, field
from typing import Callable, Literal, Protocol


@dataclass(frozen=True)
class Order:
    id: int
    restaurant_node: int
    customer_node: int
    place_time: float
    prep_time: float

    @property
    def food_ready_time(self) -> float:
        return self.place_time + self.prep_time


@dataclass(frozen=True)
class Stop:
    order_id: int
    kind: Literal["pickup", "dropoff"]
    node: int


@dataclass
class DriverState:
    location_node: int
    current_time: float
    in_hand: list[Stop] = field(default_factory=list)


@dataclass
class Decision:
    accept: bool
    new_route: list[Stop] | None = None


class DistanceMatrix:
    """Lazy Dijkstra wrapper。第一次查詢觸發底層 lookup，之後走 cache。"""

    def __init__(
        self,
        lookup_fn: Callable[[int, int], float],
        symmetric: bool = False,
    ) -> None:
        self._lookup = lookup_fn
        self._symmetric = symmetric
        self._cache: dict[tuple[int, int], float] = {}

    def __getitem__(self, key: tuple[int, int]) -> float:
        u, v = key
        if u == v:
            return 0.0
        canonical = (min(u, v), max(u, v)) if self._symmetric else (u, v)
        if canonical not in self._cache:
            self._cache[canonical] = self._lookup(u, v)
        return self._cache[canonical]


class Dispatcher(Protocol):
    name: str

    def plan(
        self,
        state: DriverState,
        candidate: Order,
        all_orders: dict[int, Order],
        dist: DistanceMatrix,
    ) -> Decision: ...
```

說明 `all_orders` 為什麼存在：`state.in_hand` 只記 stops（包含 order_id 與 node），但演算法在算等待 / 顧客成本時需要拿到 `Order.food_ready_time` 與 `place_time`。傳一個 `dict[int, Order]` 比把整個 Order 塞進 Stop 更乾淨。

- [ ] **Step 4: 跑測試確認 pass**

Run: `pytest tests/test_models.py -v`
Expected: 4 passed。

- [ ] **Step 5: Commit**

```bash
git add src/delivery/models.py tests/test_models.py
git commit -m "feat(models): add Order, Stop, DriverState, DistanceMatrix, Dispatcher Protocol"
```

---

## Task 2: Metrics（成本函數）

**Files:**

- Create: `src/delivery/metrics.py`

- Create: `tests/test_metrics.py`

- [ ] **Step 1: 寫 failing test**

Write `tests/test_metrics.py`:

```python
from delivery.models import Order, Stop, DriverState, DistanceMatrix
from delivery.metrics import cost_of_route, route_timeline


def make_dist(table: dict[tuple[int, int], float]) -> DistanceMatrix:
    """Test helper：包一個 dict 進 DistanceMatrix。"""
    def lookup(u: int, v: int) -> float:
        return table[(u, v)]
    return DistanceMatrix(lookup)


def test_cost_of_route_simple_one_order_no_wait():
    """單一訂單，餐點早就好；driver 開 100 秒到餐廳，又 100 秒到顧客。"""
    order = Order(id=1, restaurant_node=10, customer_node=20,
                  place_time=0.0, prep_time=50.0)
    state = DriverState(location_node=0, current_time=200.0, in_hand=[])
    route = [
        Stop(order_id=1, kind="pickup", node=10),
        Stop(order_id=1, kind="dropoff", node=20),
    ]
    dist = make_dist({(0, 10): 100.0, (10, 20): 100.0})
    cost, driver_time, cust_wait = cost_of_route(
        route, state, {1: order}, dist, alpha=1.0, beta=1.0
    )
    # driver_time = 100 (drive to pickup) + 0 (no wait) + 100 (drive to dropoff) = 200
    # customer_wait = dropoff_time(400) - place_time(0) = 400
    assert driver_time == 200.0
    assert cust_wait == 400.0
    assert cost == 1.0 * 200.0 + 1.0 * 400.0


def test_cost_of_route_with_food_wait():
    """抵達餐廳時餐點還沒好，要等。"""
    order = Order(id=1, restaurant_node=10, customer_node=20,
                  place_time=0.0, prep_time=500.0)  # 餐 500 秒做好
    state = DriverState(location_node=0, current_time=0.0, in_hand=[])
    route = [
        Stop(order_id=1, kind="pickup", node=10),
        Stop(order_id=1, kind="dropoff", node=20),
    ]
    dist = make_dist({(0, 10): 100.0, (10, 20): 100.0})
    # 抵達餐廳 t=100，餐 t=500 才好，等 400 秒
    # 離開餐廳 t=500，抵達顧客 t=600
    cost, driver_time, cust_wait = cost_of_route(
        route, state, {1: order}, dist, alpha=1.0, beta=1.0
    )
    assert driver_time == 600.0  # 100 + 400 wait + 100
    assert cust_wait == 600.0    # dropoff t=600 − place_time 0


def test_route_timeline_returns_event_list():
    order = Order(id=1, restaurant_node=10, customer_node=20,
                  place_time=0.0, prep_time=50.0)
    state = DriverState(location_node=0, current_time=0.0, in_hand=[])
    route = [
        Stop(order_id=1, kind="pickup", node=10),
        Stop(order_id=1, kind="dropoff", node=20),
    ]
    dist = make_dist({(0, 10): 100.0, (10, 20): 100.0})
    timeline = route_timeline(route, state, {1: order}, dist)
    # 每個 stop 應對應一個 (arrival_time, departure_time, stop) 三元組
    assert len(timeline) == 2
    assert timeline[0].arrival_time == 100.0
    assert timeline[0].departure_time == 100.0  # 餐已好，無等待
    assert timeline[1].arrival_time == 200.0
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `pytest tests/test_metrics.py -v`
Expected: `ModuleNotFoundError`。

- [ ] **Step 3: 實作 metrics.py**

Write `src/delivery/metrics.py`:

```python
"""成本函數與路線時間軸。"""
from dataclasses import dataclass

from delivery.models import DistanceMatrix, DriverState, Order, Stop


@dataclass(frozen=True)
class TimelineEntry:
    stop: Stop
    arrival_time: float
    departure_time: float


def route_timeline(
    route: list[Stop],
    state: DriverState,
    orders: dict[int, Order],
    dist: DistanceMatrix,
) -> list[TimelineEntry]:
    """逐站推進，回傳每站抵達 / 離開時刻。

    pickup 站若餐未好需等待，等待計入 departure_time。
    dropoff 站立即離開（arrival == departure）。
    """
    timeline: list[TimelineEntry] = []
    current_node = state.location_node
    current_time = state.current_time
    for stop in route:
        travel = dist[(current_node, stop.node)]
        arrival = current_time + travel
        if stop.kind == "pickup":
            order = orders[stop.order_id]
            departure = max(arrival, order.food_ready_time)
        else:
            departure = arrival
        timeline.append(TimelineEntry(stop, arrival, departure))
        current_node = stop.node
        current_time = departure
    return timeline


def cost_of_route(
    route: list[Stop],
    state: DriverState,
    orders: dict[int, Order],
    dist: DistanceMatrix,
    alpha: float = 1.0,
    beta: float = 1.0,
) -> tuple[float, float, float]:
    """回傳 (總加權成本, driver_time, customer_wait_sum)。

    - driver_time = 從 state.current_time 到最後一站 departure 的時間
    - customer_wait = sum of (dropoff_time - order.place_time) for each dropoff
    """
    if not route:
        return 0.0, 0.0, 0.0
    timeline = route_timeline(route, state, orders, dist)
    driver_time = timeline[-1].departure_time - state.current_time
    customer_wait = 0.0
    for entry in timeline:
        if entry.stop.kind == "dropoff":
            order = orders[entry.stop.order_id]
            customer_wait += entry.arrival_time - order.place_time
    cost = alpha * driver_time + beta * customer_wait
    return cost, driver_time, customer_wait
```

- [ ] **Step 4: 跑測試確認 pass**

Run: `pytest tests/test_metrics.py -v`
Expected: 3 passed。

- [ ] **Step 5: Commit**

```bash
git add src/delivery/metrics.py tests/test_metrics.py
git commit -m "feat(metrics): add cost_of_route and route_timeline"
```

---

## Task 3: 共用 test fixtures

**Files:**

- Modify: `tests/conftest.py`

- [ ] **Step 1: 加入 toy distance matrix helper**

Write `tests/conftest.py`:

```python
"""共用 test fixtures。"""
import pytest

from delivery.models import DistanceMatrix


def make_dist(table: dict[tuple[int, int], float]) -> DistanceMatrix:
    """從 dict 建一個 DistanceMatrix。對稱補齊缺項。"""
    full: dict[tuple[int, int], float] = {}
    for (u, v), d in table.items():
        full[(u, v)] = d
        full[(v, u)] = d
    for u, v in list(full):
        full.setdefault((u, u), 0.0)
        full.setdefault((v, v), 0.0)

    def lookup(a: int, b: int) -> float:
        return full[(a, b)]
    return DistanceMatrix(lookup)


@pytest.fixture
def dist_factory():
    """用法：def test_xxx(dist_factory): dist = dist_factory({(0,1): 10, ...})"""
    return make_dist
```

- [ ] **Step 2: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add shared distance matrix fixture"
```

---

## Task 4: Greedy 演算法

**Files:**

- Create: `src/delivery/algorithms/greedy.py`

- Create: `tests/test_greedy.py`

- [ ] **Step 1: 寫 failing tests**

Write `tests/test_greedy.py`:

```python
from delivery.models import Order, Stop, DriverState
from delivery.algorithms.greedy import GreedyDispatcher


def test_greedy_single_new_order_no_in_hand(dist_factory):
    """空車情境：接一張新單，應排成 pickup → dropoff。"""
    order = Order(id=1, restaurant_node=10, customer_node=20,
                  place_time=0.0, prep_time=50.0)
    state = DriverState(location_node=0, current_time=100.0, in_hand=[])
    dist = dist_factory({(0, 10): 50, (10, 20): 30, (0, 20): 200})
    disp = GreedyDispatcher()
    decision = disp.plan(state, order, {1: order}, dist)
    assert decision.accept is True
    assert decision.new_route == [
        Stop(1, "pickup", 10),
        Stop(1, "dropoff", 20),
    ]


def test_greedy_respects_precedence(dist_factory):
    """已有一張單在 in_hand，新單加入；dropoff 一定排在對應 pickup 之後。"""
    o1 = Order(id=1, restaurant_node=10, customer_node=11,
               place_time=0.0, prep_time=0.0)
    o2 = Order(id=2, restaurant_node=20, customer_node=21,
               place_time=0.0, prep_time=0.0)
    state = DriverState(
        location_node=0,
        current_time=0.0,
        in_hand=[Stop(1, "pickup", 10), Stop(1, "dropoff", 11)],
    )
    # 故意把距離設成最近順序會違反 precedence 的樣子
    dist = dist_factory({
        (0, 10): 5, (0, 11): 100, (0, 20): 10, (0, 21): 3,
        (10, 11): 50, (10, 20): 20, (10, 21): 30,
        (11, 20): 15, (11, 21): 8, (20, 21): 25,
    })
    disp = GreedyDispatcher()
    decision = disp.plan(state, o2, {1: o1, 2: o2}, dist)
    assert decision.accept is True
    # 驗證 route 中每張單的 pickup 都在 dropoff 之前
    route = decision.new_route
    for order_id in (1, 2):
        positions = [i for i, s in enumerate(route) if s.order_id == order_id]
        kinds = [route[i].kind for i in positions]
        assert kinds == ["pickup", "dropoff"]


def test_greedy_returns_all_stops(dist_factory):
    """產生的 route 必須包含所有 in_hand stops + 新單的兩 stops。"""
    o1 = Order(id=1, restaurant_node=10, customer_node=11, place_time=0, prep_time=0)
    o2 = Order(id=2, restaurant_node=20, customer_node=21, place_time=0, prep_time=0)
    state = DriverState(
        location_node=0, current_time=0.0,
        in_hand=[Stop(1, "pickup", 10)],
    )
    dist = dist_factory({
        (0, 10): 5, (0, 11): 100, (0, 20): 10, (0, 21): 30,
        (10, 11): 50, (10, 20): 20, (10, 21): 30,
        (11, 20): 15, (11, 21): 8, (20, 21): 25,
    })
    disp = GreedyDispatcher()
    decision = disp.plan(state, o2, {1: o1, 2: o2}, dist)
    assert decision.accept is True
    assert len(decision.new_route) == 3  # 1 leftover + 2 new
    assert {(s.order_id, s.kind) for s in decision.new_route} == {
        (1, "pickup"), (2, "pickup"), (2, "dropoff"),
    }
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `pytest tests/test_greedy.py -v`
Expected: `ModuleNotFoundError`。

- [ ] **Step 3: 實作 greedy.py**

Write `src/delivery/algorithms/greedy.py`:

```python
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
```

- [ ] **Step 4: 跑測試確認 pass**

Run: `pytest tests/test_greedy.py -v`
Expected: 3 passed。

- [ ] **Step 5: Commit**

```bash
git add src/delivery/algorithms/greedy.py tests/test_greedy.py
git commit -m "feat(algorithms): add GreedyDispatcher with nearest-feasible-neighbor"
```

---

## Task 5: TSP-Approx 演算法

**Files:**

- Create: `src/delivery/algorithms/tsp_approx.py`

- Create: `tests/test_tsp_approx.py`

- [ ] **Step 1: 寫 failing tests**

Write `tests/test_tsp_approx.py`:

```python
from delivery.models import Order, Stop, DriverState
from delivery.algorithms.tsp_approx import TspApproxDispatcher


def test_approx_returns_valid_route(dist_factory):
    order = Order(id=1, restaurant_node=10, customer_node=20,
                  place_time=0.0, prep_time=0.0)
    state = DriverState(location_node=0, current_time=0.0, in_hand=[])
    dist = dist_factory({(0, 10): 5, (0, 20): 7, (10, 20): 3})
    disp = TspApproxDispatcher()
    decision = disp.plan(state, order, {1: order}, dist)
    assert decision.accept is True
    assert decision.new_route == [Stop(1, "pickup", 10), Stop(1, "dropoff", 20)]


def test_approx_precedence_repair(dist_factory):
    """構造一個 MST preorder 會違反 precedence 的情境，驗證修補後合法。"""
    o1 = Order(id=1, restaurant_node=10, customer_node=11, place_time=0, prep_time=0)
    o2 = Order(id=2, restaurant_node=20, customer_node=21, place_time=0, prep_time=0)
    state = DriverState(
        location_node=0, current_time=0.0,
        in_hand=[Stop(1, "pickup", 10), Stop(1, "dropoff", 11)],
    )
    dist = dist_factory({
        (0, 10): 10, (0, 11): 5, (0, 20): 100, (0, 21): 90,
        (10, 11): 8, (10, 20): 50, (10, 21): 60,
        (11, 20): 30, (11, 21): 40, (20, 21): 12,
    })
    disp = TspApproxDispatcher()
    decision = disp.plan(state, o2, {1: o1, 2: o2}, dist)
    route = decision.new_route
    for order_id in (1, 2):
        positions = [i for i, s in enumerate(route) if s.order_id == order_id]
        kinds = [route[i].kind for i in positions]
        assert kinds == ["pickup", "dropoff"]
    assert len(route) == 4


def test_approx_contains_all_stops(dist_factory):
    o1 = Order(id=1, restaurant_node=10, customer_node=11, place_time=0, prep_time=0)
    o2 = Order(id=2, restaurant_node=20, customer_node=21, place_time=0, prep_time=0)
    o3 = Order(id=3, restaurant_node=30, customer_node=31, place_time=0, prep_time=0)
    state = DriverState(
        location_node=0, current_time=0.0,
        in_hand=[Stop(1, "pickup", 10), Stop(1, "dropoff", 11)],
    )
    nodes = [0, 10, 11, 20, 21, 30, 31]
    dist = dist_factory({
        (a, b): abs(a - b) + 1
        for a in nodes for b in nodes if a != b
    })
    # 在 plan 內加入 o2、o3 → 整個 route 應含 5 個新 stops + 2 個 in_hand
    # 但 plan 一次只加一張新單；這裡先加 o2
    disp = TspApproxDispatcher()
    decision = disp.plan(state, o2, {1: o1, 2: o2}, dist)
    route = decision.new_route
    assert {(s.order_id, s.kind) for s in route} == {
        (1, "pickup"), (1, "dropoff"),
        (2, "pickup"), (2, "dropoff"),
    }
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `pytest tests/test_tsp_approx.py -v`
Expected: `ModuleNotFoundError`。

- [ ] **Step 3: 實作 tsp_approx.py**

Write `src/delivery/algorithms/tsp_approx.py`:

```python
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
    把該 pickup 從後方拉到當前位置之前。"""
    result: list[Stop] = []
    remaining = list(preorder)
    picked_up: set[int] = set()
    while remaining:
        s = remaining.pop(0)
        if s.kind == "dropoff" and s.order_id not in picked_up:
            # 找到對應 pickup（必在 remaining 內，因為原序列含所有 stops）
            pickup_idx = next(
                i for i, t in enumerate(remaining)
                if t.order_id == s.order_id and t.kind == "pickup"
            )
            pickup = remaining.pop(pickup_idx)
            result.append(pickup)
            picked_up.add(pickup.order_id)
        result.append(s)
        if s.kind == "pickup":
            picked_up.add(s.order_id)
    return result
```

- [ ] **Step 4: 跑測試確認 pass**

Run: `pytest tests/test_tsp_approx.py -v`
Expected: 3 passed。

- [ ] **Step 5: Commit**

```bash
git add src/delivery/algorithms/tsp_approx.py tests/test_tsp_approx.py
git commit -m "feat(algorithms): add TspApproxDispatcher (MST 2-approx + precedence repair)"
```

---

## Task 6: DP 演算法

**Files:**

- Create: `src/delivery/algorithms/dp.py`

- Create: `tests/test_dp.py`

- [ ] **Step 1: 寫 failing tests**

Write `tests/test_dp.py`:

```python
import random

from delivery.models import Order, Stop, DriverState
from delivery.algorithms.dp import DpDispatcher
from delivery.algorithms.greedy import GreedyDispatcher
from delivery.algorithms.tsp_approx import TspApproxDispatcher
from delivery.metrics import cost_of_route


def test_dp_single_order(dist_factory):
    order = Order(id=1, restaurant_node=10, customer_node=20,
                  place_time=0.0, prep_time=0.0)
    state = DriverState(location_node=0, current_time=0.0, in_hand=[])
    dist = dist_factory({(0, 10): 5, (0, 20): 7, (10, 20): 3})
    disp = DpDispatcher(alpha=1.0, beta=1.0)
    decision = disp.plan(state, order, {1: order}, dist)
    assert decision.accept is True
    assert decision.new_route == [Stop(1, "pickup", 10), Stop(1, "dropoff", 20)]


def test_dp_is_oracle_vs_greedy_and_approx(dist_factory):
    """隨機產生 3 張單的小 case，DP 解 cost ≤ Greedy 與 TSP-Approx。"""
    rng = random.Random(42)
    for _ in range(5):
        nodes = list(range(7))
        # 對稱、滿足三角不等式的距離（用座標生成）
        coords = {i: (rng.uniform(0, 100), rng.uniform(0, 100)) for i in nodes}

        def euclid(a: int, b: int) -> float:
            ax, ay = coords[a]
            bx, by = coords[b]
            return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5

        dist = dist_factory({
            (a, b): euclid(a, b) for a in nodes for b in nodes if a != b
        })
        orders = {
            1: Order(1, 1, 2, place_time=0.0, prep_time=0.0),
            2: Order(2, 3, 4, place_time=0.0, prep_time=0.0),
            3: Order(3, 5, 6, place_time=0.0, prep_time=0.0),
        }
        state = DriverState(location_node=0, current_time=0.0,
                            in_hand=[
                                Stop(1, "pickup", 1),
                                Stop(1, "dropoff", 2),
                                Stop(2, "pickup", 3),
                                Stop(2, "dropoff", 4),
                            ])
        candidate = orders[3]
        dp = DpDispatcher(alpha=1.0, beta=1.0).plan(state, candidate, orders, dist)
        gr = GreedyDispatcher().plan(state, candidate, orders, dist)
        ap = TspApproxDispatcher().plan(state, candidate, orders, dist)
        c_dp, _, _ = cost_of_route(dp.new_route, state, orders, dist, 1.0, 1.0)
        c_gr, _, _ = cost_of_route(gr.new_route, state, orders, dist, 1.0, 1.0)
        c_ap, _, _ = cost_of_route(ap.new_route, state, orders, dist, 1.0, 1.0)
        assert c_dp <= c_gr + 1e-6, f"DP {c_dp} > Greedy {c_gr}"
        assert c_dp <= c_ap + 1e-6, f"DP {c_dp} > Approx {c_ap}"


def test_dp_route_respects_precedence(dist_factory):
    o1 = Order(1, 10, 11, place_time=0, prep_time=0)
    o2 = Order(2, 20, 21, place_time=0, prep_time=0)
    state = DriverState(
        location_node=0, current_time=0.0,
        in_hand=[Stop(1, "pickup", 10), Stop(1, "dropoff", 11)],
    )
    dist = dist_factory({
        (0, 10): 10, (0, 11): 5, (0, 20): 100, (0, 21): 90,
        (10, 11): 8, (10, 20): 50, (10, 21): 60,
        (11, 20): 30, (11, 21): 40, (20, 21): 12,
    })
    disp = DpDispatcher(alpha=1.0, beta=1.0)
    decision = disp.plan(state, o2, {1: o1, 2: o2}, dist)
    route = decision.new_route
    for oid in (1, 2):
        positions = [i for i, s in enumerate(route) if s.order_id == oid]
        kinds = [route[i].kind for i in positions]
        assert kinds == ["pickup", "dropoff"]
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `pytest tests/test_dp.py -v`
Expected: `ModuleNotFoundError`。

- [ ] **Step 3: 實作 dp.py**

Write `src/delivery/algorithms/dp.py`:

```python
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

    # 初始化：從起點直接到每個合法 first stop（必須是 pickup）
    for i, s in enumerate(stops):
        if s.kind != "pickup":
            continue
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
                # precedence: 若 nxt 是 dropoff，對應 pickup 必須已在 mask
                if stops[nxt].kind == "dropoff":
                    p = pickup_idx[stops[nxt].order_id]
                    if not (mask & (1 << p)):
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
```

- [ ] **Step 4: 跑測試確認 pass**

Run: `pytest tests/test_dp.py -v`
Expected: 3 passed。

- [ ] **Step 5: Commit**

```bash
git add src/delivery/algorithms/dp.py tests/test_dp.py
git commit -m "feat(algorithms): add DpDispatcher (Held-Karp with time tracking)"
```

---

## Task 7: Map Loader（OSMnx wrapper）

**Files:**

- Create: `src/delivery/map_loader.py`

- Create: `tests/test_map_loader.py`

- [ ] **Step 1: 寫 failing tests**

Write `tests/test_map_loader.py`:

```python
import networkx as nx
import pytest

from delivery.map_loader import (
    extract_restaurant_nodes,
    make_distance_matrix,
    random_customer_nodes,
)


def _toy_graph() -> nx.MultiDiGraph:
    """4-node toy graph：環狀，邊權 = travel_time 秒。"""
    g = nx.MultiDiGraph()
    coords = [(0, 0), (1, 0), (1, 1), (0, 1)]
    for i, (x, y) in enumerate(coords):
        g.add_node(i, x=x, y=y)
    edges = [(0, 1), (1, 2), (2, 3), (3, 0), (1, 0), (2, 1), (3, 2), (0, 3)]
    for u, v in edges:
        g.add_edge(u, v, travel_time=10.0, length=10.0)
    return g


def test_distance_matrix_uses_dijkstra():
    g = _toy_graph()
    dist = make_distance_matrix(g, speed_mps=1.0)
    # 0 → 1 走一條邊 = 10 秒
    assert dist[(0, 1)] == pytest.approx(10.0)
    # 0 → 2 走兩條邊 = 20 秒
    assert dist[(0, 2)] == pytest.approx(20.0)
    # 自己到自己 = 0
    assert dist[(0, 0)] == 0.0


def test_random_customer_nodes_deterministic_with_seed():
    g = _toy_graph()
    a = random_customer_nodes(g, count=3, seed=42)
    b = random_customer_nodes(g, count=3, seed=42)
    assert a == b
    assert len(a) == 3
    assert all(node in g.nodes for node in a)


def test_extract_restaurant_nodes_from_attribute():
    """測試 helper 能從帶有 amenity tag 的 graph 抽出餐廳節點。"""
    g = _toy_graph()
    # 模擬 OSMnx 標註：node 1 與 node 3 標為 restaurant
    g.nodes[1]["amenity"] = "restaurant"
    g.nodes[3]["amenity"] = "fast_food"
    restaurants = extract_restaurant_nodes(g)
    assert set(restaurants) == {1, 3}
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `pytest tests/test_map_loader.py -v`
Expected: `ImportError` 或 `ModuleNotFoundError`。

- [ ] **Step 3: 實作 map_loader.py**

Write `src/delivery/map_loader.py`:

```python
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
    """從 OSMnx 拉路網。若 cache 已存在則直接讀。"""
    import osmnx as ox  # 延遲 import，避免單元測試啟動時碰網路套件

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{place.replace(' ', '_').replace(',', '')}_{dist_meters}_{network_type}.graphml"
    if cache_file.exists():
        return ox.load_graphml(cache_file)
    # OSMnx 1.9+：geocode + graph_from_point
    point = ox.geocode(place)
    g = ox.graph_from_point(point, dist=dist_meters, network_type=network_type)
    ox.save_graphml(g, cache_file)
    return g


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
```

- [ ] **Step 4: 跑測試確認 pass**

Run: `pytest tests/test_map_loader.py -v`
Expected: 3 passed。

注意：`load_graph` 走網路，沒寫單元測試（會被 CI 拒）。整合測試另測。

- [ ] **Step 5: Commit**

```bash
git add src/delivery/map_loader.py tests/test_map_loader.py
git commit -m "feat(map_loader): add OSMnx loader, distance matrix factory, POI helpers"
```

---

## Task 8: Order Stream Generator

**Files:**

- Create: `src/delivery/order_stream.py`

- Create: `tests/test_order_stream.py`

- [ ] **Step 1: 寫 failing tests**

Write `tests/test_order_stream.py`:

```python
import networkx as nx

from delivery.order_stream import generate_orders


def _toy_graph() -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    for i in range(10):
        g.add_node(i)
    for i in [1, 3, 5]:
        g.nodes[i]["amenity"] = "restaurant"
    return g


def test_generate_orders_deterministic_with_seed():
    g = _toy_graph()
    a = generate_orders(g, lambda_per_min=0.5, duration_seconds=600.0, seed=7)
    b = generate_orders(g, lambda_per_min=0.5, duration_seconds=600.0, seed=7)
    assert len(a) == len(b)
    for x, y in zip(a, b):
        assert x == y


def test_generate_orders_arrivals_within_duration():
    g = _toy_graph()
    orders = generate_orders(g, lambda_per_min=2.0, duration_seconds=600.0, seed=7)
    for o in orders:
        assert 0.0 <= o.place_time <= 600.0
        assert o.restaurant_node in {1, 3, 5}
        assert o.customer_node in g.nodes
        assert o.prep_time > 0


def test_generate_orders_unique_ids():
    g = _toy_graph()
    orders = generate_orders(g, lambda_per_min=2.0, duration_seconds=600.0, seed=7)
    ids = [o.id for o in orders]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `pytest tests/test_order_stream.py -v`
Expected: `ModuleNotFoundError`。

- [ ] **Step 3: 實作 order_stream.py**

Write `src/delivery/order_stream.py`:

```python
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
```

- [ ] **Step 4: 跑測試確認 pass**

Run: `pytest tests/test_order_stream.py -v`
Expected: 3 passed。

- [ ] **Step 5: Commit**

```bash
git add src/delivery/order_stream.py tests/test_order_stream.py
git commit -m "feat(order_stream): add Poisson order generator"
```

---

## Task 9: Simulator（事件驅動主迴圈）

**Files:**

- Create: `src/delivery/simulator.py`

- Create: `tests/test_simulator.py`

- [ ] **Step 1: 寫 failing tests**

Write `tests/test_simulator.py`:

```python
from delivery.models import Order, Stop, DriverState, Decision, DistanceMatrix
from delivery.simulator import Simulator, SimulationResult


class _AlwaysAcceptGreedy:
    """Test double：永遠接，順序就用 in_hand + 新單 pickup → dropoff。"""
    name = "test-greedy"

    def plan(self, state, candidate, all_orders, dist):
        new_route = list(state.in_hand) + [
            Stop(candidate.id, "pickup", candidate.restaurant_node),
            Stop(candidate.id, "dropoff", candidate.customer_node),
        ]
        return Decision(accept=True, new_route=new_route)


def test_simulator_single_order_end_to_end(dist_factory):
    order = Order(id=1, restaurant_node=10, customer_node=20,
                  place_time=10.0, prep_time=50.0)
    dist = dist_factory({(0, 10): 100, (10, 20): 100, (0, 20): 200})
    sim = Simulator(
        dispatcher=_AlwaysAcceptGreedy(),
        dist=dist,
        order_stream=[order],
        start_node=0,
        end_time=1000.0,
        tolerance=480.0,
        alpha=1.0,
        beta=1.0,
    )
    result = sim.run()
    assert result.accepted_orders == [1]
    assert result.rejected_orders == []
    # 抵達餐廳 t=110，餐 t=60 已好，立即取走；抵達顧客 t=210
    # customer_wait = 210 − 10 = 200
    # driver_time = 210 − 10 = 200
    assert result.customer_wait_total == 200.0


def test_simulator_rejects_when_in_hand_full(dist_factory):
    """已有 3 單在手，第 4 單一律拒。"""
    orders = [
        Order(i, 10 * i, 10 * i + 1, place_time=0.0, prep_time=0.0)
        for i in range(1, 5)
    ]
    table = {}
    nodes = [0] + [n for o in orders for n in (o.restaurant_node, o.customer_node)]
    for a in nodes:
        for b in nodes:
            if a != b:
                table[(a, b)] = abs(a - b) + 1
    dist = dist_factory(table)

    sim = Simulator(
        dispatcher=_AlwaysAcceptGreedy(),
        dist=dist,
        order_stream=orders,
        start_node=0,
        end_time=10.0,  # 故意設超短，沒時間完成任何 stop
        tolerance=float("inf"),
        alpha=1.0,
        beta=1.0,
    )
    result = sim.run()
    # 前 3 單在 t=0 全進，第 4 單被 3-order cap 擋掉
    assert 1 in result.accepted_orders
    assert 2 in result.accepted_orders
    assert 3 in result.accepted_orders
    assert 4 in result.rejected_orders


def test_simulator_clock_monotonic(dist_factory):
    """事件處理過程中 clock 不能回頭。"""
    order = Order(id=1, restaurant_node=10, customer_node=20,
                  place_time=0.0, prep_time=0.0)
    dist = dist_factory({(0, 10): 10, (10, 20): 10, (0, 20): 20})
    sim = Simulator(
        dispatcher=_AlwaysAcceptGreedy(),
        dist=dist,
        order_stream=[order],
        start_node=0,
        end_time=1000.0,
        tolerance=480.0,
        alpha=1.0,
        beta=1.0,
    )
    result = sim.run()
    times = [e.timestamp for e in result.event_log]
    assert times == sorted(times)
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `pytest tests/test_simulator.py -v`
Expected: `ModuleNotFoundError`。

- [ ] **Step 3: 實作 simulator.py**

Write `src/delivery/simulator.py`:

```python
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
```

- [ ] **Step 4: 跑測試確認 pass**

Run: `pytest tests/test_simulator.py -v`
Expected: 3 passed。

- [ ] **Step 5: Commit**

```bash
git add src/delivery/simulator.py tests/test_simulator.py
git commit -m "feat(simulator): add event-driven simulator with tolerance-based accept rule"
```

---

## Task 10: Folium 視覺化

**Files:**

- Create: `src/delivery/visualize.py`

- Create: `tests/test_visualize.py`

- [ ] **Step 1: 寫 failing tests**

Write `tests/test_visualize.py`:

```python
from pathlib import Path

import networkx as nx

from delivery.simulator import EventLogEntry, SimulationResult
from delivery.visualize import render_route_html, render_comparison_html


def _toy_geo_graph() -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    coords = {
        0: (25.0625, 121.5290),  # 大同大學周邊隨意座標
        10: (25.0635, 121.5285),
        20: (25.0620, 121.5300),
    }
    for n, (lat, lon) in coords.items():
        g.add_node(n, y=lat, x=lon)
    g.add_edge(0, 10, length=100, travel_time=20)
    g.add_edge(10, 20, length=200, travel_time=40)
    return g


def test_render_route_html_creates_file(tmp_path: Path):
    g = _toy_geo_graph()
    result = SimulationResult(
        accepted_orders=[1],
        rejected_orders=[],
        driver_time_total=60.0,
        customer_wait_total=60.0,
        total_cost=120.0,
        dispatcher_decision_ms=[1.5],
        event_log=[
            EventLogEntry(0.0, "accept", "order 1"),
            EventLogEntry(20.0, "pickup", "order 1 (wait 0s)"),
            EventLogEntry(60.0, "dropoff", "order 1 (cust_wait 60s)"),
        ],
    )
    out = tmp_path / "route.html"
    render_route_html(
        graph=g,
        result=result,
        algorithm_name="greedy",
        out_path=out,
    )
    assert out.exists()
    assert out.stat().st_size > 0
    content = out.read_text(encoding="utf-8")
    assert "greedy" in content


def test_render_comparison_html_creates_file(tmp_path: Path):
    results = {
        "greedy": SimulationResult([1], [], 100.0, 50.0, 150.0, [1.0], []),
        "tsp_approx": SimulationResult([1], [], 90.0, 40.0, 130.0, [2.0], []),
        "dp": SimulationResult([1], [], 80.0, 30.0, 110.0, [5.0], []),
    }
    out = tmp_path / "compare.html"
    render_comparison_html(results, out_path=out)
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    for name in ("greedy", "tsp_approx", "dp"):
        assert name in content
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `pytest tests/test_visualize.py -v`
Expected: `ModuleNotFoundError`。

- [ ] **Step 3: 實作 visualize.py**

Write `src/delivery/visualize.py`:

```python
"""Folium 互動地圖輸出。"""
from pathlib import Path

import folium
import networkx as nx

from delivery.simulator import SimulationResult


def render_route_html(
    graph: nx.MultiDiGraph,
    result: SimulationResult,
    algorithm_name: str,
    out_path: Path,
) -> None:
    """畫出一個演算法的 event log + summary 在 Folium 地圖上。"""
    # 算地圖中心 = graph 所有節點座標平均
    lats = [data["y"] for _, data in graph.nodes(data=True)]
    lons = [data["x"] for _, data in graph.nodes(data=True)]
    center = (sum(lats) / len(lats), sum(lons) / len(lons))

    fmap = folium.Map(location=center, zoom_start=16, tiles="OpenStreetMap")

    # 標題與指標
    summary_html = (
        f"<h3>{algorithm_name}</h3>"
        f"<p>Accepted: {len(result.accepted_orders)} | "
        f"Rejected: {len(result.rejected_orders)}<br>"
        f"Driver time: {result.driver_time_total:.0f}s | "
        f"Customer wait: {result.customer_wait_total:.0f}s<br>"
        f"Total cost: {result.total_cost:.0f} | "
        f"Avg decision: "
        f"{(sum(result.dispatcher_decision_ms) / len(result.dispatcher_decision_ms)) if result.dispatcher_decision_ms else 0:.2f} ms</p>"
    )
    folium.Marker(
        center,
        icon=folium.DivIcon(html=f'<div style="background:white;padding:6px;border:1px solid #444;width:280px;">{summary_html}</div>'),
    ).add_to(fmap)

    # 把 event log 中的 pickup / dropoff 點標出
    color_for = {"pickup": "blue", "dropoff": "green",
                 "accept": "purple", "reject": "red"}
    for entry in result.event_log:
        if entry.kind not in color_for:
            continue
        folium.CircleMarker(
            center,  # event_log 不含座標；簡化版打在中心，後續可擴充
            radius=4,
            color=color_for[entry.kind],
            fill=True,
            popup=f"t={entry.timestamp:.0f}s {entry.kind} {entry.detail}",
        ).add_to(fmap)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(out_path))


def render_comparison_html(
    results: dict[str, SimulationResult],
    out_path: Path,
) -> None:
    """產一個只有對照表的 HTML，不畫地圖。"""
    rows = []
    for name, r in results.items():
        avg_ms = (
            sum(r.dispatcher_decision_ms) / len(r.dispatcher_decision_ms)
            if r.dispatcher_decision_ms else 0.0
        )
        rows.append(
            f"<tr><td>{name}</td>"
            f"<td>{len(r.accepted_orders)}</td>"
            f"<td>{len(r.rejected_orders)}</td>"
            f"<td>{r.driver_time_total:.0f}</td>"
            f"<td>{r.customer_wait_total:.0f}</td>"
            f"<td>{r.total_cost:.0f}</td>"
            f"<td>{avg_ms:.2f}</td></tr>"
        )
    html = (
        "<html><head><meta charset='utf-8'><title>Comparison</title>"
        "<style>body{font-family:sans-serif;padding:24px}"
        "table{border-collapse:collapse}"
        "th,td{border:1px solid #888;padding:8px 12px}"
        "th{background:#eee}</style></head><body>"
        "<h2>三演算法對照</h2>"
        "<table><thead><tr>"
        "<th>Algorithm</th><th>Accepted</th><th>Rejected</th>"
        "<th>Driver time (s)</th><th>Customer wait (s)</th>"
        "<th>Total cost</th><th>Avg decision (ms)</th>"
        "</tr></thead><tbody>"
        + "".join(rows) +
        "</tbody></table></body></html>"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
```

- [ ] **Step 4: 跑測試確認 pass**

Run: `pytest tests/test_visualize.py -v`
Expected: 2 passed。

- [ ] **Step 5: Commit**

```bash
git add src/delivery/visualize.py tests/test_visualize.py
git commit -m "feat(visualize): add Folium per-algorithm map and comparison HTML"
```

---

## Task 11: Experiment Script（CLI 入口）

**Files:**

- Create: `scripts/run_experiment.py`

- [ ] **Step 1: 寫 script**

Write `scripts/run_experiment.py`:

```python
"""一鍵跑三個演算法 + 產 HTML 與表格。

用法：
    python scripts/run_experiment.py --seed 42 --lambda 0.5 --duration 3600
"""
import argparse
import random
import sys
from pathlib import Path

# 讓 script 不靠 install 也能直接跑
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from delivery.algorithms.dp import DpDispatcher  # noqa: E402
from delivery.algorithms.greedy import GreedyDispatcher  # noqa: E402
from delivery.algorithms.tsp_approx import TspApproxDispatcher  # noqa: E402
from delivery.map_loader import load_graph, make_distance_matrix  # noqa: E402
from delivery.order_stream import generate_orders  # noqa: E402
from delivery.simulator import Simulator  # noqa: E402
from delivery.visualize import render_comparison_html, render_route_html  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--lambda-per-min", type=float, default=0.5,
                   help="訂單到達率（每分鐘）；0.5 ≈ 30 單/小時")
    p.add_argument("--duration", type=float, default=3600.0,
                   help="模擬時長（秒）；預設 1 小時")
    p.add_argument("--tolerance", type=float, default=480.0,
                   help="接單成本容忍門檻（秒）；預設 480")
    p.add_argument("--alpha", type=float, default=1.0)
    p.add_argument("--beta", type=float, default=1.0)
    p.add_argument("--speed", type=float, default=5.0,
                   help="外送員平均速度（m/s）；預設 5")
    p.add_argument("--place", type=str,
                   default="Tatung University, Taipei, Taiwan")
    p.add_argument("--dist-meters", type=int, default=1500)
    p.add_argument("--out", type=str, default="out")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/4] Loading OSM graph for {args.place} (r={args.dist_meters}m)…")
    graph = load_graph(place=args.place, dist_meters=args.dist_meters,
                       network_type="drive")
    print(f"      {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")

    print(f"[2/4] Building distance matrix…")
    dist = make_distance_matrix(graph, speed_mps=args.speed)

    print(f"[3/4] Generating order stream (seed={args.seed})…")
    orders = generate_orders(
        graph,
        lambda_per_min=args.lambda_per_min,
        duration_seconds=args.duration,
        seed=args.seed,
    )
    print(f"      {len(orders)} orders generated")

    # 選一個固定起點當外送員初始位置：第一張單的餐廳節點旁邊
    rng = random.Random(args.seed)
    start_node = rng.choice(list(graph.nodes))

    print(f"[4/4] Running three algorithms…")
    dispatchers = [
        GreedyDispatcher(),
        TspApproxDispatcher(),
        DpDispatcher(alpha=args.alpha, beta=args.beta),
    ]
    results = {}
    for d in dispatchers:
        sim = Simulator(
            dispatcher=d,
            dist=dist,
            order_stream=orders,
            start_node=start_node,
            end_time=args.duration,
            tolerance=args.tolerance,
            alpha=args.alpha,
            beta=args.beta,
        )
        result = sim.run()
        results[d.name] = result
        out_path = out_dir / f"{d.name}_route.html"
        render_route_html(graph, result, d.name, out_path)
        print(f"      {d.name}: accepted={len(result.accepted_orders)} "
              f"rejected={len(result.rejected_orders)} "
              f"cost={result.total_cost:.0f} → {out_path}")

    comparison_path = out_dir / "comparison.html"
    render_comparison_html(results, comparison_path)
    print(f"\nComparison: {comparison_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add scripts/run_experiment.py
git commit -m "feat(scripts): add run_experiment CLI"
```

---

## Task 12: Integration Test + README 收尾

**Files:**

- Create: `tests/test_integration.py`

- Modify: `README.md`

- [ ] **Step 1: 寫 integration test（用 toy graph，不打網路）**

Write `tests/test_integration.py`:

```python
"""端到端測試：用 toy graph 跑一個 mini 模擬，三演算法都跑得通並產出 HTML。"""
from pathlib import Path

import networkx as nx
import pytest

from delivery.algorithms.dp import DpDispatcher
from delivery.algorithms.greedy import GreedyDispatcher
from delivery.algorithms.tsp_approx import TspApproxDispatcher
from delivery.map_loader import make_distance_matrix
from delivery.models import Order
from delivery.simulator import Simulator
from delivery.visualize import render_comparison_html, render_route_html


@pytest.fixture
def toy_geo_graph() -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    # 5x5 grid of nodes around 大同大學附近座標
    base_lat, base_lon = 25.0625, 121.5290
    for i in range(5):
        for j in range(5):
            n = i * 5 + j
            g.add_node(n,
                       y=base_lat + i * 0.0005,
                       x=base_lon + j * 0.0005)
    # 連邊：橫向 + 縱向
    for i in range(5):
        for j in range(5):
            n = i * 5 + j
            if j < 4:
                g.add_edge(n, n + 1, length=50.0)
                g.add_edge(n + 1, n, length=50.0)
            if i < 4:
                g.add_edge(n, n + 5, length=50.0)
                g.add_edge(n + 5, n, length=50.0)
    # 標 3 個 restaurant
    for n in (0, 12, 24):
        g.nodes[n]["amenity"] = "restaurant"
    return g


def test_end_to_end_all_three_algorithms(toy_geo_graph, tmp_path: Path):
    dist = make_distance_matrix(toy_geo_graph, speed_mps=5.0)
    # 手寫 5 張單而非用 Poisson，確保可重現
    orders = [
        Order(1, 0, 8, place_time=0.0, prep_time=10.0),
        Order(2, 12, 18, place_time=30.0, prep_time=20.0),
        Order(3, 24, 4, place_time=60.0, prep_time=15.0),
        Order(4, 0, 22, place_time=120.0, prep_time=5.0),
        Order(5, 12, 6, place_time=180.0, prep_time=30.0),
    ]
    dispatchers = [
        GreedyDispatcher(),
        TspApproxDispatcher(),
        DpDispatcher(alpha=1.0, beta=1.0),
    ]
    results = {}
    for d in dispatchers:
        sim = Simulator(
            dispatcher=d, dist=dist, order_stream=orders,
            start_node=12, end_time=3600.0, tolerance=480.0,
            alpha=1.0, beta=1.0,
        )
        result = sim.run()
        results[d.name] = result
        # 每個演算法都應該接到至少 1 單
        assert len(result.accepted_orders) >= 1
        out_path = tmp_path / f"{d.name}_route.html"
        render_route_html(toy_geo_graph, result, d.name, out_path)
        assert out_path.exists()

    comparison_path = tmp_path / "comparison.html"
    render_comparison_html(results, comparison_path)
    assert comparison_path.exists()
```

- [ ] **Step 2: 跑完整 test suite**

Run: `pytest -v`
Expected: 全部 pass。

- [ ] **Step 3: 完善 README**

Edit `README.md`：

```markdown
# 外送動態路由與時間成本優化

CLRS 演算法應用：用三種演算法（DP / TSP-Approx / Greedy）解動態外送路由問題。

## 動機

外送員每日接單常遇兩種時間浪費：餐點未做好的乾等、取送順序不佳的繞遠路。本專案模擬一名外送員一小時內接 20~30 筆動態到達的訂單，比較三種 CLRS 演算法在「同條件不同決策」下的時間成本表現。

## 演算法

| 角色 | 演算法 | CLRS 章節 |
|---|---|---|
| 共用工具 | Dijkstra 距離矩陣 | Ch 22.3 |
| 精確解 | Held-Karp 動態規劃 | Ch 14 |
| 近似解 | MST-based TSP 2-approximation | Ch 35.2 + Ch 21 |
| 啟發解 | Greedy 最近可行鄰居 | Ch 15 |

## 安裝

```bash
pip install -r requirements.txt
```

第一次跑會從 OSMnx 下載大同大學周邊地圖（~1.5km），約 30 秒。下載後快取在 `data/cache/`，之後讀檔。

## 跑實驗

```bash
python scripts/run_experiment.py --seed 42
```

輸出在 `out/` 目錄：

- `greedy_route.html`、`tsp_approx_route.html`、`dp_route.html`：三個演算法各自的 Folium 互動地圖
- `comparison.html`：對照表

### CLI 參數

```
--seed              隨機種子（預設 42）
--lambda-per-min    訂單到達率（預設 0.5，約 30 單/小時）
--duration          模擬秒數（預設 3600）
--tolerance         接單成本容忍門檻秒數（預設 480）
--alpha             driver_time 權重（預設 1.0）
--beta              customer_wait 權重（預設 1.0）
--speed             外送員速度 m/s（預設 5）
--place             OSM 地名（預設 Tatung University, Taipei, Taiwan）
--dist-meters       下載半徑（預設 1500）
```

## 測試

```bash
pytest
```

## 設計文件

完整設計：`docs/superpowers/specs/2026-05-24-delivery-routing-design.md`
實作計畫：`docs/superpowers/plans/2026-05-24-delivery-routing.md`

```
- [ ] **Step 4: 最後 commit**

```bash
git add tests/test_integration.py README.md
git commit -m "test: add end-to-end integration; docs: expand README"
```

- [ ] **Step 5: 全套測試最終確認**

Run: `pytest -v`
Expected: 全綠。

Run（選擇性、需要網路）: `python scripts/run_experiment.py --seed 42 --duration 1800 --lambda-per-min 0.3`
Expected: 30 分鐘模擬，產生 `out/comparison.html` 與三個 route HTML。

---

## Self-Review Checklist

執行此計畫前，作者已自我審查：

**1. Spec coverage**：

- §4 演算法選擇 → Task 4 / 5 / 6 / 7（greedy, tsp_approx, dp, Dijkstra）
- §5 系統架構（事件驅動）→ Task 9
- §6 目錄結構 → Task 0 scaffolding + 後續每個 task 對應的檔
- §7 資料模型 → Task 1
- §8 演算法細節 → Task 4 / 5 / 6 全部覆蓋（含 DP 二元組狀態、TSP-Approx 修補、Greedy precedence）
- §8.4 共用工具（距離矩陣 lazy Dijkstra、速度 5 m/s）→ Task 1（DistanceMatrix）+ Task 7（make_distance_matrix）
- §9 模擬器事件類型 → Task 9 含 ORDER_ARRIVED / DRIVER_ARRIVED_PICKUP / DRIVER_ARRIVED_DROPOFF
- §10 接受規則（in_hand < 3 hard + tolerance 軟）→ Task 9 simulator 主迴圈內實作
- §11 成本函數 → Task 2 + 累積在 Task 9
- §12 實驗設計 → Task 11 CLI 提供 seed / 變因；多 seed 跑由使用者外層 shell 迴圈處理（不在此計畫，但 CLI 已支援）
- §13 視覺化 → Task 10
- §14 測試策略 → 每個 task 都有 unit tests + Task 12 integration
- §15 開發守則 → Task 0 pyproject + .gitignore + 命名規則隱含在代碼示例

**2. Placeholder scan**：所有步驟都有具體程式碼或具體指令。未發現 TBD / TODO / "add appropriate X" 之類 placeholder。

**3. Type consistency**：

- `Dispatcher.plan` 簽章在 Task 1 定為 `(state, candidate, all_orders, dist) → Decision`，Task 4 / 5 / 6 / 9 一致
- `DistanceMatrix` 用 `dist[(u, v)]` 風格，所有呼叫端一致
- `SimulationResult` 欄位在 Task 9 定義，Task 10 / 11 一致使用
- `Order.food_ready_time` 為 property，Task 1 定義，Task 2 / 6 / 9 使用一致

# 外送動態路由與時間成本優化 — 設計文件

- **日期**：2026-05-24
- **性質**：課程作業／學術專題（CLRS 演算法應用）
- **狀態**：草稿，待使用者審閱

---

## 1. 摘要

以 OSMnx 下載大同大學（台北市中山區）周邊約 1.5 km 的真實道路網，模擬一名外送員一小時內接送 20~30 筆動態到達的訂單。比較三種 CLRS 教材中的演算法（動態規劃、TSP 近似演算法、貪婪演算法）在同一條訂單流上對「訪問順序」的優劣。輸出 Folium 互動地圖與對照指標表，作為「動態路由與時間成本優化」的演算法比較研究。

## 2. 動機與問題定義

實務上外送員每日接單常遇兩種時間浪費：

1. **餐點未做好**：抵達餐廳後在現場乾等
2. **取送地點順序不佳**：路線繞遠路、總時間拉長

當外送員手上同時有多單時（最多三單），「先取哪家、先送哪戶、何時去取下一家」的順序影響整體時間成本與顧客等待。本專案探討的問題即：

> 給定動態到達的訂單流（每筆含餐廳、顧客、下單時刻、餐點製作時間），一名外送員（最多同時持有 3 單），如何決定接單／拒單與訪問順序，使加權成本 `α·外送員時間 + β·顧客等待時間` 最小？

## 3. 範圍與假設

**範圍內**：
- 單一外送員、單一速度模型
- 最多同時持有 3 單（硬限制）
- 動態接單：訂單按 Poisson 過程到達；每筆到達時即時決定接受／拒絕
- 接受後做「全量重新規劃」：把當前所有未完成 stops + 新單一併重排
- 三個演算法輸出可比較的訪問順序與成本

**範圍外**：
- 多外送員與派單競爭
- 即時路況／壅塞模型（速度視為常數）
- 取消單、改地址、退貨
- 真實 GPS 串接、行動端 UI

**假設**：
- 道路網靜態（OSMnx 一次下載後快取）
- 外送員以固定速度沿最短路移動
- 餐廳製作時間在下單那一刻即決定，期間不變
- 顧客一律在家、無聯繫失敗

## 4. 演算法選擇（CLRS 章節對應）

訪問順序層共比較三個演算法；最短路徑層由 Dijkstra 預先算出距離矩陣，三個演算法共用。

| 角色 | 演算法 | CLRS 章節 | 性質 |
|---|---|---|---|
| 工具層 | Dijkstra | 22.3 | 預計算 OSM 道路網上任兩節點的最短行駛時間 |
| 精確解 | Held-Karp 風格 TSP 動態規劃 | 14 | 最多 7 個節點，保證最佳解，當金標準 |
| 近似解 | MST-based 2-approximation | 35.2 + 21 | 有 2 倍上界理論保證（precedence 修補後弱化） |
| 啟發解 | Greedy 最近可行鄰居 | 15 | O(n²) baseline |

三者跨越「精確 → 近似 → 啟發」三層次，呈現品質與時間的取捨。

## 5. 系統架構

事件驅動模擬器 + 可插拔 Dispatcher：

```
┌──────────────┐  ┌─────────────────────┐  ┌──────────────────┐
│  Order Stream│→ │ Event-Driven        │← │ Dispatcher       │
│  Generator   │  │ Simulator           │  │ (3 種演算法擇一)  │
│  (Poisson)   │  │  ─ event queue      │  │ ─ DP             │
└──────────────┘  │  ─ driver state     │  │ ─ TSP-Approx     │
                  │  ─ clock            │  │ ─ Greedy         │
┌──────────────┐  └─────────────────────┘  └──────────────────┘
│ OSMnx Map +  │                ↓
│ Dijkstra     │         ┌──────────────┐
│ 距離矩陣      │         │ Metrics +    │
└──────────────┘         │ Folium 視覺化│
                         └──────────────┘
```

**事件類型**：`order_arrived`、`food_ready`、`driver_arrived_pickup`、`driver_arrived_dropoff`、`simulation_end`。

**分層原則**：
- `map_loader / models / algorithms`：純函數層（無副作用、不知道時間軸），可單元測試
- `simulator`：狀態機（持有 clock + driver state），只依賴 algorithms 介面
- `visualize / metrics`：輸出層，只讀資料

**依賴方向**：`algorithms` ⟂ `simulator` ⟂ `visualize`（不互相 import；都依賴 `models` 與 `map_loader`）。

## 6. 目錄結構

```
ALGO_Kevin/
├─ README.md                         專案說明與執行方式
├─ requirements.txt                  Python 套件鎖定
├─ pyproject.toml                    pytest 設定（最小套）
├─ data/
│   └─ cache/                        OSMnx 下載的圖快取（.graphml）
├─ docs/
│   └─ superpowers/specs/            設計文件
├─ src/
│   └─ delivery/
│       ├─ __init__.py
│       ├─ map_loader.py             OSMnx 下載 + Dijkstra 距離矩陣
│       ├─ models.py                 Order、DriverState、Route、Event 等
│       ├─ order_stream.py           訂單產生器（Poisson 抵達）
│       ├─ algorithms/
│       │   ├─ __init__.py           Dispatcher Protocol
│       │   ├─ greedy.py             貪婪：最近可行鄰居
│       │   ├─ tsp_approx.py         MST-based 2-approximation
│       │   └─ dp.py                 Held-Karp DP
│       ├─ simulator.py              事件驅動主迴圈
│       ├─ metrics.py                成本函數、累積指標
│       └─ visualize.py              Folium HTML 輸出
├─ tests/
│   ├─ test_map_loader.py
│   ├─ test_algorithms.py            三個演算法在固定 case 上的解
│   ├─ test_simulator.py             事件處理與重規劃時機
│   └─ test_integration.py           跑一個小場景驗收完整 pipeline
└─ scripts/
    └─ run_experiment.py             一鍵跑三個演算法 + 產 HTML 與表格
```

## 7. 核心資料模型

```python
# models.py — 草稿
from dataclasses import dataclass
from typing import Literal, Protocol

@dataclass(frozen=True)
class Order:
    id: int
    restaurant_node: int        # OSM node id
    customer_node: int
    place_time: float           # 顧客下單時刻（秒）
    prep_time: float            # 餐點製作時間（秒）

    @property
    def food_ready_time(self) -> float:
        return self.place_time + self.prep_time

@dataclass
class Stop:
    order_id: int
    kind: Literal["pickup", "dropoff"]
    node: int

@dataclass
class DriverState:
    location_node: int
    current_time: float
    in_hand: list[Stop]         # 已接但未完成的 stops，按計畫順序
    # 不變式：set(s.order_id for s in in_hand if s.kind == 'pickup') 的單數 ≤ 3

@dataclass
class Decision:
    accept: bool
    new_route: list[Stop] | None  # 若 accept=True，這是包含新單的全新計畫

class Dispatcher(Protocol):
    name: str
    def plan(
        self,
        state: DriverState,
        candidate: Order,
        all_orders: dict[int, Order],  # 用於演算法查 order.food_ready_time / place_time
        dist: "DistanceMatrix",
    ) -> Decision: ...
```

## 8. 演算法實作細節

三個演算法輸入皆為「目前狀態 + 候選新單 + 距離矩陣」，輸出皆為包含所有 stops 的合法路線。差別只在搜尋方式。成本由統一的 `cost_of_route(route, state, dist)` 計算，演算法本身不負責算分，僅負責找順序。

### 8.1 Greedy（`greedy.py`，CLRS Ch 15）

最近可行鄰居：

1. 從 `state.location_node` 出發
2. 在「尚未訪問 + 符合 precedence」的 stops 裡，挑 `travel_time(current → s)` 最小者
3. 若抵達 pickup 時餐點未做好，等待（等待時間計入成本）
4. 重複直到所有 stops 排完

**複雜度** O(n²)。最快、解品質最差，當 baseline。

### 8.2 TSP-Approx（`tsp_approx.py`，CLRS Ch 35.2 + Ch 21）

基於 MST 的 2-approximation：

1. 在 `{current_location} ∪ all_stops` 上以距離矩陣建完全圖（已是 metric，2-approx 保證成立）
2. 用 Prim 或 Kruskal 算 MST
3. 以 `current_location` 為根做 DFS preorder，得到初始順序
4. **precedence 修補**：從前往後掃 preorder，遇到 dropoff 但對應 pickup 還沒出現時，把該 pickup 強制提前到目前位置（單向 shift，O(n)）

**複雜度** O(n² log n)。理論 2 倍上界在 precedence 修補後會被弱化——這點要在實驗報告誠實說明。

### 8.3 DP（`dp.py`，Held-Karp 風格，CLRS Ch 14）

**狀態**：`dp[S][v]` 儲存一個 `(elapsed_time, accumulated_cost)` 二元組——從 current_location 出發、已造訪集合 S（位元遮罩）、目前在 v 時的最佳「累計時間」與「累計加權成本」。需要同時記 `elapsed_time` 是因為下一個 pickup 的等待時間依賴抵達時刻。

**轉移**：對每個 v ∈ S, u ∉ S：

```
arrival_at_u  = dp[S][v].elapsed_time + travel_time(v, u)
wait_at_u     = max(0, food_ready(u) − arrival_at_u)   if u is pickup else 0
depart_u      = arrival_at_u + wait_at_u
incr_cost     = α · (travel_time(v, u) + wait_at_u)
              + (β · (depart_u − place_time_of(u))     if u is dropoff else 0)
dp[S ∪ {u}][u] = argmin over v of (
    dp[S][v].elapsed_time + travel_time(v, u) + wait_at_u,
    dp[S][v].accumulated_cost + incr_cost
)  按 accumulated_cost 最小選取
```

**Precedence 約束**：若 u 是 dropoff 但對應 pickup ∉ S，禁止此轉移（剪枝）。

**最終答案**：`min over v of dp[full_set][v].accumulated_cost`。以回溯指標還原最佳順序。

**複雜度** O(n² · 2ⁿ)。n 最多 7（current + 3 pickups + 3 dropoffs），約 896 狀態，瞬間跑完。

**重要 caveat**：此 DP 在「每次重規劃事件」上是該批 stops 的最佳解；但「整場模擬累積指標」上不保證是全局最佳——因為過去的接單決定已固定，影響未來可選空間。Section 12 的「DP 為 oracle」是指**單次重規劃**的最佳基準，不是「整場 1 小時模擬的不可超越下界」。

### 8.4 共用工具

- **距離矩陣**：`DistanceMatrix` 物件包一個 `dict[(u, v) → seconds]` cache 與底層 graph 參照。查詢時若 `(u, v)` 不在 cache 內，懶惰呼叫 Dijkstra 補上（並把該次 Dijkstra 找到的所有副產品最短路一起 cache）。動態接單下不能預先算好整張矩陣，因為每筆訂單的餐廳與顧客節點是隨機生成的。
- **速度模型**：常數 **5 m/s（機車約 18 km/h，含紅綠燈與轉彎損失的有效平均速度）**，搭配 OSMnx `network_type='drive'`。可由 CLI 旗標覆寫。
- **等待語意**：到達 pickup 時 `wait = max(0, food_ready_time − arrival_time)`，等待時間計入 `driver_time`。

## 9. 模擬器（事件驅動）

```python
# simulator.py — 草稿
class Simulator:
    def __init__(self, dispatcher: Dispatcher, dist: DistanceMatrix,
                 order_stream: list[Order], end_time: float, seed: int): ...

    def run(self) -> SimulationResult:
        # 主迴圈：pop 最早事件 → 處理 → 推進 clock → 可能塞入新事件
        ...
```

**事件處理**：
- `order_arrived(order)`：呼叫 `dispatcher.plan(state, order, dist)`；若接受，更新 `state.in_hand` 為 new_route，重排後續 `driver_arrived_*` 事件
- `food_ready(order)`：純標記，可能觸發等待結束
- `driver_arrived_pickup(stop)`：等待餐點（若未好），標記取餐完成，排下一段移動
- `driver_arrived_dropoff(stop)`：完成送達，記錄顧客等待時間
- `simulation_end`：結束模擬，收集指標

**時間推進**：完全靠事件時間戳前進；不做 tick-based 推進（避免處理小數秒對齊問題）。

## 10. 接受／拒絕規則（共用，演算法不負責）

```
cost_with_driver_time    = driver_time component of cost_of_route(new_route, state, dist)
cost_without_driver_time = driver_time component of cost_of_route(state.in_hand, state, dist)
accept = (
    len(orders_in_hand) < 3                                    # 硬限制
    and (cost_with_driver_time - cost_without_driver_time) < tolerance   # 軟限制
)
```

`tolerance` 預設 **480 秒（8 分鐘）**，意即接這單造成的**外送員額外駕駛時間**不超過 8 分鐘。不計顧客等待時間（顧客等待天生較長，若計入會幾乎全拒）。亦作為實驗變因之一，可在 `run_experiment.py` 用 CLI 旗標覆寫。

## 11. 成本函數與指標

**單一路線成本**：

```
cost(route, state) = α · driver_time(route, state)
                   + β · Σ customer_wait_time(order)
```

其中：
- `driver_time` = 從 `state.current_time` 到完成最後一個 dropoff 的總時間（含等餐）
- `customer_wait_time(order)` = `dropoff_time(order) − order.place_time`

預設 `α = 1.0`, `β = 1.0`，可於實驗中調整。

**累積指標**（每個演算法各算一份）：
- 接單成功率（accepted / total arrivals）
- 平均顧客等待時間
- 平均外送員時間（含等餐）
- 總加權成本
- 演算法平均決策耗時（毫秒）— 主賣點：成本 vs 時間 trade-off

## 12. 實驗設計

**單次 run**：固定 `seed` 生成一條 demand stream（Poisson 到達），同一條 stream 餵給三個 Dispatcher，輸出三組結果。

**多次 runs**：跑 N = 10 個不同 seed，把指標平均並算標準差，產出對照表。

**變因**：
- 到達率（λ orders/min）
- 成本權重 (α, β)
- 接受 tolerance

**對照組**：DP 為**單次重規劃事件**的局部最佳 oracle；Greedy 為下界 baseline；TSP-Approx 為中間參照。整場 1 小時模擬的累積指標上，DP 不保證全局最佳（見 §8.3 caveat），但仍預期顯著優於另兩者。

**額外觀察項**：TSP-Approx 在 precedence 修補後**可能比未修補的 preorder 還差**（極端情況甚至比 Greedy 還差）。實驗中記錄此事件發生頻率與成本上升幅度，作為「理論 2-approximation 在 precedence 約束下實務退化程度」的報告討論點。不為此加任何 fallback 緩解——三個演算法各自保持純淨形式。

## 13. 視覺化

`visualize.py` 用 Folium 產出：

- **單演算法地圖**（HTML × 3）：完整路徑（不同訂單不同顏色）、餐廳/顧客 marker、popup 顯示時間軸（下單時刻、餐點 ready、取餐、送達）
- **對照 summary HTML**：三個演算法的指標表 + 並排小地圖縮圖

底層仍可選擇用 OSMnx 內建 matplotlib 畫出靜態圖供 README 截圖使用。

## 14. 測試策略

| 層 | 測什麼 | 範例 |
|---|---|---|
| 單元 | 演算法在手寫 case 上的解 | 「兩單同方向」應排成 P1→P2→D1→D2 |
| 正確性 oracle | 小 case 上 Greedy 與 TSP-Approx 解 cost ≥ DP cost | 隨機 5 case，跑斷言 |
| 模擬器 | 假事件序列下 driver 狀態正確變化 | clock 不回頭、in_hand 數量永不超過 3 |
| 整合 | 跑一個 mini scenario 直到輸出 Folium HTML | 5 單、固定 seed、HTML 存在且非空 |

DP 在 n ≤ 7 是最佳解，天然當其他兩者的 oracle，不需另寫驗證。

## 15. 開發守則（最小套）

```yaml
Python: 3.11+
套件:
  必要: osmnx, networkx, folium, pytest
  建議: numpy, pandas（指標彙整用）
命名:
  函式/變數: snake_case
  類別: PascalCase
  常數: SCREAMING_SNAKE
型別註解: 函式簽章一律有；複雜資料用 @dataclass
函式長度: 超過 50 行優先考慮拆分
註解: 預設不寫；只在「為什麼」非顯而易見時加一行
依賴方向: algorithms ⟂ simulator ⟂ visualize（不互相 import）
測試: 每個演算法 ≥ 2 個 unit test；至少 1 個 integration test
快取: OSMnx graph 落地 data/cache/*.graphml，第二次跑直接讀
隨機: 所有隨機都吃 seed 參數，必須可重現
```

## 16. 開放問題

設計階段的三項開放問題（tolerance 預設值、速度模型、TSP-Approx 退化現象）已於 §10、§8.4、§12 敲定。本節保留以紀錄實驗執行階段若新發現議題之處。

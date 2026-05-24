# 外送動態路由與時間成本優化

CLRS 演算法應用：用三種演算法（DP / TSP-Approx / Greedy）解動態外送路由問題。

## 動機

外送員每日接單常遇兩種時間浪費：餐點未做好的乾等、取送順序不佳的繞遠路。本專案模擬一名外送員一小時內接 20~30 筆動態到達的訂單，比較三種 CLRS 演算法在「同條件不同決策」下的時間成本表現。

## 演算法

| 角色   | 演算法                           | CLRS 章節         |
| ---- | ----------------------------- | --------------- |
| 共用工具 | Dijkstra 距離矩陣                 | Ch 22.3         |
| 精確解  | Held-Karp 動態規劃                | Ch 14           |
| 近似解  | MST-based TSP 2-approximation | Ch 35.2 + Ch 21 |
| 啟發解  | Greedy 最近可行鄰居                 | Ch 15           |

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

## 互動式版本（自行選取 / 送餐點）

不固定產生訂單，改由使用者在瀏覽器地圖上自選取餐 / 送餐地點，即時比較三種演算法。

```bash
python scripts/run_interactive.py
```

啟動後開啟 **http://127.0.0.1:5000/**，操作流程：

1. 選「🍱 新增取餐點 / 🏠 新增送餐點 / 🚗 設定司機起點」模式，點地圖佈點（取、送餐點數量須相同）。
2. 按「⚡ 計算路線」，後端以 Greedy / TSP 近似 / DP 三種演算法規劃路線。
3. 右側顯示中文「演算法比較」表（演算法、總距離、預估行駛時間、計算時間、結果說明）與自動產生的分析說明；地圖上以不同顏色畫出**沿真實道路節點**的路線。

路徑嚴格沿 OSMnx / NetworkX 道路圖：使用者點選的經緯度會 snap 到最近可行駛道路邊的可抵達節點，停靠點之間再用 shortest path 補齊實際道路折線（**非兩點直線連接**）。計算耗時以 `time.perf_counter()` 量測（毫秒）。

路線遵守道路方向（不逆向），需折返時繞經路口；取/送餐點 snap 到最近可行駛道路邊的可抵達位置。**限制**：OSM 為道路中心線資料，無法精確區分雙向道的左右車道側，故路線方向正確但「對向車道」之區分僅為中心線近似，並非真實車道級精度。

> **注意**：只放「一組」取 / 送餐點時，唯一可行路線就是「先取餐再送餐」，三種演算法必然產生**相同路徑**，差異僅在計算時間。要比較路徑品質，請新增**多組（建議 2～3 組以上）**取 / 送餐點，演算法才會對停靠順序做出不同的最佳化決策。

### CLI 參數

```
--host          綁定位址（預設 127.0.0.1）
--port          埠號（預設 5000）
--place         OSM 地名（預設 Tatung University, Taipei, Taiwan）
--dist-meters   下載半徑（預設 1500）
--speed         外送員速度 m/s（預設 5）
```

實作分工：核心邏輯在 `src/delivery/interactive.py`（snap、規劃、道路折線、中文分析，沿用既有三演算法），Flask 伺服器在 `scripts/run_interactive.py`，前端在 `templates/interactive_map.html` + `static/interactive.js`。

## 測試

```bash
pytest
```

## 設計文件

完整設計：`docs/superpowers/specs/2026-05-24-delivery-routing-design.md`
實作計畫：`docs/superpowers/plans/2026-05-24-delivery-routing.md`

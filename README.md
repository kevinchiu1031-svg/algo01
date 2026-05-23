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

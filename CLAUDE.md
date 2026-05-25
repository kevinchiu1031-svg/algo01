# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A CLRS-algorithms demo: three dispatch algorithms (Held-Karp DP, MST-based TSP 2-approximation, Greedy nearest-feasible-neighbor) solve the same dynamic food-delivery routing problem so their time-cost tradeoffs can be compared. Code comments, docstrings, and UI text are in Traditional Chinese; keep that convention when editing.

## Commands

```bash
# Install (prefer a project-local .venv — never the system Python)
python -m venv .venv && .venv\Scripts\activate   # Windows PowerShell
pip install -r requirements.txt

# Batch experiment: simulate ~1h of Poisson order arrivals, compare 3 algorithms,
# emit Folium HTML maps + comparison table to out/
python scripts/run_experiment.py --seed 42

# Interactive web app: user clicks pickup/dropoff points on a Leaflet map,
# backend plans routes with all 3 algorithms. Opens http://127.0.0.1:5000/
python scripts/run_interactive.py

# Tests
pytest                          # all
pytest tests/test_dp.py         # one file
pytest tests/test_dp.py::TestHeldKarp::test_name   # one test
```

First graph load downloads from OSMnx (~30s) and caches a `.graphml` under `data/cache/`; later runs read the cache. Unit tests never hit the network (OSMnx is imported lazily and tests use toy graphs).

## Architecture

The central seam is the **`Dispatcher` Protocol** (`src/delivery/models.py`): every algorithm implements `plan(state, candidate, all_orders, dist) -> Decision`, returning a full re-planned route (`list[Stop]`) when accepting an order. This is what lets the simulator and the interactive module swap algorithms uniformly. The three implementations live in `src/delivery/algorithms/{dp,tsp_approx,greedy}.py`.

There are **two distinct "drivers"** that consume dispatchers:

- **`Simulator`** (`simulator.py`) — event-driven (heap of timestamped events) for the batch experiment. Models order arrival, the 3-order in-hand cap, and a `tolerance` threshold that rejects orders whose marginal driver-time cost is too high. On each acceptance it re-plans and invalidates the previously scheduled arrival event (`valid_arrival_seq`).
- **`plan_full_route`** (`interactive.py`) — feeds user-selected orders to a dispatcher sequentially, accepting every plan. No rejection logic. Used by the web app.

**`DistanceMatrix`** (`models.py`) is a lazy Dijkstra cache: `dist[(u, v)]` triggers a `networkx.shortest_path_length` lookup on first access (weight `travel_time = length / speed_mps`), then caches. Built by `make_distance_matrix` in `map_loader.py`.

**Precedence constraint** — every order is a (pickup, dropoff) pair and pickup must precede dropoff. Each algorithm enforces this differently: DP gates it during mask expansion, greedy filters infeasible stops each step, tsp_approx does a post-order repair pass. All three also handle the partial case where a pickup was *already completed* by the simulator (only the dropoff `Stop` remains in `in_hand` — that order is treated as already picked up).

**Graph invariant** — `load_graph` keeps only the largest *strongly-connected* component, so every node is reachable from every other under directed (one-way-respecting) driving. Code that adds graph manipulation should preserve this.

### Interactive road geometry (the subtle part)

`interactive.py` does more than ordering — it draws routes that follow real directed roads and physically reach each stop:

- `snap_to_edge` snaps a clicked lat/lng to the nearest *drivable directed edge* (not just a node), recording the entry node `u`, exit node `v`, the edge key, the projection parameter `t`, and the "approach" point (the legal curbside position on that edge).
- `build_visited_route` stitches a single continuous polyline: directed shortest-path between stops, then an in-edge `u → approach → v` segment so the route passes the stop on the legal side of the road. It returns `arrival_indices` and `included` flags verifying every stop was actually reached. A stop not reached marks the whole algorithm result as failed.
- The dispatcher optimizes using `enter_node` directed distances, while the displayed `road_distance_m` includes the in-edge approach segments — so the optimized cost is an *approximation* of the displayed distance (orderings usually agree, magnitudes differ slightly). This is a known, documented modeling simplification.

OSM data is road centerlines, so left/right lane sides of a two-way road cannot be distinguished — directions are correct, "opposite lane" is only a centerline approximation.

### Web layer

`scripts/run_interactive.py` is the Flask server. The graph is lazy-loaded into module globals (`_GRAPH`, `_DIST`) on first request and eagerly pre-warmed at `__main__` startup. `POST /api/route` validates the JSON body, calls `compare_algorithms`, and returns per-algorithm `AlgoResult.to_dict()` plus a `chinese_analysis` summary string. Frontend is `templates/interactive_map.html` + `static/interactive.js` (Leaflet).

## Important domain notes

- With **only one pickup/dropoff pair**, the sole feasible route is "pickup then dropoff" — all three algorithms produce *identical* paths and only compute time differs. Meaningful path-quality comparison needs **2-3+ pairs**. `chinese_analysis` special-cases this and tells the user to add more points.
- Cost model: `total_cost = alpha * driver_time + beta * customer_wait`. `metrics.cost_of_route` returns `(total_cost, driver_time, customer_wait)`; `tolerance` in the simulator compares against driver_time only.
- Prep time / rider wait (interactive mode): each order carries `prep_time` (0–25 min via `prep_times_min` in the API), so `food_ready_time = prep_time*60` from t=0. Greedy is **wait-aware** — it minimizes `travel + wait + penalty` where waits beyond `WAIT_TOLERANCE_S` (180s, in `models.py`) get a `WAIT_OVERAGE_WEIGHT` penalty, so the rider does productive stops instead of idling at a restaurant. DP needs no penalty — minimizing driver_time (which already includes waiting) is globally wait-optimal. TSP-approx stays purely geometric and intentionally shows more waiting. `compare_algorithms` reports `total_wait_s`, `exceeds_wait_tolerance`, per-stop `wait_s`, and `orders_info` via `metrics.route_timeline`.
- Tests use a 5×5 grid `MultiDiGraph` toy fixture (`tests/test_interactive.py`, `tests/test_integration.py`) and a `dist_factory` fixture (`tests/conftest.py`) that builds a `DistanceMatrix` from a dict.

## Design docs

`docs/superpowers/specs/2026-05-24-delivery-routing-design.md` (design) and `docs/superpowers/plans/2026-05-24-delivery-routing.md` (implementation plan).

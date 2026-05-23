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

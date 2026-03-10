"""
MSE 433 Module 3: Warehousing — Analysis V5 (Multi-Objective Optimization)

Key changes from V4:
- Evaluates algorithms using a WEIGHTED COMPOSITE SCORE blending three objectives:
    1. Total completion time  (efficiency)
    2. Makespan               (fairness — no single order waits too long)
    3. Total circulations      (waste — fewer wasted laps)
- Each algorithm has "philosophy weights" reflecting its design intent
- Grid search over 231 weight combos finds optimal weights per-algorithm and universally
- 10-seed sensitivity analysis validates robustness
- 7 publication-quality figures

Seed=777.  All outputs saved to Module3_v5/.
"""

import os
import sys
import csv
import itertools
from collections import defaultdict

from data_pipeline import generate_data, Order, SHAPE_NAMES, NUM_SHAPES, print_summary, save_csvs
from conveyor_sim import ConveyorSimulator, SimResult
from algorithms import ALL_ALGORITHMS_CONTINUOUS, compute_tote_order
from generate_input import save_order_csv, save_tote_schedule

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1: CONFIG
# ══════════════════════════════════════════════════════════════════════════════

SEED_V5 = 777
SMALL_ORDERS = 6
SMALL_TOTES = 8
SMALL_ITEMTYPES = 8

SEEDS = [777, 42, 100, 200, 612, 888, 999, 1111, 2025, 2026]

SIM_PARAMS = {"loop_time": 40.0, "divert_time": 5.0, "load_interval": 3.0}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE_DIR, "results")
FIGURES_DIR = os.path.join(RESULTS_DIR, "figures")
CSV_DIR = os.path.join(RESULTS_DIR, "input_csvs")
DATA_DIR = os.path.join(RESULTS_DIR, "generated_data")

os.makedirs(FIGURES_DIR, exist_ok=True)
os.makedirs(CSV_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

ALGO_NAMES = list(ALL_ALGORITHMS_CONTINUOUS.keys())

# Philosophy weight profiles: (w_total_comp, w_makespan, w_circulations)
PHILOSOPHY_WEIGHTS = {
    "Random Baseline":       (0.34, 0.33, 0.33),
    "Shortest Order First":  (0.70, 0.15, 0.15),
    "Load Balanced":         (0.15, 0.70, 0.15),
    "Tote-Aware Clustering": (0.15, 0.15, 0.70),
    "Wave Batching":         (0.40, 0.35, 0.25),
}

COLORS = {
    "Random Baseline":       "#e74c3c",
    "Shortest Order First":  "#3498db",
    "Load Balanced":         "#2ecc71",
    "Tote-Aware Clustering": "#f39c12",
    "Wave Batching":         "#9b59b6",
}
COLOR_LIST = [COLORS[n] for n in ALGO_NAMES]


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2: DATA COLLECTION
# ══════════════════════════════════════════════════════════════════════════════

def collect_raw_results(seeds, n_orders=SMALL_ORDERS, n_totes=SMALL_TOTES,
                        n_itemtypes=SMALL_ITEMTYPES):
    """
    Run all 5 algorithms × len(seeds) seeds using simulate_tote_ordered().
    Returns {seed: {algo_name: SimResult}}
    """
    sim = ConveyorSimulator(**SIM_PARAMS)
    all_results = {}

    for s in seeds:
        orders, totes, params = generate_data(
            seed=s, n_orders=n_orders, n_totes=n_totes, n_itemtypes=n_itemtypes
        )
        seed_results = {}
        for name, algo in ALL_ALGORITHMS_CONTINUOUS.items():
            lane_queues = algo(orders)
            result = sim.simulate_tote_ordered(lane_queues, totes, orders)
            seed_results[name] = result
        all_results[s] = seed_results

    return all_results


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3: NORMALIZATION
# ══════════════════════════════════════════════════════════════════════════════

def extract_metrics(result):
    """Extract the three objectives from a SimResult."""
    return (result.total_completion_time, result.makespan, result.total_circulations)


def normalize_metrics_per_seed(seed_results):
    """
    Min-max normalize (total_comp, makespan, circulations) to [0,1]
    across the 5 algorithms for a single seed.

    Returns {algo_name: (norm_total_comp, norm_makespan, norm_circs)}
    Edge case: if all algorithms tie on a metric, normalized = 0 (no penalty).
    """
    names = list(seed_results.keys())
    raw = {n: extract_metrics(seed_results[n]) for n in names}

    # Find min/max for each of the 3 metrics
    mins = [min(raw[n][i] for n in names) for i in range(3)]
    maxs = [max(raw[n][i] for n in names) for i in range(3)]

    normalized = {}
    for n in names:
        norm = []
        for i in range(3):
            rng = maxs[i] - mins[i]
            if rng == 0:
                norm.append(0.0)  # all tied → no penalty
            else:
                norm.append((raw[n][i] - mins[i]) / rng)
        normalized[n] = tuple(norm)

    return normalized


def normalize_metrics_per_seed_ranks(seed_results):
    """
    Rank-based normalization: rank algorithms 1 (best) to N (worst) on each
    metric, then scale to [0, 1] where 0 = best rank, 1 = worst rank.

    Handles ties via average rank (e.g., two algorithms tied for 1st both get 1.5).
    This avoids the min-max problem where many algorithms get 0.0 when they tie
    at the minimum value.

    Returns {algo_name: (rank_total_comp, rank_makespan, rank_circs)} scaled to [0,1]
    """
    names = list(seed_results.keys())
    n = len(names)
    raw = {name: extract_metrics(seed_results[name]) for name in names}

    normalized = {name: [0.0, 0.0, 0.0] for name in names}

    for metric_idx in range(3):
        # Sort names by this metric (ascending — lower is better)
        values = [(raw[name][metric_idx], name) for name in names]
        values.sort(key=lambda x: x[0])

        # Assign ranks with average-rank tie-breaking
        ranks = {}
        i = 0
        while i < n:
            j = i
            while j < n and values[j][0] == values[i][0]:
                j += 1
            # Positions i..j-1 are tied; average rank = mean of (i+1)..(j)
            avg_rank = sum(range(i + 1, j + 1)) / (j - i)
            for k in range(i, j):
                ranks[values[k][1]] = avg_rank
            i = j

        # Normalize rank to [0, 1]: rank 1 -> 0.0, rank N -> 1.0
        for name in names:
            if n > 1:
                normalized[name][metric_idx] = (ranks[name] - 1) / (n - 1)
            else:
                normalized[name][metric_idx] = 0.0

    return {name: tuple(normalized[name]) for name in names}


def compute_composite_score(norm_metrics, weights):
    """
    Compute weighted composite score.
    norm_metrics: (norm_total_comp, norm_makespan, norm_circs)
    weights: (w1, w2, w3) summing to 1.0
    Lower score = better.
    """
    return sum(n * w for n, w in zip(norm_metrics, weights))


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5: GRID SEARCH UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def generate_weight_grid(step=0.05, min_weight=0.10):
    """
    Generate all weight combos (w1, w2, w3) where w1+w2+w3=1.0
    with the given step size. Each weight must be >= min_weight
    to prevent degenerate corner solutions (single-metric optimization).
    Returns list of 3-tuples.
    """
    grid = []
    n_steps = int(round(1.0 / step))
    for i in range(n_steps + 1):
        for j in range(n_steps + 1 - i):
            k = n_steps - i - j
            w1 = round(i * step, 4)
            w2 = round(j * step, 4)
            w3 = round(k * step, 4)
            if w1 >= min_weight and w2 >= min_weight and w3 >= min_weight:
                grid.append((w1, w2, w3))
    return grid


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 80)
    print(f"MODULE 3 — V5 MULTI-OBJECTIVE OPTIMIZATION (seed={SEED_V5})")
    print(f"  Instance: {SMALL_ORDERS} orders, {SMALL_TOTES} totes, "
          f"{SMALL_ITEMTYPES} item types max")
    print(f"  Seeds: {SEEDS}")
    print("=" * 80)

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 1: Collect raw results for all seeds
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[1/11] Collecting raw simulation results...")
    all_results = collect_raw_results(SEEDS)

    # Print raw results for primary seed
    print(f"\nRaw results for seed={SEED_V5}:")
    print(f"  {'Algorithm':<25} {'Total Comp':>12} {'Makespan':>10} {'Circulations':>13}")
    print("  " + "-" * 62)
    for name in ALGO_NAMES:
        r = all_results[SEED_V5][name]
        print(f"  {name:<25} {r.total_completion_time:>12.2f} "
              f"{r.makespan:>10.2f} {r.total_circulations:>13}")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 2: Normalize metrics per seed (rank-based)
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[2/11] Normalizing metrics (rank-based per seed)...")
    print("  Using rank-based normalization to handle ties properly.")
    print("  (Min-max normalization collapses when algorithms tie on a metric.)")
    all_normalized = {}
    all_normalized_minmax = {}
    for s in SEEDS:
        all_normalized[s] = normalize_metrics_per_seed_ranks(all_results[s])
        all_normalized_minmax[s] = normalize_metrics_per_seed(all_results[s])

    # Print both normalizations for primary seed
    print(f"\nRank-based normalized metrics for seed={SEED_V5} (0=best, 1=worst):")
    print(f"  {'Algorithm':<25} {'Total Comp':>12} {'Makespan':>10} {'Circulations':>13}")
    print("  " + "-" * 62)
    for name in ALGO_NAMES:
        n = all_normalized[SEED_V5][name]
        print(f"  {name:<25} {n[0]:>12.4f} {n[1]:>10.4f} {n[2]:>13.4f}")

    print(f"\n  (Comparison: min-max normalized for seed={SEED_V5}):")
    print(f"  {'Algorithm':<25} {'Total Comp':>12} {'Makespan':>10} {'Circulations':>13}")
    print("  " + "-" * 62)
    for name in ALGO_NAMES:
        n = all_normalized_minmax[SEED_V5][name]
        print(f"  {name:<25} {n[0]:>12.4f} {n[1]:>10.4f} {n[2]:>13.4f}")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 3: Compute average normalized metrics across seeds
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[3/11] Computing average normalized metrics across seeds...")
    avg_normalized = {}
    for name in ALGO_NAMES:
        avg = [0.0, 0.0, 0.0]
        for s in SEEDS:
            for i in range(3):
                avg[i] += all_normalized[s][name][i]
        avg = tuple(a / len(SEEDS) for a in avg)
        avg_normalized[name] = avg

    print(f"\nAverage normalized metrics ({len(SEEDS)} seeds):")
    print(f"  {'Algorithm':<25} {'Avg Total':>12} {'Avg Makespan':>14} {'Avg Circs':>12}")
    print("  " + "-" * 66)
    for name in ALGO_NAMES:
        a = avg_normalized[name]
        print(f"  {name:<25} {a[0]:>12.4f} {a[1]:>14.4f} {a[2]:>12.4f}")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 4: Philosophy weight scores
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[4/11] Scoring algorithms under philosophy weights...")

    # For each algorithm, compute its average composite score under its own weights
    philosophy_scores = {}
    for name in ALGO_NAMES:
        weights = PHILOSOPHY_WEIGHTS[name]
        scores_per_seed = []
        for s in SEEDS:
            nm = all_normalized[s][name]
            scores_per_seed.append(compute_composite_score(nm, weights))
        philosophy_scores[name] = sum(scores_per_seed) / len(scores_per_seed)

    print(f"\n  {'Algorithm':<25} {'Weights (tc,ms,ci)':>20} {'Avg Score':>12}")
    print("  " + "-" * 60)
    for name in ALGO_NAMES:
        w = PHILOSOPHY_WEIGHTS[name]
        print(f"  {name:<25} ({w[0]:.2f},{w[1]:.2f},{w[2]:.2f})      "
              f"{philosophy_scores[name]:>12.4f}")

    # Cross-score: each algorithm scored under EVERY philosophy
    print(f"\n  Cross-scoring (row = algorithm, col = weight profile):")
    header = f"  {'Algorithm':<25}" + "".join(f"{n[:10]:>12}" for n in ALGO_NAMES)
    print(header)
    print("  " + "-" * (25 + 12 * len(ALGO_NAMES)))

    cross_scores = {}
    for algo_name in ALGO_NAMES:
        cross_scores[algo_name] = {}
        for wp_name in ALGO_NAMES:
            weights = PHILOSOPHY_WEIGHTS[wp_name]
            scores_per_seed = []
            for s in SEEDS:
                nm = all_normalized[s][algo_name]
                scores_per_seed.append(compute_composite_score(nm, weights))
            cross_scores[algo_name][wp_name] = sum(scores_per_seed) / len(scores_per_seed)

        row = f"  {algo_name:<25}"
        for wp_name in ALGO_NAMES:
            row += f"{cross_scores[algo_name][wp_name]:>12.4f}"
        print(row)

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 5: Grid search — per-algorithm optimal weights
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[5/11] Grid search: finding optimal weights per algorithm...")
    weight_grid = generate_weight_grid(step=0.05)
    print(f"  Weight grid size: {len(weight_grid)} combinations")

    optimized_weights = {}
    optimized_scores = {}

    for name in ALGO_NAMES:
        best_w = None
        best_score = float('inf')

        for w in weight_grid:
            scores_per_seed = []
            for s in SEEDS:
                nm = all_normalized[s][name]
                scores_per_seed.append(compute_composite_score(nm, w))
            avg_score = sum(scores_per_seed) / len(scores_per_seed)

            if avg_score < best_score:
                best_score = avg_score
                best_w = w

        optimized_weights[name] = best_w
        optimized_scores[name] = best_score

    print(f"\n  {'Algorithm':<25} {'Philosophy Wts':>18} {'Score':>8}  "
          f"{'Optimized Wts':>18} {'Score':>8}  {'Change':>8}")
    print("  " + "-" * 90)
    for name in ALGO_NAMES:
        pw = PHILOSOPHY_WEIGHTS[name]
        ps = philosophy_scores[name]
        ow = optimized_weights[name]
        os_ = optimized_scores[name]
        change = ((os_ - ps) / ps * 100) if ps > 0 else 0
        print(f"  {name:<25} ({pw[0]:.2f},{pw[1]:.2f},{pw[2]:.2f})  {ps:>8.4f}  "
              f"({ow[0]:.2f},{ow[1]:.2f},{ow[2]:.2f})  {os_:>8.4f}  {change:>+7.1f}%")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 6: Grid search — universal best weights (seed-win method)
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[6/11] Grid search: finding universal best weights...")
    print("  Method: for each weight combo, count per-seed wins. Pick the")
    print("  weights where the top algorithm wins the MOST seeds.")

    universal_best_w = None
    universal_best_algo = None
    universal_best_wins = 0
    universal_best_avg = float('inf')  # tiebreaker

    # Grid search CSV data
    grid_search_rows = []

    for w in weight_grid:
        # Score all algorithms under this weight for CSV data
        algo_avg_scores = {}
        for name in ALGO_NAMES:
            scores_per_seed = []
            for s in SEEDS:
                nm = all_normalized[s][name]
                scores_per_seed.append(compute_composite_score(nm, w))
            avg_score = sum(scores_per_seed) / len(scores_per_seed)
            algo_avg_scores[name] = avg_score

            grid_search_rows.append({
                "w_total_comp": w[0],
                "w_makespan": w[1],
                "w_circulations": w[2],
                "algorithm": name,
                "avg_score": avg_score,
            })

        # Count per-seed wins under this weight combo
        algo_wins = {n: 0 for n in ALGO_NAMES}
        for s in SEEDS:
            seed_scores = {}
            for name in ALGO_NAMES:
                nm = all_normalized[s][name]
                seed_scores[name] = compute_composite_score(nm, w)
            winner = min(seed_scores, key=seed_scores.get)
            algo_wins[winner] += 1

        # Find the algorithm with the most wins under this weight
        top_algo = max(algo_wins, key=algo_wins.get)
        top_wins = algo_wins[top_algo]
        top_avg = algo_avg_scores[top_algo]

        # Update universal best: most wins, then lowest avg as tiebreaker
        if (top_wins > universal_best_wins or
                (top_wins == universal_best_wins and top_avg < universal_best_avg)):
            universal_best_wins = top_wins
            universal_best_w = w
            universal_best_algo = top_algo
            universal_best_avg = top_avg

    print(f"  Universal best weights: ({universal_best_w[0]:.2f}, "
          f"{universal_best_w[1]:.2f}, {universal_best_w[2]:.2f})")
    print(f"  Universal best algorithm: {universal_best_algo}")
    print(f"  Seed wins: {universal_best_wins}/{len(SEEDS)}")
    print(f"  Avg composite score: {universal_best_avg:.4f}")

    # Score all algorithms under universal weights
    universal_scores = {}
    for name in ALGO_NAMES:
        scores_per_seed = []
        for s in SEEDS:
            nm = all_normalized[s][name]
            scores_per_seed.append(compute_composite_score(nm, universal_best_w))
        universal_scores[name] = sum(scores_per_seed) / len(scores_per_seed)

    print(f"\n  All algorithms under universal weights "
          f"({universal_best_w[0]:.2f},{universal_best_w[1]:.2f},{universal_best_w[2]:.2f}):")
    print(f"  {'Algorithm':<25} {'Avg Score':>10} {'Rank':>6}")
    print("  " + "-" * 44)
    ranked = sorted(ALGO_NAMES, key=lambda n: universal_scores[n])
    for rank, name in enumerate(ranked, 1):
        marker = " <-- BEST" if rank == 1 else ""
        print(f"  {name:<25} {universal_scores[name]:>10.4f} {rank:>6}{marker}")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 7: Comparison table
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[7/11] Comparison table: philosophy vs optimized vs universal...")

    comparison_rows = []
    print(f"\n  {'Algorithm':<25} {'Phil Score':>12} {'Opt Score':>12} "
          f"{'Univ Score':>12} {'Best Profile':>14}")
    print("  " + "-" * 78)
    for name in ALGO_NAMES:
        ps = philosophy_scores[name]
        os_ = optimized_scores[name]
        us = universal_scores[name]
        best_profile = min([("Philosophy", ps), ("Optimized", os_), ("Universal", us)],
                           key=lambda x: x[1])
        print(f"  {name:<25} {ps:>12.4f} {os_:>12.4f} {us:>12.4f} {best_profile[0]:>14}")

        comparison_rows.append({
            "algorithm": name,
            "philosophy_weights": f"({PHILOSOPHY_WEIGHTS[name][0]:.2f},"
                                  f"{PHILOSOPHY_WEIGHTS[name][1]:.2f},"
                                  f"{PHILOSOPHY_WEIGHTS[name][2]:.2f})",
            "philosophy_score": ps,
            "optimized_weights": f"({optimized_weights[name][0]:.2f},"
                                 f"{optimized_weights[name][1]:.2f},"
                                 f"{optimized_weights[name][2]:.2f})",
            "optimized_score": os_,
            "universal_weights": f"({universal_best_w[0]:.2f},"
                                 f"{universal_best_w[1]:.2f},"
                                 f"{universal_best_w[2]:.2f})",
            "universal_score": us,
            "best_profile": best_profile[0],
        })

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 8: Win count analysis
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[8/11] Win count analysis across seeds...")

    win_counts = {
        "Philosophy": {n: 0 for n in ALGO_NAMES},
        "Optimized":  {n: 0 for n in ALGO_NAMES},
        "Universal":  {n: 0 for n in ALGO_NAMES},
    }

    for s in SEEDS:
        # Philosophy wins: each algo scored under its own weights, best overall
        phil_seed_scores = {}
        for name in ALGO_NAMES:
            nm = all_normalized[s][name]
            phil_seed_scores[name] = compute_composite_score(nm, PHILOSOPHY_WEIGHTS[name])
        phil_winner = min(phil_seed_scores, key=phil_seed_scores.get)
        win_counts["Philosophy"][phil_winner] += 1

        # Optimized wins: each algo scored under its optimized weights
        opt_seed_scores = {}
        for name in ALGO_NAMES:
            nm = all_normalized[s][name]
            opt_seed_scores[name] = compute_composite_score(nm, optimized_weights[name])
        opt_winner = min(opt_seed_scores, key=opt_seed_scores.get)
        win_counts["Optimized"][opt_winner] += 1

        # Universal wins: all algos scored under universal weights
        univ_seed_scores = {}
        for name in ALGO_NAMES:
            nm = all_normalized[s][name]
            univ_seed_scores[name] = compute_composite_score(nm, universal_best_w)
        univ_winner = min(univ_seed_scores, key=univ_seed_scores.get)
        win_counts["Universal"][univ_winner] += 1

    print(f"\n  {'Algorithm':<25} {'Philosophy':>12} {'Optimized':>12} {'Universal':>12}")
    print("  " + "-" * 64)
    for name in ALGO_NAMES:
        print(f"  {name:<25} {win_counts['Philosophy'][name]:>12} "
              f"{win_counts['Optimized'][name]:>12} "
              f"{win_counts['Universal'][name]:>12}")

    # Determine V4 winner (single-metric: total completion time)
    v4_win_counts = {n: 0 for n in ALGO_NAMES}
    for s in SEEDS:
        best_tc = min(ALGO_NAMES,
                      key=lambda n: all_results[s][n].total_completion_time)
        v4_win_counts[best_tc] += 1
    v4_winner = max(v4_win_counts, key=v4_win_counts.get)
    v5_winner = universal_best_algo

    print(f"\n  V4 winner (total completion only): {v4_winner} "
          f"({v4_win_counts[v4_winner]}/{len(SEEDS)} seeds)")
    print(f"  V5 winner (multi-objective):       {v5_winner} "
          f"({win_counts['Universal'][v5_winner]}/{len(SEEDS)} seeds)")
    print(f"  (V5 winner selected by: most seed wins under universal weights)")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 9: PLOTS (7 figures)
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[9/11] Generating plots...")

    # ---- Figure 1: Radar chart ----
    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    categories = ["Total Completion\n(lower=better)", "Makespan\n(lower=better)",
                   "Circulations\n(lower=better)"]
    N = len(categories)
    angles = [n / float(N) * 2 * np.pi for n in range(N)]
    angles += angles[:1]  # close the polygon

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=10)

    for name in ALGO_NAMES:
        values = list(avg_normalized[name])
        values += values[:1]
        ax.plot(angles, values, 'o-', linewidth=2, label=name, color=COLORS[name])
        ax.fill(angles, values, alpha=0.1, color=COLORS[name])

    ax.set_ylim(0, 1)
    ax.set_title("Algorithm Performance Radar\n(Avg Normalized Metrics, Smaller = Better)",
                 fontsize=13, pad=20)
    ax.legend(loc='upper right', bbox_to_anchor=(1.35, 1.1), fontsize=9)
    plt.tight_layout()
    path = os.path.join(FIGURES_DIR, "v5_radar_chart.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ---- Figure 2: Score comparison bar chart ----
    fig, ax = plt.subplots(figsize=(14, 6))
    x = np.arange(len(ALGO_NAMES))
    width = 0.25

    phil_vals = [philosophy_scores[n] for n in ALGO_NAMES]
    opt_vals = [optimized_scores[n] for n in ALGO_NAMES]
    univ_vals = [universal_scores[n] for n in ALGO_NAMES]

    bars1 = ax.bar(x - width, phil_vals, width, label="Philosophy Weights",
                   color="#3498db", edgecolor="black", linewidth=0.5)
    bars2 = ax.bar(x, opt_vals, width, label="Optimized Weights",
                   color="#2ecc71", edgecolor="black", linewidth=0.5)
    bars3 = ax.bar(x + width, univ_vals, width, label="Universal Weights",
                   color="#e74c3c", edgecolor="black", linewidth=0.5)

    for bars in [bars1, bars2, bars3]:
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.005,
                    f'{height:.3f}', ha='center', va='bottom', fontsize=7)

    ax.set_ylabel("Composite Score (lower = better)")
    ax.set_title("V5 Multi-Objective Score Comparison")
    ax.set_xticks(x)
    ax.set_xticklabels(ALGO_NAMES, rotation=15, ha="right")
    ax.legend()
    ax.set_ylim(0, max(phil_vals + opt_vals + univ_vals) * 1.2)
    plt.tight_layout()
    path = os.path.join(FIGURES_DIR, "v5_score_comparison.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ---- Figure 3: Weight profiles — stacked bars ----
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    metric_labels = ["Total Completion", "Makespan", "Circulations"]
    metric_colors = ["#3498db", "#2ecc71", "#e74c3c"]

    for ax_idx, (title, weight_dict) in enumerate([
        ("Philosophy Weights", PHILOSOPHY_WEIGHTS),
        ("Grid-Search Optimized Weights", optimized_weights),
    ]):
        ax = axes[ax_idx]
        y_pos = np.arange(len(ALGO_NAMES))
        left = np.zeros(len(ALGO_NAMES))

        for m_idx, m_label in enumerate(metric_labels):
            vals = [weight_dict[n][m_idx] for n in ALGO_NAMES]
            ax.barh(y_pos, vals, left=left, label=m_label,
                    color=metric_colors[m_idx], edgecolor="black", linewidth=0.5)
            # Add weight text
            for i, v in enumerate(vals):
                if v >= 0.08:
                    ax.text(left[i] + v/2, i, f"{v:.2f}",
                            ha="center", va="center", fontsize=8, fontweight="bold")
            left += vals

        ax.set_yticks(y_pos)
        ax.set_yticklabels(ALGO_NAMES, fontsize=9)
        ax.set_xlabel("Weight")
        ax.set_title(title, fontsize=11)
        ax.set_xlim(0, 1)
        if ax_idx == 0:
            ax.legend(loc="lower right", fontsize=8)

    plt.tight_layout()
    path = os.path.join(FIGURES_DIR, "v5_weight_profiles.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ---- Figure 4: Pareto front (seed 777) ----
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    pairs = [
        (0, 1, "Total Completion Time", "Makespan"),
        (0, 2, "Total Completion Time", "Circulations"),
        (1, 2, "Makespan", "Circulations"),
    ]
    seed_data = all_results[SEED_V5]

    for ax_idx, (i, j, xlabel, ylabel) in enumerate(pairs):
        ax = axes[ax_idx]
        for name in ALGO_NAMES:
            metrics = extract_metrics(seed_data[name])
            ax.scatter(metrics[i], metrics[j], s=150, c=COLORS[name],
                       edgecolors="black", linewidth=1, label=name, zorder=5)
            ax.annotate(name[:8], (metrics[i], metrics[j]),
                        textcoords="offset points", xytext=(8, 8), fontsize=8)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(f"{xlabel} vs {ylabel}\n(seed={SEED_V5})")
        ax.grid(True, alpha=0.3)

    axes[0].legend(fontsize=7, loc="best")
    plt.tight_layout()
    path = os.path.join(FIGURES_DIR, "v5_pareto_front.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ---- Figure 5: Sensitivity boxplot under universal weights ----
    fig, ax = plt.subplots(figsize=(10, 6))
    box_data = []
    for name in ALGO_NAMES:
        scores = []
        for s in SEEDS:
            nm = all_normalized[s][name]
            scores.append(compute_composite_score(nm, universal_best_w))
        box_data.append(scores)

    bp = ax.boxplot(box_data, tick_labels=ALGO_NAMES,
                    patch_artist=True, vert=True)
    for patch, color in zip(bp["boxes"], COLOR_LIST):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    ax.set_ylabel("Composite Score (lower = better)")
    ax.set_title(f"V5 Sensitivity: Rank-Based Composite Scores\n"
                 f"({len(SEEDS)} seeds, universal weights=({universal_best_w[0]:.2f},"
                 f"{universal_best_w[1]:.2f},{universal_best_w[2]:.2f}))")
    ax.tick_params(axis="x", rotation=15)
    ax.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    path = os.path.join(FIGURES_DIR, "v5_sensitivity_boxplot.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ---- Figure 6: Weight heatmap for best algorithm ----
    fig, ax = plt.subplots(figsize=(10, 8))

    # For the universal best algorithm, show score as function of w1 and w2
    # (w3 = 1 - w1 - w2)
    w1_vals = sorted(set(r["w_total_comp"] for r in grid_search_rows))
    w2_vals = sorted(set(r["w_makespan"] for r in grid_search_rows))

    # Build lookup for best algo's scores
    score_lookup = {}
    for r in grid_search_rows:
        if r["algorithm"] == universal_best_algo:
            score_lookup[(r["w_total_comp"], r["w_makespan"])] = r["avg_score"]

    # Create scatter plot (w1, w2, color=score)
    scatter_w1 = []
    scatter_w2 = []
    scatter_scores = []
    for (w1, w2), score in score_lookup.items():
        scatter_w1.append(w1)
        scatter_w2.append(w2)
        scatter_scores.append(score)

    sc = ax.scatter(scatter_w1, scatter_w2, c=scatter_scores, cmap="RdYlGn_r",
                    s=40, edgecolors="none", alpha=0.8)
    plt.colorbar(sc, ax=ax, label="Composite Score (lower=better)")

    # Mark optimal point
    opt_w = optimized_weights[universal_best_algo]
    ax.scatter([opt_w[0]], [opt_w[1]], s=200, c="black", marker="*",
               zorder=10, label=f"Optimal ({opt_w[0]:.2f},{opt_w[1]:.2f},{opt_w[2]:.2f})")
    # Mark philosophy point
    phil_w = PHILOSOPHY_WEIGHTS[universal_best_algo]
    ax.scatter([phil_w[0]], [phil_w[1]], s=200, c="blue", marker="D",
               zorder=10, label=f"Philosophy ({phil_w[0]:.2f},{phil_w[1]:.2f},{phil_w[2]:.2f})")

    ax.set_xlabel("w_total_completion")
    ax.set_ylabel("w_makespan")
    ax.set_title(f"Weight Landscape for {universal_best_algo}\n"
                 f"(w_circulations = 1 - w_tc - w_ms)")
    ax.legend(fontsize=9)
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)

    # Draw boundary: w1 + w2 <= 1
    boundary_x = np.linspace(0, 1, 100)
    boundary_y = 1 - boundary_x
    ax.plot(boundary_x, boundary_y, 'k--', alpha=0.3, label="w1+w2=1 boundary")
    ax.fill_between(boundary_x, boundary_y, 0, alpha=0.05, color="gray")

    plt.tight_layout()
    path = os.path.join(FIGURES_DIR, "v5_weight_heatmap.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ---- Figure 7: V4 vs V5 comparison ----
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Left: V4 ranking (total completion time only)
    ax = axes[0]
    v4_avg_totals = {}
    for name in ALGO_NAMES:
        avg_tc = sum(all_results[s][name].total_completion_time for s in SEEDS) / len(SEEDS)
        v4_avg_totals[name] = avg_tc
    v4_ranked = sorted(ALGO_NAMES, key=lambda n: v4_avg_totals[n])
    v4_vals = [v4_avg_totals[n] for n in v4_ranked]
    v4_colors = [COLORS[n] for n in v4_ranked]

    bars = ax.barh(v4_ranked, v4_vals, color=v4_colors, edgecolor="black", linewidth=0.5)
    for bar, val in zip(bars, v4_vals):
        ax.text(bar.get_width() + 5, bar.get_y() + bar.get_height()/2,
                f"{val:.0f}s", va="center", fontsize=9)
    ax.set_xlabel("Avg Total Completion Time (s)")
    ax.set_title("V4 Ranking\n(Single Metric: Total Completion Time)")

    # Right: V5 ranking (universal composite score)
    ax = axes[1]
    v5_ranked = sorted(ALGO_NAMES, key=lambda n: universal_scores[n])
    v5_vals = [universal_scores[n] for n in v5_ranked]
    v5_colors = [COLORS[n] for n in v5_ranked]

    bars = ax.barh(v5_ranked, v5_vals, color=v5_colors, edgecolor="black", linewidth=0.5)
    for bar, val in zip(bars, v5_vals):
        ax.text(bar.get_width() + 0.005, bar.get_y() + bar.get_height()/2,
                f"{val:.4f}", va="center", fontsize=9)
    ax.set_xlabel("Avg Composite Score (lower = better)")
    ax.set_title(f"V5 Ranking\n(Multi-Objective: weights=({universal_best_w[0]:.2f},"
                 f"{universal_best_w[1]:.2f},{universal_best_w[2]:.2f}))")

    plt.tight_layout()
    path = os.path.join(FIGURES_DIR, "v5_v4_vs_v5.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 10: Output files
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[10/11] Saving output files...")

    # Raw metrics CSV
    raw_path = os.path.join(RESULTS_DIR, "v5_raw_metrics.csv")
    with open(raw_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["seed", "algorithm", "total_completion_time", "makespan",
                          "circulations"])
        for s in SEEDS:
            for name in ALGO_NAMES:
                r = all_results[s][name]
                writer.writerow([s, name, f"{r.total_completion_time:.2f}",
                                 f"{r.makespan:.2f}", r.total_circulations])
    print(f"  Saved: {raw_path}")

    # Normalized metrics CSV (both methods for comparison)
    norm_path = os.path.join(RESULTS_DIR, "v5_normalized_metrics.csv")
    with open(norm_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["seed", "algorithm", "method",
                          "norm_total_comp", "norm_makespan", "norm_circulations"])
        for s in SEEDS:
            for name in ALGO_NAMES:
                nm = all_normalized[s][name]
                writer.writerow([s, name, "rank",
                                 f"{nm[0]:.6f}", f"{nm[1]:.6f}", f"{nm[2]:.6f}"])
                mm = all_normalized_minmax[s][name]
                writer.writerow([s, name, "minmax",
                                 f"{mm[0]:.6f}", f"{mm[1]:.6f}", f"{mm[2]:.6f}"])
    print(f"  Saved: {norm_path}")

    # Grid search CSV (top results per algorithm — full grid too large)
    grid_path = os.path.join(RESULTS_DIR, "v5_grid_search.csv")
    with open(grid_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["algorithm", "w_total_comp", "w_makespan", "w_circulations",
                          "avg_score", "type"])
        # Philosophy weights
        for name in ALGO_NAMES:
            w = PHILOSOPHY_WEIGHTS[name]
            writer.writerow([name, w[0], w[1], w[2],
                             f"{philosophy_scores[name]:.6f}", "philosophy"])
        # Optimized weights
        for name in ALGO_NAMES:
            w = optimized_weights[name]
            writer.writerow([name, w[0], w[1], w[2],
                             f"{optimized_scores[name]:.6f}", "optimized"])
        # Universal weights
        for name in ALGO_NAMES:
            writer.writerow([name, universal_best_w[0], universal_best_w[1],
                             universal_best_w[2],
                             f"{universal_scores[name]:.6f}", "universal"])
    print(f"  Saved: {grid_path}")

    # Comparison CSV
    comp_path = os.path.join(RESULTS_DIR, "v5_comparison.csv")
    with open(comp_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "algorithm", "philosophy_weights", "philosophy_score",
            "optimized_weights", "optimized_score",
            "universal_weights", "universal_score", "best_profile"])
        writer.writeheader()
        for row in comparison_rows:
            writer.writerow(row)
    print(f"  Saved: {comp_path}")

    # Summary CSV
    summary_path = os.path.join(RESULTS_DIR, "v5_summary.csv")
    with open(summary_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value"])
        writer.writerow(["v4_winner", v4_winner])
        writer.writerow(["v4_winner_wins", v4_win_counts[v4_winner]])
        writer.writerow(["v5_winner", v5_winner])
        writer.writerow(["v5_winner_wins_universal", win_counts["Universal"][v5_winner]])
        writer.writerow(["universal_weights",
                          f"({universal_best_w[0]:.2f},{universal_best_w[1]:.2f},"
                          f"{universal_best_w[2]:.2f})"])
        writer.writerow(["universal_best_avg_score", f"{universal_best_avg:.6f}"])
        writer.writerow(["num_seeds", len(SEEDS)])
        writer.writerow(["grid_size", len(weight_grid)])
        winner_changed = "YES" if v4_winner != v5_winner else "NO"
        writer.writerow(["winner_changed_v4_to_v5", winner_changed])
    print(f"  Saved: {summary_path}")

    # Order CSV + tote schedule for V5 best algorithm (seed 777)
    sim = ConveyorSimulator(**SIM_PARAMS)
    orders_777, totes_777, params_777 = generate_data(
        seed=SEED_V5, n_orders=SMALL_ORDERS,
        n_totes=SMALL_TOTES, n_itemtypes=SMALL_ITEMTYPES
    )
    best_algo_fn = ALL_ALGORITHMS_CONTINUOUS[v5_winner]
    best_lane_queues = best_algo_fn(orders_777)
    best_result_777 = all_results[SEED_V5][v5_winner]

    # Generated data CSVs
    save_csvs(orders_777, DATA_DIR)
    print(f"  Saved generated data to: {DATA_DIR}/")

    # Order CSV
    safe_name = v5_winner.lower().replace(' ', '_').replace('-', '_')
    order_csv_path = os.path.join(CSV_DIR, f"v5_{safe_name}_seed{SEED_V5}.csv")
    save_order_csv(best_lane_queues, orders_777, order_csv_path)
    print(f"  Saved order CSV: {order_csv_path}")

    # Tote schedule CSV
    tote_csv_path = os.path.join(CSV_DIR, f"tote_schedule_{safe_name}.csv")
    tote_order = best_result_777.tote_load_order
    save_tote_schedule(tote_order, totes_777, orders_777, tote_csv_path)
    print(f"  Saved tote schedule: {tote_csv_path}")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 11: Summary
    # ──────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("V5 MULTI-OBJECTIVE OPTIMIZATION — SUMMARY")
    print("=" * 80)

    print(f"\n  Configuration:")
    print(f"    Instance: {SMALL_ORDERS} orders, {SMALL_TOTES} totes, "
          f"{SMALL_ITEMTYPES} item types")
    print(f"    Seeds tested: {len(SEEDS)}")
    print(f"    Weight grid: {len(weight_grid)} combinations (step=0.05)")

    print(f"\n  V4 Result (single metric: total completion time):")
    print(f"    Winner: {v4_winner}")
    print(f"    Avg total completion: {v4_avg_totals[v4_winner]:.0f}s")
    print(f"    Wins: {v4_win_counts[v4_winner]}/{len(SEEDS)} seeds")

    print(f"\n  V5 Result (multi-objective: rank-based composite score):")
    print(f"    Winner: {v5_winner}")
    print(f"    Universal weights: ({universal_best_w[0]:.2f}, "
          f"{universal_best_w[1]:.2f}, {universal_best_w[2]:.2f})")
    print(f"    Avg composite score: {universal_best_avg:.4f}")
    print(f"    Wins: {win_counts['Universal'][v5_winner]}/{len(SEEDS)} seeds")
    print(f"    Normalization: rank-based (handles ties, no corner collapse)")
    print(f"    Weight floor: 0.10 (every metric always matters)")

    if v4_winner == v5_winner:
        print(f"\n  Key Insight: Multi-objective optimization CONFIRMS {v4_winner}")
        print(f"    as the best algorithm. It excels even when we account for")
        print(f"    makespan fairness and circulation waste.")
    else:
        print(f"\n  Key Insight: Multi-objective optimization CHANGES the winner!")
        print(f"    V4 picked {v4_winner} (best total time).")
        print(f"    V5 picks {v5_winner} (best composite considering fairness & waste).")
        print(f"    This shows that optimizing a single metric can miss important")
        print(f"    trade-offs in operational performance.")

    print(f"\n  Grid Search Validation:")
    for name in ALGO_NAMES:
        ow = optimized_weights[name]
        pw = PHILOSOPHY_WEIGHTS[name]
        dominant_idx = max(range(3), key=lambda i: ow[i])
        expected_idx = max(range(3), key=lambda i: pw[i])
        metric_names = ["total_comp", "makespan", "circulations"]
        match = "CONFIRMED" if dominant_idx == expected_idx else "SHIFTED"
        print(f"    {name:<25}: optimized weights emphasize "
              f"{metric_names[dominant_idx]} — {match}")

    print(f"\n  Output files saved to: {RESULTS_DIR}/")
    print(f"  Figures saved to: {FIGURES_DIR}/ (7 plots)")
    print("=" * 80)


if __name__ == "__main__":
    main()

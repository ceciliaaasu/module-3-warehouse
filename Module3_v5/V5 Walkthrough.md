# Module 3 — V5 Multi-Objective Optimization Walkthrough

## For the Team: What This Is and How to Read It

This document explains everything V5 does in plain language. No jargon. If you can read a spreadsheet, you can follow this.

---

## Quick Summary (30 seconds)

V4 picked the best algorithm by asking one question: "Which finishes all orders fastest?"
V5 asks three questions at once and blends them into a single score:

1. **Total completion time** — how fast do all orders finish overall?
2. **Makespan** — how long does the slowest single order have to wait?
3. **Circulations** — how many items go around the conveyor loop without being picked up?

**Result:** The winner changed. V4 said Random Baseline. V5 says **Wave Batching** — because it's consistently good at all three things, not just one.

---

## Why We Did This

Imagine you're picking a car. V4 only looked at price. But you also care about safety and fuel economy. A cheap car with terrible safety isn't really the "best." V5 looks at all three factors and finds the car that's best overall.

In our conveyor system:
- A fast algorithm that wastes tons of conveyor laps isn't great.
- A fair algorithm where no order waits forever but takes ages overall isn't great either.
- We want the algorithm that balances all three.

---

## The Five Algorithms (Quick Recap)

| # | Algorithm | Strategy | Good At |
|---|-----------|----------|---------|
| 0 | Random Baseline | Shuffle orders randomly | Nothing specific — it's just a benchmark |
| 1 | Shortest Order First (SOF) | Small orders go first | Total completion time (speed) |
| 2 | Load Balanced | Spread work evenly across lanes | Makespan (fairness) |
| 3 | Tote-Aware Clustering | Group orders sharing totes | Fewer circulations (less waste) |
| 4 | Wave Batching | Pair small + large orders, smallest groups first | Balanced performance |

---

## How V5 Works — Step by Step

### Step 1: Run Everything

We run all 5 algorithms on 10 different random datasets (seeds). Each seed creates a different set of orders, so we're not just testing on one lucky scenario. We use the same small instance as V4: 6 orders, 8 totes, 8 item types.

This gives us 5 algorithms x 10 seeds = 50 simulation runs. For each run we record:
- Total completion time (seconds)
- Makespan (seconds)
- Total circulations (count)

### Step 2: Normalize the Numbers

The three metrics are on completely different scales. Total completion time is in the hundreds (e.g., 560s). Circulations might be 0 or 3. You can't just add them together — the time would dominate.

**Solution: Rank-based normalization.**

For each seed, we rank the 5 algorithms 1st through 5th on each metric:
- 1st place (best) gets a score of 0.00
- 5th place (worst) gets a score of 1.00
- Ties get the average rank (e.g., two algorithms tied for 1st both get 0.125)

This puts everything on the same 0-to-1 scale. Lower is always better.

**Why not just use percentages (min-max)?** We tried that first. The problem: when 4 out of 5 algorithms tie on circulations (all have 0), min-max gives them all 0.00, which makes the metric useless. Ranks handle ties much better.

### Step 3: Assign Weights

We combine the three normalized scores into one number:

```
composite score = w1 x rank_total_time + w2 x rank_makespan + w3 x rank_circulations
```

The weights (w1, w2, w3) add up to 1.0 and say "how much do I care about each goal?"

**Philosophy weights** — each algorithm gets weights matching what it was designed for:

| Algorithm | w_time | w_fairness | w_waste | Reasoning |
|-----------|--------|------------|---------|-----------|
| Random Baseline | 0.34 | 0.33 | 0.33 | No preference — equal split |
| Shortest Order First | 0.70 | 0.15 | 0.15 | Designed for speed |
| Load Balanced | 0.15 | 0.70 | 0.15 | Designed for fairness |
| Tote-Aware Clustering | 0.15 | 0.15 | 0.70 | Designed to reduce waste |
| Wave Batching | 0.40 | 0.35 | 0.25 | Designed to be balanced |

### Step 4: Grid Search

We don't just guess the best weights. We systematically try **120 different weight combinations** (every combo from 0.10 to 0.80 in steps of 0.05).

**Important rule: every weight must be at least 0.10.** This means no metric is ever completely ignored. You can't say "I care 100% about speed and 0% about fairness." That's not multi-objective — that's just single-objective with extra steps.

For each of the 120 weight combos, we score all 5 algorithms on all 10 seeds and count: **which algorithm wins the most seeds?**

### Step 5: Pick the Winner

The weight combo where one algorithm wins the most seeds becomes the **universal weights**. The algorithm that wins becomes the **V5 winner**.

---

## The Results

### Universal Best Weights: (0.10, 0.70, 0.20)

This means the data says:
- 10% weight on total completion time
- **70% weight on makespan (fairness)**
- 20% weight on circulations (waste)

Translation: **fairness matters most.** You don't want any single order stuck waiting forever while others fly through.

### V5 Winner: Wave Batching (5 out of 10 seeds)

| | V4 (old) | V5 (new) |
|---|---|---|
| **Winner** | Random Baseline | **Wave Batching** |
| **Seeds won** | 3/10 | **5/10** |
| **What it looked at** | Speed only | Speed + fairness + waste |
| **Method** | Lowest total time | Most seed wins under best weights |

### All Algorithms Ranked (V5 Universal Weights)

| Rank | Algorithm | Avg Score | Why |
|------|-----------|-----------|-----|
| 1 | **Wave Batching** | 0.360 | Great makespan, decent speed, low waste |
| 2 | Random Baseline | 0.420 | Surprisingly decent at everything |
| 3 | Tote-Aware Clustering | 0.470 | Best at waste, but weaker on fairness |
| 4 | Shortest Order First | 0.480 | Fast overall, but some orders wait long |
| 5 | Load Balanced | 0.770 | Supposed to be fair, but worst in practice |

### Grid Search Validation

We also checked: do the grid-search-optimized weights match each algorithm's philosophy?

| Algorithm | Philosophy Says | Grid Search Found | Match? |
|-----------|----------------|-------------------|--------|
| Random Baseline | Equal | Makespan heavy (0.15, 0.75, 0.10) | Shifted |
| Shortest Order First | Speed heavy | Speed heavy (0.80, 0.10, 0.10) | Confirmed |
| Load Balanced | Fairness heavy | Waste heavy (0.10, 0.10, 0.80) | Shifted |
| Tote-Aware Clustering | Waste heavy | Speed heavy (0.80, 0.10, 0.10) | Shifted |
| Wave Batching | Balanced | Fairness heavy (0.10, 0.80, 0.10) | Shifted |

SOF was confirmed — it really is best when you only care about speed. The others shifted, meaning the data found a different sweet spot than the algorithm was designed for. This is useful information.

---

## The 7 Figures (What Each One Shows)

All saved in `results/figures/`.

| # | File | What It Shows |
|---|------|--------------|
| 1 | `v5_radar_chart.png` | Spider/radar plot of each algorithm's average rank on all 3 metrics. Smaller area = better overall. |
| 2 | `v5_score_comparison.png` | Grouped bar chart comparing each algorithm's composite score under philosophy, optimized, and universal weights. |
| 3 | `v5_weight_profiles.png` | Stacked horizontal bars showing the weight split (time/fairness/waste) for philosophy vs. grid-search-optimized weights. |
| 4 | `v5_pareto_front.png` | Three scatter plots for seed 777 showing trade-offs between each pair of metrics. Shows which algorithms are Pareto-efficient. |
| 5 | `v5_sensitivity_boxplot.png` | Box plot showing how each algorithm's composite score varies across the 10 seeds. Narrow box = consistent performer. |
| 6 | `v5_weight_heatmap.png` | Color map showing how the best algorithm's score changes as you move through the weight space. Helps visualize where the optimal region is. |
| 7 | `v5_v4_vs_v5.png` | Side-by-side: V4 ranking (speed only) vs V5 ranking (multi-objective). Shows how the winner changed. |

---

## The Output Files

All in `results/`.

| File | What's In It |
|------|-------------|
| `v5_raw_metrics.csv` | Raw simulation results: total_completion_time, makespan, circulations for all 5 algorithms x 10 seeds. |
| `v5_normalized_metrics.csv` | Rank-based and min-max normalized versions of those metrics. |
| `v5_grid_search.csv` | The philosophy, optimized, and universal weights + scores for each algorithm. |
| `v5_comparison.csv` | Summary table: each algorithm's score under all three weight profiles. |
| `v5_summary.csv` | One-row-per-fact summary (V4 winner, V5 winner, weights, etc.). |
| `input_csvs/v5_wave_batching_seed777.csv` | The actual conveyor input CSV for the V5 winner (what you'd feed to the physical belt). |
| `input_csvs/tote_schedule_wave_batching.csv` | Tote loading order for the operator. |
| `generated_data/*.csv` | The randomly generated order/tote data used (for reproducibility). |

---

## How to Run It

```bash
cd Module3_v5
python3 analysis_v5.py
```

Takes about 5 seconds. Produces all tables in the terminal, saves all 7 figures and all CSVs. No arguments needed.

Dependencies (already installed): numpy, matplotlib, and the four shared modules (algorithms.py, conveyor_sim.py, data_pipeline.py, generate_input.py) which are copied into this folder.

---

## Key Takeaway

V4 asked: "What's fastest?" and got a noisy answer (Random Baseline, barely winning 3/10).

V5 asked: "What's best when we care about speed, fairness, AND waste?" and got a clearer answer: **Wave Batching wins 5/10 seeds** with universal weights (0.10, 0.70, 0.20).

The multi-objective approach didn't just change the winner — it gave us a **more confident** winner with a **majority** of seed wins instead of a shaky plurality.

---

## Folder Structure

```
Module3_v5/
    V5 Walkthrough.md          <-- You are here
    analysis_v5.py              <-- The main script (run this)
    algorithms.py               <-- 5 heuristic algorithms
    conveyor_sim.py             <-- Conveyor belt simulator
    data_pipeline.py            <-- Random order/tote generator
    generate_input.py           <-- CSV output helpers
    results/
        v5_raw_metrics.csv
        v5_normalized_metrics.csv
        v5_grid_search.csv
        v5_comparison.csv
        v5_summary.csv
        figures/
            v5_radar_chart.png
            v5_score_comparison.png
            v5_weight_profiles.png
            v5_pareto_front.png
            v5_sensitivity_boxplot.png
            v5_weight_heatmap.png
            v5_v4_vs_v5.png
        generated_data/
            order_itemtypes.csv
            order_quantities.csv
            orders_totes.csv
        input_csvs/
            v5_wave_batching_seed777.csv
            tote_schedule_wave_batching.csv
```

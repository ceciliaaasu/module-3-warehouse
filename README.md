# MSE 433 — Module 3: Warehousing Conveyor Simulation
## Group 6 | Multi-Objective Algorithm Optimization (V5)

---

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [Physical System](#2-physical-system)
3. [Repository Structure](#3-repository-structure)
4. [Module Descriptions](#4-module-descriptions)
5. [The Five Algorithms](#5-the-five-algorithms)
6. [Objective Function](#6-objective-function)
7. [Sensitivity Analysis — Full Methodology](#7-sensitivity-analysis--full-methodology)
8. [How to Run](#8-how-to-run)
9. [Output Files Reference](#9-output-files-reference)
10. [Key Results](#10-key-results)

---

## 1. Project Overview

This project simulates and optimizes a 4-lane conveyor belt order-fulfillment system. Five
scheduling algorithms are implemented and evaluated against three competing performance
objectives: throughput efficiency, fairness, and waste reduction.

The central question is: **which algorithm performs best when we care about all three
objectives simultaneously, not just the fastest average time?**

V5 introduces a **weighted composite scoring system** and a **sensitivity analysis** over
120 weight combinations to answer this rigorously across multiple dataset sizes.

**Final answer: Wave Batching is the best overall algorithm** under multi-objective evaluation,
winning 5 out of 10 randomly generated test scenarios. This overturns the V4 single-metric
result (which selected Random Baseline).

---

## 2. Physical System

The warehouse uses a **4-conveyor circulation loop**:

```
         ┌──────────────────────────────┐
         │         CONVEYOR LOOP        │
  LOAD ──► Lane 0 ──► Lane 1 ──► Lane 2 ──► Lane 3 ──┐
         │  Scanner    Scanner   Scanner   Scanner     │
         │  Diverter   Diverter  Diverter  Diverter    │
         └────────────────────────────────────────────┘
                              ▲ items circulate if not diverted
```

- Items are loaded onto the belt from totes
- A scanner at each lane detects item shape
- A pneumatic arm diverts matching items into the lane's packing bin
- Items that do not match at any lane **circulate** back around the loop
- An order is complete when all its required items have been diverted

**Fixed simulation parameters (static throughout all analysis):**

| Parameter | Value | Description |
|---|---|---|
| `loop_time` | 40.0 s | Time for one full loop of the belt |
| `divert_time` | 5.0 s | Scanner + pneumatic arm response time |
| `load_interval` | 3.0 s | Time between loading successive items |
| `num_lanes` | 4 | Number of conveyor lanes |
| `station_spacing` | 10.0 s | `loop_time / num_lanes` — time between stations |

---

## 3. Repository Structure

```
Module3_v5/
│
├── README.md                        ← This file
├── V5 Walkthrough.md                ← Plain-language team summary
│
├── analysis_v5.py                   ← Main analysis script (run this)
├── algorithms.py                    ← 5 scheduling algorithms
├── conveyor_sim.py                  ← Discrete-event conveyor simulator
├── data_pipeline.py                 ← Random order/tote data generator
├── generate_input.py                ← Converts output to conveyor CSV format
├── plot_weight_boxplot.py           ← Standalone sensitivity box plot generator
│
├── input_csvs/                      ← Pre-generated conveyor input files
│   ├── grp6_optA_randombaseline.csv
│   ├── grp6_optA_randombaseline_toteschedule.csv
│   ├── grp6_optB_shortestorderfirst.csv
│   ├── grp6_optB_shortestorderfirst_toteschedule.csv
│   ├── grp6_optC_loadbalanced.csv
│   ├── grp6_optC_loadbalanced_toteschedule.csv
│   ├── grp6_optD_toteawareclustering.csv
│   ├── grp6_optD_toteawareclustering_toteschedule.csv
│   ├── grp6_optE_wavebatching.csv
│   └── grp6_optE_wavebatching_toteschedule.csv
│
├── medium data/                     ← Medium-scale instance data
│   ├── order_itemtypes.csv
│   ├── order_quantities.csv
│   └── orders_totes.csv
│
└── results/
    ├── grp6_objective_function_results.csv   ← Group 6 scored results (3 sizes)
    ├── sensitivity_analysis_report.md        ← Detailed methodology report
    ├── v5_raw_metrics.csv
    ├── v5_normalized_metrics.csv
    ├── v5_grid_search.csv
    ├── v5_comparison.csv
    ├── v5_summary.csv
    ├── figures/
    │   ├── v5_radar_chart.png
    │   ├── v5_score_comparison.png
    │   ├── v5_weight_profiles.png
    │   ├── v5_pareto_front.png
    │   ├── v5_sensitivity_boxplot.png
    │   ├── v5_weight_heatmap.png
    │   ├── v5_v4_vs_v5.png
    │   └── weight_sensitivity_boxplot.png    ← Cross-dataset sensitivity plot
    ├── generated_data/
    │   ├── order_itemtypes.csv
    │   ├── order_quantities.csv
    │   └── orders_totes.csv
    └── input_csvs/
        ├── v5_wave_batching_seed777.csv
        └── tote_schedule_wave_batching.csv
```

---

## 4. Module Descriptions

### `data_pipeline.py`
Generates randomized warehouse scenarios. Each call to `generate_data(seed)` produces:
- A list of `Order` objects, each containing items (shape type + quantity + tote ID)
- A list of `Tote` objects, each holding items for one or more orders
- Orders require 1–4 item types; item quantities are randomized per seed

The `seed` parameter fully determines the scenario — the same seed always produces the
same orders and totes. Supports size overrides (`n_orders`, `n_totes`, `n_itemtypes`).

**Data structures:**
- `Order`: has `order_id`, `items` list, computed `total_items`, `tote_set`, `shape_counts()`
- `Tote`: has `tote_id`, `contents` list of `(order_id, item_type, quantity)` tuples
- `OrderItem`: links a specific item type and quantity to the tote that holds it

---

### `conveyor_sim.py`
Discrete-event simulation of the physical conveyor belt. Two simulation modes:

**`simulate_wave()`** — simulates one wave (up to 4 orders, one per lane) at a time.
Used by the wave-based algorithm variants.

**`simulate_tote_ordered()`** — simulates continuous operation where lanes have queues of
orders and totes are loaded in a scheduled order. Used by V5 analysis.

For each simulation run, returns a `SimResult` containing:
- `total_completion_time` — sum of all order finish times (seconds)
- `makespan` — time when the last order finishes (seconds)
- `total_circulations` — count of items that looped without being caught
- `order_completions` — per-order finish times
- `lane_utilization` — fraction of makespan each lane was actively processing
- `tote_load_order` — the sequence in which totes were physically loaded

---

### `algorithms.py`
Implements all five scheduling algorithms in both wave-mode and continuous-mode variants.
Also contains `compute_tote_order()` — the shared tote scheduling logic used after any
algorithm determines lane queues (see Section 5 for full algorithm descriptions).

---

### `generate_input.py`
Converts algorithm output into the two CSV formats required by the physical conveyor system:

**Order input CSV** (`save_order_csv`): rows are `[conv_num, circle, pentagon, ..., cross]`
— one row per lane per wave, specifying how many of each shape that lane needs.

**Tote schedule CSV** (`save_tote_schedule`): rows list totes in loading order with their
contents — the physical document operators use to load totes onto the belt.

---

### `analysis_v5.py`
The main analysis script. Runs all 11 steps of the multi-objective sensitivity analysis
(see Section 7). Produces all output CSVs and 7 publication-quality figures.

---

### `plot_weight_boxplot.py`
Standalone script that generates `weight_sensitivity_boxplot.png` using the pre-computed
`grp6_objective_function_results.csv`. Shows composite score distributions across Small,
Medium, and Large dataset sizes for three weight profiles (Random, Optimized, Universal).

---

## 5. The Five Algorithms

All algorithms output **lane queues**: an ordered assignment of orders to the 4 conveyor
lanes, determining which order each lane processes and in what sequence.

### Algorithm A — Random Baseline
Shuffles all orders randomly (fixed seed=42) and distributes them to lanes via round-robin.
No optimization logic. Serves as the performance lower-bound benchmark.

**Tote order consequence:** Random — totes are scheduled based on whichever orders happen
to fall at the front of each lane queue after shuffling.

---

### Algorithm B — Shortest Order First (SOF)
Sorts all orders by `total_items` **ascending** — the SPT (Shortest Processing Time) rule
from classical scheduling theory. Smallest orders are dispatched first so they complete
quickly, reducing cumulative waiting time across all orders.

**Why this targets w₁ (Total Completion Time):** Each early-finishing order stops
accumulating time in the sum, so front-loading small orders minimises the total.

**Tote order consequence:** Totes serving small orders are prioritised first.

---

### Algorithm C — Load Balanced
Sorts orders **largest first**, then uses a greedy minimum-load assignment: each order is
assigned to whichever lane currently has the least total work outstanding. This is the
LPT (Longest Processing Time) rule applied to multi-machine scheduling.

**Why this targets w₂ (Makespan):** By preventing any single lane from accumulating
disproportionate work, all lanes finish at roughly the same time — minimising the last
order's wait.

**Tote order consequence:** Large orders get totes loaded early; smaller orders' totes
follow. This can increase total completion time (explaining its high w₁ scores).

---

### Algorithm D — Tote-Aware Clustering
Groups orders that share totes into the same processing group. Uses greedy overlap scoring:
starting from an unassigned order, it iteratively adds whichever remaining order shares the
most totes with the current group (up to 4 per group). Within each group, load-balancing
is applied for lane assignment.

**Why this targets w₃ (Circulations):** When orders in the same group share totes, those
totes serve multiple orders in one pass — reducing how many times totes must re-enter the
belt to satisfy items needed in later waves.

**Tote order consequence:** Totes with contents spanning multiple co-grouped orders are
prioritised, as they are needed earliest across the group.

---

### Algorithm E — Wave Batching
Uses a two-pointer pairing strategy: sorts orders by size, then pairs the smallest with the
largest, second-smallest with second-largest, etc. Each pair/group is then sorted so the
group with the fewest total items goes first. Within each group, load-balancing assigns
orders to lanes.

**Why this targets w₁ + w₂ (mix):** Pairing small with large creates internally balanced
groups (like Load Balanced), while ordering groups smallest-first means the belt is not
held up by a large wave early on (like Shortest Order First). The two-pointer approach
minimises both overall time and within-wave lane imbalance.

**Tote order consequence:** Totes are scheduled to reflect the paired-group order — early
groups' totes load first regardless of individual order size.

---

### Shared Tote Scheduling (`compute_tote_order`)

After any algorithm produces lane queues, totes are scheduled using this rule:
1. For each tote, find the **earliest queue position** of any order it serves
2. Among totes tied on earliest position, prioritise the one with the **most items** at that position
3. Final tote load order: sort by `(earliest_position ASC, active_items DESC)`

This ensures totes are physically loaded onto the belt in the order they will be needed,
minimising idle wait time between tote loads.

---

## 6. Objective Function

```
score = w₁ × norm(Total Completion Time)
      + w₂ × norm(Makespan)
      + w₃ × norm(Circulations)

where  w₁ + w₂ + w₃ = 1.0,  each wᵢ ≥ 0.10
```

**Lower score = better performance.**

| Weight | Metric | Operational Meaning |
|---|---|---|
| w₁ | Total Completion Time | Sum of all order finish times. Penalises slow average throughput. |
| w₂ | Makespan | Time until the last order finishes. Penalises unfairness — one order waiting excessively. |
| w₃ | Circulations | Items looping the belt without diversion. Penalises wasted conveyor capacity. |

**Normalization:** Before applying weights, each metric is scaled to [0, 1] using
**rank-based normalization** (not min-max). Algorithms are ranked 1–5 per metric per
instance; rank 1 (best) → 0.0, rank 5 (worst) → 1.0. Ties receive the average of their
tied rank positions. Rank-based normalization is used because min-max collapses when
multiple algorithms tie at the minimum value.

---

## 7. Sensitivity Analysis — Full Methodology

The sensitivity analysis answers: *does weight choice change which algorithm wins, and how
sensitive is each algorithm's ranking to the weights used?*

### Step 1 — Data Generation (Dynamic)
`generate_data(seed)` is called for each of 10 seeds:
`[777, 42, 100, 200, 612, 888, 999, 1111, 2025, 2026]`

Each seed produces a distinct warehouse instance (different order sizes, different
item-to-tote assignments). All 5 algorithms are run on every seed — **50 total simulation
runs**. This tests whether results hold across varied problem instances, not just one
scenario.

Instance size (static): 6 orders, 8 totes, 8 item types maximum.

### Step 2 — Metric Extraction (per run)
Each `SimResult` yields three values:
- `result.total_completion_time`
- `result.makespan`
- `result.total_circulations`

### Step 3 — Rank-Based Normalization (per seed)
Within each seed, rank all 5 algorithms 1–5 on each metric. Scale to [0, 1]:
```
normalized_rank = (rank − 1) / (N − 1)   where N = 5
```
Normalization is done per-seed so each algorithm is compared against its competition on
the same problem instance — not against algorithms on different instances.

### Step 4 — Weight Grid Generation (static structure, dynamic search)
All weight combinations `(w₁, w₂, w₃)` satisfying:
- `w₁ + w₂ + w₃ = 1.0`
- Each `wᵢ ≥ 0.10` (floor — no metric is ever fully ignored)
- Step size = 0.05

This produces **120 combinations**.

### Step 5 — Composite Score Computation
For each of the 120 weight combinations × 5 algorithms × 10 seeds:
```python
score = w1 * norm_total_comp + w2 * norm_makespan + w3 * norm_circulations
```
Scores are averaged across seeds per (algorithm, weight combo).

### Step 6 — Per-Algorithm Optimal Weights
For each algorithm, the weight combo producing the **lowest average composite score**
across 10 seeds is its "optimized weight." These are the weights under which each
algorithm performs best when judged by the data.

### Step 7 — Universal Best Weights
For each weight combo, count how many of the 10 seeds each algorithm wins (has lowest
composite score). The weight combo where the dominant algorithm wins the most seeds →
**universal best weights**. This represents the most robust weight profile for overall ranking.

Result: **(0.10, 0.70, 0.20)** — makespan-heavy. Makespan is the most discriminating
metric: algorithms cluster closely on total completion time but spread apart on makespan,
so makespan-heavy weights produce cleaner, more consistent rankings.

### Step 8 — Cross-Dataset Validation (grp6 results)
`grp6_objective_function_results.csv` contains results from three dataset sizes:
- **Small**: 6 orders, 4 totes
- **Medium**: 10 orders, 8 totes
- **Large**: 25 orders, 19 totes

These use min-max normalization within each dataset size. The box plot
(`weight_sensitivity_boxplot.png`) applies the three weight profiles to this data,
showing how robust each weight choice is when problem scale changes.

### Static vs. Dynamic Variables Summary

| Variable | Value | Type |
|---|---|---|
| `loop_time` | 40.0 s | **Static** |
| `divert_time` | 5.0 s | **Static** |
| `load_interval` | 3.0 s | **Static** |
| `NUM_LANES` | 4 | **Static** |
| `n_orders` | 6 | **Static** (V5 main analysis) |
| `n_totes` | 8 | **Static** (V5 main analysis) |
| `n_itemtypes` | 8 | **Static** |
| `weight_floor` | 0.10 | **Static** |
| `weight_step` | 0.05 | **Static** |
| `seed` | 10 values | **Dynamic** — varies problem instance |
| `algorithm` | 5 algorithms | **Dynamic** — all tested per seed |
| `weights (w₁,w₂,w₃)` | 120 combos | **Dynamic** — grid searched |

---

## 8. How to Run

### Full sensitivity analysis (V5):
```bash
cd Module3_v5
python analysis_v5.py
```
Runtime: ~5 seconds. Produces terminal output, 7 figures, and 5 CSVs.

### Weight sensitivity box plot only:
```bash
cd Module3_v5
python plot_weight_boxplot.py
```
Reads from pre-generated `results/grp6_objective_function_results.csv`. No simulation
re-run needed. Produces `results/figures/weight_sensitivity_boxplot.png`.

### Dependencies:
```
numpy
matplotlib
```
All other imports (`algorithms`, `conveyor_sim`, `data_pipeline`, `generate_input`) are
local modules in the same directory.

---

## 9. Output Files Reference

### CSVs (in `results/`)

| File | Contents |
|---|---|
| `v5_raw_metrics.csv` | Raw simulation output: total_completion_time, makespan, circulations for all 5 algorithms × 10 seeds |
| `v5_normalized_metrics.csv` | Both rank-based and min-max normalized metrics for all seeds — use `method=rank` rows for analysis |
| `v5_grid_search.csv` | Philosophy, optimized, and universal weights with their composite scores per algorithm |
| `v5_comparison.csv` | Side-by-side: each algorithm's score under all three weight profiles and which profile is best |
| `v5_summary.csv` | Single-value facts: V4 winner, V5 winner, universal weights, grid size, etc. |
| `grp6_objective_function_results.csv` | Group 6 results across Small/Medium/Large: raw metrics, normalized metrics, and composite scores using design-intent weights |

### Input CSVs (in `input_csvs/` and `results/input_csvs/`)

| File | Contents |
|---|---|
| `grp6_optX_<algorithm>.csv` | Conveyor order input for each algorithm — feed directly to the physical belt controller |
| `grp6_optX_<algorithm>_toteschedule.csv` | Operator tote loading schedule for each algorithm |
| `v5_wave_batching_seed777.csv` | V5 winner (Wave Batching) order input for seed 777 |
| `tote_schedule_wave_batching.csv` | V5 winner tote schedule for seed 777 |

### Figures (in `results/figures/`)

| File | Description |
|---|---|
| `v5_radar_chart.png` | Spider plot of average normalized metrics per algorithm — smaller area = better overall |
| `v5_score_comparison.png` | Grouped bar chart: composite score under philosophy vs. optimized vs. universal weights |
| `v5_weight_profiles.png` | Stacked bars showing weight split for philosophy vs. grid-search-optimized weights |
| `v5_pareto_front.png` | Scatter plots showing trade-offs between metric pairs for seed 777 |
| `v5_sensitivity_boxplot.png` | Box plot of composite score distribution across 10 seeds under universal weights |
| `v5_weight_heatmap.png` | Color map of the best algorithm's score as w₁ and w₂ vary (w₃ = 1 − w₁ − w₂) |
| `v5_v4_vs_v5.png` | V4 ranking (total time only) vs. V5 ranking (composite score) side by side |
| `weight_sensitivity_boxplot.png` | Box plot across Small/Medium/Large dataset sizes for three weight profiles |

---

## 10. Key Results

### Composite Scores — Universal Weights (0.10, 0.70, 0.20)

| Rank | Algorithm | Avg Score | Seed Wins |
|---|---|---|---|
| 1 | **Wave Batching** | 0.3600 | **5/10** |
| 2 | Random Baseline | 0.4200 | 2/10 |
| 3 | Tote-Aware Clustering | 0.4700 | 1/10 |
| 4 | Shortest Order First | 0.4800 | 2/10 |
| 5 | Load Balanced | 0.7700 | 0/10 |

### V4 vs. V5 Winner Comparison

| | V4 (single metric) | V5 (multi-objective) |
|---|---|---|
| **Method** | Lowest total completion time | Most seed wins under composite score |
| **Winner** | Random Baseline | **Wave Batching** |
| **Seed wins** | 3/10 | **5/10** |
| **Weights** | Implicit: (1.0, 0.0, 0.0) | (0.10, 0.70, 0.20) |

### Per-Algorithm Optimized Weights vs. Design Intent

| Algorithm | Design Weights | Optimized Weights | Dominant Metric | Confirmed? |
|---|---|---|---|---|
| Random Baseline | (0.34, 0.33, 0.33) | (0.15, 0.75, 0.10) | w₂ Makespan | Shifted |
| Shortest Order First | **(0.70**, 0.15, 0.15) | **(0.80**, 0.10, 0.10) | w₁ Total Comp | **Confirmed** |
| Load Balanced | (0.15, **0.70**, 0.15) | (0.10, 0.10, **0.80**) | w₃ Circulations | Shifted |
| Tote-Aware Clustering | (0.15, 0.15, **0.70**) | (**0.80**, 0.10, 0.10) | w₁ Total Comp | Shifted |
| Wave Batching | (0.40, 0.35, 0.25) | (0.10, **0.80**, 0.10) | w₂ Makespan | Shifted |

Only Shortest Order First's design philosophy was validated by the grid search.
All other algorithms performed best under weights that differed from their design intent —
indicating the data-driven approach reveals performance characteristics that intuition misses.

---

*MSE 433 Module 3 — Group 6*

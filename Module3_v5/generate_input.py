"""
MSE 433 Module 3: Warehousing — Input CSV Generator
Converts algorithm output (wave plans) into the conveyor belt's expected CSV format.
"""

import csv
import os
from typing import List, Dict, Tuple
from data_pipeline import Order, SHAPE_NAMES, NUM_SHAPES


def wave_to_input_csv(wave_plan: Dict[int, Tuple[int, dict]],
                      num_lanes: int = 4) -> List[List]:
    """
    Convert a wave plan to the conveyor input CSV format.

    Args:
        wave_plan: {lane_id: (order_id, {shape_id: count})}
        num_lanes: number of conveyor lanes (default 4)

    Returns:
        List of rows: [[conv_num, circle, pentagon, ..., cross], ...]
    """
    rows = []
    for lane_id in range(num_lanes):
        row = [lane_id]
        if lane_id in wave_plan:
            _, shape_counts = wave_plan[lane_id]
            for shape_id in range(NUM_SHAPES):
                row.append(shape_counts.get(shape_id, 0))
        else:
            row.extend([0] * NUM_SHAPES)
        rows.append(row)
    return rows


def save_input_csv(rows: List[List], filepath: str):
    """Save input CSV in the conveyor's expected format."""
    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
    header = ["conv_num"] + SHAPE_NAMES
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def save_all_waves(wave_plans: List[Dict[int, Tuple[int, dict]]],
                   output_dir: str, prefix: str = "wave"):
    """Save input CSVs for all waves of an algorithm."""
    os.makedirs(output_dir, exist_ok=True)
    filepaths = []
    for i, wave in enumerate(wave_plans):
        rows = wave_to_input_csv(wave)
        filepath = os.path.join(output_dir, f"{prefix}_{i+1}.csv")
        save_input_csv(rows, filepath)
        filepaths.append(filepath)
    return filepaths


def lane_queues_to_csvs(lane_queues: Dict[int, list],
                        output_dir: str, prefix: str = "continuous",
                        num_lanes: int = 4) -> List[str]:
    """
    Save input CSVs for continuous-mode lane queues.
    Produces one CSV per order-step (each CSV shows what each lane needs at that step).

    Args:
        lane_queues: {lane_id: [(order_id, {shape_id: count}), ...]}
        output_dir: directory to save CSVs
        prefix: filename prefix
        num_lanes: number of lanes

    Returns:
        List of saved file paths
    """
    os.makedirs(output_dir, exist_ok=True)

    # Find the max queue length across lanes
    max_depth = max((len(q) for q in lane_queues.values()), default=0)

    filepaths = []
    for step in range(max_depth):
        rows = []
        for lane_id in range(num_lanes):
            row = [lane_id]
            queue = lane_queues.get(lane_id, [])
            if step < len(queue):
                _, shape_counts = queue[step]
                for shape_id in range(NUM_SHAPES):
                    row.append(shape_counts.get(shape_id, 0))
            else:
                row.extend([0] * NUM_SHAPES)
            rows.append(row)

        filepath = os.path.join(output_dir, f"{prefix}_step_{step+1}.csv")
        save_input_csv(rows, filepath)
        filepaths.append(filepath)

    return filepaths


def save_order_csv(lane_queues: Dict[int, list], orders: list,
                   filepath: str, num_lanes: int = 4):
    """
    Save a single CSV with one row per order in the conveyor belt's format.

    Format (matching the physical conveyor):
        conv_num,circle,pentagon,trapezoid,triangle,star,moon,heart,cross
        1,0,0,2,3,0,0,0,0
        2,3,0,0,0,2,0,0,0
        ...

    - conv_num is 1-indexed {1,2,3,4}
    - Each row is one order
    - Number of rows = number of orders
    - Orders appear in their queue processing order (lane 0 first order,
      lane 1 first order, ..., lane 0 second order, ...)
    """
    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)

    # Build (order_id, lane_id, shape_counts) tuples sorted by queue position
    # so the CSV matches the physical processing order
    rows = []
    max_depth = max((len(q) for q in lane_queues.values()), default=0)
    for step in range(max_depth):
        for lane_id in range(num_lanes):
            queue = lane_queues.get(lane_id, [])
            if step < len(queue):
                oid, shape_counts = queue[step]
                row = [lane_id + 1]  # 1-indexed conv_num
                for shape_id in range(NUM_SHAPES):
                    row.append(shape_counts.get(shape_id, 0))
                rows.append(row)

    header = ["conv_num"] + SHAPE_NAMES
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def save_tote_schedule(tote_order: List[int], totes: list, orders: list,
                       filepath: str):
    """
    Save a CSV showing the tote loading sequence with which orders each tote serves.

    Columns: load_seq, tote_id, total_items, orders_served, items_per_order
    """
    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)

    # Build tote lookup
    tote_map = {t.tote_id: t for t in totes}

    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["load_seq", "tote_id", "total_items", "orders_served", "items_per_order"])
        for seq, tid in enumerate(tote_order, 1):
            tote = tote_map.get(tid)
            if tote is None:
                continue
            total = tote.total_items
            # Group items by order
            order_items = {}
            for oid, itype, qty in tote.contents:
                order_items[oid] = order_items.get(oid, 0) + qty
            orders_str = ";".join(f"O{oid}" for oid in sorted(order_items))
            items_str = ";".join(f"O{oid}={qty}" for oid, qty in sorted(order_items.items()))
            writer.writerow([seq, tid, total, orders_str, items_str])


def print_wave_plan(wave_plan: Dict[int, Tuple[int, dict]], wave_num: int = 1):
    """Pretty-print a wave plan."""
    print(f"--- Wave {wave_num} ---")
    for lane_id in sorted(wave_plan.keys()):
        oid, shapes = wave_plan[lane_id]
        items_str = ", ".join(
            f"{SHAPE_NAMES[sid]}x{cnt}" for sid, cnt in shapes.items()
        )
        total = sum(shapes.values())
        print(f"  Lane {lane_id} -> Order {oid}: {items_str} ({total} items)")


if __name__ == "__main__":
    # Test with example data
    from data_pipeline import generate_data
    from conveyor_sim import orders_to_wave_plan

    orders, totes, params = generate_data(seed=100)

    # Create a test wave with first 4 orders
    assignments = {0: 0, 1: 1, 2: 2, 3: 3}
    wave = orders_to_wave_plan([0, 1, 2, 3], orders, assignments)

    print_wave_plan(wave, 1)
    rows = wave_to_input_csv(wave)

    print("\nCSV output:")
    header = ["conv_num"] + SHAPE_NAMES
    print(",".join(header))
    for row in rows:
        print(",".join(str(x) for x in row))

    # Save it
    save_input_csv(rows, "../results/input_csvs/test_wave_1.csv")
    print("\nSaved to results/input_csvs/test_wave_1.csv")

"""
MSE 433 Module 3: Warehousing — Heuristic Algorithms
Five algorithms for order-to-lane assignment and wave batching.
All aim to minimize total order completion time.
"""

import random
from typing import List, Dict, Tuple
from data_pipeline import Order
from conveyor_sim import orders_to_wave_plan

NUM_LANES = 4


def _batch_into_waves(order_sequence: List[int], lane_assignments_per_wave: List[Dict[int, int]]) -> List[Dict[int, Tuple[int, dict]]]:
    """Helper: convert order sequence + lane assignments into wave plans."""
    # This is handled by each algorithm individually
    pass


def _create_wave_plans(waves: List[List[int]], orders: List[Order]) -> List[Dict[int, Tuple[int, dict]]]:
    """
    Given a list of waves (each wave is a list of order_ids),
    assign orders to lanes within each wave and build wave plans.

    Simple approach: assign orders to lanes 0, 1, 2, 3 in order.
    """
    wave_plans = []
    for wave_orders in waves:
        assignment = {}
        for i, oid in enumerate(wave_orders):
            assignment[oid] = i  # lane = position in wave
        wave_plan = orders_to_wave_plan(wave_orders, orders, assignment)
        wave_plans.append(wave_plan)
    return wave_plans


# =============================================================================
# Algorithm 0: Random Baseline
# =============================================================================

def random_baseline(orders: List[Order], seed: int = 42) -> List[Dict[int, Tuple[int, dict]]]:
    """
    Randomly shuffle orders and assign to lanes in arbitrary order.
    Batch into waves of 4.
    """
    rng = random.Random(seed)
    order_ids = list(range(len(orders)))
    rng.shuffle(order_ids)

    # Batch into waves of NUM_LANES
    waves = []
    for i in range(0, len(order_ids), NUM_LANES):
        waves.append(order_ids[i:i + NUM_LANES])

    return _create_wave_plans(waves, orders)


# =============================================================================
# Algorithm 1: Shortest Order First (SOF)
# =============================================================================

def shortest_order_first(orders: List[Order]) -> List[Dict[int, Tuple[int, dict]]]:
    """
    Sort orders by total item count (ascending) — analogous to SPT rule.
    Smallest orders first means they finish quickly, reducing total completion time.
    Batch into waves of 4.
    """
    order_ids = sorted(range(len(orders)), key=lambda i: orders[i].total_items)

    waves = []
    for i in range(0, len(order_ids), NUM_LANES):
        waves.append(order_ids[i:i + NUM_LANES])

    return _create_wave_plans(waves, orders)


# =============================================================================
# Algorithm 2: Load-Balanced Lane Assignment
# =============================================================================

def load_balanced(orders: List[Order]) -> List[Dict[int, Tuple[int, dict]]]:
    """
    Sort orders largest-first, then greedily assign each order to the
    lane with the least total work (LPT-style for makespan, combined
    with wave batching). This balances the load within each wave so no
    lane becomes a bottleneck.
    """
    order_ids = sorted(range(len(orders)), key=lambda i: orders[i].total_items, reverse=True)

    # Batch into waves of NUM_LANES first, then balance within each wave
    waves_raw = []
    for i in range(0, len(order_ids), NUM_LANES):
        waves_raw.append(order_ids[i:i + NUM_LANES])

    wave_plans = []
    for wave_orders in waves_raw:
        # Greedy load balancing within the wave
        lane_loads = [0] * NUM_LANES
        assignment = {}

        # Sort orders in this wave by size descending
        sorted_wave = sorted(wave_orders, key=lambda oid: orders[oid].total_items, reverse=True)

        for oid in sorted_wave:
            # Assign to the lane with the least load
            min_lane = min(range(min(NUM_LANES, len(wave_orders))),
                          key=lambda l: lane_loads[l])
            assignment[oid] = min_lane
            lane_loads[min_lane] += orders[oid].total_items

        wave_plan = orders_to_wave_plan(wave_orders, orders, assignment)
        wave_plans.append(wave_plan)

    return wave_plans


# =============================================================================
# Algorithm 3: Tote-Aware Clustering
# =============================================================================

def tote_aware_clustering(orders: List[Order]) -> List[Dict[int, Tuple[int, dict]]]:
    """
    Group orders that share totes into the same wave to minimize
    the number of tote loads. Within each wave, use load balancing.

    Greedy approach:
    1. Build a tote-sharing graph between orders
    2. Greedily form waves by clustering orders with shared totes
    3. Balance within each wave
    """
    n = len(orders)
    order_ids = list(range(n))

    # Build tote-sharing score: how many totes two orders share
    tote_sets = {i: orders[i].tote_set for i in order_ids}

    # Greedy wave formation
    assigned = set()
    waves = []

    while len(assigned) < n:
        remaining = [oid for oid in order_ids if oid not in assigned]
        if not remaining:
            break

        # Start a wave with the first unassigned order
        wave = [remaining[0]]
        assigned.add(remaining[0])
        wave_totes = set(tote_sets[remaining[0]])

        # Greedily add orders that share the most totes with current wave
        while len(wave) < NUM_LANES and len(assigned) < n:
            best_oid = None
            best_score = -1

            for oid in remaining:
                if oid in assigned:
                    continue
                shared = len(wave_totes & tote_sets[oid])
                if shared > best_score:
                    best_score = shared
                    best_oid = oid

            if best_oid is None:
                break

            wave.append(best_oid)
            assigned.add(best_oid)
            wave_totes |= tote_sets[best_oid]

        waves.append(wave)

    # Within each wave, apply load balancing for lane assignment
    wave_plans = []
    for wave_orders in waves:
        lane_loads = [0] * NUM_LANES
        assignment = {}
        sorted_wave = sorted(wave_orders, key=lambda oid: orders[oid].total_items, reverse=True)

        for oid in sorted_wave:
            min_lane = min(range(min(NUM_LANES, len(wave_orders))),
                          key=lambda l: lane_loads[l])
            assignment[oid] = min_lane
            lane_loads[min_lane] += orders[oid].total_items

        wave_plan = orders_to_wave_plan(wave_orders, orders, assignment)
        wave_plans.append(wave_plan)

    return wave_plans


# =============================================================================
# Algorithm 4: Wave-Based Batching (Smallest Waves First)
# =============================================================================

def wave_batching(orders: List[Order]) -> List[Dict[int, Tuple[int, dict]]]:
    """
    Optimally batch orders into waves of 4 to minimize total completion time.

    Strategy:
    1. Sort all orders by size (ascending)
    2. Pair smallest with largest to form balanced waves
    3. Process waves with smallest total items first
    4. Within each wave, load-balance across lanes

    The intuition: waves that finish quickly should go first (reducing
    cumulative waiting time), and within each wave the lanes should be balanced.
    """
    n = len(orders)
    order_ids = sorted(range(n), key=lambda i: orders[i].total_items)

    # Pair orders: smallest with largest for balanced waves
    # Use a two-pointer approach
    waves_raw = []
    left, right = 0, n - 1
    current_wave = []

    while left <= right:
        current_wave.append(order_ids[left])
        left += 1
        if left <= right and len(current_wave) < NUM_LANES:
            current_wave.append(order_ids[right])
            right -= 1

        if len(current_wave) == NUM_LANES or left > right:
            waves_raw.append(current_wave)
            current_wave = []

    if current_wave:
        waves_raw.append(current_wave)

    # Sort waves by total items (smallest total first)
    waves_raw.sort(key=lambda w: sum(orders[oid].total_items for oid in w))

    # Within each wave, load-balance
    wave_plans = []
    for wave_orders in waves_raw:
        lane_loads = [0] * NUM_LANES
        assignment = {}
        sorted_wave = sorted(wave_orders, key=lambda oid: orders[oid].total_items, reverse=True)

        for oid in sorted_wave:
            min_lane = min(range(min(NUM_LANES, len(wave_orders))),
                          key=lambda l: lane_loads[l])
            assignment[oid] = min_lane
            lane_loads[min_lane] += orders[oid].total_items

        wave_plan = orders_to_wave_plan(wave_orders, orders, assignment)
        wave_plans.append(wave_plan)

    return wave_plans


# =============================================================================
# Continuous mode helpers
# =============================================================================

def _build_lane_queues(ordered_ids: List[int], orders: List[Order],
                       num_lanes: int = NUM_LANES) -> Dict[int, List[Tuple[int, dict]]]:
    """
    Distribute an ordered list of order IDs across lanes using round-robin.
    Returns {lane_id: [(order_id, {shape_id: count}), ...]}.
    """
    lane_queues: Dict[int, List[Tuple[int, dict]]] = {i: [] for i in range(num_lanes)}
    for idx, oid in enumerate(ordered_ids):
        lane_id = idx % num_lanes
        lane_queues[lane_id].append((oid, orders[oid].shape_counts()))
    return lane_queues


def _build_lane_queues_load_balanced(ordered_ids: List[int], orders: List[Order],
                                     num_lanes: int = NUM_LANES) -> Dict[int, List[Tuple[int, dict]]]:
    """
    Distribute orders across lanes using greedy load-balancing (assign each order
    to the lane with the least total work so far).
    """
    lane_queues: Dict[int, List[Tuple[int, dict]]] = {i: [] for i in range(num_lanes)}
    lane_loads = [0] * num_lanes

    for oid in ordered_ids:
        min_lane = min(range(num_lanes), key=lambda l: lane_loads[l])
        lane_queues[min_lane].append((oid, orders[oid].shape_counts()))
        lane_loads[min_lane] += orders[oid].total_items

    return lane_queues


# =============================================================================
# Continuous algorithm variants
# =============================================================================

def random_baseline_continuous(orders: List[Order], seed: int = 42) -> Dict[int, List[Tuple[int, dict]]]:
    """Random shuffle, distribute to lanes via round-robin."""
    rng = random.Random(seed)
    order_ids = list(range(len(orders)))
    rng.shuffle(order_ids)
    return _build_lane_queues(order_ids, orders)


def shortest_order_first_continuous(orders: List[Order]) -> Dict[int, List[Tuple[int, dict]]]:
    """Sort by item count ascending, distribute via round-robin."""
    order_ids = sorted(range(len(orders)), key=lambda i: orders[i].total_items)
    return _build_lane_queues(order_ids, orders)


def load_balanced_continuous(orders: List[Order]) -> Dict[int, List[Tuple[int, dict]]]:
    """Sort largest-first, then greedily assign to least-loaded lane."""
    order_ids = sorted(range(len(orders)), key=lambda i: orders[i].total_items, reverse=True)
    return _build_lane_queues_load_balanced(order_ids, orders)


def tote_aware_clustering_continuous(orders: List[Order]) -> Dict[int, List[Tuple[int, dict]]]:
    """
    Greedy tote-sharing clustering to determine order sequence,
    then distribute via round-robin.
    """
    n = len(orders)
    order_ids = list(range(n))
    tote_sets = {i: orders[i].tote_set for i in order_ids}

    assigned = set()
    ordered_sequence = []

    while len(assigned) < n:
        remaining = [oid for oid in order_ids if oid not in assigned]
        if not remaining:
            break

        # Pick order with most tote overlap with recently assigned, or first remaining
        current = remaining[0]
        ordered_sequence.append(current)
        assigned.add(current)
        wave_totes = set(tote_sets[current])

        # Greedily add up to (NUM_LANES-1) more orders sharing totes
        added_in_group = 1
        while added_in_group < NUM_LANES and len(assigned) < n:
            best_oid = None
            best_score = -1
            for oid in remaining:
                if oid in assigned:
                    continue
                shared = len(wave_totes & tote_sets[oid])
                if shared > best_score:
                    best_score = shared
                    best_oid = oid
            if best_oid is None:
                break
            ordered_sequence.append(best_oid)
            assigned.add(best_oid)
            wave_totes |= tote_sets[best_oid]
            added_in_group += 1

    return _build_lane_queues(ordered_sequence, orders)


def wave_batching_continuous(orders: List[Order]) -> Dict[int, List[Tuple[int, dict]]]:
    """
    Pair smallest with largest orders (two-pointer), sort groups by total,
    then distribute via round-robin.
    """
    n = len(orders)
    order_ids = sorted(range(n), key=lambda i: orders[i].total_items)

    # Two-pointer pairing into groups of NUM_LANES
    groups = []
    left, right = 0, n - 1
    current_group = []
    while left <= right:
        current_group.append(order_ids[left])
        left += 1
        if left <= right and len(current_group) < NUM_LANES:
            current_group.append(order_ids[right])
            right -= 1
        if len(current_group) == NUM_LANES or left > right:
            groups.append(current_group)
            current_group = []
    if current_group:
        groups.append(current_group)

    # Sort groups by total items (smallest first)
    groups.sort(key=lambda g: sum(orders[oid].total_items for oid in g))

    # Flatten into ordered sequence
    ordered_sequence = []
    for g in groups:
        ordered_sequence.extend(g)

    return _build_lane_queues(ordered_sequence, orders)


# =============================================================================
# Master runner
# =============================================================================

ALL_ALGORITHMS = {
    "Random Baseline": random_baseline,
    "Shortest Order First": shortest_order_first,
    "Load Balanced": load_balanced,
    "Tote-Aware Clustering": tote_aware_clustering,
    "Wave Batching": wave_batching,
}

ALL_ALGORITHMS_CONTINUOUS = {
    "Random Baseline": random_baseline_continuous,
    "Shortest Order First": shortest_order_first_continuous,
    "Load Balanced": load_balanced_continuous,
    "Tote-Aware Clustering": tote_aware_clustering_continuous,
    "Wave Batching": wave_batching_continuous,
}


def run_all(orders: List[Order]) -> Dict[str, List[Dict[int, Tuple[int, dict]]]]:
    """Run all algorithms and return their wave plans."""
    results = {}
    for name, algo in ALL_ALGORITHMS.items():
        results[name] = algo(orders)
    return results


def compute_tote_order(lane_queues: Dict[int, List[Tuple[int, dict]]],
                       orders: List[Order],
                       totes: list) -> List[int]:
    """
    V4: Compute a static tote loading schedule based on lane queues.
    For each tote, find the earliest queue position of any order it serves.
    Sort totes by earliest-need (ascending), break ties by number of items
    serving orders at that earliest position (descending).

    Args:
        lane_queues: {lane_id: [(order_id, {shape_id: count}), ...]}
        orders: List of Order objects
        totes: List of Tote objects

    Returns:
        Ordered list of tote IDs (load first → load last)
    """
    # Build order -> (lane_id, queue_position) mapping
    order_queue_pos = {}
    for lane_id, queue in lane_queues.items():
        for pos, (oid, _) in enumerate(queue):
            order_queue_pos[oid] = (lane_id, pos)

    # For each tote, compute:
    #   earliest_pos: min queue position across all orders this tote serves
    #   active_items: number of items for orders at that earliest position
    tote_scores = []
    for tote in totes:
        tid = tote.tote_id
        if not tote.contents:
            tote_scores.append((tid, float('inf'), 0))
            continue

        earliest_pos = float('inf')
        for oid, itype, qty in tote.contents:
            if oid in order_queue_pos:
                _, pos = order_queue_pos[oid]
                earliest_pos = min(earliest_pos, pos)

        # Count items serving orders at the earliest position
        active_items = 0
        for oid, itype, qty in tote.contents:
            if oid in order_queue_pos:
                _, pos = order_queue_pos[oid]
                if pos == earliest_pos:
                    active_items += qty

        tote_scores.append((tid, earliest_pos, active_items))

    # Sort: earliest position first, then most active items first
    tote_scores.sort(key=lambda x: (x[1], -x[2]))
    return [tid for tid, _, _ in tote_scores]


def run_all_continuous(orders: List[Order]) -> Dict[str, Dict[int, List[Tuple[int, dict]]]]:
    """Run all continuous algorithms and return their lane queues."""
    results = {}
    for name, algo in ALL_ALGORITHMS_CONTINUOUS.items():
        results[name] = algo(orders)
    return results


if __name__ == "__main__":
    from data_pipeline import generate_data, SHAPE_NAMES
    from generate_input import print_wave_plan

    orders, totes, params = generate_data(seed=100)

    print(f"Orders: {params['n_orders']}, Total items: {params['total_items']}")
    print(f"Order sizes: {[o.total_items for o in orders]}")
    print()

    for name, algo in ALL_ALGORITHMS.items():
        print(f"{'='*50}")
        print(f"Algorithm: {name}")
        print(f"{'='*50}")
        wave_plans = algo(orders)
        for i, wave in enumerate(wave_plans):
            print_wave_plan(wave, i + 1)
        print()

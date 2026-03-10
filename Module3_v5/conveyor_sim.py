"""
MSE 433 Module 3: Warehousing — Conveyor Belt Simulation
Discrete-event simulation of the 4-conveyor circulation loop.

Physical system:
- 4 conveyors forming a circulation loop
- 1 scanner + 1 lane per conveyor
- Each lane holds 1 active order at a time
- Pneumatic arms divert items when scanner detects a match
- Items circulate until diverted
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import heapq
from data_pipeline import Order, SHAPE_NAMES, NUM_SHAPES


@dataclass
class LaneState:
    """State of one conveyor lane."""
    lane_id: int
    order_queue: List[dict] = field(default_factory=list)  # orders waiting
    active_order: Optional[dict] = None  # {shape_id: remaining_count}
    active_order_id: Optional[int] = None
    items_collected: int = 0
    items_needed: int = 0
    completion_times: List[Tuple[int, float]] = field(default_factory=list)  # (order_id, time)


@dataclass
class CirculatingItem:
    """An item on the circulation loop."""
    item_id: int
    shape: int
    target_lane: int  # which lane needs this item
    load_time: float
    circulations: int = 0


@dataclass
class SimResult:
    """Results from a simulation run."""
    order_completions: Dict[int, float]  # order_id -> completion time
    total_completion_time: float         # sum of all order completion times
    makespan: float                      # time when last order finishes
    avg_completion_time: float
    total_circulations: int              # total item circulations across all items
    lane_utilization: Dict[int, float]   # lane_id -> fraction of makespan active
    item_events: List[dict]              # [{conv_num, shape, time}, ...] for output CSV
    wave_results: List[dict] = field(default_factory=list)  # per-wave breakdowns
    tote_load_order: List[int] = field(default_factory=list)  # V4: ordered tote IDs as loaded


class ConveyorSimulator:
    """
    Simulates the 4-conveyor circulation loop.

    Parameters (calibrate from physical testing):
        loop_time: Time for an item to complete one full loop (seconds)
        divert_time: Time for scanner + pneumatic arm to divert an item (seconds)
        load_interval: Time between loading successive items onto the loop (seconds)
        num_lanes: Number of conveyor lanes (default 4)
    """

    def __init__(self, loop_time=40.0, divert_time=5.0, load_interval=3.0, num_lanes=4):
        self.loop_time = loop_time
        self.divert_time = divert_time
        self.load_interval = load_interval
        self.num_lanes = num_lanes
        self.station_spacing = loop_time / num_lanes  # time between stations

    def simulate_wave(self, lane_assignments: Dict[int, dict],
                      start_time: float = 0.0) -> Tuple[List[dict], float, Dict[int, float]]:
        """
        Simulate one wave of orders (up to 4 orders, one per lane).

        Args:
            lane_assignments: {lane_id: {shape_id: count}} for each lane's order
            start_time: simulation clock offset

        Returns:
            item_events: list of {conv_num, shape, time} dicts
            wave_end_time: when the last order in this wave completes
            order_times: {order_placeholder -> completion_time} (lane-based)
        """
        # Initialize lanes
        lanes = {}
        for lane_id in range(self.num_lanes):
            needed = lane_assignments.get(lane_id, {})
            lanes[lane_id] = {
                "remaining": dict(needed),
                "total": sum(needed.values()),
                "collected": 0,
            }

        # Create all items and assign them to the loop
        items = []
        item_id = 0
        for lane_id, shape_counts in lane_assignments.items():
            for shape_id, count in shape_counts.items():
                for _ in range(count):
                    items.append(CirculatingItem(
                        item_id=item_id,
                        shape=shape_id,
                        target_lane=lane_id,
                        load_time=start_time + item_id * self.load_interval,
                    ))
                    item_id += 1

        # Event-driven simulation using a priority queue
        # Events: (time, counter, event_type, data) — counter breaks ties
        events = []
        item_events = []
        event_counter = 0

        # Schedule first arrival at each item's target station
        for item in items:
            # Time for item to reach its target lane's station
            # Items enter at station 0 and travel around the loop
            travel_time = self.station_spacing * item.target_lane
            if travel_time == 0:
                travel_time = self.station_spacing * 0.5  # small offset for station 0
            arrival_time = item.load_time + travel_time
            heapq.heappush(events, (arrival_time, event_counter, "arrive", item))
            event_counter += 1

        lane_busy_until = {i: 0.0 for i in range(self.num_lanes)}

        while events:
            time, _, event_type, item = heapq.heappop(events)

            if event_type == "arrive":
                lane = lanes[item.target_lane]

                # Check if this item's shape is still needed
                if lane["remaining"].get(item.shape, 0) > 0:
                    # Divert the item
                    divert_start = max(time, lane_busy_until[item.target_lane])
                    divert_end = divert_start + self.divert_time

                    lane["remaining"][item.shape] -= 1
                    if lane["remaining"][item.shape] == 0:
                        del lane["remaining"][item.shape]
                    lane["collected"] += 1
                    lane_busy_until[item.target_lane] = divert_end

                    item_events.append({
                        "conv_num": item.target_lane,
                        "shape": item.shape,
                        "time": divert_end,
                    })
                else:
                    # Item not needed (already collected enough), it keeps circulating
                    # This shouldn't happen in a well-formed input, but handle gracefully
                    item.circulations += 1
                    next_arrival = time + self.loop_time
                    if item.circulations < 50:  # safety limit
                        heapq.heappush(events, (next_arrival, event_counter, "arrive", item))
                        event_counter += 1

        # Sort events by time
        item_events.sort(key=lambda e: e["time"])

        # Calculate per-lane completion times
        lane_completion = {}
        for lane_id in range(self.num_lanes):
            lane_items = [e for e in item_events if e["conv_num"] == lane_id]
            if lane_items:
                lane_completion[lane_id] = lane_items[-1]["time"]
            else:
                lane_completion[lane_id] = start_time

        wave_end = max(lane_completion.values()) if lane_completion else start_time

        return item_events, wave_end, lane_completion

    def simulate_full(self, wave_plans: List[Dict[int, Tuple[int, dict]]]) -> SimResult:
        """
        Simulate multiple waves of orders sequentially.

        Args:
            wave_plans: List of wave dicts, each is:
                {lane_id: (order_id, {shape_id: count})}

        Returns:
            SimResult with all metrics
        """
        all_events = []
        order_completions = {}
        total_circulations = 0
        current_time = 0.0
        wave_results = []

        for wave_idx, wave in enumerate(wave_plans):
            # Convert to lane_assignments format
            lane_assignments = {}
            order_lane_map = {}
            for lane_id, (order_id, shape_counts) in wave.items():
                lane_assignments[lane_id] = shape_counts
                order_lane_map[lane_id] = order_id

            events, wave_end, lane_completion = self.simulate_wave(
                lane_assignments, start_time=current_time
            )

            # Map lane completions to order IDs
            for lane_id, comp_time in lane_completion.items():
                if lane_id in order_lane_map:
                    oid = order_lane_map[lane_id]
                    order_completions[oid] = comp_time

            all_events.extend(events)
            wave_results.append({
                "wave": wave_idx,
                "start_time": current_time,
                "end_time": wave_end,
                "orders": list(order_lane_map.values()),
                "lane_completions": {
                    order_lane_map.get(lid, -1): t
                    for lid, t in lane_completion.items()
                    if lid in order_lane_map
                },
            })

            current_time = wave_end  # next wave starts when current wave finishes

        # Compute metrics
        if order_completions:
            makespan = max(order_completions.values())
            total_completion = sum(order_completions.values())
            avg_completion = total_completion / len(order_completions)
        else:
            makespan = total_completion = avg_completion = 0.0

        # Lane utilization (fraction of makespan each lane was "active")
        lane_util = {}
        for lid in range(self.num_lanes):
            lane_events = [e for e in all_events if e["conv_num"] == lid]
            if lane_events and makespan > 0:
                active_time = lane_events[-1]["time"] - lane_events[0]["time"]
                lane_util[lid] = active_time / makespan
            else:
                lane_util[lid] = 0.0

        return SimResult(
            order_completions=order_completions,
            total_completion_time=total_completion,
            makespan=makespan,
            avg_completion_time=avg_completion,
            total_circulations=total_circulations,
            lane_utilization=lane_util,
            item_events=all_events,
            wave_results=wave_results,
        )


    def simulate_continuous(self, lane_queues: Dict[int, List[Tuple[int, dict]]]) -> SimResult:
        """
        Simulate a continuous conveyor where each lane has its own order queue.
        When a lane finishes its active order, it immediately starts the next one
        without waiting for other lanes.

        Args:
            lane_queues: {lane_id: [(order_id, {shape_id: count}), ...]}
                Each lane has an ordered list of orders to process.

        Returns:
            SimResult with all metrics
        """
        # Flatten all items across all orders in all lanes, but tag with order_id
        # Each lane processes orders sequentially from its queue.

        # Track per-lane state
        lane_state: Dict[int, dict] = {}
        for lane_id in range(self.num_lanes):
            queue = lane_queues.get(lane_id, [])
            if queue:
                first_oid, first_shapes = queue[0]
                lane_state[lane_id] = {
                    "queue": queue,
                    "queue_idx": 0,
                    "active_order_id": first_oid,
                    "remaining": dict(first_shapes),
                    "total": sum(first_shapes.values()),
                    "collected": 0,
                }
            else:
                lane_state[lane_id] = {
                    "queue": [],
                    "queue_idx": 0,
                    "active_order_id": None,
                    "remaining": {},
                    "total": 0,
                    "collected": 0,
                }

        # Load ALL items for ALL orders onto the loop at time 0.
        # Each item knows its target lane AND order_id.
        items = []
        item_id = 0
        for lane_id, queue in lane_queues.items():
            for order_id, shape_counts in queue:
                for shape_id, count in shape_counts.items():
                    for _ in range(count):
                        items.append({
                            "item_id": item_id,
                            "shape": shape_id,
                            "target_lane": lane_id,
                            "order_id": order_id,
                            "load_time": item_id * self.load_interval,
                            "circulations": 0,
                        })
                        item_id += 1

        # Event-driven simulation
        events = []
        item_events = []
        event_counter = 0
        order_completions: Dict[int, float] = {}

        # Schedule first arrival at target station for each item
        for item in items:
            travel_time = self.station_spacing * item["target_lane"]
            if travel_time == 0:
                travel_time = self.station_spacing * 0.5
            arrival_time = item["load_time"] + travel_time
            heapq.heappush(events, (arrival_time, event_counter, "arrive", item))
            event_counter += 1

        lane_busy_until = {i: 0.0 for i in range(self.num_lanes)}

        while events:
            time, _, event_type, item = heapq.heappop(events)

            if event_type == "arrive":
                lane_id = item["target_lane"]
                ls = lane_state[lane_id]

                # Is this item's order currently active on this lane?
                if ls["active_order_id"] == item["order_id"]:
                    # Check if shape is still needed
                    if ls["remaining"].get(item["shape"], 0) > 0:
                        divert_start = max(time, lane_busy_until[lane_id])
                        divert_end = divert_start + self.divert_time

                        ls["remaining"][item["shape"]] -= 1
                        if ls["remaining"][item["shape"]] == 0:
                            del ls["remaining"][item["shape"]]
                        ls["collected"] += 1
                        lane_busy_until[lane_id] = divert_end

                        item_events.append({
                            "conv_num": lane_id,
                            "shape": item["shape"],
                            "time": divert_end,
                            "order_id": item["order_id"],
                        })

                        # Check if order is complete
                        if ls["collected"] == ls["total"]:
                            order_completions[ls["active_order_id"]] = divert_end

                            # Advance to next order in queue
                            ls["queue_idx"] += 1
                            if ls["queue_idx"] < len(ls["queue"]):
                                next_oid, next_shapes = ls["queue"][ls["queue_idx"]]
                                ls["active_order_id"] = next_oid
                                ls["remaining"] = dict(next_shapes)
                                ls["total"] = sum(next_shapes.values())
                                ls["collected"] = 0
                            else:
                                ls["active_order_id"] = None
                                ls["remaining"] = {}
                                ls["total"] = 0
                                ls["collected"] = 0
                    else:
                        # Shape not needed, item circulates
                        item["circulations"] += 1
                        if item["circulations"] < 100:
                            next_arrival = time + self.loop_time
                            heapq.heappush(events, (next_arrival, event_counter, "arrive", item))
                            event_counter += 1
                else:
                    # Item's order is NOT active on this lane yet — keep circulating
                    item["circulations"] += 1
                    if item["circulations"] < 100:
                        next_arrival = time + self.loop_time
                        heapq.heappush(events, (next_arrival, event_counter, "arrive", item))
                        event_counter += 1

        # Sort events by time
        item_events.sort(key=lambda e: e["time"])

        # Compute metrics
        if order_completions:
            makespan = max(order_completions.values())
            total_completion = sum(order_completions.values())
            avg_completion = total_completion / len(order_completions)
        else:
            makespan = total_completion = avg_completion = 0.0

        # Lane utilization
        lane_util = {}
        for lid in range(self.num_lanes):
            lane_events = [e for e in item_events if e["conv_num"] == lid]
            if lane_events and makespan > 0:
                active_time = lane_events[-1]["time"] - lane_events[0]["time"]
                lane_util[lid] = active_time / makespan
            else:
                lane_util[lid] = 0.0

        total_circs = sum(it["circulations"] for it in items)

        return SimResult(
            order_completions=order_completions,
            total_completion_time=total_completion,
            makespan=makespan,
            avg_completion_time=avg_completion,
            total_circulations=total_circs,
            lane_utilization=lane_util,
            item_events=item_events,
            wave_results=[],  # no waves in continuous mode
        )


    def simulate_tote_ordered(self, lane_queues: Dict[int, List[Tuple[int, dict]]],
                              totes: 'List', orders: 'List') -> SimResult:
        """
        V4: Tote-ordered loading simulation.
        Instead of loading ALL items at time 0, items are loaded tote-by-tote.
        A greedy scheduler picks the next tote to load based on how many items
        it contributes to currently-active orders.

        Args:
            lane_queues: {lane_id: [(order_id, {shape_id: count}), ...]}
            totes: List of Tote objects (from data_pipeline)
            orders: List of Order objects (from data_pipeline)

        Returns:
            SimResult with tote_load_order populated
        """
        # Build tote -> items mapping: for each tote, list the (order_id, shape, lane_id) items
        # We need to know which lane each order is assigned to
        order_to_lane = {}
        order_queue_pos = {}  # order_id -> position in its lane's queue
        for lane_id, queue in lane_queues.items():
            for pos, (oid, _) in enumerate(queue):
                order_to_lane[oid] = lane_id
                order_queue_pos[oid] = pos

        # Build tote items list: each tote produces items tagged with (order_id, shape, lane_id)
        tote_items_map = {}  # tote_id -> [(order_id, item_type, quantity, lane_id), ...]
        for tote in totes:
            tid = tote.tote_id
            tote_items_map[tid] = []
            for oid, itype, qty in tote.contents:
                if oid in order_to_lane:
                    tote_items_map[tid].append((oid, itype, qty, order_to_lane[oid]))

        # Track per-lane state (same as simulate_continuous)
        lane_state: Dict[int, dict] = {}
        for lane_id in range(self.num_lanes):
            queue = lane_queues.get(lane_id, [])
            if queue:
                first_oid, first_shapes = queue[0]
                lane_state[lane_id] = {
                    "queue": queue,
                    "queue_idx": 0,
                    "active_order_id": first_oid,
                    "remaining": dict(first_shapes),
                    "total": sum(first_shapes.values()),
                    "collected": 0,
                }
            else:
                lane_state[lane_id] = {
                    "queue": [],
                    "queue_idx": 0,
                    "active_order_id": None,
                    "remaining": {},
                    "total": 0,
                    "collected": 0,
                }

        def get_active_orders():
            """Return set of currently active order IDs across all lanes."""
            return {ls["active_order_id"] for ls in lane_state.values()
                    if ls["active_order_id"] is not None}

        def score_tote(tid):
            """Score a tote: (active_items, -non_active_items) for greedy selection."""
            active = get_active_orders()
            active_count = 0
            non_active_count = 0
            for oid, itype, qty, lane_id in tote_items_map.get(tid, []):
                if oid in active:
                    active_count += qty
                else:
                    non_active_count += qty
            return (active_count, -non_active_count)

        # Determine tote loading order dynamically
        unloaded_totes = set(tote_items_map.keys())
        tote_load_order = []
        items = []
        item_id = 0
        load_clock = 0.0  # tracks when the loader is free

        while unloaded_totes:
            # Pick the best tote to load next
            best_tid = max(unloaded_totes, key=score_tote)
            tote_load_order.append(best_tid)
            unloaded_totes.remove(best_tid)

            # Load all items from this tote onto the loop
            for oid, itype, qty, lane_id in tote_items_map[best_tid]:
                for _ in range(qty):
                    items.append({
                        "item_id": item_id,
                        "shape": itype,
                        "target_lane": lane_id,
                        "order_id": oid,
                        "load_time": load_clock,
                        "circulations": 0,
                        "tote_id": best_tid,
                    })
                    load_clock += self.load_interval
                    item_id += 1

            # NOTE: We don't dynamically re-check order completions during loading
            # because completions happen in simulation time, not loading-schedule time.
            # The scoring is re-evaluated before each tote pick using current lane_state,
            # but lane_state only changes during the event simulation below.
            # For the greedy pre-scheduling, we do a static re-score after simulating
            # partial completions. However, since items haven't been simulated yet,
            # we use the initial active set for scoring.
            # A more sophisticated approach would interleave loading and simulation,
            # but the static greedy is sufficient and matches the plan.

        # Now run the event-driven simulation (same as simulate_continuous)
        # but lane_state is already initialized above
        events_pq = []
        item_events = []
        event_counter = 0
        order_completions: Dict[int, float] = {}

        for item in items:
            travel_time = self.station_spacing * item["target_lane"]
            if travel_time == 0:
                travel_time = self.station_spacing * 0.5
            arrival_time = item["load_time"] + travel_time
            heapq.heappush(events_pq, (arrival_time, event_counter, "arrive", item))
            event_counter += 1

        lane_busy_until = {i: 0.0 for i in range(self.num_lanes)}

        while events_pq:
            time, _, event_type, item = heapq.heappop(events_pq)

            if event_type == "arrive":
                lane_id = item["target_lane"]
                ls = lane_state[lane_id]

                if ls["active_order_id"] == item["order_id"]:
                    if ls["remaining"].get(item["shape"], 0) > 0:
                        divert_start = max(time, lane_busy_until[lane_id])
                        divert_end = divert_start + self.divert_time

                        ls["remaining"][item["shape"]] -= 1
                        if ls["remaining"][item["shape"]] == 0:
                            del ls["remaining"][item["shape"]]
                        ls["collected"] += 1
                        lane_busy_until[lane_id] = divert_end

                        item_events.append({
                            "conv_num": lane_id,
                            "shape": item["shape"],
                            "time": divert_end,
                            "order_id": item["order_id"],
                            "tote_id": item["tote_id"],
                        })

                        if ls["collected"] == ls["total"]:
                            order_completions[ls["active_order_id"]] = divert_end
                            ls["queue_idx"] += 1
                            if ls["queue_idx"] < len(ls["queue"]):
                                next_oid, next_shapes = ls["queue"][ls["queue_idx"]]
                                ls["active_order_id"] = next_oid
                                ls["remaining"] = dict(next_shapes)
                                ls["total"] = sum(next_shapes.values())
                                ls["collected"] = 0
                            else:
                                ls["active_order_id"] = None
                                ls["remaining"] = {}
                                ls["total"] = 0
                                ls["collected"] = 0
                    else:
                        item["circulations"] += 1
                        if item["circulations"] < 100:
                            next_arrival = time + self.loop_time
                            heapq.heappush(events_pq, (next_arrival, event_counter, "arrive", item))
                            event_counter += 1
                else:
                    item["circulations"] += 1
                    if item["circulations"] < 100:
                        next_arrival = time + self.loop_time
                        heapq.heappush(events_pq, (next_arrival, event_counter, "arrive", item))
                        event_counter += 1

        item_events.sort(key=lambda e: e["time"])

        if order_completions:
            makespan = max(order_completions.values())
            total_completion = sum(order_completions.values())
            avg_completion = total_completion / len(order_completions)
        else:
            makespan = total_completion = avg_completion = 0.0

        lane_util = {}
        for lid in range(self.num_lanes):
            lane_events = [e for e in item_events if e["conv_num"] == lid]
            if lane_events and makespan > 0:
                active_time = lane_events[-1]["time"] - lane_events[0]["time"]
                lane_util[lid] = active_time / makespan
            else:
                lane_util[lid] = 0.0

        total_circs = sum(it["circulations"] for it in items)

        return SimResult(
            order_completions=order_completions,
            total_completion_time=total_completion,
            makespan=makespan,
            avg_completion_time=avg_completion,
            total_circulations=total_circs,
            lane_utilization=lane_util,
            item_events=item_events,
            wave_results=[],
            tote_load_order=tote_load_order,
        )


def orders_to_wave_plan(order_ids: List[int], orders: List[Order],
                        lane_assignment: Dict[int, int]) -> Dict[int, Tuple[int, dict]]:
    """
    Convert a set of order IDs + lane assignments into a wave plan.

    Args:
        order_ids: which orders are in this wave
        orders: full list of Order objects
        lane_assignment: {order_id: lane_id}

    Returns:
        {lane_id: (order_id, {shape_id: count})}
    """
    wave = {}
    for oid in order_ids:
        order = orders[oid]
        lane_id = lane_assignment[oid]
        shape_counts = order.shape_counts()
        wave[lane_id] = (oid, shape_counts)
    return wave


if __name__ == "__main__":
    from data_pipeline import generate_data

    # Quick test with example input data
    # Example: Conv 0 gets 3 triangles + 2 crosses, etc.
    sim = ConveyorSimulator(loop_time=40.0, divert_time=5.0, load_interval=3.0)

    lane_assignments = {
        0: {3: 3, 7: 2},  # 3 triangles, 2 crosses
        1: {1: 2, 6: 3},  # 2 pentagons, 3 hearts
        2: {5: 3},         # 3 moons
        3: {0: 2},         # 2 circles
    }

    events, end_time, lane_comp = sim.simulate_wave(lane_assignments)

    print("=== Simulation of Example Input ===")
    print(f"{'Conv':>4} {'Shape':>10} {'Time':>10}")
    print("-" * 28)
    for e in events:
        print(f"{e['conv_num']:>4} {SHAPE_NAMES[e['shape']]:>10} {e['time']:>10.2f}")
    print(f"\nWave end time: {end_time:.2f}s")
    print(f"Lane completions: {lane_comp}")

    # Now test with generated data
    print("\n\n=== Full Simulation with Generated Data ===")
    orders, totes, params = generate_data(seed=100)

    # Simple test: put first 4 orders in wave 1
    wave1_assignments = {}
    for i, oid in enumerate([0, 1, 2, 3]):
        wave1_assignments[oid] = i  # order -> lane

    wave1 = orders_to_wave_plan([0, 1, 2, 3], orders, wave1_assignments)
    wave2_assignments = {4: 0, 5: 1, 6: 2, 7: 3}
    wave2 = orders_to_wave_plan([4, 5, 6, 7], orders, wave2_assignments)
    wave3_assignments = {8: 0, 9: 1, 10: 2}
    wave3 = orders_to_wave_plan([8, 9, 10], orders, wave3_assignments)

    result = sim.simulate_full([wave1, wave2, wave3])

    print(f"Total completion time: {result.total_completion_time:.2f}s")
    print(f"Makespan: {result.makespan:.2f}s")
    print(f"Avg completion time: {result.avg_completion_time:.2f}s")
    print(f"\nPer-order completions:")
    for oid in sorted(result.order_completions):
        print(f"  Order {oid}: {result.order_completions[oid]:.2f}s")

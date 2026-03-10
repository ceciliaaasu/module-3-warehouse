"""
MSE 433 Module 3: Warehousing — Data Pipeline
Generates order/tote data and provides clean data structures for algorithms.
"""

import random
from dataclasses import dataclass, field
from typing import List, Tuple, Dict
import csv
import os

# 8 shape types used by the conveyor system
SHAPE_NAMES = ["circle", "pentagon", "trapezoid", "triangle", "star", "moon", "heart", "cross"]
NUM_SHAPES = len(SHAPE_NAMES)


@dataclass
class OrderItem:
    """A single item-type entry within an order."""
    item_type: int      # 0-7 (shape index)
    quantity: int        # how many of this type
    tote_id: int         # which tote contains these items


@dataclass
class Order:
    """A customer order consisting of one or more item types."""
    order_id: int
    items: List[OrderItem] = field(default_factory=list)

    @property
    def total_items(self) -> int:
        return sum(item.quantity for item in self.items)

    @property
    def item_types_set(self) -> set:
        return {item.item_type for item in self.items}

    @property
    def tote_set(self) -> set:
        return {item.tote_id for item in self.items}

    def shape_counts(self) -> Dict[int, int]:
        """Returns {shape_id: total_quantity} for this order."""
        counts = {}
        for item in self.items:
            counts[item.item_type] = counts.get(item.item_type, 0) + item.quantity
        return counts


@dataclass
class Tote:
    """A tote containing items for one or more orders."""
    tote_id: int
    contents: List[Tuple[int, int, int]] = field(default_factory=list)  # (order_id, item_type, quantity)

    @property
    def total_items(self) -> int:
        return sum(qty for _, _, qty in self.contents)


def _generate_random_number(seed, begin, end):
    """Replicates the notebook's generate_random_number: resets seed each call."""
    random.seed(seed)
    return random.randint(begin, end)


def generate_data(seed: int = 100, n_orders: int = None,
                  n_itemtypes: int = None, n_totes: int = None
                  ) -> Tuple[List[Order], List[Tote], dict]:
    """
    Generate random order/tote data using the same logic as the course notebook.
    Replicates the exact seed behavior: generate_random_number resets seed each call,
    so the random state entering the order loop is seed(seed) + 1 consumed randint.

    Optional overrides let you create a smaller instance while keeping
    the same random-state sequence (the three _generate_random_number
    calls always run so that downstream random state is unchanged).

    Returns:
        orders: List of Order objects
        totes: List of Tote objects
        params: Dict with n_orders, n_itemtypes, n_totes
    """
    # These three calls each reset the seed (matching notebook behavior)
    _n_orders = _generate_random_number(seed, 10, 15)
    _n_itemtypes = _generate_random_number(seed, 7, 10)
    _n_totes = _generate_random_number(seed, 15, 20)
    # After the last call, random state = seed(seed) + 1 consumed randint

    # Apply overrides (if provided) while keeping random state intact
    n_orders = n_orders if n_orders is not None else _n_orders
    n_itemtypes = n_itemtypes if n_itemtypes is not None else _n_itemtypes
    n_totes = n_totes if n_totes is not None else _n_totes
    # Cap item types to the number of known shapes
    n_itemtypes = min(n_itemtypes, NUM_SHAPES)

    # Generate order item types and quantities
    order_itemtypes = []
    order_quantities = []
    for i in range(n_orders):
        order_size = random.randint(1, 3)
        tt = random.sample(range(0, n_itemtypes - 1), order_size)
        qq = [random.randint(1, 3) for _ in range(order_size)]
        order_itemtypes.append(tt)
        order_quantities.append(qq)

    # Generate tote assignments
    orders_totes = [[] for _ in range(n_orders)]
    for i in range(n_orders):
        for j in range(len(order_itemtypes[i])):
            if j == 0:
                orders_totes[i].append(random.randint(0, n_totes - 1))
            else:
                if random.randint(0, 1) == 0:
                    orders_totes[i].append(orders_totes[i][0])
                else:
                    orders_totes[i].append(random.randint(0, n_totes - 1))

    # Build Order objects
    orders = []
    for i in range(n_orders):
        order_items = []
        for j in range(len(order_itemtypes[i])):
            order_items.append(OrderItem(
                item_type=order_itemtypes[i][j],
                quantity=order_quantities[i][j],
                tote_id=orders_totes[i][j]
            ))
        orders.append(Order(order_id=i, items=order_items))

    # Build Tote objects
    tote_dict = {}
    for order in orders:
        for item in order.items:
            if item.tote_id not in tote_dict:
                tote_dict[item.tote_id] = Tote(tote_id=item.tote_id)
            tote_dict[item.tote_id].contents.append(
                (order.order_id, item.item_type, item.quantity)
            )
    totes = sorted(tote_dict.values(), key=lambda t: t.tote_id)

    params = {
        "seed": seed,
        "n_orders": n_orders,
        "n_itemtypes": n_itemtypes,
        "n_totes": n_totes,
        "total_items": sum(o.total_items for o in orders),
    }

    return orders, totes, params


def print_summary(orders: List[Order], totes: List[Tote], params: dict):
    """Print a human-readable summary of the generated data."""
    print(f"=== Data Summary (seed={params['seed']}) ===")
    print(f"Orders: {params['n_orders']}, Item Types: {params['n_itemtypes']}, "
          f"Totes: {params['n_totes']}, Total Items: {params['total_items']}")
    print()

    print("Orders:")
    for o in orders:
        items_str = ", ".join(
            f"{SHAPE_NAMES[it.item_type]}x{it.quantity} (tote {it.tote_id})"
            for it in o.items
        )
        print(f"  Order {o.order_id}: {items_str}  [total={o.total_items}]")
    print()

    print("Totes:")
    for t in totes:
        contents_str = ", ".join(
            f"Order{oid}:{SHAPE_NAMES[itype]}x{qty}"
            for oid, itype, qty in t.contents
        )
        print(f"  Tote {t.tote_id}: {contents_str}  [total={t.total_items}]")


def save_csvs(orders: List[Order], output_dir: str):
    """Save order data as CSVs matching the course format."""
    os.makedirs(output_dir, exist_ok=True)

    # order_itemtypes.csv
    with open(os.path.join(output_dir, "order_itemtypes.csv"), "w", newline="") as f:
        writer = csv.writer(f)
        for o in orders:
            writer.writerow([it.item_type for it in o.items])

    # order_quantities.csv
    with open(os.path.join(output_dir, "order_quantities.csv"), "w", newline="") as f:
        writer = csv.writer(f)
        for o in orders:
            writer.writerow([it.quantity for it in o.items])

    # orders_totes.csv
    with open(os.path.join(output_dir, "orders_totes.csv"), "w", newline="") as f:
        writer = csv.writer(f)
        for o in orders:
            writer.writerow([it.tote_id for it in o.items])


if __name__ == "__main__":
    orders, totes, params = generate_data(seed=100)
    print_summary(orders, totes, params)

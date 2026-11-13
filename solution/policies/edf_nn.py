"""Explored policy, design step 1 (superseded by Policy A, edf_nn_wait): EDF + nearest neighbor.

Kept to document the design history (report_findings.md, section 7). Policy letters
below use the earlier naming: A = edf_nn, A2 = edf_nn_skip_overdue, B = grow_2opt,
C = grow_2opt_wait.

Selection rule: try waiting parcels in order of earliest delivery_window_end (parcel ID
    breaks ties). Skip any parcel that would break capacity, range or the return cutoff, and
    keep trying later ones. Parcels already past their window are still selected first.
Routing rule: nearest neighbor from the hub. Each candidate is tested on the nearest-neighbor
    tour that includes it, because that tour can be longer than the selection order. The
    returned route is therefore always a route that has already passed the checks.
Timing rule: no waiting. The vehicle leaves whenever at least one parcel fits, even if that
    delivers the parcel before its window starts.

Complexity, for n waiting parcels and k parcels in the trip (k <= n):
    Time: O(n log n + n k^2). Sorting costs O(n log n), and each of the n candidates may
        need a nearest-neighbor tour costing O(k^2). Building the waiting list also scans
        every arrived parcel once. Worst case, when k grows with n, this is O(n^3).
    Space: O(n + k) for the sorted list and the trip.
"""

from typing import Dict, List

from simulator.models import Parcel, SimulationContext
from solution.policies.helpers import (
    nearest_neighbor_order, route_distance, waiting_parcels, within_limits,
)


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Return one trip: the most urgent parcels that fit, in nearest-neighbor order."""

    distances = context["travel_distance"]
    # Most urgent first; the parcel ID makes the order repeatable.
    by_deadline = sorted(
        waiting_parcels(parcel),
        key=lambda parcel_id: (parcel[parcel_id]["delivery_window_end"], parcel_id),
    )

    route: List[str] = []
    load = 0.0
    for parcel_id in by_deadline:
        # Capacity is the cheap check, so do it before building a tour.
        if load + parcel[parcel_id]["size"] > context["capacity"]:
            continue
        trial = nearest_neighbor_order(route + [parcel_id], parcel, distances)
        if within_limits(route_distance(trial, parcel, distances), context):
            route = trial
            load += parcel[parcel_id]["size"]
    return route

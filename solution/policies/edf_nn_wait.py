"""Policy A: Earliest Deadline First selection, nearest-neighbor routing, on-time-only trips.

Selection rule: candidates are waiting parcels that can still be on time (overdue parcels
    are never sent). Try them by earliest delivery_window_end (parcel ID breaks ties). Keep
    a parcel only if capacity allows, and the nearest-neighbor tour that includes it meets
    range and the return cutoff and delivers every parcel on it inside its window: none
    early, none late.
Routing rule: nearest neighbor from the hub: always drive to the closest remaining stop.
Timing rule: return [] if no parcel fits (nothing can be reached inside its window yet),
    or if the trip is nearly empty (load below MIN_FILL of capacity) and every parcel on
    it can still be on time one round later (slack of at least WAIT_SLACK minutes). The
    thresholds are Policy B's tuned values, not tuned separately for this policy.

Policy A and Policy B share the same timing rules and differ in selection and routing, so
    comparing them measures deadline-order selection with nearest-neighbor routing against
    cheapest-insertion trips with 2-opt.

Algorithms and data structures: sorting (deadline order); greedy selection; nearest-neighbor
    routing.

Complexity per dispatch call, for N arrived parcels, n candidates and k parcels in the trip:
    Time: O(N + n log n + n k^2). Each of the n candidates may need a nearest-neighbor tour,
        O(k^2), plus O(k) to check every window on it; the waiting test is O(k).
    Space: O(n + k).
"""

from typing import Dict, List

from simulator.models import Parcel, SimulationContext
from solution.policies.helpers import (
    HUB, MINUTES_PER_KM, can_still_be_on_time, departure_time, is_on_time,
    nearest_neighbor_order, route_distance, should_wait, waiting_parcels, within_limits,
)

MIN_FILL = 0.75     # A trip below this share of capacity counts as nearly empty.
WAIT_SLACK = 10.0   # Minutes every parcel must be able to wait: one planning interval.


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Return the most urgent parcels that all arrive inside their windows, or [] to wait."""

    distances = context["travel_distance"]
    departure = departure_time(context)
    # Most urgent first; overdue parcels are left out, since they can only be late.
    candidates = sorted(
        (p for p in waiting_parcels(parcel) if can_still_be_on_time(p, parcel, context)),
        key=lambda parcel_id: (parcel[parcel_id]["delivery_window_end"], parcel_id),
    )

    route: List[str] = []
    load = 0.0
    for parcel_id in candidates:
        # Capacity is the cheap check, so do it before building a tour.
        if load + parcel[parcel_id]["size"] > context["capacity"]:
            continue
        trial = nearest_neighbor_order(route + [parcel_id], parcel, distances)
        if (within_limits(route_distance(trial, parcel, distances), context)
                and all_inside_windows(trial, parcel, distances, departure)):
            route = trial
            load += parcel[parcel_id]["size"]

    if route and should_wait(route, parcel, context, min_fill=MIN_FILL, wait_slack=WAIT_SLACK):
        return []
    return route


def all_inside_windows(
    route: List[str], parcel: Dict[str, Parcel], distances: Dict[str, Dict[str, float]],
    departure: float,
) -> bool:
    """Return True if every parcel on the route arrives inside its window. O(k)."""

    arrival = departure
    location = HUB
    for parcel_id in route:
        destination = parcel[parcel_id]["delivery_location_id"]
        arrival += distances[location][destination] * MINUTES_PER_KM
        location = destination
        if not is_on_time(parcel[parcel_id], arrival):
            return False
    return True

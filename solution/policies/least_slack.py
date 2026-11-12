"""Policy C: Least Slack First selection from a min-heap, with Policy B's timing and filling.

Selection rule: candidates are waiting parcels that can still be on time and fit a trip
    alone. A parcel's slack is window_end - (departure + direct drive from the hub): how
    many minutes it can still afford to wait. The seed is the least-slack candidate that a
    direct drive reaches inside its window. The other candidates go into a min-heap keyed
    by (slack, window end, parcel ID) and are popped most urgent first. Each popped parcel
    is inserted at its cheapest feasible position, or skipped if none exists. A position is
    feasible if capacity, range and the 18:00 cutoff hold, the parcel arrives inside its
    window (never early, never late), and no parcel already on the trip is pushed past its
    window end.
Routing rule: insertion order, then 2-opt over the distinct stops (a move is kept only if
    strictly shorter and the on-time count does not fall).
Timing rule: return [] if no candidate can be reached inside its window yet, or if the trip
    is nearly empty (load below MIN_FILL of capacity) and every parcel on it can still be
    on time one round later (slack of at least WAIT_SLACK minutes). The thresholds are
    Policy B's tuned values, not tuned separately for this policy.
Filling rule: as Policy B, overdue parcels fill spare capacity where they delay no on-time
    parcel.

Policy B picks the parcel that adds the least distance; this policy picks the parcel that is
    most urgent and only uses distance to place it. Routing, timing and filling are the
    same, so comparing B and C measures distance-first against urgency-first selection.

Algorithms and data structures: binary min-heap (heapq) as a priority queue; greedy
    insertion; 2-opt local search.

Complexity per dispatch call, for N arrived parcels, n candidates, k parcels and s distinct
    stops in the trip, P 2-opt passes, m overdue parcels at L' locations:
    Filtering O(N); heapify O(n); n pops O(n log n); each popped parcel is priced at s + 1
    positions after an O(s + k) timing pass, so O(n (s + k)); filling as Policy B.
    Time: O(N + n log n + n (s + k) + P s^2 (s + k) + m log m + k (L' s + s + k)).
    Space: O(N + k) (the heap holds n parcels).
"""

import heapq
from typing import Dict, List, Optional

from simulator.models import Parcel, SimulationContext
from solution.policies.helpers import (
    HUB, MINUTES_PER_KM, departure_time, fill_overdue, is_on_time, on_time_candidates,
    overdue_parcels, reachable_in_window, should_wait, trip_timing, two_opt, within_limits,
)

MIN_FILL = 0.75     # A trip below this share of capacity counts as nearly empty.
WAIT_SLACK = 10.0   # Minutes every parcel must be able to wait: one planning interval.


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Return a trip built most-urgent-first from a min-heap, or [] to wait."""

    distances = context["travel_distance"]
    departure = departure_time(context)

    def slack(parcel_id: str) -> float:
        """Minutes the parcel can still wait before a direct drive would be late."""
        direct = distances[HUB][parcel[parcel_id]["delivery_location_id"]] * MINUTES_PER_KM
        return parcel[parcel_id]["delivery_window_end"] - (departure + direct)

    candidates = on_time_candidates(parcel, context)
    seeds = [p for p in candidates if reachable_in_window(p, parcel, context)]
    if not seeds:
        return []
    seed = min(seeds, key=lambda p: (slack(p), parcel[p]["delivery_window_end"], p))

    heap = [(slack(p), parcel[p]["delivery_window_end"], p) for p in candidates if p != seed]
    heapq.heapify(heap)

    route = [seed]
    load = parcel[seed]["size"]
    while heap:
        _, _, parcel_id = heapq.heappop(heap)
        if load + parcel[parcel_id]["size"] > context["capacity"] + 1e-9:
            continue
        position = cheapest_feasible_position(route, parcel_id, parcel, context)
        if position is not None:
            route.insert(position, parcel_id)
            load += parcel[parcel_id]["size"]

    route = two_opt(route, parcel, distances, departure)
    if should_wait(route, parcel, context, min_fill=MIN_FILL, wait_slack=WAIT_SLACK):
        return []
    return fill_overdue(route, overdue_parcels(parcel, context, set(route)), parcel, context)


def cheapest_feasible_position(
    route: List[str], parcel_id: str, parcel: Dict[str, Parcel], context: SimulationContext
) -> Optional[int]:
    """Return the route index where parcel_id adds the least km on time, or None. O(s + k)."""

    distances = context["travel_distance"]
    departure = departure_time(context)
    record = parcel[parcel_id]
    location = record["delivery_location_id"]
    groups, stops, arrivals, total, slack = trip_timing(route, parcel, distances, departure)

    best = None  # (added km, stop position)
    for position in range(len(stops) + 1):
        before = HUB if position == 0 else stops[position - 1]
        after = HUB if position == len(stops) else stops[position]
        added = (distances[before][location] + distances[location][after]
                 - distances[before][after])
        if best is not None and added >= best[0]:
            continue
        arrival = (departure if position == 0 else arrivals[position - 1]) \
            + distances[before][location] * MINUTES_PER_KM
        if not is_on_time(record, arrival):
            continue
        if added * MINUTES_PER_KM > slack[position] + 1e-9:
            continue
        if not within_limits(total + added, context):
            continue
        best = (added, position)
    if best is None:
        return None
    # Insert after the last parcel of the stop before position (or at the front).
    return sum(len(g) for g in groups[:best[1]])

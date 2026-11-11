"""Policy E: Least Slack First selection from a min-heap, with Policy C's timing rules.

Selection rule: candidates are waiting parcels that can still be on time and fit a trip
    alone. A parcel's slack is window_end - (departure + direct drive from the hub): how
    many minutes it can still afford to wait. The seed is the least-slack parcel that a
    direct drive reaches inside its window (as in Policy C). The other candidates go into
    a min-heap keyed by (slack, window end, parcel ID) and are popped most urgent first.
    Each popped parcel is inserted at its cheapest feasible position, or skipped if none
    exists. A position is feasible if capacity, range and the 18:00 cutoff hold, the
    parcel arrives inside its window (never early, never late), and no parcel already on
    the trip is pushed past its window end.
Routing rule: insertion order, then the same 2-opt as Policies B and C (keep a move only if
    strictly shorter and the on-time count does not fall).
Timing rule: as Policy C. Return [] if no parcel can be reached inside its window yet, or
    if the trip is nearly empty and waiting one round loses nothing.

Policy C picks the parcel that adds the least distance; this policy picks the parcel that is
    most urgent and only uses distance to place it. Everything else is the same, so the
    difference between C and E measures urgency-first against distance-first selection.

Algorithms and data structures: binary min-heap (heapq) as the priority queue; greedy
    insertion; 2-opt local search.

Complexity per dispatch call, for N arrived parcels, n candidates, k parcels and s distinct
    stops in the trip, P 2-opt passes:
    Filtering O(N); heapify O(n); n pops O(n log n); each popped parcel is priced at s + 1
    positions after an O(s + k) pass for arrival times and slack, so O(n (s + k)).
    Time: O(N + n log n + n (s + k) + P s^2 (s + k)). Space: O(N + k) (the heap holds n).
"""

import heapq
import math
from typing import Dict, List, Optional

from simulator.models import Parcel, SimulationContext
from solution.policies.grow_2opt_wait import _should_wait
from solution.policies.helpers import (
    HUB, MINUTES_PER_KM, can_still_be_on_time, departure_time, group_by_stop, is_on_time,
    route_distance, stop_arrivals, stops_distance, two_opt, waiting_parcels, within_limits,
)


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Return a trip built most-urgent-first from a min-heap, or [] to wait."""

    distances = context["travel_distance"]
    departure = departure_time(context)

    def slack(parcel_id: str) -> float:
        """Minutes the parcel can still wait before a direct drive would be late."""
        direct = distances[HUB][parcel[parcel_id]["delivery_location_id"]] * MINUTES_PER_KM
        return parcel[parcel_id]["delivery_window_end"] - (departure + direct)

    candidates = [
        parcel_id for parcel_id in waiting_parcels(parcel)
        if can_still_be_on_time(parcel_id, parcel, context)
        and within_limits(route_distance([parcel_id], parcel, distances), context)
    ]
    # Seed: least slack among parcels a direct drive reaches inside their window.
    seeds = [
        parcel_id for parcel_id in candidates
        if departure + distances[HUB][parcel[parcel_id]["delivery_location_id"]]
        * MINUTES_PER_KM >= parcel[parcel_id]["delivery_window_start"]
    ]
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
    if _should_wait(route, parcel, context):
        return []
    return route


def cheapest_feasible_position(
    route: List[str], parcel_id: str, parcel: Dict[str, Parcel], context: SimulationContext
) -> Optional[int]:
    """Return the route index where parcel_id adds the least km on time, or None. O(s + k)."""

    distances = context["travel_distance"]
    departure = departure_time(context)
    record = parcel[parcel_id]
    location = record["delivery_location_id"]

    groups = group_by_stop(route, parcel)
    stops = [parcel[g[0]]["delivery_location_id"] for g in groups]
    arrivals = stop_arrivals(stops, distances, departure)
    total = stops_distance(stops, distances)
    # slack[i]: minutes stops i.. can be delayed before an on-time parcel turns late.
    slack = [math.inf] * (len(stops) + 1)
    for i in range(len(stops) - 1, -1, -1):
        own = math.inf
        for other in groups[i]:
            if is_on_time(parcel[other], arrivals[i]):
                own = min(own, parcel[other]["delivery_window_end"] - arrivals[i])
        slack[i] = min(own, slack[i + 1])

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

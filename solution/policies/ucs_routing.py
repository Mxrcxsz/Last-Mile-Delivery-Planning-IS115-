"""Policy D: Policy B's trips, with the stop order found by exact uniform-cost search.

Selection rule: as Policy B (cheapest insertion from the most urgent parcel that a direct
    drive reaches inside its window; every parcel inside its window, nothing early).
Timing rule: as Policy B (wait if nothing is reachable in its window yet, or if the trip is
    nearly empty and waiting one round loses nothing; same MIN_FILL and WAIT_SLACK).
Filling rule: as Policy B (overdue parcels fill spare capacity where they delay no on-time
    parcel), applied after the exact routing.
Routing rule: the trip is first ordered by 2-opt, as in Policy B. Its parcels are then
    grouped by location into stops. Each stop has a
    feasible arrival interval [latest window start, earliest window end] of its parcels.
    If the trip has at most MAX_STOPS stops, uniform-cost search (UCS) finds the shortest
    order that visits every stop inside its interval and returns to the hub:
      * a state is (current location, set of visited stops), with cost = km driven so far;
      * at 60 km/h km equals minutes, so the cost also gives the arrival time, and a move
        to a stop is allowed only if it arrives inside that stop's interval;
      * states are expanded cheapest first from a min-heap, so the first complete tour
        popped is the shortest feasible one.
    The 2-opt route is feasible, so its length is an upper bound: any partial tour that
    cannot return to the hub in fewer km is pruned. If no shorter order exists, or the trip
    has more than MAX_STOPS stops, the 2-opt route is kept.
    Two states with the same location and visited set are not merged: with time windows
    and no waiting, arriving later can make a later stop feasible, so the cheaper of the
    two does not dominate the other.

Why this policy: 2-opt is a local search. Policies B and D differ only in this routing
    step, so comparing them measures how much an exact (optimal) order gains over 2-opt.

Algorithms and data structures: uniform-cost search (a best-first graph search, Dijkstra's
    algorithm on the state graph); a binary min-heap (heapq) as the frontier; a bitmask for
    the visited set.

Complexity per dispatch call: Policy B's cost, plus the search. With s <= MAX_STOPS stops,
    a partial tour of d stops is one of s!/(s - d)! orders, so the search holds at most
    sum over d of s!/(s - d)! <= e s! states. Each state stores its order of up to s stops,
    so space is O(s! s). Each popped state pushes up to s children, each copying an order
    of O(s) and costing O(log(e s!)) = O(s log s) on the heap, so time is O(s! s^2 log s).
    MAX_STOPS = 8 caps this at a constant (8! = 40,320 orders), and the upper bound and
    the windows prune most of them.
    In general (no cap) exact routing is exponential in s, which is why the cap exists.
"""

import heapq
from typing import Dict, List, Optional

from simulator.models import Parcel, SimulationContext
from solution.policies.helpers import (
    HUB, MINUTES_PER_KM, departure_time, fill_overdue, grow_trip, on_time_candidates,
    overdue_parcels, reachable_in_window, route_distance, should_wait, two_opt, within_limits,
)

MAX_STOPS = 8       # 71% of Policy B's trips have at most 8 distinct stops.
MIN_FILL = 0.75     # As Policy B: a trip below this share of capacity counts as nearly empty.
WAIT_SLACK = 10.0   # As Policy B: minutes every parcel must be able to wait.


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Return Policy B's trip, reordered optimally when it has at most MAX_STOPS stops."""

    candidates = on_time_candidates(parcel, context)
    seeds = [p for p in candidates if reachable_in_window(p, parcel, context)]
    if not seeds:
        return []
    seed = min(seeds, key=lambda p: (parcel[p]["delivery_window_end"], p))
    route = grow_trip(seed, candidates, parcel, context, allow_early=False)
    route = two_opt(route, parcel, context["travel_distance"], departure_time(context))
    better = exact_order(route, parcel, context)
    if better is not None:
        route = better

    if should_wait(route, parcel, context, min_fill=MIN_FILL, wait_slack=WAIT_SLACK):
        return []
    return fill_overdue(route, overdue_parcels(parcel, context, set(route)), parcel, context)


def exact_order(
    route: List[str], parcel: Dict[str, Parcel], context: SimulationContext
) -> Optional[List[str]]:
    """Return a strictly shorter order with every parcel on time, or None if there is none."""

    distances = context["travel_distance"]
    departure = departure_time(context)

    # One stop per location, keeping each location's parcels in their route order.
    stops: Dict[str, List[str]] = {}
    for parcel_id in route:
        stops.setdefault(parcel[parcel_id]["delivery_location_id"], []).append(parcel_id)
    if len(stops) > MAX_STOPS or len(stops) < 2:
        return None
    locations = list(stops)
    opens = [max(parcel[p]["delivery_window_start"] for p in stops[loc]) for loc in locations]
    closes = [min(parcel[p]["delivery_window_end"] for p in stops[loc]) for loc in locations]
    if any(o > c for o, c in zip(opens, closes)):
        return None  # No single arrival time suits all parcels at some location.

    bound = route_distance(route, parcel, distances)  # 2-opt route: feasible, an upper bound
    full = (1 << len(locations)) - 1
    # Frontier entries: (km so far, tie-break counter, location, visited bitmask, order).
    frontier = [(0.0, 0, HUB, 0, ())]
    counter = 1
    while frontier:
        km, _, location, visited, order = heapq.heappop(frontier)
        if location == HUB and visited == full:
            # First complete tour popped is the shortest; keep it only if it beats 2-opt's.
            if km < bound - 1e-9:
                result = [p for index in order for p in stops[locations[index]]]
                if within_limits(route_distance(result, parcel, distances), context):
                    return result
            return None
        if visited == full:
            back = km + distances[location][HUB]
            if back < bound - 1e-9:
                heapq.heappush(frontier, (back, counter, HUB, full, order))
                counter += 1
            continue
        for index, nxt in enumerate(locations):
            if visited & (1 << index):
                continue
            reach = km + distances[location][nxt]
            arrival = departure + reach * MINUTES_PER_KM
            if not opens[index] <= arrival <= closes[index]:
                continue
            # Prune: even returning straight to the hub would not beat the bound.
            if reach + distances[nxt][HUB] >= bound - 1e-9:
                continue
            heapq.heappush(frontier, (reach, counter, nxt, visited | (1 << index), order + (index,)))
            counter += 1
    return None

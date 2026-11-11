"""Policy D: Policy C's trips, with the stop order found by exact uniform-cost search.

Selection rule: exactly Policy C (cheapest insertion from the most urgent parcel, every
    parcel inside its window, nothing early).
Timing rule: exactly Policy C (wait if nothing is reachable in its window yet, or if the
    trip is nearly empty and waiting one round loses nothing).
Routing rule: the parcels of C's trip are grouped by location into stops. Each stop has a
    feasible arrival interval [latest window start, earliest window end] of its parcels.
    If the trip has at most MAX_STOPS stops, uniform-cost search (UCS) finds the shortest
    order that visits every stop inside its interval and returns to the hub:
      * a state is (current location, set of visited stops), with cost = km driven so far;
      * at 60 km/h km equals minutes, so the cost also gives the arrival time, and a move
        to a stop is allowed only if it arrives inside that stop's interval;
      * states are expanded cheapest first from a min-heap, so the first complete tour
        popped is the shortest feasible one.
    C's own 2-opt route is feasible, so its length is an upper bound: any partial tour that
    cannot return to the hub in fewer km is pruned. If no shorter order exists, or the trip
    has more than MAX_STOPS stops, C's route is kept.
    Two states with the same location and visited set are not merged: with time windows
    and no waiting, arriving later can make a later stop feasible, so the cheaper of the
    two does not dominate the other.

Why this policy: Policy C's 2-opt is a local search. This policy measures how much an exact
    (optimal) order gains over it, everything else equal.

Algorithms and data structures: uniform-cost search (a best-first graph search, Dijkstra's
    algorithm on the state graph); a binary min-heap (heapq) as the frontier; a bitmask for
    the visited set.

Complexity per dispatch call: Policy C's cost, plus the search. With s <= MAX_STOPS stops,
    there are at most s! partial orders of each length, so the search is O(s! s log(s! s))
    time and O(s! s) space in the worst case. MAX_STOPS = 8 caps this at a constant
    (8! = 40,320 orders), and the upper bound and the windows prune most of them.
    In general (no cap) exact routing is exponential in s, which is why the cap exists.
"""

import heapq
from typing import Dict, List, Optional

from simulator.models import Parcel, SimulationContext
from solution.policies import grow_2opt_wait
from solution.policies.helpers import (
    HUB, MINUTES_PER_KM, departure_time, route_distance, within_limits,
)

MAX_STOPS = 8  # 71% of Policy C's trips have at most 8 distinct stops.


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Return Policy C's trip, reordered optimally when it has at most MAX_STOPS stops."""

    route = grow_2opt_wait.dispatch(parcel, context)
    if not route:
        return route
    better = exact_order(route, parcel, context)
    return better if better is not None else route


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

    bound = route_distance(route, parcel, distances)  # C's route: feasible, so an upper bound
    full = (1 << len(locations)) - 1
    # Frontier entries: (km so far, tie-break counter, location, visited bitmask, order).
    frontier = [(0.0, 0, HUB, 0, ())]
    counter = 1
    while frontier:
        km, _, location, visited, order = heapq.heappop(frontier)
        if location == HUB and visited == full:
            # First complete tour popped is the shortest; keep it only if it beats C's.
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

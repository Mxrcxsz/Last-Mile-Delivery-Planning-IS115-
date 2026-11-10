"""Shared helpers for the dispatch policies. Inputs are read-only and never modified."""

import math
from typing import Dict, List

from simulator.models import Parcel, SimulationContext

HUB = "HUB"


def waiting_parcels(parcel: Dict[str, Parcel]) -> List[str]:
    """Return the IDs of parcels not yet assigned or delivered. O(N) for N arrived parcels."""

    waiting = []
    for parcel_id, record in parcel.items():
        if record["vehicle_assigned"] is None and record["delivery_time"] is None:
            waiting.append(parcel_id)
    return waiting


def route_distance(
    route: List[str], parcel: Dict[str, Parcel], distances: Dict[str, Dict[str, float]]
) -> float:
    """Return the km of the trip HUB -> stops -> HUB, following the directed legs. O(k)."""

    legs = []
    location = HUB
    for parcel_id in route:
        destination = parcel[parcel_id]["delivery_location_id"]
        legs.append(distances[location][destination])
        location = destination
    legs.append(distances[location][HUB])
    # fsum is what the simulator uses, so both sides get exactly the same total.
    return math.fsum(legs)


def within_limits(distance: float, context: SimulationContext) -> bool:
    """Return True if a trip of this many km meets the range and return-cutoff rules. O(1)."""

    # At 60 km/h, km also equals travel time in minutes.
    departure = context["current_time"] + context["departure_delay"]
    return (distance <= context["max_trip_distance_km"]
            and departure + distance <= context["return_cutoff"])


def nearest_neighbor_order(
    stops: List[str], parcel: Dict[str, Parcel], distances: Dict[str, Dict[str, float]]
) -> List[str]:
    """Reorder parcels by always driving to the closest remaining stop. O(k^2) time, O(k) space.

    Ties go to the parcel listed first in stops, so the result is deterministic.
    """

    remaining = list(stops)
    ordered = []
    location = HUB
    while remaining:
        best = remaining[0]
        best_distance = distances[location][parcel[best]["delivery_location_id"]]
        for parcel_id in remaining:
            distance = distances[location][parcel[parcel_id]["delivery_location_id"]]
            if distance < best_distance:
                best = parcel_id
                best_distance = distance
        ordered.append(best)
        remaining.remove(best)
        location = parcel[best]["delivery_location_id"]
    return ordered


# ---------------------------------------------------------------------------
# Added for Policies B (grow_2opt) and C (grow_2opt_wait). Functions above are unchanged.
# ---------------------------------------------------------------------------

def departure_time(context: SimulationContext) -> float:
    """Return when a trip planned now would leave the hub. O(1)."""

    return context["current_time"] + context["departure_delay"]


def can_still_be_on_time(
    parcel_id: str, parcel: Dict[str, Parcel], context: SimulationContext
) -> bool:
    """Return True if driving straight to the parcel would reach it by its window end. O(1).

    This is the A2 idea: a parcel that fails this test can no longer count as on time,
    whatever trip it joins, so spending capacity on it gains nothing for the metric.
    """

    record = parcel[parcel_id]
    direct = context["travel_distance"][HUB][record["delivery_location_id"]]
    return departure_time(context) + direct <= record["delivery_window_end"]


def stop_arrivals(
    stops: List[str], distances: Dict[str, Dict[str, float]], departure: float
) -> List[float]:
    """Return the arrival time at each location in stops, leaving the hub at departure. O(s)."""

    arrivals = []
    time = departure
    location = HUB
    for stop in stops:
        time += distances[location][stop]
        arrivals.append(time)
        location = stop
    return arrivals


def stops_distance(stops: List[str], distances: Dict[str, Dict[str, float]]) -> float:
    """Return the km of HUB -> stops -> HUB over the directed legs. O(s)."""

    path = [HUB] + stops + [HUB]
    return math.fsum(distances[a][b] for a, b in zip(path, path[1:]))


def is_on_time(record: Parcel, arrival: float) -> bool:
    """Return True if arriving at this time is inside the window, both ends included. O(1)."""

    return record["delivery_window_start"] <= arrival <= record["delivery_window_end"]


def group_by_stop(route: List[str], parcel: Dict[str, Parcel]) -> List[List[str]]:
    """Merge consecutive parcels with the same location into one stop. O(k).

    Parcels in one stop are delivered at the same moment (service time is zero), so
    routing only needs to order the stops, not the parcels inside them.
    """

    groups: List[List[str]] = []
    for parcel_id in route:
        location = parcel[parcel_id]["delivery_location_id"]
        if groups and parcel[groups[-1][0]]["delivery_location_id"] == location:
            groups[-1].append(parcel_id)
        else:
            groups.append([parcel_id])
    return groups


def two_opt(
    route: List[str], parcel: Dict[str, Parcel], distances: Dict[str, Dict[str, float]],
    departure: float,
) -> List[str]:
    """Improve the stop order with 2-opt on a directed distance table.

    A move reverses the stops between positions i and j. Distances are directed, so the
    reversed segment is driven the other way and its length changes too: every candidate
    is costed in full rather than by comparing four edges. A move is kept only if it makes
    the trip strictly shorter and does not reduce the number of parcels delivered on time.
    The search restarts after each kept move (first improvement) and stops when no move
    helps. Each kept move shortens the trip, so the loop always ends.

    Complexity, for s distinct stops and k parcels: one pass tries O(s^2) moves and costs
    each in O(s + k), so O(s^2 (s + k)) per pass. Space O(s + k).
    """

    groups = group_by_stop(route, parcel)
    if len(groups) < 3:
        return list(route)

    def score(order: List[List[str]]):
        stops = [parcel[g[0]]["delivery_location_id"] for g in order]
        arrivals = stop_arrivals(stops, distances, departure)
        on_time = sum(
            is_on_time(parcel[p], arrival) for g, arrival in zip(order, arrivals) for p in g
        )
        return on_time, stops_distance(stops, distances)

    best_on_time, best_km = score(groups)
    improved = True
    while improved:
        improved = False
        for i in range(len(groups) - 1):
            for j in range(i + 1, len(groups)):
                candidate = groups[:i] + groups[i:j + 1][::-1] + groups[j + 1:]
                on_time, km = score(candidate)
                if on_time >= best_on_time and km < best_km - 1e-9:
                    groups, best_on_time, best_km = candidate, on_time, km
                    improved = True
                    break
            if improved:
                break
    return [parcel_id for group in groups for parcel_id in group]


def grow_trip(
    seed: str, candidates: List[str], parcel: Dict[str, Parcel], context: SimulationContext,
    *, allow_early: bool,
) -> List[str]:
    """Grow a trip from seed by cheapest insertion, keeping every on-time parcel on time.

    Data structure: candidates are bucketed in a hash map keyed by delivery location, and
    each bucket is a list sorted by (window end, parcel ID). All parcels at one location
    share the same insertion cost, so each step prices each location once per position.

    Each step considers every location and every insertion position in the current stop
    list, and adds the single parcel whose insertion adds the least distance. Ties go to
    the earliest window end, then parcel ID. An insertion is allowed only if:
      * the load stays within capacity, and the trip stays within range and the cutoff;
      * the new parcel arrives no later than its window end (it would count as on time);
      * if allow_early is False, it also arrives no earlier than its window start;
      * no parcel already on the trip that is on time is pushed past its window end.
    Growing stops when no parcel can be added.

    Complexity, for n candidates, L distinct locations (L <= n) and k parcels in the trip:
    bucketing costs O(n log n). Each of the k steps prices L locations at up to k + 1
    positions and scans a bucket to find a parcel that fits, so O(L k + n) per step and
    O(n log n + k (L k + n)) per trip. Space O(n + k).
    """

    distances = context["travel_distance"]
    departure = departure_time(context)
    capacity = context["capacity"]

    buckets: Dict[str, List[str]] = {}
    for parcel_id in sorted(
        candidates, key=lambda p: (parcel[p]["delivery_window_end"], p)
    ):
        if parcel_id != seed:
            buckets.setdefault(parcel[parcel_id]["delivery_location_id"], []).append(parcel_id)

    route = [seed]
    load = parcel[seed]["size"]
    while buckets:
        groups = group_by_stop(route, parcel)
        stops = [parcel[g[0]]["delivery_location_id"] for g in groups]
        arrivals = stop_arrivals(stops, distances, departure)
        total = stops_distance(stops, distances)
        # slack[i]: how many minutes stops i.. can be delayed before an on-time parcel turns late.
        slack = [math.inf] * (len(stops) + 1)
        for i in range(len(stops) - 1, -1, -1):
            own = math.inf
            for parcel_id in groups[i]:
                if is_on_time(parcel[parcel_id], arrivals[i]):
                    own = min(own, parcel[parcel_id]["delivery_window_end"] - arrivals[i])
            slack[i] = min(own, slack[i + 1])

        best = None  # (added km, window end, parcel ID, stop position, location)
        for location in list(buckets):
            bucket = buckets[location]
            for position in range(len(stops) + 1):
                before = HUB if position == 0 else stops[position - 1]
                after = HUB if position == len(stops) else stops[position]
                added = (distances[before][location] + distances[location][after]
                         - distances[before][after])
                if best is not None and added > best[0] + 1e-9:
                    continue
                if added > slack[position] + 1e-9 or not within_limits(total + added, context):
                    continue
                arrival = (departure if position == 0 else arrivals[position - 1]) \
                    + distances[before][location]
                for parcel_id in bucket:  # most urgent first
                    record = parcel[parcel_id]
                    if load + record["size"] > capacity + 1e-9:
                        continue
                    if arrival > record["delivery_window_end"]:
                        continue
                    if not allow_early and arrival < record["delivery_window_start"]:
                        continue
                    key = (added, record["delivery_window_end"], parcel_id, position, location)
                    if best is None or key < best:
                        best = key
                    break
        if best is None:
            break
        _, _, parcel_id, position, location = best
        buckets[location].remove(parcel_id)
        if not buckets[location]:
            del buckets[location]
        # Insert after the last parcel of the stop before position (or at the front).
        index = sum(len(g) for g in groups[:position])
        route.insert(index, parcel_id)
        load += parcel[parcel_id]["size"]
    return route

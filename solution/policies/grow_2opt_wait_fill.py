"""Policy C2: Policy C, then fill the trip's spare capacity with overdue parcels.

Selection rule: first build exactly Policy C's trip (or wait, if C waits). Then repeatedly
    add the overdue parcel (one that can no longer be on time, so any delivery is late)
    whose cheapest insertion adds the fewest km (ties: earliest window end, then parcel
    ID). An insertion is allowed only if capacity, range and the 18:00 cutoff still hold,
    and the extra driving does not push any on-time parcel on the trip past its window end.
    Parcels that can still be on time but are not on C's trip are never added here; they
    stay at the hub for a later trip, where they can count as on time.
Routing rule: C's order, with each overdue parcel inserted at its cheapest allowed position.
    Inserting at an existing stop for the same location adds 0 km and delays nobody.
Timing rule: as Policy C. Overdue parcels only ride on trips C sends anyway: they never
    make a vehicle leave, wait or take an extra trip.

Because no on-time parcel is delayed, C2 delivers every parcel on time that C's trip
    would, so the change can only add (late) deliveries to the same trip. Over a whole day
    trips can still drift apart from C's, since longer trips return later.

Algorithms and data structures: as Policy C, plus a second cheapest-insertion pass using a
    hash map from location to a deadline-sorted list of overdue parcels.

Complexity per dispatch call: Policy C's cost, plus the filling pass. For m overdue
    parcels at L' distinct locations, s stops and k parcels in the trip: bucketing costs
    O(m log m); each of up to k added parcels prices L' locations at s + 1 positions
    after an O(s + k) pass for arrivals and slack, so O(m log m + k (L' s + s + k)).
    Space O(m + k).
"""

import math
from typing import Dict, List

from simulator.models import Parcel, SimulationContext
from solution.policies import grow_2opt_wait
from solution.policies.helpers import (
    HUB, can_still_be_on_time, departure_time, group_by_stop, is_on_time, stop_arrivals,
    stops_distance, waiting_parcels, within_limits,
)


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Return Policy C's trip with overdue parcels added where they delay no on-time parcel."""

    route = grow_2opt_wait.dispatch(parcel, context)
    if not route:
        return route
    on_trip = set(route)
    overdue = [
        parcel_id for parcel_id in waiting_parcels(parcel)
        if parcel_id not in on_trip and not can_still_be_on_time(parcel_id, parcel, context)
    ]
    return fill_overdue(route, overdue, parcel, context)


def fill_overdue(
    route: List[str], overdue: List[str], parcel: Dict[str, Parcel], context: SimulationContext
) -> List[str]:
    """Insert overdue parcels by cheapest insertion without delaying any on-time parcel."""

    distances = context["travel_distance"]
    departure = departure_time(context)
    capacity = context["capacity"]

    # All parcels at one location cost the same to insert, so price each location once.
    buckets: Dict[str, List[str]] = {}
    for parcel_id in sorted(overdue, key=lambda p: (parcel[p]["delivery_window_end"], p)):
        buckets.setdefault(parcel[parcel_id]["delivery_location_id"], []).append(parcel_id)

    route = list(route)
    load = sum(parcel[p]["size"] for p in route)
    while buckets:
        groups = group_by_stop(route, parcel)
        stops = [parcel[g[0]]["delivery_location_id"] for g in groups]
        arrivals = stop_arrivals(stops, distances, departure)
        total = stops_distance(stops, distances)
        # slack[i]: minutes stops i.. can be delayed before an on-time parcel turns late.
        slack = [math.inf] * (len(stops) + 1)
        for i in range(len(stops) - 1, -1, -1):
            own = math.inf
            for parcel_id in groups[i]:
                if is_on_time(parcel[parcel_id], arrivals[i]):
                    own = min(own, parcel[parcel_id]["delivery_window_end"] - arrivals[i])
            slack[i] = min(own, slack[i + 1])

        best = None  # (added km, window end, parcel ID, stop position)
        for location, bucket in buckets.items():
            # Most overdue parcel at this location that still fits the load.
            fitting = next(
                (p for p in bucket if load + parcel[p]["size"] <= capacity + 1e-9), None
            )
            if fitting is None:
                continue
            for position in range(len(stops) + 1):
                before = HUB if position == 0 else stops[position - 1]
                after = HUB if position == len(stops) else stops[position]
                added = (distances[before][location] + distances[location][after]
                         - distances[before][after])
                # The detour delays every later stop by `added` minutes (km == minutes).
                if added > slack[position] + 1e-9 or not within_limits(total + added, context):
                    continue
                key = (added, parcel[fitting]["delivery_window_end"], fitting, position)
                if best is None or key < best:
                    best = key
        if best is None:
            break
        _, _, parcel_id, position = best
        bucket = buckets[parcel[parcel_id]["delivery_location_id"]]
        bucket.remove(parcel_id)
        if not bucket:
            del buckets[parcel[parcel_id]["delivery_location_id"]]
        # Insert after the last parcel of the stop before position (or at the front).
        route.insert(sum(len(g) for g in groups[:position]), parcel_id)
        load += parcel[parcel_id]["size"]
    return route

"""Policy B: urgent seed, grow by cheapest insertion, then improve the order with 2-opt.

Selection rule: a parcel is overdue if departure time + distance from the hub to its location
    > its delivery_window_end, as in Policy A2. Seed the trip with the most urgent parcel
    (earliest delivery_window_end, parcel ID breaks ties) that can still be on time and fits
    on its own; if none can be on time, seed with the most urgent overdue parcel that fits.
    Then repeatedly add the parcel that adds the fewest km at its cheapest position, among
    the parcels that can still be on time and keep the trip within capacity, range and the
    return cutoff (parcel ID breaks ties). When none fits, do the same with the overdue
    parcels. Stop when nothing else fits.
Routing rule: each parcel is placed at its cheapest insertion position as it is added. When
    the trip is full, 2-opt reverses segments of the route while that makes it shorter.
    2-opt only ever shortens the route, so the result still passes the checks. It minimises
    distance, not lateness, so it can move the urgent seed later in the trip.
Timing rule: no waiting. The vehicle leaves whenever at least one parcel fits, even if that
    delivers the parcel before its window starts.

Complexity, for n waiting parcels and k parcels in the trip (k <= n):
    Time: O(n log n + n k^2 + p k^3). Sorting costs O(n log n). Each of the k growth steps
        tries up to n candidates, and finding a candidate's cheapest position costs O(k).
        Each 2-opt pass tries O(k^2) reversals and scores each in O(k); p is the number of
        passes, which is small in practice because every pass but the last shortens the
        route. Building the waiting list also scans every arrived parcel once.
    Space: O(n + k) for the two groups and the trip.
"""

from typing import Dict, List

from simulator.models import Parcel, SimulationContext
from solution.policies.helpers import (
    HUB, MINUTES_PER_KM, cheapest_insertion, route_distance, two_opt, waiting_parcels,
    within_limits,
)


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Return one trip: an urgent seed plus the parcels that are cheapest to add, 2-opt ordered."""

    return two_opt(grow_trip(parcel, context), parcel, context["travel_distance"])


def grow_trip(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Return the seeded, grown trip in cheapest-insertion order, before any 2-opt.

    Shared with the policies that build on B, which change only the routing or timing.
    """

    distances = context["travel_distance"]
    departure = context["current_time"] + context["departure_delay"]

    # Split the waiting parcels: can they still arrive by their window end?
    can_be_on_time = []
    overdue = []
    for parcel_id in waiting_parcels(parcel):
        record = parcel[parcel_id]
        # Earliest possible arrival: drive straight from the hub.
        earliest_arrival = (departure
                            + distances[HUB][record["delivery_location_id"]] * MINUTES_PER_KM)
        if earliest_arrival > record["delivery_window_end"]:
            overdue.append(parcel_id)
        else:
            can_be_on_time.append(parcel_id)

    def by_deadline(parcel_id: str):
        """Sort key: earliest window end first; the parcel ID makes the order repeatable."""
        return (parcel[parcel_id]["delivery_window_end"], parcel_id)

    # Seed: the most urgent parcel that fits alone, preferring ones that can be on time.
    route: List[str] = []
    load = 0.0
    distance = 0.0
    for parcel_id in sorted(can_be_on_time, key=by_deadline) + sorted(overdue, key=by_deadline):
        if parcel[parcel_id]["size"] > context["capacity"]:
            continue
        distance = route_distance([parcel_id], parcel, distances)
        if within_limits(distance, context):
            route = [parcel_id]
            load = parcel[parcel_id]["size"]
            break
    if not route:
        return []

    # Grow: on-time candidates first, then overdue ones, each time adding the cheapest parcel.
    for group in (can_be_on_time, overdue):
        remaining = set(group) - set(route)
        while remaining:
            best = None
            for parcel_id in remaining:
                if load + parcel[parcel_id]["size"] > context["capacity"]:
                    continue
                position, added = cheapest_insertion(route, parcel_id, parcel, distances)
                if not within_limits(distance + added, context):
                    continue
                if best is None or (added, parcel_id) < (best[1], best[0]):
                    best = (parcel_id, added, position)
            if best is None:
                break
            parcel_id, _, position = best
            remaining.discard(parcel_id)
            trial = route[:position] + [parcel_id] + route[position:]
            # Re-check with the exact total, since summing deltas can drift in the last digit.
            trial_distance = route_distance(trial, parcel, distances)
            if within_limits(trial_distance, context):
                route = trial
                distance = trial_distance
                load += parcel[parcel_id]["size"]

    return route

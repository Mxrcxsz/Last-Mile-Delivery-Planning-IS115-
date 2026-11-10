"""Policy A2: Earliest Deadline First with overdue parcels last, Nearest-Neighbor routing.

Selection rule: a parcel is overdue if departure time + distance from the hub to its location
    > its delivery_window_end, so it cannot be on time even as the first stop. Try the
    parcels that can still be on time first, by earliest delivery_window_end (parcel ID
    breaks ties), then the overdue parcels in the same order. Skip any parcel that would
    break capacity, range or the return cutoff, and keep trying later ones.
Routing rule: nearest neighbor from the hub. Each candidate is tested on the nearest-neighbor
    tour that includes it, because that tour can be longer than the selection order. The
    returned route is therefore always a route that has already passed the checks.
Timing rule: no waiting. The vehicle leaves whenever at least one parcel fits, even if that
    delivers the parcel before its window starts.

Complexity, for n waiting parcels and k parcels in the trip (k <= n):
    Time: O(n log n + n k^2). Splitting into two groups costs O(n), sorting them O(n log n),
        and each of the n candidates may need a nearest-neighbor tour costing O(k^2).
        Building the waiting list also scans every arrived parcel once. Worst case, when k
        grows with n, this is O(n^3).
    Space: O(n + k) for the two groups and the trip.
"""

from typing import Dict, List

from simulator.models import Parcel, SimulationContext
from solution.policies.helpers import (
    HUB, MINUTES_PER_KM, nearest_neighbor_order, route_distance, waiting_parcels,
    within_limits,
)


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Return one trip: urgent parcels that can still be on time first, in nearest-neighbor order."""

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

    # Overdue parcels are still tried, but only after every parcel that can be on time.
    candidates = sorted(can_be_on_time, key=by_deadline) + sorted(overdue, key=by_deadline)

    route: List[str] = []
    load = 0.0
    for parcel_id in candidates:
        # Capacity is the cheap check, so do it before building a tour.
        if load + parcel[parcel_id]["size"] > context["capacity"]:
            continue
        trial = nearest_neighbor_order(route + [parcel_id], parcel, distances)
        if within_limits(route_distance(trial, parcel, distances), context):
            route = trial
            load += parcel[parcel_id]["size"]
    return route

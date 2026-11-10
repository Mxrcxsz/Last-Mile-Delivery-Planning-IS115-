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

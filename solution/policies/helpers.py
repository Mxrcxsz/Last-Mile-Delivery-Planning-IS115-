"""Shared helpers for the dispatch policies. Inputs are read-only and never modified."""

import math
from typing import Dict, List, Tuple

from simulator.models import Parcel, SimulationContext
from simulator.simulator import HUB, MINUTES_PER_KM


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

    departure = context["current_time"] + context["departure_delay"]
    return (distance <= context["max_trip_distance_km"]
            and departure + distance * MINUTES_PER_KM <= context["return_cutoff"])


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


def cheapest_insertion(
    route: List[str], parcel_id: str, parcel: Dict[str, Parcel],
    distances: Dict[str, Dict[str, float]],
) -> Tuple[int, float]:
    """Return (position, added km) for the cheapest place to insert parcel_id. O(k) time.

    Position i means the parcel goes before route[i]; len(route) means last. Ties go to the
    earliest position, so the result is deterministic.
    """

    target = parcel[parcel_id]["delivery_location_id"]
    stops = [HUB] + [parcel[stop]["delivery_location_id"] for stop in route] + [HUB]
    best_position = 0
    best_added = math.inf
    for position in range(len(stops) - 1):
        before, after = stops[position], stops[position + 1]
        # Directed legs: replace before -> after with before -> target -> after.
        added = distances[before][target] + distances[target][after] - distances[before][after]
        if added < best_added:
            best_position = position
            best_added = added
    return best_position, best_added


def two_opt(
    route: List[str], parcel: Dict[str, Parcel], distances: Dict[str, Dict[str, float]]
) -> List[str]:
    """Shorten a route by reversing segments until no reversal helps. O(k^3) time per pass.

    The distances are directed, so reversing a segment also reverses every leg inside it.
    Each candidate is therefore scored by recomputing its whole distance in O(k), rather
    than by the usual four-edge shortcut. Only strict improvements are kept, so the loop
    ends and the result is never longer than the input.
    """

    best = list(route)
    best_distance = route_distance(best, parcel, distances)
    improved = True
    while improved:
        improved = False
        for start in range(len(best) - 1):
            for end in range(start + 1, len(best)):
                trial = best[:start] + best[start:end + 1][::-1] + best[end + 1:]
                trial_distance = route_distance(trial, parcel, distances)
                # The tolerance stops float noise from counting as an improvement.
                if trial_distance < best_distance - 1e-9:
                    best = trial
                    best_distance = trial_distance
                    improved = True
    return best

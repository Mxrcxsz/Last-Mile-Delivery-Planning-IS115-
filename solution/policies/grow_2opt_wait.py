"""Policy C: Policy B plus two timing rules: no early deliveries, and no nearly empty trips.

Selection rule: as Policy B (cheapest insertion grown from the most urgent parcel that can
    still be on time, keeping every on-time parcel on time), with one change: a parcel is
    added only if it arrives inside its window, never before it opens. Early parcels stay
    at the hub for a later trip, where they can still count as on time. The seed is the
    most urgent candidate that a direct drive would reach inside its window.
Routing rule: as Policy B (insertion order, then 2-opt that never lowers the on-time count).
Timing rule: return [] (wait for the next planning round, 10 minutes later) when either
    * no waiting parcel can be reached inside its window yet, or
    * the trip is nearly empty (load below MIN_FILL of capacity) and every parcel on it
      can still be on time after one more round (slack of at least WAIT_SLACK minutes),
      so waiting costs nothing and lets more parcels join the trip.
    The vehicle never waits past the last departure that still meets the 18:00 cutoff.

MIN_FILL and WAIT_SLACK were chosen by grid search on day_001 to day_010 only, then
    checked on day_011 to day_020, so the gain is not fitted to the days it is tested on.
    Reproduce with: python3 tune_grow_2opt_wait.py (writes results/tuning_grow_2opt_wait.csv).

Algorithms and data structures: as Policy B (greedy cheapest insertion, 2-opt, a hash map
    from location to a deadline-sorted list).

Complexity per dispatch call: as Policy B, plus O(k) for the waiting test, so
    Time: O(N + n log n + k (L k + n) + P s^2 (s + k)); Space: O(N + k).
    Waiting does not change the cost of one call, but a waiting vehicle is asked again
    every round, so the number of calls per day can rise by up to (rounds x vehicles),
    which is at most 58 x 10 = 580 calls.
"""

from typing import Dict, List

from simulator.models import Parcel, SimulationContext
from solution.policies.helpers import (
    can_still_be_on_time, departure_time, grow_trip, route_distance, stop_arrivals,
    group_by_stop, two_opt, waiting_parcels, within_limits,
)

MIN_FILL = 0.75     # A trip below this share of capacity counts as nearly empty.
WAIT_SLACK = 10.0   # Minutes every parcel must be able to wait: one planning interval.
PLANNING_INTERVAL = 10.0  # From the brief: planning runs every ten minutes.


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Return one trip whose parcels all arrive inside their windows, or [] to wait."""

    distances = context["travel_distance"]
    departure = departure_time(context)
    candidates = [
        parcel_id for parcel_id in waiting_parcels(parcel)
        if can_still_be_on_time(parcel_id, parcel, context)
        and within_limits(route_distance([parcel_id], parcel, distances), context)
    ]
    # Seed: most urgent parcel that a direct drive reaches inside its window.
    seeds = [
        parcel_id for parcel_id in candidates
        if departure + distances["HUB"][parcel[parcel_id]["delivery_location_id"]]
        >= parcel[parcel_id]["delivery_window_start"]
    ]
    if not seeds:
        return []
    seed = min(seeds, key=lambda p: (parcel[p]["delivery_window_end"], p))
    route = grow_trip(seed, candidates, parcel, context, allow_early=False)
    route = two_opt(route, parcel, distances, departure)

    if _should_wait(route, parcel, context):
        return []
    return route


def _should_wait(route: List[str], parcel: Dict[str, Parcel], context: SimulationContext) -> bool:
    """Return True if the trip is nearly empty and waiting one round loses nothing. O(k)."""

    load = sum(parcel[p]["size"] for p in route)
    if load >= MIN_FILL * context["capacity"]:
        return False
    distances = context["travel_distance"]
    later = context.copy()
    later["current_time"] = context["current_time"] + PLANNING_INTERVAL
    # Same trip one round later must still be legal (range is unchanged, cutoff may not be).
    if not within_limits(route_distance(route, parcel, distances), later):
        return False
    groups = group_by_stop(route, parcel)
    stops = [parcel[g[0]]["delivery_location_id"] for g in groups]
    arrivals = stop_arrivals(stops, distances, departure_time(context))
    for group, arrival in zip(groups, arrivals):
        for parcel_id in group:
            if parcel[parcel_id]["delivery_window_end"] - arrival < WAIT_SLACK:
                return False
    return True

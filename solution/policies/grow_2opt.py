"""Explored policy, design step 4 (superseded by Policy B): cheapest insertion, 2-opt, no waiting.

Kept to document the design history (report_findings.md, section 7). Policy letters
below use the earlier naming: A = edf_nn, A2 = edf_nn_skip_overdue, B = grow_2opt,
C = grow_2opt_wait.

Selection rule: only parcels that can still be on time are considered (the A2 idea: a
    parcel whose window end cannot be reached even by driving straight to it is skipped).
    The trip is seeded with the most urgent of them (earliest window end, parcel ID breaks
    ties). It then grows one parcel at a time by cheapest insertion: of all parcels that
    can be added, take the one whose best insertion position adds the least distance
    (ties: earliest window end, then parcel ID). A parcel can be added only if the trip
    stays within capacity, range and the 18:00 cutoff, the parcel itself arrives by its
    window end, and no parcel already on time on the trip is pushed past its window end.
    Early arrival (before window start) is allowed; Policy C removes that.
Routing rule: the insertion order, then 2-opt over the distinct stops on the directed
    distance table. A 2-opt move is kept only if the trip gets strictly shorter and the
    number of on-time parcels does not fall.
Timing rule: no waiting. The vehicle leaves whenever the seed exists.

Algorithms and data structures: greedy cheapest insertion; 2-opt local search; a hash map
    from location to a deadline-sorted list of parcels (all parcels at one location cost
    the same to insert, so each location is priced once per position).

Complexity per dispatch call, for N arrived parcels, n candidates (n <= N), L distinct
    locations among them, k parcels in the trip and s distinct stops (s <= min(k, L)):
    Filtering O(N); seed O(n); bucketing O(n log n); growth O(k s n) in the worst case
    (see helpers.grow_trip); 2-opt O(s^2 (s + k)) per improving pass.
    Time: O(N + n log n + k s n + P s^2 (s + k)) for P 2-opt passes. Here L <= 36,
        k is about 30 (capacity 30, mean size about 1), so in practice the cost is close
        to linear in n. In the worst case (k and L grow with n) growth is O(n^3).
    Space: O(N + k).
"""

from typing import Dict, List

from simulator.models import Parcel, SimulationContext
from solution.policies.helpers import (
    can_still_be_on_time, departure_time, grow_trip, route_distance, two_opt,
    waiting_parcels, within_limits,
)


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Return one trip: a cluster grown around the most urgent parcel, ordered by 2-opt."""

    distances = context["travel_distance"]
    candidates = [
        parcel_id for parcel_id in waiting_parcels(parcel)
        if can_still_be_on_time(parcel_id, parcel, context)
        and within_limits(route_distance([parcel_id], parcel, distances), context)
    ]
    if not candidates:
        return []
    seed = min(candidates, key=lambda p: (parcel[p]["delivery_window_end"], p))
    route = grow_trip(seed, candidates, parcel, context, allow_early=True)
    return two_opt(route, parcel, distances, departure_time(context))

"""Policy B: cheapest-insertion trips, 2-opt, no early deliveries, waiting, overdue filling.

Selection rule: candidates are waiting parcels that can still be on time (a direct drive
    reaches them by their window end) and fit a trip on their own. Seed the trip with the
    most urgent candidate that a direct drive reaches inside its window (earliest window
    end, parcel ID breaks ties). Then grow it by cheapest insertion: repeatedly add the
    candidate whose best insertion position adds the least distance (ties: earliest window
    end, then parcel ID). A parcel can be added only if capacity, range and the 18:00
    cutoff hold, it arrives inside its window (never early, never late), and no parcel
    already on the trip is pushed past its window end.
Routing rule: insertion order, then 2-opt over the distinct stops; a move is kept only if
    the trip gets strictly shorter and the number of on-time parcels does not fall.
Timing rule: return [] (wait for the next round, 10 minutes later) if no candidate can be
    reached inside its window yet, or if the trip is nearly empty (load below MIN_FILL of
    capacity) and every parcel on it can still be on time one round later (slack of at
    least WAIT_SLACK minutes).
Filling rule: when the trip leaves, its spare capacity is filled with overdue parcels (ones
    that can only be late) by cheapest insertion, but only where the detour pushes no
    on-time parcel past its window end. They never cause a departure, a wait or a trip.

MIN_FILL and WAIT_SLACK were chosen by grid search on day_001 to day_010 only, then checked
    on day_011 to day_020: python3 tune_grow_2opt_wait_fill.py.

Algorithms and data structures: greedy cheapest insertion; 2-opt local search; hash maps
    from location to a deadline-sorted list of parcels (all parcels at one location cost
    the same to insert, so each location is priced once per position).

Complexity per dispatch call, for N arrived parcels, n candidates at L distinct locations,
    k parcels and s distinct stops in the trip, P 2-opt passes, m overdue parcels at L'
    locations:
    Filtering O(N); bucketing O(n log n); growth O(k s n) in the worst case (see
    helpers.grow_trip); 2-opt O(s^2 (s + k)) per pass; waiting test O(k); filling
    O(m log m + k (m + L' s + s + k)).
    Time: O(N + n log n + k s n + P s^2 (s + k) + m log m + k (m + L' s + s + k)).
    Worst case O(n^3) if k and s grow with n. In practice k is about 30, s is at most 36
    and a bucket's first parcel usually fits, so this is close to linear in N.
    Space: O(N + k).
    A waiting vehicle is asked again every round, so waiting raises the number of calls per
    day, to at most 58 rounds x 10 vehicles = 580.
"""

from typing import Dict, List

from simulator.models import Parcel, SimulationContext
from solution.policies.helpers import (
    departure_time, fill_overdue, grow_trip, on_time_candidates, overdue_parcels,
    reachable_in_window, should_wait, two_opt,
)

MIN_FILL = 0.75     # A trip below this share of capacity counts as nearly empty.
WAIT_SLACK = 10.0   # Minutes every parcel must be able to wait: one planning interval.


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Return one trip whose on-time parcels all arrive inside their windows, or [] to wait."""

    candidates = on_time_candidates(parcel, context)
    seeds = [p for p in candidates if reachable_in_window(p, parcel, context)]
    if not seeds:
        return []
    seed = min(seeds, key=lambda p: (parcel[p]["delivery_window_end"], p))
    route = grow_trip(seed, candidates, parcel, context, allow_early=False)
    route = two_opt(route, parcel, context["travel_distance"], departure_time(context))

    if should_wait(route, parcel, context, min_fill=MIN_FILL, wait_slack=WAIT_SLACK):
        return []
    return fill_overdue(route, overdue_parcels(parcel, context, set(route)), parcel, context)

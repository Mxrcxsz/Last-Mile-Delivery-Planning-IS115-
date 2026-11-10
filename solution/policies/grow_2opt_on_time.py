"""Policy B2: Policy B with a 2-opt that looks at delivery windows instead of distance alone.

Selection rule: the same as Policy B. Seed with the most urgent parcel that can still be on
    time (or the most urgent overdue parcel if none can), then keep adding the parcel that
    adds the fewest km at its cheapest position, on-time candidates before overdue ones,
    while capacity, range and the return cutoff hold.
Routing rule: cheapest insertion as parcels are added, as in Policy B. Then 2-opt reverses
    segments of the route, keeping a reversal only if it delivers more parcels inside their
    window, or the same number over fewer km, and still meets the range and return cutoff.
    Policy B's 2-opt looks at distance only, so it can push urgent parcels later; this one
    cannot lose an on-time delivery, and can also move an early stop later into its window.
Timing rule: no waiting. The vehicle leaves whenever at least one parcel fits, even if that
    delivers the parcel before its window starts.

Complexity, for n waiting parcels and k parcels in the trip (k <= n):
    Time: O(n log n + n k^2 + p k^3), as for Policy B. Scoring a reversal now also counts the
        on-time stops, which is another O(k) pass, so each 2-opt pass is still O(k^3); p is
        the number of passes.
    Space: O(n + k) for the two groups and the trip.
"""

from typing import Dict, List

from simulator.models import Parcel, SimulationContext
from solution.policies.grow_2opt import grow_trip
from solution.policies.helpers import two_opt_on_time


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Return Policy B's trip, reordered to deliver as many parcels on time as 2-opt can."""

    return two_opt_on_time(grow_trip(parcel, context), parcel, context)

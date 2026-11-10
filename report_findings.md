# IS115 Last-Mile Delivery: findings for the report

Prepared 10 Nov 2026 from the code and results on branch `marcus`. Deadline: Fri 13 Nov 2026, 23:59.

## How to use this file

This is source material for writing the project report. It is not the report.

- Every number below comes from runs of the code in this repository on day_001 to day_020. Do not invent or round differently from what is here; if a number is needed that is not here, ask for it to be computed.
- The report is limited to **8 pages, excluding references**. Not everything here fits; prioritise by the rubric weights below.
- Policy C (waiting rule) is **not implemented yet**. Do not write results for it.
- Each team member will be asked an exam question about this work (10% of the grade), so explanations should be ones a student can defend, not just state.

## 1. What the brief requires

Rubric:

| Section | Weight |
| --- | --- |
| Problem statement and motivation | 10% |
| Algorithmic approaches | 20% |
| Computational complexity analysis | 20% |
| Experimental results | 20% |
| Conclusion | 10% |
| Code reproducibility and references | 10% |
| Final-exam question on the team's own work | 10% of the project |

Requirements from the brief that the report must visibly satisfy:

1. Choose a performance metric, justify why it matters for last-mile delivery, and define how it is calculated including assumptions. **"Any metric that leads to a trivial approach will receive zero marks."**
2. Establish baseline performance with the supplied `baseline.py`.
3. Propose **several** dispatch policies, analyse their **time and space** complexity, assess **advantages and limitations**, discuss **trade-offs**, explain **where each approach performs well or poorly**, and **recommend a final approach**.
4. The solution must **meaningfully incorporate at least one algorithm and one data structure taught in class** (see section 4.7; check against the IS115 syllabus).
5. Report sections: problem statement and motivation, algorithmic approaches, computational complexity, experimental results, conclusion, references.

## 2. Problem setting

From the brief and the data files:

- One hub, 10 identical vehicles, capacity 30 size units per trip, range 320 km per trip (full recharge at each return), speed 60 km/h, so 1 km = 1 minute.
- Planning every 10 minutes from 08:00 to 17:30. In each round the simulator calls `dispatch(parcel, context)` once per idle vehicle, longest-idle first. The policy returns an ordered list of parcel IDs, or `[]` to leave the vehicle idle until the next round.
- A confirmed vehicle departs 30 minutes later (loading and charging). Service time at a stop is zero.
- Hard constraints (the simulator rejects a route that breaks them): capacity 30, range 320 km, back at the hub by 18:00.
- Delivery windows are **soft**: early and late deliveries are allowed. 100% delivery is not required.
- The policy may only use the `parcel` and `context` it is given (no reading `data/`), and must treat both as read-only.

Dataset facts (computed from `data/`):

| Fact | Value |
| --- | --- |
| Days | 20 (day_001 to day_020) |
| Parcels per day | 763 to 811, mean 793.35 |
| Delivery locations | 36, all of which appear every day (about 22 parcels per location per day) |
| Distance from hub to a location | 22.1 to 50.5 km, median 40.8 km |
| Parcel size | 0.2 to 1.8, mean 0.96 (so about 31 average parcels fill a vehicle) |
| Window width (end − start) | 30 to 600 min, median 93 min |
| Window end − arrival time | 30 to 600 min, median 218 min |
| Parcels arriving before 12:00 | 73.6% |
| Distance matrix | Supplied as directed (`dist.csv` lists both directions), but in this data every pair is **symmetric** (0 of 1,332 off-diagonal pairs differ) |

Why the problem is hard: a vehicle must leave at least 30 minutes after a decision and the nearest location is 22 km away, so a parcel whose window closes soon after it arrives may be impossible to serve on time. Many parcels share each location, so batching by location is cheap, but windows differ, so the cheapest batch is not always the most punctual one.

**Upper bound on the metric.** A parcel is counted impossible to deliver on time if, even sent alone on the first planning round after it arrives, it would reach its location after `window_end`, or could not get back by 18:00. This ignores fleet limits, so it is an optimistic ceiling. On average **28.05 parcels per day (23 to 33)** are impossible, so no policy can exceed an on-time rate of about **0.9646** (0.9585 to 0.9715 by day). Useful for putting results in context: B2's 0.7331 reaches about 76% of this ceiling.

## 3. The metric: on-time delivery rate

Definition (implemented in `solution/performance_monitor.py`):

```text
on_time_rate = parcels delivered inside [window_start, window_end] / ALL parcels in that day's CSV
```

- Both window boundaries count as on time.
- Delivery before `window_start` is **early** and does **not** count. Delivery after `window_end` is late.
- Undelivered parcels stay in the denominator.
- Rounded to 4 decimal places.

Why it is not trivial (needed because of the "trivial approach scores zero" rule):

- Doing nothing scores 0, because the denominator is every parcel of the day, not only the delivered ones.
- Delivering everything as fast as possible does not maximise it either, because early deliveries do not count. A policy must balance coverage (deliver many) against timing (deliver inside the window).
- It is a customer-facing service measure: a delivery outside the promised window means a missed customer, a failed handover or a complaint.

Supporting metrics, also in every `metrics.json`: `parcels_total`, `parcels_delivered`, `parcels_on_time`, `parcels_late`, `parcels_early`, `delivery_rate` (delivered / total), and `km_per_delivered_parcel` (total km of all trips rebuilt from the delivery order, HUB → stops → HUB, divided by delivered parcels; an operating-cost proxy).

Assumptions: one simulated day per CSV; all parcels arrive by 17:30; time windows taken exactly as given; km driven is rebuilt from the order of delivery events within each trip.

## 4. Algorithmic approaches

All policies are built from three choices made at each `dispatch` call: **timing** (leave now or wait), **selection** (which waiting parcels go on this trip) and **routing** (the order of stops). Each policy changes one idea from the one before it, so the gain of each idea can be measured separately.

Shared building blocks (`solution/policies/helpers.py`):

- `waiting_parcels`: parcels with `vehicle_assigned` and `delivery_time` both `None`. O(N) for N arrived parcels.
- `route_distance`: km of HUB → stops → HUB using `math.fsum`, the same summation the simulator uses, so the policy's check and the simulator's check agree exactly. O(k).
- `within_limits`: range ≤ 320 km and departure + travel time ≤ 18:00. O(1).
- `nearest_neighbor_order`: from the hub, repeatedly drive to the closest remaining stop. O(k²).
- `cheapest_insertion`: for one parcel, the position in the route that adds the fewest km. O(k).
- `two_opt`: reverse route segments while the route gets shorter. O(k³) per pass.
- `on_time_count`: how many stops on a route arrive inside their window. O(k).
- `two_opt_on_time`: 2-opt that maximises on-time stops first and minimises km second. O(k³) per pass.
- Constants `HUB` and `MINUTES_PER_KM` are imported from the supplied simulator rather than redeclared.

"Overdue" (used by A2, B, B2): a parcel is overdue if `departure + distance(HUB, location) > window_end`, that is, it would be late even as the first stop of a trip leaving now.

### 4.1 Baseline (`baseline.py`, supplied, unchanged)

- Selection: try every waiting parcel in arrival order (parcel ID breaks ties); skip one that breaks capacity, range or the return cutoff, keep trying later ones. Ignores windows.
- Routing: stops visited in selection order.
- Timing: leave whenever at least one parcel fits.
- Weakness: arrival order is geographically random, so routes zigzag and use up range quickly; it delivers only about 40% of parcels.

### 4.2 Policy A: `edf_nn.py` (Earliest Deadline First + Nearest Neighbor)

- Selection: try waiting parcels in order of earliest `window_end` (parcel ID breaks ties). Keep a parcel if capacity allows and the nearest-neighbor tour that includes it meets range and the return cutoff.
- Routing: nearest neighbor from the hub. Each candidate is tested on the nearest-neighbor tour that includes it, so the returned route has already passed the checks.
- Timing: leave whenever at least one parcel fits.
- Idea it adds: deadline order (EDF, a classic scheduling rule) plus a shorter tour, so more parcels fit under the 320 km range.
- Weakness: EDF puts parcels that are **already** past their window first, so trips are spent on parcels that will be late anyway (282 late parcels per day).

### 4.3 Policy A2: `edf_nn_skip_overdue.py`

- Same as A, except for the order candidates are tried in: parcels that can still be on time first (by earliest `window_end`), then overdue parcels in the same order.
- Idea it adds: do not spend capacity on lost causes while savable parcels are waiting.
- Effect: late parcels fall from 282 to 145 per day, on-time rate 0.4141 → 0.5587.

### 4.4 Policy B: `grow_2opt.py` (urgent seed, cheapest insertion, 2-opt)

- Selection: seed the trip with the most urgent parcel that can still be on time (or the most urgent overdue parcel if none can). Then repeatedly add the parcel that adds the **fewest km** at its cheapest position, among parcels that can still be on time and keep the trip feasible; when none fits, do the same with overdue parcels.
- Routing: cheapest insertion as parcels are added, then 2-opt (reverse a segment while that shortens the route).
- Timing: leave whenever at least one parcel fits.
- Idea it adds: choose parcels that are close together on purpose (geographic batching) instead of taking them in deadline order.
- 2-opt detail: the interface describes distances as directed, so reversing a segment also reverses every leg inside it. Each candidate reversal is therefore scored by recomputing the whole route in O(k), not with the usual O(1) four-edge shortcut. (In this data the matrix happens to be symmetric, so the shortcut would also be correct here; the O(k) rescoring is correct for any directed matrix.)
- Weakness: choosing the cheapest parcel ignores whether its window has opened, so B delivers about 196 parcels per day **early**, which do not count.

### 4.5 Policy B2: `grow_2opt_on_time.py` (B with time-window-aware 2-opt)

- Selection: identical to B (it calls B's `grow_trip`).
- Routing: cheapest insertion, then a 2-opt that keeps a reversal only if it delivers **more parcels inside their window**, or the **same number over fewer km**, and still meets range and the return cutoff.
- Timing: leave whenever at least one parcel fits.
- Idea it adds: optimise the stop order for the actual objective (on-time deliveries), not for distance.
- Why it terminates: every kept reversal strictly improves the pair (on-time count, −distance) in lexicographic order, and a route has finitely many orders.
- Why it helps: it can move an early stop later in the route so that it arrives inside its window, and it never loses an on-time delivery that the route already had.

### 4.6 Ablation (not a submitted policy): B without 2-opt

B's selection and cheapest-insertion order, with the final 2-opt removed. Used only to measure what 2-opt contributes. It was run from a scratch module outside the repository (see section 9).

### 4.7 Algorithms and data structures used (for the "taught in class" requirement)

Check these against the IS115 syllabus and name the course topics explicitly in the report.

| Item | Where it is used |
| --- | --- |
| Sorting (Python's Timsort, O(n log n)) | Deadline order in A, A2, B, B2 |
| Greedy algorithms | Every policy builds a trip greedily (EDF selection; cheapest insertion) |
| Local search | 2-opt in B and B2 |
| Hash tables (`dict`) | The `parcel` records and the nested distance lookup `travel_distance[origin][destination]`, O(1) average access |
| Sets | Remaining candidates in B's growth step (O(1) average removal and membership) |
| Lists / arrays | Routes and candidate lists |
| Graph (complete directed weighted graph as an adjacency matrix stored in nested dicts) | The distance lookup; routing is a TSP-style tour on this graph |

Not yet used: a heap or priority queue, or a graph search such as uniform-cost search. The planned optional Policy D (`ucs_routing`, exact UCS over (location, visited set) for small trips) would add both, if the syllabus requirement needs them.

### 4.8 Planned but not implemented

- **Policy C `grow_2opt_wait`** (builds on B2): return `[]` (wait) if the trip is nearly empty and the most urgent parcel still has slack, or if the parcels would arrive before their windows open. Motivation: B2 still delivers about 98 parcels per day early.
- **Policy D `ucs_routing`** (optional): exact routing for small trips, to measure how much optimal routing gains over the heuristics. The state space grows as 2^k, so it needs a cap of about 8 to 10 distinct stops.

## 5. Computational complexity

Notation: N = arrived parcels, n = waiting parcels (n ≤ N), k = parcels in the trip (k ≤ n; capacity limits k to about 30 here), p = number of 2-opt passes. Complexity is per `dispatch` call. A day has 58 planning rounds and up to 10 calls per round.

| Policy | Time per `dispatch` call | Space | Where the time goes |
| --- | --- | --- | --- |
| baseline | O(N + n log n) | O(n + k) | Sort by arrival, then one O(1) check per candidate (it extends the route incrementally) |
| A | O(N + n log n + n k²) | O(n + k) | Sort; each of n candidates may need a nearest-neighbor tour, O(k²) |
| A2 | O(N + n log n + n k²) | O(n + k) | As A, plus an O(n) split into on-time and overdue groups |
| B | O(N + n log n + n k² + p k³) | O(n + k) | Growth: k steps × up to n candidates × O(k) cheapest-insertion search. 2-opt: O(k²) reversals per pass × O(k) rescoring |
| B2 | O(N + n log n + n k² + p k³) | O(n + k) | As B; scoring a reversal adds an O(k) on-time count, which leaves each pass at O(k³) |

Worst cases and points to discuss:

- If k grows with n, A and A2 become O(n³). In practice k ≤ about 30 because of capacity, so the n k² term behaves like a large constant times n.
- p is not bounded by a polynomial in theory (each pass must strictly improve, and there are k! orders), but in practice it is small. A pass cap would make the bound strict; this is a possible improvement to mention.
- Space stays O(n + k): candidate lists plus one trial route at a time. The distance matrix (36 locations + hub, 1,369 entries) belongs to the simulator and is not copied.
- 2-opt rescoring is O(k) because the interface says distances are directed; with a symmetric matrix the standard O(1) delta would make a pass O(k²). For B2 the O(k) on-time count is needed anyway, because moving one segment changes the arrival time of every later stop.

Measured runtime (whole simulator plus performance monitor, 20 days, one run each, macOS; includes Python start-up, so treat as rough):

| Policy | Wall time for 20 days |
| --- | --- |
| baseline | 10.4 s |
| A | 12.3 s |
| A2 | 10.7 s |
| B | 28.0 s in one session, 20.7 s in a later session |
| B2 | 22.8 s (same session as B's 20.7 s) |

Every policy runs a full day in about 1.5 s or less, far below the 10-minute planning interval. B and B2 cost roughly 2× A2, consistent with the extra n k² insertion search and the k³ 2-opt passes. Timings vary between sessions by about 30%, so compare only within a session.

## 6. Experimental results

All results: 20 days, means of the daily `metrics.json` values (unweighted mean over days). Paired tests compare two policies on the same 20 days (df = 19; |t| > 2.093 means p < 0.05; sign test two-sided).

### 6.1 Main table

| Policy | On-time rate (sd) | Min to max by day | Delivery rate | On time / late / early / undelivered per day | Trips per day | Parcels per trip | km per day | km per delivered parcel |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 0.2741 (0.016) | 0.2475 to 0.3118 | 0.4045 | 217 / 104 / 0 / 472 | 20.7 | 15.6 | 5204 | 16.33 |
| A `edf_nn` | 0.4141 (0.046) | 0.3653 to 0.5051 | 0.7885 | 329 / 282 / 15 / 168 | 22.9 | 27.4 | 4840 | 7.75 |
| A2 `edf_nn_skip_overdue` | 0.5587 (0.048) | 0.4687 to 0.6270 | 0.7835 | 443 / 145 / 33 / 172 | 23.3 | 26.8 | 4787 | 7.73 |
| B `grow_2opt` | 0.5912 (0.033) | 0.5247 to 0.6501 | 0.9598 | 469 / 96 / 196 / 32 | 34.0 | 22.4 | 4132 | 5.43 |
| B without 2-opt (ablation) | 0.6104 (0.047) | 0.5294 to 0.7021 | 0.9595 | 484 / 100 / 177 / 32 | 33.6 | 22.7 | 4173 | 5.48 |
| **B2 `grow_2opt_on_time`** | **0.7331 (0.047)** | **0.6304 to 0.8018** | 0.9593 | **582 / 81 / 98 / 32** | 33.4 | 22.8 | 4198 | 5.52 |

Average lateness and earliness of the parcels that were late or early (minutes):

| Policy | Mean minutes early (early parcels only) | Mean minutes late (late parcels only) |
| --- | --- | --- |
| baseline | none early | 214 |
| A | 15 | 73 |
| A2 | 37 | 115 |
| B | 36 | 191 |
| B without 2-opt | 37 | 191 |
| B2 | 51 | 225 |

### 6.2 Paired comparisons (on-time rate)

| Comparison | Mean difference | Range of daily differences | Days the first policy wins | Sign test p | Paired t |
| --- | --- | --- | --- | --- | --- |
| A vs baseline | +0.1400 | +0.058 to +0.235 | 20/20 | < 0.001 | 11.98 |
| A2 vs A | +0.1447 | +0.071 to +0.213 | 20/20 | < 0.001 | 17.59 |
| B vs A | +0.1771 | +0.073 to +0.277 | 20/20 | < 0.001 | 12.65 |
| B vs A2 | +0.0325 | −0.055 to +0.171 | 13/20 | 0.26 | 2.31 |
| B vs B without 2-opt | −0.0192 | −0.118 to +0.050 | 6/20 | 0.12 | −2.06 |
| B without 2-opt vs A2 | +0.0517 | −0.098 to +0.194 | 18/20 | < 0.001 | 3.24 |
| B2 vs B | +0.1419 | +0.042 to +0.246 | 20/20 | < 0.001 | 11.93 |
| B2 vs B without 2-opt | +0.1227 | +0.024 to +0.265 | 20/20 | < 0.001 | 10.32 |
| B2 vs A2 | +0.1744 | +0.028 to +0.293 | 20/20 | < 0.001 | 10.99 |

### 6.3 On-time rate by day

| Day | baseline | A | A2 | B | B without 2-opt | B2 |
| --- | --- | --- | --- | --- | --- | --- |
| day_001 | 0.2666 | 0.4631 | 0.6270 | 0.5732 | 0.5294 | 0.7084 |
| day_002 | 0.2902 | 0.3666 | 0.5440 | 0.6256 | 0.7021 | 0.8018 |
| day_003 | 0.2645 | 0.3967 | 0.5113 | 0.6071 | 0.5743 | 0.7179 |
| day_004 | 0.2537 | 0.4542 | 0.5928 | 0.5483 | 0.6015 | 0.7364 |
| day_005 | 0.2854 | 0.3970 | 0.5521 | 0.6266 | 0.5769 | 0.7221 |
| day_006 | 0.2666 | 0.4337 | 0.6110 | 0.5944 | 0.6148 | 0.6390 |
| day_007 | 0.3118 | 0.3702 | 0.4783 | 0.5578 | 0.5801 | 0.7230 |
| day_008 | 0.2475 | 0.3762 | 0.5297 | 0.5879 | 0.6188 | 0.7463 |
| day_009 | 0.2732 | 0.5013 | 0.5727 | 0.5890 | 0.6404 | 0.7343 |
| day_010 | 0.2639 | 0.3687 | 0.5820 | 0.6141 | 0.6227 | 0.7842 |
| day_011 | 0.2822 | 0.4530 | 0.5965 | 0.5866 | 0.6077 | 0.7735 |
| day_012 | 0.2733 | 0.3653 | 0.4687 | 0.6398 | 0.6207 | 0.7612 |
| day_013 | 0.2535 | 0.4689 | 0.6134 | 0.6236 | 0.6210 | 0.7085 |
| day_014 | 0.2699 | 0.5051 | 0.6041 | 0.5784 | 0.6967 | 0.7815 |
| day_015 | 0.3053 | 0.3945 | 0.5415 | 0.5729 | 0.5766 | 0.6721 |
| day_016 | 0.2811 | 0.4228 | 0.6035 | 0.5483 | 0.5295 | 0.7942 |
| day_017 | 0.2750 | 0.3929 | 0.4968 | 0.5247 | 0.5843 | 0.7288 |
| day_018 | 0.2647 | 0.3735 | 0.4993 | 0.6501 | 0.6933 | 0.7759 |
| day_019 | 0.2823 | 0.3952 | 0.5885 | 0.5872 | 0.6186 | 0.7227 |
| day_020 | 0.2711 | 0.3824 | 0.5614 | 0.5882 | 0.5985 | 0.6304 |

## 7. Key findings (the story of the results)

1. **Shorter tours mean more deliveries.** The baseline's arrival-order routes zigzag: 15.6 parcels per trip and 16.3 km per delivered parcel. Nearest-neighbor ordering (A) halves the km per parcel (7.75) and nearly doubles the delivery rate (0.40 → 0.79), because more parcels fit under the 320 km range.
2. **Deadline order alone is not enough.** EDF serves parcels that are already lost first. Skipping them until savable parcels are served (A2) adds +0.145 on-time rate, wins on every day, and halves late parcels (282 → 145), with the same delivery rate. Cheapest single idea in the project: an O(n) split.
3. **Geographic batching gives coverage, not punctuality.** B delivers 96% of parcels and drives about 650 km per day less than A2 (5.4 km per parcel against 7.7), with 11 more, shorter trips per day. But its on-time gain over A2 is small and inconsistent (+0.033, 13 of 20 days, sign test not significant), because cheap nearby parcels are often not yet due: early deliveries jump from 33 to 196 per day.
4. **Optimising the wrong objective hurts.** Standard distance-only 2-opt makes B worse (−0.019 against B without 2-opt) while saving only about 1% of km, because it reorders stops without looking at windows and can push urgent parcels later.
5. **Optimising the right objective helps a lot.** Changing only 2-opt's acceptance rule to "more on-time stops, then shorter" (B2) raises the on-time rate from 0.5912 to **0.7331**, wins on all 20 days against every other policy, and halves early deliveries (196 → 98) at a cost of 1.6% more km than B. Each `dispatch` call selects exactly the parcels B would select in the same situation; only the stop order differs. (Over a whole day the trips do drift apart, because a different order changes when a vehicle returns: 33.4 against 34.0 trips per day, with the same delivery rate.) **The same local-search move gives −0.02 or +0.14 depending on what it optimises.** This is the central lesson for the report.
6. **Trade-off between coverage and punctuality.** Late parcels in B2 are very late (225 min on average) because overdue parcels are only added once nothing savable fits; they are delivered rather than dropped. A policy that dropped them would have a lower delivery rate but the same on-time rate.
7. **Remaining gap.** B2 reaches 0.7331 against an optimistic ceiling of about 0.9646. Of the remaining parcels, about 98 per day are early (the target of Policy C), 81 late and 32 undelivered.

Where each approach performs well or poorly (brief asks for this):

- A2 beats B on days 001, 004, 006, 011, 014, 016 and 019 (by up to 0.055); B's distance-first selection does worst on those days. Why these days differ has **not** been analysed; do not invent a reason.
- B2's weakest days are day_020 (0.6304) and day_006 (0.6390), where its lead over B is smallest (+0.042 and +0.045). Not analysed either.
- B and B2 are the most efficient in km per parcel; A and A2 make fewer, fuller trips.
- The baseline is the most consistent (sd 0.016) only because it is uniformly poor.

## 8. Recommendation and conclusion points (current state)

- Recommended policy so far: **B2 `grow_2opt_on_time`**. Best on-time rate (0.7331), best on every day, near-best delivery rate (0.959) and km per parcel (5.5), and fast enough (about 1 s per day).
- If Policy C is finished and beats B2, the recommendation should be revisited.
- Conclusion themes: choose parcels that are close together; never spend capacity on lost causes while savable parcels wait; make local search optimise the real metric, not a proxy; early deliveries are the largest remaining loss.

## 9. Limitations and threats to validity

- 20 days of data from one town; results may not transfer to other demand patterns.
- Every policy is greedy and myopic: it plans one vehicle's trip at a time, with no coordination across vehicles or look-ahead to future arrivals.
- 2-opt is a local search: it stops at a route no single reversal improves, which may not be optimal.
- No policy waits deliberately yet (Policy C).
- Runtimes are wall-clock times including the simulator and Python start-up, from single runs on one laptop.
- The upper bound in section 2 ignores fleet size and capacity, so the true ceiling is lower.
- The "B without 2-opt" ablation was run from a scratch module outside the repository. To include it in the report it should be added to the repository so it can be reproduced.

## 10. Reproducing the results

From the project root, Python 3.9 or later, standard library only:

```sh
for policy in baseline edf_nn edf_nn_skip_overdue grow_2opt grow_2opt_on_time; do
  for day in $(seq -f "day_%03g" 1 20); do
    python3 -m simulator --policy "solution.policies.$policy" \
        --data data --day "$day" --output "results/$policy/$day"
    python3 -m solution.performance_monitor \
        --data data --day "$day" --log "results/$policy/$day/log.txt"
  done
done
```

Outputs: `results/<policy>/day_XXX/log.txt` (event log) and `metrics.json` (metrics). The README has the averaging script. The simulator is deterministic: re-running gives byte-for-byte identical logs.

## 11. Open items before submission

- Policy C, and optionally D and a random-feasible control, are not implemented.
- `run_experiments.py` (run all policies and days, print the comparison table) does not exist yet; the loop above is used instead.
- `results/` is listed in `.gitignore`, but the brief requires `results/` in the ZIP. Make sure it is included in the submission.
- The ablation and analysis scripts (paired tests, per-day table, upper bound) are not in the repository yet.
- Confirm which "algorithm and data structure taught in class" the report will name, against the syllabus.
- References still need to be added (candidates below).

## 12. Candidate references (verify each before citing)

- Croes, G. A. (1958). A method for solving traveling-salesman problems. *Operations Research*, 6(6), 791–812. (Origin of 2-opt.)
- Liu, C. L., & Layland, J. W. (1973). Scheduling algorithms for multiprogramming in a hard-real-time environment. *Journal of the ACM*, 20(1), 46–61. (Earliest Deadline First.)
- Rosenkrantz, D. J., Stearns, R. E., & Lewis, P. M. (1977). An analysis of several heuristics for the traveling salesman problem. *SIAM Journal on Computing*, 6(3), 563–581. (Nearest neighbor and insertion heuristics.)
- Solomon, M. M. (1987). Algorithms for the vehicle routing and scheduling problems with time window constraints. *Operations Research*, 35(2), 254–265. (Vehicle routing with time windows, insertion heuristics.)
- The IS115 project brief and the supplied simulator.

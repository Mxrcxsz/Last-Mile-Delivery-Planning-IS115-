# IS115 Last-Mile Delivery: findings for the report

Prepared 11 Nov 2026 from the code and results on branch `marcus` after merging `main` (commit `1d4c7f7`). Deadline: Fri 13 Nov 2026, 23:59.

## How to use this file

This is source material for writing the project report. It is not the report.

- Every number below comes from runs of the code in this repository on day_001 to day_020. Do not invent numbers or round them differently from what is here; if a number is needed that is not here, ask for it to be computed.
- The report is limited to **8 pages, excluding references**. Not everything here fits; prioritise by the rubric weights below.
- The policies are baseline, A, A2, B, C, C2, D and E. An earlier B and "B2" written by Marcus were replaced by Varshni's B and C and are **not** in the repository; do not report them as policies (see section 13 for what to keep from them).
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

1. Choose a performance metric, justify why it matters for last-mile delivery, and define how it is calculated, including assumptions. **"Any metric that leads to a trivial approach will receive zero marks."**
2. Establish baseline performance with the supplied `baseline.py`.
3. Propose **several** dispatch policies, analyse their **time and space** complexity, assess **advantages and limitations**, discuss **trade-offs**, explain **where each approach performs well or poorly**, and **recommend a final approach**.
4. The solution must **meaningfully incorporate at least one algorithm and one data structure taught in class** (see section 4.10; check against the IS115 syllabus).
5. Report sections: problem statement and motivation, algorithmic approaches, computational complexity, experimental results, conclusion, references.

## 2. Problem setting

From the brief and the data files:

- One hub, 10 identical vehicles, capacity 30 size units per trip, range 320 km per trip (full recharge at each return), speed 60 km/h, so 1 km = 1 minute.
- Planning every 10 minutes from 08:00 to 17:30 (58 rounds). In each round the simulator calls `dispatch(parcel, context)` once per idle vehicle, longest-idle first. The policy returns an ordered list of parcel IDs, or `[]` to leave the vehicle idle until the next round.
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

Why the problem is hard: a vehicle leaves at least 30 minutes after a decision and the nearest location is 22 km away, so a parcel whose window closes soon after it arrives may be impossible to serve on time. Many parcels share each location, so batching by location is cheap, but windows differ, so the cheapest batch is not always the most punctual one.

**Upper bound on the metric.** A parcel is counted impossible to deliver on time if, even sent alone on the first planning round after it arrives, it would reach its location after `window_end`, or could not get back by 18:00. This ignores fleet size and capacity, so it is an optimistic ceiling. On average **28.05 parcels per day (23 to 33)** are impossible, so no policy can exceed an on-time rate of about **0.9646** (0.9585 to 0.9715 by day). Policy C's 0.9408 reaches about **97.5%** of this ceiling.

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
- Delivering everything as fast as possible does not maximise it either, because early deliveries do not count. A policy must balance coverage (deliver many) against timing (deliver inside the window). The results show this directly: B delivers 87% of parcels but only 61% on time.
- It is a customer-facing service measure: a delivery outside the promised window means a missed customer, a failed handover or a complaint.

Supporting metrics, also in every `metrics.json`: `parcels_total`, `parcels_delivered`, `parcels_on_time`, `parcels_late`, `parcels_early`, `delivery_rate` (delivered / total), and `km_per_delivered_parcel` (total km of all trips rebuilt from the delivery order, HUB → stops → HUB, divided by delivered parcels; an operating-cost proxy).

Assumptions: one simulated day per CSV; all parcels arrive by 17:30; time windows taken exactly as given; km driven is rebuilt from the order of delivery events within each trip.

## 4. Algorithmic approaches

All policies are built from three choices made at each `dispatch` call: **timing** (leave now or wait), **selection** (which waiting parcels go on this trip) and **routing** (the order of stops). Each policy changes one idea from the one before it, so the gain of each idea can be measured separately.

Shared building blocks (`solution/policies/helpers.py`):

- `waiting_parcels`: parcels with `vehicle_assigned` and `delivery_time` both `None`. O(N) for N arrived parcels.
- `route_distance`: km of HUB → stops → HUB using `math.fsum`, the same summation the simulator uses, so the policy's check and the simulator's check agree exactly. O(k).
- `within_limits`: range ≤ 320 km and departure + travel time ≤ 18:00. O(1).
- `nearest_neighbor_order`: from the hub, repeatedly drive to the closest remaining stop. O(k²). Used by A and A2.
- `can_still_be_on_time`: departure + direct drive from the hub ≤ `window_end`. O(1). Used by A2's idea, B and C.
- `group_by_stop`: merges consecutive parcels with the same location into one stop. O(k). Parcels at one stop are delivered at the same moment, so routing only orders stops.
- `stop_arrivals`, `stops_distance`, `is_on_time`: arrival times along a stop list, its km, and the window test.
- `grow_trip`: cheapest-insertion growth from a seed (see 4.4). Used by B, C and C2.
- `two_opt`: 2-opt over distinct stops that keeps a move only if it is strictly shorter and the on-time count does not fall (see 4.4). Used by B, C and C2.
- Constants `HUB` and `MINUTES_PER_KM` are imported from the supplied simulator rather than redeclared.

"Overdue": a parcel is overdue if `departure + distance(HUB, location) > window_end`, that is, it would be late even as the first stop of a trip leaving now.

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

### 4.4 Policy B: `grow_2opt.py` (urgent seed, cheapest insertion, on-time-safe 2-opt)

- Selection: candidates are only the parcels that **can still be on time** and fit a trip on their own; overdue parcels are never sent. Seed with the most urgent candidate (earliest `window_end`, parcel ID breaks ties). Then grow the trip one parcel at a time by **cheapest insertion**: of all parcels that can be added, take the one whose best insertion position adds the fewest km (ties: earliest window end, then parcel ID). A parcel can be added only if:
  - capacity, range and the 18:00 cutoff still hold;
  - the new parcel arrives by its `window_end`;
  - no parcel already on time on the trip is pushed past its `window_end` (checked with a precomputed "slack" array: how many minutes each suffix of the route can be delayed).
  Early arrival (before `window_start`) is allowed in B.
- Routing: the insertion order, then 2-opt over the **distinct stops**. A move reverses a segment of stops; it is kept only if the trip gets **strictly shorter and the on-time count does not fall**. First improvement: the search restarts after each kept move and stops when no move helps.
- Timing: no waiting; leave whenever a seed exists.
- Data structure: a **hash map from location to a list of parcels sorted by (window end, parcel ID)**. All parcels at one location cost the same to insert, so each step prices each location once per position instead of each parcel.
- Idea it adds: build geographic clusters on purpose, while protecting deadlines.
- Weakness: early arrival is allowed, and cheap nearby parcels are often not due yet, so B delivers about **201 parcels per day early**, which do not count.

### 4.5 Policy C: `grow_2opt_wait.py` (Policy B with two timing rules)

- Selection: as B, with one change: a parcel is added only if it arrives **inside** its window, never before it opens (`allow_early=False`). The seed must also be reachable inside its window by a direct drive. Early parcels stay at the hub for a later trip, where they can still count as on time.
- Routing: as B.
- Timing: return `[]` (wait 10 minutes for the next round) when either
  - no waiting parcel can be reached inside its window yet, or
  - the trip is **nearly empty** (load below `MIN_FILL` = 75% of capacity) **and** every parcel on it can still be on time one round later (slack of at least `WAIT_SLACK` = 10 minutes), and the same trip one round later still meets the 18:00 cutoff. Waiting then costs nothing and lets more parcels join the trip.
- Threshold choice: `MIN_FILL` and `WAIT_SLACK` were chosen by **grid search on day_001 to day_010 only**, then checked on day_011 to day_020 (`tune_grow_2opt_wait.py`). This avoids fitting the thresholds to the days used for evaluation. See section 6.4.
- Ideas it adds: (1) never deliver early; (2) do not send nearly empty trips when waiting is free.
- Consequence of the design: C never delivers late or early, so its delivery rate equals its on-time rate. Parcels it cannot deliver on time are never delivered (47 per day).

### 4.6 Policy C2: `grow_2opt_wait_fill.py` (Policy C plus overdue parcels in spare space)

- Selection: build exactly Policy C's trip (or wait, if C waits). Then repeatedly add the **overdue** parcel (one that can only be late) whose cheapest insertion adds the fewest km, as long as capacity, range and the 18:00 cutoff hold and the detour pushes **no on-time parcel on the trip past its window end** (same slack test as `grow_trip`). Parcels that can still be on time but are not on C's trip are never added; they stay for a later trip where they can count.
- Routing: C's order, with each overdue parcel at its cheapest allowed position. A parcel for a location already on the trip goes into that stop at 0 extra km.
- Timing: as C. Overdue parcels only ride on trips C sends anyway: they never cause a departure, a wait or an extra trip.
- Idea it adds: a late delivery earns nothing on the metric, but it is still worth making when it costs no on-time delivery. This addresses C's main trade-off (section 8).
- Note: an overdue parcel cannot be delivered early: by definition even a direct drive arrives after its window closes, so any delivery is late.
- Data structure: a second location → deadline-sorted bucket map, for the overdue parcels.

### 4.7 Policy D: `ucs_routing.py` (Policy C with exact routing by uniform-cost search)

- Selection and timing: exactly Policy C.
- Routing: C's trip is grouped into one stop per location. Each stop gets an arrival interval [latest window start, earliest window end] of its parcels (if that interval is empty, C's route is kept). If the trip has **at most 8 stops**, uniform-cost search finds the shortest order that arrives at every stop inside its interval and returns to the hub:
  - state = (current location, set of visited stops as a bitmask); cost = km driven so far;
  - at 60 km/h km equals minutes, so the cost also gives the arrival time; a move is allowed only if it arrives inside the next stop's interval;
  - states are expanded cheapest first from a **min-heap**, so the first complete tour popped is the shortest feasible one (Dijkstra's algorithm on the state graph);
  - C's own 2-opt route is feasible, so its length is an upper bound: a partial tour that cannot get back to the hub in fewer km is pruned;
  - the new order is used only if it is strictly shorter than C's.
- Why states with the same (location, visited set) are **not** merged: with time windows and no waiting at stops, arriving later can make a later stop feasible, so the cheaper path does not dominate. This is a correctness point worth one sentence in the report.
- Why the cap: the number of orders grows as s!, so exact routing is exponential in the number of stops. 71% of C's trips have at most 8 stops (measured over all 20 days).
- Idea it tests: how much does an optimal stop order gain over 2-opt, everything else equal?

### 4.8 Policy E: `least_slack.py` (least slack first from a min-heap, with C's timing)

- Selection: candidates as in C. A parcel's **slack** = window end − (departure + direct drive from the hub): minutes it can still afford to wait. Seed: the least-slack parcel a direct drive reaches inside its window. All other candidates go into a **min-heap** keyed by (slack, window end, parcel ID) and are popped most urgent first. Each popped parcel is inserted at its cheapest feasible position (arrives inside its window, no on-time parcel pushed late, capacity, range and cutoff hold), or skipped.
- Routing: insertion order, then C's 2-opt.
- Timing: exactly Policy C (no early deliveries; wait for fuller trips when that is free).
- Idea it tests: **urgency-first** selection (a classic scheduling rule, "least laxity first") against C's **distance-first** selection, everything else equal.

### 4.9 Ablation (not a submitted policy): C without the waiting rule

C with `MIN_FILL = 0`, so the "nearly empty" rule never fires and only the "no early delivery" rule remains. Used to split C's gain between its two ideas. The same setting appears as the `MIN_FILL = 0.0` rows of `tune_grow_2opt_wait.py`. The full 20-day run in section 6 was made from a scratch module outside the repository (see section 11).

### 4.10 Algorithms and data structures used (for the "taught in class" requirement)

Check these against the IS115 syllabus and name the course topics explicitly in the report.

| Item | Where it is used |
| --- | --- |
| Sorting (Python's Timsort, O(n log n)) | Deadline order in A and A2; deadline-sorted location buckets in B and C |
| Greedy algorithms | Every policy builds a trip greedily (EDF selection; nearest neighbor; cheapest insertion, twice in C2) |
| Local search | 2-opt in B and C |
| Graph search: uniform-cost search (Dijkstra on the state graph) | Exact routing in D |
| Priority queue (binary min-heap, `heapq`) | UCS frontier in D; least-slack order in E |
| Bitmask as a set | Visited stops in D's search states |
| Hash tables (`dict`) | `parcel` records; distance lookup `travel_distance[origin][destination]`; **location → sorted parcel list** buckets in B and C, O(1) average access |
| Lists / arrays | Routes, candidate lists, the slack array in `grow_trip` |
| Graph (complete weighted graph stored as an adjacency matrix in nested dicts) | The distance lookup; routing is a TSP-style tour on this graph |
| Grid search with a tuning/test split | Choosing C's two thresholds |

Policies D and E add a priority queue (heap) and a graph search (uniform-cost search), so the report can name sorting, greedy, local search, graph search, hash tables and heaps.

## 5. Computational complexity

Notation: N = arrived parcels, n = candidate (waiting) parcels (n ≤ N), k = parcels in the trip (capacity limits k to about 30 here), L = distinct locations among the candidates (L ≤ 36 here), s = distinct stops in the trip (s ≤ min(k, L)), P = number of improving 2-opt passes. Complexity is per `dispatch` call. A day has 58 planning rounds and up to 10 calls per round.

| Policy | Time per `dispatch` call | Space | Where the time goes |
| --- | --- | --- | --- |
| baseline | O(N + n log n) | O(n + k) | Sort by arrival, then an O(1) check per candidate (the route is extended incrementally) |
| A | O(N + n log n + n k²) | O(n + k) | Sort; each of n candidates may need a nearest-neighbor tour, O(k²) |
| A2 | O(N + n log n + n k²) | O(n + k) | As A, plus an O(n) split into on-time and overdue groups |
| B | O(N + n log n + k(Lk + n) + P s²(s + k)) | O(N + k) | Filter O(N); seed O(n); bucketing O(n log n); growth: k steps, each pricing L locations at up to k + 1 positions and scanning a bucket; 2-opt: O(s²) moves per pass, each scored in O(s + k) |
| C | As B, plus O(k) for the waiting test | O(N + k) | Same per call; but a waiting vehicle is asked again every round, so the number of calls per day rises, at most 58 × 10 = 580 |
| C2 | As C, plus O(m log m + k(L′s + s + k)) | O(N + k) | Filling pass: bucket m overdue parcels by location, then up to k steps that each price L′ locations at s + 1 positions after an O(s + k) slack pass |
| D | As C, plus O(s! · s · log(s! · s)) | O(N + s! · s) | The search: at most s! partial orders, each expanded in O(s) with O(log) heap operations. Capped at s ≤ 8 stops, so a constant (8! = 40,320) in practice; exponential without the cap |
| E | O(N + n log n + n(s + k) + P s²(s + k)) | O(N + k) | Heapify O(n); n pops O(n log n); each popped parcel priced at s + 1 positions after an O(s + k) arrival/slack pass; then 2-opt |

Points to discuss:

- Because L ≤ 36 and k ≈ 30 here, B and C are close to linear in n in practice. In the worst case (k and L growing with n) growth is O(n³), as for A.
- The location buckets are the key data-structure choice: they make the growth step cost depend on L (locations) rather than n (parcels), because all parcels at a location have the same insertion cost.
- 2-opt works on distinct stops (s), not parcels (k), since parcels at one stop are delivered together; this shrinks the search.
- Each move is scored in full (O(s + k)), not with the classic O(1) four-edge delta, for two reasons: the interface describes distances as directed (reversing a segment reverses its legs), and the on-time count depends on the arrival time at every later stop. (In this data the matrix is in fact symmetric.)
- P is not bounded by a polynomial in theory (each kept move strictly shortens the trip, and there are finitely many orders), but is small in practice. A pass cap would make the bound strict.
- Space: candidate lists, buckets and one trial route at a time. The distance matrix (37 × 37 = 1,369 entries) belongs to the simulator and is not copied.

Measured runtime (whole simulator plus performance monitor, 20 days, run one after another in one session on a MacBook, includes Python start-up; treat as rough):

| Policy | Wall time for 20 days |
| --- | --- |
| baseline | 7.7 s |
| A | 10.0 s |
| A2 | 10.7 s |
| B | 18.4 s |
| C without waiting (ablation) | 18.1 s |
| C | 25.5 s |

A second session timed C, D and E with the simulator only (no performance monitor): C 20.3 s, **D 22.7 s**, **E 13.4 s** for 20 days. D costs about 12% more than C for its exact search. E is the fastest of the three: its heap selection costs O(n log n + n(s + k)), against C's O(k(Lk + n)) cheapest-insertion search.

Every policy runs a full day in under 1.3 s, far below the 10-minute planning interval. B costs about 1.7× A2, consistent with the insertion search and 2-opt. C costs about 1.4× B because waiting vehicles are re-planned every round (more `dispatch` calls), which matches the complexity analysis. Timings vary between sessions by up to about 30%, so compare only within a session.

## 6. Experimental results

All results: 20 days, means of the daily `metrics.json` values (unweighted mean over days). Paired tests compare two policies on the same 20 days (df = 19; |t| > 2.093 means p < 0.05; sign test two-sided).

### 6.1 Main table

| Policy | On-time rate (sd) | Min to max by day | Delivery rate | On time / late / early / undelivered per day | Trips per day | Parcels per trip | km per day | km per delivered parcel |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 0.2741 (0.016) | 0.2475 to 0.3118 | 0.4045 | 217 / 104 / 0 / 472 | 20.7 | 15.6 | 5204 | 16.33 |
| A `edf_nn` | 0.4141 (0.046) | 0.3653 to 0.5051 | 0.7885 | 329 / 282 / 15 / 168 | 22.9 | 27.4 | 4840 | 7.75 |
| A2 `edf_nn_skip_overdue` | 0.5587 (0.048) | 0.4687 to 0.6270 | 0.7835 | 443 / 145 / 33 / 172 | 23.3 | 26.8 | 4787 | 7.73 |
| B `grow_2opt` | 0.6117 (0.026) | 0.5665 to 0.6487 | 0.8653 | 485 / 0 / 201 / 107 | 32.5 | 21.2 | 3949 | 5.76 |
| C without waiting (ablation) | 0.8317 (0.033) | 0.7809 to 0.8871 | 0.8317 | 660 / 0 / 0 / 134 | 32.2 | 20.5 | 3874 | 5.88 |
| C `grow_2opt_wait` | 0.9408 (0.031) | 0.8356 to 0.9615 | 0.9408 | 746 / 0 / 0 / 47 | 28.8 | 26.0 | 3303 | 4.43 |
| **C2 `grow_2opt_wait_fill`** | **0.9408 (0.030)** | **0.8356 to 0.9615** | **0.9546** | **746 / 11 / 0 / 36** | **28.8** | **26.4** | **3325** | **4.39** |
| D `ucs_routing` | 0.9419 (0.031) | 0.8356 to 0.9615 | 0.9419 | 747 / 0 / 0 / 46 | 28.8 | 26.0 | 3302 | 4.43 |
| E `least_slack` | 0.8961 (0.034) | 0.8296 to 0.9598 | 0.8961 | 711 / 0 / 0 / 82 | 28.2 | 25.3 | 4033 | 5.68 |

Average earliness and lateness of the parcels that were early or late (minutes):

| Policy | Mean minutes early (early parcels only) | Mean minutes late (late parcels only) |
| --- | --- | --- |
| baseline | none early | 214 |
| A | 15 | 73 |
| A2 | 37 | 115 |
| B | 37 | none late |
| C without waiting | none early | none late |
| C | none early | none late |
| C2 | none early | not computed |

Fleet usage (from the `trips`, `total_km`, `capacity_utilisation` and `range_utilisation` metrics, means of daily values; capacity utilisation = size delivered / (trips × 30), range utilisation = km driven / (trips × 320 km)):

| Policy | Trips per day | km per day | Capacity utilisation | Range utilisation |
| --- | --- | --- | --- | --- |
| baseline | 20.6 | 5204 | 0.4983 | 0.7883 |
| A | 22.9 | 4840 | 0.8717 | 0.6631 |
| A2 | 23.2 | 4787 | 0.8536 | 0.6472 |
| B | 32.5 | 3949 | 0.6776 | 0.3805 |
| C | 28.8 | 3303 | 0.8288 | 0.3594 |
| C2 | 28.8 | 3325 | 0.8412 | 0.3618 |
| D | 28.8 | 3302 | 0.8284 | 0.3587 |
| E | 28.2 | 4033 | 0.8070 | 0.4484 |

Reading it:

- The baseline is **range-bound**: its zigzag routes use 79% of the range while vehicles leave only half full.
- A and A2 fill vehicles (85 to 87%) because shorter tours let more parcels fit under the range limit.
- B and C use only about 36 to 38% of the range: once trips are clustered, range stops being the binding constraint, and capacity and time windows take over.
- C's waiting rule raises capacity utilisation from 0.68 (B) to 0.83 with fewer trips, which is where its lower km per day comes from.

### 6.2 Paired comparisons (on-time rate)

| Comparison | Mean difference | Range of daily differences | Days the first policy wins | Sign test p | Paired t |
| --- | --- | --- | --- | --- | --- |
| A vs baseline | +0.1400 | +0.058 to +0.235 | 20/20 | < 0.001 | 11.98 |
| A2 vs A | +0.1447 | +0.071 to +0.213 | 20/20 | < 0.001 | 17.59 |
| B vs A2 | +0.0530 | −0.028 to +0.158 | 16/20 | 0.012 | 4.30 |
| C without waiting vs B | +0.2200 | +0.166 to +0.280 | 20/20 | < 0.001 | 33.03 |
| C vs C without waiting | +0.1091 | +0.019 to +0.175 | 20/20 | < 0.001 | 11.68 |
| C vs B | +0.3291 | +0.187 to +0.390 | 20/20 | < 0.001 | 31.11 |
| C vs A2 | +0.3821 | +0.247 to +0.485 | 20/20 | < 0.001 | 27.08 |
| D vs C | +0.0011 | 0 to +0.019 | 2/20 (18 ties, 0 losses) | 0.50 | 1.19 |
| E vs C | −0.0447 | −0.126 to +0.024 | 4/20 (16 losses) | 0.012 | −5.04 |

C2's on-time rate is **identical to C's on every one of the 20 days** (the per-day column below applies to both). Its delivery rate is higher on average: 0.9546 against 0.9408.

### 6.3 On-time rate by day

| Day | baseline | A | A2 | B | C without waiting | C |
| --- | --- | --- | --- | --- | --- | --- |
| day_001 | 0.2666 | 0.4631 | 0.6270 | 0.5995 | 0.8360 | 0.9186 |
| day_002 | 0.2902 | 0.3666 | 0.5440 | 0.6438 | 0.8523 | 0.9171 |
| day_003 | 0.2645 | 0.3967 | 0.5113 | 0.6259 | 0.8791 | 0.9446 |
| day_004 | 0.2537 | 0.4542 | 0.5928 | 0.6213 | 0.8156 | 0.8886 |
| day_005 | 0.2854 | 0.3970 | 0.5521 | 0.6216 | 0.8871 | 0.9615 |
| day_006 | 0.2666 | 0.4337 | 0.6110 | 0.6441 | 0.8814 | 0.9541 |
| day_007 | 0.3118 | 0.3702 | 0.4783 | 0.6062 | 0.8137 | 0.9615 |
| day_008 | 0.2475 | 0.3762 | 0.5297 | 0.6448 | 0.8304 | 0.9443 |
| day_009 | 0.2732 | 0.5013 | 0.5727 | 0.6266 | 0.8383 | 0.9449 |
| day_010 | 0.2639 | 0.3687 | 0.5820 | 0.5808 | 0.8101 | 0.9568 |
| day_011 | 0.2822 | 0.4530 | 0.5965 | 0.5817 | 0.7809 | 0.9554 |
| day_012 | 0.2733 | 0.3653 | 0.4687 | 0.6271 | 0.7931 | 0.9540 |
| day_013 | 0.2535 | 0.4689 | 0.6134 | 0.6210 | 0.8251 | 0.9607 |
| day_014 | 0.2699 | 0.5051 | 0.6041 | 0.6131 | 0.8483 | 0.9602 |
| day_015 | 0.3053 | 0.3945 | 0.5415 | 0.5666 | 0.7839 | 0.9322 |
| day_016 | 0.2811 | 0.4228 | 0.6035 | 0.5972 | 0.8770 | 0.9586 |
| day_017 | 0.2750 | 0.3929 | 0.4968 | 0.5792 | 0.8226 | 0.9556 |
| day_018 | 0.2647 | 0.3735 | 0.4993 | 0.6186 | 0.8506 | 0.9554 |
| day_019 | 0.2823 | 0.3952 | 0.5885 | 0.6487 | 0.8168 | 0.8356 |
| day_020 | 0.2711 | 0.3824 | 0.5614 | 0.5665 | 0.7916 | 0.9565 |

### 6.4 Policies D and E against C

- **D (exact routing):** over 20 days C produced 576 trips; 364 (63%) had 2 to 8 stops and were searched; UCS found a strictly shorter feasible order for only **12 of them (3.3%)**, saving 3.0 km per day in total. In the other 97% of searched trips, C's 2-opt route was already optimal. D's on-time rate equals C's on 18 days and is higher on day_010 (+0.0037) and day_015 (+0.0188); these gains come from knock-on effects (a vehicle returning a few minutes earlier is free for the next round), not from the routes themselves. The 20-day gain (+0.0011) is not significant.
- **E (least slack first):** 0.8961, below C on 16 of 20 days (−0.045 on average, significant). With the same timing rules, picking the most urgent parcel first pulls parcels from across town, so trips drive 22% more km (4033 against 3303 per day; 5.68 against 4.43 km per parcel) and deliver 35 fewer parcels per day. But E **beats C on day_002, day_004, day_016 and day_019**, and day_004 and day_019 are C's two weakest days (the late-morning surge days). On those days urgency-first protects parcels that C's distance-first growth strands.

Scratch experiment (not in the repository): giving A2 C's timing rules. Only adding a parcel if every parcel on the nearest-neighbor tour arrives inside its window gives 0.6932; adding C's wait-for-fuller-trips rule as well gives 0.7591 (A2: 0.5587, C: 0.9408). So C's advantage over A2 splits roughly in half: about +0.20 from timing rules, about +0.18 from distance-first clustered selection with deadline checks.

### 6.5 Policy C threshold tuning (from `tune_grow_2opt_wait.py`)

Mean on-time rate of C for each setting, on the tuning days (day_001 to day_010) and the test days (day_011 to day_020). The setting was chosen by the tuning column only.

| MIN_FILL | WAIT_SLACK (min) | Tuning days | Test days |
| --- | --- | --- | --- |
| 0.0 (waiting rule off) | any | 0.8444 | 0.8190 |
| 0.25 | 10 / 20 / 40 | 0.8980 | 0.8876 |
| 0.5 | 10 or 20 | 0.9308 | 0.9356 |
| 0.5 | 40 | 0.9281 | 0.9288 |
| **0.75** | **10** | **0.9392** | **0.9424** ← chosen |
| 0.75 | 20 | 0.9372 | 0.9404 |
| 0.75 | 40 | 0.9330 | 0.9329 |
| 0.9 | 10 | 0.9387 | 0.9537 |
| 0.9 | 20 | 0.9368 | 0.9517 |
| 0.9 | 40 | 0.9337 | 0.9438 |

Reading it:

- With the waiting rule off, `WAIT_SLACK` has no effect (identical rows), as expected.
- Waiting for fuller trips helps steadily up to 0.75: 0.82 → 0.89 → 0.94 on the test days.
- A longer `WAIT_SLACK` is slightly worse at every fill level, because holding parcels back longer leaves less margin later.
- The chosen setting scores **higher** on the test days (0.9424) than on the tuning days (0.9392), so there is no sign of overfitting. 0.9 would have scored higher on the test days (0.9537), but choosing it would mean choosing on the test data; the honest choice is 0.75.

## 7. Key findings (the story of the results)

1. **Shorter tours mean more deliveries.** The baseline's arrival-order routes zigzag: 15.6 parcels per trip and 16.3 km per delivered parcel. Nearest-neighbor ordering (A) halves the km per parcel (7.75) and nearly doubles the delivery rate (0.40 → 0.79), because more parcels fit under the 320 km range.
2. **Deadline order alone is not enough.** EDF serves parcels that are already lost first. Skipping them until savable parcels are served (A2) adds +0.145 on-time rate, wins on every day and halves late parcels (282 → 145), at the same delivery rate. The cheapest idea in the project: an O(n) split.
3. **Clustering by location cuts cost and lateness, but not early deliveries.** B builds trips from nearby parcels while protecting every deadline: zero late parcels and 18% fewer km per day than A2 (3949 against 4787). But its on-time gain over A2 is modest (+0.053, 16 of 20 days), because about 201 parcels per day arrive **before** their window opens and do not count.
4. **Not delivering early is the biggest single gain.** Refusing early arrivals (C without waiting) turns those wasted deliveries into on-time ones: +0.220 over B, every day, the largest step in the project. Delivery rate drops slightly (0.87 → 0.83), but every delivery now counts.
5. **Waiting for fuller trips is free and helps again.** Holding a nearly empty trip for one round when no parcel on it would become late adds +0.109 (every day), reaching **0.9408**. It also makes trips fuller (20.5 → 26.0 parcels per trip), so C uses fewer trips (28.8 against 32.2) and the fewest km of any policy (3303 per day, 4.43 per parcel).
6. **Late deliveries can be added for free.** C2 rides overdue parcels on C's trips only where the detour delays no on-time parcel. On-time rate is unchanged on every day, 11 more parcels per day are delivered (late), never-delivered parcels fall from 47 to 36, and km per delivered parcel even improves slightly (4.43 → 4.39) because the extra parcels mostly join stops already on the route. Total km per day rises only 0.7% (3303 → 3325).
7. **The best policy is also the cheapest.** C beats every other policy on the metric **and** on km per delivered parcel. Better timing removed wasted trips rather than adding cost.
8. **Remaining gap.** C reaches 0.9408 against an optimistic ceiling of about 0.9646 (97.5% of it). It leaves 47 parcels undelivered per day; about 28 of those could not have been on time under any policy, leaving roughly 19 per day that a better policy might save.
9. **Optimal routing buys almost nothing here.** Exact uniform-cost search (D) found a shorter order than 2-opt on only 3.3% of searched trips, saving 3 km per day, and changed the on-time rate on 2 of 20 days. Routing is not the bottleneck: trips use only about 36% of their range, and 2-opt is already optimal on almost every trip. Selection and timing decide the result.
10. **Distance-first beats urgency-first, except on surge days.** Least slack first from a heap (E) scores 0.8961 against C's 0.9408 with the same timing rules: urgency-first selection drives 22% more km. But E wins on C's two weakest days (day_004, day_019), which points to a hybrid (urgency-first when many parcels are close to their deadline, distance-first otherwise) as the most promising next step. Not implemented.

Where each approach performs well or poorly (the brief asks for this):

- **A2 vs B:** A2 beats B on 4 days (day_001, day_010, day_011 and day_016, by up to 0.028). Not analysed further.
- **C's weak days:** day_019 (0.8356) and day_004 (0.8886) are C's worst; every other day is at least 0.9171. On day_019, 105 of C's 131 undelivered parcels arrived between 10:00 and 12:59, and 73 had windows ending in the 15:00 hour; that day has no arrivals between 09:00 and 09:59 and a large surge from 10:00. day_004 shows a smaller version of the same pattern (65 undelivered with windows ending in the 14:00 hour). A plausible reading is that a late-morning surge with tight windows exceeds what 10 vehicles can serve in time, but this has **not** been tested; present it as an observation.
- **B and C** are the most efficient in km per parcel; **A and A2** make fewer, fuller trips but drive further.
- The **baseline** is the most consistent (sd 0.016) only because it is uniformly poor.

## 8. Trade-offs to discuss

- **Coverage vs punctuality.** C never delivers a parcel it cannot deliver on time, so 47 parcels per day are not delivered at all. The metric gives no credit for a late delivery, so this is optimal for the metric, but a real company would still want late parcels delivered. **C2 addresses this**: it fills spare capacity on C's trips with overdue parcels whenever that delays no on-time parcel, delivering 11 more per day at no cost to the on-time rate. 36 per day are still never delivered: C2 only uses trips C sends anyway, and does not send extra trips just for late parcels. Sending such trips was not tried; it could delay later on-time trips.
- **Waiting vs responsiveness.** C's waiting rule only holds a trip when every parcel on it has at least 10 minutes of slack, so waiting never causes a lateness on that trip. It still delays parcels relative to "leave now", and it increases the number of `dispatch` calls (runtime 25.5 s against 18.4 s for B over 20 days).
- **Thresholds vs generality.** C has two tuned parameters. The tuning/test split shows they generalise across these 20 days, but they may need re-tuning for a different town, fleet or demand pattern.
- **Heuristic vs optimal.** All policies are greedy and myopic, plus a local search. None coordinates across vehicles or looks ahead to future arrivals.

## 9. Recommendation and conclusion points

- **Recommended policy: C2 `grow_2opt_wait_fill`** (or C, if the team prefers the simpler policy). Both have the highest on-time rate (0.9408) and beat every earlier policy on all 20 days. C2 matches C's on-time rate on every day and also delivers 11 more parcels per day (delivery rate 0.9546), with the lowest km per delivered parcel (4.39). It is the better choice for a real operator, since it serves more customers at no cost to punctuality.
- If the report recommends C2, state clearly that C2's gain is on delivery rate, not on the headline metric.
- D and E are not recommended: D matches C at higher cost, and E scores lower. Both are valuable as experiments: D shows routing is not the bottleneck, E shows distance-first selection matters except on surge days.
- Conclusion themes: choose parcels that are close together; never spend capacity on lost causes; never deliver early when the metric does not reward it; do not send nearly empty trips when waiting is free; the best policy for service was also the cheapest to run.

## 10. Limitations and threats to validity

- 20 days of data from one town; results may not transfer to other demand patterns or fleet sizes.
- Every policy plans one vehicle's trip at a time, with no coordination across vehicles or look-ahead to future arrivals.
- 2-opt is a local search: it stops at a route that no single reversal improves, which may not be optimal.
- C's two thresholds were tuned on day_001 to day_010; the reported 20-day mean (0.9408) includes those tuning days. The test-day mean alone is 0.9424.
- Runtimes are wall-clock times including the simulator and Python start-up, from single runs on one laptop.
- The upper bound in section 2 ignores fleet size and capacity, so the true ceiling is lower.
- The cause of C's weak days (section 7) is an observation, not a tested explanation.

## 11. Reproducing the results

From the project root, Python 3.9 or later, standard library only:

```sh
python3 run_experiments.py                                        # every policy, all 20 days, prints the table
python3 run_experiments.py --policies grow_2opt grow_2opt_wait    # selected policies
python3 run_experiments.py --summary-only --per-day               # re-print from existing results
python3 tune_grow_2opt_wait.py                                    # Policy C threshold grid search (about 2.5 min)
```

Outputs: `results/<policy>/day_XXX/log.txt` (event log) and `metrics.json` (metrics), `results/summary.csv`, `results/summary_per_day.csv` and `results/tuning_grow_2opt_wait.csv`. The README also gives the equivalent shell loop. Runs are deterministic: repeating a command gives byte-for-byte identical logs.

Not yet reproducible from the repository: the full 20-day run of "C without waiting" (section 6, made from a scratch module), the paired tests, the per-day upper bound and the day_019 breakdown (made with a scratch analysis script). The tuning table's `MIN_FILL = 0.0` rows reproduce "C without waiting" on both halves of the days.

## 12. Open items before submission

- `results/` is listed in `.gitignore`, but the brief requires `results/` in the ZIP. Make sure it is included in the submission.
- Decide whether to add the analysis script (paired tests, upper bound, per-day tables) and the "C without waiting" ablation to the repository, so every number in the report can be reproduced.
- Confirm which "algorithm and data structure taught in class" the report will name, against the syllabus.
- README "Recommended policy: [name]" still needs filling in (C, if the team agrees).
- Policy D and E are implemented; a hybrid of C and E (section 7, finding 10) is not.
- References still need to be added (candidates below).

## 13. Design history worth one paragraph (optional)

An earlier version of Policy B (Marcus's, since replaced) used a 2-opt that only minimised distance. On the same 20 days, removing that 2-opt **raised** the on-time rate (0.5912 → 0.6104), and changing its acceptance rule to "more on-time stops first, then shorter" raised it to 0.7331. The lesson, that local search must optimise the real objective and not a proxy, is why the current B and C keep a 2-opt move only if the on-time count does not fall. That code is no longer in the repository, so these numbers cannot be reproduced from the submission; use them only as a design note, if at all.

## 14. Candidate references (verify each before citing)

- Croes, G. A. (1958). A method for solving traveling-salesman problems. *Operations Research*, 6(6), 791–812. (Origin of 2-opt.)
- Liu, C. L., & Layland, J. W. (1973). Scheduling algorithms for multiprogramming in a hard-real-time environment. *Journal of the ACM*, 20(1), 46–61. (Earliest Deadline First.)
- Rosenkrantz, D. J., Stearns, R. E., & Lewis, P. M. (1977). An analysis of several heuristics for the traveling salesman problem. *SIAM Journal on Computing*, 6(3), 563–581. (Nearest neighbor and insertion heuristics.)
- Solomon, M. M. (1987). Algorithms for the vehicle routing and scheduling problems with time window constraints. *Operations Research*, 35(2), 254–265. (Vehicle routing with time windows, insertion heuristics.)
- The IS115 project brief and the supplied simulator.

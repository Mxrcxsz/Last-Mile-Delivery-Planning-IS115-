# IS115 Last-Mile Delivery: findings for the report

Prepared 12 Nov 2026 from the code on branch `marcus` after the policies were merged into four files. Deadline: Fri 13 Nov 2026, 23:59.

## How to use this file

This is source material for writing the project report. It is not the report.

- Every number below comes from runs of the code in this repository on day_001 to day_020. Do not invent numbers or round them differently from what is here; if a number is needed that is not here, ask for it to be computed.
- The report is limited to **8 pages, excluding references**. Prioritise by the rubric weights below.
- The submitted policies are the supplied **baseline** and four team policies: **A** `edf_nn_wait`, **B** `grow_2opt_wait_fill`, **C** `least_slack`, **D** `ucs_routing`.
- Earlier versions (A without waiting, A with overdue parcels last, B without its timing rules, B without filling) were merged into these four. They are **not** separate policies in the submission. Section 7 gives their numbers as the design history (how each idea earned its gain); they are reproducible from git commit `92948fd` or, for one step, from the tuning script.
- Each team member will be asked an exam question about this work (10% of the grade), so explanations should be ones a student can defend, not just state.

## 1. What the brief requires

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
4. The solution must **meaningfully incorporate at least one algorithm and one data structure taught in class** (section 4.6).
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

**Upper bound on the metric.** A parcel is counted impossible to deliver on time if, even sent alone on the first planning round after it arrives, it would reach its location after `window_end`, or could not get back by 18:00. This ignores fleet size and capacity, so it is an optimistic ceiling. On average **28.05 parcels per day (23 to 33)** are impossible, so no policy can exceed an on-time rate of about **0.9646** (0.9585 to 0.9715 by day). Policy B's 0.9408 reaches about **97.5%** of this ceiling.

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
- Delivering everything as fast as possible does not maximise it either, because early deliveries do not count. A policy must balance coverage (deliver many) against timing (deliver inside the window). The design history shows this directly: an early version of B delivered 87% of parcels but only 61% on time (section 7).
- It is a customer-facing service measure: a delivery outside the promised window means a missed customer, a failed handover or a complaint.

Supporting metrics, also in every `metrics.json`: `parcels_total`, `parcels_delivered`, `parcels_on_time`, `parcels_late`, `parcels_early`, `delivery_rate`, `km_per_delivered_parcel` (an operating-cost proxy), `trips`, `total_km`, `km_per_trip`, `parcels_per_trip`, `capacity_utilisation` (size delivered / (trips × 30)) and `range_utilisation` (km driven / (trips × 320)).

Assumptions: one simulated day per CSV; all parcels arrive by 17:30; time windows taken exactly as given; km driven is rebuilt from the order of delivery events within each trip.

## 4. Algorithmic approaches

Every policy makes four choices at each `dispatch` call: **timing** (leave now or wait), **selection** (which waiting parcels go on this trip), **routing** (the order of stops) and **filling** (whether parcels that can only be late ride along). Policies B, C and D share timing and filling and each differs from B in one choice, so each comparison isolates one idea.

**Code convention.** A policy file never imports another policy file. Everything two or more policies use lives in `solution/policies/helpers.py`; each policy keeps its own thresholds as constants and passes them to the helpers. Each policy file starts with a docstring giving its rules and complexity.

Shared building blocks (`helpers.py`):

- `waiting_parcels`, `route_distance` (uses `math.fsum`, as the simulator does, so the policy's check and the simulator's agree exactly), `within_limits` (range ≤ 320 km and back by 18:00).
- `can_still_be_on_time`: departure + direct drive from the hub ≤ `window_end`. A parcel that fails this is **overdue**: it can only be late.
- `on_time_candidates`: waiting parcels that can still be on time and fit a trip on their own. `reachable_in_window`: a direct drive arrives inside the window. `overdue_parcels`.
- `nearest_neighbor_order`: from the hub, always drive to the closest remaining stop. O(k²).
- `group_by_stop`, `stop_arrivals`, `stops_distance`, `is_on_time`, and `trip_timing`, which returns a route's stops, arrival times, km and **slack** (how many minutes each suffix of the route can be delayed before an on-time parcel turns late).
- `grow_trip`: cheapest-insertion trip building (see Policy B).
- `two_opt`: 2-opt over distinct stops, keeping a move only if strictly shorter and the on-time count does not fall.
- `should_wait(route, ..., min_fill, wait_slack)`: the waiting rule.
- `fill_overdue`: overdue filling.
- Constants `HUB`, `MINUTES_PER_KM` and `PLANNING_INTERVAL` are imported from the supplied simulator.

### 4.1 Baseline (`baseline.py`, supplied, unchanged)

- Selection: try every waiting parcel in arrival order (parcel ID breaks ties); skip one that breaks capacity, range or the return cutoff, keep trying later ones. Ignores windows.
- Routing: stops visited in selection order.
- Timing: leave whenever at least one parcel fits.
- Weakness: arrival order is geographically random, so routes zigzag and use up range quickly; it delivers only about 40% of parcels.

### 4.2 Policy A: `edf_nn_wait.py` (Earliest Deadline First, Nearest Neighbor, on-time-only trips)

- Selection: only parcels that can still be on time (overdue parcels are never sent), tried by earliest `window_end` (Earliest Deadline First, a classic scheduling rule; parcel ID breaks ties). Keep a parcel only if capacity allows and the nearest-neighbor tour that includes it meets range and the cutoff **and delivers every parcel on it inside its window** (none early, none late).
- Routing: nearest neighbor from the hub.
- Timing: return `[]` if nothing fits, or if the trip is nearly empty (load below 75% of capacity) and every parcel on it can still be on time one round later. Uses Policy B's thresholds; not tuned separately.
- Strength: simple, and every delivery counts.
- Weakness: deadline order pulls parcels from all over town, and nearest neighbor ignores windows, so many candidates are rejected because the tour would make some parcel early or late. It leaves 191 parcels per day undelivered.

### 4.3 Policy B: `grow_2opt_wait_fill.py` (cheapest insertion, 2-opt, timing rules, overdue filling) — recommended

- Selection: candidates are parcels that can still be on time and fit alone. Seed: the most urgent one (earliest window end) that a direct drive reaches **inside** its window. Then grow the trip by **cheapest insertion**: repeatedly add the candidate whose best insertion position adds the fewest km (ties: earliest window end, parcel ID). A parcel can be added only if:
  - capacity, range and the 18:00 cutoff still hold;
  - it arrives **inside** its window (never early, never late);
  - no parcel already on the trip is pushed past its window end (checked with the slack array).
- Data structure: a **hash map from location to a list of parcels sorted by (window end, parcel ID)**. All parcels at one location cost the same to insert, so each step prices each location once per position instead of each parcel.
- Routing: insertion order, then **2-opt** over the distinct stops: reverse a segment of stops; keep the move only if the trip gets strictly shorter and the on-time count does not fall. First improvement: restart after each kept move, stop when no move helps.
- Timing: return `[]` (wait 10 minutes) if no candidate can be reached inside its window yet, or if the trip is **nearly empty** (load below `MIN_FILL` = 75% of capacity) and every parcel on it still has at least `WAIT_SLACK` = 10 minutes of slack one round later. `MIN_FILL` and `WAIT_SLACK` were chosen by grid search on day_001 to day_010 only and checked on day_011 to day_020 (section 6.5).
- Filling: when the trip leaves, its spare capacity is filled with **overdue** parcels by cheapest insertion, but only where the detour pushes no on-time parcel past its window end. An overdue parcel can only be late (by definition even a direct drive arrives after its window closes), so it earns nothing on the metric; filling only adds deliveries that cost no on-time delivery on that trip. Overdue parcels never cause a departure, a wait or an extra trip.
- Consequence: B never delivers early; its only late deliveries are overdue parcels that would otherwise not be delivered at all.

### 4.4 Policy C: `least_slack.py` (least slack first from a min-heap)

- Selection: candidates as in B. A parcel's **slack** = window end − (departure + direct drive from the hub): minutes it can still afford to wait. Seed: the least-slack candidate a direct drive reaches inside its window. All other candidates go into a **min-heap** keyed by (slack, window end, parcel ID) and are popped most urgent first. Each popped parcel is inserted at its cheapest feasible position (inside its window, nobody pushed late, capacity, range and cutoff hold), or skipped.
- Routing, timing and filling: as B (same 2-opt, same thresholds, same filling).
- Idea it tests: **urgency-first** selection ("least laxity first") against B's **distance-first** selection, everything else equal.

### 4.5 Policy D: `ucs_routing.py` (Policy B with exact routing by uniform-cost search)

- Selection, timing and filling: as B.
- Routing: B's 2-opt route, then, if the trip has **at most 8 distinct stops**, uniform-cost search finds the shortest order that arrives at every stop inside its interval [latest window start, earliest window end of its parcels] and returns to the hub:
  - state = (current location, set of visited stops as a bitmask); cost = km driven so far;
  - km equals minutes, so the cost also gives the arrival time; a move is allowed only if it arrives inside the next stop's interval;
  - states are expanded cheapest first from a **min-heap**, so the first complete tour popped is the shortest feasible one (Dijkstra's algorithm on the state graph);
  - the 2-opt route is feasible, so its length is an upper bound for pruning;
  - the new order is used only if strictly shorter. Filling then runs on the final order.
- Correctness point: states with the same (location, visited set) are **not** merged. With time windows and no waiting at stops, arriving later can make a later stop feasible, so the cheaper path does not dominate.
- Why the cap: the number of stop orders grows as s!, so exact routing is exponential in the number of stops. 71% of B's trips have at most 8 stops.
- Idea it tests: how much does an optimal stop order gain over 2-opt, everything else equal?

### 4.6 Algorithms and data structures used (for the "taught in class" requirement)

Check against the IS115 syllabus and name the course topics explicitly.

| Item | Where it is used |
| --- | --- |
| Sorting (Timsort, O(n log n)) | Deadline order in A; deadline-sorted location buckets in B, C, D |
| Greedy algorithms | Every policy builds trips greedily (Earliest Deadline First, nearest neighbor, cheapest insertion) |
| Local search | 2-opt in B, C, D |
| Graph search: uniform-cost search (Dijkstra on the state graph) | Exact routing in D |
| Priority queue (binary min-heap, `heapq`) | Least-slack order in C; search frontier in D |
| Hash tables (`dict`) | `parcel` records; distance lookup `travel_distance[origin][destination]`; location → sorted parcel list buckets in B, C, D |
| Bitmask as a set | Visited stops in D's search states |
| Graph (complete weighted graph as an adjacency matrix in nested dicts) | The distance lookup; routing is a TSP-style tour on it |
| Grid search with a tuning/test split | Choosing B's two thresholds |

## 5. Computational complexity

Notation: N = arrived parcels, n = candidate parcels (n ≤ N), k = parcels in the trip (capacity limits k to about 30 here), L = distinct locations among the candidates (L ≤ 36), s = distinct stops in the trip (s ≤ min(k, L)), P = number of improving 2-opt passes, m = overdue parcels at L′ locations. Complexity is per `dispatch` call. A day has 58 planning rounds and up to 10 calls per round.

| Policy | Time per `dispatch` call | Space | Where the time goes |
| --- | --- | --- | --- |
| baseline | O(N + n log n) | O(n + k) | Sort by arrival, then an O(1) check per candidate |
| A | O(N + n log n + n k²) | O(n + k) | Sort; each of n candidates may need a nearest-neighbor tour, O(k²), plus an O(k) window check; waiting test O(k) |
| B | O(N + n log n + k(Lk + n) + P s²(s + k) + m log m + k(L′s + s + k)) | O(N + k) | Filter O(N); bucketing O(n log n); growth: k steps, each pricing L locations at up to k + 1 positions; 2-opt: O(s²) moves per pass, each scored in O(s + k); waiting O(k); filling as growth over the overdue buckets |
| C | O(N + n log n + n(s + k) + P s²(s + k)) plus filling as B | O(N + k) | Heapify O(n); n pops O(n log n); each popped parcel priced at s + 1 positions after an O(s + k) timing pass; 2-opt as B |
| D | As B, plus O(s! · s · log(s! · s)) | O(N + s! · s) | The search: at most s! partial orders, each expanded in O(s) with O(log) heap operations; capped at s ≤ 8, so a constant (8! = 40,320) in practice; exponential without the cap |

Points to discuss:

- Because L ≤ 36 and k ≈ 30 here, B is close to linear in N in practice. In the worst case (k and L growing with n) its growth step is O(n³), as for A.
- The location buckets make B's growth cost depend on L (locations) rather than n (parcels), because all parcels at a location have the same insertion cost. This is the key data-structure choice.
- 2-opt works on distinct stops (s), not parcels (k), since parcels at one stop are delivered together.
- Each move is scored in full (O(s + k)), not with the classic O(1) four-edge delta, because the interface describes distances as directed (reversing a segment reverses its legs) and the on-time count depends on the arrival time at every later stop. (In this data the matrix is in fact symmetric.)
- P is not bounded by a polynomial in theory (each kept move strictly shortens the trip and there are finitely many orders), but is small in practice; a pass cap would make the bound strict.
- C trades B's O(k(Lk + n)) cheapest-insertion search for O(n log n + n(s + k)) heap selection. With n in the hundreds and L ≤ 36, that is more work in practice, not less (measured below).
- Waiting does not change the cost of one call, but a waiting vehicle is asked again every round, so the number of calls per day rises, to at most 58 × 10 = 580.

Measured runtime: time spent inside each policy's `dispatch()` only (not the simulator, the performance monitor or Python start-up), from `python3 run_experiments.py --workers 1` on a MacBook. Per-day values are in `results/<policy>/<day>/timing.json`; the means are in the `runtime` section of `results/summary.json`. Timings depend on the machine and vary between runs; compare policies within one run.

| Policy | `dispatch()` calls per day | of which waits (`[]`) | Policy time per day | Mean per call | Slowest call |
| --- | --- | --- | --- | --- | --- |
| baseline | 30.7 | 10.1 | 0.009 s | 0.28 ms | 9.9 ms |
| A | 140.1 | 115.8 | 0.083 s | 0.59 ms | 57.7 ms |
| B | 184.8 | 156.1 | 0.206 s | 1.12 ms | 101.3 ms |
| C | 117.0 | 88.9 | 0.259 s | 2.21 ms | 161.4 ms |
| D | 184.8 | 156.0 | 0.486 s | 2.63 ms | 324.2 ms |

Reading it:

- **Compute is negligible.** Even D spends under half a second per day inside the policy, and its slowest single call (324 ms) is far below the 10-minute planning interval. Earlier wall-clock timings of 20 to 40 s per 20 days were almost entirely the simulator and Python start-up.
- **Waiting multiplies the calls.** Policies with the waiting rule are called 117 to 185 times per day against 31 for the baseline, and most calls (76 to 84%) return `[]`. The complexity per call is unchanged, but the number of calls rises, as section 5 predicts.
- **The location buckets pay off.** C (heap, urgency first) costs about twice as much per call as B (2.21 ms against 1.12 ms), although its heap selection looks cheaper on paper. C prices every popped candidate with an O(s + k) timing pass, so its selection is O(n(s + k)) over n parcels, while B's buckets price each of at most L ≤ 36 locations once per position. With hundreds of waiting parcels and only 36 locations, n ≫ L, so B's bucketed cheapest insertion is the cheaper one in practice.
- **Exact routing costs about 2.4× B per day** (0.486 s against 0.206 s), for no meaningful on-time gain (section 6.4). Its slowest call (324 ms) is the factorial search on an 8-stop trip.
- **A** is cheap per call (0.59 ms) despite its n k² worst case, because its trips are built from a sorted list with few accepted parcels.

## 6. Experimental results

All results: 20 days, means of the daily `metrics.json` values (unweighted mean over days). Paired tests compare two policies on the same 20 days (df = 19; |t| > 2.093 means p < 0.05; sign test two-sided). Regenerate with `python3 run_experiments.py --per-day`.

### 6.1 Main table

| Policy | On-time rate (sd) | Min to max by day | Delivery rate | On time / late / early / undelivered per day | Trips per day | Parcels per trip | km per day | km per delivered parcel |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 0.2741 (0.016) | 0.2475 to 0.3118 | 0.4045 | 217 / 104 / 0 / 472 | 20.6 | 15.6 | 5204 | 16.33 |
| A `edf_nn_wait` | 0.7591 (0.056) | 0.6619 to 0.8750 | 0.7591 | 603 / 0 / 0 / 191 | 24.3 | 24.8 | 3900 | 6.49 |
| **B `grow_2opt_wait_fill`** | **0.9408 (0.031)** | **0.8356 to 0.9615** | **0.9546** | **746 / 11 / 0 / 36** | **28.8** | **26.4** | **3325** | **4.39** |
| C `least_slack` | 0.8956 (0.035) | 0.8296 to 0.9598 | 0.9384 | 711 / 34 / 0 / 49 | 28.1 | 26.5 | 4046 | 5.44 |
| D `ucs_routing` | 0.9419 (0.031) | 0.8356 to 0.9615 | 0.9546 | 747 / 10 / 0 / 36 | 28.8 | 26.3 | 3324 | 4.39 |

Fleet usage (means of daily values; capacity utilisation = size delivered / (trips × 30), range utilisation = km driven / (trips × 320 km)):

| Policy | Capacity utilisation | Range utilisation |
| --- | --- | --- |
| baseline | 0.4983 | 0.7883 |
| A | 0.7887 | 0.5028 |
| B | 0.8412 | 0.3618 |
| C | 0.8459 | 0.4505 |
| D | 0.8396 | 0.3611 |

- The baseline is **range-bound**: zigzag routes use 79% of the range while vehicles leave half full.
- B and D use only about 36% of the range: once trips are clustered, range stops being the binding constraint, and capacity and time windows take over.
- C fills vehicles as well as B but drives 25% further per trip (range utilisation 0.45 against 0.36), because urgent parcels are spread across town.

### 6.2 Paired comparisons (on-time rate)

| Comparison | Mean difference | Range of daily differences | Days the first policy wins | Sign test p | Paired t |
| --- | --- | --- | --- | --- | --- |
| A vs baseline | +0.4850 | +0.372 to +0.593 | 20/20 | < 0.001 | 37.67 |
| B vs A | +0.1817 | +0.080 to +0.266 | 20/20 | < 0.001 | 13.27 |
| C vs A | +0.1365 | +0.056 to +0.272 | 20/20 | < 0.001 | 10.53 |
| C vs B | −0.0452 | −0.126 to +0.024 | 4/20 (16 losses) | 0.012 | −5.04 |
| D vs B | +0.0011 | 0 to +0.019 | 2/20 (18 ties, 0 losses) | 0.50 | 1.19 |

### 6.3 On-time rate by day

| Day | baseline | A | B | C | D |
| --- | --- | --- | --- | --- | --- |
| day_001 | 0.2666 | 0.7797 | 0.9186 | 0.8360 | 0.9186 |
| day_002 | 0.2902 | 0.6619 | 0.9171 | 0.9339 | 0.9171 |
| day_003 | 0.2645 | 0.6801 | 0.9446 | 0.8627 | 0.9446 |
| day_004 | 0.2537 | 0.7760 | 0.8886 | 0.8948 | 0.8886 |
| day_005 | 0.2854 | 0.7916 | 0.9615 | 0.8797 | 0.9615 |
| day_006 | 0.2666 | 0.8253 | 0.9541 | 0.9298 | 0.9541 |
| day_007 | 0.3118 | 0.6957 | 0.9615 | 0.9130 | 0.9615 |
| day_008 | 0.2475 | 0.7203 | 0.9443 | 0.9245 | 0.9443 |
| day_009 | 0.2732 | 0.7732 | 0.9449 | 0.8922 | 0.9449 |
| day_010 | 0.2639 | 0.7398 | 0.9568 | 0.9199 | 0.9605 |
| day_011 | 0.2822 | 0.8750 | 0.9554 | 0.9406 | 0.9554 |
| day_012 | 0.2733 | 0.7063 | 0.9540 | 0.9144 | 0.9540 |
| day_013 | 0.2535 | 0.7262 | 0.9607 | 0.8631 | 0.9607 |
| day_014 | 0.2699 | 0.8380 | 0.9602 | 0.9010 | 0.9602 |
| day_015 | 0.3053 | 0.8103 | 0.9322 | 0.8894 | 0.9510 |
| day_016 | 0.2811 | 0.8143 | 0.9586 | 0.9598 | 0.9586 |
| day_017 | 0.2750 | 0.7681 | 0.9556 | 0.8847 | 0.9556 |
| day_018 | 0.2647 | 0.7064 | 0.9554 | 0.8296 | 0.9554 |
| day_019 | 0.2823 | 0.7440 | 0.8356 | 0.8595 | 0.8356 |
| day_020 | 0.2711 | 0.7506 | 0.9565 | 0.8836 | 0.9565 |

### 6.4 Policies C and D against B

- **C (least slack first):** 0.8956, below B on 16 of 20 days (−0.045 on average, significant). Picking the most urgent parcel first pulls parcels from across town, so C drives 22% more km per day (4046 against 3325) and delivers 35 fewer parcels on time per day. But C **beats B on day_002, day_004, day_016 and day_019**, and day_004 and day_019 are B's two weakest days (late-morning surge days, section 8). On those days urgency-first protects parcels that B's distance-first growth strands.
- **D (exact routing):** equal to B on 18 days, higher on day_010 (+0.0037) and day_015 (+0.0188), never lower. Exact search runs on every candidate trip with 2 to 8 stops (71% of 2,101 calls over 20 days) and finds a strictly shorter order in only 8.2% of them; km per day is essentially unchanged (3325 → 3324). The two better days come from knock-on effects (a vehicle returning a few minutes earlier is free for the next round), not from the routes themselves. The 20-day gain (+0.0011) is not significant (sign test p = 0.50, t = 1.19).

### 6.5 Policy B threshold tuning (`results/tuning_grow_2opt_wait_fill.csv`)

Mean on-time rate of B for each setting, on the tuning days (day_001 to day_010) and the test days (day_011 to day_020). The setting was chosen by the tuning column only.

| MIN_FILL | WAIT_SLACK (min) | Tuning days | Test days |
| --- | --- | --- | --- |
| 0.0 (waiting off) | any | 0.8448 | 0.8187 |
| 0.25 | 10 / 20 | 0.8980 | 0.8875 |
| 0.25 | 40 | 0.8980 | 0.8876 |
| 0.5 | 10 or 20 | 0.9310 | 0.9356 |
| 0.5 | 40 | 0.9282 | 0.9288 |
| **0.75** | **10** | **0.9392** | **0.9424** ← chosen |
| 0.75 | 20 | 0.9372 | 0.9404 |
| 0.75 | 40 | 0.9330 | 0.9329 |
| 0.9 | 10 | 0.9387 | 0.9537 |
| 0.9 | 20 | 0.9368 | 0.9517 |
| 0.9 | 40 | 0.9337 | 0.9438 |

Reading it:

- Waiting for fuller trips helps steadily up to about 0.5 and flattens after: 0.82 → 0.89 → 0.94 on the test days. Anything from 0.5 to 0.9 gives 0.93 to 0.95, so the policy does not depend on a finely tuned number.
- A longer `WAIT_SLACK` is slightly worse at every fill level, because holding parcels back longer leaves less margin later. With waiting off, `WAIT_SLACK` has no effect (identical rows), as expected.
- The chosen setting scores **higher** on the test days (0.9424) than on the tuning days (0.9392): no sign of overfitting. 0.9 scores higher on the test days (0.9537), but choosing it would mean choosing on the test data; the honest choice is 0.75.
- The `MIN_FILL = 0.0` rows are B without its waiting rule: 20-day mean 0.8318 (section 7).
- These are the same choices and nearly the same scores as before overdue filling was added to B; filling does not change the best thresholds.

## 7. Design history: how each idea earned its gain

The four policies are the end of a sequence in which each step added one idea. The intermediate versions are not in the submission as separate files, but the steps make the strongest "which idea earned which gain" argument for the report. Numbers are 20-day mean on-time rates from the same simulator and data.

| Step | Version | On-time rate | Delivery rate | What changed | Reproduce |
| --- | --- | --- | --- | --- | --- |
| 0 | baseline | 0.2741 | 0.4045 | Supplied | `baseline.py` |
| 1 | A without timing rules (`edf_nn`) | 0.4141 | 0.7885 | Earliest Deadline First + nearest neighbor | commit `92948fd` |
| 2 | + overdue parcels last (`edf_nn_skip_overdue`) | 0.5587 | 0.7835 | Do not spend trips on lost causes | commit `92948fd` |
| 3 | **Policy A** (+ on-time-only trips and waiting) | **0.7591** | 0.7591 | Never early or late; wait for fuller trips | `edf_nn_wait.py` |
| 4 | B without timing rules (`grow_2opt`) | 0.6117 | 0.8653 | Cheapest insertion by location, 2-opt; early arrival allowed | commit `92948fd` |
| 5 | + no early deliveries | 0.8318 | not measured | Only add parcels that arrive inside their window (measured with filling on, which does not change the on-time rate) | tuning script, `MIN_FILL = 0.0` rows |
| 6 | + waiting for fuller trips (`grow_2opt_wait`) | 0.9408 | 0.9408 | Wait one round when nearly empty and free | commit `92948fd` |
| 7 | **Policy B** (+ overdue filling) | **0.9408** | **0.9546** | Late parcels ride along where they delay no one | `grow_2opt_wait_fill.py` |

What it shows:

- **Shorter tours mean more deliveries** (step 0 → 1): nearest-neighbor ordering halves km per parcel (16.3 → 7.75) and nearly doubles the delivery rate.
- **Deadline order alone is not enough** (1 → 2): skipping lost causes adds +0.145 at almost no cost (an O(n) split).
- **Timing rules are worth about +0.20 on A** (2 → 3): refusing early and late deliveries and waiting for fuller trips.
- **Clustering cuts cost but not early deliveries** (step 4): B without timing rules has zero late parcels and 18% fewer km than step 2, but delivers about 201 parcels per day early, which do not count.
- **Not delivering early is the largest single gain** (4 → 5): +0.22.
- **Waiting is free and helps again** (5 → 6): +0.11, and trips get fuller (20.5 → 26.0 parcels per trip), so it also cuts km.
- **Filling adds deliveries for free** (6 → 7): on-time rate identical on every day; 11 more parcels delivered per day (late); never-delivered parcels fall from 47 to 36 per day; km per delivered parcel improves slightly (4.43 → 4.39) because most fill parcels join stops already on the route.
- **Same timing, different trip building** (3 vs 7): A and B share the timing rules, and B scores +0.18 more on every day. So B's lead over the deadline-order family splits roughly in half: about +0.20 from timing and about +0.18 from clustered, deadline-checked trip building.

An even earlier B (not in git) used a 2-opt that only minimised distance; it lowered the on-time rate, which is why the current 2-opt keeps a move only if the on-time count does not fall. Mention only as a design note: the lesson is that local search must optimise the real objective.

## 8. Key findings, where each policy does well or poorly, trade-offs

Key findings for the conclusion:

1. **B is the best policy** (0.9408 on time, 0.9546 delivered, 4.39 km per delivered parcel), and the best for service is also the cheapest to run: fewest km per parcel of any policy except D, which matches it.
2. **Timing and selection decide the result; routing hardly matters.** Exact routing (D) changes the on-time rate on 2 of 20 days and km per day by about 1 km. Trips use only 36% of their range, and 2-opt is already optimal on almost every trip.
3. **Distance-first beats urgency-first overall, but not on surge days.** C loses to B by 0.045 on average yet wins on B's two weakest days. A hybrid that switches to urgency-first when many parcels are close to their deadline is the most promising next step (not implemented).
4. **Remaining gap.** B reaches 0.9408 against an optimistic ceiling of about 0.9646 (97.5% of it). It leaves 36 parcels undelivered per day; about 28 of those could not have been on time under any policy.

Where each policy performs well or poorly (the brief asks for this):

- **B's weak days:** day_019 (0.8356) and day_004 (0.8886); every other day is at least 0.9171. On day_019, 105 of the then-131 undelivered parcels (measured on B before filling) arrived between 10:00 and 12:59, and 73 had windows ending in the 15:00 hour; that day has no arrivals between 09:00 and 09:59 and a large surge from 10:00. day_004 shows a smaller version of the same pattern. A plausible reading is that a late-morning surge with tight windows exceeds what 10 vehicles can serve in time; this has **not** been tested, so present it as an observation. These are exactly the days where C (urgency-first) beats B.
- **A** is above the baseline every day by at least 0.37 but has the widest spread (sd 0.056): deadline-order trips are sometimes efficient and sometimes not.
- **C** is best on surge days and worst on calm days (day_018: 0.8296 against B's 0.9554).
- **D** is never worse than B in these 20 days, but that is not guaranteed: a shorter route changes return times, and knock-on effects can go either way.
- The **baseline** is the most consistent (sd 0.016) only because it is uniformly poor.

Trade-offs:

- **Coverage vs punctuality.** The metric gives no credit for late deliveries. B delivers late parcels only when that costs no on-time delivery (filling), and 36 per day are still never delivered, because B does not send extra trips just for late parcels (that could delay later on-time trips; not tried).
- **Waiting vs responsiveness.** Waiting only happens when every parcel on the trip has at least 10 minutes of slack, so it never makes that trip's parcels late, but it does delay them and it increases the number of `dispatch` calls.
- **Thresholds vs generality.** B has two tuned parameters. The tuning/test split shows they generalise across these 20 days, but they may need re-tuning for a different town, fleet or demand pattern.
- **Exact vs heuristic.** D's exact routing is exponential in the number of stops and needs a cap; it buys almost nothing here. 2-opt is the right trade-off for this data.
- **Myopic planning.** All policies plan one vehicle's trip at a time, with no coordination across vehicles or look-ahead to future arrivals.

## 9. Recommendation and conclusion points

- **Recommended policy: B `grow_2opt_wait_fill`.** On-time rate 0.9408, best delivery rate (0.9546), lowest km per delivered parcel (4.39, tied with D), about 0.2 s of policy time per day.
- **Why not D**, although its mean is 0.0011 higher: the difference is on 2 days only, not significant, comes from knock-on timing rather than better routes, costs about 2.4× B's policy time per day (still under half a second) and needs an exponential search with a cap. If the team prefers D, the report must say all of this.
- C and A are valuable as comparisons: C shows distance-first selection matters except on surge days; A shows timing rules alone are worth a lot but not enough.
- Conclusion themes: choose parcels that are close together; never spend capacity on lost causes; never deliver early when the metric does not reward it; do not send nearly empty trips when waiting is free; let late parcels ride along only when it costs nothing; routing quality matters far less than selection and timing.

## 10. Limitations and threats to validity

- 20 days of data from one town; results may not transfer to other demand patterns or fleet sizes.
- Every policy plans one vehicle's trip at a time, with no coordination across vehicles or look-ahead to future arrivals.
- 2-opt is a local search: it stops at a route that no single reversal improves.
- B's thresholds were tuned on day_001 to day_010; the reported 20-day mean (0.9408) includes those days. The test-day mean alone is 0.9424. A, C and D reuse B's thresholds without separate tuning.
- Runtimes are from single runs on one laptop and depend on the machine; only the relative costs should be quoted.
- The upper bound in section 2 ignores fleet size and capacity, so the true ceiling is lower.
- The cause of B's weak days (section 8) is an observation, not a tested explanation.

## 11. Reproducing the results

From the project root, Python 3.9 or later, standard library only:

```sh
python3 run_experiments.py --per-day                              # all five policies, all 20 days, table + per-day
python3 run_experiments.py --policies grow_2opt_wait_fill ucs_routing
python3 tune_grow_2opt_wait_fill.py                               # Policy B threshold grid search (about 2.5 min)
```

Outputs: `results/<policy>/day_XXX/log.txt`, `metrics.json` and `timing.json`, `results/summary.csv`, `results/summary_per_day.csv`, `results/summary.json`, `results/tuning_grow_2opt_wait_fill.csv`. Runs are deterministic: repeating a command gives byte-for-byte identical logs and metrics; only the timings change. Use `--workers 1` for the timings. After the merge into four files, Policies A and B produce byte-for-byte the same logs as before.

To reproduce the design-history steps 1, 2, 4 and 6 (section 7): `git checkout 92948fd`, then `python3 run_experiments.py --policies edf_nn edf_nn_skip_overdue grow_2opt grow_2opt_wait`.

Not reproducible from the repository: the paired tests, the 0.9646 ceiling, the day_019 breakdown and D's search counts were computed with a scratch analysis script. Add it to the repository if the report uses these numbers.

## 12. Open items before submission

- `results/` is listed in `.gitignore`, but the brief requires it in the ZIP. Add it by hand, together with `run_experiments.py` and `tune_grow_2opt_wait_fill.py` (they are at the project root, outside `solution/`).
- Decide whether to add the analysis script (paired tests, ceiling, per-day tables) to the repository.
- Confirm against the syllabus which "algorithm and data structure taught in class" the report will name (section 4.6 lists the candidates).
- Remove the team-status section from the README before submission.
- Push `marcus` and merge into `main`; tell Varshni that her `grow_2opt.py` and `grow_2opt_wait.py` were merged into `grow_2opt_wait_fill.py` and her tuning script was renamed.
- Add references (candidates below).

## 13. Candidate references (verify each before citing)

- Croes, G. A. (1958). A method for solving traveling-salesman problems. *Operations Research*, 6(6), 791–812. (Origin of 2-opt.)
- Liu, C. L., & Layland, J. W. (1973). Scheduling algorithms for multiprogramming in a hard-real-time environment. *Journal of the ACM*, 20(1), 46–61. (Earliest Deadline First.)
- Rosenkrantz, D. J., Stearns, R. E., & Lewis, P. M. (1977). An analysis of several heuristics for the traveling salesman problem. *SIAM Journal on Computing*, 6(3), 563–581. (Nearest neighbor and insertion heuristics.)
- Solomon, M. M. (1987). Algorithms for the vehicle routing and scheduling problems with time window constraints. *Operations Research*, 35(2), 254–265. (Vehicle routing with time windows, insertion heuristics.)
- Dijkstra, E. W. (1959). A note on two problems in connexion with graphs. *Numerische Mathematik*, 1, 269–271. (Shortest paths; uniform-cost search.)
- The IS115 project brief and the supplied simulator.

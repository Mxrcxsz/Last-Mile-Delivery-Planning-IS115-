# IS115 Project: Last-Mile Delivery Planning

A logistics company delivers parcels from 1 hub using 10 vehicles, each with capacity 30 and a range of 320 km per trip, travelling at 60 km/h. Planning runs every 10 minutes from 08:00 to 17:30, a confirmed vehicle departs 30 minutes later, and every vehicle must be back at the hub by 18:00. This repository contains the supplied simulator and 20 days of parcel data, the dispatch policies, a performance monitor that scores each run on on-time delivery, and the commands to reproduce the results.

Team members: Marcus Yeong, [teammate name(s)]

Deadline: Friday 13 Nov 2026, 23:59 (submit one ZIP to eLearn: `solution/`, `results/`, `README.md` and the report).

## Team status and plan

> This section is for the team. Delete it, or reduce it to a short "Policies implemented" list, before submission.

### Where we are (updated 7 Nov 2026)

| Item | Status | Owner | Notes |
| --- | --- | --- | --- |
| Metric: on-time rate (`solution/performance_monitor.py`) | Done, on `main` | Marcus | Definition in "The metric" below. |
| Baseline run on day_001 to day_020 | Done | Marcus | Average on-time rate 0.2741. |
| README skeleton | Done, on `main` | Marcus | This file. |
| Policy A: `edf_nn.py` and `helpers.py` | Done, on `main` | Marcus | Average on-time rate 0.4141. |
| Merge `marcus` into `main` | Done | Marcus | Do this first so everyone builds on `helpers.py`. |
| Policy A2: `edf_nn_skip_overdue.py` | Done, on `main` | Marcus | Average on-time rate 0.5587. |
| Policy A3: `edf_nn_wait.py` | Done, on branch `marcus` | Marcus | A2 with C's timing rules. Average on-time rate 0.7591, above A2 on all 20 days. |
| `run_experiments.py` (run policies on all 20 days, print a comparison table) | Done, on branch `varshni` | Varshni | `python3 run_experiments.py --policies grow_2opt`. Also writes `results/summary.csv`. |
| Policy B: `grow_2opt.py` | Done, on branch `varshni` | Varshni | Average on-time rate 0.6117. Adds functions to the end of `helpers.py`; existing helpers unchanged. |
| Policy C: `grow_2opt_wait.py` | Done, on branch `varshni` | Varshni | Average on-time rate 0.9408. Thresholds tuned on days 1 to 10, checked on 11 to 20 with `tune_grow_2opt_wait.py`. |
| Policy C2: `grow_2opt_wait_fill.py` | Done, on branch `marcus` | Marcus | C plus overdue parcels in spare space. Same on-time rate as C on every day (0.9408); delivery rate 0.9408 → 0.9546. |
| Policy D: `ucs_routing.py` | Done, on branch `marcus` | Marcus | C with exact (UCS) routing for trips of at most 8 stops. Average on-time rate 0.9419; shorter than 2-opt on only 3% of searched trips. |
| Policy E: `least_slack.py` | Done, on branch `marcus` | Marcus | C's timing with least-slack-first selection from a min-heap. Average on-time rate 0.8961. |
| Control: `random_feasible.py` (optional) | Idea | [name] | A "does our idea beat luck" comparison. |
| Full 20-day runs for every policy, committed under `results/` | To do | Everyone | Required deliverable. |
| Report (at most 8 pages) | To do | Everyone | Split described below. |
| Final README (policy rows, results, no status section) | To do | Marcus | |

### Findings so far

These come from Marcus's runs. Regenerate all numbers with the commands in "Reproduce the results" before they go into the report.

- The baseline keeps arrival order as the route order, so its routes zigzag. On day_001 it averages 17.4 parcels per trip. Policy A averages 28.2, because nearest-neighbor ordering makes each tour shorter, so more parcels fit under the 320 km range.
- Policy A already helps a lot (on-time rate 0.2741 to 0.4141, delivery rate 0.4045 to 0.7885).
- Policy A still serves parcels that are already past their window before it serves others. Moving them to the back of the queue (the A2 prototype) lifted the on-time rate to 0.5587 and almost halved the late parcels per day.
- Policy A delivers about 14.8 parcels per day before their window opens, and the A2 prototype about 33.1. These do not count as on time, which is the reason for the waiting rule in Policy C.

### Policy plan

Each policy is a standalone file. All of them are built from three choices: timing (leave now or wait), selection (which parcels) and routing (the order of stops). Each file changes one idea from the one before it, so we can say which idea earned which gain. File names are provisional.

| Policy | Timing | Selection | Routing | Idea it adds |
| --- | --- | --- | --- | --- |
| baseline | Leave now | Arrival order | Selection order | Supplied. |
| A `edf_nn` | Leave now | Earliest window end first | Nearest-neighbor | Deadline order and a shorter tour. |
| A2 `edf_nn_skip_overdue` | Leave now | Earliest window end first, parcels that can no longer be on time go last | Nearest-neighbor | Do not spend trips on lost causes. |
| A3 `edf_nn_wait` | Wait as in C; nothing early or late | Same as A2, overdue parcels never sent; keep a parcel only if every parcel on the nearest-neighbor tour arrives inside its window | Nearest-neighbor | How much of C's gain is timing alone? |
| B `grow_2opt` | Leave now | Seed with the most urgent parcel that can still be on time, then add the feasible parcel that adds the least distance | Nearest insertion, then 2-opt on the distance table | Choose nearby parcels on purpose and improve the order. |
| C `grow_2opt_wait` | Wait if the trip is nearly empty and the most urgent parcel still has slack, or if the parcels would arrive before their window opens | Same as B | Same as B | Do not send trips too early or too empty. |
| C2 `grow_2opt_wait_fill` | Same as C | Same as C, then fill spare capacity with overdue parcels whose insertion delays no on-time parcel | Same as C, plus cheapest insertion of the overdue parcels | Deliver lost causes late when it costs nothing. |
| D `ucs_routing` | Same as C | Same as C | Exact: uniform-cost search over (location, visited stops) with a min-heap, for trips of at most 8 stops; C's 2-opt route otherwise | How much does optimal routing buy over 2-opt? |
| E `least_slack` | Same as C | Least slack first: candidates popped from a min-heap by slack, each inserted at its cheapest feasible position | Same as C | Urgency-first instead of distance-first selection. |

Design points to remember:

- There are no coordinates, only the directed distance matrix. 2-opt must compare distances and recompute the reversed segment, not test whether edges cross.
- Policies must not read `data/` and must treat `parcel` and `context` as read-only.
- UCS needs a cap on the number of distinct stops (about 8 to 10), because the number of states grows as 2^k.
- Delivery before `window_start` does not count as on time, so early deliveries are wasted.

### Open decisions

- The brief says "several" policies and gives no minimum. We are aiming for at least three. Ask the teaching team if a minimum exists.
- ~~Thresholds for the waiting rule in Policy C~~ Settled: MIN_FILL 0.75, WAIT_SLACK 10 minutes, chosen on days 1 to 10 only (tuning 0.9392, unseen days 11 to 20: 0.9424).
- Whether D is worth the time. Decide after B and C are done.

### Schedule (proposal)

| Day | Goal |
| --- | --- |
| Sat 7 to Sun 8 Nov | Merge `marcus`; A2, `run_experiments.py`; start B |
| Mon 9 Nov | Finish B and C; first full 20-day runs |
| Tue 10 Nov | Optional D and control; all results committed; start the report |
| Wed 11 Nov | Report draft done; README final |
| Thu 12 Nov | Check complexity analysis and numbers against `results/`; each of us explains the other's policies |
| Fri 13 Nov | Reproduce everything on a fresh copy, then submit before 23:59 |

### How we work in git

- One branch per person, for example `marcus`. Merge into `main` by pull request, and the other person reads it first.
- One owner per policy file. Changes to `helpers.py` or `performance_monitor.py` go through the owner, and the others are told before they are merged.
- Never change `simulator/`, `data/`, `baseline.py` or any `__init__.py`.
- Run a policy on all 20 days before merging it, and commit its `results/<policy>/` folder.
- Each policy file starts with a docstring giving its selection rule, routing rule, timing rule and worst-case time and space complexity. The report's complexity section is written from these.

### Report split (proposal)

- Problem statement and motivation, experimental results, conclusion: [name].
- Algorithmic approaches and computational complexity: [name]. Each person writes about their own policies, then we swap and read.
- Everyone: 10% of the grade comes from a final-exam question about our own work, so every member must be able to explain every policy.

## Requirements

Python 3.9 or later, standard library only. There is no installation step. Run every command from the project root (the folder containing this file).

Tested with Python 3.13.7 and Python 3.9.6 on macOS. The commands in section "Reproduce the results" gave identical results on both for the baseline.

## Folder structure

```text
.
├── README.md                     This file
├── IS115_Project_Brief.pdf       Project brief
├── .gitignore                    Files excluded from git
├── run_experiments.py            Runs policies on many days, scores them and prints a comparison table
├── tune_grow_2opt_wait.py        Grid search for Policy C's two thresholds (tuning vs test days)
├── simulator/                    Supplied and unchanged: simulation framework
│   ├── __init__.py               Package marker
│   ├── __main__.py               Entry point for python3 -m simulator
│   ├── simulator.py              Runs events, validates routes, writes the log
│   ├── loaders.py                Reads and validates the input files
│   └── models.py                 Event, parcel, config and context structures
├── data/                         Supplied and unchanged: input data
│   ├── config.json               Number of vehicles, capacity and range
│   ├── dist.csv                  Directed distances between locations
│   └── demand/                   day_001.csv to day_020.csv, one day's parcels each
├── solution/                     Team code
│   ├── __init__.py               Package marker
│   ├── performance_monitor.py    Reads a log and a day's CSV, writes metrics.json
│   └── policies/                 Dispatch policies
│       ├── __init__.py           Package marker
│       ├── baseline.py           Supplied and unchanged: greedy first-fit in arrival order
│       ├── helpers.py            Shared helpers
│       ├── edf_nn.py             Policy A: earliest deadline first, nearest-neighbor
│       ├── edf_nn_skip_overdue.py Policy A2: as A, overdue parcels last
│       ├── edf_nn_wait.py        Policy A3: A2 with Policy C's timing rules
│       ├── grow_2opt.py          Policy B: urgent seed, cheapest insertion, 2-opt
│       ├── grow_2opt_wait.py     Policy C: Policy B with no early deliveries and no nearly empty trips
│       ├── grow_2opt_wait_fill.py Policy C2: Policy C plus overdue parcels in spare space
│       ├── ucs_routing.py        Policy D: Policy C with exact uniform-cost-search routing
│       ├── least_slack.py        Policy E: least slack first from a min-heap, with C's timing
│       └── ...                   Planned policies, see "Policy plan"
└── results/                      Generated by the commands below
    └── <policy>/day_XXX/         log.txt and metrics.json for one policy and day
```

## How it works

1. In each planning round, the simulator calls `dispatch(parcel, context)` once per free vehicle, starting with the vehicle idle longest.
2. The policy returns an ordered list of parcel IDs for that vehicle's trip, or `[]` to leave it idle until the next round.
3. The simulator validates the route against capacity, range and the 18:00 return cutoff, then simulates the trip.
4. Every event is written to `log.txt` in the output folder, one JSON record per line.
5. `solution/performance_monitor.py` reads the log and the day's CSV and writes `metrics.json` beside the log.

## The metric

```text
on_time_rate = parcels delivered inside [window_start, window_end] / ALL parcels that arrived that day
```

Both window boundaries count as on time. A delivery before `window_start` is early and does not count. Undelivered parcels stay in the denominator, so a policy that delivers nothing scores 0. The denominator is every row of the day's CSV; all of those parcels arrive by 17:30.

`metrics.json` contains these keys:

- `on_time_rate`: as defined above, rounded to 4 decimal places.
- `parcels_total`: parcels in the day's CSV.
- `parcels_delivered`: delivery events in the log.
- `parcels_on_time`: delivered inside the window.
- `parcels_late`: delivered after `window_end`.
- `parcels_early`: delivered before `window_start`.
- `delivery_rate`: `parcels_delivered / parcels_total`, rounded to 4 decimal places.
- `km_per_delivered_parcel`: total km of all trips (HUB to stops to HUB, rebuilt from delivery order) divided by `parcels_delivered`, rounded to 3 decimal places.
- `trips`: trips that left the hub (each trip delivers at least one parcel).
- `total_km`: km driven over all trips, rebuilt as above, rounded to 3 decimal places.
- `km_per_trip`: `total_km / trips`, rounded to 3 decimal places.
- `parcels_per_trip`: `parcels_delivered / trips`, rounded to 3 decimal places.
- `capacity_utilisation`: total size of delivered parcels / (`trips` × vehicle capacity), rounded to 4 decimal places. 1.0 means every trip left full.
- `range_utilisation`: `total_km` / (`trips` × vehicle range), rounded to 4 decimal places. 1.0 means every trip used its full 320 km.

## The policies

| File | Selection rule | Routing rule | Timing rule | Worst-case time per `dispatch` call |
| --- | --- | --- | --- | --- |
| `solution/policies/baseline.py` | Try every waiting parcel in arrival order (parcel ID breaks ties). Skip a parcel that breaks capacity, range or the return cutoff, and keep trying later ones. Delivery windows are ignored. | Visit stops in selection order. | No waiting: leave whenever at least one parcel fits. | O(n log n), for n arrived parcels |
| `solution/policies/grow_2opt.py` (Policy B) | Only parcels that can still be on time (direct drive reaches them by window end). Seed with the most urgent, then repeatedly add the parcel whose cheapest insertion adds the least distance (ties: earliest window end). An insertion must keep capacity, range and cutoff, arrive by the new parcel's window end, and push no on-time parcel past its window end. Early arrival allowed. | Insertion order, then 2-opt over distinct stops on the directed table; a move is kept only if strictly shorter and the on-time count does not fall. | No waiting. | O(N + n log n + k(Lk + n) + P s²(s + k)), for N arrived, n candidate parcels, L locations, k parcels and s stops in the trip, P 2-opt passes |
| `solution/policies/grow_2opt_wait.py` (Policy C) | As B, but a parcel is added only if it arrives inside its window (never early); the seed must also be reachable inside its window. | As B. | Return `[]` if no parcel can be reached inside its window yet, or if the load is below 75% of capacity and every parcel can wait 10 more minutes. | As B, plus O(k) for the waiting test |
| `solution/policies/grow_2opt_wait_fill.py` (Policy C2) | Policy C's trip, then repeatedly add the overdue parcel (one that can only be late) whose cheapest insertion adds the fewest km, as long as capacity, range and the cutoff hold and no on-time parcel on the trip is pushed past its window end. Parcels that can still be on time but are not on C's trip are never added. | C's order, with each overdue parcel at its cheapest allowed position. | As C: overdue parcels never cause a departure or a wait. | As C, plus O(m log m + k(L′s + s + k)) for m overdue parcels at L′ locations |
| `solution/policies/ucs_routing.py` (Policy D) | As C. | Parcels grouped into one stop per location, each with an arrival interval [latest window start, earliest window end]. For at most 8 stops, uniform-cost search over (location, visited set), cost = km = minutes, expanding cheapest first from a min-heap; a move is allowed only if it arrives inside the stop's interval; C's 2-opt route is the upper bound for pruning. The first complete tour popped is the shortest feasible one; used only if strictly shorter than C's. | As C. | As C, plus O(s! s log(s! s)) for s ≤ 8 stops (a constant under the cap) |
| `solution/policies/least_slack.py` (Policy E) | Candidates as C. Slack = window end − (departure + direct drive). Seed: least-slack parcel reachable inside its window. Other candidates go into a min-heap by (slack, window end, parcel ID); each popped parcel is inserted at its cheapest feasible position (inside its window, no on-time parcel pushed late, capacity, range and cutoff), or skipped. | Insertion order, then C's 2-opt. | As C. | O(N + n log n + n(s + k) + P s²(s + k)) |
| `solution/policies/edf_nn.py` (Policy A) | Try waiting parcels by earliest `delivery_window_end` (parcel ID breaks ties). Skip a parcel that breaks capacity, and keep a parcel only if the nearest-neighbor tour that includes it meets the range and return cutoff. Parcels already past their window are still tried first. | Nearest neighbor from the hub. | No waiting: leave whenever at least one parcel fits. | O(n log n + n k²), for n waiting parcels and k parcels in the trip |
| `solution/policies/edf_nn_skip_overdue.py` (Policy A2) | Same as Policy A, except for the order parcels are tried in. A parcel is overdue if departure time + distance from the hub to its location > `delivery_window_end`. Parcels that can still be on time are tried first by earliest `delivery_window_end` (parcel ID breaks ties), then overdue parcels in the same order. | Nearest neighbor from the hub. | No waiting: leave whenever at least one parcel fits. | O(n log n + n k²), for n waiting parcels and k parcels in the trip |
| `solution/policies/edf_nn_wait.py` (Policy A3) | Only parcels that can still be on time, by earliest `delivery_window_end` (parcel ID breaks ties). Keep a parcel only if capacity allows and the nearest-neighbor tour that includes it meets range and the cutoff and delivers every parcel on it inside its window (none early, none late). | Nearest neighbor from the hub. | As C: return `[]` if nothing fits, or if the trip is nearly empty and every parcel can wait one more round. | O(N + n log n + n k²) |

The docstring of each policy file states its rules and complexity. The routing rule, timing rule and complexity of `baseline.py` are read from its code.

Add a row here for each new policy.

Recommended policy: [name]

## Reproduce the results

### a. Baseline, one day

Run the simulation:

```sh
python3 -m simulator --policy solution.policies.baseline \
    --data data --day day_001 \
    --output results/baseline/day_001
```

The last two lines printed are `Delivered: 349` and `Event log: results/baseline/day_001/log.txt`.

Run the performance monitor on that log:

```sh
python3 -m solution.performance_monitor \
    --data data --day day_001 \
    --log results/baseline/day_001/log.txt
```

This prints `Metrics report: results/baseline/day_001/metrics.json`. That file contains `"on_time_rate": 0.2666`.

### b. One non-baseline policy (Policy A)

This needs the `marcus` branch, or `main` after it is merged.

```sh
python3 -m simulator --policy solution.policies.edf_nn \
    --data data --day day_001 \
    --output results/edf_nn/day_001

python3 -m solution.performance_monitor \
    --data data --day day_001 \
    --log results/edf_nn/day_001/log.txt
```

The metrics are written to `results/edf_nn/day_001/metrics.json`.

### c. All policies on all 20 days

The quickest way, on any operating system, is the experiment runner. It does exactly what the two commands above do for every policy and day (same `log.txt` and `metrics.json`), runs days in parallel, then prints the comparison table and writes `results/summary.csv` and `results/summary_per_day.csv`:

```sh
python3 run_experiments.py                                   # every policy in solution/policies/, all 20 days
python3 run_experiments.py --policies grow_2opt grow_2opt_wait
python3 run_experiments.py --policies grow_2opt --days 1-5   # day_001 to day_005
python3 run_experiments.py --summary-only --per-day          # only re-print the table from existing results
```

To reproduce Policy C's threshold choice (writes `results/tuning_grow_2opt_wait.csv`, does not touch `results/<policy>/`):

```sh
python3 tune_grow_2opt_wait.py
```

Equivalently, this loop needs bash or zsh (macOS or Linux). It runs the simulator and the performance monitor for each policy and day:

```sh
for policy in baseline edf_nn edf_nn_skip_overdue grow_2opt grow_2opt_wait grow_2opt_wait_fill ucs_routing least_slack edf_nn_wait; do
  for day in $(seq -f "day_%03g" 1 20); do
    python3 -m simulator --policy "solution.policies.$policy" \
        --data data --day "$day" \
        --output "results/$policy/$day"
    python3 -m solution.performance_monitor \
        --data data --day "$day" \
        --log "results/$policy/$day/log.txt"
  done
done
```

To include another policy, add its module name after `edf_nn_wait` in the first line.

For each policy and day it prints 8 lines: parcels, vehicles, capacity, range, scheduled events, delivered, the log path and the metrics path. It writes the two files listed in part d, overwriting any earlier run in the same folder.

To compute the averages in section "Results summary" (run this after the loop):

```sh
python3 - <<'EOF'
import json
from pathlib import Path
from statistics import mean

keys = ("on_time_rate", "delivery_rate", "km_per_delivered_parcel")
for folder in sorted(p for p in Path("results").iterdir() if p.is_dir()):
    days = [json.loads(p.read_text()) for p in sorted(folder.glob("day_*/metrics.json"))]
    print(folder.name, len(days), *(f"{mean(d[k] for d in days):.4f}" for k in keys))
EOF
```

It prints one line per policy: the policy name, the number of days, then the three averages in table order.

### d. Where outputs appear

- `results/<policy>/day_XXX/log.txt`: event log, written by the simulator.
- `results/<policy>/day_XXX/metrics.json`: metrics, written by the performance monitor.

## Results summary

Unweighted mean of the daily `metrics.json` values over day_001 to day_020:

| Policy | Average on_time_rate | Average delivery_rate | Average km_per_delivered_parcel |
| --- | --- | --- | --- |
| baseline | 0.2741 | 0.4045 | 16.3299 |
| edf_nn (A) | 0.4141 | 0.7885 | 7.751 |
| edf_nn_skip_overdue (A2) | 0.5587 | 0.7835 | 7.731 |
| edf_nn_wait (A3) | 0.7591 | 0.7591 | 6.493 |
| grow_2opt (B) | 0.6117 | 0.8653 | 5.757 |
| grow_2opt_wait (C) | 0.9408 | 0.9408 | 4.431 |
| grow_2opt_wait_fill (C2) | 0.9408 | 0.9546 | 4.393 |
| ucs_routing (D) | 0.9419 | 0.9419 | 4.425 |
| least_slack (E) | 0.8961 | 0.8961 | 5.682 |

All four rows were regenerated with `python3 run_experiments.py --policies baseline edf_nn grow_2opt grow_2opt_wait` on 9 Nov (the baseline and edf_nn rows match Marcus's runs exactly). Regenerate it with the commands in part c and replace it with the exact output. The A2 row comes from Marcus's 20-day run on 10 Nov, the A3, C2, D and E rows from his runs on 11 Nov.

[Add a row for each policy added to `solution/policies/`.]

The full run in part c took about 10 to 20 seconds for the baseline on the machine used for testing.

## Notes

Do not modify `simulator/`, `data/`, `solution/policies/baseline.py`, `solution/__init__.py` or `solution/policies/__init__.py`.

Runs are repeatable. Nothing uses randomness, so there is no seed. Ties are broken as follows:

- Events: by time, then event type priority, then parcel or vehicle ID.
- Vehicles in a planning round: longest idle first, then vehicle ID.
- Baseline parcel order: arrival time, then parcel ID.
- `edf_nn`, `edf_nn_skip_overdue` and `edf_nn_wait`: window end, then parcel ID.
- `grow_2opt`, `grow_2opt_wait`, `grow_2opt_wait_fill` and `ucs_routing`: least added distance, then window end, then parcel ID.
- `ucs_routing` search: equal-cost states are popped in the order they were pushed (a counter breaks heap ties).
- `least_slack`: slack, then window end, then parcel ID; insertion position: least added distance, then earliest position.

Known limitations:

- The performance monitor does not check that a log is complete. Use only logs from simulator runs that finished without an error.
- The performance monitor does not check that `--day` matches the log. Pass the same day used for the simulation.
- The commands were tested only on macOS. The loop in part c uses `seq` and bash or zsh syntax, so it will not run in Windows Command Prompt or PowerShell.
- The simulator models a fixed speed of 60 km/h and zero service time at stops, as specified in the brief.
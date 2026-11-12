# IS115 Project: Last-Mile Delivery Planning

A logistics company delivers parcels from 1 hub using 10 vehicles, each with capacity 30 and a range of 320 km per trip, travelling at 60 km/h. Planning runs every 10 minutes from 08:00 to 17:30, a confirmed vehicle departs 30 minutes later, and every vehicle must be back at the hub by 18:00. This repository contains the supplied simulator and 20 days of parcel data, the dispatch policies, a performance monitor that scores each run on on-time delivery, and the commands to reproduce the results.

Team members: Marcus Yeong, [teammate name(s)]

Deadline: Friday 13 Nov 2026, 23:59 (submit one ZIP to eLearn: `solution/`, `results/`, `README.md`, `run_experiments.py`, `tune_grow_2opt_wait_fill.py` and the report).

## Team status and plan

> This section is for the team. Delete it, or reduce it to a short "Policies implemented" list, before submission.

### Where we are (updated 12 Nov 2026)

| Item | Status | Owner | Notes |
| --- | --- | --- | --- |
| Metric: on-time rate (`solution/performance_monitor.py`) | Done | Marcus | Definition in "The metric" below, plus fleet-usage metrics. |
| `run_experiments.py` and `tune_grow_2opt_wait_fill.py` | Done | Varshni | Run every policy on 20 days; tune Policy B's thresholds. |
| Policy A: `edf_nn_wait.py` | Done | Marcus | Average on-time rate 0.7591. |
| Policy B: `grow_2opt_wait_fill.py` | Done | Varshni, Marcus | Average on-time rate 0.9408, delivery rate 0.9546. Merges the earlier B, C and C2. |
| Policy C: `least_slack.py` | Done | Marcus | Average on-time rate 0.8956. |
| Policy D: `ucs_routing.py` | Done | Marcus | Average on-time rate 0.9419 (not significantly above B). |
| Full 20-day runs for every policy under `results/` | Done | Marcus | `results/` is git-ignored: add it to the ZIP by hand. |
| Report (at most 8 pages) | In progress | Everyone | Source material: `report_findings.md`. |
| Final README (no status section) | To do | Marcus | |

Earlier policies (Policy A without waiting, A with overdue parcels last, Policy B without waiting or filling, and B without filling) were merged into the four policies above on 12 Nov. They are in git history at commit `92948fd` and summarised in `report_findings.md`.

### Policy plan

All policies are built from four choices: timing (leave now or wait), selection (which parcels), routing (the order of stops) and filling (whether late parcels ride along). Policies B, C and D share timing and filling and differ in one choice each, so each comparison isolates one idea.

| Policy | Timing | Selection | Routing | Filling | What the comparison shows |
| --- | --- | --- | --- | --- | --- |
| baseline | Leave now | Arrival order | Selection order | None | Supplied reference. |
| A `edf_nn_wait` | Wait if nothing fits or the trip is nearly empty | Earliest window end first, only parcels that arrive inside their window | Nearest neighbor | None | Deadline order with timing rules. |
| B `grow_2opt_wait_fill` | As A | Seed with the most urgent parcel, then add the parcel that adds the least distance, never early or late | Cheapest insertion, then 2-opt | Overdue parcels where they delay no one | Recommended policy. |
| C `least_slack` | As B | Least slack first, popped from a min-heap | As B | As B | Urgency-first vs B's distance-first selection. |
| D `ucs_routing` | As B | As B | Exact uniform-cost search for at most 8 stops, otherwise as B | As B | Optimal routing vs B's 2-opt. |

Design points to remember:

- There are no coordinates, only the directed distance matrix. 2-opt must compare distances and recompute the reversed segment, not test whether edges cross.
- Policies must not read `data/` and must treat `parcel` and `context` as read-only.
- Exact routing needs a cap on the number of distinct stops (8), because the number of stop orders grows as s!.
- Delivery before `window_start` does not count as on time, so early deliveries are wasted.

### Open decisions

- ~~Thresholds for the waiting rule~~ Settled: MIN_FILL 0.75, WAIT_SLACK 10 minutes, chosen on days 1 to 10 only (tuning 0.9392, unseen days 11 to 20: 0.9424).
- Recommended policy: B, unless the team prefers D (see `report_findings.md`).

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
- A policy file never imports another policy file. Code that two or more policies use lives in `helpers.py`; each policy keeps its own thresholds as module constants and passes them to the helpers (for example `should_wait(..., min_fill=MIN_FILL, wait_slack=WAIT_SLACK)`).
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
├── tune_grow_2opt_wait_fill.py   Grid search for Policy B's two thresholds (tuning vs test days)
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
│       ├── helpers.py            Shared helpers (trip building, timing, waiting, filling)
│       ├── edf_nn_wait.py        Policy A: earliest deadline first, nearest neighbor, on-time-only trips
│       ├── grow_2opt_wait_fill.py Policy B: cheapest insertion, 2-opt, waiting, overdue filling
│       ├── least_slack.py        Policy C: least slack first from a min-heap, B's timing and filling
│       └── ucs_routing.py        Policy D: Policy B with exact uniform-cost-search routing
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
| `solution/policies/edf_nn_wait.py` (Policy A) | Only parcels that can still be on time, by earliest `delivery_window_end` (parcel ID breaks ties). Keep a parcel only if capacity allows and the nearest-neighbor tour that includes it meets range and the cutoff and delivers every parcel on it inside its window (none early, none late). | Nearest neighbor from the hub. | Return `[]` if nothing fits, or if the load is below 75% of capacity and every parcel can wait 10 more minutes. | O(N + n log n + n k²) |
| `solution/policies/grow_2opt_wait_fill.py` (Policy B) | Only parcels that can still be on time and fit alone. Seed: the most urgent one a direct drive reaches inside its window. Then repeatedly add the parcel whose cheapest insertion adds the least distance (ties: earliest window end, parcel ID), if it arrives inside its window, keeps capacity, range and cutoff, and pushes no on-time parcel past its window end. When the trip leaves, overdue parcels fill spare capacity where they delay no on-time parcel. | Insertion order, then 2-opt over distinct stops on the directed table; a move is kept only if strictly shorter and the on-time count does not fall. | Return `[]` if no parcel can be reached inside its window yet, or if the load is below 75% of capacity and every parcel can wait 10 more minutes. | O(N + n log n + k(Lk + n) + P s²(s + k) + m log m + k(L′s + s + k)) |
| `solution/policies/least_slack.py` (Policy C) | Candidates as B. Slack = window end − (departure + direct drive). Seed: least-slack parcel reachable inside its window. Other candidates go into a min-heap by (slack, window end, parcel ID); each popped parcel is inserted at its cheapest feasible position (inside its window, no on-time parcel pushed late, capacity, range and cutoff), or skipped. Filling as B. | Insertion order, then B's 2-opt. | As B. | O(N + n log n + n(s + k) + P s²(s + k)) plus filling as B |
| `solution/policies/ucs_routing.py` (Policy D) | As B. | B's 2-opt route, then, for at most 8 stops, uniform-cost search over (location, visited set) with cost = km = minutes, expanding cheapest first from a min-heap; a move is allowed only if it arrives inside the stop's interval [latest window start, earliest window end]; the 2-opt route is the upper bound for pruning. Used only if strictly shorter. | As B. | As B, plus O(s! s log(s! s)) for s ≤ 8 stops (a constant under the cap) |

Notation: N arrived parcels, n candidates, L locations among them, k parcels and s distinct stops in the trip, P 2-opt passes, m overdue parcels at L′ locations.

The docstring of each policy file states its rules and complexity. The routing rule, timing rule and complexity of `baseline.py` are read from its code.

Recommended policy: B (`grow_2opt_wait_fill`).

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

### b. One non-baseline policy (Policy B)

```sh
python3 -m simulator --policy solution.policies.grow_2opt_wait_fill \
    --data data --day day_001 \
    --output results/grow_2opt_wait_fill/day_001

python3 -m solution.performance_monitor \
    --data data --day day_001 \
    --log results/grow_2opt_wait_fill/day_001/log.txt
```

The metrics are written to `results/grow_2opt_wait_fill/day_001/metrics.json`. That file contains `"on_time_rate": 0.9186`.

### c. All policies on all 20 days

The quickest way, on any operating system, is the experiment runner. It does exactly what the two commands above do for every policy and day (same `log.txt` and `metrics.json`), runs days in parallel, then prints the comparison table and writes `results/summary.csv` and `results/summary_per_day.csv`:

```sh
python3 run_experiments.py                                   # every policy in solution/policies/, all 20 days
python3 run_experiments.py --policies grow_2opt_wait_fill ucs_routing
python3 run_experiments.py --policies edf_nn_wait --days 1-5 # day_001 to day_005
python3 run_experiments.py --summary-only --per-day          # only re-print the table from existing results
```

To reproduce Policy B's threshold choice (writes `results/tuning_grow_2opt_wait_fill.csv`, does not touch `results/<policy>/`; about 2.5 minutes):

```sh
python3 tune_grow_2opt_wait_fill.py
```

Equivalently, this loop needs bash or zsh (macOS or Linux). It runs the simulator and the performance monitor for each policy and day:

```sh
for policy in baseline edf_nn_wait grow_2opt_wait_fill least_slack ucs_routing; do
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

To include another policy, add its module name after `ucs_routing` in the first line.

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
| baseline | 0.2741 | 0.4045 | 16.330 |
| edf_nn_wait (A) | 0.7591 | 0.7591 | 6.493 |
| grow_2opt_wait_fill (B) | 0.9408 | 0.9546 | 4.393 |
| least_slack (C) | 0.8956 | 0.9384 | 5.440 |
| ucs_routing (D) | 0.9419 | 0.9546 | 4.392 |

Regenerated on 12 Nov with `python3 run_experiments.py`. Policies A and B produce byte-for-byte the same logs as before they were merged into single files.

## Notes

Do not modify `simulator/`, `data/`, `solution/policies/baseline.py`, `solution/__init__.py` or `solution/policies/__init__.py`.

Runs are repeatable. Nothing uses randomness, so there is no seed. Ties are broken as follows:

- Events: by time, then event type priority, then parcel or vehicle ID.
- Vehicles in a planning round: longest idle first, then vehicle ID.
- Baseline parcel order: arrival time, then parcel ID.
- `edf_nn_wait`: window end, then parcel ID.
- `grow_2opt_wait_fill` and `ucs_routing`: least added distance, then window end, then parcel ID; overdue filling: least added distance, window end, parcel ID, earliest position.
- `ucs_routing` search: equal-cost states are popped in the order they were pushed (a counter breaks heap ties).
- `least_slack`: slack, then window end, then parcel ID; insertion position: least added distance, then earliest position.

Known limitations:

- The performance monitor does not check that a log is complete. Use only logs from simulator runs that finished without an error.
- The performance monitor does not check that `--day` matches the log. Pass the same day used for the simulation.
- The commands were tested only on macOS. The loop in part c uses `seq` and bash or zsh syntax, so it will not run in Windows Command Prompt or PowerShell.
- The simulator models a fixed speed of 60 km/h and zero service time at stops, as specified in the brief.
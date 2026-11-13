"""Compute the report's supporting analyses from the data and the results of run_experiments.py.

Run from the project root after `python3 run_experiments.py` (all policies, all 20 days):

    python3 analyse_results.py

It prints each analysis and writes results/analysis.json. Standard library only. Nothing here
is timed or random, so the same results always give the same file.

Analyses:
    dataset            parcels per day, locations, distances, sizes, windows, matrix symmetry
    ceiling            parcels that no policy could deliver on time, and the resulting upper
                       bound on on_time_rate (optimistic: ignores fleet size and capacity)
    paired_tests       daily on_time_rate differences between policies: mean, range, days
                       better / equal / worse, exact two-sided sign test, paired t (df = n - 1)
    sensitivity        mean on_time_rate and delivered_by_deadline_rate (early counted as a
                       success) per policy, and the ranking under each
    weak_days          undelivered parcels on chosen days, by arrival hour and window-end hour
    stops_per_trip     distinct stops per trip, from the logs
    exact_search       how often Policy D's uniform-cost search finds a shorter order than 2-opt
                       (re-simulates D on every day; about 40 seconds)
"""

import argparse
import csv
import json
import math
import sys
import tempfile
from collections import Counter
from pathlib import Path
from statistics import mean, median, stdev
from typing import Dict, List

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from simulator.loaders import day_input_paths, parse_time  # noqa: E402
from simulator.simulator import (  # noqa: E402
    DAY_START, DEPARTURE_DELAY, HUB, PLANNING_INTERVAL, RETURN_CUTOFF, Simulator,
)

DAYS = [f"day_{d:03d}" for d in range(1, 21)]
# Last planning round, as the simulator schedules them: 17:30.
LAST_ROUND = DAY_START + PLANNING_INTERVAL * int(
    (RETURN_CUTOFF - DEPARTURE_DELAY - DAY_START) / PLANNING_INTERVAL)

# Comparisons reported in the report: (later policy, earlier policy, label).
PAIRS = [
    ("edf_nn_wait", "baseline", "A vs baseline"),
    ("grow_2opt_wait_fill", "edf_nn_wait", "B vs A"),
    ("least_slack", "edf_nn_wait", "C vs A"),
    ("least_slack", "grow_2opt_wait_fill", "C vs B"),
    ("ucs_routing", "grow_2opt_wait_fill", "D vs B"),
    ("edf_nn", "baseline", "design step 1 vs 0"),
    ("edf_nn_skip_overdue", "edf_nn", "design step 2 vs 1"),
    ("edf_nn_wait", "edf_nn_skip_overdue", "design step 3 vs 2"),
    ("grow_2opt", "edf_nn_skip_overdue", "design step 4 vs 2"),
    ("grow_2opt_wait", "grow_2opt", "design step 6 vs 4"),
    ("grow_2opt_wait_fill", "grow_2opt_wait", "design step 7 vs 6"),
]


def load_rows(path: Path) -> List[Dict[str, str]]:
    """Read a CSV file into a list of row dictionaries."""

    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def load_metrics(results: Path, policy: str) -> Dict[str, dict]:
    """Return metrics.json by day for one policy (days without results are left out)."""

    found = {}
    for day in DAYS:
        path = results / policy / day / "metrics.json"
        if path.exists():
            found[day] = json.loads(path.read_text(encoding="utf-8"))
    return found


def distances_table(data: Path) -> Dict[str, Dict[str, float]]:
    """Return the directed distance lookup as distances[origin][destination]."""

    table: Dict[str, Dict[str, float]] = {}
    for row in load_rows(data / "dist.csv"):
        table.setdefault(row["location_1"], {})[row["location_2"]] = float(row["dist"])
    return table


def dataset_facts(data: Path) -> dict:
    """Describe the 20 days of demand and the distance matrix."""

    distances = distances_table(data)
    per_day, sizes, widths, leads, early_arrivals, locations = [], [], [], [], 0, set()
    for day in DAYS:
        rows = load_rows(day_input_paths(data, day)[0])
        per_day.append(len(rows))
        for row in rows:
            arrival = parse_time(row["arrival_time"])
            start = parse_time(row["delivery_window_start"])
            end = parse_time(row["delivery_window_end"])
            sizes.append(float(row["size"]))
            widths.append(end - start)
            leads.append(end - arrival)
            early_arrivals += arrival < 12 * 60
            locations.add(row["delivery_location_id"])
    hub = [d for loc, d in distances[HUB].items() if loc != HUB]
    pairs = [(a, b) for a in distances for b in distances[a] if a != b]
    asymmetric = sum(abs(distances[a][b] - distances[b][a]) > 1e-9 for a, b in pairs)
    return {
        "parcels_per_day": {"min": min(per_day), "mean": round(mean(per_day), 2), "max": max(per_day)},
        "locations": len(locations),
        "hub_distance_km": {"min": min(hub), "median": round(median(hub), 3), "max": max(hub)},
        "parcel_size": {"min": min(sizes), "mean": round(mean(sizes), 2), "max": max(sizes)},
        "window_width_min": {"min": min(widths), "median": median(widths), "max": max(widths)},
        "window_end_minus_arrival_min": {"min": min(leads), "median": median(leads), "max": max(leads)},
        "share_arriving_before_noon": round(early_arrivals / sum(per_day), 3),
        "distance_pairs": len(pairs),
        "asymmetric_distance_pairs": asymmetric,
    }


def first_round(arrival: float) -> float:
    """Return the first planning round at or after a parcel's arrival."""

    rounds = math.ceil(max(0.0, arrival - DAY_START) / PLANNING_INTERVAL)
    return DAY_START + rounds * PLANNING_INTERVAL


def impossible(row: Dict[str, str], distances: Dict[str, Dict[str, float]]) -> bool:
    """Return True if even a dedicated vehicle on the first possible round would be late.

    Also counts parcels that arrive after the last round, or whose round trip cannot return
    by the cutoff. At 60 km/h km equals minutes.
    """

    plan = first_round(parse_time(row["arrival_time"]))
    out = distances[HUB][row["delivery_location_id"]]
    back = distances[row["delivery_location_id"]][HUB]
    if plan > LAST_ROUND:
        return True
    departure = plan + DEPARTURE_DELAY
    return (departure + out > parse_time(row["delivery_window_end"])
            or departure + out + back > RETURN_CUTOFF)


def ceiling(data: Path) -> dict:
    """Count impossible parcels per day and the upper bound on on_time_rate they imply."""

    distances = distances_table(data)
    per_day = {}
    for day in DAYS:
        rows = load_rows(day_input_paths(data, day)[0])
        lost = sum(impossible(row, distances) for row in rows)
        per_day[day] = {"parcels": len(rows), "impossible": lost,
                        "upper_bound": round(1 - lost / len(rows), 4)}
    lost = [v["impossible"] for v in per_day.values()]
    bounds = [v["upper_bound"] for v in per_day.values()]
    return {
        "impossible_per_day": {"min": min(lost), "mean": round(mean(lost), 2), "max": max(lost)},
        "upper_bound": {"min": min(bounds), "mean": round(mean(bounds), 4), "max": max(bounds)},
        "per_day": per_day,
    }


def paired(later: Dict[str, dict], earlier: Dict[str, dict]) -> dict:
    """Compare daily on_time_rate of two policies on their shared days."""

    days = [d for d in DAYS if d in later and d in earlier]
    diffs = [later[d]["on_time_rate"] - earlier[d]["on_time_rate"] for d in days]
    better = sum(x > 0 for x in diffs)
    worse = sum(x < 0 for x in diffs)
    decided = better + worse
    tail = min(better, worse)
    sign_p = (min(1.0, 2 * sum(math.comb(decided, i) for i in range(tail + 1)) / 2 ** decided)
              if decided else 1.0)
    sd = stdev(diffs) if len(diffs) > 1 else 0.0
    return {
        "days": len(diffs),
        "mean_difference": round(mean(diffs), 4),
        "min_difference": round(min(diffs), 4),
        "max_difference": round(max(diffs), 4),
        "days_better": better,
        "days_equal": len(diffs) - decided,
        "days_worse": worse,
        "sign_test_p": round(sign_p, 4),
        "paired_t": round(mean(diffs) / (sd / math.sqrt(len(diffs))), 2) if sd else None,
    }


def sensitivity(metrics: Dict[str, Dict[str, dict]]) -> dict:
    """Rank policies by on_time_rate and by delivered_by_deadline_rate (early counts)."""

    table = {}
    for policy, days in metrics.items():
        values = list(days.values())
        if "delivered_by_deadline_rate" not in values[0]:
            continue
        table[policy] = {
            "on_time_rate": round(mean(v["on_time_rate"] for v in values), 4),
            "delivered_by_deadline_rate": round(mean(v["delivered_by_deadline_rate"] for v in values), 4),
        }
    return {
        "means": table,
        "rank_by_on_time_rate": sorted(table, key=lambda p: -table[p]["on_time_rate"]),
        "rank_by_delivered_by_deadline_rate":
            sorted(table, key=lambda p: -table[p]["delivered_by_deadline_rate"]),
    }


def delivered_ids(log: Path) -> set:
    """Return the IDs of parcels delivered in a simulator log."""

    found = set()
    with log.open(encoding="utf-8") as stream:
        for line in stream:
            event = json.loads(line)
            if event["event_type"] == "delivery":
                found.add(event["parcel_id"])
    return found


def weak_days(data: Path, results: Path, policy: str, days: List[str]) -> dict:
    """Break down a policy's undelivered parcels on the given days by hour."""

    distances = distances_table(data)
    out = {}
    for day in days:
        log = results / policy / day / "log.txt"
        if not log.exists():
            continue
        rows = load_rows(day_input_paths(data, day)[0])
        done = delivered_ids(log)
        missed = [r for r in rows if r["parcel_id"] not in done]
        hour = lambda value: f"{int(parse_time(value) // 60):02d}:00"  # noqa: E731
        out[day] = {
            "parcels": len(rows),
            "undelivered": len(missed),
            "undelivered_impossible": sum(impossible(r, distances) for r in missed),
            "undelivered_by_arrival_hour": dict(sorted(Counter(hour(r["arrival_time"]) for r in missed).items())),
            "undelivered_by_window_end_hour": dict(sorted(Counter(hour(r["delivery_window_end"]) for r in missed).items())),
            "all_parcels_by_arrival_hour": dict(sorted(Counter(hour(r["arrival_time"]) for r in rows).items())),
        }
    return out


def stops_per_trip(data: Path, results: Path, policy: str, cap: int) -> dict:
    """Count distinct stops per trip in a policy's logs, and the share with at most cap."""

    counts: Counter = Counter()
    for day in DAYS:
        log = results / policy / day / "log.txt"
        if not log.exists():
            continue
        location = {r["parcel_id"]: r["delivery_location_id"]
                    for r in load_rows(day_input_paths(data, day)[0])}
        trips: Dict[tuple, list] = {}
        with log.open(encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                if event["event_type"] == "delivery":
                    trips.setdefault((event["vehicle_id"], event["trip_id"]), []).append(
                        (event["time"], location[event["parcel_id"]]))
        for stops in trips.values():
            stops.sort()
            sequence = [loc for _, loc in stops]
            counts[sum(i == 0 or sequence[i] != sequence[i - 1] for i in range(len(sequence)))] += 1
    total = sum(counts.values())
    return {
        "trips": total,
        "distribution": {str(k): counts[k] for k in sorted(counts)},
        f"share_with_at_most_{cap}_stops": round(sum(v for k, v in counts.items() if k <= cap) / total, 3)
        if total else None,
    }


def exact_search(data: Path) -> dict:
    """Re-simulate Policy D and count how often exact search beats the 2-opt order."""

    from solution.policies import ucs_routing
    from solution.policies.helpers import route_distance

    stats = {"calls": 0, "searched": 0, "shorter": 0, "km_saved": 0.0}
    original = ucs_routing.exact_order

    def counting(route, parcel, context):
        stats["calls"] += 1
        stops = {parcel[p]["delivery_location_id"] for p in route}
        stats["searched"] += 2 <= len(stops) <= ucs_routing.MAX_STOPS
        result = original(route, parcel, context)
        if result is not None:
            distances = context["travel_distance"]
            stats["shorter"] += 1
            stats["km_saved"] += (route_distance(route, parcel, distances)
                                  - route_distance(result, parcel, distances))
        return result

    ucs_routing.exact_order = counting
    try:
        for day in DAYS:
            with tempfile.TemporaryDirectory() as folder:
                Simulator(*day_input_paths(data, day), dispatch_policy=ucs_routing.dispatch).run(
                    Path(folder) / "log.txt")
    finally:
        ucs_routing.exact_order = original
    return {
        "candidate_trips": stats["calls"],
        "searched": stats["searched"],
        "share_searched": round(stats["searched"] / stats["calls"], 3),
        "shorter_than_2opt": stats["shorter"],
        "share_of_searched_shorter": round(stats["shorter"] / stats["searched"], 3),
        "km_saved_per_day_on_candidate_trips": round(stats["km_saved"] / len(DAYS), 1),
        "note": "Counts every candidate trip D builds, including trips that then wait.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data", default="data")
    parser.add_argument("--results", default="results")
    parser.add_argument("--skip-search", action="store_true",
                        help="skip the exact_search analysis (re-simulates Policy D)")
    args = parser.parse_args(argv)
    data, results = Path(args.data), Path(args.results)

    policies = sorted(p.name for p in results.iterdir()
                      if p.is_dir() and (p / "day_001" / "metrics.json").exists())
    metrics = {p: load_metrics(results, p) for p in policies}

    report = {
        "dataset": dataset_facts(data),
        "ceiling": ceiling(data),
        "paired_tests": {label: paired(metrics[a], metrics[b]) for a, b, label in PAIRS
                         if a in metrics and b in metrics},
        "sensitivity": sensitivity(metrics),
        "weak_days": {
            "grow_2opt_wait_fill": weak_days(data, results, "grow_2opt_wait_fill", ["day_019", "day_004"]),
            "grow_2opt_wait": weak_days(data, results, "grow_2opt_wait", ["day_019", "day_004"]),
        },
        "stops_per_trip": {"grow_2opt_wait_fill": stops_per_trip(data, results, "grow_2opt_wait_fill", 8)},
    }
    if not args.skip_search:
        report["exact_search"] = exact_search(data)

    for section, value in report.items():
        print(f"\n== {section}")
        print(json.dumps(value if section != "ceiling" else
                         {k: v for k, v in value.items() if k != "per_day"}, indent=2))
    path = results / "analysis.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Run dispatch policies on many days, score every run and print a comparison table.

For each policy and day this does exactly what the two README commands do:
it runs the simulator (writing results/<policy>/<day>/log.txt) and then the
performance monitor (writing metrics.json beside the log). Afterwards it prints
the mean of every metric per policy and writes results/summary.csv.

Examples, from the project root:

    python3 run_experiments.py                                  # every policy, all 20 days
    python3 run_experiments.py --policies baseline grow_2opt_wait_fill  # selected policies
    python3 run_experiments.py --policies edf_nn_wait --days 1-5      # day_001 to day_005
    python3 run_experiments.py --summary-only                   # re-print the table from existing results
    python3 run_experiments.py --per-day                        # also print one row per day

Standard library only. Runs are deterministic, so repeating a command gives the same files.
"""

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from statistics import mean, pstdev
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
POLICY_DIR = ROOT / "solution" / "policies"
NOT_POLICIES = {"__init__", "helpers"}

# Metrics shown in the summary table, in this order. Rates are averaged as daily rates.
TABLE_KEYS = (
    "on_time_rate", "delivery_rate", "parcels_on_time", "parcels_late",
    "parcels_early", "km_per_delivered_parcel", "trips", "total_km",
    "parcels_per_trip", "capacity_utilisation", "range_utilisation",
)


def discover_policies() -> List[str]:
    """Return every policy module in solution/policies/, baseline first."""

    names = sorted(
        path.stem for path in POLICY_DIR.glob("*.py")
        if path.stem not in NOT_POLICIES and not path.stem.startswith("_")
    )
    return sorted(names, key=lambda name: name != "baseline")


def parse_days(spec: str) -> List[str]:
    """Turn '1-20', '3' or '1,4,7-9' into day identifiers such as 'day_001'."""

    days: List[int] = []
    for part in spec.split(","):
        if "-" in part:
            low, high = part.split("-")
            days.extend(range(int(low), int(high) + 1))
        else:
            days.append(int(part))
    return [f"day_{day:03d}" for day in days]


def run_one(task: Tuple[str, str, str, str]) -> Tuple[str, str, float, Optional[str]]:
    """Simulate one policy on one day, then score it. Returns (policy, day, seconds, error)."""

    policy, day, data, results = task
    # Imported here so each worker process loads the project from the project root.
    sys.path.insert(0, str(ROOT))
    from simulator.loaders import day_input_paths
    from simulator.simulator import Simulator, load_policy
    from solution import performance_monitor

    started = time.perf_counter()
    try:
        output = Path(results) / policy / day
        parcels, distances, config = day_input_paths(Path(data), day)
        simulator = Simulator(
            parcels, distances, config,
            dispatch_policy=load_policy(f"solution.policies.{policy}"),
        )
        simulator.run(output / "log.txt")
        status = performance_monitor.main(
            ["--data", data, "--day", day, "--log", str(output / "log.txt")]
        )
        if status:
            raise RuntimeError(f"performance monitor exited with {status}")
    except Exception as exc:  # Report and carry on with the other runs.
        return policy, day, time.perf_counter() - started, f"{type(exc).__name__}: {exc}"
    return policy, day, time.perf_counter() - started, None


def load_metrics(results: Path, policy: str, days: List[str]) -> Dict[str, Dict[str, float]]:
    """Read metrics.json for each day that has one."""

    found = {}
    for day in days:
        path = results / policy / day / "metrics.json"
        if path.exists():
            found[day] = json.loads(path.read_text(encoding="utf-8"))
    return found


def print_summary(results: Path, policies: List[str], days: List[str], per_day: bool) -> None:
    """Print mean metrics per policy, compare with baseline, and write results/summary.csv."""

    rows = []
    baseline = load_metrics(results, "baseline", days)
    for policy in policies:
        metrics = load_metrics(results, policy, days)
        if not metrics:
            print(f"{policy}: no metrics.json found, skipped")
            continue
        rates = [m["on_time_rate"] for m in metrics.values()]
        row = {"policy": policy, "days": len(metrics)}
        for key in TABLE_KEYS:
            row[key] = mean(m[key] for m in metrics.values())
        row["on_time_rate_sd"] = pstdev(rates)
        shared = [day for day in metrics if day in baseline]
        if policy != "baseline" and shared:
            row["days_beating_baseline"] = sum(
                metrics[d]["on_time_rate"] > baseline[d]["on_time_rate"] for d in shared
            )
        rows.append((row, metrics))

    header = (f"{'policy':<22}{'days':>5}{'on_time':>9}{'sd':>8}{'deliv':>8}"
              f"{'on_time#':>10}{'late#':>8}{'early#':>8}{'km/parcel':>11}{'trips':>7}"
              f"{'km/day':>9}{'cap_use':>9}{'rng_use':>9}{'>base':>7}")
    print()
    print(header)
    print("-" * len(header))
    for row, _ in rows:
        beat = row.get("days_beating_baseline")
        beat_text = "" if beat is None else f"{beat}/{row['days']}"
        print(f"{row['policy']:<22}{row['days']:>5}{row['on_time_rate']:>9.4f}"
              f"{row['on_time_rate_sd']:>8.4f}{row['delivery_rate']:>8.4f}"
              f"{row['parcels_on_time']:>10.1f}{row['parcels_late']:>8.1f}"
              f"{row['parcels_early']:>8.1f}{row['km_per_delivered_parcel']:>11.3f}"
              f"{row['trips']:>7.1f}{row['total_km']:>9.0f}"
              f"{row['capacity_utilisation']:>9.4f}{row['range_utilisation']:>9.4f}"
              f"{beat_text:>7}")
    print("on_time, deliv, km/parcel, cap_use and rng_use are means of the daily values; "
          "# columns, trips and km/day are per day;\ncap_use = share of trip capacity filled, "
          "rng_use = share of trip range driven; >base = days with a higher on_time_rate "
          "than baseline.")

    if per_day and rows:
        print()
        print(f"{'day':<10}" + "".join(f"{row['policy'][:14]:>16}" for row, _ in rows))
        for day in days:
            cells = "".join(
                f"{metrics[day]['on_time_rate']:>16.4f}" if day in metrics else f"{'-':>16}"
                for _, metrics in rows
            )
            print(f"{day:<10}{cells}")

    results.mkdir(parents=True, exist_ok=True)
    with (results / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = ["policy", "days", *TABLE_KEYS, "on_time_rate_sd", "days_beating_baseline"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row, _ in rows:
            writer.writerow({key: row.get(key, "") for key in fields})
    with (results / "summary_per_day.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["policy", "day", *TABLE_KEYS])
        for row, metrics in rows:
            for day in days:
                if day in metrics:
                    writer.writerow([row["policy"], day, *(metrics[day][k] for k in TABLE_KEYS)])
    print(f"\nWrote {results / 'summary.csv'} and {results / 'summary_per_day.csv'}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--policies", nargs="+",
                        help="module names in solution/policies/ (default: all of them)")
    parser.add_argument("--days", default="1-20", help="for example 1-20, 3 or 1,4,7-9")
    parser.add_argument("--data", default="data", help="input data directory")
    parser.add_argument("--results", default="results", help="output root directory")
    parser.add_argument("--workers", type=int, default=None,
                        help="parallel processes (default: one per CPU; 1 runs sequentially)")
    parser.add_argument("--summary-only", action="store_true",
                        help="do not simulate; summarise the existing results")
    parser.add_argument("--per-day", action="store_true", help="also print on_time_rate per day")
    args = parser.parse_args(argv)

    policies = args.policies or discover_policies()
    days = parse_days(args.days)
    results = Path(args.results)

    if not args.summary_only:
        tasks = [(p, d, args.data, args.results) for p in policies for d in days]
        started = time.perf_counter()
        failures = 0
        if args.workers == 1:
            outcomes = map(run_one, tasks)
            pool = None
        else:
            pool = ProcessPoolExecutor(max_workers=args.workers)
            outcomes = pool.map(run_one, tasks)
        for policy, day, seconds, error in outcomes:
            if error:
                failures += 1
                print(f"FAILED {policy} {day}: {error}")
            else:
                print(f"done   {policy:<22}{day}  {seconds:6.1f}s")
        if pool is not None:
            pool.shutdown()
        print(f"{len(tasks)} runs, {failures} failed, {time.perf_counter() - started:.1f}s total")

    # Always include baseline in the table when its results exist, for comparison.
    shown = policies if "baseline" in policies else ["baseline"] + policies
    print_summary(results, shown, days, args.per_day)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

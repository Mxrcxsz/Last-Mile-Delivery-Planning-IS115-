"""Grid-search Policy B's two thresholds, choosing on tuning days and checking on test days.

Policy B (solution/policies/grow_2opt_wait_fill.py) has two settings:
    MIN_FILL    a trip loaded below this share of capacity counts as nearly empty
    WAIT_SLACK  minutes every parcel on the trip must be able to wait before C holds it back
MIN_FILL = 0 switches the waiting rule off, so those rows measure Policy B without waiting.

Each setting is run on every day. The best setting is chosen by its mean on_time_rate on
the tuning days only (default day_001 to day_010); its score on the test days (default
day_011 to day_020) shows whether the gain carries over to days it was not chosen on.

Run from the project root (standard library only, about 1 to 3 minutes):

    python3 tune_grow_2opt_wait_fill.py

Prints a table and writes results/tuning_grow_2opt_wait_fill.csv. Logs go to a temporary folder,
so results/<policy>/ is not touched.
"""

import argparse
import csv
import json
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from statistics import mean
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
FILLS = (0.0, 0.25, 0.5, 0.75, 0.9)
SLACKS = (10.0, 20.0, 40.0)


def run_one(task: Tuple[float, float, str, str]) -> Tuple[float, float, str, float]:
    """Run Policy B with the given thresholds on one day; return its on_time_rate."""

    fill, slack, day, data = task
    sys.path.insert(0, str(ROOT))
    import solution.policies.grow_2opt_wait_fill as policy_b
    from simulator.loaders import day_input_paths
    from simulator.simulator import Simulator
    from solution.performance_monitor import calculate_metrics

    policy_b.MIN_FILL, policy_b.WAIT_SLACK = fill, slack
    parcels_path, distances_path, config_path = day_input_paths(Path(data), day)
    simulator = Simulator(parcels_path, distances_path, config_path,
                          dispatch_policy=policy_b.dispatch)
    with tempfile.TemporaryDirectory() as folder:
        log = Path(folder) / "log.txt"
        simulator.run(log)
        with log.open(encoding="utf-8") as stream:
            events = [json.loads(line) for line in stream if line.strip()]
    with parcels_path.open(newline="", encoding="utf-8-sig") as stream:
        parcels = list(csv.DictReader(stream))
    with distances_path.open(newline="", encoding="utf-8-sig") as stream:
        distances = list(csv.DictReader(stream))
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    metrics = calculate_metrics(parcels, distances, config, events)
    return fill, slack, day, metrics["on_time_rate"]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data", default="data")
    parser.add_argument("--tune-days", default="1-10")
    parser.add_argument("--test-days", default="11-20")
    parser.add_argument("--output", default="results/tuning_grow_2opt_wait_fill.csv")
    args = parser.parse_args(argv)

    def days(spec: str) -> List[str]:
        low, high = (int(x) for x in spec.split("-"))
        return [f"day_{d:03d}" for d in range(low, high + 1)]

    tune, test = days(args.tune_days), days(args.test_days)
    tasks = [(f, s, d, args.data) for f in FILLS for s in SLACKS for d in tune + test]
    scores = {}
    with ProcessPoolExecutor() as pool:
        for fill, slack, day, rate in pool.map(run_one, tasks):
            scores.setdefault((fill, slack), {})[day] = rate

    rows = []
    for (fill, slack), by_day in scores.items():
        rows.append({
            "min_fill": fill, "wait_slack": slack,
            "tune_on_time_rate": round(mean(by_day[d] for d in tune), 4),
            "test_on_time_rate": round(mean(by_day[d] for d in test), 4),
        })
    best = max(rows, key=lambda r: (r["tune_on_time_rate"], -r["min_fill"], -r["wait_slack"]))

    print(f"{'MIN_FILL':>9}{'WAIT_SLACK':>12}{'tune':>9}{'test':>9}")
    for row in rows:
        mark = "  <- chosen on tuning days" if row is best else ""
        print(f"{row['min_fill']:>9}{row['wait_slack']:>12}"
              f"{row['tune_on_time_rate']:>9.4f}{row['test_on_time_rate']:>9.4f}{mark}")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

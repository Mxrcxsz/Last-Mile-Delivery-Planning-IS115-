"""Calculate performance metrics from one simulation run's event log."""

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from simulator.loaders import day_input_paths, parse_time
from simulator.simulator import HUB


def calculate_metrics(
    parcels: List[Dict[str, str]],
    distances: List[Dict[str, str]],
    config: Dict[str, Any],
    events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return a JSON-serializable dictionary for the chosen performance metric.

    parcels and distances are the rows of the day's CSV files, config is the
    contents of config.json, and events are the records from the run's log.
    CSV values are strings, so convert them before calculating. In particular,
    parcel times are "HH:MM" strings while event times are minutes after
    midnight: "17:00" is 17 * 60 = 1020.
    """

    # Headline metric: on-time delivery rate.
    #   on_time_rate = parcels delivered inside [window_start, window_end]
    #                  / ALL parcels that arrived that day.
    # Undelivered parcels stay in the denominator, so doing nothing scores 0
    # and the metric cannot be won by a trivial policy.
    # Early delivery (before window start) is NOT counted as on time.
    window = {}
    for row in parcels:
        window[row["parcel_id"]] = (
            parse_time(row["delivery_window_start"]),
            parse_time(row["delivery_window_end"]),
            row["delivery_location_id"],
        )
    total = len(window)

    deliveries = [e for e in events if e["event_type"] == "delivery"]
    on_time = early = late = 0
    for event in deliveries:
        start, end, _ = window[event["parcel_id"]]
        if event["time"] < start:
            early += 1
        elif event["time"] > end:
            late += 1
        else:
            on_time += 1

    # Supporting metric: km driven per delivered parcel.
    # Rebuild each trip's route from its delivery order: HUB -> stops -> HUB.
    dist = {}
    for row in distances:
        dist[(row["location_1"], row["location_2"])] = float(row["dist"])
    trips: Dict[Any, List[Any]] = {}
    for event in deliveries:
        trips.setdefault((event["vehicle_id"], event["trip_id"]), []).append(event)
    total_km = 0.0
    for stops in trips.values():
        stops.sort(key=lambda e: e["time"])
        route = [HUB] + [window[e["parcel_id"]][2] for e in stops] + [HUB]
        for a, b in zip(route, route[1:]):
            total_km += 0.0 if a == b else dist[(a, b)]

    # Fleet usage: how full and how long the trips that left the hub were.
    #   capacity_utilisation = size delivered / (trips x vehicle capacity)
    #   range_utilisation    = km driven / (trips x vehicle range)
    size = {row["parcel_id"]: float(row["size"]) for row in parcels}
    load = sum(size[event["parcel_id"]] for event in deliveries)
    number_of_trips = len(trips)
    capacity_offered = number_of_trips * float(config["capacity"])
    range_offered = number_of_trips * float(config["vehicle_range_km"])

    delivered = len(deliveries)
    return {
        "on_time_rate": round(on_time / total, 4) if total else 0.0,
        "parcels_total": total,
        "parcels_delivered": delivered,
        "parcels_on_time": on_time,
        "parcels_late": late,
        "parcels_early": early,
        "delivery_rate": round(delivered / total, 4) if total else 0.0,
        "km_per_delivered_parcel": round(total_km / delivered, 3) if delivered else 0.0,
        "trips": number_of_trips,
        "total_km": round(total_km, 3),
        "km_per_trip": round(total_km / number_of_trips, 3) if number_of_trips else 0.0,
        "parcels_per_trip": round(delivered / number_of_trips, 3) if number_of_trips else 0.0,
        "capacity_utilisation": round(load / capacity_offered, 4) if capacity_offered else 0.0,
        "range_utilisation": round(total_km / range_offered, 4) if range_offered else 0.0,
    }


def main(argv: Optional[List[str]] = None) -> int:
    """Load one day's inputs and event log, then write the metrics report."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"),
                        help="directory containing dist.csv, config.json and demand/")
    parser.add_argument("--day", required=True, help="day identifier, for example day_001")
    parser.add_argument("--log", type=Path, required=True,
                        help="event log from a simulator run")
    parser.add_argument("--output", type=Path,
                        help="JSON report (default: metrics.json beside the selected log)")
    args = parser.parse_args(argv)
    try:
        parcel_path, distance_path, config_path = day_input_paths(args.data, args.day)
        output = args.output if args.output is not None else args.log.with_name("metrics.json")
        # The input files all live in the data directory, so this also protects them.
        if output.resolve() == args.data.resolve() or args.data.resolve() in output.resolve().parents:
            raise ValueError("report output must be outside the input data directory")
        if output.resolve() == args.log.resolve():
            raise ValueError("report output must not overwrite the log")
        with parcel_path.open(newline="", encoding="utf-8-sig") as stream:
            parcels = list(csv.DictReader(stream))
        with distance_path.open(newline="", encoding="utf-8-sig") as stream:
            distances = list(csv.DictReader(stream))
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        with args.log.open(encoding="utf-8") as stream:
            events = [json.loads(line) for line in stream if line.strip()]
        metrics = calculate_metrics(parcels, distances, config, events)
        report = json.dumps(metrics, indent=2, allow_nan=False) + "\n"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
    except (OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(f"Metrics report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
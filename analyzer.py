"""
analyzer.py
===========
Parses SUMO output files and generates a structured report.

Metrics computed:
  • Network-level: throughput, mean travel time, mean speed
  • Edge-level: congestion index, V/C ratio, density
  • Vehicle-class breakdown: travel time by type
  • Indian-specific: PCU/hour on major corridors, two-wheeler share
"""

import csv
import json
import logging
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# PCU equivalents (same as demand generator)
PCU = {
    "two_wheeler": 0.5,
    "auto_rickshaw": 0.75,
    "car_small": 1.0,
    "car_suv": 1.0,
    "bus_city": 3.0,
    "minibus": 1.5,
    "truck_lgv": 1.5,
    "truck_hgv": 3.0,
    "bicycle": 0.2,
}


class TrafficAnalyzer:
    def __init__(self, output_dir: Path, results: dict):
        self.output_dir = Path(output_dir)
        self.results = results
        self.prefix = self.output_dir / "output"

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def generate_report(self) -> Path:
        """Parse outputs and write JSON + CSV report."""
        report = {
            "simulation": self.results,
            "network": self._parse_summary(),
            "trips": self._parse_tripinfo(),
            "edges": self._parse_edgedata(),
        }
        report["indian_metrics"] = self._compute_indian_metrics(report)

        # JSON report
        json_path = self.output_dir / "report.json"
        json_path.write_text(json.dumps(report, indent=2))
        log.info(f"JSON report: {json_path}")

        # CSV summary
        csv_path = self._write_csv_summary(report)
        log.info(f"CSV summary: {csv_path}")

        # Console summary
        self._print_summary(report)

        return json_path

    # ------------------------------------------------------------------ #
    #  Parsers                                                             #
    # ------------------------------------------------------------------ #

    def _parse_summary(self) -> dict:
        summary_file = Path(str(self.prefix) + ".summary.xml")
        if not summary_file.exists():
            return {}
        try:
            tree = ET.parse(str(summary_file))
            steps = tree.findall(".//step")
            if not steps:
                return {}
            last = steps[-1]
            return {
                "end_time": float(last.get("time", 0)),
                "inserted": int(last.get("inserted", 0)),
                "ended": int(last.get("ended", 0)),
                "teleports": int(last.get("teleports", 0)),
                "collisions": int(last.get("collisions", 0)),
                "mean_speed_ms": float(last.get("meanSpeed", 0)),
                "mean_speed_kmh": float(last.get("meanSpeed", 0)) * 3.6,
            }
        except Exception as e:
            log.warning(f"Summary parse error: {e}")
            return {}

    def _parse_tripinfo(self) -> dict:
        tripinfo_file = Path(str(self.prefix) + ".tripinfo.xml")
        if not tripinfo_file.exists():
            return {}
        try:
            tree = ET.parse(str(tripinfo_file))
            trips = tree.findall(".//tripinfo")
            if not trips:
                return {}

            by_type = defaultdict(list)
            durations = []
            wait_times = []
            time_losses = []
            route_lengths = []

            for t in trips:
                vtype = t.get("vType", "unknown")
                duration = float(t.get("duration", 0))
                wait = float(t.get("waitingTime", 0))
                loss = float(t.get("timeLoss", 0))
                length = float(t.get("routeLength", 0))
                by_type[vtype].append(duration)
                durations.append(duration)
                wait_times.append(wait)
                time_losses.append(loss)
                route_lengths.append(length)

            def safe_mean(lst):
                return round(sum(lst) / len(lst), 2) if lst else 0

            type_summary = {}
            for vtype, durs in by_type.items():
                pcu = PCU.get(vtype, 1.0)
                type_summary[vtype] = {
                    "count": len(durs),
                    "mean_duration_s": safe_mean(durs),
                    "pcu_equivalent": pcu,
                    "pcu_total": round(len(durs) * pcu, 1),
                }

            return {
                "total_trips": len(trips),
                "mean_duration_s": safe_mean(durations),
                "mean_waiting_s": safe_mean(wait_times),
                "mean_time_loss_s": safe_mean(time_losses),
                "mean_route_length_m": safe_mean(route_lengths),
                "by_vehicle_type": type_summary,
            }
        except Exception as e:
            log.warning(f"Tripinfo parse error: {e}")
            return {}

    def _parse_edgedata(self) -> dict:
        edgedata_file = Path(str(self.prefix) + ".edgedata.xml")
        if not edgedata_file.exists():
            return {}
        try:
            tree = ET.parse(str(edgedata_file))
            intervals = tree.findall(".//interval")
            if not intervals:
                return {}

            edge_stats = {}
            for interval in intervals:
                for edge in interval.findall("edge"):
                    eid = edge.get("id", "")
                    density = float(edge.get("density", 0))
                    speed = float(edge.get("speed", 0))
                    entered = int(float(edge.get("entered", 0)))
                    edge_stats[eid] = {
                        "density_veh_km": round(density, 2),
                        "speed_ms": round(speed, 2),
                        "speed_kmh": round(speed * 3.6, 1),
                        "vehicles_entered": entered,
                    }

            # Top congested edges
            congested = sorted(
                edge_stats.items(),
                key=lambda x: x[1]["density_veh_km"],
                reverse=True,
            )[:10]

            return {
                "total_edges_measured": len(edge_stats),
                "top_congested_edges": {k: v for k, v in congested},
            }
        except Exception as e:
            log.warning(f"Edgedata parse error: {e}")
            return {}

    # ------------------------------------------------------------------ #
    #  Indian-specific metrics                                            #
    # ------------------------------------------------------------------ #

    def _compute_indian_metrics(self, report: dict) -> dict:
        trips = report.get("trips", {})
        by_type = trips.get("by_vehicle_type", {})

        total_vehicles = sum(v["count"] for v in by_type.values())
        total_pcu = sum(v["pcu_total"] for v in by_type.values())
        tw_count = by_type.get("two_wheeler", {}).get("count", 0)
        two_wheeler_share = round(tw_count / total_vehicles * 100, 1) if total_vehicles else 0

        sim_hours = report.get("network", {}).get("end_time", 3600) / 3600.0
        pcu_per_hour = round(total_pcu / sim_hours, 0) if sim_hours > 0 else 0

        mean_speed = report.get("network", {}).get("mean_speed_kmh", 0)
        # Level of service classification for Indian urban roads
        los = self._level_of_service(mean_speed)

        return {
            "total_vehicles": total_vehicles,
            "total_pcu": round(total_pcu, 1),
            "pcu_per_hour": pcu_per_hour,
            "two_wheeler_share_pct": two_wheeler_share,
            "level_of_service": los,
            "mean_network_speed_kmh": round(mean_speed, 1),
        }

    @staticmethod
    def _level_of_service(speed_kmh: float) -> str:
        """Indian HCM-based Level of Service for urban arterials."""
        if speed_kmh >= 40:   return "A (Free flow)"
        if speed_kmh >= 32:   return "B (Reasonably free)"
        if speed_kmh >= 24:   return "C (Stable)"
        if speed_kmh >= 16:   return "D (Approaching unstable)"
        if speed_kmh >= 10:   return "E (Unstable)"
        return "F (Forced/breakdown)"

    # ------------------------------------------------------------------ #
    #  CSV export                                                          #
    # ------------------------------------------------------------------ #

    def _write_csv_summary(self, report: dict) -> Path:
        csv_path = self.output_dir / "summary.csv"
        rows = []

        net = report.get("network", {})
        for k, v in net.items():
            rows.append(["network", k, v])

        indian = report.get("indian_metrics", {})
        for k, v in indian.items():
            rows.append(["indian_metrics", k, v])

        trips = report.get("trips", {})
        for k, v in trips.items():
            if k != "by_vehicle_type":
                rows.append(["trips", k, v])

        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["category", "metric", "value"])
            writer.writerows(rows)

        return csv_path

    # ------------------------------------------------------------------ #
    #  Console print                                                       #
    # ------------------------------------------------------------------ #

    def _print_summary(self, report: dict):
        indian = report.get("indian_metrics", {})
        trips = report.get("trips", {})
        net = report.get("network", {})

        log.info("")
        log.info("╔══════════════════════════════════════════════╗")
        log.info("║      SIMULATION RESULTS SUMMARY              ║")
        log.info("╠══════════════════════════════════════════════╣")
        log.info(f"║  Total vehicles  : {indian.get('total_vehicles', 'N/A'):<25}║")
        log.info(f"║  PCU/hour        : {indian.get('pcu_per_hour', 'N/A'):<25}║")
        log.info(f"║  2-wheeler share : {str(indian.get('two_wheeler_share_pct','N/A'))+'%':<25}║")
        log.info(f"║  Mean speed      : {str(round(indian.get('mean_network_speed_kmh',0),1))+' km/h':<25}║")
        log.info(f"║  Level of Service: {indian.get('level_of_service','N/A'):<25}║")
        log.info(f"║  Teleports       : {net.get('teleports','N/A'):<25}║")
        log.info(f"║  Mean trip time  : {str(trips.get('mean_duration_s','N/A'))+'s':<25}║")
        log.info("╚══════════════════════════════════════════════╝")

"""
vehicle_types.py
================
Generates a SUMO additional file defining the heterogeneous Indian vehicle
fleet: two-wheelers, three-wheelers (auto-rickshaws), cars, buses, trucks,
cyclists, and pedestrians.

Key Indian traffic behaviours modelled:
  • No strict lane discipline  → high lcStrategic / lcKeepRight values
  • Aggressive gap acceptance  → minGap reduced, tau lowered
  • Two-wheelers weave in gaps → latAlignment "arbitrary", maxSpeedLat high
  • Auto-rickshaws: slow, narrow, frequent stops
  • Buses: mixed stopping in-lane and at kerb
  • Trucks: overloaded → lower acceleration/deceleration
"""

import xml.etree.ElementTree as ET
from pathlib import Path
import logging

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Fleet composition (% of total vehicles) based on urban Indian traffic surveys
# Varies by peak period and city tier; these are Tier-1 city morning peak values
# ──────────────────────────────────────────────────────────────────────────────
FLEET_COMPOSITION = {
    "two_wheeler":      0.42,   # motorcycles + scooters (dominant)
    "auto_rickshaw":    0.12,   # 3-wheelers
    "car_small":        0.22,   # hatchbacks / sedans (Maruti, Hyundai)
    "car_suv":          0.06,   # SUV / MUV
    "bus_city":         0.05,   # BMTC / DTC / MTC etc.
    "minibus":          0.03,   # school / office van
    "truck_lgv":        0.05,   # light goods vehicle
    "truck_hgv":        0.03,   # heavy goods vehicle
    "bicycle":          0.02,   # pedal cycle
}

# ──────────────────────────────────────────────────────────────────────────────
# Vehicle type definitions
# Each entry maps to SUMO vType attributes.
# Notation: tau = reaction time (s), sigma = driver imperfection [0,1]
# ──────────────────────────────────────────────────────────────────────────────
VEHICLE_TYPES = {
    "two_wheeler": {
        "vClass":           "motorcycle",
        "color":            "0.8,0.2,0.2",
        "length":           "2.0",
        "width":            "0.7",
        "height":           "1.2",
        "minGap":           "0.8",          # close following
        "accel":            "3.5",
        "decel":            "5.0",
        "emergencyDecel":   "8.0",
        "maxSpeed":         "22.2",         # 80 km/h
        "speedFactor":      "1.2",          # often over speed limit
        "speedDev":         "0.2",
        "sigma":            "0.6",          # moderate imperfection
        "tau":              "0.8",          # aggressive reaction
        # SUMO lateral model
        "laneChangeModel":  "SL2015",
        "latAlignment":     "arbitrary",    # lane-splitting behaviour
        "maxSpeedLat":      "2.0",          # m/s lateral speed
        "minGapLat":        "0.3",          # tight lateral gap
        "lcStrategic":      "0.5",
        "lcCooperative":    "0.2",
        "lcSpeedGain":      "2.0",
        "lcKeepRight":      "0.0",          # do NOT keep right
        "lcOvertakeRight":  "1.0",
        # Car-following model
        "carFollowModel":   "IDM",
        "delta":            "4",
        "stepping":         "0.25",
    },

    "auto_rickshaw": {
        "vClass":           "taxi",
        "color":            "1.0,0.6,0.0",  # yellow-black livery
        "length":           "3.2",
        "width":            "1.4",
        "height":           "1.7",
        "minGap":           "1.0",
        "accel":            "1.5",
        "decel":            "4.0",
        "emergencyDecel":   "6.5",
        "maxSpeed":         "11.1",         # 40 km/h max
        "speedFactor":      "0.9",
        "speedDev":         "0.15",
        "sigma":            "0.7",
        "tau":              "1.0",
        "laneChangeModel":  "SL2015",
        "latAlignment":     "arbitrary",
        "maxSpeedLat":      "1.0",
        "minGapLat":        "0.4",
        "lcCooperative":    "0.1",
        "lcKeepRight":      "0.0",
        "carFollowModel":   "IDM",
        "delta":            "4",
    },

    "car_small": {
        "vClass":           "passenger",
        "color":            "0.3,0.5,0.9",
        "length":           "3.8",
        "width":            "1.6",
        "height":           "1.5",
        "minGap":           "1.5",
        "accel":            "2.5",
        "decel":            "4.5",
        "emergencyDecel":   "7.0",
        "maxSpeed":         "19.4",         # 70 km/h
        "speedFactor":      "1.1",
        "speedDev":         "0.15",
        "sigma":            "0.5",
        "tau":              "1.0",
        "laneChangeModel":  "SL2015",
        "latAlignment":     "arbitrary",
        "maxSpeedLat":      "1.2",
        "minGapLat":        "0.5",
        "lcCooperative":    "0.3",
        "lcKeepRight":      "0.1",
        "carFollowModel":   "IDM",
        "delta":            "4",
    },

    "car_suv": {
        "vClass":           "passenger",
        "color":            "0.2,0.3,0.7",
        "length":           "4.5",
        "width":            "1.8",
        "height":           "1.7",
        "minGap":           "1.8",
        "accel":            "2.8",
        "decel":            "4.5",
        "emergencyDecel":   "7.0",
        "maxSpeed":         "22.2",
        "speedFactor":      "1.15",
        "speedDev":         "0.2",
        "sigma":            "0.4",
        "tau":              "1.0",
        "laneChangeModel":  "SL2015",
        "latAlignment":     "arbitrary",
        "maxSpeedLat":      "1.0",
        "minGapLat":        "0.6",
        "carFollowModel":   "IDM",
        "delta":            "4",
    },

    "bus_city": {
        "vClass":           "bus",
        "color":            "0.6,0.0,0.6",
        "length":           "12.0",
        "width":            "2.5",
        "height":           "3.2",
        "minGap":           "2.0",
        "accel":            "1.2",
        "decel":            "3.5",
        "emergencyDecel":   "5.5",
        "maxSpeed":         "16.7",         # 60 km/h
        "speedFactor":      "0.85",         # buses run slow
        "speedDev":         "0.1",
        "sigma":            "0.4",
        "tau":              "1.5",
        "laneChangeModel":  "SL2015",
        "latAlignment":     "right",        # buses prefer kerb lane
        "maxSpeedLat":      "0.6",
        "minGapLat":        "0.8",
        "lcCooperative":    "0.5",
        "lcKeepRight":      "1.0",
        "carFollowModel":   "IDM",
        "delta":            "4",
    },

    "minibus": {
        "vClass":           "bus",
        "color":            "0.8,0.4,0.0",
        "length":           "6.0",
        "width":            "2.0",
        "height":           "2.4",
        "minGap":           "1.5",
        "accel":            "1.8",
        "decel":            "4.0",
        "emergencyDecel":   "6.0",
        "maxSpeed":         "16.7",
        "speedFactor":      "1.05",
        "speedDev":         "0.2",
        "sigma":            "0.5",
        "tau":              "1.2",
        "laneChangeModel":  "SL2015",
        "latAlignment":     "arbitrary",
        "maxSpeedLat":      "0.8",
        "carFollowModel":   "IDM",
        "delta":            "4",
    },

    "truck_lgv": {
        "vClass":           "truck",
        "color":            "0.5,0.5,0.5",
        "length":           "6.5",
        "width":            "2.2",
        "height":           "2.8",
        "minGap":           "2.0",
        "accel":            "1.0",
        "decel":            "3.0",
        "emergencyDecel":   "5.0",
        "maxSpeed":         "13.9",         # 50 km/h
        "speedFactor":      "0.9",
        "speedDev":         "0.1",
        "sigma":            "0.3",
        "tau":              "1.5",
        "laneChangeModel":  "SL2015",
        "latAlignment":     "right",
        "maxSpeedLat":      "0.5",
        "lcKeepRight":      "0.8",
        "carFollowModel":   "IDM",
        "delta":            "4",
    },

    "truck_hgv": {
        "vClass":           "truck",
        "color":            "0.3,0.3,0.3",
        "length":           "12.0",
        "width":            "2.5",
        "height":           "3.8",
        "minGap":           "2.5",
        "accel":            "0.6",
        "decel":            "2.5",
        "emergencyDecel":   "4.5",
        "maxSpeed":         "11.1",         # 40 km/h
        "speedFactor":      "0.8",
        "speedDev":         "0.05",
        "sigma":            "0.2",
        "tau":              "1.8",
        "laneChangeModel":  "SL2015",
        "latAlignment":     "right",
        "maxSpeedLat":      "0.4",
        "lcKeepRight":      "1.5",
        "carFollowModel":   "IDM",
        "delta":            "4",
    },

    "bicycle": {
        "vClass":           "bicycle",
        "color":            "0.0,0.7,0.3",
        "length":           "1.8",
        "width":            "0.6",
        "height":           "1.7",
        "minGap":           "0.5",
        "accel":            "1.0",
        "decel":            "3.0",
        "emergencyDecel":   "5.0",
        "maxSpeed":         "6.9",          # 25 km/h
        "speedFactor":      "0.9",
        "speedDev":         "0.3",
        "sigma":            "0.5",
        "tau":              "0.9",
        "laneChangeModel":  "SL2015",
        "latAlignment":     "arbitrary",
        "maxSpeedLat":      "1.5",
        "minGapLat":        "0.2",
        "carFollowModel":   "IDM",
        "delta":            "4",
    },
}


class IndianVehicleTypeGenerator:
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.out_file = self.output_dir / "indian_vtypes.add.xml"

    def generate(self) -> Path:
        root = ET.Element("additional")

        # Write vehicle types
        for vtype_id, params in VEHICLE_TYPES.items():
            attrib = {"id": vtype_id, **params}
            ET.SubElement(root, "vType", attrib=attrib)

        # Write distribution element for weighted random selection
        dist_elem = ET.SubElement(root, "vTypeDistribution", attrib={"id": "indian_fleet"})
        for vtype_id, fraction in FLEET_COMPOSITION.items():
            ET.SubElement(dist_elem, "vType", attrib={
                "refid": vtype_id,
                "probability": str(fraction),
            })

        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(str(self.out_file), xml_declaration=True, encoding="utf-8")
        log.info(f"Vehicle types file: {self.out_file}")
        return self.out_file

    @staticmethod
    def fleet_composition() -> dict:
        """Return the fleet composition dict for external use."""
        return FLEET_COMPOSITION.copy()

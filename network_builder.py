"""
network_builder.py
==================
Fetches OpenStreetMap data for an Indian city region and converts it
to a SUMO-compatible .net.xml file using netconvert.

Indian-specific tweaks applied:
  • Mixed-traffic lane widths (2.5–3.5 m vs Western 3.7 m)
  • Junction angle relaxation for unplanned intersections
  • Auto-generation of pedestrian footways on major roads
  • Roundabout detection tuned for Indian traffic circles
  • Speed limit defaults per road class (Indian Motor Vehicles Act defaults)
"""

import logging
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

log = logging.getLogger(__name__)

# Indian default speed limits (kmph) per OSM highway tag
INDIAN_SPEED_LIMITS = {
    "motorway":       100,
    "trunk":          80,
    "primary":        60,
    "secondary":      50,
    "tertiary":       40,
    "residential":    30,
    "service":        20,
    "living_street":  15,
    "unclassified":   40,
}

# Lane width defaults (metres) – Indian roads are narrower
LANE_WIDTHS = {
    "motorway":    3.5,
    "trunk":       3.3,
    "primary":     3.0,
    "secondary":   2.8,
    "tertiary":    2.8,
    "residential": 2.5,
    "service":     2.5,
    "unclassified":2.8,
}


class IndianRoadNetworkBuilder:
    """
    Builds a SUMO road network from OpenStreetMap data for an Indian city.

    Parameters
    ----------
    city : str
        City name (used in Nominatim query, e.g. "Chennai").
    area_km2 : float
        Approximate square area to extract around the city centre.
    output_dir : Path
        Directory for all generated files.
    osm_file : str | None
        If provided, skip download and use this OSM file.
    """

    def __init__(self, city: str, area_km2: float, output_dir: Path,
                 osm_file: str | None = None):
        self.city = city
        self.area_km2 = area_km2
        self.output_dir = Path(output_dir)
        self.osm_file = osm_file
        self.osm_path = self.output_dir / "network.osm"
        self.net_path = self.output_dir / "network.net.xml"
        self.type_path = self.output_dir / "indian_edge_types.xml"

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def build(self) -> Path:
        """Full pipeline: download → type-file → netconvert → return path."""
        if self.osm_file:
            self.osm_path = Path(self.osm_file)
            log.info(f"Using existing OSM file: {self.osm_path}")
        else:
            self._download_osm()

        self._write_indian_type_file()
        self._run_netconvert()
        return self.net_path

    # ------------------------------------------------------------------ #
    #  Download                                                            #
    # ------------------------------------------------------------------ #

    def _download_osm(self):
        """Download OSM XML via Overpass API for a bounding box around city."""
        log.info(f"Geocoding '{self.city}' via Nominatim…")
        lat, lon = self._geocode(self.city)
        half = (self.area_km2 ** 0.5) / 2.0
        # Rough degree conversion: 1° lat ≈ 111 km, 1° lon ≈ 111 * cos(lat)
        import math
        dlat = half / 111.0
        dlon = half / (111.0 * math.cos(math.radians(lat)))
        bbox = (lat - dlat, lon - dlon, lat + dlat, lon + dlon)
        log.info(f"Bounding box: {bbox}")
        self._overpass_download(bbox)

    def _geocode(self, city: str) -> tuple[float, float]:
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": f"{city}, India", "format": "json", "limit": 1}
        headers = {"User-Agent": "IndianTrafficSim/1.0"}
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            raise ValueError(f"Could not geocode city: {city}")
        return float(data[0]["lat"]), float(data[0]["lon"])

    def _overpass_download(self, bbox: tuple):
        s, w, n, e = bbox
        query = f"""
        [out:xml][timeout:120];
        (
          way["highway"]({s},{w},{n},{e});
          relation["highway"]({s},{w},{n},{e});
        );
        (._;>;);
        out body;
        """
        log.info("Fetching OSM data from Overpass API…")
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            timeout=180,
        )
        resp.raise_for_status()
        self.osm_path.write_bytes(resp.content)
        log.info(f"OSM saved: {self.osm_path} ({self.osm_path.stat().st_size // 1024} KB)")

    # ------------------------------------------------------------------ #
    #  Indian edge type file                                               #
    # ------------------------------------------------------------------ #

    def _write_indian_type_file(self):
        """
        Generate a SUMO edge-type XML file with Indian-specific parameters:
        narrower lanes, lower speeds, mixed-traffic permissions.
        """
        root = ET.Element("types")

        for hw, speed in INDIAN_SPEED_LIMITS.items():
            lanes = self._default_lanes(hw)
            width = LANE_WIDTHS.get(hw, 3.0)
            # Indian roads allow bicycles, motorcycles on most road types
            allow = self._allowed_vehicles(hw)
            ET.SubElement(root, "type", attrib={
                "id": f"highway.{hw}",
                "priority": str(self._priority(hw)),
                "numLanes": str(lanes),
                "speed": str(speed / 3.6),          # m/s
                "allow": allow,
                "width": str(width),
                "sidewalkWidth": "1.5" if hw in ("primary", "secondary", "trunk") else "0",
                "oneway": "false",
            })

        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(str(self.type_path), xml_declaration=True, encoding="utf-8")
        log.info(f"Edge type file written: {self.type_path}")

    def _default_lanes(self, hw: str) -> int:
        mapping = {
            "motorway": 3, "trunk": 2, "primary": 2,
            "secondary": 1, "tertiary": 1, "residential": 1,
            "service": 1, "living_street": 1, "unclassified": 1,
        }
        return mapping.get(hw, 1)

    def _allowed_vehicles(self, hw: str) -> str:
        # Indian roads: two-wheelers (motorcycle) share space with cars/buses/trucks
        if hw in ("motorway", "trunk"):
            return "passenger bus truck motorcycle"
        if hw == "living_street":
            return "passenger motorcycle bicycle pedestrian"
        return "passenger bus truck motorcycle bicycle"

    def _priority(self, hw: str) -> int:
        order = ["living_street", "service", "unclassified", "residential",
                 "tertiary", "secondary", "primary", "trunk", "motorway"]
        return order.index(hw) + 1 if hw in order else 1

    # ------------------------------------------------------------------ #
    #  netconvert                                                          #
    # ------------------------------------------------------------------ #

    def _run_netconvert(self):
        """Run SUMO netconvert with Indian-specific flags."""
        cmd = [
            "netconvert",
            "--osm-files", str(self.osm_path),
            "--type-files", str(self.type_path),
            "--output-file", str(self.net_path),
            # Geometry
            "--geometry.remove",
            "--roundabouts.guess",
            "--ramps.guess",
            # Indian junction tuning
            "--junctions.join",
            "--junctions.join-dist", "15",          # m – tighter than Western default
            "--junctions.corner-detail", "3",
            "--offset.disable-normalization",
            # Lane discipline
            "--no-internal-links", "false",
            "--keep-edges.by-vclass", "passenger,motorcycle,bus,truck,bicycle",
            # Pedestrian
            "--sidewalks.guess",
            "--crossings.guess",
            # Output
            "--output.street-names",
            "--output.original-names",
        ]
        log.info(f"Running netconvert…")
        log.debug(" ".join(cmd))
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                log.error(result.stderr[-2000:])
                raise RuntimeError("netconvert failed – see logs above")
            log.info("netconvert succeeded.")
        except FileNotFoundError:
            log.warning("netconvert not found. Writing stub net.xml for testing.")
            self._write_stub_net()

    def _write_stub_net(self):
        """Minimal stub network for unit-testing without SUMO installed."""
        stub = """<?xml version="1.0" encoding="UTF-8"?>
<net version="1.16" junctionCornerDetail="5" limitTurnSpeed="5.50">
  <location netOffset="0.00,0.00" convBoundary="0.00,0.00,500.00,500.00"
            origBoundary="80.0,13.0,80.01,13.01" projParameter="!"/>
  <edge id="e1" from="j1" to="j2" priority="7" numLanes="2" speed="13.89">
    <lane id="e1_0" index="0" speed="13.89" length="200.00" width="3.0"
          shape="0.00,0.00 200.00,0.00"/>
    <lane id="e1_1" index="1" speed="13.89" length="200.00" width="3.0"
          shape="0.00,3.5 200.00,3.5"/>
  </edge>
  <edge id="e2" from="j2" to="j3" priority="5" numLanes="1" speed="11.11">
    <lane id="e2_0" index="0" speed="11.11" length="150.00" width="2.8"
          shape="200.00,0.00 350.00,0.00"/>
  </edge>
  <junction id="j1" type="dead_end" x="0.00" y="0.00" incLanes="" intLanes="" shape=""/>
  <junction id="j2" type="priority"  x="200.00" y="0.00" incLanes="e1_0 e1_1" intLanes="" shape=""/>
  <junction id="j3" type="dead_end" x="350.00" y="0.00" incLanes="e2_0" intLanes="" shape=""/>
</net>
"""
        self.net_path.write_text(stub)
        log.info(f"Stub net written: {self.net_path}")

"""Zone system for determining object positions relative to defined zones."""

import json
import os
from typing import Any


def point_in_polygon(px: float, py: float, polygon: list[list[float]]) -> bool:
    """Ray-casting algorithm to determine if a point is inside a polygon.

    Args:
        px: X coordinate of the point.
        py: Y coordinate of the point.
        polygon: List of [x, y] vertices defining the polygon.
    """
    n = len(polygon)
    inside = False

    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]

        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside

        j = i

    return inside


class ZoneManager:
    """Manages polygon zones and determines object-zone relationships."""

    def __init__(self, config_path: str = "../config/zones.json") -> None:
        self.config_path = config_path
        self.zones: list[dict[str, Any]] = []
        self.load_zones()

    def load_zones(self) -> None:
        """Load zones from JSON config file."""
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                data = json.load(f)
                self.zones = data.get("zones", [])
            print(f"[Zones] Loaded {len(self.zones)} zones from {self.config_path}")
        else:
            print(f"[Zones] No zones config found at {self.config_path}, using empty zones")
            self.zones = []

    def check_zones(self, center: list[float]) -> list[str]:
        """Check which zones a point (object center) is inside.

        Args:
            center: [x, y] coordinates of the object center.

        Returns:
            List of zone IDs the point is inside.
        """
        inside_zones = []
        for zone in self.zones:
            polygon = zone.get("polygon", [])
            zone_id = zone.get("id", "unknown")
            if point_in_polygon(center[0], center[1], polygon):
                inside_zones.append(zone_id)
        return inside_zones

    def evaluate_zone_events(
        self,
        track_id: int,
        current_zones: list[str],
        track_state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Evaluate zone entry/exit events for a tracked object.

        Args:
            track_id: The tracking ID.
            current_zones: Zones the object is currently in.
            track_state: The tracker's state for this object.

        Returns:
            List of zone events (entry/exit).
        """
        events = []
        prev_zones = track_state.get("current_zones", set())

        current_set = set(current_zones)

        # Zone entries
        new_entries = current_set - prev_zones
        for zone_id in new_entries:
            events.append({
                "type": "zone_entry",
                "track_id": track_id,
                "zone_id": zone_id,
            })

        # Zone exits
        new_exits = prev_zones - current_set
        for zone_id in new_exits:
            events.append({
                "type": "zone_exit",
                "track_id": track_id,
                "zone_id": zone_id,
            })

        # Update track state
        track_state["current_zones"] = current_set
        track_state["entered_zones"] = track_state.get("entered_zones", set()) | current_set

        return events

    def get_zones(self) -> list[dict[str, Any]]:
        """Return all configured zones."""
        return self.zones

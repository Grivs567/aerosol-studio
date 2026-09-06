"""Pure geometry helpers for Aerosol Studio."""

from aerosolstudio.geometry.coordinates import (
    bounding_box,
    normalize_polygon,
    time_diameter_points,
)
from aerosolstudio.geometry.polygons import (
    point_in_polygon,
    points_in_polygon,
    polygon_mask,
    validate_polygon,
)

__all__ = [
    "bounding_box",
    "normalize_polygon",
    "point_in_polygon",
    "points_in_polygon",
    "polygon_mask",
    "time_diameter_points",
    "validate_polygon",
]

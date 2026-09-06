"""Shared constants that do not affect scientific calculations."""

from aerosolstudio.config.branding import APP_SESSION_SOFTWARE

SESSION_SCHEMA_NAME = "aerosol_studio_roi_session"
SESSION_SCHEMA_VERSION = "2.0"
SESSION_SOFTWARE_NAME = APP_SESSION_SOFTWARE

DEFAULT_TIMEZONE_OFFSET_HOURS = 5.5
DEFAULT_TIMEZONE_NOTE = (
    "The canonical app currently applies the historical 5.5 hour NetCDF offset. "
    "Future refactors must make this explicit before changing timestamp behavior."
)

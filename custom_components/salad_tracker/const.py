"""Constants for the Salad Tracker integration."""

from __future__ import annotations

import logging

DOMAIN = "salad_tracker"
LOGGER = logging.getLogger(__package__)

API_BASE = "https://app-api.salad.com"

CONF_UPDATE_INTERVAL_MIN = "update_interval_min"
CONF_ENABLE_GPU_DEMAND = "enable_gpu_demand"

DEFAULT_UPDATE_INTERVAL_MIN = 5
DEFAULT_ENABLE_GPU_DEMAND = True

REQUEST_TIMEOUT = 30

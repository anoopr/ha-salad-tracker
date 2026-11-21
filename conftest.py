import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Pre-import so mock.patch string targets resolve even if another
# `custom_components` namespace sneaks onto sys.path from site-packages.
import custom_components.salad_tracker.coordinator as _coordinator  # noqa: E402,F401
import custom_components.salad_tracker.sensor as _sensor  # noqa: E402,F401
import custom_components.salad_tracker.config_flow as _config_flow  # noqa: E402,F401
import custom_components.salad_tracker.api as _api  # noqa: E402,F401

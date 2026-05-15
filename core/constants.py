"""Shared constants used across packages.

Centralised here to avoid hand-duplication that has drifted in the past
(`MADRID_TZ`, `LEAGUE_ID`, etc.). Import the symbol you need; don't redefine.
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

# Madrid timezone — all timestamps surfaced to the user (CSV `fecha`,
# admin panel "last updated", scheduled-job logs) are expected in this zone.
MADRID_TZ = ZoneInfo("Europe/Madrid")

# Biwenger league ID. Single value for now — if we ever need to operate
# multiple leagues, this becomes per-config.
LEAGUE_ID = "340703"

# A dynamic Drive file is considered stale if it hasn't been touched in
# this long. Surfaced as a red "is_stale" badge in the admin panel.
DRIVE_STALE_THRESHOLD = timedelta(days=7)

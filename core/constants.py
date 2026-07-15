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

# Stable user_id → real-name mapping for the Mochileros league. Biwenger
# lets users rename their team at will, so the team `name` field drifts;
# the numeric `id` is stable, so this is the source of truth when
# attributing a row to a real person (palmares, post-rollover reports).
# Per-season team names live in `palmares/{season}/standings_table` — don't
# duplicate them as comments here, they drift on every rollover.
LEAGUE_MEMBERS: dict[int, str] = {
    7728610: "Fabio",
    1376351: "Lucena",
    12449616: "Pablo",
    1372802: "Jorge",
    7728598: "Javi",
    7727371: "Ruben",
    13753285: "Manu",
}

# A dynamic Drive file is considered stale if it hasn't been touched in
# this long. Surfaced as a red "is_stale" badge in the admin panel.
DRIVE_STALE_THRESHOLD = timedelta(days=7)

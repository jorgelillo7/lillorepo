"""Constants shared across packages.

Only what genuinely crosses package boundaries lives here. League-specific
values (member ids, draft order) belong to the package that owns the league
— see `packages/biwenger_tools/constants.py` — because `_init` rides into
every service image, and a Chuck Norris bot has no business carrying a
Biwenger roster.
"""

from zoneinfo import ZoneInfo

# Madrid timezone — all timestamps surfaced to the user (CSV `fecha`,
# admin panel "last updated", scheduled-job logs) are expected in this zone.
MADRID_TZ = ZoneInfo("Europe/Madrid")

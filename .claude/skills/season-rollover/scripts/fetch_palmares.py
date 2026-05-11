"""
Fetch end-of-season palmares data from the Biwenger API and emit CSV rows.

Usage:
    python .claude/skills/season-rollover/scripts/fetch_palmares.py <season>

Example:
    python .claude/skills/season-rollover/scripts/fetch_palmares.py 25-26

Required env vars (same as scraper_job):
    BIWENGER_EMAIL, BIWENGER_PASSWORD, LEAGUE_ID

Outputs ready-to-paste CSV rows to stdout. Read-only — touches nothing in Biwenger.
"""

import os
import sys

# Allow running from repo root without installing packages.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../"))

from core.sdk.biwenger import (  # noqa: E402
    BiwengerClient,
    LOGIN_URL,
    ACCOUNT_URL,
    league_standings_url,
    clausulazos_url,
)


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python fetch_palmares.py <season>  (e.g. 25-26)")
        sys.exit(1)

    season = sys.argv[1]
    email = os.getenv("BIWENGER_EMAIL", "")
    password = os.getenv("BIWENGER_PASSWORD", "")
    league_id = os.getenv("LEAGUE_ID", "")

    if not all([email, password, league_id]):
        print(
            "ERROR: BIWENGER_EMAIL, BIWENGER_PASSWORD and LEAGUE_ID must be set.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        client = BiwengerClient(
            email=email,
            password=password,
            login_url=LOGIN_URL,
            account_url=ACCOUNT_URL,
            league_id=league_id,
        )
    except Exception as exc:
        print(f"ERROR: Biwenger authentication failed: {exc}", file=sys.stderr)
        print("You will need to fill in the palmares rows manually.", file=sys.stderr)
        sys.exit(1)

    rows = []

    # --- Standings (position, name, points) ---
    try:
        standings = client.get_standings_full(league_standings_url(league_id))
        if standings:
            # Sort by position ascending to be safe; API usually returns sorted.
            standings_sorted = sorted(
                standings, key=lambda u: u.get("position", 999)
            )
            if len(standings_sorted) >= 1:
                rows.append(f'{season},campeon,{standings_sorted[0]["name"]}')
                rows.append(
                    f'{season},puntuacion,{standings_sorted[0].get("points", "?")}'
                )
            if len(standings_sorted) >= 2:
                rows.append(f'{season},subcampeon,{standings_sorted[1]["name"]}')
            if len(standings_sorted) >= 3:
                rows.append(f'{season},tercero,{standings_sorted[2]["name"]}')
            if len(standings_sorted) >= 1:
                rows.append(f'{season},farolillo,{standings_sorted[-1]["name"]}')
        else:
            print("WARNING: standings returned empty.", file=sys.stderr)
    except Exception as exc:
        print(f"WARNING: Could not fetch standings: {exc}", file=sys.stderr)

    # --- Clausulazos total ---
    try:
        result = client.get_all_clausulazos(clausulazos_url(league_id))
        total = len(result.get("data", []))
        rows.append(f"{season},clausulazos_total,{total}")
    except Exception as exc:
        print(f"WARNING: Could not fetch clausulazos: {exc}", file=sys.stderr)

    # --- Manual fields (output placeholders) ---
    rows.append(f'{season},record_puntos,"RELLENAR — Jugador — X puntos (JY)"')
    rows.append(f'{season},jornadas_ganadas,"RELLENAR — Jugador — N jornadas"')
    rows.append(f"{season},multa,RELLENAR_O_BORRAR")
    rows.append(f"{season},sancion,RELLENAR_O_BORRAR")

    print("\n--- Paste the following rows into palmares.csv in Google Drive ---\n")
    for row in rows:
        print(row)
    print("\n--- End of rows ---")
    print(
        "\nNote: replace RELLENAR_O_BORRAR lines with real values, "
        "or delete them if not applicable."
    )


if __name__ == "__main__":
    main()

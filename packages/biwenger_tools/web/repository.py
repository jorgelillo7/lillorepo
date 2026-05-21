"""Firestore-backed reads for the web app.

This module holds only the ``firestore`` branch of the ``DATA_BACKEND``
feature flag. The legacy CSV/Drive reads stay inline in the route modules
(``routes/season.py``, ``routes/main.py``) until the flag is removed — that
keeps the existing CSV code, and the tests that patch it, untouched during
the migration.

Every function returns the same domain models the CSV path produces, so the
routes are backend-agnostic once they have the data. Collections mirror the
layout written by ``scripts/backfill_firestore.py`` and the scraper:

    comunicados/{season}/messages/{id_hash}
    participacion/{season}/authors/{autor}
    clausulazos/{season}/transfers/{id}
    tabla_justicia/{season}/teams/{equipo}
    palmares/{temporada}
"""

from datetime import datetime

from core.domain.models import (
    Clausulazo,
    JusticeEntry,
    LeagueMessage,
    Palmares,
    Participation,
    _parse_fecha,
)
from core.sdk import firestore


def _fecha_sort_key(fecha: str) -> datetime:
    """Naive datetime sort key for a display date string.

    Returns ``datetime.min`` when the value is empty or unparseable, and
    strips tzinfo so parsed and fallback values stay mutually comparable.
    """
    parsed = _parse_fecha(fecha)
    return parsed.replace(tzinfo=None) if parsed else datetime.min


def get_messages(season: str) -> list[LeagueMessage]:
    """All league messages for a season, most recent first.

    Firestore returns documents unordered; the scraper used to hand the web a
    pre-sorted CSV, so we re-sort here to preserve that contract.
    """
    docs = firestore.list_documents(f"comunicados/{season}/messages")
    messages = [LeagueMessage.from_firestore(doc_id, data) for doc_id, data in docs]
    messages.sort(key=lambda m: _fecha_sort_key(m.fecha), reverse=True)
    return messages


def get_participaciones(season: str) -> list[Participation]:
    """Participation aggregates for a season (unordered — the route sorts)."""
    docs = firestore.list_documents(f"participacion/{season}/authors")
    return [Participation.from_firestore(doc_id, data) for doc_id, data in docs]


def get_clausulazos(season: str) -> list[Clausulazo]:
    """Release-clause transfers for a season, most recent first."""
    docs = firestore.list_documents(f"clausulazos/{season}/transfers")
    clausulazos = [Clausulazo.from_firestore(doc_id, data) for doc_id, data in docs]
    clausulazos.sort(key=lambda c: _fecha_sort_key(c.fecha), reverse=True)
    return clausulazos


def get_tabla_justicia(season: str) -> list[JusticeEntry]:
    """Justice table for a season, ordered by attacks made (descending) —
    the same order the scraper wrote into the CSV."""
    docs = firestore.list_documents(f"tabla_justicia/{season}/teams")
    tabla = [JusticeEntry.from_firestore(doc_id, data) for doc_id, data in docs]
    tabla.sort(key=lambda e: e.total_hechos, reverse=True)
    return tabla


def get_palmares() -> list[Palmares]:
    """All historical honours (unordered — the route sorts by season)."""
    docs = firestore.list_documents("palmares")
    return [Palmares.from_firestore(doc_id, data) for doc_id, data in docs]

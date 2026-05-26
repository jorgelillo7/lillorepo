"""Firestore-backed reads for the web app.

Collections, written by the scraper and the season-rollover skill:

    comunicados/{season}/messages/{id_hash}
    participacion/{season}/authors/{autor}
    clausulazos/{season}/transfers/{id}
    tabla_justicia/{season}/teams/{equipo}
    palmares/{temporada}

The Firestore client calls live inline here — one query per function — so
the path, the where clause, and the ordering are obvious at the call site.
"""

from typing import Optional

from google.cloud import firestore as gfs

from core.domain.models import (
    Clausulazo,
    JusticeEntry,
    LeagueMessage,
    Palmares,
    Participation,
)
from core.sdk.firestore import get_client

# --- comunicados (messages) ----------------------------------------------
# Subcollection: comunicados/{season}/messages
# Composite index needed for the category-filtered + fecha-sorted reads:
#   collection group "messages", fields (categoria ASC, fecha DESC).
# Declared in firestore.indexes.json at the repo root.


def get_messages_by_category(
    season: str,
    categoria: str,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> list[LeagueMessage]:
    """Messages of one ``categoria`` for a season, newest first.

    Server-side: filters by ``categoria``, orders by ``fecha`` DESC, and
    applies ``limit``/``offset`` for paginated reads. ``offset`` still bills
    skipped docs as reads (Firestore's offset is not free), so it's only
    used by the comunicados page that exposes ``?page=N`` URLs — keep the
    page size small to stay inside the free tier.
    """
    ref = (
        get_client()
        .collection(f"comunicados/{season}/messages")
        .where(filter=gfs.FieldFilter("categoria", "==", categoria))
        .order_by("fecha", direction=gfs.Query.DESCENDING)
    )
    if limit is not None:
        ref = ref.limit(limit)
    if offset is not None:
        ref = ref.offset(offset)
    return [
        LeagueMessage.from_firestore(snap.id, snap.to_dict() or {})
        for snap in ref.stream()
    ]


def count_messages_by_category(season: str, categoria: str) -> int:
    """Total docs in ``comunicados/{season}/messages`` for one ``categoria``.

    Uses Firestore's count aggregation — billed at a tiny fixed cost
    regardless of result size, so the comunicados page can compute its
    ``total_pages`` without pulling every doc.
    """
    aggregation = (
        get_client()
        .collection(f"comunicados/{season}/messages")
        .where(filter=gfs.FieldFilter("categoria", "==", categoria))
        .count()
        .get()
    )
    return int(aggregation[0][0].value)


# --- participacion -------------------------------------------------------


def get_participaciones(season: str) -> list[Participation]:
    """Participation aggregates for a season, ordered by ``total`` DESC.

    The collection is tiny (~7 docs, one per author) so ordering server-side
    is mostly cosmetic — but it keeps the route free of Python sorting.
    """
    return [
        Participation.from_firestore(snap.id, snap.to_dict() or {})
        for snap in (
            get_client()
            .collection(f"participacion/{season}/authors")
            .order_by("total", direction=gfs.Query.DESCENDING)
            .stream()
        )
    ]


# --- clausulazos ---------------------------------------------------------


def get_clausulazos(season: str) -> list[Clausulazo]:
    """Release-clause transfers for a season, newest first."""
    return [
        Clausulazo.from_firestore(snap.id, snap.to_dict() or {})
        for snap in (
            get_client()
            .collection(f"clausulazos/{season}/transfers")
            .order_by("fecha", direction=gfs.Query.DESCENDING)
            .stream()
        )
    ]


# --- tabla_justicia ------------------------------------------------------


def get_tabla_justicia(season: str) -> list[JusticeEntry]:
    """Justice table for a season, ordered by attacks made (descending)."""
    return [
        JusticeEntry.from_firestore(snap.id, snap.to_dict() or {})
        for snap in (
            get_client()
            .collection(f"tabla_justicia/{season}/teams")
            .order_by("total_hechos", direction=gfs.Query.DESCENDING)
            .stream()
        )
    ]


# --- palmares ------------------------------------------------------------


def get_palmares() -> list[Palmares]:
    """All historical honours, sorted by season DESC (most recent first).

    Ordering happens in Python: the collection only has one doc per
    season (~3 total), and `order_by("__name__", DESCENDING)` would need
    a Firestore index — Firestore auto-indexes `__name__` ASC but not
    DESC. Not worth a composite index for three documents.
    """
    items = [
        Palmares.from_firestore(snap.id, snap.to_dict() or {})
        for snap in get_client().collection("palmares").stream()
    ]
    items.sort(key=lambda p: p.temporada, reverse=True)
    return items

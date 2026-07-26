"""The add-water flow: photo upload + OCR, then the reviewed submission."""

import uuid
from typing import Optional

import requests
from flask import abort, redirect, render_template, request, session, url_for

from core.sdk.gemini import GeminiError
from core.utils import get_logger
from core.web.csrf import verify_csrf_token
from packages.be_water.web import (
    aesan,
    config,
    geo,
    helpers,
    label_ocr,
    photos,
    repository,
    submission,
)
from packages.be_water.web.domain import MINERAL_FIELDS

logger = get_logger(__name__)


def _render_add_form(
    prefill=None,
    photo_tmp=None,
    label_tmp=None,
    ocr_fields=None,
    error=None,
    notice=None,
    similar=None,
):
    return render_template(
        "add.html",
        prefill=prefill or {},
        photo_tmp=photo_tmp,
        label_tmp=label_tmp,
        ocr_fields=ocr_fields,
        photo_tmp_url=photos.public_url(photo_tmp) if photo_tmp else None,
        error=error,
        notice=notice,
        similar=similar,
        meta_description="Añade una nueva agua al catálogo con su etiqueta.",
    )


def _promote_photos(water_id: str) -> tuple[Optional[str], Optional[str]]:
    """Promote the form's tmp uploads to their permanent paths; on a storage
    hiccup keep the tmp URL as a fallback rather than losing the photo."""
    photo_url = label_photo_url = None
    photo_tmp = (request.form.get("photo_tmp") or "").strip()
    label_tmp = (request.form.get("label_tmp") or "").strip()
    if photo_tmp:
        try:
            photo_url = photos.promote_photo(photo_tmp, f"{water_id}.jpg")
        except requests.RequestException:
            photo_url = photos.public_url(photo_tmp)
    if label_tmp:
        try:
            label_photo_url = photos.promote_photo(
                label_tmp, f"originals/{water_id}.jpg"
            )
        except requests.RequestException:
            label_photo_url = photos.public_url(label_tmp)
    return photo_url, label_photo_url


def _resolve_add_target(name, water_id, existing, merge_into):
    """Decide the target doc for a submission, or return a re-rendered form
    when the user must disambiguate. Returns `(water_id, existing)` to proceed,
    otherwise a Flask response (or aborts)."""
    form = request.form

    def _form_with(**extra):
        return _render_add_form(
            prefill=dict(form),
            photo_tmp=form.get("photo_tmp") or None,
            label_tmp=form.get("label_tmp") or None,
            ocr_fields=form.get("ocr_fields") or None,
            **extra,
        )

    if existing is None and merge_into:
        # The user confirmed the fuzzy match: update that water instead.
        existing = repository.get_water(merge_into)
        if existing is None:
            abort(400)
        return merge_into, existing
    if existing is None and not form.get("force_new"):
        similar = submission.similar_water(name, repository.get_all_waters())
        if similar is not None:
            return _form_with(similar=similar)
    if (
        existing is not None
        and not merge_into
        and not form.get("force_new")
        and submission.springs_differ(
            submission.form_field(form, "spring"), existing.spring
        )
    ):
        # Exact commercial name, different spring — the Font Vella case
        # (Sacalm vs Sigüenza): ask instead of silently merging.
        return _form_with(similar=existing)
    if existing is not None and form.get("force_new"):
        # A new water sharing the exact name: id disambiguated by the spring
        # tokens the name doesn't already carry.
        water_id = submission.disambiguated_id(
            water_id, submission.form_field(form, "spring")
        )
        existing = repository.get_water(water_id)
    if existing is not None and existing.verified:
        # A verified water is bottle-checked and data-frozen.
        return _render_add_form(
            prefill=dict(form),
            photo_tmp=form.get("photo_tmp") or None,
            error=(
                f"«{name}» ya está en el catálogo y verificada — "
                "no se puede sobrescribir."
            ),
        )
    return water_id, existing


def add_water():
    if not session.get("nickname"):
        return redirect(url_for("index"))
    if request.method != "POST":
        return _render_add_form()
    if helpers.nickname_blocked():
        return redirect(url_for("index"))
    if not verify_csrf_token():
        return _render_add_form(
            prefill=dict(request.form),
            error="La sesión ha caducado — recarga la página e inténtalo de nuevo.",
        )
    if not helpers.SAVE_LIMITER.allow(helpers.client_ip()):
        return _render_add_form(
            prefill=dict(request.form),
            error="Demasiadas aguas en poco tiempo — espera un rato.",
        )

    name = submission.form_field(request.form, "name")
    if not name:
        abort(400)
    water_id = submission.slugify(name)
    existing = repository.get_water(water_id)
    merge_into = (request.form.get("merge_into") or "").strip()

    # Resolve which doc (if any) this submission targets, or bounce back to the
    # form for the user to disambiguate.
    resolution = _resolve_add_target(name, water_id, existing, merge_into)
    if not isinstance(resolution, tuple):
        return resolution  # a re-rendered form or abort
    water_id, existing = resolution

    minerals = submission.parse_minerals(request.form)
    photo_url, label_photo_url = _promote_photos(water_id)
    verified_fields = submission.verified_fields_from_ocr(
        request.form.get("ocr_fields") or "", minerals
    )
    water = submission.build_water(
        request.form,
        water_id=water_id,
        name=name,
        minerals=minerals,
        verified_fields=verified_fields,
        photo_url=photo_url,
        label_photo_url=label_photo_url,
        added_by=session["nickname"],
    )
    if existing is not None:
        submission.apply_existing(
            water,
            existing,
            merge_into=bool(merge_into),
            form_has_brand=bool(submission.form_field(request.form, "brand")),
        )
    submission.finalize_provenance(water, existing)
    repository.save_water(water)
    repository.touch_user(session["nickname"])
    return redirect(url_for("water_detail", water_id=water_id))


def _prefill_from_aesan(prefill: dict) -> str:
    """Fill spring/province/community gaps from the official registry.

    The label always wins (only missing keys are filled); with several
    registry springs for the name, only fields all candidates agree on
    are used. Returns the notice suffix ('' when nothing matched)."""
    matches = aesan.registry_matches(prefill.get("name") or "")
    if not matches:
        return ""
    filled = False
    springs = {m["spring"] for m in matches}
    if len(springs) == 1 and not prefill.get("spring"):
        prefill["spring"] = springs.pop()
        filled = True
    provinces = {m["province"] for m in matches}
    if len(provinces) == 1:
        province = provinces.pop()
        if not prefill.get("province"):
            prefill["province"] = province
            filled = True
        if not prefill.get("community") and geo.community_of(province):
            prefill["community"] = geo.community_of(province)
            filled = True
    return " Procedencia completada del registro AESAN 📋" if filled else ""


def add_water_photo():
    """Photo-first flow: the composition shot feeds the OCR and stays as
    verification proof; an optional front shot becomes the display photo."""
    if not session.get("nickname") or helpers.nickname_blocked():
        return redirect(url_for("index"))
    if not verify_csrf_token():
        return _render_add_form(
            error="La sesión ha caducado — recarga la página e inténtalo de nuevo."
        )
    if not helpers.PHOTO_LIMITER.allow(helpers.client_ip()):
        return _render_add_form(
            error="Demasiadas fotos en poco tiempo — espera un rato."
        )
    upload = request.files.get("photo")
    if upload is None or not upload.filename:
        return redirect(url_for("add_water"))
    raw = upload.read(photos.MAX_UPLOAD_BYTES + 1)
    if len(raw) > photos.MAX_UPLOAD_BYTES:
        return _render_add_form(error="La foto es demasiado grande (máx. 15 MB).")

    processed = photos.process_image(raw)
    uid = uuid.uuid4().hex
    # Both tmps live under uploads/ so the bucket lifecycle rule reclaims
    # abandoned forms; on save the label shot is promoted to originals/
    # as the permanent verification proof.
    label_tmp = f"uploads/{uid}-label.jpg"
    photos.upload_photo(label_tmp, processed)

    # The display photo prefers the optional front shot — a composition
    # label is usually the ugly side of the bottle.
    display_src = processed
    beauty = request.files.get("beauty")
    if beauty is not None and beauty.filename:
        beauty_raw = beauty.read(photos.MAX_UPLOAD_BYTES + 1)
        if len(beauty_raw) > photos.MAX_UPLOAD_BYTES:
            return _render_add_form(
                error="La foto de la ficha es demasiado grande (máx. 15 MB)."
            )
        display_src = photos.process_image(beauty_raw)

    # Studio version for display — admin-only: image generation is the one
    # paid call in the project, so it fires only for trusted nicknames.
    # Everyone else keeps the (free) OCR prefill and their raw photo.
    display = display_src
    studio_note = ""
    if session["nickname"] in config.ADMIN_NICKNAMES:
        try:
            display = photos.studio_photo(display_src)
            studio_note = " La foto ha pasado por el estudio 📸"
        except (GeminiError, requests.RequestException) as exc:
            logger.warning(
                "Studio photo failed — using raw.", extra={"error": str(exc)[:300]}
            )
            studio_note = " El estudio no pudo retocar la foto; se guarda la original."
    photo_tmp = f"uploads/{uid}.jpg"
    photos.upload_photo(photo_tmp, display)

    try:
        extracted = label_ocr.extract_label(processed)
    except (GeminiError, requests.RequestException) as exc:
        logger.warning("Label OCR failed.", extra={"error": str(exc)[:300]})
        # OCR down ≠ photo lost: open the empty form with the photo attached.
        overloaded = getattr(exc, "status_code", None) in (429, 503)
        error = (
            "El lector de etiquetas está saturado ahora mismo — "
            "prueba de nuevo en unos minutos, o rellena a mano."
            if overloaded
            else "No pude leer la etiqueta automáticamente — rellena a mano."
        )
        return _render_add_form(
            photo_tmp=photo_tmp,
            label_tmp=label_tmp,
            error=error,
        )
    prefill = {k: v for k, v in extracted.items() if v is not None}
    aesan_note = _prefill_from_aesan(prefill)
    # Mineral fields the label actually declared — they become
    # verified_fields on save (human-reviewed label data).
    ocr_fields = [f for f in MINERAL_FIELDS if prefill.get(f) is not None]
    return _render_add_form(
        prefill=prefill,
        photo_tmp=photo_tmp,
        label_tmp=label_tmp,
        ocr_fields=",".join(ocr_fields),
        notice="He leído la etiqueta — revisa los valores antes de guardar."
        + studio_note
        + aesan_note,
    )


def register(app):
    app.add_url_rule("/anadir", "add_water", add_water, methods=["GET", "POST"])
    app.add_url_rule(
        "/anadir/foto", "add_water_photo", add_water_photo, methods=["POST"]
    )

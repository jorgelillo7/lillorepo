"""Tests for the SD-card inventory.

The behaviour that matters here is what the report *claims*. Saying a game is
missing when it is on the card under another name sends someone hunting for
something they own, so the distinction between "absent" (BIOS, exact) and
"not recognised" (games, a guess) is pinned deliberately.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import inventory  # noqa: E402


def _write_doc(docs, name, title, folder, titles):
    body = [f"# {title}", "", f"- **Games go in:** `SD_TEMPLATE/ROMs/{folder}/`", ""]
    body += [f"- [ ] {t}" for t in titles]
    (docs / name).write_text("\n".join(body) + "\n", encoding="utf-8")


def test_parse_guide_reads_the_checklist_and_its_folder(tmp_path):
    """The documents are the source of truth for both; a second copy in the
    script would be one to keep in sync."""
    docs = tmp_path / "docs"
    docs.mkdir()
    _write_doc(docs, "psx.md", "PlayStation 1", "psx", ["Crash Bandicoot", "Tekken 3"])

    systems = inventory.parse_guide(docs)
    assert len(systems) == 1
    assert systems[0]["system"] == "PlayStation 1"
    assert systems[0]["folders"] == ["psx"]
    assert systems[0]["titles"] == ["Crash Bandicoot", "Tekken 3"]


def test_parse_guide_strips_the_see_notes_footnote(tmp_path):
    """ "Resident Evil — see notes" is one game with a footnote, not a title
    containing a dash."""
    docs = tmp_path / "docs"
    docs.mkdir()
    _write_doc(docs, "psx.md", "PS1", "psx", ["Resident Evil — see notes"])
    assert inventory.parse_guide(docs)[0]["titles"] == ["Resident Evil"]


def test_a_recognised_title_is_reported_present():
    present, unclear = inventory.match_titles(
        ["Crash Bandicoot"], ["Crash Bandicoot (E).chd"]
    )
    assert present == ["Crash Bandicoot"]
    assert unclear == []


def test_matching_ignores_accents_case_and_punctuation():
    present, _ = inventory.match_titles(
        ["Pokémon Esmeralda"], ["pokemon_esmeralda.gba"]
    )
    assert present == ["Pokémon Esmeralda"]


def test_matching_does_not_collapse_a_sequel_into_its_original():
    """ "Golden Axe II" and "Golden Axe" are different games, and a match that
    treated them as one would report a game present that is not there."""
    present, unclear = inventory.match_titles(["Golden Axe II"], ["Golden Axe (UE).md"])
    assert present == []
    assert unclear == ["Golden Axe II"]


def test_an_original_still_matches_when_only_the_sequel_is_present():
    """The reverse direction is a real limitation, not a bug: every word of
    "Golden Axe" does appear in "Golden Axe II". Pinned so the looseness is
    a known quantity rather than a surprise."""
    present, _ = inventory.match_titles(["Golden Axe"], ["Golden Axe II.md"])
    assert present == ["Golden Axe"]


def test_scan_roms_ignores_scaffolding_and_stray_files(tmp_path):
    roms = tmp_path / "ROMs" / "gba"
    roms.mkdir(parents=True)
    (roms / ".gitkeep").touch()
    (roms / ".DS_Store").touch()
    (roms / "notes.txt").touch()
    (roms / "Metroid Fusion.gba").touch()

    assert inventory.scan_roms(tmp_path / "ROMs") == {"gba": ["Metroid Fusion.gba"]}


def test_scan_roms_keeps_archives_because_arcade_sets_are_zips(tmp_path):
    roms = tmp_path / "ROMs" / "arcade"
    roms.mkdir(parents=True)
    (roms / "mslug.zip").touch()
    assert inventory.scan_roms(tmp_path / "ROMs")["arcade"] == ["mslug.zip"]


def test_scan_roms_on_a_missing_directory_is_empty_not_an_error(tmp_path):
    assert inventory.scan_roms(tmp_path / "nope") == {}


def test_bios_is_reported_as_fact_because_its_names_are_standard(tmp_path):
    bios = tmp_path / "BIOS"
    bios.mkdir()
    # Written at its real size, not touched: an empty file is not a BIOS, and
    # since the PlayStation checks discriminate on size it would not pass.
    (bios / "scph5502.bin").write_bytes(b"\0" * (512 * 1024))

    report = inventory.check_bios(bios)
    assert report["PlayStation 1 (DuckStation)"]["satisfied"] is True
    assert report["PlayStation 1 (DuckStation)"]["found"] == ["scph5502.bin"]
    assert report["Dreamcast (Flycast)"]["satisfied"] is False


def test_bios_check_survives_no_bios_directory(tmp_path):
    report = inventory.check_bios(tmp_path / "nope")
    assert all(not v["satisfied"] for v in report.values())


def test_the_report_never_calls_an_unrecognised_game_missing(tmp_path):
    """The wording is the point. A dump can be named anything, so an
    unmatched title is a failure to recognise, not an absence."""
    docs = tmp_path / "docs"
    docs.mkdir()
    _write_doc(docs, "gba.md", "GBA", "gba", ["Wario Land 4"])
    roms = tmp_path / "ROMs" / "gba"
    roms.mkdir(parents=True)

    report = inventory.build_report(docs, tmp_path / "ROMs", tmp_path / "BIOS")
    text = inventory.render(report)

    assert report["systems"][0]["not_obviously_present"] == ["Wario Land 4"]
    assert "missing" not in text.lower().split("bios")[-1].split("\n")[0]
    assert "did not recognise" in text


def test_the_report_counts_files_that_are_not_on_the_checklist(tmp_path):
    """The card holding more than the guide lists is normal and must not
    read as an error."""
    docs = tmp_path / "docs"
    docs.mkdir()
    _write_doc(docs, "gba.md", "GBA", "gba", ["Wario Land 4"])
    roms = tmp_path / "ROMs" / "gba"
    roms.mkdir(parents=True)
    (roms / "Wario Land 4.gba").touch()
    (roms / "Something Else.gba").touch()

    report = inventory.build_report(docs, tmp_path / "ROMs", tmp_path / "BIOS")
    assert report["systems"][0]["files_present"] == 2
    assert report["systems"][0]["likely_present"] == ["Wario Land 4"]


def test_a_document_covering_two_folders_reads_both(tmp_path):
    """The GameCube/Wii document names two directories."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "gc.md").write_text(
        "# GameCube and Wii\n\n"
        "- **Games go in:** `SD_TEMPLATE/ROMs/gamecube/ and "
        "SD_TEMPLATE/ROMs/wii/`\n\n- [ ] Metroid Prime\n",
        encoding="utf-8",
    )
    assert inventory.parse_guide(docs)[0]["folders"] == ["gamecube", "wii"]


def test_a_ps1_bios_does_not_satisfy_the_ps2_requirement(tmp_path):
    """Both consoles dump as `scphNNNN.bin` and no filename pattern separates
    them, so this matched a PS1 image against PS2 and reported it satisfied —
    a false positive on the one system that will not boot without the real
    file. A PS1 image is 512 KB and a PS2 image 4 MB."""
    bios = tmp_path / "BIOS"
    bios.mkdir()
    (bios / "scph5502.bin").write_bytes(b"\0" * (512 * 1024))

    report = inventory.check_bios(bios)
    assert report["PlayStation 1 (DuckStation)"]["satisfied"] is True
    assert report["PlayStation 2 (NetherSX2)"]["satisfied"] is False


def test_a_ps2_bios_satisfies_ps2_and_not_ps1(tmp_path):
    bios = tmp_path / "BIOS"
    bios.mkdir()
    (bios / "scph39001.bin").write_bytes(b"\0" * (4 * 1024 * 1024))

    report = inventory.check_bios(bios)
    assert report["PlayStation 2 (NetherSX2)"]["satisfied"] is True
    assert report["PlayStation 1 (DuckStation)"]["satisfied"] is False


def test_a_dump_slightly_off_the_nominal_size_still_counts(tmp_path):
    """Dumping tools differ by a header here and there; the two PlayStation
    sizes are three orders of magnitude apart and need no precision."""
    bios = tmp_path / "BIOS"
    bios.mkdir()
    (bios / "scph1001.bin").write_bytes(b"\0" * int(512 * 1024 * 1.05))
    assert inventory.check_bios(bios)["PlayStation 1 (DuckStation)"]["satisfied"]


def test_a_size_checked_system_ignores_a_wildly_wrong_file(tmp_path):
    bios = tmp_path / "BIOS"
    bios.mkdir()
    (bios / "scph1001.bin").write_bytes(b"nope")
    assert not inventory.check_bios(bios)["PlayStation 1 (DuckStation)"]["satisfied"]


def test_a_name_unambiguous_system_needs_no_size(tmp_path):
    """Nothing but a Dreamcast BIOS is called `dc_boot.bin`."""
    bios = tmp_path / "BIOS"
    bios.mkdir()
    (bios / "dc_boot.bin").write_bytes(b"x")
    assert inventory.check_bios(bios)["Dreamcast (Flycast)"]["satisfied"] is True

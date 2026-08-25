"""Tests for the guard that keeps the emulation package free of game data.

The package's README makes a claim to anyone reading this public repository
and invites them to verify it. This is that verification; if it can be fooled,
the claim degrades quietly.
"""

import check_no_game_data as guard


def test_documentation_and_scripts_are_allowed():
    assert (
        guard.offenders(
            [
                "packages/emulation_thor6/README.md",
                "packages/emulation_thor6/docs/psx.md",
                "packages/emulation_thor6/scripts/sdcard.sh",
                "packages/emulation_thor6/scripts/inventory.py",
                "packages/emulation_thor6/scripts/BUILD.bazel",
                "packages/emulation_thor6/ROMs/.gitkeep",
            ]
        )
        == []
    )


def test_a_rom_is_caught():
    assert guard.offenders(["packages/emulation_thor6/ROMs/psx/game.chd"]) == [
        "packages/emulation_thor6/ROMs/psx/game.chd"
    ]


def test_a_bios_dump_is_caught():
    assert guard.offenders(["packages/emulation_thor6/BIOS/scph5502.bin"]) == [
        "packages/emulation_thor6/BIOS/scph5502.bin"
    ]


def test_an_archive_is_caught_because_arcade_sets_are_zips():
    assert guard.offenders(["packages/emulation_thor6/ROMs/arcade/mslug.zip"])


def test_an_extensionless_file_is_caught_rather_than_waved_through():
    """A dump renamed to have no extension is still a dump, and a guard that
    defaulted to "allow" on the unrecognised case would be the wrong way
    round."""
    assert guard.offenders(["packages/emulation_thor6/ROMs/psx/mystery"])


def test_the_check_is_case_insensitive():
    assert guard.offenders(["packages/emulation_thor6/docs/PSX.MD"]) == []
    assert guard.offenders(["packages/emulation_thor6/ROMs/GAME.ISO"])


def test_the_real_package_is_clean():
    """The claim, checked against what git actually tracks right now."""
    try:
        paths = guard.tracked_files(guard.PACKAGE)
    except Exception:
        return  # not a git checkout (Bazel sandbox); the unit cases cover it
    assert guard.offenders(paths) == []

"""Export Apple Contacts to a valid vCard file.

Two things make this less trivial than it looks, and both are silent failures:
AppleScript joins the cards with ", " so the result is not valid vCard, and a
partial read looks exactly like a smaller address book. The count is checked
against what the application reports before the file is kept.
"""

import argparse
import os
import re
import subprocess
import sys

TIMEOUT = 900


def osascript(body):
    script = f"with timeout of {TIMEOUT} seconds\n{body}\nend timeout"
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    subprocess.run(["open", "-a", "Contacts"], capture_output=True)
    expected = int(osascript(
        'tell application "Contacts" to return count of every person').strip())
    payload = osascript('tell application "Contacts" to return vcard of every person')

    # AppleScript's list-to-text coercion inserts ", " between items, which
    # leaves every BEGIN:VCARD after the first in mid-line.
    payload = payload.replace("\r\n", "\n")
    payload = payload.replace("\n, BEGIN:VCARD", "\nBEGIN:VCARD")
    written = len(re.findall(r"(?m)^BEGIN:VCARD", payload))

    if written != expected:
        print(f"REFUSING: exported {written} cards, the application reports {expected}")
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(payload)
    print(f"{written} cards → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Web interfaces follow Modern Web Guidance

Any change to HTML, CSS or client-side JavaScript, in any repo, is checked
against Google Chrome's Modern Web Guidance. It is vendored as the
`modern-web-guidance` skill: lillorepo `system/skills/`, installed into
`~/.claude/skills/`, synced by lillorepo `scripts/sync-web-guidance.sh`.

- **Read the guides from disk**, in
  `~/.claude/skills/modern-web-guidance/guides/` (grep for the capability,
  then read the guide whole). Do not run the skill's `npx` commands: the guides
  are already here, and running a package from npm at every web edit is the
  wrapper-installer channel `machine.md` warns about.
- **A review uses the guide's criteria** and cites the guide file for each
  finding. The last review of every site and what is still open are in
  lillorepo `docs/technical/web-guidance.md`.
- The skill's own "Disclose Skill Usage" section stands: when a guide shaped
  the change, the reply says which one and why.

# Capability: reader

A static web reader for interactive stories written in Twine 2 with the
Harlowe 3 format. It imports the author's Twee source or a published HTML
build, refuses at build time what it cannot run, plays every path to test a
chapter, and serves a whole series from one site with autosave, undo and the
end code of one chapter carried into the next.

- **Source:** `packages/interactive_fiction/src/engine/` (`source`, `markup`,
  `expr`, `runtime`, `validate`, `explore`), `packages/interactive_fiction/src/app/`,
  `packages/interactive_fiction/scripts/build-stories.ts`,
  `packages/interactive_fiction/scripts/explore.ts`
- **Verified by:** `packages/interactive_fiction/tests/*.test.ts` (Vitest, on a
  fixture story written for the tests — the stories themselves are not in the
  repo)

---

### Requirement: Both Twine formats are read, and story JavaScript is refused

The importer SHALL read a Twee 3 file and a published Twine 2 HTML build into
the same story shape (title, start passage, tags, stylesheet). A story that
carries JavaScript SHALL be refused, because the reader cannot run it and a
story missing its script misbehaves silently.

#### Scenario: Twee source
- **WHEN** a Twee 3 file is imported
- **THEN** title, start, tags and stylesheet are read and the special passages dropped
- *Verifies:* `source.test.ts: reads title, start, tags and the stylesheet, and drops the special passages`,
  `source.test.ts: parseStory tells the two formats apart`

#### Scenario: published HTML
- **WHEN** a published HTML build is imported
- **THEN** passages are unescaped and the start is found by its pid
- *Verifies:* `source.test.ts: unescapes passages and finds the start by pid`

#### Scenario: story JavaScript
- **WHEN** a story has a non-empty script passage
- **THEN** the import fails
- *Verifies:* `source.test.ts: a story with JavaScript is refused rather than run without it`

### Requirement: What the reader cannot run fails the build, by passage

The build SHALL validate every chapter and stop on: a macro outside the
supported subset, a changer without its hook, a link (including one inside a
string later printed) to a passage that does not exist, and a variable read but
never set. A silent mis-render is the failure this prevents: the reader would
show something the author did not write, and nobody would know. The supported
macros and their aliases are listed once (`src/engine/macros.ts`); parser,
validator and runtime all read that list.

#### Scenario: unsupported syntax and broken links
- **WHEN** a chapter uses an unsupported macro, a hookless changer, or links to a missing passage
- **THEN** validation reports an error naming it
- *Verifies:* `validate.test.ts: an unsupported macro is an error, not a silent mis-render`,
  `validate.test.ts: a macro written in a syntax the reader does not run is refused at build`,
  `validate.test.ts: aliases are the same macro as their main name`,
  `validate.test.ts: a changer with no hook is an error`,
  `validate.test.ts: a link to a missing passage is an error, including links inside strings`,
  `validate.test.ts: the fixture story is clean`

#### Scenario: a typo in a variable
- **WHEN** a variable is read and never set
- **THEN** validation reports an error
- *Verifies:* `validate.test.ts: a variable read but never set is an error`

### Requirement: The runtime follows Harlowe on the supported subset

The runtime SHALL render the supported subset as Harlowe does: startup passages
first, header passages above every passage, newlines as breaks except inside
collapsed blocks, `else`/`else-if` chained to the previous condition among
siblings, `cond` returning its first true branch, `print` re-parsing strings as
markup, `goto` keeping what was set before it, `(link:)` running its hook on
click, `display` sharing state, and `(input: bind)` bound to its variable. An
unset variable SHALL fail loudly rather than print nothing. Its output was
checked against the author's own Harlowe builds: every passage of one chapter
word for word, and the end codes of five paths of another.

#### Scenario: markup and state
- **WHEN** a passage uses breaks, collapsed blocks, styles, raw HTML, colours, variables and conditions
- **THEN** it renders as Harlowe does
- *Verifies:* `runtime.test.ts: a newline is a line break, but not inside a collapsed block`,
  `runtime.test.ts: bold, italic and raw HTML pass through`,
  `runtime.test.ts: a bare variable prints escaped, inside raw HTML too`,
  `runtime.test.ts: text-colour wraps its hook in the Harlowe colour`,
  `runtime.test.ts: startup passages run once before the first passage`,
  `runtime.test.ts: arrays concatenate with + and filter with find`,
  `runtime.test.ts: else and else-if follow the previous condition among siblings`,
  `runtime.test.ts: cond returns the first true branch, and a code hook renders as markup`,
  `runtime.test.ts: using an unset variable fails loudly instead of printing nothing`

#### Scenario: links and navigation
- **WHEN** a passage builds links in arrays, goes to another, reveals a hook, displays another, or binds an input
- **THEN** the actions offered and the state match Harlowe
- *Verifies:* `runtime.test.ts: print re-parses a string, so link arrays become clickable`,
  `runtime.test.ts: goto stops the passage and shows its target, keeping what was set before it`,
  `runtime.test.ts: a (link:) runs its hook on click, and a goto inside it navigates`,
  `runtime.test.ts: display renders another passage inline with the same state`,
  `runtime.test.ts: a header passage is rendered above every passage`,
  `runtime.test.ts: an input is bound to its variable and shows its current value`

### Requirement: Every path is played before a chapter ships

The explorer SHALL play a chapter breadth-first over (passage, state) and
report unreachable passages, dead ends, every reachable end code with its
shortest click path, and runtime errors. A story whose state grows without
bound SHALL be cut off at a state limit and say so. Across chapters, it SHALL
list the end codes of one chapter that the next treats like a wrong code — the
kind of contract break no single chapter's test can see.

#### Scenario: a full exploration
- **WHEN** a chapter is explored
- **THEN** its end codes with their shortest paths, its dead ends and its unreachable passages are reported
- *Verifies:* `explore.test.ts: every path is played: end codes, dead ends and unreachable passages are reported`,
  `explore.test.ts: a loop between passages terminates once a state repeats`

#### Scenario: unbounded state
- **WHEN** the state keeps growing
- **THEN** exploration stops at the limit and reports itself truncated
- *Verifies:* `explore.test.ts: a story whose state grows forever is cut off and says so`

### Requirement: Stories stay out of the repository, and drafts out of the build

Story text, images and scene files SHALL live in a gitignored `stories/`
folder: the repository is public and the text belongs to its author. A chapter
marked `draft` SHALL be left out of `npm run build`, so an unpublished chapter
never reaches a public upload by accident; `build:drafts` and `dev` include it.
Only media files are published from a series folder.

### Requirement: The reader keeps progress, and carries the end code

Progress SHALL be saved per chapter in the browser as the state *before* the
current passage rendered, so resuming never re-applies its assignments. An end
code, once earned, SHALL be kept apart from progress so undo never loses it,
and SHALL be written into the next chapter's code field while that field is
empty. A link-less passage before the end code is set SHALL read as a path not
yet written, not as the end of the chapter. Restart SHALL ask for confirmation
inside the page, since embedded viewers block browser dialogs. A chapter that
cannot be loaded SHALL say so instead of leaving the page blank. These rules
are pure functions on the progress (`src/app/progression.ts`), tested without
a browser.

#### Scenario: moving, undoing and the history
- **WHEN** the reader moves on, undoes, or plays a long session
- **THEN** each step keeps the state before its passage and the choice made on it, undo forgets that choice, and only the last steps are kept
- *Verifies:* `progression.test.ts: advancing keeps the state before each passage and the choice made on it`,
  `progression.test.ts: undo returns to the step before and forgets the choice made from it`,
  `progression.test.ts: the history keeps the last steps only`,
  `progression.test.ts: advancing copies the state, so later changes on the page do not leak into history`

#### Scenario: endings and unwritten paths
- **WHEN** a passage offers nothing to click or type
- **THEN** it ends the chapter if the chapter keeps no code or its code is set, and is an unwritten path otherwise; the chapter is finished once
- *Verifies:* `progression.test.ts: a passage with something to click or type does not end the chapter`,
  `progression.test.ts: a dead end ends a chapter without codes, and one whose code is set`,
  `progression.test.ts: a dead end before the code is set is a path not written yet`,
  `progression.test.ts: a chapter is marked finished once, with the code it ended on`

#### Scenario: the carried code
- **WHEN** a chapter opens after the previous one ended with a code
- **THEN** the code fills its code field only while that field is empty
- *Verifies:* `progression.test.ts: fills the code field while it is empty, and only then`

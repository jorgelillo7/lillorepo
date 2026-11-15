# Interactive Fiction — Release Notes

What changed in the reader, newest first. The stories have their own history, in their author's repository. 📖

### **One Gate Before Every Deploy (15 November 2026)**

Nothing a reader sees changed.

* **🚦 Nothing ships unchecked**: a deploy now builds the site, plays every path of every chapter, compares every page with the author's own Twine build and clicks through to every ending in a real browser — and stops if any of it fails.
* **🔎 The live site is checked after the upload**: the chapters, their versions and the security headers online must be the ones just built.

### **Saves That Survive a Rewrite (12 November 2026)**

Nothing in the story changed. The reader got safer to publish and kinder when a chapter is edited after someone started it.

* **💾 A rewritten chapter no longer breaks a save**: every save records the version of the chapter it was made in. If the passage it points at is gone, the reader says the chapter changed and offers to start that chapter again; the other chapters, the codes and the discoveries stay.
* **🗣️ Every new passage is announced**: focus moves to the passage and a screen reader says how it opens.
* **🚦 Only what the author published goes out**: publishing stops unless the story's copy is the author's published branch, clean and up to date. A deliberate preview needs an explicit switch.
* **🛡️ Served with a content policy**: the site loads only its own files and cannot be shown inside another site's frame.

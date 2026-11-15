# Interactive Fiction — Release Notes

What changed in the reader, newest first. The stories have their own history, in their author's repository. 📖

### **Pictures Five Times Lighter (15 November 2026)**

The scenes look the same and arrive much sooner, on a phone most of all.

* **🖼️ Every picture in a modern format**: scenes, the title and the pictures inside the text are served as AVIF or WebP at the size your screen needs. All the pictures of both chapters weigh 1.8 MB instead of 8.7 MB; the first room of chapter 1 went from 249 KB to 32 KB on a phone.
* **📐 Nothing jumps while loading**: each picture's place is reserved before it arrives.

### **One Gate Before Every Deploy (15 November 2026)**

Nothing a reader sees changed.

* **🚦 Nothing ships unchecked**: a deploy now builds the site, plays every path of every chapter, compares every page with the author's own Twine build and clicks through to every ending in a real browser — and stops if any of it fails.
* **🔎 The live site is checked after the upload**: the chapters, their versions and the security headers online must be the ones just built.

### **The 3D Preview Keeps Drafts In (15 November 2026)**

Nothing a reader sees changed.

* **🚦 An unpublished chapter cannot reach the 3D preview**: the preview refuses to be prepared while a draft chapter is in the build, and its deploy rebuilds from what the author published first.

### **Saves That Survive a Rewrite (12 November 2026)**

Nothing in the story changed. The reader got safer to publish and kinder when a chapter is edited after someone started it.

* **💾 A rewritten chapter no longer breaks a save**: every save records the version of the chapter it was made in. If the passage it points at is gone, the reader says the chapter changed and offers to start that chapter again; the other chapters, the codes and the discoveries stay.
* **🗣️ Every new passage is announced**: focus moves to the passage and a screen reader says how it opens.
* **🚦 Only what the author published goes out**: publishing stops unless the story's copy is the author's published branch, clean and up to date. A deliberate preview needs an explicit switch.
* **🛡️ Served with a content policy**: the site loads only its own files and cannot be shown inside another site's frame.

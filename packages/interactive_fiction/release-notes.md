# Interactive Fiction — Release Notes

What changed in the reader, newest first. The stories have their own history, in their author's repository. 📖

### **Easier to Follow Without Seeing It (15 November 2026)**

The reader and the 3D preview, after a check against Chrome's Modern Web Guidance.

* **🧭 Focus lands where the page starts**: moving to the index, the credits or the achievements puts a keyboard or screen reader on the page's title.
* **🔗 Sharing says what happened**: "Enlace copiado" shows under the buttons and goes away; if the link cannot be copied, it is shown, selected, to copy by hand.
* **🖼️ Lighter pictures on big phones, and the index's at once**: a new 1280 px size, and the first chapter pictures of the index load straight away in a modern format.
* **🌑 Dark from the first frame**: the site and its link pages tell the browser they are dark, so nothing flashes white, and a link to the site is titled with the series.
* **🫨 Less motion keeps the fades**: with reduced motion on, nothing moves, but colours and fades still change gently.
* **📶 The 3D preview's loading bar is a real one**: a screen reader hears it, and it keeps moving when the server does not say how big a room is.
* **⚡ Faster repeat visits**: the site's scripts, styles and fonts are kept by the browser for a year; a new version gets new names.

### **The 3D Preview Loads a Third Lighter (15 November 2026)**

For the 3D preview only; the reader is unchanged.

* **⚡ A room without its scaffolding**: where each thing to touch sits is now worked out before publishing, so a room downloads 8.3 MB instead of 12.8 MB, and the preview as a whole is 65 MB smaller.
* **📶 Loading you can see**: the title shows how much of the first room has arrived, and so does the fade between rooms.
* **🔁 Nothing downloaded twice**: a room already seen is kept by the browser until it actually changes.
* **🔊 Sound, and a way to turn it off**: stings, steps and the heartbeat as in the reader, and a mute switch in the corner.
* **🎥 A steadier look around**: the view glides to where you turn it instead of snapping.

### **Links That Show What They Lead To (15 November 2026)**

* **🔗 A preview when you share it**: a link to the site, or to one chapter, now unfolds in WhatsApp and other chats with the chapter's title, the series, its author and the picture the chapter opens on.
* **📤 Share a chapter from its ending**: the end of each chapter has a "Compartir" button that hands its link to your phone's share sheet, or copies it.

### **Set Like a Book (15 November 2026)**

The story reads the same, word for word. Everything around the words was redrawn.

* **📖 A reading typeface and a proper column**: the text is set in Literata with Cormorant Garamond headings, in a column the eye can cross, with air between paragraphs and lines of dialogue.
* **✍️ The author on the cover**: the title screen and the index name who wrote it right under the title, and the credits page opens with the author, large.
* **🗂️ An index like a table of contents**: each chapter with its number, its title, the picture it opens on and where you left it.
* **🗣️ Every voice readable**: the dark blue and purple some characters speak in were almost invisible on black (1.3:1 and 2.2:1). They keep their colour and are now lightened just enough to read (4.5:1).
* **🔘 Choices you can see and reach**: choices are buttons with room for a thumb, the toolbar uses drawn icons with names, and everything shows where the keyboard focus is.
* **⌨️ Kinder to everyone**: the settings and status sheets close with Escape and keep the keyboard inside them, and all animation stops if your system asks for less motion.

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

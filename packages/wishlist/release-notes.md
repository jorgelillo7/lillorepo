# Wishlist — Release Notes

What changed for whoever opens the list, newest first. 🎁

### **v1.1 - Added From the Shop (12 November 2026)**

A gift used to exist only if someone edited a file and ran a script. Now it is added where the toy is: standing in the shop, from the phone.

* **📱 Gifts from `/admin`**: add, edit, hide and delete a gift, with a photo taken on the spot or picked from the library. Deleting one that somebody already reserved asks first.
* **🧼 A photo never carries where it was taken**: it is cleaned twice — the page redraws it before sending, and the server rebuilds it keeping only the picture — so no location, camera data or anything appended survives.
* **🗃️ The list lives in the database**: the 18 gifts that were there keep their links, their photos and their reservations.
* **🔒 The admin answers only to its own page**: a write must come from the admin page itself, no page can be shown inside another site's frame, and the admin is never cached.
* **🧪 Still to try**: the admin's buttons on a real iPhone, and the first photo stored for real.

### **v1.0 - The List (9 November 2026)**

* **🎄 One list for the family**: photos of the toys, who each one is for, and a button to reserve a gift and mark it bought. Names are optional and only the admin sees them.

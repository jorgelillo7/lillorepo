// Helpers shared by the list and the admin page. Everything a visitor typed is set
// with textContent, never as HTML.

/** Build an element with attributes and children (strings become text nodes). */
export function el(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (value === false || value == null) continue;
    if (name === "class") node.className = value;
    else node.setAttribute(name, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

const WHEN = new Intl.DateTimeFormat("es-ES", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Europe/Madrid",
});

/** "9 nov, 18:42" in Spain's time, whatever the viewer's zone. */
export const when = (iso) => (iso ? WHEN.format(new Date(iso)) : "");

// Paths resolve against the origin, not the page address: a page opened as
// https://user:pass@host/admin would otherwise make fetch refuse every call.
const at = (path) => new URL(path, location.origin);

export async function getJSON(url) {
  const response = await fetch(at(url), { cache: "no-store" });
  if (!response.ok) throw new Error(`${url}: ${response.status}`);
  return response.json();
}

export async function post(url, body) {
  return fetch(at(url), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function plural(count, one, many) {
  return `${count} ${count === 1 ? one : many}`;
}

export function showError(message) {
  const box = document.getElementById("error");
  box.textContent = message;
  box.hidden = !message;
}

import { el, when, getJSON, post, showError } from "/common.js";
import { nameMatches } from "/match.js";

const grid = document.getElementById("gifts");
const dialog = document.getElementById("reserveDialog");
const form = document.getElementById("reserveForm");
const nameInput = document.getElementById("reserveName");
let list = null;
let claims = new Map();
let pending = null;

// The filters live in the address (?para=older&estado=libres&buscar=lego), so a link
// can open one brother's list straight away.
const STATUSES = [
  { id: "", label: "Todos" },
  { id: "libres", label: "Libres", test: (claim) => !claim },
  { id: "reservados", label: "Reservados", test: (claim) => claim && !claim.boughtAt },
  { id: "comprados", label: "Comprados", test: (claim) => claim?.boughtAt },
];
const params = new URLSearchParams(location.search);
const filter = {
  who: params.get("para") ?? "",
  kind: params.get("tipo") ?? "",
  status: params.get("estado") ?? "",
  name: params.get("buscar") ?? "",
};

const FAILED = {
  taken: "Alguien acaba de reservarlo. La lista ya está al día.",
  "not-yours": "Esa reserva se hizo desde otro móvil u ordenador, así que solo se puede cambiar desde allí.",
};

function rememberedName() {
  try {
    return localStorage.getItem("wl-name") ?? "";
  } catch {
    return "";
  }
}

async function act(path, body) {
  const response = await post(path, body);
  if (!response.ok) {
    const { error } = await response.json().catch(() => ({}));
    showError(FAILED[error] ?? "No se ha podido guardar. Prueba otra vez en un momento.");
  } else {
    showError("");
  }
  await refresh();
}

function stateBlock(gift, claim) {
  if (!claim) {
    const button = el("button", { class: "button primary", type: "button" }, "Lo regalo yo");
    button.addEventListener("click", () => {
      pending = gift;
      document.getElementById("reserveGift").textContent = gift.title;
      nameInput.value = rememberedName();
      dialog.showModal();
    });
    return [button];
  }
  if (claim.boughtAt) {
    return [
      el("span", { class: "badge bought" }, claim.mine ? "✓ Lo has comprado tú" : "✓ Comprado"),
      el("span", { class: "when" }, `Comprado el ${when(claim.boughtAt)}`),
    ];
  }
  const parts = [
    el("span", { class: "badge reserved" }, claim.mine ? "Lo has reservado tú" : "Reservado"),
    el("span", { class: "when" }, `Reservado el ${when(claim.reservedAt)}`),
  ];
  if (claim.mine) {
    const bought = el("button", { class: "button secondary", type: "button" }, "Ya lo he comprado");
    const release = el("button", { class: "button ghost", type: "button" }, "Ya no lo regalo");
    bought.addEventListener("click", () => {
      bought.disabled = release.disabled = true;
      act("/api/bought", { id: gift.id });
    });
    release.addEventListener("click", () => {
      if (!confirm(`¿Dejar libre «${gift.title}» para que lo regale otra persona?`)) return;
      bought.disabled = release.disabled = true;
      act("/api/release", { id: gift.id });
    });
    parts.push(el("div", { class: "row" }, bought, release));
  }
  return parts;
}

const recipientLabel = (id) => list.recipients?.find((recipient) => recipient.id === id)?.label;
const forWho = (gift) => !filter.who || gift.for === filter.who;
const ofKind = (gift) => !filter.kind || gift.category === filter.kind;
const inStatus = (gift, status) => !status.test || Boolean(status.test(claims.get(gift.id)));
// Every count and every card goes through the name search first.
const searched = () => list.gifts.filter((gift) => nameMatches(gift.title, filter.name));

function buttons(container, kind, options, selected, count, choose, dots = true, favourites = null) {
  container.replaceChildren(
    ...options.map((option) => {
      const button = el(
        "button",
        {
          class: kind,
          type: "button",
          "aria-pressed": String(option.id === selected),
          "data-state": dots && kind === "chip" ? option.id || "todos" : null,
        },
        dots && kind === "chip" && option.id ? el("span", { class: "dot", "aria-hidden": "true" }) : null,
        option.label,
        el("span", { class: "n" }, count(option)),
        favourites && favouriteCount(favourites(option)),
      );
      button.addEventListener("click", () => choose(option.id));
      return button;
    }),
  );
}

/** "★ 3" with a spoken label, or nothing when the filter has no favourites. */
function favouriteCount(n) {
  if (!n) return null;
  return el(
    "span",
    { class: "fav-n" },
    el("span", { "aria-hidden": "true" }, `★ ${n}`),
    el("span", { class: "visually-hidden" }, n === 1 ? ", 1 favorito" : `, ${n} favoritos`),
  );
}

function renderFilters() {
  const status = STATUSES.find((s) => s.id === filter.status) ?? STATUSES[0];
  const recipients = list.recipients ?? [];
  const gifts = searched();
  document.getElementById("whoLevel").hidden = recipients.length < 2;
  buttons(
    document.getElementById("whoFilter"),
    "segment",
    [{ id: "", label: "Ambos" }, ...recipients],
    filter.who,
    (option) => gifts.filter((g) => (!option.id || g.for === option.id) && ofKind(g) && inStatus(g, status)).length,
    (id) => setFilter({ who: id }),
    true,
    (option) =>
      gifts.filter((g) => g.featured && (!option.id || g.for === option.id) && ofKind(g) && inStatus(g, status)).length,
  );
  // Only the kinds this recipient has gifts of, so the row stays short; the chosen
  // one stays even when the other filters empty it, so it can be undone.
  const kinds = (list.categories ?? []).filter(
    (kind) => kind.id === filter.kind || gifts.some((g) => forWho(g) && g.category === kind.id),
  );
  document.getElementById("kindLevel").hidden = kinds.length < 2;
  buttons(
    document.getElementById("kindFilter"),
    "chip",
    [{ id: "", label: "Todos" }, ...kinds],
    filter.kind,
    (option) => gifts.filter((g) => forWho(g) && (!option.id || g.category === option.id) && inStatus(g, status)).length,
    (id) => setFilter({ kind: id }),
    false,
  );
  buttons(
    document.getElementById("statusFilter"),
    "chip",
    STATUSES,
    status.id,
    (option) => gifts.filter((g) => forWho(g) && ofKind(g) && inStatus(g, option)).length,
    (id) => setFilter({ status: id }),
  );
}

function setFilter(change) {
  Object.assign(filter, change);
  const query = new URLSearchParams();
  if (filter.who) query.set("para", filter.who);
  if (filter.kind) query.set("tipo", filter.kind);
  if (filter.status) query.set("estado", filter.status);
  if (filter.name.trim()) query.set("buscar", filter.name.trim());
  history.replaceState(null, "", query.size ? `?${query}` : location.pathname);
  render();
}

/** The occasion's look: colours and header icon by CSS, and the browser bar's colour. */
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme ?? "navidad";
  const accent = getComputedStyle(document.documentElement).getPropertyValue("--red").trim();
  if (accent) document.querySelector('meta[name="theme-color"]')?.setAttribute("content", accent);
}

// The first row is on screen at load: those photos load at once, and the first, the
// page's largest paint, ahead of the rest.
const EAGER = 4;

function card(gift, index) {
  const claim = claims.get(gift.id);
  const photo = gift.photo;
  const label = recipientLabel(gift.for);
  return el(
    "article",
    { class: ["gift", gift.featured && "featured", claim?.boughtAt && "done"].filter(Boolean).join(" ") },
    el(
      "a",
      { class: "photo", href: photo, target: "_blank", rel: "noopener" },
      el("img", {
        src: photo,
        alt: gift.title,
        ...(index >= EAGER ? { loading: "lazy" } : {}),
        ...(index === 0 ? { fetchpriority: "high" } : {}),
      }),
    ),
    el(
      "div",
      { class: "body" },
      (label || gift.featured) &&
        el("div", { class: "tags" }, gift.featured && el("span", { class: "fav" }, "★ Favorito"), label && el("span", { class: "tag" }, label)),
      el("h3", {}, gift.title),
      gift.detail && el("p", { class: "detail" }, gift.detail),
      gift.note && el("p", { class: "note" }, gift.note),
      el("div", { class: "state" }, stateBlock(gift, claim)),
    ),
  );
}

function render() {
  const status = STATUSES.find((s) => s.id === filter.status) ?? STATUSES[0];
  const shown = searched().filter((gift) => forWho(gift) && ofKind(gift) && inStatus(gift, status));
  grid.replaceChildren(...shown.map(card));
  document.getElementById("empty").hidden = shown.length > 0;
  document.getElementById("shown").textContent =
    shown.length === 1 ? "Se muestra 1 regalo." : `Se muestran ${shown.length} regalos.`;
  renderFilters();
}

async function refresh() {
  try {
    const state = await getJSON("/api/state");
    claims = new Map(state.map((claim) => [claim.id, claim]));
    render();
  } catch {
    showError("No se ha podido cargar quién regala qué. Recarga la página en un momento.");
  }
}

form.addEventListener("submit", (event) => {
  if (event.submitter?.value !== "confirm" || !pending) return;
  const name = nameInput.value.trim();
  try {
    if (name) localStorage.setItem("wl-name", name);
  } catch {
    // Private browsing: the name is simply not remembered.
  }
  act("/api/reserve", { id: pending.id, name });
  pending = null;
});

const search = document.getElementById("search");
search.value = filter.name;
search.addEventListener("input", () => setFilter({ name: search.value }));
// The phone keyboard's search key closes the keyboard; the list is already filtered.
search.addEventListener("keydown", (event) => {
  if (event.key === "Enter") search.blur();
});

list = await getJSON("/api/list");
document.getElementById("title").textContent = list.title;
applyTheme(list.theme);
document.getElementById("subtitle").textContent = list.subtitle ?? "";
document.title = list.title;
await refresh();

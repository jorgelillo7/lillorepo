import { el, when, getJSON, post, showError } from "/common.js";

const grid = document.getElementById("gifts");
const dialog = document.getElementById("reserveDialog");
const form = document.getElementById("reserveForm");
const nameInput = document.getElementById("reserveName");
let list = null;
let claims = new Map();
let pending = null;

// The filters live in the address (?para=older&estado=libres), so a link can open
// one brother's list straight away.
const STATUSES = [
  { id: "", label: "Todos" },
  { id: "libres", label: "Libres", test: (claim) => !claim },
  { id: "reservados", label: "Reservados", test: (claim) => claim && !claim.boughtAt },
  { id: "comprados", label: "Comprados", test: (claim) => claim?.boughtAt },
];
const params = new URLSearchParams(location.search);
const filter = { who: params.get("para") ?? "", status: params.get("estado") ?? "" };

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
const inStatus = (gift, status) => !status.test || Boolean(status.test(claims.get(gift.id)));

function buttons(container, kind, options, selected, count, choose) {
  container.replaceChildren(
    ...options.map((option) => {
      const button = el(
        "button",
        {
          class: kind,
          type: "button",
          "aria-pressed": String(option.id === selected),
          "data-state": kind === "chip" ? option.id || "todos" : null,
        },
        kind === "chip" && option.id ? el("span", { class: "dot", "aria-hidden": "true" }) : null,
        option.label,
        el("span", { class: "n" }, count(option)),
      );
      button.addEventListener("click", () => choose(option.id));
      return button;
    }),
  );
}

function renderFilters() {
  const status = STATUSES.find((s) => s.id === filter.status) ?? STATUSES[0];
  const recipients = list.recipients ?? [];
  document.getElementById("whoLevel").hidden = recipients.length < 2;
  buttons(
    document.getElementById("whoFilter"),
    "segment",
    [{ id: "", label: "Ambos" }, ...recipients],
    filter.who,
    (option) => list.gifts.filter((g) => (!option.id || g.for === option.id) && inStatus(g, status)).length,
    (id) => setFilter({ who: id }),
  );
  buttons(
    document.getElementById("statusFilter"),
    "chip",
    STATUSES,
    status.id,
    (option) => list.gifts.filter((g) => forWho(g) && inStatus(g, option)).length,
    (id) => setFilter({ status: id }),
  );
}

function setFilter(change) {
  Object.assign(filter, change);
  const query = new URLSearchParams();
  if (filter.who) query.set("para", filter.who);
  if (filter.status) query.set("estado", filter.status);
  history.replaceState(null, "", query.size ? `?${query}` : location.pathname);
  render();
}

function card(gift) {
  const claim = claims.get(gift.id);
  const photo = `/photos/${gift.photo}`;
  const label = recipientLabel(gift.for);
  return el(
    "article",
    { class: claim?.boughtAt ? "gift done" : "gift" },
    el(
      "a",
      { class: "photo", href: photo, target: "_blank", rel: "noopener" },
      el("img", { src: photo, alt: gift.title, loading: "lazy" }),
    ),
    el(
      "div",
      { class: "body" },
      label && el("span", { class: "tag" }, label),
      el("h3", {}, gift.title),
      gift.detail && el("p", { class: "detail" }, gift.detail),
      gift.note && el("p", { class: "note" }, gift.note),
      el("div", { class: "state" }, stateBlock(gift, claim)),
    ),
  );
}

function render() {
  const status = STATUSES.find((s) => s.id === filter.status) ?? STATUSES[0];
  const shown = list.gifts.filter((gift) => forWho(gift) && inStatus(gift, status));
  grid.replaceChildren(...shown.map(card));
  document.getElementById("empty").hidden = shown.length > 0;
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

list = await getJSON("/gifts.json");
document.getElementById("title").textContent = list.title;
document.getElementById("subtitle").textContent = list.subtitle ?? "";
document.title = list.title;
await refresh();

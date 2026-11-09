import { el, when, getJSON, post, plural, showError } from "/common.js";

const grid = document.getElementById("gifts");
const dialog = document.getElementById("reserveDialog");
const form = document.getElementById("reserveForm");
const nameInput = document.getElementById("reserveName");
let list = null;
let pending = null;

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

function render(state) {
  const claims = new Map(state.map((claim) => [claim.id, claim]));
  const cards = list.gifts.map((gift) => {
    const claim = claims.get(gift.id);
    const photo = `/photos/${gift.photo}`;
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
        el("h3", {}, gift.title),
        gift.detail && el("p", { class: "detail" }, gift.detail),
        gift.note && el("p", { class: "note" }, gift.note),
        el("div", { class: "state" }, stateBlock(gift, claim)),
      ),
    );
  });
  grid.replaceChildren(...cards);
  const bought = state.filter((claim) => claim.boughtAt).length;
  const reserved = state.length - bought;
  const free = list.gifts.length - state.length;
  document.getElementById("counts").textContent = [
    plural(list.gifts.length, "regalo", "regalos"),
    plural(free, "libre", "libres"),
    plural(reserved, "reservado", "reservados"),
    plural(bought, "comprado", "comprados"),
  ].join(" · ");
}

async function refresh() {
  try {
    render(await getJSON("/api/state"));
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

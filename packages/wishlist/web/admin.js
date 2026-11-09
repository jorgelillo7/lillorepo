import { el, when, getJSON, post, plural, showError } from "/common.js";

const rows = document.getElementById("rows");
let list = null;

async function change(path, gift, question) {
  if (!confirm(question)) return;
  const response = await post(path, { id: gift.id });
  showError(response.ok ? "" : "No se ha podido guardar. Recarga y prueba otra vez.");
  await refresh();
}

function render(state) {
  const claims = new Map(state.map((claim) => [claim.id, claim]));
  rows.replaceChildren(
    ...list.gifts.map((gift) => {
      const claim = claims.get(gift.id);
      const status = !claim ? "Libre" : claim.boughtAt ? "Comprado" : "Reservado";
      const actions = [];
      if (claim && !claim.boughtAt) {
        const bought = el("button", { class: "button secondary", type: "button" }, "Marcar comprado");
        bought.addEventListener("click", () =>
          change("/admin/api/bought", gift, `¿Marcar «${gift.title}» como comprado?`),
        );
        actions.push(bought);
      }
      if (claim) {
        const release = el("button", { class: "button ghost", type: "button" }, "Liberar");
        release.addEventListener("click", () =>
          change("/admin/api/release", gift, `¿Dejar «${gift.title}» libre otra vez? Se borra la reserva.`),
        );
        actions.push(release);
      }
      return el(
        "tr",
        {},
        el("td", {}, el("img", { class: "thumb", src: `/photos/${gift.photo}`, alt: "" }), gift.title),
        el("td", {}, status),
        el("td", {}, claim ? (claim.name ?? "Sin nombre") : ""),
        el("td", {}, when(claim?.reservedAt)),
        el("td", {}, when(claim?.boughtAt)),
        el("td", {}, el("div", { class: "row" }, actions)),
      );
    }),
  );
  const bought = state.filter((claim) => claim.boughtAt).length;
  document.getElementById("counts").textContent = [
    plural(list.gifts.length, "regalo", "regalos"),
    plural(list.gifts.length - state.length, "libre", "libres"),
    plural(state.length - bought, "reservado", "reservados"),
    plural(bought, "comprado", "comprados"),
  ].join(" · ");
}

async function refresh() {
  try {
    render(await getJSON("/admin/api/state"));
  } catch {
    showError("No se ha podido cargar el estado. Recarga la página.");
  }
}

list = await getJSON("/gifts.json");
await refresh();

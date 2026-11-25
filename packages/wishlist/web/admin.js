import { el, when, getJSON, post, postPhoto, plural, showError } from "/common.js";

const rows = document.getElementById("rows");
const dialog = document.getElementById("giftDialog");
const form = document.getElementById("giftForm");
const fields = {
  title: document.getElementById("giftTitle"),
  recipient: document.getElementById("giftFor"),
  category: document.getElementById("giftKind"),
  detail: document.getElementById("giftDetail"),
  note: document.getElementById("giftNote"),
};
const preview = document.getElementById("preview");
const formError = document.getElementById("giftError");
const save = document.getElementById("giftSave");
let list = { gifts: [], recipients: [], categories: [] };
let editing = null;
let chosen = null;
let previewUrl = null;

// A photo is resized and re-encoded through a canvas before it leaves the phone: a canvas
// writes a fresh JPEG, so the EXIF (GPS included) never goes up, and the upload is small.
// The Worker strips and checks it again.
const LONG_EDGE = 1280;
const QUALITY = 0.82;

async function decode(file) {
  try {
    return await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    const url = URL.createObjectURL(file);
    try {
      const image = new Image();
      image.src = url;
      await image.decode();
      return image;
    } finally {
      URL.revokeObjectURL(url);
    }
  }
}

async function resize(file) {
  const image = await decode(file);
  const width = image.width ?? image.naturalWidth;
  const height = image.height ?? image.naturalHeight;
  const scale = Math.min(1, LONG_EDGE / Math.max(width, height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("canvas"))), "image/jpeg", QUALITY),
  );
}

function showPreview(source) {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = source instanceof Blob ? URL.createObjectURL(source) : null;
  preview.src = previewUrl ?? source ?? "";
  preview.hidden = !preview.src;
}

for (const button of document.querySelectorAll("[data-pick]")) {
  button.addEventListener("click", () => document.getElementById(button.dataset.pick).click());
}

for (const id of ["photoCamera", "photoLibrary"]) {
  const input = document.getElementById(id);
  input.addEventListener("change", async () => {
    const file = input.files[0];
    input.value = "";
    if (!file) return;
    formError.hidden = true;
    try {
      chosen = await resize(file);
      showPreview(chosen);
    } catch {
      chosen = null;
      formError.textContent = "No se ha podido leer esa foto. Prueba con otra.";
      formError.hidden = false;
    }
  });
}

function openForm(gift) {
  editing = gift;
  chosen = null;
  formError.hidden = true;
  document.getElementById("giftHeading").textContent = gift ? "Editar regalo" : "Añadir regalo";
  fields.recipient.replaceChildren(
    el("option", { value: "" }, "Sin destinatario"),
    ...list.recipients.map((r) => el("option", { value: r.id }, r.label)),
  );
  fields.category.replaceChildren(
    el("option", { value: "" }, "Sin tipo"),
    ...list.categories.map((c) => el("option", { value: c.id }, c.label)),
  );
  fields.title.value = gift?.title ?? "";
  fields.recipient.value = gift?.for ?? "";
  fields.category.value = gift?.category ?? "";
  fields.detail.value = gift?.detail ?? "";
  fields.note.value = gift?.note ?? "";
  showPreview(gift?.photo ?? null);
  dialog.showModal();
}

const FAILED = {
  photo: "La foto no es válida. Haz otra.",
  "photo-size": "La foto es demasiado grande.",
  title: "Falta el nombre del regalo.",
};

async function reason(response) {
  const { error } = await response.json().catch(() => ({}));
  return FAILED[error] ?? "No se ha podido guardar. Prueba otra vez.";
}

form.addEventListener("submit", async (event) => {
  if (event.submitter?.value !== "save") return;
  event.preventDefault();
  if (!form.reportValidity()) return;
  save.disabled = true;
  formError.hidden = true;
  try {
    let photo = editing?.photo;
    if (chosen) {
      const uploaded = await postPhoto("/admin/api/photo", chosen);
      if (!uploaded.ok) throw new Error(await reason(uploaded));
      photo = (await uploaded.json()).photo;
    } else if (!editing) {
      throw new Error("Falta la foto del regalo.");
    }
    const body = {
      title: fields.title.value,
      recipient: fields.recipient.value,
      category: fields.category.value,
      detail: fields.detail.value,
      note: fields.note.value,
      photo,
    };
    const response = await post(editing ? "/admin/api/gift/edit" : "/admin/api/gift/add", {
      ...body,
      ...(editing ? { id: editing.id } : {}),
    });
    if (!response.ok) throw new Error(await reason(response));
    dialog.close();
    await refresh();
  } catch (error) {
    formError.textContent = error.message;
    formError.hidden = false;
  } finally {
    save.disabled = false;
  }
});

dialog.addEventListener("close", () => showPreview(null));

const occasionDialog = document.getElementById("occasionDialog");
const occasionForm = document.getElementById("occasionForm");
const occasionError = document.getElementById("occasionError");

function openOccasion() {
  occasionError.hidden = true;
  document.getElementById("occasionTitle").value = list.title ?? "";
  document.getElementById("occasionSubtitle").value = list.subtitle ?? "";
  const theme = document.getElementById("occasionTheme");
  theme.replaceChildren(...(list.themes ?? []).map((t) => el("option", { value: t.id }, t.label)));
  theme.value = list.theme ?? "navidad";
  const fieldset = document.getElementById("occasionRecipients");
  fieldset.replaceChildren(
    el("legend", {}, "Para quién"),
    ...list.recipients.map((recipient, index) =>
      el(
        "div",
        { class: "occasion-recipient", "data-id": recipient.id },
        el("input", {
          type: "text",
          value: recipient.label,
          maxlength: "40",
          required: "",
          autocomplete: "off",
          "aria-label": `Nombre ${index + 1}`,
        }),
        el("label", {}, el("input", { type: "checkbox", ...(recipient.active ? { checked: "" } : {}) }), "Activo"),
      ),
    ),
  );
  occasionDialog.showModal();
}

occasionForm.addEventListener("submit", async (event) => {
  if (event.submitter?.value !== "save") return;
  event.preventDefault();
  const recipients = [...document.querySelectorAll(".occasion-recipient")].map((row) => ({
    id: row.dataset.id,
    label: row.querySelector('input[type="text"]').value,
    active: row.querySelector('input[type="checkbox"]').checked,
  }));
  const response = await post("/admin/api/occasion", {
    title: document.getElementById("occasionTitle").value,
    subtitle: document.getElementById("occasionSubtitle").value,
    theme: document.getElementById("occasionTheme").value,
    recipients,
  });
  if (!response.ok) {
    occasionError.textContent = "No se ha podido guardar: revisa que el título y los nombres no estén vacíos.";
    occasionError.hidden = false;
    return;
  }
  occasionDialog.close();
  await refresh();
});

document.getElementById("editOccasion").addEventListener("click", openOccasion);
document.getElementById("hideAll").addEventListener("click", () =>
  change("/admin/api/gift/hide-all", { hidden: true }, "¿Ocultar todos los regalos de la lista pública? Luego puedes mostrar uno a uno los que quieras."),
);
document.getElementById("showAll").addEventListener("click", () =>
  change("/admin/api/gift/hide-all", { hidden: false }, "¿Mostrar todos los regalos en la lista pública?"),
);
document.getElementById("addGift").addEventListener("click", () => openForm(null));

async function change(path, body, question) {
  if (question && !confirm(question)) return;
  const response = await post(path, body);
  showError(response.ok ? "" : "No se ha podido guardar. Recarga y prueba otra vez.");
  await refresh();
}

async function remove(gift, claim) {
  if (!confirm(`¿Borrar «${gift.title}»? No se puede deshacer.`)) return;
  let response = await post("/admin/api/gift/delete", { id: gift.id });
  if (response.status === 409) {
    const who = claim?.name ? ` por ${claim.name}` : "";
    if (!confirm(`«${gift.title}» está reservado${who}. ¿Borrarlo de todos modos? Se pierde la reserva.`)) return;
    response = await post("/admin/api/gift/delete", { id: gift.id, force: true });
  }
  showError(response.ok ? "" : "No se ha podido borrar. Recarga y prueba otra vez.");
  await refresh();
}

function button(label, kind, handler) {
  const node = el("button", { class: `button ${kind}`, type: "button" }, label);
  node.addEventListener("click", handler);
  return node;
}

function recipientName(id) {
  const recipient = list.recipients.find((r) => r.id === id);
  if (!recipient) return id;
  return recipient.active === false ? `${recipient.label} (desactivado)` : recipient.label;
}

function render(state) {
  const claims = new Map(state.map((claim) => [claim.id, claim]));
  rows.replaceChildren(
    ...list.gifts.map((gift) => {
      const claim = claims.get(gift.id);
      const status = gift.hidden ? "Oculto" : !claim ? "Libre" : claim.boughtAt ? "Comprado" : "Reservado";
      const actions = [];
      if (claim && !claim.boughtAt) {
        actions.push(
          button("Marcar comprado", "secondary", () =>
            change("/admin/api/bought", { id: gift.id }, `¿Marcar «${gift.title}» como comprado?`),
          ),
        );
      }
      if (claim) {
        actions.push(
          button("Liberar", "ghost", () =>
            change("/admin/api/release", { id: gift.id }, `¿Dejar «${gift.title}» libre otra vez? Se borra la reserva.`),
          ),
        );
      }
      const star = button("★ Destacado", "ghost star", () =>
        change("/admin/api/gift/feature", { id: gift.id, featured: !gift.featured }),
      );
      star.setAttribute("aria-pressed", String(Boolean(gift.featured)));
      actions.push(star);
      actions.push(button("Editar", "ghost", () => openForm(gift)));
      actions.push(
        button(gift.hidden ? "Mostrar" : "Ocultar", "ghost", () =>
          change("/admin/api/gift/hide", { id: gift.id, hidden: !gift.hidden }),
        ),
      );
      actions.push(button("Borrar", "ghost", () => remove(gift, claim)));
      return el(
        "tr",
        {},
        el("td", {}, el("img", { class: "thumb", src: gift.photo, alt: "" }), gift.featured ? `★ ${gift.title}` : gift.title,
          gift.for && el("span", { class: "when" }, ` · ${recipientName(gift.for)}`),
          gift.category && el("span", { class: "when" }, ` · ${list.categories.find((c) => c.id === gift.category)?.label ?? gift.category}`)),
        el("td", {}, status),
        el("td", {}, claim ? (claim.name ?? "Sin nombre") : ""),
        el("td", {}, when(claim?.reservedAt)),
        el("td", {}, when(claim?.boughtAt)),
        el("td", {}, el("div", { class: "row" }, actions)),
      );
    }),
  );
  // What the public list shows: not hidden, and not for a switched-off recipient.
  const shown = list.gifts.filter((gift) => !gift.hidden && list.recipients.find((r) => r.id === gift.for)?.active !== false);
  const live = state.filter((claim) => shown.some((gift) => gift.id === claim.id));
  const bought = live.filter((claim) => claim.boughtAt).length;
  document.getElementById("counts").textContent = [
    plural(shown.length, "regalo", "regalos"),
    plural(shown.length - live.length, "libre", "libres"),
    plural(live.length - bought, "reservado", "reservados"),
    plural(bought, "comprado", "comprados"),
    ...(list.gifts.length > shown.length ? [plural(list.gifts.length - shown.length, "sin publicar", "sin publicar")] : []),
  ].join(" · ");
}

async function refresh() {
  try {
    [list, state] = await Promise.all([getJSON("/admin/api/gifts"), getJSON("/admin/api/state")]);
    document.documentElement.dataset.theme = list.theme ?? "navidad";
    render(state);
  } catch {
    showError("No se ha podido cargar el estado. Recarga la página.");
  }
}

let state = [];
await refresh();

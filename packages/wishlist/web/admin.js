import { el, when, getJSON, post, postPhoto, plural, showError } from "/common.js";

const rows = document.getElementById("rows");
const dialog = document.getElementById("giftDialog");
const form = document.getElementById("giftForm");
const fields = {
  title: document.getElementById("giftTitle"),
  recipient: document.getElementById("giftFor"),
  detail: document.getElementById("giftDetail"),
  note: document.getElementById("giftNote"),
};
const preview = document.getElementById("preview");
const formError = document.getElementById("giftError");
const save = document.getElementById("giftSave");
let list = { gifts: [], recipients: [] };
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
  fields.title.value = gift?.title ?? "";
  fields.recipient.value = gift?.for ?? "";
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
        el("td", {}, el("img", { class: "thumb", src: gift.photo, alt: "" }), gift.title,
          gift.for && el("span", { class: "when" }, ` · ${list.recipients.find((r) => r.id === gift.for)?.label ?? gift.for}`)),
        el("td", {}, status),
        el("td", {}, claim ? (claim.name ?? "Sin nombre") : ""),
        el("td", {}, when(claim?.reservedAt)),
        el("td", {}, when(claim?.boughtAt)),
        el("td", {}, el("div", { class: "row" }, actions)),
      );
    }),
  );
  const shown = list.gifts.filter((gift) => !gift.hidden);
  const live = state.filter((claim) => shown.some((gift) => gift.id === claim.id));
  const bought = live.filter((claim) => claim.boughtAt).length;
  document.getElementById("counts").textContent = [
    plural(shown.length, "regalo", "regalos"),
    plural(shown.length - live.length, "libre", "libres"),
    plural(live.length - bought, "reservado", "reservados"),
    plural(bought, "comprado", "comprados"),
    ...(list.gifts.length > shown.length ? [plural(list.gifts.length - shown.length, "oculto", "ocultos")] : []),
  ].join(" · ");
}

async function refresh() {
  try {
    [list, state] = await Promise.all([getJSON("/admin/api/gifts"), getJSON("/admin/api/state")]);
    render(state);
  } catch {
    showError("No se ha podido cargar el estado. Recarga la página.");
  }
}

let state = [];
await refresh();

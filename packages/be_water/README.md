# 💧 be_water

> **Estado**: **en producción** desde 2026-07-18 (`be-water`, proyecto GCP
> `be-water-app`). Para el detalle operativo, ver:
>
> - **Qué ha shipeado**: `release-notes.md` (junto a este fichero).
> - **Comandos y runbooks** (correr, tests, deploy, catalog sync, tooling de
>   curación/auditoría): `OPERATIONS.md` (en este paquete).
> - **Modelo de datos Firestore**: `docs/firestore.md` (raíz) → sección
>   `be-water-app`.
> - **Seguimiento pendiente**: `PENDING.md` (raíz) → sección `be_water`.
> - **Sistema de diseño de la web**: `web/DESIGN.md`.

Catálogo colaborativo de aguas minerales españolas, servido con Flask sobre
Cloud Run. Cualquiera con el link sube una foto de la etiqueta y la ficha se
rellena sola (OCR con Gemini); el catálogo cruza **perfil mineral × procedencia**
para recomendar aguas parecidas a las tuyas allá donde estés.

## Piezas principales (bajo `web/`)

- **App** (`app.py`) — catálogo, ficha, favoritas, /comunidad (ranking +
  logros), recomendador, alta con foto + OCR, /acerca, /admin (dormant).
- **Datos** — `domain.py` (`Water`, con **procedencia por campo** en `sources`
  y `verified_fields`), `repository.py` (Firestore), `seed_data.py`,
  `aesan_snapshot.py` (registro oficial AESAN), `catalog_sync.py` (sync mensual).
- **Fotos + IA** — `photos.py` (GCS + tratamiento *studio* con Gemini,
  admin-gated), `label_ocr.py` (OCR de etiquetas). SDK compartido en
  `core/sdk/gemini.py`.
- **Motores reutilizables** (los reusa también `/admin`): `provenance.py`
  (deriva la fuente de cada valor), `photo_audit.py` (diagnóstico/reparación de
  fotos), `data_audit.py` (sign-off de verificación, duplicados, valores
  sospechosos), `similarity.py`.

## Modelo de confianza del dato

Cada valor lleva su fuente (`label` / `manufacturer` / `manual` / `aesan`),
visible en la ficha. Una ficha se **verifica y bloquea** contra sobrescritura
por dos vías: auto-promoción (todo respaldado por etiqueta) o sign-off de admin
(etiqueta fotografiada + al menos un valor confirmado). El registro oficial
AESAN aporta identidad (denominación + manantial + provincia); la composición
viene siempre de la etiqueta, la fuente legal.

## Decisiones de diseño (el *por qué*)

- **Package del monorepo + proyecto GCP propio.** El código vive en lillorepo
  como package autocontenido (comparte Bazel, `core/`, imagen `python-base`, CI
  y disciplina de PRs). El *runtime* corre en un proyecto GCP separado
  (`be-water-app`): free tier de Firestore independiente del de la liga, coste
  atribuible (budget €1 propio), y aislamiento total — nada de be_water puede
  rozar la SLO del digest de biwenger. Mismo `deploy.yml`, destino distinto vía
  paths-filter + `--project`.
- **Similitud: distancia euclídea normalizada en log-scale, k-NN en memoria.**
  El vector mineral es fijo (~10 dimensiones), así que el catálogo entero cabe
  en RAM y se compara sin infra vectorial. El log corrige los órdenes de
  magnitud (el Na va de 0 a >1000 mg/L, el TDS de 20 a >4000): 100 mg de
  diferencia en TDS no pesan lo mismo que 100 mg en Na. El recomendador por
  ubicación reusa el motor: centroide de tus favoritas × candidatas de la zona.
- **OCR con Gemini multimodal, no Cloud Vision.** Una llamada con la foto + un
  schema estructurado devuelve el vector mineral ya parseado en JSON, sin regex
  frágiles por etiqueta. El humano revisa y corrige antes de guardar; si Gemini
  falla, el form se abre vacío sin perder la foto.
- **"Auth" ligera.** Login por nickname (sin password), suficiente para un uso
  entre amigos. Google Sign-In + /admin shipearon dormant, listos para
  endurecerlo cuando el grupo crezca (runbook en `OPERATIONS.md`).

## Fuentes de datos

- [Lista oficial AESAN](https://www.aesan.gob.es/AECOSAN/web/seguridad_alimentaria/subdetalle/lista_aguas_envasadas.htm)
  ([PDF](https://www.aesan.gob.es/AECOSAN/docs/documentos/seguridad_alimentaria/gestion_riesgos/lista_espanola.pdf))
  — identidad oficial (denominación + manantial + lugar); base del snapshot en repo.
- [IGME — Aguas minerales reconocidas](https://aguasmineralesytermales.igme.es/introduccion/aguas-minerales-reconocidas)
  — inventario geológico con visor.
- **Etiquetas reales** (fotos + Gemini) — la composición, siempre desde la botella.
- [mineralwaters.org](https://mineralwaters.org/) — cross-check de composiciones dudosas.

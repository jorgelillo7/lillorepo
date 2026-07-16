# 💧 be_water — brainstorming + plan

> **Estado**: plan v2.1 (2026-07-17) tras análisis de competencia.
> Arquitectura: **package del monorepo** (`packages/be_water/`) con su propio
> servicio Cloud Run — la razón de ser de lillorepo es exactamente esta:
> cada package es un proyecto con despliegue propio sobre infra compartida.
> No hay código todavía.
> **Brand sugerida (display)**: "Be Water" o "Be Water, My Friend".
> **Cloud Run service**: `be-water`.

## 1. Contexto — el problema real

El problema que dispara el proyecto es personal y concreto: **fuera de casa,
si no están las aguas de siempre (Lanjarón, Solán de Cabras), la elección es
al tuntún** — y a veces sale Bezoya, que es justo lo contrario de lo que
busca el paladar en cuestión (27 mg/L de residuo seco vs los ~261 de Solán).

Casos de uso, por orden de importancia:

1. **Recomendador por ubicación** (la feature estrella): "estoy en
   Tarragona" → dime qué aguas de esa zona tienen composición similar a
   mis favoritas. Combina el lugar de procedencia del catálogo con el
   perfil mineral del usuario.
2. **Decidir en el lineal**: en una tienda con seis marcas delante, saber
   cuál se parece más a la que ya bebo y cuál se aleja.
3. **Lista personal**: user/login sencillo, cada uno marca sus favoritas
   sobre el catálogo y de ahí sale su perfil.
4. **Catálogo colaborativo**: cualquiera con el link sube foto + ficha de
   un agua nueva y enriquece la base.

Objetivo de coste: **€0**. No es un producto serio en cuanto a auth ni
roles — multijugador entre colegas.

## 2. Competencia — qué existe y qué no

| Quién | Qué hace | Qué NO hace (nuestro hueco) |
|---|---|---|
| **[Abar App](https://abar.app/)** | App móvil cerrada: catálogo + comparativa + filtros + reviews. Demuestra demanda. | No es web, no es abierta, sin recomendador geográfico. |
| **[FineWaters](https://www.finewaters.com/)** | Comunidad de catadores desde 2002; ~100 marcas con composición y "terroir"; mapa mundial. | Contenido editorial premium, no herramienta. España apenas cubierta. |
| **[mineralwaters.org](https://mineralwaters.org/)** | Base comunitaria internacional (cientos de aguas) con composición; admite contribuciones. | En inglés, foco internacional, sin perfil de usuario ni recomendador; España floja. |
| **[Comparador OCU](https://www.ocu.org/alimentacion/agua/comparar-agua-mineral)** | Comparativa de composición + precio de aguas del súper español. | De pago (socios), responde "cuál es mejor", no "cuál se parece a la tuya"; sin ubicación. |

**Conclusión**: nadie hace *"tu perfil mineral + dónde estás → recomendación
local"*, ni en España ni en abierto. Ese cruce (similitud × procedencia) es
la apuesta diferencial y es barato de construir (§5).

### Fuentes de datos para el seed (no competencia: materia prima)

- **[Lista oficial AESAN](https://www.aesan.gob.es/AECOSAN/web/seguridad_alimentaria/subdetalle/lista_aguas_envasadas.htm)**
  de aguas minerales naturales reconocidas en España: denominación
  comercial + **manantial + lugar de explotación**. Es exactamente el campo
  "procedencia" que necesita el recomendador, con bendición oficial.
- **[IGME — Aguas minerales y termales](https://aguasmineralesytermales.igme.es/introduccion/aguas-minerales-reconocidas)**:
  inventario geológico con ~1.000 captaciones y visor geográfico.
- **Etiquetas reales** (fotos nuestras + Gemini, §4): la composición viene
  de la botella, que es la fuente legal y siempre actualizada.
- **mineralwaters.org** como cross-check de composiciones dudosas.

### ¿La composición está estandarizada?

**Sí**, las etiquetas españolas (norma UE) siempre llevan el mismo vector
de campos. Definimos el modelo de datos directamente sobre ese vector:

| Campo | Unidad | Obligatorio | Notas |
|---|---|---|---|
| Residuo seco (TDS) | mg/L | ✅ | Clasificador primario |
| Bicarbonatos (HCO₃⁻) | mg/L | ✅ | |
| Cloruros (Cl⁻) | mg/L | ✅ | |
| Sulfatos (SO₄²⁻) | mg/L | ✅ | |
| Calcio (Ca²⁺) | mg/L | ✅ | |
| Magnesio (Mg²⁺) | mg/L | ✅ | |
| Sodio (Na⁺) | mg/L | ✅ | Crítico para hipertensos |
| Potasio (K⁺) | mg/L | ⚠️ | Cuando aparece |
| Sílice (SiO₂) | mg/L | ⚠️ | |
| Nitratos (NO₃⁻) | mg/L | ⚠️ | |
| pH | — | ⚠️ | |

**Clasificación por TDS (UE)**:

- `< 50 mg/L` → mineralización muy débil (ej. Bezoya, 27 mg/L)
- `50–500 mg/L` → mineralización débil/media (ej. Solán de Cabras, 261 mg/L)
- `500–1500 mg/L` → mineralización fuerte
- `> 1500 mg/L` → mineralización muy fuerte

Ese único número ya cuenta la mitad de la historia. El resto del vector
mineral es para afinar.

## 3. Hallazgos clave

1. **Vector fijo de ~10 dimensiones por agua** → algoritmo de similitud
   trivial: distancia euclídea normalizada (log-scale por la diferencia de
   órdenes de magnitud entre Na de Bezoya y Na de Vichy Catalán). k-NN en
   memoria con todo el catálogo cabe holgado mientras tengamos <10 k aguas.
2. **OCR vía Gemini multimodal (no Vision API)**. El usuario tiene
   Google AI Pro. En lugar de Cloud Vision API (que solo extrae texto
   bruto y obliga a regex frágiles por etiqueta), una sola llamada a
   Gemini con la foto + prompt estructurado devuelve los campos del
   vector mineral ya **parseados en JSON**. Más simple, más robusto,
   sin coste adicional dentro de la cuota Pro. Detalle en §4.
3. **"Login" simple por nickname** es suficiente. Sin password, sin email.
   Cualquiera escoge un nickname al entrar; si el nickname ya existe,
   asumimos que es el mismo (riesgo aceptable: amigos, no producto serio).
4. **El monorepo ya tiene todo lo que necesita**: Cloud Run + Flask (patrón
   `biwenger_tools/web`), Firestore (`core/sdk/firestore.py`), la macro
   Bazel `python_service`, el CI con paths-filter por módulo y la imagen
   `python-base` compartida. Añadir el package es replicar estructura, no
   construir infra.
5. **Coste real estimado**: <€0.50/mes con 5 usuarios y 200 aguas. Firestore
   y Cloud Run free-tier cubren con creces.

## 4. Decisión por decisión

### Package del monorepo (decisión 2026-07-17)

be_water es un **package de lillorepo** (`packages/be_water/web/`), como
manda la filosofía del repo: packages autocontenidos, cada uno con su
servicio Cloud Run, compartiendo Bazel, `core/`, la imagen `python-base`,
el CI y la disciplina de PRs. Un repo separado duplicaría toda esa infra
para no ganar nada a esta escala.

Salvaguardas (por ser el primer package "social" junto a biwenger):

- **Firestore compartido pero con colecciones propias** (`waters/`,
  `users/`): el free tier del proyecto (50k reads/día) da órdenes de
  magnitud de margen para ambos; si algún día be_water lo amenazara, la
  migración a proyecto GCP propio es un cambio de config, no de código.
- **Deploy independiente**: entry propio en `deploy.yml` con paths-filter
  (`packages/be_water/**`) — un cambio en be_water jamás redespliega
  biwenger, y viceversa. La SLO del digest ni se entera.

### Stack

- **Backend**: Python 3.13 + Flask (reuso patrón `biwenger_tools/web`).
- **Build**: Bazel + `tools/bazel/python_service.bzl`.
- **Deploy**: Cloud Run en `europe-southwest1` (mismo project + región que
  el resto), servicio `be-water`.
- **Datos**: Firestore (`core/sdk/firestore.py` ya empaqueta el cliente).
- **Fotos**: Cloud Storage bucket `be-water-photos`.
- **Frontend**: server-side rendered HTML + Tailwind via CDN
  (sin SPA framework — UX rápida, cero build pipeline, mismo enfoque que
  `biwenger_tools/web`). HTMX para los pequeños AJAX (toggle favorita,
  autocompletado de marca).

### "Auth"

- Nickname-only, sin password. Guardamos en cookie `be_water_nickname`.
- Endpoint `POST /login` con `{nickname}` → crea doc `users/{nickname}` si
  no existe y setea cookie.
- Cualquiera puede ver el catálogo. Solo logueado se puede marcar favoritas
  y añadir aguas.
- **Sin protección contra suplantación**. Amigos, no producto. Si en v2
  hace falta, se añade Google Sign-In (Cloud Run admite IAP fácil).

### Modelo de datos

```
waters/{water_id}
├── name: "Solán de Cabras"
├── brand: "Solán de Cabras"
├── region: "Cuenca"
├── country: "ES"
├── source: "Manantial El Reino" (opcional)
├── photo_url: gs://be-water-photos/{water_id}.jpg
├── photo_thumb_url: gs://be-water-photos/{water_id}_thumb.jpg
├── minerals:
│   ├── tds: 261
│   ├── bicarbonates: 284.8
│   ├── chlorides: 1.5
│   ├── sulfates: 18.3
│   ├── calcium: 58.3
│   ├── magnesium: 25.1
│   ├── sodium: 5.2
│   ├── potassium: 1.1
│   ├── silica: null
│   ├── nitrates: null
│   └── ph: null
├── added_by: "jorge"
├── added_at: 2026-06-02T18:00:00Z

users/{nickname}
├── nickname: "jorge"
├── favorites: [water_id, water_id, …]
├── created_at: 2026-06-02T18:00:00Z
```

Una sola colección de aguas, una de usuarios. Sin reviews ni ratings en v1
(deliberado: añade complejidad de moderación). Si crece, se añade
`reviews/{water_id}/{nickname}` luego.

### Subida de fotos + OCR vía Gemini

Flujo: el usuario hace foto → el server la manda a Gemini → Gemini
devuelve JSON con los campos → el usuario revisa/edita y confirma.

- **Captura**: form multipart estándar con
  `<input type="file" accept="image/*" capture>` para que el móvil
  abra cámara directo (también admite galería).
- **Procesamiento server-side**: Pillow para redimensionar
  (max 1600×1600 — Gemini cobra por imagen, no por píxel, pero menos
  bytes = menos latencia) y generar thumbnail 400×400. Subida a GCS.
- **Extracción con Gemini**: una llamada a `gemini-2.0-flash` (o
  superior) con la imagen + prompt:

  ```
  Eres un parser de etiquetas de agua mineral embotellada.
  Extrae estos campos. Si un campo no aparece, deja null. Devuelve
  solo JSON, sin texto adicional.

  Campos:
  - name (str): marca o denominación comercial
  - source (str): manantial / fuente
  - country (ISO-3166 alpha-2)
  - region (str): provincia o región
  - tds, bicarbonates, chlorides, sulfates, calcium, magnesium,
    sodium, potassium, silica, nitrates (float, mg/L)
  - ph (float)
  ```

  Gemini admite **structured output** (`responseMimeType=application/json`
  + `responseSchema=…`) → la respuesta es JSON válido garantizado.

- **Pre-fill del formulario**: los campos llegan ya rellenos. El
  usuario revisa, corrige lo que haga falta y confirma. Edición humana
  siempre disponible — Gemini puede equivocarse en una décima y eso
  no se penaliza al usuario.
- **Coste**: la cuota Google AI Pro del usuario cubre todo el uso
  inicial. Si crece, AI Studio API tiene tier free generoso
  (15 RPM para flash) + tier pagado barato. Sin Vision API, sin
  parseadores regex.
- **Fallback**: si Gemini falla (timeout, error, JSON inválido), el
  formulario se abre vacío y se rellena a mano.
- **Sin moderación pre-publicación**. Si hay spam en v2, approval queue.

#### Secreto y SDK

- API key en Secret Manager (`BEWATER_GEMINI_API_KEY`).
- SDK: `google-generativeai` (oficial Python). Lo encapsulamos en
  `core/sdk/gemini.py` para que cualquier paquete futuro lo reuse.

## 5. Algoritmo de similitud

**Distancia euclídea normalizada en log-scale**:

```
similarity(a, b) = sqrt(sum_i (log10(a_i + 1) - log10(b_i + 1))²)
                          ────────────────────────────────────
                                         w_i
```

donde `w_i` es el peso por mineral (TDS pesa más, micros pesan menos), y
`+ 1` evita `log(0)` cuando un campo es null o cero.

**Por qué log**: el rango de Na va de 0 a 1.200 mg/L, el de Mg de 0 a 126,
el de TDS de 20 a 4.000+. Una diferencia de 100 mg en TDS no es la misma
que 100 mg en Na. log-scale corrige eso.

**Búsqueda**: k-NN en memoria. Catálogo cabe en RAM (10.000 aguas × 11
campos × 8 bytes = 880 KB). Sin Vespa, sin Pinecone, sin nada.

**Cache**: pre-cómputo de la matriz de distancias al arrancar el proceso.
Re-cálculo on-demand al añadir agua nueva (invalida cache).

**Recomendador por ubicación** (la feature estrella, mismo motor):

```
recomendar(user, lugar) =
    centroide = media log-scale de las favoritas del user
    candidatas = aguas cuyo lugar de procedencia ∈ lugar
    → top-N candidatas por distancia al centroide
```

Ejemplo: favoritas = {Lanjarón, Solán de Cabras} → centroide de
mineralización débil-media; lugar = "Tarragona" → candidatas de esa zona
ordenadas por cercanía al centroide (y aviso si la más cercana sigue
estando lejos: "por aquí no hay nada como lo tuyo, la menos mala es X").
El campo procedencia sale de la lista oficial AESAN (§2), no de texto libre.

## 6. Plan v1 — sprint 1 (MVP entregable)

> **Objetivo**: web funcional con catálogo, favoritas, similitud, subida
> de foto y OCR vía Gemini. Diseño que entre por los ojos.

### Sprint 1.A — esqueleto + catálogo (entregable cerrado)

| Paso | Acción | Notas |
|---|---|---|
| 1 | Crear `packages/be_water/web/` con esqueleto Flask + `BUILD.bazel` siguiendo el patrón de `biwenger_tools/web` | Copia y adapta |
| 2 | Modelo Firestore: colecciones `waters` + `users`. SDK helpers en `be_water/repository.py` | Reuso `core/sdk/firestore.py` |
| 3 | Endpoints: `GET /` (catálogo), `GET /water/<id>`, `POST /water` (nueva, manual), `POST /favorite/<id>`, `GET /similar/<id>`, `POST /login` | |
| 4 | UI: lista con cards (foto + nombre + TDS + region), buscador en cliente, tag por mineralización (muy débil / débil / fuerte / muy fuerte) | Tailwind CDN |
| 5 | Ficha de agua: foto grande, tabla minerales, botón ❤️ favorita, sección "aguas similares" (top 3 por k-NN) | |
| 6 | **Recomendador por ubicación**: `GET /recommend?place=<region>` — filtra por procedencia + ordena por distancia al centroide de tus favoritas. UI: un select de "¿dónde estás?" en la home | La feature estrella entra en el MVP |
| 7 | Formulario manual "añadir agua": campos del vector mineral + foto desde móvil + validación inline | Sin OCR todavía |
| 8 | `be-water-photos` bucket en GCP + IAM (Cloud Run SA con `storage.objectAdmin`) | Manual |
| 9 | Deploy a Cloud Run: entry en `deploy.yml` con paths-filter `packages/be_water/**` | Bajo `concurrency: deploy-master` ya en sitio |
| 10 | Seed: 15-20 aguas españolas con datos reales de etiqueta (Bezoya, Solán, Lanjarón, Mondariz, Vichy Catalán, Font Vella, Veri…), procedencia cruzada con la lista oficial AESAN | |

### Sprint 1.B — OCR vía Gemini

| Paso | Acción | Notas |
|---|---|---|
| 1 | `core/sdk/gemini.py`: cliente compartido con `google-generativeai`, configurable vía secret `GEMINI_API_KEY` | Patrón `core/sdk/firestore.py` |
| 2 | Prompt + JSON schema para extraer el vector mineral. Iterar con fotos reales de etiqueta hasta tener tasa de acierto razonable | Test fixture con 5-10 etiquetas |
| 3 | Wire en `POST /water`: si llega foto, llamar Gemini, pre-rellenar el form. Si llega solo el form, usar valores manuales | |
| 4 | UI: spinner mientras Gemini parsea, banner "revisa los valores antes de guardar" sobre el form pre-rellenado | |
| 5 | Fallback: cuando Gemini falle, mostrar form vacío con la foto cargada — no perder la foto del usuario | |
| 6 | Métrica simple (log estructurado) de tasa de éxito para iterar el prompt | |

## 7. Plan v2 — sprints futuros

| Sprint | Pieza | Notas |
|---|---|---|
| v2.1 | **Reviews con texto libre** + rating 1-5 estrellas | Solo si hay tracción |
| v2.2 | **Recomendador por perfil**: a partir de tus favoritas, sugiere nuevas. Usa los centroides de tus aguas en el espacio mineral | |
| v2.3 | **Mapa de aguas** (referencia Bottled Waters of the World de FineWaters) — Open Street Map con un pin por agua filtrable por TDS | |
| v2.4 | **PWA / installable**: manifest + service worker para que se "instale" en el móvil sin app store | |
| v2.5 | **Google Sign-In opcional** (Cloud Run IAP) para endurecer "auth" si el grupo crece más allá de amigos | |

## 8. Open questions

1. **¿Multi-idioma desde el inicio o solo ES?** — Recomiendo ES en v1; EN
   en v2 si hay tracción. Cuesta poco con `flask-babel` pero alarga
   el sprint 1.
2. **¿Validación de los datos minerales?** Cualquiera puede meter cualquier
   número. ¿Solo añadimos sanity checks (rangos plausibles) o vamos a
   "todo vale, los amigos cuidan los datos"? Recomiendo sanity checks
   blandos (warning, no bloqueo).
3. **¿Qué hacer con duplicados?** Si dos personas suben "Bezoya" con datos
   ligeramente distintos, ¿deduplicamos por marca+región? Recomiendo
   advertencia al añadir si ya existe una con la misma marca, y dejar
   que el usuario decida.
4. **¿Permitimos editar aguas o son inmutables?** — Recomiendo edición
   abierta para corregir typos, sin historial en v1.
5. **GDPR**: nickname no es PII si no metemos email. Cookies sin tracking.
   Banner mínimo de "usamos cookies para recordar tu nickname". Cero
   analytics.

## 9. Lo que NO hace este paquete

- **No es una app móvil nativa**. Es web responsive que el móvil puede
  guardar como icono.
- **No es un producto comercial**. Sin pasarela de pago, sin tienda, sin
  SEO serio.
- **No reemplaza a Abar / FineWaters / Etiquetalo** para usuarios externos.
  Es para nosotros.
- **No hace OCR en el sprint 1.A**. El alta manual llega primero; Gemini
  entra en el sprint 1.B sobre un flujo que ya funciona.
- **No tiene moderación pre-publicación**. v2 si hay spam.

## 10. Próximo paso

Con luz verde del usuario, **paso 1 del sprint 1**: esqueleto
`packages/be_water/web/` (Flask + `BUILD.bazel` con `python_service`) con un
`GET /` "hello water", entry en `deploy.yml` con su paths-filter, y deploy a
Cloud Run — validar el camino completo antes de meter lógica de negocio.

A partir de ahí, paso a paso por la tabla del sprint 1.

## 11. Fuentes consultadas

- [Lista oficial AESAN de aguas minerales naturales reconocidas](https://www.aesan.gob.es/AECOSAN/web/seguridad_alimentaria/subdetalle/lista_aguas_envasadas.htm) (+ [PDF](https://www.aesan.gob.es/AECOSAN/docs/documentos/seguridad_alimentaria/gestion_riesgos/lista_espanola.pdf))
- [IGME — Aguas minerales reconocidas en España](https://aguasmineralesytermales.igme.es/introduccion/aguas-minerales-reconocidas)
- [mineralwaters.org — base comunitaria internacional](https://mineralwaters.org/)
- [Comparador de aguas OCU](https://www.ocu.org/alimentacion/agua/comparar-agua-mineral)
- [Abar App — Water Bottle Labels Explained: Sodium & Minerals](https://abar.app/en/blogs/how-to-read-water-bottle-labels-sodium-fluoride-and-other-minerals-explained)
- [FineWaters — TDS / Minerality concept](https://finewaters.com/the-story-of-fine-water/key-concepts/minerality-tds)
- [FineWaters — Bottled Waters of the World Map](https://finewaters.com/bottled-waters-of-the-world)
- [Aguas Fondetal — Cómo elegir agua mineral (etiquetas, mineralización, origen)](https://aguasfondetal.com/noticias/como-elegir-agua-mineral/)
- [El Español — Comparativa Bezoya vs Solán vs Lanjarón](https://www.elespanol.com/reportajes/20210530/mejores-lidl-mercadona-doctora-carmen-bezoya-lanjaron/584692983_0.html)
- [SaludBio — Comparativa Aguas Minerales](https://saludbio.com/articulo/aguas-minerales-comparaci%C3%B3n)
- [PMC — Comparison of the Mineral Content of Tap Water and Bottled Waters](https://pmc.ncbi.nlm.nih.gov/articles/PMC1495189/)
- [Classification of Mineral Water Types (ResearchGate)](https://www.researchgate.net/publication/225738865_Classification_of_Mineral_Water_Types_and_Comparison_with_Drinking_Water_Standards)

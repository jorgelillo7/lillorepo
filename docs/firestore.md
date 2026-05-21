# Firestore — modelo de datos e índices

Documento de referencia para la base de datos Firestore de `biwenger-tools`.
Se mantiene a mano cuando añadas/cambies colecciones, campos o índices —
no hay autogeneración.

- **Proyecto GCP:** `biwenger-tools`
- **Base de datos:** `(default)`, modo Native, regional **`europe-southwest1`**
  (free tier, co-localizada con Cloud Run).
- **Auth:** Application Default Credentials (ADC).
  - En Cloud Run la SA de compute la coge automáticamente.
  - Localmente: `gcloud auth application-default login` una vez.

---

## Colecciones

```
comunicados/{season}/messages/{id_hash}
participacion/{season}/authors/{autor}
clausulazos/{season}/transfers/{content_hash}
tabla_justicia/{season}/teams/{equipo}
palmares/{temporada}
```

Hay un documento "season" intermedio (`comunicados/{season}`,
`participacion/{season}`, etc.) que está vacío — sólo existe como
contenedor de la subcolección. Firestore lo crea implícitamente.

Los modelos Python que sirializan/deserializan estos documentos viven en
`core/domain/models.py` con métodos `to_firestore()` / `from_firestore()`.

---

## Esquemas

### `comunicados/{season}/messages/{id_hash}` — `LeagueMessage`

Comunicados, datos curiosos, crónicas y cesiones del muro de Biwenger.
La categoría (`comunicado`, `dato`, `cronica`, `cesion`) está dentro del
documento, no en el path — el mismo doc puede pasar de una sección a
otra de la web sin moverse.

| Campo       | Tipo                       | Notas |
|-------------|----------------------------|-------|
| `fecha`     | timestamp                  | Sirializa desde `dd-MM-YYYY HH:mm:ss` |
| `autor`     | string                     | Nombre del manager |
| `titulo`    | string                     | |
| `contenido` | string                     | HTML; sanitizado en lectura por la web (`safe_html`) |
| `categoria` | string                     | Enum: `comunicado` / `dato` / `cronica` / `cesion` |

**Doc id:** SHA-256 hex del `(date + content)` original (calculado en
`scraper_job/main.py::_process_new_messages`). Determinista — el mismo
mensaje siempre tiene el mismo id, lo que hace el dual-write idempotente.

### `participacion/{season}/authors/{autor}` — `Participation`

Agregado por manager: qué mensajes ha posteado y de qué categoría. Lo
recalcula el scraper en cada run (no se incrementa, se reescribe entero).

| Campo         | Tipo            | Notas |
|---------------|-----------------|-------|
| `comunicados` | array&lt;string&gt; | IDs (`id_hash`) de los comunicados firmados |
| `datos`       | array&lt;string&gt; | IDs de los datos curiosos |
| `cesiones`    | array&lt;string&gt; | |
| `cronicas`    | array&lt;string&gt; | |
| `total`       | int             | Derivado (suma de longitudes); guardado en escritura para poder `order_by("total")` server-side |

**Doc id:** el nombre del manager (`autor`).

### `clausulazos/{season}/transfers/{content_hash}` — `Clausulazo`

Transferencias ejecutadas vía cláusula de rescisión.

| Campo               | Tipo       | Notas |
|---------------------|------------|-------|
| `fecha`             | timestamp  | Sirializa desde `dd-MM-YYYY HH:mm` (sin segundos) |
| `jugador`           | string     | |
| `equipo_vendedor`   | string     | |
| `equipo_comprador`  | string     | |
| `precio`            | int        | Euros (`6475000` = 6.4M); igual que en la API de Biwenger |

**Doc id:** SHA-256[:20] del `fecha|jugador|equipo_vendedor|equipo_comprador|precio`
(`scraper_job/main.py::_clausulazo_doc_id` y
`scripts/backfill_firestore.py::_clausulazo_id`). Determinista — debe
coincidir entre el scraper y la backfill para que reescribir sea no-op.

### `tabla_justicia/{season}/teams/{equipo}` — `JusticeEntry`

Resumen de "ataques" (clausulazos hechos/recibidos) por equipo.

| Campo              | Tipo                            | Notas |
|--------------------|---------------------------------|-------|
| `total_hechos`     | int                             | Nº de clausulazos hechos por el equipo |
| `total_recibidos`  | int                             | |
| `punto_de_mira`    | string                          | Equipo al que más le clausula |
| `mayor_agresor`    | string                          | Equipo que más le clausula |
| `hechos`           | array&lt;map&lt;string,int&gt;&gt; | `[{team, count}, ...]` orden desc |
| `recibidos`        | array&lt;map&lt;string,int&gt;&gt; | |

**Doc id:** el nombre del equipo (`equipo`). El equipo placeholder de
managers que se han ido se llama `Usuario` (convención de Biwenger).

### `palmares/{temporada}` — `Palmares`

Honores históricos. Un documento por temporada (`24-25`, `23-24`, ...).

| Campo              | Tipo            | Notas |
|--------------------|-----------------|-------|
| `campeon`          | string          | |
| `subcampeon`       | string          | |
| `tercero`          | string          | |
| `farolillo`        | string          | Último clasificado (paga multa) |
| `puntuacion`       | string          | "Score (decisivo)" del campeón |
| `record_puntos`    | string          | e.g. `"112 @fabio"` |
| `jornadas_ganadas` | string          | |
| `multas`           | array&lt;string&gt; | Quién paga multa (puede ser >1) |

**Doc id:** la temporada (`24-25`, etc.). Orden alfabético DESC = orden
cronológico DESC, así que `order_by("__name__")` da por ejemplo
`["25-26", "24-25", "23-24"]`.

---

## Índices

Firestore auto-indexa **cada campo de raíz** y **arrays** (membership) en
sentido ascendente y descendente. **No** auto-indexa combinaciones de
campos — esos son **índices compuestos** y hay que declararlos.

### Auto (no hace falta nada)

Todas las queries de "ordenar por un solo campo" funcionan sin tocar nada:

| Colección                                 | Query                                          |
|-------------------------------------------|------------------------------------------------|
| `participacion/{season}/authors`          | `order_by("total", DESCENDING)`                |
| `clausulazos/{season}/transfers`          | `order_by("fecha", DESCENDING)`                |
| `tabla_justicia/{season}/teams`           | `order_by("total_hechos", DESCENDING)`         |
| `palmares`                                | `order_by("__name__", DESCENDING)` (doc id)    |

### Compuesto (declarado)

| Collection group | Scope      | Campos                                              | Para qué |
|------------------|------------|-----------------------------------------------------|----------|
| `messages`       | COLLECTION | `categoria` ASC, `fecha` DESC                       | Paginar y filtrar comunicados / salseo (`get_messages_by_category`) sin escanear los ~2.800 mensajes |

`queryScope: COLLECTION` hace que el índice aplique a **cada subcolección
llamada `messages`** (una por temporada). Cuando se añada una temporada
nueva, no hace falta crear otro índice.

### Dónde están declarados

`firestore.indexes.json` en la raíz del repo. Es la fuente de verdad
declarativa.

### Crear / actualizar índices

```bash
# Crear el índice de "messages" (idempotente — falla suave si ya existe)
gcloud firestore indexes composite create \
  --collection-group=messages \
  --query-scope=COLLECTION \
  --field-config=field-path=categoria,order=ascending \
  --field-config=field-path=fecha,order=descending \
  --project=biwenger-tools

# Ver índices actuales
gcloud firestore indexes composite list --project=biwenger-tools

# Borrar uno por id (rara vez)
gcloud firestore indexes composite delete <id> --project=biwenger-tools
```

Cuando una query pide un índice que no existe, Firestore devuelve
`FAILED_PRECONDITION` con un link directo a la consola para crearlo. La
construcción tarda de segundos a minutos según el tamaño de la
colección.

---

## Dónde se lee y dónde se escribe

| Operación | Fichero | Notas |
|-----------|---------|-------|
| Lecturas web | `packages/biwenger_tools/web/repository.py` | Cada función es una query inline — sin abstracción genérica |
| Escrituras (scraper) | `packages/biwenger_tools/scraper_job/main.py` | Dual-write CSV + Firestore vía `_write_to_firestore` |
| Backfill (one-shot) | `scripts/backfill_firestore.py` | Wipe + bulk-write desde los CSVs existentes |
| SDK | `core/sdk/firestore.py` | Sólo helpers genéricos: `get_client`, `list_documents`, `set_document`, `query`, `count`, `batch_write`, `delete_collection` |

---

## Reads esperados por página

Con el modelo + índices actuales, en visita normal:

| Página | Reads |
|--------|-------|
| `/<season>/` (comunicados) | 1 count + 7 page = **~8** |
| `/<season>/` con buscador activo | +~530 (sólo la primera vez por sesión, vía `comunicados/search-data`) |
| `/<season>/salseo` | ~600 (datos + crónicas + clausulazos + tabla_justicia) |
| `/<season>/participacion` | ~7 |
| `/<season>/mercado` | ~111 |
| `/palmares` | ~3 |

Free tier: 50.000 reads/día y 20.000 writes/día. Holgado para uso normal.

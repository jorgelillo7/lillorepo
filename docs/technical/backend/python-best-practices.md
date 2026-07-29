# Python en lillorepo — convenciones del repo

Guía de cómo se escribe Python **en este monorepo**, destilada del código que
ya funciona en producción. No es una guía genérica: cada regla existe porque
aquí hubo un motivo, y el motivo se cuenta. Si una regla deja de tener motivo,
se cambia la regla.

Complementa (no repite) a `CLAUDE.md` (flujo de trabajo, PRs, deps) y a
`.claude/CLAUDE.md` (política de comentarios). Los ejemplos citan ficheros
reales — leerlos vale más que cualquier párrafo.

---

## 1. Dónde vive cada cosa

```
core/sdk/        Clientes de servicios externos (Biwenger, JP, Telegram,
                 Firestore, GCP). Sin lógica de negocio: hablan un protocolo.
core/domain/     Modelos compartidos (dataclasses con to_firestore/from_*).
core/constants.py  Hechos de la liga que lee más de un paquete. Un dato que
                 dos paquetes escriben por separado acaba divergiendo
                 (pasó con el orden del draft: "Lucen"/"Lillo" vs
                 "Lucena"/"Jorge").
packages/*/logic/   La lógica de negocio del módulo.
packages/*/app.py   Shell HTTP plano (Flask): parsea, delega, serializa.
packages/*/scripts/ Cirugía puntual sobre Firestore (ver §7).
```

**Regla de oro de capas** — el patrón del draft es el canon:

| Capa | Ejemplo | Puede tocar |
|---|---|---|
| Lógica pura | `api/logic/draft.py` | nada: ni HTTP, ni Firestore, ni Telegram |
| Servicio | `api/logic/draft_service.py` | persistencia + clientes, orquesta la lógica pura |
| Ruta HTTP | `api/app.py` | request/response y llamar al servicio |
| Bot | `bot/app.py` | **cero lógica de negocio**: formatea y reenvía; la api responde `message` listo para enviar |

La lógica pura se testea sin mocks; el servicio con fakes pequeños; la ruta
sólo pin-ea el cableado. Si un test de lógica necesita `MagicMock`, la capa
está mal cortada.

## 2. Funciones y dataclasses antes que clases

Por defecto: funciones puras + `@dataclass` para el estado
(`DraftState`, `Pick`, `NameMatch`). Una clase sólo cuando hay estado de
sesión real que mantener (`BiwengerClient` guarda auth + `requests.Session`).
Nada de herencia entre nuestras clases; composición explícita.

## 3. Errores: ruidoso gana a silencioso

- **Un fallo callado es peor que un crash.** JP responde a un token inválido
  con HTTP 200 y `{"error": "auth"}`; eso parseaba a lista vacía y el digest
  habría corrido sin datos. La regla: valida el *payload*, no sólo el status
  (`core/sdk/jp.py::_raise_if_unhealthy`).
- **Nunca reintentar mutaciones no idempotentes.** `retry_http_request` es
  para lecturas y para escrituras con clave de idempotencia. Los endpoints
  admin de Biwenger (204 sin body, sin clave) van en POST directo con un
  comentario del porqué (`BiwengerClient._post_admin_operation`). Un retry
  ahí cobra dos veces.
- **Verificar tras escribir** cuando la API responde 204 vacío: releer el
  estado es la única confirmación que existe.
- **La idempotencia se construye en nuestro lado**: documento determinista +
  transacción de Firestore ANTES de llamar al externo
  (`draft_service._reserve_pick`). Telegram reintenta webhooks; contar con
  ello.
- En el bot, todo error de api acaba en el chat vía un único helper
  (`_report_api_error`) con `html.escape` — un mensaje de error que a su vez
  falla el parseo de Telegram deja al usuario sin feedback ninguno.

## 4. Logging

`core.utils.get_logger(__name__)` — JSON a stdout, Cloud Logging lo indexa.
Datos en `extra={...}`, nunca interpolados en el mensaje: `extra` es
filtrable (`jsonPayload.chat_id=...`), el f-string no. Sin `print` fuera de
scripts.

## 5. Docstrings, comentarios y tipos

- Política completa en `.claude/CLAUDE.md` ("no testaments"). Resumen: el
  docstring dice el **contrato**; el comentario existe sólo si el *porqué* no
  es obvio; nada de fechas, historia, ni referencias a PRs.
- Type hints en toda firma pública. `X | None` explícito cuando el default es
  `None`. Sin `Any` gratuito; sin hints en locals obvios.
- Strings de cara al usuario en **español**; código, logs y docstrings en
  inglés.

## 6. Tests

- Cada módulo tiene su target Bazel (`//packages/.../x:x_tests`); la suite
  entera es `bazel test //...` y CI la exige verde antes del deploy.
- **Spec y test son un par** (`openspec/`): un escenario sin test es un
  hueco; un test sin escenario es comportamiento sin documentar.
- Se mockea **en la frontera**, no en el interior: `FakeFirestore` en
  memoria, `MagicMock` para la sesión de Biwenger, `_run_in_background`
  parcheado a síncrono. La lógica pura no se mockea.
- Todo camino que mueve dinero tiene un test de duplicados: "la segunda
  llamada NO llega al externo"
  (`test_duplicate_applied_pick_does_not_recall_biwenger`) y "un POST fallido
  se emite exactamente una vez" (`call_count == 1`).
- Los tests no tocan la red. Si un default de config apunta a una URL, el
  fixture lo redirige a fichero local (la precedencia path-sobre-URL de
  `DRAFT_MARKET_CSV_PATH` existe para esto).

## 7. Scripts operativos

Patrón fijo (`biwenger_reset_draft.py`, `fetch_palmares.py`):

- **Dry-run por defecto, `--apply` para escribir.** Sin excepciones: el modo
  seco enseña qué haría, con recuentos.
- ADC (`gcloud auth application-default login`), nunca claves en el script.
- Bootstrap con `sys.path.insert(0, ...parents[N])` para correr desde la
  raíz del repo sin instalación.
- Si borra algo: imprimir qué conserva y por qué (el reset conserva
  `managers` y lo dice).

## 8. Trampas de este stack (aprendidas, no teóricas)

- **`requests.text` sin charset declarado decodifica ISO-8859-1** (RFC). Un
  CSV UTF-8 servido por GCS sin `content-type` pierde todos los acentos.
  Decodificar explícito: `response.content.decode("utf-8-sig")`.
- **`source .env` en bash expande `$`**: un token con `$` dentro se trunca
  en silencio. Los `.env` se leen desde Python, no desde la shell.
- **Cachés por instancia en Cloud Run**: válidas para datos congelados (el
  mercado del draft), pero re-subir el objeto NO refresca instancias
  calientes; documentarlo donde se opere.
- **`--set-env-vars` reemplaza el bloque entero** en el deploy: una env que
  deba sobrevivir va en variable de repositorio de GitHub, no puesta a mano
  en Cloud Run.
- **Ids de Telegram**: un chat con id negativo es un grupo; los ids de
  usuario son siempre positivos. No derivar uno del otro.

## 9. Dependencias

No se añaden a mano: skill `add-python-dep` (cinco capas sincronizadas).
Nunca mezclar un bump de dependencia con un PR de feature (regla de
`CLAUDE.md`). Ante la duda: ¿se puede con `requests` y la stdlib? — el draft
lee GCS con `requests` precisamente para no arrastrar
`google-cloud-storage`.

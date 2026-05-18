# Refactor: extraer la lógica de negocio a una API RESTful + rename de paquetes

> **Fecha**: 2026-05-18 (v2)
> **Estado**: pendiente de implementar — plan acordado, sin código.

## Por qué

Hoy el flujo de `/alinear` es:

```
Telegram ──webhook──→ telegram_bot (Service)
                       └── trigger_analyzer_job ──→ teams_analyzer (Cloud Run Job)
                                                     ├── cold start ~5-10s
                                                     ├── lógica de negocio
                                                     └── envía PNG/mensaje a Telegram
```

Problemas:

- **`teams_analyzer` es un Job que se usa como Service de baja latencia.** Cada
  `/alinear` paga cold start completo (~30-60s end to end). Los Cloud Run Jobs
  están pensados para batch (cron, ETL, datos masivos), no para invocación
  síncrona desde un usuario en Telegram.
- **El nombre `teams_analyzer` miente**: además de "analyze teams" también hace
  análisis de mercado y aplica alineaciones (acción que muta estado en Biwenger).
- **El nombre `telegram_bot` es demasiado genérico** ahora que tenemos otro bot
  (chucknorris). Y el display real en Telegram es "Teams Analyzer Bot", que
  refuerza la confusión.
- **Saturación del prefijo `biwenger_`**: el proyecto GCP ya se llama
  `biwenger-tools`, la ruta es `/packages/biwenger_tools/`, los subpaquetes
  `biwenger_api` / `biwenger_bot` repetirían la palabra cuatro veces antes de
  llegar al fichero. Mejor simplificar el nivel interno.
- La lógica de negocio está mezclada con el orquestador de comandos del bot, lo
  que dificulta tests y reutilización (p.ej. desde la admin web o desde un
  endpoint nuevo de recomendaciones).

## Estado objetivo

```
Telegram ──webhook──→ bot (Cloud Run Service, antes `telegram_bot`)
                       └── HTTP (ID token) ──→ api (Cloud Run Service, NUEVO)
                                                ├── REST endpoints (ver abajo)
                                                └── lógica de negocio aquí

Cloud Scheduler ──HTTP (ID token)──→ api/POST /digests/daily   (cron diario)

scraper_job (Cloud Run Job) ───────→ sigue siendo un job, esto SÍ es batch real
                                       (1 vez/semana, paginación masiva de Biwenger)
```

### Topología de despliegue

| Antes | Después |
|---|---|
| `web` (Service, `biwenger-summary`) | `web` (Service) — sin cambios |
| `telegram_bot` (Service, `biwenger-telegram-bot`) | **`bot`** (Service, `biwenger-bot`) — renombrado, ahora llama a la API |
| `chucknorris_bot` (Service) | `chucknorris_bot` (Service) — sin cambios |
| **`teams_analyzer` (Job, `biwenger-teams-analyzer`)** | **eliminado** — su contenido vive en `api` |
| | **`api`** (Service, `biwenger-api`) — NUEVO |
| `scraper_job` (Job, `biwenger-scraper-data`) | `scraper_job` (Job) — sin cambios |
| Cloud Scheduler → trigger Job | Cloud Scheduler → HTTP POST a `api/digests/daily` |
| 4 Services + 2 Jobs = 6 unidades | 5 Services + 1 Job = 6 unidades |

Mismo número de unidades desplegadas. Operativamente más simple: todo lo
síncrono es HTTP, lo asíncrono masivo (scraper) sigue siendo Job.

## Naming acordado

### Dentro de `/packages/biwenger_tools/` (paquetes locales)

Subpaquetes con nombre simple, sin reprefijar `biwenger_`. El directorio padre
ya da el contexto.

| Carpeta | Antes | Después |
|---|---|---|
| API HTTP (lógica de negocio) | — | **`api/`** |
| Bot de Telegram | `telegram_bot/` | **`bot/`** |
| Job semanal del scraper | `scraper_job/` | sin cambios |
| Web dashboard | `web/` | sin cambios |
| Cron + comandos batch viejos | `teams_analyzer/` | eliminado |

Bazel targets:
- `//packages/biwenger_tools/api:api_local`
- `//packages/biwenger_tools/bot:bot_local`
- `//packages/biwenger_tools/web:web_local`
- `//packages/biwenger_tools/scraper_job:scraper_job_local`

### Cloud Run service / job names (namespace global de GCP)

Estos sí mantienen el prefijo, son IDs globales y compiten con cualquier otro
recurso del proyecto.

| Recurso | Antes | Después |
|---|---|---|
| Web | `biwenger-summary` | `biwenger-summary` (sin cambios — coste de rename no compensa) |
| Bot | `biwenger-telegram-bot` | **`biwenger-bot`** |
| API | — | **`biwenger-api`** |
| Scraper | `biwenger-scraper-data` | `biwenger-scraper-data` (sin cambios) |
| Analyzer job | `biwenger-teams-analyzer` | eliminado |

### Display name en Telegram

Cambiar a **"Biwenger Bot"** (era "Teams Analyzer Bot") — coherencia total con
el código nuevo. Es un cambio cosmético en `@BotFather`, no requiere deploy.

### Nombres descartados

- `bff` / `backend_for_frontend` — implica un frontend tradicional; aquí los consumidores son Telegram + Scheduler, no un SPA
- `biwenger_engine` / `biwenger_actions` — más vagos que `_api`
- `core_api` — confusión con la library `/core`
- `biwenger_api` / `biwenger_bot` como nombre de paquete — redundante con la ruta padre

## API RESTful — diseño de endpoints

Convenciones:
- Inglés, recursos en plural cuando son colecciones.
- Acciones-no-CRUD viven como sub-recursos verbo (`/lineups/auto-pick`,
  `/digests/daily`). No metemos verbos como query strings.
- `GET` = lectura (incluye "enviar foto al chat" como side-effect del bot,
  porque el endpoint en sí solo lee de Biwenger/JP).
- `POST` = muta estado externo (Biwenger PUT, envío de digest programado).
- Todos los endpoints van con `--no-allow-unauthenticated` + ID token del bot
  o del Scheduler.

| Método | Ruta | Mapea a comando | Qué hace |
|---|---|---|---|
| `GET` | `/healthz` | — | Liveness |
| `GET` | `/version` | `/version` | SHA + deploy_time |
| `GET` | `/teams` | `/analizar` | Foto PNG de cada equipo (mío + rivales) + mercado |
| `GET` | `/teams/mine` | `/myteam` | Foto PNG solo de mi equipo |
| `GET` | `/market` | `/mercado` | Foto PNG del mercado |
| `POST` | `/lineups/auto-pick` | `/alinear` | Calcula mejor alineación, PUT a Biwenger, confirma por Telegram |
| `POST` | `/digests/daily` | (cron) | Mi equipo + mercado — invocado por Scheduler |
| `GET` | `/budget/recommendations` | `/recomendar` (nuevo) | Saldo + max bid + 3 fichajes/posición que podría clausular |

### Cómo manda el bot a Telegram

Decisión tomada (de la lista abierta de la v1): el **api manda directamente**
al `chat_id` (`_send_image` / `send_telegram_message` viven en core y ya son
reutilizables). El bot solo dispara la llamada HTTP y devuelve 200 a Telegram
inmediatamente. Razón: ahorra un roundtrip (api → bot → telegram pasaría por 3
saltos) y el código de envío ya está en `core/sdk/telegram.py`.

El bot sí envía los acks rápidos (`⏳ /analizar recibido, procesando…`) y los
errores que el api le devuelva por HTTP.

## Nuevo endpoint — `GET /budget/recommendations`

**Objetivo**: si me pegan uno o varios clausulazos, ¿a quién voy rápido a coger
con el dinero que voy a tener?

### Inputs

Ninguno (lee mi liga del config). Opcionalmente `?top=3` (default 3) para
afinar el número de recomendaciones por posición.

### Lógica (toda reusada)

1. `BiwengerClient._authenticate()` ya pega a `/account` y carga las ligas del
   user. Exponer `cash` y `max_bid` (campos `balance` y `maxBid` que ya devuelve
   Biwenger por liga) como propiedades del cliente o como método nuevo
   `get_account_state()`.
2. Recorrer rivales con `get_league_users` + `get_manager_squad` (igual que
   `_run_all_teams`).
3. Construir filas con `_build_squad_rows(squad, biwenger_players, jp_index,
   include_clause=True)` — ya existe, ya rellena `Clausulable` y `Cláusula`.
4. Para cada fila de rival:
   - Excluir si `Clausulable` empieza por `"No"` (locked).
   - Excluir si `clause` numérico > `max_bid`.
   - Excluir si `bw_id` está en mi propio squad.
   - Anotar `owner` (manager_name) y `multi` (lista de posiciones alternativas
     en formato corto: `["MED"]` si es DEF/MED, `[]` si monoposición).
5. Agrupar por posición **primaria** del jugador (no se duplica entre
   posiciones — multi-posición sale solo en su primary, con `multi: [...]`).
6. Ordenar por SF desc, top N (default 3) por posición.

### Output JSON

```json
{
  "budget": {
    "cash": 7000000,
    "max_bid": 35000000
  },
  "recommendations": {
    "GK":  [
      { "bw_id": 123, "name": "...", "owner": "Pepe", "clause": 12000000, "sf": 410, "multi": [] }
    ],
    "DEF": [...],
    "MID": [...],
    "FWD": [...]
  }
}
```

### Formato en Telegram (lo envía el api)

Texto, no foto. Tres bloques cortos por sección, con badge `[multi: MED/DEL]`
cuando el jugador es polivalente:

```
💰 Cash: 7,0M  ·  Max bid: 35,0M

🥅 Porteros
  · Bono (Pepe) — clausula 8,5M · SF 380
  · ...

🛡️ Defensas
  · Vivian (Ana) — clausula 12M · SF 410  [multi: MED]
  ...
```

### Comando + menú

- Bot añade `/recomendar` → `GET /budget/recommendations`.
- `setup_commands.py` del bot: nueva entrada en el array `COMMANDS`.

## Auth entre `bot` ↔ `api` y `scheduler` ↔ `api`

`api` con `--no-allow-unauthenticated`. Service accounts:

- SA del bot → `roles/run.invoker` sobre el service `biwenger-api`.
- SA del Scheduler → mismo rol.
- Cliente HTTP en el bot: `google.auth.transport.requests.Request` →
  `google.oauth2.id_token.fetch_id_token(audience)` → header
  `Authorization: Bearer <id_token>`.
- En el Scheduler, configurar `oidcToken.audience` apuntando al URL del api.

Helper compartido en `core/sdk/gcp.py` (o `core/sdk/cloud_run.py` nuevo) para
no duplicar la lógica del ID token.

## Cost / free-tier impact

Sin cambios materiales:

- Cloud Run **no tiene límite de services** por proyecto. Solo cuenta el uso
  real (vCPU-s, GiB-s, requests).
- `api` correrá con `min-instances=0` → cero coste idle.
- Cold start ~1-2s al primer hit del día. Mejora frente al cold start del Job
  actual (~5-10s).
- Operativa normal mensual estimada: <1% del free tier, igual que hoy.

## Plan de migración (por PRs, en orden)

1. **PR 1 — esqueleto del `api`**
   - Nuevo paquete `packages/biwenger_tools/api/`
   - Flask + gunicorn, mismo patrón que `web` / `bot`
   - Endpoints `GET /healthz` y `GET /version`
   - Macro `python_service` en `BUILD.bazel`
   - CI: nueva ruta en `deploy.yml` → service `biwenger-api`
   - Sin lógica de negocio todavía
   - **Pre-trabajo**: mover `_format_madrid` y `_send_image` a core
     (`core/utils.py` y `core/sdk/telegram.py` respectivamente) para que
     ambos consumidores (bot y api) los compartan sin copy-paste.

2. **PR 2 — mover la lógica del modo `daily`**
   - `_run_daily()` → `POST /digests/daily`
   - Cloud Scheduler actualizado para apuntar al endpoint HTTP con OIDC
   - El job `teams_analyzer` sigue existiendo con el resto de modos
   - Verificar 24h que el cron daily funciona

3. **PR 3 — mover los otros 4 modos del analyzer**
   - `_run_all_teams` → `GET /teams`
   - `_run_my_team`   → `GET /teams/mine`
   - `_run_market`    → `GET /market`
   - `_run_alinear`   → `POST /lineups/auto-pick`
   - `bot` ahora llama HTTP en lugar de `trigger_analyzer_job`
   - Borrar `bot/job_trigger.py` (queda un cliente HTTP minimal)

4. **PR 4 — nuevo endpoint `/budget/recommendations`**
   - Implementación + tests unitarios del filtro/orden
   - `BiwengerClient.get_account_state()` (cash + max_bid)
   - Bot añade comando `/recomendar`
   - `setup_commands.py` regenerado

5. **PR 5 — rename `telegram_bot` → `bot` y eliminación de `teams_analyzer`**
   - Mover `packages/biwenger_tools/telegram_bot/` → `packages/biwenger_tools/bot/`
   - Borrar `packages/biwenger_tools/teams_analyzer/`
   - Actualizar imports, `BUILD.bazel`, `deploy.yml`
   - Renombrar Cloud Run service `biwenger-telegram-bot` → `biwenger-bot` (es
     destructivo: borrar y recrear, reconfigurar webhook de Telegram a la URL
     nueva)
   - Borrar Cloud Run Job `biwenger-teams-analyzer` (manual)
   - Limpiar secrets binding del job (manual)
   - Cambiar display name del bot en `@BotFather` a "Biwenger Bot"
   - Es el último PR para no acumular fricción mid-refactor

6. **PR 6 — sweep final**
   - READMEs de cada subpaquete actualizados
   - `docs/operations.md` con los comandos nuevos
   - `.claude/plans/next_phases.md` actualizado
   - Buscar referencias rotas: `grep -r teams_analyzer`, `grep -r telegram_bot`,
     `grep -r trigger_analyzer_job`
   - **Skill `google-cloud-waf-cost-optimization`** sobre el repo: revisar que
     el cambio (1 Job → 1 Service más) no rompe el presupuesto €1/mes ni los
     umbrales del free tier. Documentar conclusiones en `docs/gcp.md` si hay
     ajustes.
   - **Verificar `scripts/check-gcp-costs.sh`**: ejecutarlo y comprobar que
     reconoce el nuevo service `biwenger-api`, los renames (`biwenger-bot`)
     y que ya no espera el job `biwenger-teams-analyzer`. Ajustar el script
     si la lista de servicios/jobs esperados está hardcoded.
   - **Verificar `scripts/clean-images-artifact.sh`**: ejecutarlo y comprobar
     que limpia tanto las imágenes viejas del `biwenger-teams-analyzer`
     (huérfanas tras el borrado del Job) como que reconoce las nuevas (`biwenger-api`).
     Añadir `biwenger-api` al array `SIMPLE_IMAGES` o equivalente si hace falta.
   - **Release notes (`release-notes` skill)**: generar entry resumiendo el
     refactor (de v5.X a v6.0 o lo que toque) — antes de borrar el plan.
   - Borrar este plan (`.claude/plans/biwenger_api_refactor.md`)

## Reuso de código — checklist

Para que el api no se reinvente nada:

- [x] `core/sdk/biwenger.py` — cliente completo, ya cubre todo lo que necesita el api
- [x] `core/sdk/jp.py` — `fetch_all_players`, `get_predict_rate`, `check_api_health`
- [x] `core/sdk/telegram.py` — `send_telegram_message`, `send_telegram_photo`, `parse_command`, etc.
- [x] `packages/biwenger_tools/teams_analyzer/logic/` — `image_formatter.py`, `lineup.py`, `player_matching.py` se mueven **tal cual** a `packages/biwenger_tools/api/logic/`
- [x] `packages/biwenger_tools/teams_analyzer/player_formatting.py` → `packages/biwenger_tools/api/player_formatting.py`
- [x] `packages/biwenger_tools/teams_analyzer/main.py` → handlers Flask en `api/app.py`, una función pública por endpoint, todas reutilizan `_build_row`, `_build_squad_rows`, `_build_market_rows`
- [ ] `_format_madrid` (hoy en `telegram_bot/app.py`) → `core/utils.py` (lo necesitan ambos `/version`)
- [ ] Nuevo: `BiwengerClient.get_account_state()` para el endpoint `/budget/recommendations`
- [ ] Nuevo: helper de ID token en `core/sdk/` para que el bot autentique al api sin duplicar

## ¿Falta mover algo a core para los bots?

Revisado en la v2. Estado actual:

- Ambos bots (`telegram_bot` y `chucknorris_bot`) **ya tienen menú** vía
  `setup_commands.py` y los helpers en `core/sdk/telegram.py`.
  - `register_bot_commands` ✅
  - `set_commands_menu_button` ✅
  - Si en Telegram ves el menú en uno y no en el otro, es estado del lado
    Telegram (un `setMyCommands` se hizo y otro no), no código que falte.
- Patrón duplicado entre los dos `app.py`: validar secret → extraer chat/text
  → parsear cmd → despachar. Son ~15 líneas. Extraer un mini "BotRunner" a
  core para 2 bots es over-engineering. **No tocar**.
- Sí extraer: `_format_madrid` y, si lo necesita el api, un `bot_runner`
  solo si en el futuro aparece un tercer bot.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Rotura del `/alinear` durante la migración | Mover modo por modo, validar cada uno antes de pasar al siguiente |
| URL del webhook de Telegram cambia al renombrar el bot | Se hace en el último PR; `setWebhook` con la URL nueva el mismo día |
| Tests existentes del `teams_analyzer` no aplican tras el refactor | Reescribir como tests HTTP del `api` con `pytest`+`flask.test_client` (mismo patrón que `web_tests`) |
| Cron de Scheduler apunta al job viejo durante una ventana | Actualizar Scheduler **antes** de eliminar el job (PR 2) |
| `trigger_analyzer_job` deja de existir | Reemplazado por cliente HTTP simple (`requests` + ID token) en el bot |
| Multi-posición duplica jugadores en `/budget/recommendations` | Agrupamos por **primary** position, `multi: [...]` solo es metadato. Test unitario explícito |
| `max_bid` de Biwenger devuelve 0 / no disponible para alguna liga | Fallback a `cash`; log warning |

## Rollback

Cada PR es independiente y reversible:

- PR 1 reverso: borrar el service (no había consumidores)
- PR 2 reverso: restaurar el Scheduler al job, mantener endpoint en paralelo
- PR 3 reverso: el bot vuelve a `trigger_analyzer_job` (el job sigue vivo)
- PR 4 reverso: borrar comando del bot + endpoint
- PR 5 es el punto de no retorno — solo cuando 1-4 están en producción
  validados al menos 1 semana

## Estado actual de la conversación

- Acuerdo sobre la dirección.
- Acuerdo sobre los nombres: paquetes locales en simple (`api/`, `bot/`),
  Cloud Run con prefijo (`biwenger-api`, `biwenger-bot`).
- Acuerdo en cambiar display name a "Biwenger Bot".
- Acuerdo en API RESTful en inglés con la tabla de arriba.
- Acuerdo en añadir endpoint `/budget/recommendations` (PR 4).
- Acuerdo en que `teams_analyzer` desaparece.
- Acuerdo en que el api manda fotos al chat directamente (no roundtrip por el bot).
- No hay urgencia — sistema funciona. Arrancamos cuando haya tiempo.

## Decisiones aún abiertas

- ¿Qué exactamente cuenta como "jugadores a evitar" para la lógica del
  max_bid? La respuesta de Biwenger en `/account` ya da un `maxBid`
  calculado por ellos; con eso es suficiente para v1 y no necesitamos
  meter heurística propia ("vender baja SF" etc.). Revisitar tras 2-3
  usos reales.
- ¿Mantener `biwenger-summary` como nombre del Cloud Run service de la web,
  o aprovechar el sprint para renombrarlo a `biwenger-web`? Por defecto
  **no** se renombra (es destructivo: requiere redeploy + actualizar DNS
  custom si lo hubiera).

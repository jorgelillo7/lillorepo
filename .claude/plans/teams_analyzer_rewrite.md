# Plan: Reescritura de teams_analyzer con JP API

## Contexto

Descubrimos la API privada de Jornada Perfecta mediante Frida + emulador Android (API 33, ARM64).
La app es React Native. El endpoint devuelve puntuaciones predictivas por jugador para el próximo
partido, calculadas por ABACODEV usando datos de Sofascore.

También hemos reverse-engineado el endpoint de alineación de Biwenger vía DevTools del navegador.

---

## Fases

| Fase | Scope | Dependencias |
|------|-------|-------------|
| 1 | Reescritura core: JP API + eliminar Selenium/AF + output Telegram | Ninguna |
| 2 | Telegram bot interactivo: recibir comandos | Fase 1 |
| 3 | Auto-alineación Biwenger desde Telegram | Fase 2 + investigar multi-posición |

---

## API de Jornada Perfecta (reverse-engineered)

### Endpoint principal

```
GET https://www.jornadaperfecta.com/api/fitness-daily
```

### Headers (imitar la app móvil)

```
accept: application/json, text/plain, */*
user-agent: AppBlog/Android
```

### Parámetros

| Parámetro     | Valor         | Descripción                                        |
|---------------|---------------|----------------------------------------------------|
| `auth`        | `lks9k2k$iJK` | Token fijo de la app (no cambia entre sesiones)    |
| `competition` | `1`           | LaLiga (ver tabla abajo)                           |
| `score`       | `2`           | Sistema de puntuación (ver tabla abajo)            |
| `offset`      | `0`           | Paginación — siempre 0 para coger todo             |
| `limit`       | `600`         | 546 jugadores activos; 600 cubre con margen        |
| `order`       | `priceIncrement` | Campo de ordenación                             |
| `orderBy`     | `desc`        | Dirección de orden                                 |
| `playerStatus`| `all`         | Incluir lesionados/dudas/sancionados               |
| `showPredict` | `true`        | **CRÍTICO** — activa el array `predict` con rates  |

### Competiciones disponibles (`competition`)

| ID | Nombre   |
|----|----------|
| 1  | LaLiga   |
| 4  | Premier  |
| 6  | Segunda  |

### Sistemas de puntuación (`score` y `predict.type`)

| type | Sistema            |
|------|--------------------|
| 1    | Picas Diario AS    |
| 2    | **SofaScore** ← el del Automanager |
| 16   | Media AS + SofaScore |
| 19   | LaLiga Fantasy     |

### Estructura de respuesta

```json
{
  "meta": {
    "total": 546,
    "competition": 1,
    "score": 2
  },
  "players": [
    {
      "id": 38216,
      "name": "Roony",
      "slug": "roony",
      "teamID": 5,
      "teamRemote": 3,
      "position": 4,
      "price": 3200000,
      "lfm_price": 2009567,
      "fantasyPrice": 8000000,
      "status": "ok",           // "ok" | "injured" | "doubt" | "suspended"
      "statusInfo": "",          // texto libre si hay novedad
      "estimatedReturn": "",     // fecha estimada de vuelta si lesionado
      "priceIncrement": 380000,  // subida/bajada precio Biwenger hoy
      "priceIncrementLF": 109120,
      "playedHome": 12,
      "playedAway": 6,
      "fitness": "3,4,,,",       // últimas 5 jornadas (puntos SofaScore)
      "fitnessAvg": "1.40",      // media últimas 5 jornadas
      "points": 55,              // puntos acumulados temporada (score=2 → SofaScore)
      "pointsHome": 32,
      "pointsAway": 23,
      "pointsLastSeason": 0,
      "streak": 4,               // racha actual
      "predict": [
        { "type": 1,  "rate": 208, "updated_at": 1777730275 },
        { "type": 2,  "rate": 178, "updated_at": 1777730275 },  // ← Automanager
        { "type": 16, "rate": 204, "updated_at": 1777730275 },
        { "type": 19, "rate": 149, "updated_at": 1777730275 }
      ],
      "nextMatch": {
        "id": 12310,
        "isLocal": false,
        "rivalTeamId": 15,
        "rivalTeamIdRemote": 93,
        "playerInLineup": true,  // ¿se espera que juegue?
        "status": "pending"      // "pending" | "break" (no hay partido)
      }
    }
  ]
}
```

### Verificación de los números del Automanager

- Roony → `predict[type=2].rate` = **178** ✓
- Gonzalo García → `predict[type=2].rate` = **141** ✓
- Vini Jr → `predict[type=2].rate` = **910** (top del juego)
- Sin partido (`nextMatch.status = "break"`) → no aparece en predict

### Llamada de prueba rápida

```python
import requests

r = requests.get(
    "https://www.jornadaperfecta.com/api/fitness-daily",
    headers={"accept": "application/json", "user-agent": "AppBlog/Android"},
    params={
        "auth": "lks9k2k$iJK",
        "competition": "1",
        "score": "2",
        "offset": "0",
        "limit": "600",
        "playerStatus": "all",
        "orderBy": "desc",
        "order": "priceIncrement",
        "showPredict": "true",
    }
)
players = r.json()["players"]  # lista de 546 jugadores
jp_map = {p["slug"]: p for p in players}  # dict slug → player
```

---

## Endpoints secundarios descubiertos

```
GET https://www.jornadaperfecta.com/active-competitions?auth=lks9k2k$iJK
```
Devuelve las competiciones activas con jornada actual/total.

```
GET https://www.jornadaperfecta.com/tracking?secure=lks9k2k$iJK&limit=10&offset=0&competition=1
```
(Pendiente de analizar respuesta — posiblemente tracking de partidos)

---

## API de Biwenger — Alineación (reverse-engineered)

### Endpoint

```
PUT https://biwenger.as.com/api/v2/user?fields=*,lineup(date)
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

El token Bearer es el mismo que obtiene `BiwengerClient` en el login.

### Request body

```json
{
  "lineup": {
    "type": "4-5-1",
    "playersID": [257, 37495, 23840, 23403, 1074, 10139, 1612, 39360, 32338, 20102, 3159],
    "reservesID": [null, null, null, 19577],
    "captain": 39360
  }
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `type` | string | Formación (ej: "4-5-1", "3-5-2") |
| `playersID` | int[] | 11 IDs de titulares, ordenados por posición según formación |
| `reservesID` | (int\|null)[] | Suplentes; `null` para huecos vacíos |
| `captain` | int | ID del capitán (debe estar en `playersID`) |

### Response (200 OK)

```json
{
  "status": 200,
  "data": {
    "name": "Farolillo Oracle United ⭐️",
    "lineup": { "date": 1777761874 }
  }
}
```

### Formaciones disponibles

3-4-3, 3-5-2, 4-3-3, 4-4-2, 4-5-1, 5-3-2, 5-4-1, 3-6-1, 3-3-4, 4-2-4, 4-6-0, 5-2-3

---

## FASE 1 — Reescritura core

### Objetivo

Script que:
1. Descarga todos los jugadores JP (una sola petición HTTP)
2. Lee mi equipo actual de Biwenger + equipos rivales + mercado del día
3. Cruza los datos JP por nombre normalizado
4. Envía resumen formateado a Telegram (múltiples mensajes de texto)

### Arquitectura

```
teams_analyzer/
  logic/
    jp_client.py          # NUEVO: cliente JP API
    player_matching.py    # ADAPTAR: matching Biwenger ↔ JP por nombre normalizado
    scrapers.py           # ELIMINAR ENTERO
  teams_analyzer.py       # REESCRIBIR: orquestador principal
  telegram_formatter.py   # NUEVO: formatea mensajes Telegram
  config.py               # ACTUALIZAR: añadir JP config, quitar AF/JP web URLs
```

### Matching Biwenger ↔ JP

Estrategia: normalizar nombres de ambas fuentes y matchear.

- **Biwenger** → campo `name` del player (ej: "Vinícius Júnior")
- **JP** → campo `name` del player (ej: "Vini Jr") + campo `slug` como fallback

Reutilizar `normalize_name()` (unidecode + lowercase + strip). Adaptar `find_player_match()`
para buscar en el mapa JP en vez del mapa AF. La lógica de 4 tiers (directo, mappings manuales,
transformaciones automáticas, subset) sigue siendo válida — solo cambia el mapa destino.

Construir el mapa JP indexado por nombre normalizado:
```python
jp_map = {normalize_name(p["name"]): p for p in jp_players}
```

### jp_client.py

```python
JP_URL = "https://www.jornadaperfecta.com/api/fitness-daily"
JP_AUTH = "lks9k2k$iJK"
JP_HEADERS = {"accept": "application/json", "user-agent": "AppBlog/Android"}

def fetch_all_players(competition=1, score_type=2) -> list[dict]:
    """Devuelve lista completa de jugadores JP."""

def get_predict_rate(player: dict, score_type=2) -> int | None:
    """Extrae rate de predict para score_type. None si no hay partido."""

def check_api_health():
    """Lanza RuntimeError si la API no responde o el token ha rotado."""
```

### config.py — cambios

Añadir:
```python
JP_AUTH_TOKEN = "lks9k2k$iJK"
JP_COMPETITION = 1  # LaLiga
JP_SCORE_TYPE = 2   # SofaScore (Automanager)
```

Eliminar:
```python
# JORNADA_PERFECTA_MERCADO_URL  (scraping web viejo)
# ANALITICA_FANTASY_URL         (Selenium)
# BACKUP_COEFFS_CSV             (ya no se genera)
```

### Posiciones

Usar la posición de **Biwenger** (campo `positionId`). Biwenger soporta multi-posición
en la web pero el campo API actual devuelve solo una. Investigar en Fase 3 si hay campo
extra de posiciones secundarias.

El `map_position()` actual sigue válido. Mover a un sitio compartido si se usa en Fase 3.

### Datos a mostrar por jugador

| Campo          | Fuente    | Descripción                              |
|----------------|-----------|------------------------------------------|
| Nombre         | Biwenger  | Nombre oficial                           |
| Posición       | Biwenger  | POR/DEF/MED/DEL                          |
| Precio         | Biwenger  | Valor actual en millones                 |
| Estado         | JP        | ok / injured / doubt / suspended         |
| Juega          | JP        | `nextMatch.playerInLineup`               |
| Predict AS     | JP        | `predict[type=1].rate`                   |
| Predict SF     | JP        | `predict[type=2].rate` ← Automanager    |
| Predict Media  | JP        | `predict[type=16].rate`                  |
| Streak         | JP        | racha últimas jornadas                   |
| Fitness        | JP        | últimas 5 jornadas                       |
| fitnessAvg     | JP        | media últimas 5 jornadas                 |
| priceIncrement | JP        | subida/bajada de hoy                     |

### Output Telegram

Enviar **múltiples mensajes de texto** (via `sendMessage` con `parse_mode=HTML`).
Límite Telegram: 4096 chars por mensaje. Partir por sección:

1. **Mensaje 1 — MI EQUIPO** (titulares ordenados por predict SF desc)
2. **Mensaje 2 — MERCADO** (top 10 por predict SF)
3. **Mensajes 3..N — RIVALES** (un mensaje por rival si cabe, o agrupar)

Formato por jugador (compacto para iPhone):
```
🟢 Vini Jr (DEL) · 42M · ⬆️380K
  SF:910 | AS:850 | Avg:880 | Racha:11
  Juega: ✅ fuera vs Betis
```

Indicadores:
- 🟢 predict SF ≥ 300
- 🟡 predict SF 100–299
- 🔴 lesionado / no juega / predict SF < 100

### SDK Telegram — cambios en core

Añadir función en `core/sdk/telegram.py`:
```python
def send_telegram_message(bot_token: str, chat_id: str, text: str, parse_mode: str = "HTML") -> None:
    """Envía mensaje de texto a Telegram via sendMessage."""
```

### Eliminar Selenium / AF

Archivos a modificar:
- **Eliminar**: `logic/scrapers.py` (entero)
- **Eliminar**: `analitica_fantasy_data_backup.csv`
- **Eliminar**: `tests/test_scrappers.py`
- **Actualizar**: `tests/test_team_analyzer.py` (adaptar al nuevo orquestador)
- **Actualizar**: `tests/test_player_matching.py` (adaptar al mapa JP)
- **Actualizar**: `requirements.txt` — quitar `selenium`, `webdriver-manager`, `beautifulsoup4`
- **Regenerar**: `requirements.in` → `requirements_lock.txt`
- **Actualizar**: `BUILD.bazel` — quitar deps `@pypi//selenium`, `@pypi//webdriver_manager`, `@pypi//beautifulsoup4`
- **Simplificar imagen Docker** en `BUILD.bazel`: quitar Chromium, X11 libs, usar imagen base ligera
- **Rebuild + push** imagen Docker a GCP

### Orden de implementación Fase 1

1. `jp_client.py` — cliente JP con health check
2. Actualizar `config.py`
3. Adaptar `player_matching.py` para mapa JP
4. Añadir `send_telegram_message()` a `core/sdk/telegram.py`
5. `telegram_formatter.py` — formatear mensajes por sección
6. Reescribir `teams_analyzer.py` — orquestador
7. Eliminar `scrapers.py` y archivos AF
8. Actualizar tests
9. Limpiar deps: `requirements.txt` → `requirements.in` → `requirements_lock.txt`
10. Actualizar `BUILD.bazel` (deps + imagen Docker)
11. Rebuild + push imagen base a GCP

### Dependencias

**Nuevas:** ninguna
**Eliminar:** `selenium`, `webdriver-manager`, `beautifulsoup4`
**Mantener:** `requests`, `python-dotenv`, `unidecode`

---

## FASE 2 — Telegram bot interactivo (pendiente)

### Objetivo

Recibir comandos en el canal de Telegram para ejecutar acciones on-demand.

### Comandos

| Comando | Acción |
|---------|--------|
| `/analizar` | Ejecutar análisis completo y enviar resultado |
| `/alinear` | Auto-alineación con datos JP (Fase 3) |

### Arquitectura — opciones a evaluar

**Opción A: Webhook en el Flask web existente** (recomendada)
- El web ya corre en Cloud Run (siempre activo)
- Añadir ruta `/telegram/webhook` que recibe updates
- Registrar webhook con `POST https://api.telegram.org/bot{token}/setWebhook`
- Pro: no añade infra nueva
- Con: acopla el bot al web

**Opción B: Cloud Run service dedicado**
- Servicio separado que recibe webhooks
- Escala a 0 cuando no hay comandos
- Pro: aislado
- Con: más infra

**Opción C: Polling en Cloud Run Job**
- Job que hace long-polling con `getUpdates`
- No requiere URL pública
- Con: no es on-demand, requiere job corriendo

### Pendiente de decidir

- Qué opción elegir
- Si el bot necesita estado (ej: último análisis cacheado)
- Rate limiting de comandos

---

## FASE 3 — Auto-alineación Biwenger (pendiente)

### Objetivo

Comando `/alinear` que lee el equipo de Biwenger, cruza con datos JP, elige el
mejor XI posible, selecciona capitán y aplica la alineación.

### API disponible

```
PUT https://biwenger.as.com/api/v2/user?fields=*,lineup(date)
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "lineup": {
    "type": "4-5-1",
    "playersID": [id1, ..., id11],
    "reservesID": [null, ..., idN],
    "captain": idX
  }
}
```

### Lógica de auto-alineación

1. Obtener squad propio de Biwenger (IDs de jugadores)
2. Obtener datos JP de todos los jugadores
3. Cruzar por nombre normalizado
4. Filtrar jugadores disponibles (status != injured/suspended, nextMatch.status == pending)
5. Para cada formación posible:
   - Asignar mejores jugadores por posición según predict SF
   - Calcular score total del XI
6. Elegir la formación con mayor score total
7. **Capitán**: priorizar jugadores con precio < 3M (puntúan doble), entre ellos el de mayor predict SF
8. Enviar PUT a Biwenger
9. Confirmar por Telegram con el XI elegido

### Pendiente de investigar

- **Multi-posición**: ¿la API de Biwenger devuelve posiciones secundarias en algún campo?
  Si no, habrá que mantener un mapping manual o scrapearlo de otro sitio.
- **Orden de playersID**: ¿importa el orden dentro de la formación? Investigar con
  varias pruebas (probablemente: POR → DEF → MED → DEL).
- **Validación server-side**: ¿Biwenger valida que los jugadores encajen en la formación?
  Probar con una alineación inválida para ver el error.

### Añadir al SDK Biwenger

```python
def set_lineup(self, formation: str, players: list[int], reserves: list[int | None], captain: int) -> dict:
    """Establece alineación. Devuelve response de la API."""
```

---

## Notas de seguridad / rate limiting

- El token `lks9k2k$iJK` es el token hardcoded de la app. Si JP lo rota habrá que
  volver a interceptar con Frida.
- Una sola llamada con limit=600 es suficiente — no hacer polling agresivo.
- User-agent `AppBlog/Android` + header `accept` son los que usa la app real.
- No hay autenticación de usuario — el endpoint es público con token fijo.

---

## Resiliencia del token — cómo recuperarlo si rota

### Dónde vive el token

El token está **hardcoded en el bundle JavaScript** del APK (`assets/index.android.bundle`),
no es un token de sesión. Solo cambia si JP lanza una nueva versión de la app y lo rota
deliberadamente — algo costoso para ellos y poco frecuente.

### Extracción sin Frida (< 1 minuto)

Si el token deja de funcionar, basta con descargar el APK nuevo de APKPure o Uptodown y ejecutar:

```bash
unzip -p com.ideatic.jornadaperfecta.apk assets/index.android.bundle \
  | strings | grep -o 'lks9k2k[^ "&]*'
```

El patrón `lks9k2k` es el prefijo actual — si cambia por completo, buscar por contexto:

```bash
unzip -p com.ideatic.jornadaperfecta.apk assets/index.android.bundle \
  | strings | grep -o '"auth":"[^"]*"' | sort -u
```

No hace falta emulador ni Frida para esta operación.

### Health check en el script

Añadir al arranque de `jp_client.py`:

```python
def check_api_health():
    """Lanza RuntimeError si la API no responde o el token ha rotado."""
    r = requests.get(JP_URL, headers=JP_HEADERS, params={**JP_BASE_PARAMS, "limit": "1"})
    if r.status_code != 200 or not r.json().get("players"):
        raise RuntimeError(
            f"JP API no responde (HTTP {r.status_code}) — token posiblemente rotado. "
            "Descargar APK nuevo y extraer token con: "
            "unzip -p app.apk assets/index.android.bundle | strings | grep -o 'lks9k2k[^ \"&]*'"
        )
```

# 📸 my_photos — brainstorming + plan

> **Estado**: brainstorming validado con datos reales. Plan v1 pendiente de
> confirmar. No hay código todavía.
> **Última sesión**: 2026-05-17.

## 1. Contexto

Flujo 100 % manual durante años + cambio de Google Photos compartido a fototeca
compartida iCloud que **no se completó**. Resultado: backlog de fotos sin
organizar y procrastinación crónica.

Objetivo doble:
1. Cerrar el backlog actual (one-off).
2. Tener herramientas para que el día a día no se vuelva a romper.

## 2. Inventario (con datos reales)

### Hardware

| Equipo | Notas |
|---|---|
| Mac M1 | **No encendido 24/7** — descarta cualquier "demonio local always-on" |
| iPhone 14 (Jorge) | iCloud Photos activo |
| iPhone 12 mini (mujer) | Fototeca compartida iCloud |
| iPad Pro | Lectura |
| Disco duro antiguo | Histórico desde 2014 con convención `YYYY-MM-DD nombre evento` |
| **Disco duro nuevo: 5 TB, vacío** | El que vamos a usar de aquí en adelante |

### Suscripciones y uso real

| Servicio | Coste | Plan | Uso real | Decisión |
|---|---|---|---|---|
| **Google One** | ~20 €/mes | **5 TB familiar** | 9.91 GB total (6.21 Fotos · 2.68 Drive · 1.02 Gmail) | **CANCELAR** (user lo va a hacer; reemplaza Gemini por Claude) |
| iCloud+ | 2-3 €/mes | 200 GB | **26.89 GB** (3 933 fotos + 598 vídeos) — 13 % del plan | Mantener. **No hace falta subir cuota** |
| Amazon Prime | 50 €/año | Fotos ilimitadas (NO vídeos) | Backup secundario | Mantener |
| Claude Pro | 20 €/mes | — | IA general | Mantener |

**Coste neto tras cancelar Google One**: −20 €/mes / **−240 €/año**. Sin
contraparte: con 26.89 GB de fototeca real, los 200 GB de iCloud sobran.

### Flujo actual (manual hoy)

```
iPhone Jorge ─┐
iPhone Mujer ─┴─→ iCloud (fototeca compartida) ─→ app Fotos en Mac
                                                       │ "Download Originals"
                                                       ▼
                                          Disco duro viejo
                                          /YYYY-MM-DD nombre evento/
                                                       │ (solo fotos)
                                                       ▼
                                              Amazon Photos
```

## 3. Hallazgos clave

1. **Google Photos no es la fuente principal**: solo 6.21 GB. Lo que sobreviva
   ahí es lo de los antiguos álbumes compartidos. Trivial de migrar antes de
   cancelar Google One.
2. **iCloud es la fuente real** de la fototeca actual: **26.89 GB** (3 933
   fotos + 598 vídeos). Bien dentro del plan de 200 GB; sin upgrade necesario.
3. **Vídeos**: el user acepta que vivan solo en iCloud + disco duro (sin
   Amazon). Simplifica el backup secundario.
4. **Mac no 24/7** + "trigger manual cuando estemos" → **no necesitamos cron
   ni Cloud Run permanente**. Todo puede ser **CLI local + bot Telegram que
   pollee solo cuando el Mac está encendido**. Cero coste cloud para esto.
5. **"Cowork"** = **Claude Code / Claude desktop**, no Immich. Por tanto la
   herramienta principal de gestión va a ser **Claude Code + scripts CLI en
   este monorepo**, no un visor self-hosted aparte.

## 4. Decisión por decisión

### Nube primaria
- **iCloud Photos** (Apple ecosystem, fototeca compartida ya configurada).
- **Plan 200 GB se mantiene**: 26.89 GB / 200 GB = 13 % de uso. Sin upgrade.

### Nube secundaria (backup)
- **Amazon Photos** para fotos (gratis con Prime que ya tiene).
- **Vídeos solo en iCloud + disco**, sin tercer backup.

### Backup local "fuente de verdad fría"
- **Disco duro nuevo de 5 TB** (vacío).
- Mantener convención `YYYY-MM-DD nombre evento/`.

### Visor / gestor
- Apple Photos en iPhone/iPad/Mac. **No Immich** — añade superficie de error
  para cero ganancia neta ahora.

### Automatización
- **Trigger manual**. No cron, no scheduled jobs.
- **Bot Telegram que corre en el Mac cuando está encendido** (polling, no
  webhook). Para ambos (Jorge + mujer).
- Ejecución del trabajo pesado: **scripts CLI locales** que Claude Code puede
  ejecutar directamente, o el bot Telegram puede disparar.

### Cancelación de Google One
- **Antes** de cancelar: dump completo de Google Photos (6.21 GB, rápido).
- **Después** del dump y verificación: cancelar el plan, borrar fotos
  remanentes de Google Photos.
- Calendario sugerido: una sola tarde, no se hace en piezas.

## 5. Plan v1 — sprint 1 (limpieza one-off)

> Objetivo: dejar el disco duro nuevo como **fuente de verdad fría** unificada,
> con todo el histórico volcado y organizado por `YYYY-MM-DD evento/`, antes
> de cancelar nada.

| Paso | Acción | Herramienta |
|---|---|---|
| 1 | Inventario inicial: medir tamaño real iCloud, fototeca local en Mac, Google Photos, Amazon Photos, disco viejo, disco nuevo | `du -sh`, app Fotos, Google One UI |
| 2 | Copiar **disco viejo → disco nuevo** tal cual (rsync con verificación) | `rsync -av --progress` |
| 3 | Volcar **Google Photos → disco nuevo** preservando álbumes | `gphotos-sync` |
| 4 | Volcar **iCloud → disco nuevo** (lo que aún no esté). `icloudpd` con `--until-found` baja sólo lo nuevo. Confirmado que la biblioteca local del Mac está en "Optimizar almacenamiento", así que no sirve `osxphotos` para esto | `icloudpd` |
| 5 | Detectar duplicados y normalizar convención `YYYY-MM-DD evento/` | `exiftool` + script de organización (parte de este paquete) |
| 6 | Subir lo nuevo (lo que no estaba) a **Amazon Photos** | Cliente Amazon Photos Mac o `rclone` |
| 7 | Verificar que todo está en disco nuevo + Amazon | Script de checksum + comparación |
| 8 | **Cancelar Google One**; borrar fotos remanentes de Google Photos | manual |

## 6. Plan v1 — sprint 2 (herramientas día a día)

> Objetivo: que el flujo mensual sea "enciendo el Mac, le doy a `/photos-sync`
> en Telegram, espera 10 min, recibo confirmación".

| Pieza | Descripción |
|---|---|
| **CLI `lillophotos sync`** | Wrapper sobre `icloudpd` que descarga lo nuevo de iCloud al disco nuevo, lo organiza con exiftool en `YYYY-MM-DD/` |
| **CLI `lillophotos organize <dir>`** | Renombra una carpeta nueva siguiendo la convención y mueve los archivos |
| **CLI `lillophotos backup-amazon`** | Sube al cliente de Amazon Photos lo nuevo (o, si no hay CLI oficial, recordatorio + abre la app) |
| **CLI `lillophotos status`** | Muestra: último sync · tamaño de cada destino · fotos sin organizar |
| **Bot Telegram `photos_bot`** | Endpoints `/photos-sync`, `/photos-status`, `/photos-organize <carpeta>`. Single-tenant (lista de `chat_id` de Jorge + mujer). **Polling, no webhook** — corre en el Mac cuando está encendido. Comparte código con `core/sdk/telegram.py` |

**No** vamos a:
- Desplegar en Cloud Run (sin sentido para trigger manual).
- Programar cron (queremos trigger manual).
- Self-hostear Immich/PhotoPrism (cero ganancia con Apple Photos como visor).
- Tocar la sincronización cloud (iCloud lo hace solo).

## 7. Open questions

1. ~~**Modo de la fototeca en el Mac**~~ — **resuelto**: tanto el iPhone como
   el Mac están en "Optimizar almacenamiento". La biblioteca local no contiene
   todos los originales. Por tanto el volcado one-off va con **`icloudpd`**
   contra los servidores de iCloud, no con `osxphotos` contra la biblioteca
   local.
2. ~~**Mujer y disco duro**~~ — **resuelto** (2026-05-17): misma casa, mismo
   acceso al disco. El bot puede asumir que cualquiera de los dos puede
   disparar `/photos-sync`, no hace falta lógica de "esperar al dueño".
3. **App Amazon Photos desde CLI**: que yo sepa **no hay CLI oficial**.
   Alternativas: dejar el cliente desktop corriendo (auto-upload de la carpeta
   del disco), o usar `rclone` con WebDAV si Amazon lo expone (no creo).
   Investigaremos en el sprint 2.

## 8. Próximo paso

Si te suena bien este plan, doy luz verde a:
1. Commitear este README + abrir PR (sin código todavía).
2. Empezar **paso 1 del sprint 1** (inventario de tamaños) — yo escribo un
   script `scripts/inventory.sh` que mide todo. Lo corres tú y me pegas los
   números.

A partir de esos números calibramos el resto: si iCloud está en 80 GB, no hay
upgrade ni urgencia. Si está en 180 GB, sprint 1 se acelera para no quedarse
sin espacio.

## 9. Lo que NO hace este paquete (acotado para no perderse el alcance)

- No es un visor de fotos (Apple Photos lo hace).
- No es una nube (iCloud lo hace).
- No reemplaza la sync iPhone → iCloud (Apple lo hace).
- No corre 24/7.
- No edita fotos.

Es solo: **descargar, organizar, hacer backup secundario, dar visibilidad**.

## 10. Fuentes consultadas

- [Apple Community — Photo library management best practices 2026](https://ask.metafilter.com/389706/Photo-library-management-best-practices-in-2026)
- [Photo Backup Strategy 2026 — Alex Smale](https://www.alexsmale.co.uk/photo-backup-strategy-2026-icloud-google-photos-nas-or-both/)
- [iCloud Photos is not a backup — 9to5Mac](https://9to5mac.com/guides/icloud-photos/)
- [icloudpd — CLI to download iCloud Photos](https://github.com/icloud-photos-downloader/icloud_photos_downloader)
- [gphotos-sync — Google Photos backup CLI](https://github.com/gilesknap/gphotos-sync)
- [osxphotos — Export Apple Photos library](https://github.com/RhetTbull/osxphotos)
- [ExifTool — bulk rename + organize by EXIF date](https://exiftool.org/)

# 📸 my_photos — brainstorming + plan

> **Estado**: plan v2 validado. No hay código todavía.
> **Última sesión**: 2026-07-11.

## 1. Contexto

Flujo 100 % manual durante años + cambio de Google Photos compartido a fototeca
compartida iCloud que **no se completó**. Resultado: backlog de fotos sin
organizar y procrastinación crónica.

Objetivo doble:
1. Cerrar el backlog actual (one-off).
2. Tener herramientas para que el día a día no se vuelva a romper.

Criterio de diseño transversal: **pereza**. Cada pieza del plan se evalúa por
cuántas decisiones y pasos manuales le quita al usuario, no por lo completa
que sea.

## 2. Inventario (con datos reales)

### Hardware

| Equipo | Notas |
|---|---|
| Mac M1 | **No encendido 24/7**, y solo **19 GB libres** de 228 GB — descarta demonios always-on y cualquier staging local de la fototeca |
| iPhone 14 (Jorge) | iCloud Photos activo |
| iPhone 12 mini (mujer) | Fototeca compartida iCloud |
| iPad Pro | Lectura |
| Disco duro antiguo | Histórico desde 2014 con convención `YYYY-MM-DD nombre evento` |
| **Disco duro nuevo: 5 TB, vacío** | El que vamos a usar de aquí en adelante |

### Suscripciones y uso real

| Servicio | Coste | Plan | Uso real | Decisión |
|---|---|---|---|---|
| **Google One** | ~20 €/mes | **5 TB familiar** | 9.91 GB total (6.21 Fotos · 2.68 Drive · 1.02 Gmail) | **MANTENER** — ahora incluye YouTube Premium Lite al mismo precio y Gemini es de uso diario. Los 5 TB ociosos pasan a ser tercer backup opcional (ver §4) |
| iCloud+ | 2-3 €/mes | 200 GB | **26.89 GB** (3 933 fotos + 598 vídeos) — 13 % del plan | Mantener. **No hace falta subir cuota** |
| Amazon Prime | 50 €/año | Fotos ilimitadas (NO vídeos) | Backup secundario | Mantener |
| Claude Pro | 20 €/mes | — | IA general + **Cowork para organizar la fototeca** | Mantener |

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

1. **iCloud es la fuente real** de la fototeca actual: **26.89 GB** (3 933
   fotos + 598 vídeos). Bien dentro del plan de 200 GB; sin upgrade necesario.
2. **Google Photos es legacy**: solo 6.21 GB de los antiguos álbumes
   compartidos. Con Google One quedándose, el dump a disco pierde toda
   urgencia — es un "un día que me aburra".
3. **Vídeos**: Amazon Prime no los cubre. Viven en iCloud + disco duro, y
   opcionalmente en Google Photos como segunda copia cloud (ver §4).
4. **Mac no 24/7 + 19 GB libres** → no hay cron, no hay Cloud Run, y el
   staging de descargas va **directo al disco externo**, nunca al Mac. La app
   Fotos del Mac sigue en "Optimizar almacenamiento".
5. **Amazon Photos no tiene CLI y no la habrá**: Amazon cerró la API de Drive
   en 2023 y `rclone` no funciona contra Amazon Photos. La única vía
   automatizada es la app de escritorio con auto-upload vigilando una carpeta.
   Casualmente es también la opción más perezosa.
6. **El cuello de botella nunca fue descargar — es nombrar y limpiar.** Un
   script agrupa por fechas, pero no sabe si el 5 de julio fue "Playa" o
   "Cumple de la abuela", ni cuál de las 8 fotos de una ráfaga conservar.
   **Claude Cowork sí**: puede mirar las imágenes, proponer el nombre del
   evento y resolver los near-duplicados visualmente.

## 4. Decisión por decisión

### Nube primaria
- **iCloud Photos** (Apple ecosystem, fototeca compartida ya configurada).
- **Plan 200 GB se mantiene**: 26.89 GB / 200 GB = 13 % de uso. Sin upgrade.

### Backup local "fuente de verdad fría"
- **Disco duro nuevo de 5 TB** (vacío).
- Convención `YYYY-MM-DD nombre evento/`. El disco es el único sitio donde la
  fototeca está *organizada*; las nubes son copias, no se curan.

### Nube secundaria (backup de fotos)
- **Amazon Photos** vía su app de escritorio con auto-upload apuntando a la
  carpeta del disco. Cero comandos: sube sola cuando el disco está montado y
  el Mac encendido.

### Nube terciaria (opcional, cubre los vídeos)
- **Google Photos** vía Google Drive for Desktop, que permite backup de
  carpetas locales a Google Photos. Apuntado a la misma carpeta del disco da
  una segunda copia cloud **que sí incluye vídeos**, aprovechando los 5 TB
  de Google One que ya se pagan por otros motivos.

### Visor / gestor
- Apple Photos en iPhone/iPad/Mac. **No Immich** — añade superficie de error
  para cero ganancia neta ahora.

### Organización y dedupe
- **Claude Cowork es el organizador**, no un script ciego. El paquete aporta
  scripts finos (wrapper de `icloudpd`, hashing, clustering por fecha EXIF) y
  un skill `/photos-sync` que orquesta la sesión. Claude decide lo que
  requiere ojos; el humano solo confirma nombres de evento.

### Automatización
- **Trigger manual**: Mac encendido + disco enchufado + sesión de Claude Code.
- **Sin bot de Telegram** (descartado; en v1 estaba). Era la pieza con más
  código del plan y su única razón era el trigger remoto — pero el trabajo
  exige Mac + disco físicamente presentes, así que no ahorraba nada. Con que
  Jorge lo lance cuando toque, la fototeca compartida de iCloud ya cubre el
  día a día de ambos.
- **Sin GCP**: el trabajo es local (disco físico, Mac intermitente). Que el
  monorepo despliegue fácil a Cloud Run no es razón para subir algo que no
  puede tocar el disco.

## 5. Flujo final (edición pereza)

```
iPhones (Jorge + mujer) ──→ iCloud fototeca compartida      (automático)

── Cuando toque (mensual-ish): Mac encendido + disco enchufado ──

Sesión Claude Cowork (/photos-sync):
  1. icloudpd baja solo lo nuevo → staging/ EN EL DISCO EXTERNO
  2. dedupe exacto (hash) + near-dupes (ráfagas, HEIC/JPEG);
     Claude mira las dudosas y decide cuál conservar
  3. clustering por huecos de fecha EXIF; Claude propone
     "2026-07-05 Playa" mirando contenido + GPS; el humano confirma
  4. mueve a /YYYY-MM-DD evento/ en el disco 5 TB

Apps de escritorio vigilando la carpeta del disco (suben solas):
  → Amazon Photos app          (fotos, ilimitado con Prime)
  → Google Drive for Desktop   (opcional: a Google Photos, INCLUYE vídeos)
```

Intervención humana total: enchufar el disco, abrir Claude Code, confirmar
3-4 nombres de evento.

## 6. Plan — sprint 1 (limpieza one-off)

> Objetivo: dejar el disco nuevo como **fuente de verdad fría** unificada,
> con todo el histórico volcado y organizado por `YYYY-MM-DD evento/`.

| Paso | Acción | Herramienta |
|---|---|---|
| 1 | Inventario inicial: tamaño real iCloud, Google Photos, Amazon, disco viejo, disco nuevo | `scripts/inventory.sh` |
| 2 | Copiar **disco viejo → disco nuevo** tal cual, con verificación | `rsync -av --progress` |
| 3 | Volcar **iCloud → disco nuevo** (staging en el disco, no en el Mac). La biblioteca local del Mac está en "Optimizar almacenamiento", así que no sirve `osxphotos` | `icloudpd` |
| 4 | Dedupe + organizar en `YYYY-MM-DD evento/` | `exiftool` + hashing + **Claude Cowork** |
| 5 | Instalar Amazon Photos app (y opcionalmente Google Drive for Desktop) apuntando a la carpeta del disco | apps de escritorio |
| 6 | Verificar: checksums disco + spot-check de que las apps han subido | script de verificación |
| — | (sin prisa) dump de los 6.21 GB legacy de Google Photos al disco | `gphotos-sync` o Takeout |

## 7. Plan — sprint 2 (herramientas día a día)

> Objetivo: que el flujo mensual sea "enchufo disco, abro Claude Code,
> `/photos-sync`, confirmo nombres, listo".

| Pieza | Descripción |
|---|---|
| **CLI `lillophotos sync`** | Wrapper sobre `icloudpd`: baja lo nuevo de iCloud al staging del disco |
| **CLI `lillophotos organize`** | Hashing (dupes exactos), perceptual hash (near-dupes), clustering por fecha EXIF; emite propuesta de carpetas para que Claude/humano la refine |
| **CLI `lillophotos status`** | Último sync · tamaño de cada destino · fotos en staging sin organizar |
| **Skill `/photos-sync`** | Orquesta la sesión Cowork: corre sync + organize, revisa near-dupes con ojos, propone nombres de evento, mueve a definitivo |

**No** vamos a:
- Desplegar en Cloud Run ni usar GCP (trigger manual, disco local).
- Programar cron (queremos trigger manual).
- Montar bot de Telegram (descartado en v2; el trigger es la sesión local).
- Self-hostear Immich/PhotoPrism (cero ganancia con Apple Photos como visor).
- Tocar la sincronización cloud (iCloud lo hace solo).

## 8. Open questions

1. ~~**Modo de la fototeca en el Mac**~~ — **resuelto**: Mac e iPhone en
   "Optimizar almacenamiento" → el volcado va con `icloudpd` contra los
   servidores de iCloud, no con `osxphotos` contra la biblioteca local.
2. ~~**Mujer y disco duro**~~ — **resuelto**: misma casa, mismo acceso al
   disco; con que Jorge dispare el sync es suficiente.
3. ~~**Amazon Photos desde CLI**~~ — **resuelto**: no existe ni existirá
   (API cerrada en 2023, `rclone` no funciona). Vía única: app de escritorio
   con auto-upload sobre la carpeta del disco. Es además la opción con menos
   fricción.
4. **Google Drive for Desktop → Google Photos con disco externo**: confirmar
   que el backup de carpeta a Google Photos funciona bien cuando la carpeta
   vive en un disco que se monta/desmonta. Verificar en sprint 1 paso 5.

## 9. Próximo paso

1. Merge de este README actualizado.
2. **Paso 1 del sprint 1**: escribir `scripts/inventory.sh` (mide iCloud,
   discos, Google, Amazon), correrlo y calibrar el resto con números reales.

## 10. Lo que NO hace este paquete (acotado para no perderse el alcance)

- No es un visor de fotos (Apple Photos lo hace).
- No es una nube (iCloud lo hace).
- No reemplaza la sync iPhone → iCloud (Apple lo hace).
- No corre 24/7.
- No edita fotos.

Es solo: **descargar, organizar (con Cowork), hacer backup secundario, dar
visibilidad**.

## 11. Fuentes consultadas

- [Apple Community — Photo library management best practices 2026](https://ask.metafilter.com/389706/Photo-library-management-best-practices-in-2026)
- [Photo Backup Strategy 2026 — Alex Smale](https://www.alexsmale.co.uk/photo-backup-strategy-2026-icloud-google-photos-nas-or-both/)
- [iCloud Photos is not a backup — 9to5Mac](https://9to5mac.com/guides/icloud-photos/)
- [icloudpd — CLI to download iCloud Photos](https://github.com/icloud-photos-downloader/icloud_photos_downloader)
- [gphotos-sync — Google Photos backup CLI](https://github.com/gilesknap/gphotos-sync)
- [osxphotos — Export Apple Photos library](https://github.com/RhetTbull/osxphotos)
- [ExifTool — bulk rename + organize by EXIF date](https://exiftool.org/)

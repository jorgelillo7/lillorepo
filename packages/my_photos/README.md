# 📸 my_photos — brainstorming + plan

> **Estado**: plan v3 validado — v2 + decisiones de discos y nubes.
> No hay código todavía.
> **Última sesión**: 2026-07-12.

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
| PC Windows | Solo interviene en el sprint 0 (baile de discos) |
| Disco duro antiguo (+10 años) | Histórico desde 2014 con convención `YYYY-MM-DD nombre evento`. Tratar como frágil: **copiar, no mover** |
| **Disco duro nuevo: 5 TB** | **No está vacío** — hay que vaciarlo y formatearlo (exFAT + GPT) antes de usarlo. Ver sprint 0 |

### Suscripciones y uso real

| Servicio | Coste | Plan | Uso real | Decisión |
|---|---|---|---|---|
| **Google One** | ~20 €/mes | **5 TB familiar** | 9.91 GB total (6.21 Fotos · 2.68 Drive · 1.02 Gmail) | **MANTENER** — ahora incluye YouTube Premium Lite al mismo precio y Gemini es de uso diario. Google Photos queda **a cero** (Takeout → disco) y después solo recibe **vídeos** vía rclone (ver §4) |
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
   compartidos (más lo que haya en la cuenta de la mujer). Decisión: Takeout
   de ambas cuentas → disco → **borrar a cero**. Deja de ser un sitio que
   haya que curar a mano.
3. **Vídeos**: Amazon Prime no los cubre. Copias: iCloud (no se purga) +
   disco + Google Photos vía rclone **solo vídeos** (ver §4).
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
- **No se purga.** iCloud NO va a cero: es el carrete de los iPhones y el
  visor (recuerdos, compartir, "hace 3 años hoy"). Al ritmo actual
  (~18 GB/año) hay ~9 años de margen. Si algún día se acerca a ~150 GB, la
  sesión de sync propondrá purgar lo antiguo ya verificado en disco + Amazon.
  El hábito de "borrar la nube cuando se llena" era un vicio de la era
  Google Fotos; aquí no hay presión de espacio.
- **Sin álbumes.** iCloud queda como carrete cronológico sin organizar; la
  organización (`YYYY-MM-DD evento/`) solo existe en el disco y nace en la
  sesión de sync. Crear álbumes en Apple Photos es opcional y solo para
  mirar en el móvil — el pipeline ni los usa ni los necesita.

### Google Photos (legacy) → a cero
- Takeout de las dos cuentas (Jorge + mujer) → volcar al disco → verificar →
  **borrar todo**. 0 fotos y 0 vídeos en Google Photos.
- Tras el reset, a Google Photos solo entra lo que sube rclone (vídeos, ver
  nube terciaria). Nunca más se cura nada a mano ahí.

### Backup local "fuente de verdad fría"
- **Disco duro nuevo de 5 TB** (vacío).
- Convención `YYYY-MM-DD nombre evento/`. El disco es el único sitio donde la
  fototeca está *organizada*; las nubes son copias, no se curan.

### Nube secundaria (backup de fotos)
- **Amazon Photos** vía su app de escritorio con auto-upload apuntando a la
  carpeta del disco. Cero comandos: sube sola cuando el disco está montado y
  el Mac encendido.

### Nube terciaria — SOLO vídeos a Google Photos (rclone)
- Objetivo: tercera copia de los vídeos (lo único que Amazon no cubre) sin
  duplicar en Google las fotos que ya están en disco + Amazon.
- **Google Drive for Desktop descartado**: su backup de carpeta a Google
  Photos no filtra por tipo de fichero — subiría también todas las fotos.
- **rclone con remote `gphotos` + filtro de vídeo**
  (`--include "*.{mp4,mov,m4v,3gp}"` o equivalente): sube únicamente los
  vídeos de la carpeta organizada, creando un álbum por carpeta de evento.
  Corre como paso de script al final de la sesión de sync
  (`lillophotos backup-videos`) — 0 tokens, determinista.
- Notas API (restricciones de 2025): una app solo ve los medios que ella
  misma subió — irrelevante, solo subimos. Lo subido cuenta contra el
  storage de Google One: con 5 TB ociosos, sin problema.

### Visor / gestor
- Apple Photos en iPhone/iPad/Mac. **No Immich** — añade superficie de error
  para cero ganancia neta ahora.

### Organización y dedupe
- **Claude Cowork es el organizador**, no un script ciego. El paquete aporta
  scripts finos (wrapper de `icloudpd`, hashing, clustering por fecha EXIF) y
  un skill `/photos-sync` que orquesta la sesión. Claude decide lo que
  requiere ojos; el humano solo confirma nombres de evento.
- "Cowork" = **Claude Code o la app de escritorio de Claude, indiferente**.
  Primaria: Claude Code (el skill vive en este repo, ejecuta los CLI en
  terminal y también lee imágenes). La app de escritorio vale como
  alternativa para sesiones puramente visuales. Los CLI de `lillophotos`
  son agnósticos: cualquier agente (o un humano) puede invocarlos.

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

Al montar el disco (launchd StartOnMount, automático):
  0. `lillophotos sync` arranca solo: icloudpd baja lo nuevo → staging/
     EN EL DISCO EXTERNO. Notificación: "N fotos nuevas en staging".

Sesión Claude Cowork (/photos-sync), cuando quieras:
  1. dedupe exacto (hash) automático; near-dupes: por defecto SE CONSERVAN
     todos (5 TB dan para ráfagas; curar con Claude es opt-in)
  2. clustering por huecos de fecha EXIF + GPS → lugar (scripts, 0 tokens)
  3. Claude mira 3-4 miniaturas por grupo y propone "2026-07-05 Playa";
     el humano confirma o corrige el nombre
  4. mueve a /YYYY-MM-DD evento/ en el disco 5 TB
  5. `lillophotos backup-videos`: rclone sube SOLO los vídeos nuevos a
     Google Photos (álbum por evento)

Amazon Photos app vigilando la carpeta del disco:
  → sube las fotos sola (ilimitado con Prime; vídeos NO — de eso se
    encarga el paso 5)
```

Intervención humana total: enchufar el disco, abrir Claude Code, confirmar
3-4 nombres de evento.

**Ejemplo (boda con 40 fotos):** el día de la boda no se hace nada — las
fotos suben solas a iCloud, sin crear álbum. Semanas después, en la sesión
de sync, el clustering las agrupa (40 fotos seguidas un sábado, hueco >6 h
con lo anterior, GPS "Hacienda X"), Claude mira 3-4 miniaturas y propone
"2026-07-12 Boda (Hacienda X)"; el humano lo deja en "Boda Marta y Luis".
Coste humano total: una línea de texto, semanas después, cuando venga bien.

### Reparto script vs Claude (coste en tokens)

Principio de diseño: **todo lo determinista va en scripts Python fijos;
Claude solo entra donde hacen falta ojos o criterio.**

| Paso | Quién | Tokens |
|---|---|---|
| Descarga incremental de iCloud (icloudpd) | script | 0 |
| Dedupe exacto (SHA-256) | script | 0 |
| Candidatos near-dupe (hash perceptual) | script | 0 |
| Clustering por fecha EXIF (umbral fijo, p. ej. gap 6 h) | script | 0 |
| GPS → nombre de lugar (geocoding inverso) | script | 0 |
| Proponer nombre de evento | **Claude** (3-4 miniaturas reducidas + metadatos) | ~5-8k/evento |
| Adjudicar near-dupes dudosos | **Claude**, solo si se activa la curación | opt-in |
| Mover a carpetas, subir vídeos (rclone), log | script | 0 |

Sesión mensual típica (6-8 eventos): ~50k tokens. Claude nunca ve las 40
fotos de la boda — ve 3-4 representativas en miniatura, y muchos grupos se
nombran solo con metadatos (fecha + hora + lugar) sin mirar ninguna imagen.

### Corner cases de capacidad — orden de sacrificio

Números a ritmo actual (~18 GB/año, subirá con más vídeo):

| Límite | ¿Cuándo llega? | Qué se hace |
|---|---|---|
| iCloud 200 GB | ~5-9 años | **Purga rodante, no reset a cero**: la sesión de sync propone borrar los años más viejos ya verificados en disco+Amazon+Google; en el móvil quedan siempre los últimos ~2 años. Alternativa perezosa: subir a 2 TB (~10 €/mes) |
| Disco 5 TB | Por espacio, décadas (~3.3 TB libres). **Muere de viejo antes que de lleno** | Reemplazo por edad cada ~6-8 años: disco nuevo, **copiar todo** (no partir por rangos de fechas — fragmentaría el árbol único que vigilan Amazon/rclone). El viejo queda como copia fría extra con pegatina "completa hasta YYYY" |
| Google 5 TB (solo vídeos) | Matemáticamente nunca (~10 GB de vídeo/año contra 5 TB) | Si algún día se baja el plan de Google One: borrar lo viejo ahí sin duelo — es la copia sacrificable, el archivo completo de vídeos vive en el disco |
| Amazon (fotos ∞) | Nunca | Nada. Supuesto a vigilar: depende de mantener Prime |

Orden de sacrificio si hay que borrar en algún sitio: **iCloud primero,
Google después, el disco jamás** (el disco se reemplaza, no se poda).

Propiedad de resiliencia del diseño: si el disco muere mañana no se pierde
nada — fotos completas en Amazon, vídeos completos en Google (el backfill
de rclone sube también el histórico). El disco es la única copia
*organizada*, pero no es punto único de fallo.

## 6. Plan — sprint 0 (baile de discos) + sprint 1 (limpieza one-off)

### Sprint 0 — discos (en el PC Windows)

> El 5 TB no está vacío y el histórico vive en un disco de +10 años.
> Regla estricta: **nunca borrar un original sin copia verificada.**

| Paso | Acción | Notas |
|---|---|---|
| 0.1 | Vaciar el contenido actual del 5 TB al PC Windows | temporal |
| 0.2 | Formatear el 5 TB: **exFAT + tabla GPT** | compatible Windows y Mac. exFAT no tiene journaling: expulsar siempre en condiciones |
| 0.3 | **Copiar (no mover)** disco viejo → 5 TB y verificar (checksums + spot-check) | el disco viejo tiene +10 años; tratarlo como si fuera a morir mañana |
| 0.4 | Solo tras verificar 0.3: wipe del disco viejo y meterle lo vaciado en 0.1 | queda como almacén Windows; asumir que puede fallar |

### Sprint 1 — limpieza one-off

> Objetivo: dejar el disco nuevo como **fuente de verdad fría** unificada,
> con todo el histórico volcado y organizado por `YYYY-MM-DD evento/`.

| Paso | Acción | Herramienta |
|---|---|---|
| 1 | Inventario inicial: tamaño real iCloud, Google Photos, Amazon, disco viejo, disco nuevo | `scripts/inventory.sh` |
| 2 | **Takeout de Google Photos (ambas cuentas)** → volcar al disco → verificar → **borrar Google Photos a cero** | Takeout |
| 3 | Volcar **iCloud → disco nuevo** (staging en el disco, no en el Mac; iCloud NO se borra después). La biblioteca local del Mac está en "Optimizar almacenamiento", así que no sirve `osxphotos` | `icloudpd` |
| 4 | Dedupe + organizar en `YYYY-MM-DD evento/` | `exiftool` + hashing + **Claude Cowork** |
| 5 | Instalar Amazon Photos app apuntando a la carpeta del disco; configurar rclone → Google Photos (solo vídeos) y probar la subida + nombrado de álbumes | app + `rclone` |
| 6 | Verificar: checksums disco + spot-check de que Amazon ha subido y los vídeos están en Google Photos | script de verificación |

## 7. Plan — sprint 2 (herramientas día a día)

> Objetivo: que el flujo mensual sea "enchufo disco, abro Claude Code,
> `/photos-sync`, confirmo nombres, listo".

| Pieza | Descripción |
|---|---|
| **CLI `lillophotos sync`** | Wrapper sobre `icloudpd`: baja lo nuevo de iCloud al staging del disco |
| **CLI `lillophotos organize`** | Hashing (dupes exactos), perceptual hash (near-dupes), clustering por fecha EXIF; emite propuesta de carpetas para que Claude/humano la refine |
| **CLI `lillophotos backup-videos`** | rclone → Google Photos, solo extensiones de vídeo, álbum por evento |
| **CLI `lillophotos status`** | Último sync · tamaño de cada destino · fotos en staging sin organizar |
| **Skill `/photos-sync`** | Orquesta la sesión Cowork: revisa lo que el script marca ambiguo, propone nombres de evento, mueve a definitivo, lanza backup-videos |
| **launchd StartOnMount** | Al montar el 5 TB, lanza `lillophotos sync` solo y notifica "N fotos nuevas en staging" |

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
4. ~~**Google Drive for Desktop → Google Photos**~~ — **descartado**: no
   filtra por tipo de fichero y subiría también las fotos (duplicadas con
   Amazon). Sustituido por rclone solo-vídeos. Queda por verificar (sprint 1
   paso 5): subida rclone → Google Photos y nombrado de álbumes por evento.

## 9. Próximo paso

1. Merge de este README actualizado.
2. **Sprint 0** en el PC Windows (baile de discos) — no necesita código.
3. Correr `scripts/inventory.sh` (ya existe) con el disco nuevo montado y
   calibrar el resto con números reales.

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

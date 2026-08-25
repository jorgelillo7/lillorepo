# Notas privadas — Thor 6

**Este fichero está en `.gitignore` y no se sube.** Es tu cuaderno: enlaces,
versiones, lo que vayas descubriendo. El resto del paquete es la parte pública
y va en inglés; esto no.

Sigue aplicando lo mismo que el README público: aquí tampoco hay enlaces a
ROMs, BIOS ni claves, y no los va a haber. Todo lo de abajo es software
oficial y documentación.

---

## Enlaces

### La guía de la que salieron los ajustes

- [Cómo instalar emuladores en la AYN Thor](https://www.profesionalreview.com/2026/08/16/como-instalar-emuladores-ayn-thor/)
  — Profesional Review, 16/08/2026. Es la que tiene el paso a paso con
  capturas. Lo que se ha quedado en la guía pública es lo que sobrevive a los
  cambios de versión; para seguir el proceso pantalla a pantalla, esta.

### Emuladores — sitios oficiales

| Sistema | App | Dónde |
|---|---|---|
| Multi (Sega, GBA, arcade) | RetroArch | https://www.retroarch.com/ |
| PS1 | DuckStation | https://www.duckstation.org/ |
| DS | melonDS | https://melonds.kuribo64.net/ |
| DS | DraStic | Google Play (de pago) |
| 3DS | Azahar | https://azahar-emu.org/ |
| PSP | PPSSPP | https://www.ppsspp.org/ |
| Dreamcast | Redream | https://redream.io/ |
| Dreamcast | Flycast | core de RetroArch |
| GameCube / Wii | Dolphin | https://dolphin-emu.org/ |
| PS2 | NetherSX2 | fork comunitario de AetherSX2 |
| Arcade | FBNeo | core de RetroArch |
| Fangames PC | JoiPlay | https://joiplay.net/ |

Comprueba los enlaces antes de fiarte: los emuladores de Android cambian de
casa a menudo y alguno de estos habrá cambiado desde que se escribió esto.

### Cacharreo del dispositivo

- **AYN** (soporte, firmware, foro oficial) — https://www.ayntec.com/
- **Retro Game Corps** — https://retrogamecorps.com/ — guías largas y bien
  hechas por dispositivo; la referencia habitual para handhelds Android.

---

## Ajustes que da la guía, en un sitio

Copiados aquí para no tener que abrir el artículo cada vez.

**melonDS (DS)**
- Renderer: OpenGL
- Resolución interna: 5x nativa (1280x960)
- Configurar la disposición de las dos pantallas a mano

**Azahar (3DS)**
- API: Vulkan
- Compilación asíncrona de shaders: ON
- Resolución interna: 5x nativa
- Pantalla secundaria: pantalla inferior

**NetherSX2 / AetherSX2 (PS2)**
- Renderer: Vulkan
- Caché de shaders en disco: ON
- Shaders asíncronos: ON
- Necesita BIOS (región Europa)

**Drivers GPU**
- Sólo hacen falta para Switch, que no está en esta colección.
- La guía usa un explorador de drivers de GPU, deja que detecte el recomendado
  (mencionaba "Mr. Purple T23") y si falla la descarga se elige a mano.

---

## Orden de montaje

Lo mismo que dice el README pero como lista para ir tachando:

- [ ] Formatear la SD y copiar `SD_TEMPLATE/` (sin los `.gitkeep`)
- [ ] RetroArch: instalar, asignar mando al puerto 1, quitar el overlay táctil
- [ ] RetroArch: teclas rápidas — menú y salir
- [ ] Cores: Genesis Plus GX, FBNeo
- [ ] Neo Geo: `neogeo.zip` junto a los sets de Metal Slug
- [ ] DuckStation + BIOS PS1 → probar con algo corto
- [ ] PPSSPP → 3 juegos, rápido
- [ ] melonDS o DraStic (decide uno) con los ajustes de arriba
- [ ] Azahar con los ajustes de arriba
- [ ] Redream o Flycast (+ BIOS si Flycast)
- [ ] NetherSX2 + BIOS PS2 → el que más ajuste por juego va a pedir
- [ ] Dolphin → lo más exigente de la lista
- [ ] JoiPlay + plugin RPG Maker, un juego por carpeta
- [ ] Al final, y sólo al final: el launcher

---

## Cosas que se olvidan

- Los sets de arcade **se quedan en zip y con su nombre**. Es la causa número
  uno de que un juego que debería tirar no tire.
- Una sola carpeta `BIOS/`, y cada emulador apuntando a ella. No una por
  sistema.
- Gran Turismo 2 son dos discos: dos imágenes, las dos en la lista.
- Metal Slug X es revisión del 2, no secuela. Están los dos porque se juegan
  distinto.
- El mando hay que asignarlo **en cada emulador**. No se hereda.

---

## Diario

Apunta aquí lo que te pase: qué versión de cada app te funcionó, qué juego dio
guerra, qué ajuste tuviste que cambiar. Dentro de seis meses no te vas a
acordar y este fichero es el único sitio donde vive.

| Fecha | Qué | Nota |
|---|---|---|
| | | |

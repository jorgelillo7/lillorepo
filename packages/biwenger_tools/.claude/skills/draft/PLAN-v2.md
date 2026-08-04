# Plan de mejora de la skill de draft — v2

Escrito tras el draft 26-27, con el draft aún abierto y la memoria fresca.
Este fichero es de trabajo: se borra cuando la v2 esté implantada y probada.

---

## Qué falló en la v1

Ninguno de estos fallos fue un bug. Todos fueron **decisiones de diseño que
parecían razonables y resultaron falsas en cuanto llegó un dato real**.

**1. Rankeaba con la métrica equivocada.** La skill ordenaba por la proyección
SofaScore de Jornada Perfecta. La liga puntúa *Personalizado*. No es un ajuste
fino: el factor `real / proyección` medido sobre 22 jugadores va de **0,225 a
0,610**. Con esa dispersión, ninguna constante de conversión sirve para comparar
a dos jugadores entre sí.

**2. No miraba los partidos jugados.** Guido tenía 116 puntos y parecía flojo;
eran 17 partidos, o sea ~218 por temporada. Terrats tenía 85 y parecía
recuperable; eran 29 partidos, o sea que juega y no rinde. **El mismo número
significa lo contrario según los partidos**, y la v1 no tenía forma de saberlo.

**3. Se fiaba de un relleno.** Cuando JP no tiene datos de un jugador le pone
`400` por defecto. La v1 lo trataba como una puntuación más. Amatucci y Calero
entraron en varias propuestas de once con un número inventado.

**4. Descargó 552 jugadores en paralelo.** Biwenger limita a **500 peticiones
por ventana de 8 horas y por cuenta**. Dejó a la liga entera sin app durante la
tarde del draft.

**5. Los arquetipos ignoraban que esto es un draft.** Proponían el quince ideal
como si todos los jugadores fueran comprables, cuando entre pick y pick
desaparecen ocho.

---

## La fórmula, ya resuelta

Sacada de la pantalla de configuración de la liga y **verificada al punto**
contra Vinícius (330) y Joan García (274):

```
Personalizado = Puntos SofaScore
              + 1  si victoria y minutos > 65
              − 1  si derrota  y minutos > 65
              + 1  si minutos > 65
              + 2  portería a cero (portero)   ·  + 1 (defensa)
              − 1  por tarjeta amarilla
              + 1  gol de portero   ·  + 2 asistencia de portero
              + 1  asistencia de defensa
              − 1  gol en propia    ·  − 2 penalti fallado
              − 1  gol de penalti
              + 3  MVP              ·  + 2 penalti parado
```

Lo que implica y la v1 no veía:

- **Jugar es media puntuación.** `+1 por jugar` y `+1 por victoria` son hasta
  **+76 al año** por ser titular en un equipo que gana.
- **Las porterías a cero solo pagan a portero (+2) y defensa (+1).**
- **El gol de penalti resta.** Un especialista puntúa menos aquí que en
  cualquier otra liga.

---

## El flujo v2

Tres fases, y la clave está en **dónde se corta el embudo**.

### Fase 1 — Mercado congelado (~500 jugadores)

Entrada: el CSV de precios cerrados que exporta el usuario.

- Se une con la proyección de JP por nombre.
- **La columna de JP se recalcula en cada ejecución**: JP actualiza varias veces
  al día y el CSV de precios no. Nunca se cachea entre ejecuciones.
- Los `400` de relleno se marcan como tales en el CSV de salida, no solo en el
  generador. Un humano que abra el fichero debe ver que ese número es falso.

Salida: `draft-ranked.csv`, que **sirve para descartar, no para decidir**.

### Fase 2 — Lista corta (30-45 jugadores)

Aquí está el cambio de fondo. De las ~500 se baja a los que de verdad compiten
por las plazas que quedan, filtrando por línea, banda de precio y
disponibilidad.

Para **esos y solo esos** se pide a Biwenger:

```
GET /players/la-liga/{slug}?fields=*,seasons(*),reports(*)
```

y de ahí salen los dos datos que faltaban:

| Dato | De dónde | Para qué |
|---|---|---|
| `seasons[].games` | directo | separar «70 en 5 partidos» de «70 en 38» |
| `seasons[].points` por sistema | directo | la base SofaScore real, no la proyección |
| `reports[].rawStats` | por partido | victorias, porterías a cero, tarjetas → Personalizado exacto |

**Por qué 30-45 y no 15.** Si solo consultas a los quince que ya elegiste,
confirmas tu propio sesgo. En el draft 26-27, Dmitrović era el **sexto** portero
por proyección y el **primero** por dato real; Juan Iglesias no estaba ni en el
equipo y acabó de capitán. Ninguno habría entrado en una lista de quince.

**Presupuesto de peticiones:** 45 de 500 por ventana = 9%. Secuencial, con
espera entre llamadas, caché en disco y **parada al primer 429**. Si el draft
está en marcha y no hay caché, no se ejecuta: se estima y se dice que es una
estimación.

### Fase 3 — Decisión

- Se generan los arquetipos con los datos refinados.
- Se elige el mejor por **puntos del once**, no por los quince: en Biwenger solo
  puntúan los titulares.
- **Se itera**: si un jugador se cae (te lo quitan, hay una noticia mala), se
  promociona al siguiente candidato, se analiza con el mismo detalle y se vuelve
  a comprobar presupuesto y composición.
- La comprobación de noticias es **bloqueante**, no opcional. En el 26-27 sacó
  tres cosas que ningún número veía: Marcos Alonso sin convocar en pretemporada,
  Canales volviendo a los 35 desde México, Fortuño disputándole el puesto al
  portero que iba a ser inclausulable.

---

## El output

Un único fichero de decisión, con **una fila por jugador y su procedencia
visible**:

| Columna | Por qué está |
|---|---|
| Pick | En qué turno toca cogerlo |
| Pos · Jugador · Equipo | Identificación |
| Precio | Presupuesto |
| **JP** | Proyección de la temporada que viene |
| **Real** | Personalizado de la temporada pasada |
| **PJ** | Partidos jugados — sin esto, «Real» engaña |
| **Pts/partido** | Rendimiento, independiente de los minutos |
| **Pts/M** | Eficiencia de la ficha |
| Fuente | ✅ real · ⚠️ parcial · ~ proyección · 🎲 apuesta |

Más: el once resultante, el capitán (tope de 3M), los recambios por pick con su
coste en puntos, y el reparto por club.

**La columna «Fuente» no es decorativa.** En el 26-27 fue lo que permitió ver de
un vistazo dónde se estaba apostando a ciegas y dónde había suelo.

---

## Orden de implantación

1. `draft-real-points.csv` y el cargador que lo prefiere sobre la proyección.
2. Marcar los `400` de relleno también en `draft_ranking.py`.
3. El descargador acotado de la fase 2, con freno y caché.
4. Calcular el Personalizado con la fórmula verificada.
5. Columnas `PJ` y `pts/partido` en todo el pipeline.
6. Selección de arquetipo por puntos del **once**, con iteración.
7. El informe final con la tabla de arriba.
8. Reescribir `SKILL.md` alrededor de las tres fases.

---

## Cierre del draft — el informe de disponibilidad

Un script que se ejecuta **una vez, al acabar el draft**, y deja un `.md` con
cuándo se fue cada cosa. No sirve para este draft: sirve para el siguiente.

La pregunta que hay que responder cada año es *«¿en qué pick tengo que coger
portero?»*, y hoy se contesta a ojo. Con los picks ya en Firestore el dato es
exacto: en qué pick se fue el último portero bueno, cuántos delanteros por
debajo de 3M quedaban en la ronda 8, qué precio medio se pagó por línea y ronda.

Salida por línea: pick del primero y del último, cuántos se fueron en cada
tramo de diez picks, y la banda de precio que se agotó antes. Más el detalle
pick a pick, que es lo que se comparte con el grupo al terminar.

Se alimenta de `draft/{season}/picks`, que ya tiene `global_pick`, `round`,
`position`, precio y los tiempos de turno. No hace ni una llamada a Biwenger.

---

## Lo que este plan NO arregla

Sigue pendiente y queda anotado en `PENDING.md`:

- **El hueco de un pick en el backfill de tiempos.**

Descartado a propósito: **nacionalidad y torneos internacionales**. La respuesta
cambió entre dos ediciones consecutivas y no compensa mantenerlo.

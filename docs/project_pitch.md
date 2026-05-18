# Presentación del proyecto

> Notas de cómo narrar este proyecto en una entrevista o revisión técnica.

## La frase de posicionamiento

> "Usé un proyecto de Biwenger como excusa para practicar Bazel monorepos, arquitectura GCP cloud-native y CI/CD a nivel producción."

Esa frase posiciona el proyecto correctamente: no como un side project de primavera sino como práctica deliberada de habilidades reales.

---

## Puntos fuertes a destacar

**Bazel en un proyecto personal** es la señal más fuerte. El 99% de side projects usan un Makefile o directamente `python app.py`. Este repo tiene bzlmod, macros custom, capas OCI separadas, lock file con hashes, imagen base pre-compilada y plataformas definidas.

**Imagen base pre-compilada** (`Dockerfile.base` con todos los deps pre-instalados) reduce cold starts. Es un detalle de optimización del ciclo de deployment que no todo el mundo considera.

**Secrets management correcto.** Secret Manager con montaje como fichero en Cloud Run, sin variables de entorno con datos sensibles, con fallback local a `.env`. Exactamente como se hace en producción.

**CI/CD con cleanup automático incluido.** El script de limpieza que distingue entre imágenes tagged y untagged multi-arch en Artifact Registry es un detalle fino. Muchos proyectos dejan el registry llenarse.

**`DESIGN.md` para un proyecto personal.** Adopción del formato de [Google Labs](https://github.com/google-labs-code/design.md) para describir sistemas de diseño a agentes de IA: tokens de color, tipografía y reglas de composición en YAML + prosa legible por humanos. La mayoría de devs backend nunca documentan la UI; además, este formato es el estándar emergente para que los agentes apliquen consistencia visual de forma programática.

**Pipeline de datos desacoplado correctamente.** El scraper no sabe nada de la web, la web no sabe nada del scraper. La interfaz es el CSV en Drive (y en el futuro, Firestore).

---

## Debilidades a tener preparadas

**CSV como base de datos.** Es la pregunta más obvia. La respuesta honesta funciona bien: "Drive ya estaba en el stack, el dataset es pequeño, el scraper es single-instance por diseño, y prioricé simplicidad sobre escalabilidad para este caso concreto." Lo que no se puede decir es que no se había pensado en ello. La migración a Firestore ya está planificada.

**JSON dentro de celdas CSV** en `tabla_justicia` (`hechos`, `recibidos`). Es señal de que el formato CSV se está estirando más allá de sus límites. Se resuelve con Firestore.

**`TEMPORADA_ACTUAL` duplicado** en `web/config.py` y `scraper_job/config.py` — dos deployments independientes que pueden desincronizarse.

**La imagen base aún incluye Selenium** (~150MB) por inercia: ya nadie la usa (v4.2 reemplazó la única dependencia por una llamada HTTP directa a la API privada de Jornada Perfecta; toda esa lógica vive hoy en `biwenger-api`). El siguiente rebuild de `Dockerfile.base` la quita.

---

## Valoración global

Para carta de presentación: sólido. Demuestra que se sabe construir infraestructura real alrededor de un proyecto Python: build system, cloud deployment, secrets, CI/CD, tests, documentación. Eso ya es más de lo que muestra el 80% de portfolios.

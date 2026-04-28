---
name: Firestore migration plan
description: Pending migration from CSV/Google Drive to Firestore — effort ~16h, coste $0/mes (free tier)
type: project
---

Decisión: migrar el data layer de CSV en Google Drive a Firestore.

**Why:** Resuelve CSVs que se cargan enteros en cada request, JSON-en-celdas-CSV (hechos/recibidos en tabla_justicia), reescritura completa del CSV en el scraper, y mejora la carta de presentación.

**How to apply:** Cuando se retome, empezar por `core/sdk/firestore.py`, luego modelo de datos, luego scraper_job, luego web routes. Ver evaluación completa en la conversación de 2026-04-28.

Estructura de colecciones decidida:
```
comunicados/{season}/messages/{id_hash}
clausulazos/{season}/transfers/{auto_id}
tabla_justicia/{season}/teams/{equipo}
participacion/{season}/authors/{autor}
palmares/{auto_id}
```

Los domain models de `core/domain/models.py` ya existen y mapean directo a documentos Firestore.

Firestore ≠ autenticación de usuarios. Si en el futuro se quiere login → Firebase Auth + Google login (los miembros ya tienen Google). No prioritario.

Coste: $0/mes (free tier cubre holgadamente el tráfico de una liga de ~10 personas).

# TODO

> 📌 **Para retomar trabajo en una sesión nueva**, leer
> [`.claude/plans/next_phases.md`](../.claude/plans/next_phases.md).
>
> Este fichero solo lista **pendientes activos**. La historia de lo cerrado vive en
> `next_phases.md` (sprint by sprint) y en `release-notes.md`.

## Pendiente

- [ ] **Migración CSV → Firestore** — diferida indefinidamente (2026-05-10). Los modelos
      de dominio están listos para que el cambio sea localizado en lecturas/escrituras GCP
      en lugar de tocar todos los call sites. Plan completo en `next_phases.md` § 1.
- [ ] **Mover IDs de Drive/Sheets a Secret Manager / env** — hardcodeados en
      `packages/biwenger_tools/web/BUILD.bazel:13-19`. Mueren con la migración Firestore,
      no hay urgencia hasta entonces.
- [ ] **Nuevo proyecto Google para fotos** — sin spec todavía.
- [ ] **Opus doc review** — pasar Opus sobre todos los MDs, docs, READMEs y diagramas del
      repo. Hecho parcialmente el 2026-05-16 tras el sprint de cleanup. Reabrir si surgen
      huecos.

from unidecode import unidecode

# Mapeo manual Biwenger -> JP para casos en los que ninguna estrategia
# automática funciona (nombres completamente distintos, apodos, alias).
# Las claves están normalizadas (lowercase + sin acentos).
PLAYER_NAME_MAPPINGS = {
    # Vinicius en Biwenger ↔ "Vini Jr" en JP
    "vinicius jr": "vini jr",
    "vinicius junior": "vini jr",
    # Inversiones / variaciones conocidas históricas
    "sancet": "oihan sancet",
    "javi hernandez": "javier hernandez",
    "javier rueda": "javi rueda",
    "brugue": "brugui",
    "ricardo rodriguez": "r. rodriguez",
    "matias moreno": "m. moreno",
}


def normalize_name(name: str) -> str:
    """Normaliza nombres: minúsculas, sin acentos, recortado."""
    return unidecode(name.lower().strip())


def build_jp_index(jp_players: list[dict]) -> dict:
    """Construye índices del listado JP para acelerar el matching.

    Devuelve dict con dos claves:
      - 'by_name': nombre normalizado -> jugador JP
      - 'by_slug': slug normalizado -> jugador JP (fallback)
    """
    by_name: dict[str, dict] = {}
    by_slug: dict[str, dict] = {}
    for p in jp_players:
        name = p.get("name") or ""
        slug = p.get("slug") or ""
        if name:
            by_name[normalize_name(name)] = p
        if slug:
            by_slug[normalize_name(slug)] = p
    return {"by_name": by_name, "by_slug": by_slug}


def find_player_match(biwenger_name: str, jp_index: dict) -> dict | None:
    """Busca el jugador JP que corresponde al nombre Biwenger dado.

    Prueba en orden:
      1. Coincidencia directa por nombre normalizado
      2. Mapeo manual de excepciones (PLAYER_NAME_MAPPINGS)
      3. Coincidencia por slug
      4. Transformaciones automáticas (apellido, nombre, "i. apellido")
      5. Subconjunto de tokens

    Devuelve el dict del jugador JP o None si no hay coincidencia.
    """
    by_name = jp_index["by_name"]
    by_slug = jp_index["by_slug"]
    norm = normalize_name(biwenger_name)

    if norm in by_name:
        return by_name[norm]

    if norm in PLAYER_NAME_MAPPINGS:
        mapped = PLAYER_NAME_MAPPINGS[norm]
        if mapped in by_name:
            return by_name[mapped]

    if norm in by_slug:
        return by_slug[norm]

    # Slug suele ser sin espacios; probar también la variante sin espacios
    no_spaces = norm.replace(" ", "")
    if no_spaces in by_slug:
        return by_slug[no_spaces]

    parts = norm.split()
    if len(parts) > 1:
        last = parts[-1]
        if last in by_name:
            return by_name[last]

        first = parts[0]
        if first in by_name:
            return by_name[first]

        initial_last = f"{parts[0][0]}. {parts[-1]}"
        if initial_last in by_name:
            return by_name[initial_last]

    parts_set = set(parts)
    for jp_norm, jp_player in by_name.items():
        if parts_set and parts_set.issubset(set(jp_norm.split())):
            return jp_player

    return None

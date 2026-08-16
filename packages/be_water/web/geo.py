"""Spanish province adjacency, for the recommender's nearby fallback.

Canonical names match `seed_data.py` spelling; lookups are
accent-insensitive. Symmetry is enforced by the test suite.
"""

from unidecode import unidecode

PROVINCE_ADJACENCY = {
    "A Coruña": ["Lugo", "Pontevedra"],
    "Álava": ["Burgos", "Guipúzcoa", "La Rioja", "Navarra", "Vizcaya"],
    "Albacete": [
        "Alicante",
        "Ciudad Real",
        "Cuenca",
        "Granada",
        "Jaén",
        "Murcia",
        "Valencia",
    ],
    "Alicante": ["Albacete", "Murcia", "Valencia"],
    "Almería": ["Granada", "Murcia"],
    "Asturias": ["Cantabria", "León", "Lugo"],
    "Ávila": ["Cáceres", "Madrid", "Salamanca", "Segovia", "Toledo", "Valladolid"],
    "Badajoz": ["Cáceres", "Ciudad Real", "Córdoba", "Huelva", "Sevilla", "Toledo"],
    "Barcelona": ["Girona", "Lleida", "Tarragona"],
    "Burgos": [
        "Álava",
        "Cantabria",
        "La Rioja",
        "Palencia",
        "Segovia",
        "Soria",
        "Valladolid",
        "Vizcaya",
    ],
    "Cáceres": ["Ávila", "Badajoz", "Salamanca", "Toledo"],
    "Cádiz": ["Huelva", "Málaga", "Sevilla"],
    "Cantabria": ["Asturias", "Burgos", "León", "Palencia", "Vizcaya"],
    "Castellón": ["Tarragona", "Teruel", "Valencia"],
    "Ciudad Real": ["Albacete", "Badajoz", "Córdoba", "Cuenca", "Jaén", "Toledo"],
    "Córdoba": ["Badajoz", "Ciudad Real", "Granada", "Jaén", "Málaga", "Sevilla"],
    "Cuenca": [
        "Albacete",
        "Ciudad Real",
        "Guadalajara",
        "Madrid",
        "Teruel",
        "Toledo",
        "Valencia",
    ],
    "Girona": ["Barcelona", "Lleida"],
    "Granada": ["Albacete", "Almería", "Córdoba", "Jaén", "Málaga", "Murcia"],
    "Guadalajara": ["Cuenca", "Madrid", "Segovia", "Soria", "Teruel", "Zaragoza"],
    "Guipúzcoa": ["Álava", "Navarra", "Vizcaya"],
    "Huelva": ["Badajoz", "Cádiz", "Sevilla"],
    "Huesca": ["Lleida", "Navarra", "Zaragoza"],
    "Illes Balears": [],
    "Jaén": ["Albacete", "Ciudad Real", "Córdoba", "Granada"],
    "La Rioja": ["Álava", "Burgos", "Navarra", "Soria", "Zaragoza"],
    "Las Palmas": [],
    "León": [
        "Asturias",
        "Cantabria",
        "Lugo",
        "Ourense",
        "Palencia",
        "Valladolid",
        "Zamora",
    ],
    "Lleida": ["Barcelona", "Girona", "Huesca", "Tarragona", "Zaragoza"],
    "Lugo": ["A Coruña", "Asturias", "León", "Ourense", "Pontevedra"],
    "Madrid": ["Ávila", "Cuenca", "Guadalajara", "Segovia", "Toledo"],
    "Málaga": ["Cádiz", "Córdoba", "Granada", "Sevilla"],
    "Murcia": ["Albacete", "Alicante", "Almería", "Granada"],
    "Navarra": ["Álava", "Guipúzcoa", "Huesca", "La Rioja", "Zaragoza"],
    "Ourense": ["León", "Lugo", "Pontevedra", "Zamora"],
    "Palencia": ["Burgos", "Cantabria", "León", "Valladolid"],
    "Pontevedra": ["A Coruña", "Lugo", "Ourense"],
    "Salamanca": ["Ávila", "Cáceres", "Valladolid", "Zamora"],
    "Santa Cruz de Tenerife": [],
    "Segovia": ["Ávila", "Burgos", "Guadalajara", "Madrid", "Soria", "Valladolid"],
    "Sevilla": ["Badajoz", "Cádiz", "Córdoba", "Huelva", "Málaga"],
    "Soria": ["Burgos", "Guadalajara", "La Rioja", "Segovia", "Zaragoza"],
    "Tarragona": ["Barcelona", "Castellón", "Lleida", "Teruel", "Zaragoza"],
    "Teruel": [
        "Castellón",
        "Cuenca",
        "Guadalajara",
        "Tarragona",
        "Valencia",
        "Zaragoza",
    ],
    "Toledo": ["Ávila", "Badajoz", "Cáceres", "Ciudad Real", "Cuenca", "Madrid"],
    "Valencia": ["Albacete", "Alicante", "Castellón", "Cuenca", "Teruel"],
    "Valladolid": [
        "Ávila",
        "Burgos",
        "León",
        "Palencia",
        "Salamanca",
        "Segovia",
        "Zamora",
    ],
    "Vizcaya": ["Álava", "Burgos", "Cantabria", "Guipúzcoa"],
    "Zamora": ["León", "Ourense", "Salamanca", "Valladolid"],
    "Zaragoza": [
        "Guadalajara",
        "Huesca",
        "La Rioja",
        "Lleida",
        "Navarra",
        "Soria",
        "Tarragona",
        "Teruel",
    ],
}

ALL_PROVINCES = sorted(PROVINCE_ADJACENCY)

_COMMUNITY_PROVINCES = {
    "Andalucía": [
        "Almería",
        "Cádiz",
        "Córdoba",
        "Granada",
        "Huelva",
        "Jaén",
        "Málaga",
        "Sevilla",
    ],
    "Aragón": ["Huesca", "Teruel", "Zaragoza"],
    "Asturias": ["Asturias"],
    "Canarias": ["Las Palmas", "Santa Cruz de Tenerife"],
    "Cantabria": ["Cantabria"],
    "Castilla y León": [
        "Ávila",
        "Burgos",
        "León",
        "Palencia",
        "Salamanca",
        "Segovia",
        "Soria",
        "Valladolid",
        "Zamora",
    ],
    "Castilla-La Mancha": [
        "Albacete",
        "Ciudad Real",
        "Cuenca",
        "Guadalajara",
        "Toledo",
    ],
    "Cataluña": ["Barcelona", "Girona", "Lleida", "Tarragona"],
    "Comunidad de Madrid": ["Madrid"],
    "Comunidad Valenciana": ["Alicante", "Castellón", "Valencia"],
    "Extremadura": ["Badajoz", "Cáceres"],
    "Galicia": ["A Coruña", "Lugo", "Ourense", "Pontevedra"],
    "Illes Balears": ["Illes Balears"],
    "La Rioja": ["La Rioja"],
    "Navarra": ["Navarra"],
    "País Vasco": ["Álava", "Guipúzcoa", "Vizcaya"],
    "Región de Murcia": ["Murcia"],
}

ALL_COMMUNITIES = sorted(_COMMUNITY_PROVINCES)

# Older sources (the AESAN PDF included) use pre-normalization spellings.
_PROVINCE_ALIASES = {
    "la coruna": "A Coruña",
    "coruna": "A Coruña",
    "gerona": "Girona",
    "lerida": "Lleida",
    "orense": "Ourense",
    "baleares": "Illes Balears",
    "islas baleares": "Illes Balears",
    "gipuzkoa": "Guipúzcoa",
    "bizkaia": "Vizcaya",
    "araba": "Álava",
}


def place_key(name: str) -> str:
    """Normalised form a place is compared by: accent- and case-insensitive.

    The single normalisation for the whole app — `similarity` and the routes
    import this instead of lowercasing on their own, which is how `?lugar=cadiz`
    used to miss Cádiz on one code path and hit it on another.
    """
    return unidecode(name or "").strip().lower()


_PROVINCE_COMMUNITY = {
    place_key(province): community
    for community, provinces in _COMMUNITY_PROVINCES.items()
    for province in provinces
}
for _alias, _canonical in _PROVINCE_ALIASES.items():
    _PROVINCE_COMMUNITY[_alias] = _PROVINCE_COMMUNITY[place_key(_canonical)]


def community_of(province: str) -> str:
    """Autonomous community of a province, alias/accent tolerant; '' when
    unknown."""
    return _PROVINCE_COMMUNITY.get(place_key(province), "")


_INDEX = {place_key(p): neighbors for p, neighbors in PROVINCE_ADJACENCY.items()}

_COMMUNITY_INDEX = {
    place_key(c): provinces for c, provinces in _COMMUNITY_PROVINCES.items()
}


def adjacent_provinces(place: str) -> list[str]:
    """Bordering provinces of `place` (accent-insensitive); [] when the
    place is unknown, an island, or a community rather than a province."""
    return list(_INDEX.get(place_key(place), []))


def provinces_of(community: str) -> list[str]:
    """Provinces making up `community`; [] when it is not a community."""
    return list(_COMMUNITY_INDEX.get(place_key(community), []))


def adjacent_places(place: str) -> list[str]:
    """Bordering provinces of `place`, whether it names a province or a
    community.

    A community's neighbours are the union of its provinces' neighbours minus
    its own — `adjacent_provinces` alone returns [] for every community, which
    silently emptied the "nearby" section for half the selector.
    """
    own = provinces_of(place)
    if not own:
        return adjacent_provinces(place)
    own_keys = {place_key(p) for p in own}
    neighbors = {
        n
        for province in own
        for n in adjacent_provinces(province)
        if place_key(n) not in own_keys
    }
    return sorted(neighbors)

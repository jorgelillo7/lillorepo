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


def _key(name: str) -> str:
    return unidecode(name).strip().lower()


_INDEX = {_key(p): neighbors for p, neighbors in PROVINCE_ADJACENCY.items()}


def adjacent_provinces(place: str) -> list[str]:
    """Bordering provinces of `place` (accent-insensitive); [] when the
    place is unknown, an island, or a community rather than a province."""
    return list(_INDEX.get(_key(place), []))

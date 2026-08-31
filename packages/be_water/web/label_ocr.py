"""Label extraction: bottle photo → mineral vector, via Gemini structured output."""

from core.sdk import gemini
from packages.be_water.web import config
from packages.be_water.web.domain import MINERAL_FIELDS

_PROMPT = """Eres un parser de etiquetas de agua mineral embotellada española.
Extrae los campos de la etiqueta de la foto. Los valores minerales van en
mg/L tal como aparecen (acepta coma decimal y convierte a número). Si un
campo no aparece en la etiqueta, devuélvelo como null — no inventes valores.
"tds" es el residuo seco (a 180°C). "sparkling" es true solo si es agua con
gas. "province" y "community" se refieren al lugar del manantial en España.
"analysis_date" es la fecha del análisis de laboratorio que declara la etiqueta
("CNTA, Febrero 2025" → "2025-02"; "CNTA 2023" → "2023"): devuélvela siempre
como "YYYY-MM", o "YYYY" si la etiqueta solo imprime el año, y null si no
aparece — no la confundas con el lote ni con el consumo preferente."""

_NUMBER = {"type": "NUMBER", "nullable": True}
LABEL_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "name": {"type": "STRING", "nullable": True},
        "spring": {"type": "STRING", "nullable": True},
        "province": {"type": "STRING", "nullable": True},
        "community": {"type": "STRING", "nullable": True},
        "sparkling": {"type": "BOOLEAN", "nullable": True},
        "analysis_date": {"type": "STRING", "nullable": True},
        **{field: _NUMBER for field in MINERAL_FIELDS},
    },
}


def extract_label(image_bytes: bytes) -> dict:
    """Photo → {name, spring, province, community, sparkling, analysis_date, minerals…}.

    Raises `gemini.GeminiError` / `requests.RequestException`; the route
    degrades to the empty form keeping the photo.
    """
    return gemini.generate_json(
        api_key=config.GEMINI_API_KEY,
        prompt=_PROMPT,
        image_bytes=image_bytes,
        schema=LABEL_SCHEMA,
        model=config.GEMINI_MODEL,
        fallback_api_key=config.GEMINI_API_KEY_PAID,
        retries=1,
        # 45 s (the default) threw away reads that were merely slow — the
        # observed failure was a read timeout, not an API error. The worker
        # allows 240 s and this call now runs beside the studio photo rather
        # than after it, so waiting is affordable.
        timeout=90,
    )

# Buenas Prácticas en Python - Retrofit Team

> Guía de estándares de desarrollo Python basada en PEP 8, PEP 20 y experiencia del equipo Retrofit

**Actualizado:** Febrero 2026
**Mantenedor:** Retrofit Chapter - MasOrange
**Basado en:** Refactorización MOS MCP Server v1.4.0

---

## 📋 Índice

1. [Los Mandamientos (PEP 20)](#los-mandamientos-pep-20)
2. [Estructura de Proyectos](#estructura-de-proyectos)
3. [Organización del Código](#organización-del-código)
4. [Funciones vs Clases](#funciones-vs-clases)
5. [Composición sobre Herencia](#composición-sobre-herencia)
6. [Convenciones de Nombres](#convenciones-de-nombres)
7. [Documentación](#documentación)
8. [Testing](#testing)
9. [Errores Comunes a Evitar](#errores-comunes-a-evitar)
10. [Checklist de Code Review](#checklist-de-code-review)

---

## 🧘 Los Mandamientos (PEP 20)

### The Zen of Python

```python
import this
```

### Principios Clave Aplicados en Retrofit

#### ✅ "Simple is better than complex"

**❌ Evitar:**
```python
# Herencia múltiple innecesaria
class Client(LoginMixin, SearchMixin, ArticleMixin, HelpersMixin, Base):
    pass  # ¿De dónde viene cada método?
```

**✅ Preferir:**
```python
# Composición simple y explícita
class Client:
    def __init__(self):
        self.session = Session()
        self.auth = Auth()

    async def login(self, code=None):
        return await login(self.session, self.auth, code)
```

#### ✅ "Flat is better than nested"

**❌ Evitar:**
```python
src/
├── core/
│   ├── modules/
│   │   ├── components/
│   │   │   ├── handlers/
│   │   │   │   └── login.py  # 4 niveles!
```

**✅ Preferir:**
```python
src/
├── client/
│   ├── login.py
│   └── search.py
├── handlers/
│   └── api.py
```

**Máximo 2-3 niveles de anidamiento**

#### ✅ "Explicit is better than implicit"

**❌ Evitar:**
```python
# Magia implícita
class Magic:
    def __getattr__(self, name):
        return lambda: f"Called {name}"  # ¿Qué métodos existen?

magic = Magic()
magic.anything()  # Funciona pero... ¿qué hace?
```

**✅ Preferir:**
```python
# Métodos explícitos
class Client:
    async def login(self):
        """Login explicitly defined."""
        pass

    async def search(self):
        """Search explicitly defined."""
        pass
```

#### ✅ "Readability counts"

**Archivos de 50-200 líneas** son más legibles que 1 archivo de 800 líneas.

---

## 📦 Estructura de Proyectos

### Estructura Estándar Retrofit

```
project/
│
├── README.md                  # Documentación principal
├── pyproject.toml             # Configuración moderna (PEP 621)
├── requirements.txt           # Dependencias
├── .gitignore
│
├── src/
│   ├── __init__.py
│   │
│   ├── exceptions.py          # Excepciones centralizadas
│   ├── config.py              # Configuración
│   │
│   ├── client/                # Módulo cliente
│   │   ├── __init__.py        # Exporta clase principal
│   │   ├── session.py         # Gestión de sesión
│   │   ├── login.py           # Funciones de login
│   │   ├── search.py          # Funciones de búsqueda
│   │   └── helpers.py         # Funciones auxiliares puras
│   │
│   ├── handlers/              # Handlers de API/eventos
│   │   ├── __init__.py
│   │   ├── base.py            # Handler base con lógica común
│   │   ├── api.py             # Handlers de API
│   │   └── events.py          # Handlers de eventos
│   │
│   └── server.py              # Punto de entrada
│
├── tests/
│   ├── __init__.py
│   ├── test_client.py
│   ├── test_handlers.py
│   └── test_helpers.py
│
└── docs/
    ├── technical/
    └── architecture/
```

### Principios de Organización

1. **Un módulo = Una responsabilidad**
   - `login.py` → Solo login
   - `search.py` → Solo búsqueda
   - `helpers.py` → Solo funciones auxiliares

2. **Máximo 200 líneas por archivo**
   - Si crece más, dividir en submódulos

3. **Imports explícitos en `__init__.py`**
   ```python
   # src/client/__init__.py
   from src.client.session import Session
   from src.client.login import login, logout

   __all__ = ['Session', 'login', 'logout']
   ```

---

## 🏗️ Organización del Código

### Orden de Elementos en un Archivo

```python
#!/usr/bin/env python3
"""Module docstring - Qué hace este módulo."""

# 1. Imports estándar
import os
import sys
from pathlib import Path

# 2. Imports de terceros
import requests
from playwright.async_api import async_playwright

# 3. Imports locales
from src.exceptions import CustomError
from src.config import settings

# 4. Constantes módulo
DEFAULT_TIMEOUT = 30
API_VERSION = "v1"

# 5. Clases y funciones
class MyClass:
    """Class docstring."""
    pass

def my_function():
    """Function docstring."""
    pass

# 6. Script principal (si aplica)
if __name__ == "__main__":
    main()
```

### Tamaño de Funciones

**Regla:** Una función = Una responsabilidad

**❌ Evitar funciones largas:**
```python
async def process_user(user_id):
    # 150 líneas de código...
    # Hace validación, búsqueda, procesamiento, logging, notificación...
    pass
```

**✅ Dividir en funciones pequeñas:**
```python
async def process_user(user_id):
    """Procesa un usuario (orquestación)."""
    user = await fetch_user(user_id)
    validate_user(user)
    result = await apply_business_logic(user)
    await notify_result(result)
    return result

async def fetch_user(user_id):
    """Obtiene datos del usuario."""
    pass

def validate_user(user):
    """Valida estructura del usuario."""
    pass

async def apply_business_logic(user):
    """Aplica lógica de negocio."""
    pass

async def notify_result(result):
    """Notifica el resultado."""
    pass
```

---

## 🔧 Funciones vs Clases

### Cuándo Usar Funciones (Preferido)

**✅ Usa funciones cuando:**
- No hay estado que mantener
- Es una transformación pura (input → output)
- Se puede testear fácilmente

```python
# ✅ BUENO: Función pura
def extract_doc_id(text: str) -> str:
    """
    Extrae Doc ID de un texto.

    Función pura: mismo input → mismo output.
    Sin efectos secundarios.
    """
    import re
    match = re.search(r'\[ID\s+(\d+)\]', text)
    return match.group(1) if match else "unknown"
```

### Cuándo Usar Clases

**✅ Usa clases cuando:**
- Necesitas mantener estado
- Necesitas lifecycle (contexto `with`, `async with`)
- Agrupas lógica relacionada con datos

```python
# ✅ BUENO: Clase con estado
class Session:
    """Gestiona sesión de navegador."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser = None
        self.page = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def start(self):
        """Inicia sesión."""
        self.browser = await launch_browser(self.headless)
        self.page = await self.browser.new_page()

    async def close(self):
        """Cierra sesión."""
        if self.browser:
            await self.browser.close()
```

---

## 🧩 Composición sobre Herencia

### ❌ Evitar: Herencia Múltiple

```python
# ❌ MAL: Herencia múltiple confusa
class Client(LoginMixin, SearchMixin, ArticleMixin, Base):
    """¿De dónde viene cada método? No es obvio."""
    pass

client = Client()
client.login()  # ¿De qué clase viene?
```

**Problemas:**
- Método Resolution Order (MRO) complejo
- Difícil de debuggear
- Difícil de testear

### ✅ Preferir: Composición

```python
# ✅ BUENO: Composición explícita
class Client:
    """Cliente con composición clara."""

    def __init__(self):
        self.session = Session()
        self.auth = Auth()

    async def login(self, code=None):
        """Delega explícitamente a módulo login."""
        return await login_module.login(self.session, self.auth, code)

    async def search(self, query):
        """Delega explícitamente a módulo search."""
        return await search_module.search(self.session, query)
```

**Ventajas:**
- Explícito: se ve claramente de dónde viene cada cosa
- Testeable: puedes mockear `session` y `auth`
- Mantenible: cambios localizados

---

## 📝 Convenciones de Nombres

### PEP 8 Naming Conventions

```python
# Módulos y paquetes
my_module.py
my_package/

# Clases (PascalCase)
class MyClass:
    pass

# Funciones y variables (snake_case)
def my_function():
    pass

my_variable = 42

# Constantes (UPPER_CASE)
MAX_CONNECTIONS = 100
API_TIMEOUT = 30

# Métodos/funciones privadas (prefijo _)
def _internal_helper():
    pass

# Métodos "muy privados" (prefijo __)
def __name_mangling():
    pass
```

### Nombres Descriptivos

**❌ Evitar:**
```python
def proc(d):
    return d * 2
```

**✅ Preferir:**
```python
def calculate_double(value: float) -> float:
    """Calcula el doble de un valor."""
    return value * 2
```

---

## 📚 Documentación

### Docstrings (PEP 257)

**Para módulos:**
```python
"""
MOS Client - Functional approach.

Simple client using composition and pure functions.
No mixins, no multiple inheritance - just clean, explicit code.
"""
```

**Para funciones:**
```python
def extract_doc_id(text: str) -> str:
    """
    Extract Doc ID from text/URL.

    Pure function with no side effects.

    Args:
        text: Text containing Doc ID (title, URL, etc.)

    Returns:
        Extracted Doc ID or "unknown" if not found

    Examples:
        >>> extract_doc_id("[ID 123456] Some Article")
        '123456'
        >>> extract_doc_id("(KB147735) Article Title")
        '147735'
    """
    # Implementation...
```

**Para clases:**
```python
class MOSClient:
    """
    MOS client using functional composition.

    Instead of mixins and inheritance, this class wraps a session
    and delegates to pure functions. Simple and explicit.

    Example:
        async with MOSClient(headless=True) as client:
            results = await client.search("ORA-00600", limit=5)
            article = await client.get_article(results[0]['doc_id'])
    """
```

### Type Hints (PEP 484)

**✅ Usar type hints siempre:**
```python
from typing import Optional, List, Dict

async def search(
    session: Session,
    query: str,
    limit: int = 10,
    totp_code: Optional[str] = None
) -> List[Dict[str, str]]:
    """
    Search MOS knowledge base.

    Args:
        session: Active session instance
        query: Search query string
        limit: Maximum results to return
        totp_code: Optional 2FA code

    Returns:
        List of search results with doc_id, title, url
    """
    pass
```

---

## 🧪 Testing

### Estructura de Tests

```python
# tests/test_helpers.py
import pytest
from src.client.helpers import extract_doc_id

def test_extract_doc_id_with_bracket_format():
    """Test extraction with [ID XXXXX] format."""
    result = extract_doc_id("[ID 123456] Some Article")
    assert result == "123456"

def test_extract_doc_id_with_kb_format():
    """Test extraction with (KB#####) format."""
    result = extract_doc_id("(KB147735) Article Title")
    assert result == "147735"

def test_extract_doc_id_unknown():
    """Test extraction when no ID found."""
    result = extract_doc_id("No ID here")
    assert result == "unknown"

@pytest.mark.asyncio
async def test_login_success(mock_session, mock_auth):
    """Test successful login."""
    result = await login(mock_session, mock_auth, "123456")
    assert result is True
```

### Funciones Puras = Fáciles de Testear

**Funciones puras** (sin estado, sin efectos secundarios) son **extremadamente fáciles de testear**:

```python
# ✅ Función pura - Test trivial
def extract_doc_id(text: str) -> str:
    """Función pura."""
    import re
    match = re.search(r'\[ID\s+(\d+)\]', text)
    return match.group(1) if match else "unknown"

# Test: solo necesitas verificar input → output
def test_extract_doc_id():
    assert extract_doc_id("[ID 123]") == "123"
    assert extract_doc_id("No ID") == "unknown"
```

---

## ⚠️ Errores Comunes a Evitar

### 1. ❌ Código Muerto

```python
# ❌ MAL: Función que nunca se usa
def list_service_requests():  # 199 líneas de código muerto
    pass

# ❌ MAL: Test ejecutado al importar
if __name__ == "__main__":
    asyncio.run(test())  # Se ejecuta al importar!
```

**✅ Solución:**
- Revisar periódicamente código no usado
- Eliminar sin miedo (está en git)
- No dejar código comentado

### 2. ❌ Archivos Demasiado Grandes

```python
# ❌ MAL: client.py con 793 líneas
class MOSClient:
    # 160 líneas de login
    # 153 líneas de search
    # 76 líneas de get_article
    # 199 líneas de método no usado
    pass
```

**✅ Solución:**
- Dividir en módulos de 50-200 líneas
- Cada módulo = una responsabilidad

### 3. ❌ Imports Circulares

```python
# ❌ MAL: module_a.py
from module_b import foo

# ❌ MAL: module_b.py
from module_a import bar  # Circular!
```

**✅ Solución:**
- Imports al final de la función (si es necesario)
- Reorganizar módulos
- Usar inyección de dependencias

### 4. ❌ Mutación de Argumentos

```python
# ❌ MAL: Mutación inesperada
def add_item(items_list=[]):
    items_list.append("new")
    return items_list

result1 = add_item()  # ["new"]
result2 = add_item()  # ["new", "new"] ¡Sorpresa!
```

**✅ Solución:**
```python
# ✅ BUENO: Valor por defecto inmutable
def add_item(items_list=None):
    if items_list is None:
        items_list = []
    items_list.append("new")
    return items_list
```

---

## ✅ Checklist de Code Review

### Estructura
- [ ] ¿Archivos < 200 líneas?
- [ ] ¿Funciones < 50 líneas?
- [ ] ¿Estructura de carpetas clara (max 2-3 niveles)?
- [ ] ¿Cada módulo tiene una responsabilidad?

### Código
- [ ] ¿Usa composición en lugar de herencia múltiple?
- [ ] ¿Funciones puras donde es posible?
- [ ] ¿Type hints en funciones públicas?
- [ ] ¿Sin código muerto?
- [ ] ¿Sin imports circulares?

### Documentación
- [ ] ¿Docstrings en funciones públicas?
- [ ] ¿Docstring en módulo?
- [ ] ¿Ejemplos en docstrings de funciones complejas?
- [ ] ¿README actualizado?

### Testing
- [ ] ¿Tests para funciones críticas?
- [ ] ¿Tests para funciones puras?
- [ ] ¿Nombres de tests descriptivos?

### PEP Compliance
- [ ] ¿Sigue PEP 8 (snake_case, etc.)?
- [ ] ¿Sigue PEP 20 (simple, explícito, flat)?
- [ ] ¿Imports ordenados correctamente?

### Performance
- [ ] ¿Sin duplicación innecesaria?
- [ ] ¿Operaciones costosas optimizadas?
- [ ] ¿Usa generadores donde es apropiado?

---

## 📖 Referencias

- [PEP 8 - Style Guide for Python Code](https://peps.python.org/pep-0008/)
- [PEP 20 - The Zen of Python](https://peps.python.org/pep-0020/)
- [PEP 257 - Docstring Conventions](https://peps.python.org/pep-0257/)
- [PEP 484 - Type Hints](https://peps.python.org/pep-0484/)

---

**Nota:** Este documento es un *living document* y se actualiza con cada aprendizaje del equipo.

**Última refactorización:** MOS MCP Server v1.4.0 (Febrero 2026)
- Eliminó 199 líneas de código muerto
- Redujo archivo principal de 793 → 114 líneas
- Aplicó enfoque funcional sobre herencia múltiple

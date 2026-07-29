# Python Best Practices - Retrofit Team

> Python development standards guide based on PEP 8, PEP 20, and Retrofit team experience.

**Updated:** February 2026
**Maintainer:** Retrofit Chapter - MasOrange
**Based on:** MOS MCP Server v1.4.0 refactoring

---

## 📋 Index

1. [The Commandments (PEP 20)](#the-commandments-pep-20)
2. [Project Structure](#project-structure)
3. [Code Organization](#code-organization)
4. [Functions vs Classes](#functions-vs-classes)
5. [Composition over Inheritance](#composition-over-inheritance)
6. [Naming Conventions](#naming-conventions)
7. [Documentation](#documentation)
8. [Testing](#testing)
9. [Common Mistakes to Avoid](#common-mistakes-to-avoid)
10. [Code Review Checklist](#code-review-checklist)

---

## 🧘 The Commandments (PEP 20)

### The Zen of Python

```python
import this
```

### Key Principles Applied in Retrofit

#### ✅ "Simple is better than complex"

**❌ Avoid:**
```python
# Unnecessary multiple inheritance
class Client(LoginMixin, SearchMixin, ArticleMixin, HelpersMixin, Base):
    pass  # Where does each method come from?
```

**✅ Prefer:**
```python
# Simple, explicit composition
class Client:
    def __init__(self):
        self.session = Session()
        self.auth = Auth()

    async def login(self, code=None):
        return await login(self.session, self.auth, code)
```

#### ✅ "Flat is better than nested"

**❌ Avoid:**
```python
src/
├── core/
│   ├── modules/
│   │   ├── components/
│   │   │   ├── handlers/
│   │   │   │   └── login.py  # 4 levels deep!
```

**✅ Prefer:**
```python
src/
├── client/
│   ├── login.py
│   └── search.py
├── handlers/
│   └── api.py
```

**Maximum 2-3 nesting levels.**

#### ✅ "Explicit is better than implicit"

**❌ Avoid:**
```python
# Implicit magic
class Magic:
    def __getattr__(self, name):
        return lambda: f"Called {name}"  # Which methods exist?

magic = Magic()
magic.anything()  # Works but... what does it do?
```

**✅ Prefer:**
```python
# Explicit methods
class Client:
    async def login(self):
        """Login explicitly defined."""
        pass

    async def search(self):
        """Search explicitly defined."""
        pass
```

#### ✅ "Readability counts"

**Files of 50-200 lines** are more readable than one 800-line file.

---

## 📦 Project Structure

### Retrofit Standard Layout

```
project/
│
├── README.md                  # Main documentation
├── pyproject.toml             # Modern config (PEP 621)
├── requirements.txt           # Dependencies
├── .gitignore
│
├── src/
│   ├── __init__.py
│   │
│   ├── exceptions.py          # Centralised exceptions
│   ├── config.py              # Configuration
│   │
│   ├── client/                # Client module
│   │   ├── __init__.py        # Exports main class
│   │   ├── session.py         # Session management
│   │   ├── login.py           # Login functions
│   │   ├── search.py          # Search functions
│   │   └── helpers.py         # Pure helper functions
│   │
│   ├── handlers/              # API/event handlers
│   │   ├── __init__.py
│   │   ├── base.py            # Base handler with shared logic
│   │   ├── api.py             # API handlers
│   │   └── events.py          # Event handlers
│   │
│   └── server.py              # Entry point
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

### Organisation Principles

1. **One module = one responsibility**
   - `login.py` → login only
   - `search.py` → search only
   - `helpers.py` → helper functions only

2. **Maximum 200 lines per file**
   - If it grows, split into submodules.

3. **Explicit imports in `__init__.py`**
   ```python
   # src/client/__init__.py
   from src.client.session import Session
   from src.client.login import login, logout

   __all__ = ['Session', 'login', 'logout']
   ```

---

## 🏗️ Code Organization

### Order of Elements in a File

```python
#!/usr/bin/env python3
"""Module docstring - what this module does."""

# 1. Standard library imports
import os
import sys
from pathlib import Path

# 2. Third-party imports
import requests
from playwright.async_api import async_playwright

# 3. Local imports
from src.exceptions import CustomError
from src.config import settings

# 4. Module-level constants
DEFAULT_TIMEOUT = 30
API_VERSION = "v1"

# 5. Classes and functions
class MyClass:
    """Class docstring."""
    pass

def my_function():
    """Function docstring."""
    pass

# 6. Main script (if applicable)
if __name__ == "__main__":
    main()
```

### Function Size

**Rule:** One function = one responsibility.

**❌ Avoid long functions:**
```python
async def process_user(user_id):
    # 150 lines of code...
    # Does validation, lookup, processing, logging, notification...
    pass
```

**✅ Split into small functions:**
```python
async def process_user(user_id):
    """Process a user (orchestration)."""
    user = await fetch_user(user_id)
    validate_user(user)
    result = await apply_business_logic(user)
    await notify_result(result)
    return result

async def fetch_user(user_id):
    """Fetch user data."""
    pass

def validate_user(user):
    """Validate user structure."""
    pass

async def apply_business_logic(user):
    """Apply business logic."""
    pass

async def notify_result(result):
    """Notify the result."""
    pass
```

---

## 🔧 Functions vs Classes

### When to Use Functions (Preferred)

**✅ Use functions when:**
- There is no state to keep.
- It's a pure transformation (input → output).
- It's easy to test.

```python
# ✅ GOOD: Pure function
def extract_doc_id(text: str) -> str:
    """
    Extract Doc ID from a text.

    Pure function: same input → same output.
    No side effects.
    """
    import re
    match = re.search(r'\[ID\s+(\d+)\]', text)
    return match.group(1) if match else "unknown"
```

### When to Use Classes

**✅ Use classes when:**
- You need to keep state.
- You need a lifecycle (`with`, `async with` contexts).
- You group logic tightly related to data.

```python
# ✅ GOOD: Stateful class
class Session:
    """Manages a browser session."""

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
        """Start the session."""
        self.browser = await launch_browser(self.headless)
        self.page = await self.browser.new_page()

    async def close(self):
        """Close the session."""
        if self.browser:
            await self.browser.close()
```

---

## 🧩 Composition over Inheritance

### ❌ Avoid: Multiple Inheritance

```python
# ❌ BAD: Confusing multiple inheritance
class Client(LoginMixin, SearchMixin, ArticleMixin, Base):
    """Where does each method come from? Not obvious."""
    pass

client = Client()
client.login()  # Which class does this come from?
```

**Problems:**
- Complex Method Resolution Order (MRO).
- Hard to debug.
- Hard to test.

### ✅ Prefer: Composition

```python
# ✅ GOOD: Explicit composition
class Client:
    """Client with clear composition."""

    def __init__(self):
        self.session = Session()
        self.auth = Auth()

    async def login(self, code=None):
        """Explicitly delegate to the login module."""
        return await login_module.login(self.session, self.auth, code)

    async def search(self, query):
        """Explicitly delegate to the search module."""
        return await search_module.search(self.session, query)
```

**Advantages:**
- Explicit: the origin of every call is obvious.
- Testable: `session` and `auth` are easy to mock.
- Maintainable: changes stay localised.

---

## 📝 Naming Conventions

### PEP 8 Naming Conventions

```python
# Modules and packages
my_module.py
my_package/

# Classes (PascalCase)
class MyClass:
    pass

# Functions and variables (snake_case)
def my_function():
    pass

my_variable = 42

# Constants (UPPER_CASE)
MAX_CONNECTIONS = 100
API_TIMEOUT = 30

# Private methods/functions (_ prefix)
def _internal_helper():
    pass

# "Very private" methods (__ prefix)
def __name_mangling():
    pass
```

### Descriptive Names

**❌ Avoid:**
```python
def proc(d):
    return d * 2
```

**✅ Prefer:**
```python
def calculate_double(value: float) -> float:
    """Calculate the double of a value."""
    return value * 2
```

---

## 📚 Documentation

### Docstrings (PEP 257)

**For modules:**
```python
"""
MOS Client - Functional approach.

Simple client using composition and pure functions.
No mixins, no multiple inheritance - just clean, explicit code.
"""
```

**For functions:**
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

**For classes:**
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

**✅ Always use type hints:**
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

### Test Structure

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

### Pure Functions = Easy to Test

**Pure functions** (no state, no side effects) are **trivially testable**:

```python
# ✅ Pure function - trivial test
def extract_doc_id(text: str) -> str:
    """Pure function."""
    import re
    match = re.search(r'\[ID\s+(\d+)\]', text)
    return match.group(1) if match else "unknown"

# Test: just verify input → output
def test_extract_doc_id():
    assert extract_doc_id("[ID 123]") == "123"
    assert extract_doc_id("No ID") == "unknown"
```

---

## ⚠️ Common Mistakes to Avoid

### 1. ❌ Dead Code

```python
# ❌ BAD: Function that is never called
def list_service_requests():  # 199 lines of dead code
    pass

# ❌ BAD: Test executed on import
if __name__ == "__main__":
    asyncio.run(test())  # Runs at import time!
```

**✅ Fix:**
- Review unused code periodically.
- Delete without fear (it's in git).
- Do not leave commented-out code.

### 2. ❌ Files That Are Too Big

```python
# ❌ BAD: client.py with 793 lines
class MOSClient:
    # 160 lines of login
    # 153 lines of search
    # 76 lines of get_article
    # 199 lines of an unused method
    pass
```

**✅ Fix:**
- Split into 50-200 line modules.
- One module = one responsibility.

### 3. ❌ Circular Imports

```python
# ❌ BAD: module_a.py
from module_b import foo

# ❌ BAD: module_b.py
from module_a import bar  # Circular!
```

**✅ Fix:**
- Import inside the function (if needed).
- Reorganise modules.
- Use dependency injection.

### 4. ❌ Argument Mutation

```python
# ❌ BAD: Unexpected mutation
def add_item(items_list=[]):
    items_list.append("new")
    return items_list

result1 = add_item()  # ["new"]
result2 = add_item()  # ["new", "new"] - surprise!
```

**✅ Fix:**
```python
# ✅ GOOD: Immutable default
def add_item(items_list=None):
    if items_list is None:
        items_list = []
    items_list.append("new")
    return items_list
```

---

## ✅ Code Review Checklist

### Structure
- [ ] Are files < 200 lines?
- [ ] Are functions < 50 lines?
- [ ] Is the folder structure clear (max 2-3 levels)?
- [ ] Does each module have a single responsibility?

### Code
- [ ] Does it favour composition over multiple inheritance?
- [ ] Are functions pure where possible?
- [ ] Type hints on public functions?
- [ ] No dead code?
- [ ] No circular imports?

### Documentation
- [ ] Docstrings on public functions?
- [ ] Module-level docstring?
- [ ] Examples in docstrings for complex functions?
- [ ] README up to date?

### Testing
- [ ] Tests for critical functions?
- [ ] Tests for pure functions?
- [ ] Descriptive test names?

### PEP Compliance
- [ ] Follows PEP 8 (snake_case, etc.)?
- [ ] Follows PEP 20 (simple, explicit, flat)?
- [ ] Imports ordered correctly?

### Performance
- [ ] No needless duplication?
- [ ] Expensive operations optimised?
- [ ] Uses generators where appropriate?

---

## 📖 References

- [PEP 8 - Style Guide for Python Code](https://peps.python.org/pep-0008/)
- [PEP 20 - The Zen of Python](https://peps.python.org/pep-0020/)
- [PEP 257 - Docstring Conventions](https://peps.python.org/pep-0257/)
- [PEP 484 - Type Hints](https://peps.python.org/pep-0484/)

---

**Note:** This is a living document, updated with every team learning.

**Last refactor:** MOS MCP Server v1.4.0 (February 2026)
- Removed 199 lines of dead code.
- Cut main file from 793 → 114 lines.
- Adopted functional composition over multiple inheritance.

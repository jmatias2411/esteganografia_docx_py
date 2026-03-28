# Fingerprinting Esteganográfico Robusto — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactorizar `docx_fingerprint.py` para incrustar huellas con AES-256-GCM + HMAC en dos capas independientes (chars invisibles en múltiples XML + Custom XML Part silenciosa), con compatibilidad hacia atrás con documentos v1.

**Architecture:** El payload (nombre + timestamp + hash del doc) se cifra con AES-256-GCM y se firma con HMAC-SHA256 usando una clave local (`fingerprint.key`). Se inyecta en dos capas independientes dentro del ZIP del docx. Al decodificar se prueban ambas capas y, si fallan, se intenta el método legacy.

**Tech Stack:** Python 3.10+, `cryptography` (pip), `zipfile` (stdlib), `tkinter` (stdlib), `pytest` (tests)

---

## Estructura de Archivos

| Archivo | Acción | Responsabilidad |
|---------|--------|-----------------|
| `requirements.txt` | Crear | Dependencia `cryptography` |
| `docx_fingerprint.py` | Modificar | Toda la lógica core (crypto, capas, CLI) |
| `docx_fingerprint_gui.py` | Modificar | Campo de clave, resultado de integridad |
| `tests/test_fingerprint.py` | Crear | Suite de tests TDD |
| `tests/conftest.py` | Crear | Fixtures: docx mínimo, clave de prueba |

---

## Task 1: Setup — requirements.txt y scaffolding de tests

**Files:**
- Create: `requirements.txt`
- Create: `tests/conftest.py`
- Create: `tests/test_fingerprint.py`

- [ ] **Step 1: Crear requirements.txt**

```
cryptography>=42.0.0
pytest>=8.0.0
```

- [ ] **Step 2: Crear tests/conftest.py con fixture de docx mínimo**

```python
# tests/conftest.py
import io
import os
import tempfile
import zipfile
import pytest


def _build_docx_bytes(paragraphs: list[str]) -> bytes:
    """Construye un .docx mínimo válido en memoria."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""")
        z.writestr("_rels/.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""")
        z.writestr("word/_rels/document.xml.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
</Relationships>""")
        paras = "\n".join(
            f'<w:p><w:r><w:t>{p}</w:t></w:r></w:p>' for p in paragraphs
        )
        z.writestr("word/document.xml", f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>{paras}</w:body>
</w:document>""")
    return buf.getvalue()


@pytest.fixture
def tmp_docx(tmp_path):
    """Crea un .docx temporal con 5 párrafos de texto."""
    paragraphs = [
        "Este es el primer parrafo del documento de prueba",
        "Segundo parrafo con contenido relevante para la prueba",
        "Tercer parrafo que contiene informacion adicional aqui",
        "Cuarto parrafo para aumentar la cobertura de inyeccion",
        "Quinto parrafo final del documento de prueba completo",
    ]
    path = tmp_path / "test_document.docx"
    path.write_bytes(_build_docx_bytes(paragraphs))
    return str(path)


@pytest.fixture
def test_key():
    """Clave de 32 bytes fija para tests reproducibles."""
    return b"\x01" * 32
```

- [ ] **Step 3: Crear tests/test_fingerprint.py (vacío con imports)**

```python
# tests/test_fingerprint.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import docx_fingerprint as df
```

- [ ] **Step 4: Instalar dependencias**

```bash
pip install cryptography pytest
```

Expected output: `Successfully installed cryptography-...`

- [ ] **Step 5: Verificar que los tests corren (sin fallos)**

```bash
cd C:/Trabajo/Esteganografia
pytest tests/ -v
```

Expected: `no tests ran` o `0 passed`

---

## Task 2: Gestión de Clave (`load_or_create_key`)

**Files:**
- Modify: `docx_fingerprint.py` — agregar al inicio del archivo
- Modify: `tests/test_fingerprint.py` — tests de clave

- [ ] **Step 1: Escribir los tests**

Agregar al final de `tests/test_fingerprint.py`:

```python
import tempfile
import os


class TestKeyManagement:
    def test_creates_key_if_not_exists(self, tmp_path):
        key_path = str(tmp_path / "new.key")
        key = df.load_or_create_key(key_path)
        assert len(key) == 32
        assert os.path.exists(key_path)

    def test_loads_existing_key(self, tmp_path):
        key_path = str(tmp_path / "existing.key")
        original = os.urandom(32)
        with open(key_path, "wb") as f:
            f.write(original)
        loaded = df.load_or_create_key(key_path)
        assert loaded == original

    def test_same_key_returned_twice(self, tmp_path):
        key_path = str(tmp_path / "stable.key")
        key1 = df.load_or_create_key(key_path)
        key2 = df.load_or_create_key(key_path)
        assert key1 == key2
```

- [ ] **Step 2: Ejecutar tests — verificar que fallan**

```bash
pytest tests/test_fingerprint.py::TestKeyManagement -v
```

Expected: `AttributeError: module 'docx_fingerprint' has no attribute 'load_or_create_key'`

- [ ] **Step 3: Implementar en docx_fingerprint.py**

Agregar después de los imports existentes (después de `from pathlib import Path`):

```python
# ─── Gestión de clave ────────────────────────────────────────────────────────

DEFAULT_KEY_FILE = "fingerprint.key"


def load_or_create_key(key_path: str = DEFAULT_KEY_FILE) -> bytes:
    """Carga la clave secreta desde archivo o genera una nueva si no existe."""
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            key = f.read()
        if len(key) != 32:
            raise ValueError(f"Clave inválida en {key_path}: debe ser 32 bytes.")
        return key
    key = os.urandom(32)
    with open(key_path, "wb") as f:
        f.write(key)
    print(f"🔑 Clave generada: {key_path}  ← ¡Guárdala en lugar seguro!")
    return key
```

- [ ] **Step 4: Ejecutar tests — verificar que pasan**

```bash
pytest tests/test_fingerprint.py::TestKeyManagement -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add requirements.txt tests/ docx_fingerprint.py
git commit -m "feat: setup tests y gestion de clave fingerprint.key"
```

---

## Task 3: Capa Criptográfica (`encrypt_payload` / `decrypt_payload`)

**Files:**
- Modify: `docx_fingerprint.py`
- Modify: `tests/test_fingerprint.py`

- [ ] **Step 1: Escribir los tests**

```python
class TestCrypto:
    def test_roundtrip(self, test_key):
        data = {"recipient": "Pepe García", "timestamp": "2026-03-28T10:00:00", "doc_hash": "abc123"}
        raw = df.encrypt_payload(data, test_key)
        assert isinstance(raw, bytes)
        result = df.decrypt_payload(raw, test_key)
        assert result == data

    def test_wrong_key_raises(self, test_key):
        data = {"recipient": "Ana", "timestamp": "2026-03-28T10:00:00", "doc_hash": "xyz"}
        raw = df.encrypt_payload(data, test_key)
        wrong_key = b"\x02" * 32
        with pytest.raises(ValueError, match="HMAC"):
            df.decrypt_payload(raw, wrong_key)

    def test_tampered_data_raises(self, test_key):
        data = {"recipient": "Luis", "timestamp": "2026-03-28T10:00:00", "doc_hash": "def"}
        raw = bytearray(df.encrypt_payload(data, test_key))
        raw[20] ^= 0xFF  # corromper un byte del HMAC
        with pytest.raises(ValueError):
            df.decrypt_payload(bytes(raw), test_key)

    def test_different_nonce_each_call(self, test_key):
        data = {"recipient": "Test", "timestamp": "2026-03-28T10:00:00", "doc_hash": "hash"}
        raw1 = df.encrypt_payload(data, test_key)
        raw2 = df.encrypt_payload(data, test_key)
        assert raw1 != raw2  # nonce aleatorio → ciphertexts distintos
```

- [ ] **Step 2: Ejecutar tests — verificar que fallan**

```bash
pytest tests/test_fingerprint.py::TestCrypto -v
```

Expected: `AttributeError: module 'docx_fingerprint' has no attribute 'encrypt_payload'`

- [ ] **Step 3: Agregar import de cryptography al inicio de docx_fingerprint.py**

Agregar junto a los imports existentes:

```python
import hmac as hmac_mod
import hashlib
import struct

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False
```

- [ ] **Step 4: Implementar encrypt_payload y decrypt_payload**

Agregar después de la sección de gestión de clave:

```python
# ─── Capa criptográfica (v2) ─────────────────────────────────────────────────
# Formato del blob cifrado: nonce(12B) + hmac(32B) + ciphertext(variable)


def _require_crypto():
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError(
            "La librería 'cryptography' no está instalada.\n"
            "Ejecuta: pip install cryptography"
        )


def encrypt_payload(data: dict, key: bytes) -> bytes:
    """
    Cifra el payload con AES-256-GCM y lo firma con HMAC-SHA256.
    Retorna bytes: nonce(12) + hmac(32) + ciphertext.
    """
    _require_crypto()
    plaintext = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    mac = hmac_mod.new(key, nonce + ciphertext, hashlib.sha256).digest()
    return nonce + mac + ciphertext


def decrypt_payload(raw: bytes, key: bytes) -> dict:
    """
    Verifica HMAC y descifra el payload.
    Lanza ValueError si el HMAC no coincide o si la clave es incorrecta.
    """
    _require_crypto()
    if len(raw) < 12 + 32 + 16:
        raise ValueError("Blob demasiado corto — datos corruptos.")
    nonce = raw[:12]
    mac_stored = raw[12:44]
    ciphertext = raw[44:]
    mac_expected = hmac_mod.new(key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac_mod.compare_digest(mac_stored, mac_expected):
        raise ValueError("HMAC inválido — huella alterada o clave incorrecta.")
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
    return json.loads(plaintext.decode("utf-8"))
```

- [ ] **Step 5: Ejecutar tests — verificar que pasan**

```bash
pytest tests/test_fingerprint.py::TestCrypto -v
```

Expected: `4 passed`

- [ ] **Step 6: Commit**

```bash
git add docx_fingerprint.py tests/test_fingerprint.py
git commit -m "feat: capa criptografica AES-256-GCM + HMAC-SHA256"
```

---

## Task 4: Codificación Invisible V2 (4 símbolos, 2 bits/char)

**Files:**
- Modify: `docx_fingerprint.py`
- Modify: `tests/test_fingerprint.py`

- [ ] **Step 1: Escribir los tests**

```python
class TestInvisibleEncodingV2:
    def test_roundtrip_bytes(self):
        data = b"\x00\xFF\xAB\x42\x00"
        invisible = df.bytes_to_invisible(data)
        assert invisible.startswith('\uFEFF')
        assert invisible.endswith('\uFEFF')
        recovered = df.invisible_to_bytes(invisible)
        assert recovered == data

    def test_roundtrip_arbitrary(self):
        for val in [b"", b"hello", os.urandom(50)]:
            assert df.invisible_to_bytes(df.bytes_to_invisible(val)) == val

    def test_only_valid_chars(self):
        invisible = df.bytes_to_invisible(b"\xAB\xCD")
        valid = {'\uFEFF', '\u200B', '\u200C', '\u200D', '\u2060'}
        assert all(c in valid for c in invisible)

    def test_returns_none_if_no_marker(self):
        assert df.invisible_to_bytes("texto normal sin marcadores") is None

    def test_ignores_surrounding_text(self):
        data = b"\x42\x43"
        invisible = df.bytes_to_invisible(data)
        text_with_context = "Texto antes " + invisible + " texto después"
        assert df.invisible_to_bytes(text_with_context) == data
```

- [ ] **Step 2: Ejecutar tests — verificar que fallan**

```bash
pytest tests/test_fingerprint.py::TestInvisibleEncodingV2 -v
```

Expected: `AttributeError: module 'docx_fingerprint' has no attribute 'bytes_to_invisible'`

- [ ] **Step 3: Implementar en docx_fingerprint.py**

Agregar después de la sección criptográfica:

```python
# ─── Codificación invisible v2 (4 símbolos, 2 bits/char) ────────────────────

_MARKER_V2 = "\uFEFF"  # BOM como marcador inicio/fin
_BITS_TO_CHAR = {"00": "\u200B", "01": "\u200C", "10": "\u200D", "11": "\u2060"}
_CHAR_TO_BITS = {v: k for k, v in _BITS_TO_CHAR.items()}


def bytes_to_invisible(data: bytes) -> str:
    """Convierte bytes a string con chars invisibles entre marcadores FEFF."""
    result = [_MARKER_V2]
    for byte in data:
        bits = f"{byte:08b}"
        result.append(_BITS_TO_CHAR[bits[0:2]])
        result.append(_BITS_TO_CHAR[bits[2:4]])
        result.append(_BITS_TO_CHAR[bits[4:6]])
        result.append(_BITS_TO_CHAR[bits[6:8]])
    result.append(_MARKER_V2)
    return "".join(result)


def invisible_to_bytes(text: str) -> bytes | None:
    """Extrae bytes de la primera secuencia entre marcadores FEFF."""
    start = text.find(_MARKER_V2)
    if start == -1:
        return None
    end = text.find(_MARKER_V2, start + 1)
    if end == -1:
        return None
    segment = text[start + 1:end]
    bits = "".join(_CHAR_TO_BITS[c] for c in segment if c in _CHAR_TO_BITS)
    if len(bits) % 8 != 0:
        return None
    return bytes(int(bits[i:i+8], 2) for i in range(0, len(bits), 8))
```

- [ ] **Step 4: Ejecutar tests — verificar que pasan**

```bash
pytest tests/test_fingerprint.py::TestInvisibleEncodingV2 -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add docx_fingerprint.py tests/test_fingerprint.py
git commit -m "feat: codificacion invisible v2 con 4 simbolos y marcadores FEFF"
```

---

## Task 5: Capa 1 — Inyección multi-XML

**Files:**
- Modify: `docx_fingerprint.py`
- Modify: `tests/test_fingerprint.py`

- [ ] **Step 1: Escribir los tests**

```python
import tempfile
import zipfile


class TestLayer1:
    def _extract_docx(self, docx_bytes: bytes, dest: str):
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
            z.extractall(dest)

    def test_inject_into_xml_adds_payload(self):
        xml = '<w:t>Hola mundo texto aqui</w:t>'
        payload = df.bytes_to_invisible(b"\x42")
        result = df.inject_into_xml(xml, payload)
        assert payload in result
        assert "Hola" in result  # texto original intacto

    def test_inject_into_xml_no_match_returns_unchanged(self):
        xml = '<w:t>ab</w:t>'  # texto < 3 chars
        payload = df.bytes_to_invisible(b"\x42")
        result = df.inject_into_xml(xml, payload)
        assert result == xml

    def test_get_injectable_xml_files_finds_document(self, tmp_docx):
        with tempfile.TemporaryDirectory() as tmpdir:
            df.extract_docx(tmp_docx, tmpdir)
            files = df.get_injectable_xml_files(tmpdir)
        assert any("document.xml" in f for f in files)

    def test_inject_and_extract_layer1_roundtrip(self, tmp_docx, test_key):
        data = {"recipient": "Ana López", "timestamp": "2026-01-01T00:00:00", "doc_hash": "abc"}
        raw = df.encrypt_payload(data, test_key)
        invisible = df.bytes_to_invisible(raw)
        with tempfile.TemporaryDirectory() as tmpdir:
            df.extract_docx(tmp_docx, tmpdir)
            df.inject_layer1(tmpdir, invisible)
            recovered_raw = df.extract_layer1(tmpdir)
        assert recovered_raw == raw
```

- [ ] **Step 2: Ejecutar tests — verificar que fallan**

```bash
pytest tests/test_fingerprint.py::TestLayer1 -v
```

Expected: `AttributeError: module 'docx_fingerprint' has no attribute 'inject_into_xml'`

- [ ] **Step 3: Implementar en docx_fingerprint.py**

Agregar después de la sección de codificación invisible:

```python
# ─── Capa 1: Inyección en múltiples XML (chars invisibles) ──────────────────

_INJECTABLE_XML_NAMES = [
    os.path.join("word", "document.xml"),
    os.path.join("word", "header1.xml"),
    os.path.join("word", "header2.xml"),
    os.path.join("word", "header3.xml"),
    os.path.join("word", "footer1.xml"),
    os.path.join("word", "footer2.xml"),
    os.path.join("word", "footer3.xml"),
    os.path.join("word", "footnotes.xml"),
    os.path.join("word", "endnotes.xml"),
]
_WT_PATTERN = re.compile(r'(<w:t(?:\s[^>]*)?>)([^<]{3,})(</w:t>)')


def get_injectable_xml_files(extract_dir: str) -> list[str]:
    """Retorna rutas absolutas de los XML inyectables que existen en el docx."""
    return [
        os.path.join(extract_dir, name)
        for name in _INJECTABLE_XML_NAMES
        if os.path.exists(os.path.join(extract_dir, name))
    ]


def inject_into_xml(xml_content: str, invisible_payload: str) -> str:
    """
    Inyecta el payload en hasta 5 posiciones distribuidas del XML.
    Posición dentro del texto: aleatoria entre inicio y fin del fragmento.
    """
    import random
    matches = list(_WT_PATTERN.finditer(xml_content))
    if not matches:
        return xml_content

    # Seleccionar hasta 5 posiciones distribuidas uniformemente
    step = max(1, len(matches) // 5)
    selected = matches[::step][:5]

    new_content = xml_content
    for match in reversed(selected):
        opening, text, closing = match.group(1), match.group(2), match.group(3)
        words = text.split(" ")
        if len(words) >= 2:
            pos = random.randint(1, len(words) - 1)
            words.insert(pos, invisible_payload)
            new_text = " ".join(words)
        else:
            new_text = text + invisible_payload
        new_content = (
            new_content[: match.start()]
            + opening + new_text + closing
            + new_content[match.end():]
        )
    return new_content


def inject_layer1(extract_dir: str, invisible_payload: str) -> list[str]:
    """Inyecta el payload en todos los XML inyectables. Retorna lista de archivos modificados."""
    modified = []
    for xml_path in get_injectable_xml_files(extract_dir):
        with open(xml_path, "r", encoding="utf-8") as f:
            content = f.read()
        new_content = inject_into_xml(content, invisible_payload)
        if new_content != content:
            with open(xml_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            modified.append(xml_path)
    return modified


def extract_layer1(extract_dir: str) -> bytes | None:
    """Busca y extrae el payload de la Capa 1 en todos los XML del docx."""
    for xml_path in get_injectable_xml_files(extract_dir):
        if not os.path.exists(xml_path):
            continue
        with open(xml_path, "rb") as f:
            content = f.read().decode("utf-8")
        raw = invisible_to_bytes(content)
        if raw is not None:
            return raw
    return None
```

- [ ] **Step 4: Ejecutar tests — verificar que pasan**

```bash
pytest tests/test_fingerprint.py::TestLayer1 -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add docx_fingerprint.py tests/test_fingerprint.py
git commit -m "feat: capa 1 inyeccion multi-XML con chars invisibles v2"
```

---

## Task 6: Capa 2 — Custom XML Part silenciosa

**Files:**
- Modify: `docx_fingerprint.py`
- Modify: `tests/test_fingerprint.py`

- [ ] **Step 1: Escribir los tests**

```python
import io


class TestLayer2:
    def test_inject_and_extract_roundtrip(self, tmp_docx, test_key):
        data = {"recipient": "Carlos", "timestamp": "2026-01-01T00:00:00", "doc_hash": "xyz"}
        raw = df.encrypt_payload(data, test_key)
        with tempfile.TemporaryDirectory() as tmpdir:
            df.extract_docx(tmp_docx, tmpdir)
            df.inject_layer2(tmpdir, raw)
            recovered = df.extract_layer2(tmpdir)
        assert recovered == raw

    def test_custom_xml_file_created(self, tmp_docx):
        with tempfile.TemporaryDirectory() as tmpdir:
            df.extract_docx(tmp_docx, tmpdir)
            df.inject_layer2(tmpdir, b"\xDE\xAD\xBE\xEF")
            xml_path = os.path.join(tmpdir, "word", "customXml", "fingerprint.xml")
            assert os.path.exists(xml_path)

    def test_extract_returns_none_if_absent(self, tmp_docx):
        with tempfile.TemporaryDirectory() as tmpdir:
            df.extract_docx(tmp_docx, tmpdir)
            assert df.extract_layer2(tmpdir) is None

    def test_content_types_updated(self, tmp_docx):
        with tempfile.TemporaryDirectory() as tmpdir:
            df.extract_docx(tmp_docx, tmpdir)
            df.inject_layer2(tmpdir, b"\x01\x02")
            ct_path = os.path.join(tmpdir, "[Content_Types].xml")
            ct = open(ct_path).read()
            assert "fingerprint.xml" in ct
```

- [ ] **Step 2: Ejecutar tests — verificar que fallan**

```bash
pytest tests/test_fingerprint.py::TestLayer2 -v
```

Expected: `AttributeError: module 'docx_fingerprint' has no attribute 'inject_layer2'`

- [ ] **Step 3: Implementar en docx_fingerprint.py**

Agregar después de la sección de Capa 1:

```python
# ─── Capa 2: Custom XML Part silenciosa ──────────────────────────────────────

_CUSTOM_XML_DIR = os.path.join("word", "customXml")
_CUSTOM_XML_FILE = os.path.join(_CUSTOM_XML_DIR, "fingerprint.xml")
_CUSTOM_XML_NS = "urn:fingerprint:v2"
_CONTENT_TYPES_FILE = "[Content_Types].xml"
_DOC_RELS_FILE = os.path.join("word", "_rels", "document.xml.rels")


def inject_layer2(extract_dir: str, raw_payload: bytes) -> None:
    """
    Crea word/customXml/fingerprint.xml con el payload en base64.
    Actualiza [Content_Types].xml y word/_rels/document.xml.rels.
    """
    import base64

    # 1. Crear directorio y archivo XML
    custom_dir = os.path.join(extract_dir, _CUSTOM_XML_DIR)
    os.makedirs(custom_dir, exist_ok=True)
    b64 = base64.b64encode(raw_payload).decode("ascii")
    xml_content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<fingerprint xmlns="{_CUSTOM_XML_NS}">\n'
        f'  <data><![CDATA[{b64}]]></data>\n'
        '</fingerprint>\n'
    )
    with open(os.path.join(extract_dir, _CUSTOM_XML_FILE), "w", encoding="utf-8") as f:
        f.write(xml_content)

    # 2. Actualizar [Content_Types].xml
    ct_path = os.path.join(extract_dir, _CONTENT_TYPES_FILE)
    with open(ct_path, "r", encoding="utf-8") as f:
        ct = f.read()
    override = '<Override PartName="/word/customXml/fingerprint.xml" ContentType="application/xml"/>'
    if "fingerprint.xml" not in ct:
        ct = ct.replace("</Types>", f"  {override}\n</Types>")
        with open(ct_path, "w", encoding="utf-8") as f:
            f.write(ct)

    # 3. Actualizar word/_rels/document.xml.rels
    rels_path = os.path.join(extract_dir, _DOC_RELS_FILE)
    if os.path.exists(rels_path):
        with open(rels_path, "r", encoding="utf-8") as f:
            rels = f.read()
        rel_type = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml"
        rel_entry = f'<Relationship Id="rIdFP1" Type="{rel_type}" Target="customXml/fingerprint.xml"/>'
        if "fingerprint.xml" not in rels:
            rels = rels.replace("</Relationships>", f"  {rel_entry}\n</Relationships>")
            with open(rels_path, "w", encoding="utf-8") as f:
                f.write(rels)


def extract_layer2(extract_dir: str) -> bytes | None:
    """Extrae el payload raw de word/customXml/fingerprint.xml. Retorna None si no existe."""
    import base64
    xml_path = os.path.join(extract_dir, _CUSTOM_XML_FILE)
    if not os.path.exists(xml_path):
        return None
    with open(xml_path, "r", encoding="utf-8") as f:
        content = f.read()
    # Extraer contenido del CDATA
    match = re.search(r'<!\[CDATA\[([^\]]+)\]\]>', content)
    if not match:
        return None
    try:
        return base64.b64decode(match.group(1))
    except Exception:
        return None
```

- [ ] **Step 4: Ejecutar tests — verificar que pasan**

```bash
pytest tests/test_fingerprint.py::TestLayer2 -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add docx_fingerprint.py tests/test_fingerprint.py
git commit -m "feat: capa 2 custom XML part silenciosa en docx"
```

---

## Task 7: Encode/Decode V2 completo con fallback

**Files:**
- Modify: `docx_fingerprint.py`
- Modify: `tests/test_fingerprint.py`

- [ ] **Step 1: Escribir los tests**

```python
class TestEncodeDecode:
    def test_encode_decode_v2_roundtrip(self, tmp_docx, test_key, tmp_path):
        output = str(tmp_path / "out.docx")
        result = df.encode_document(tmp_docx, "María López", output, test_key)
        assert os.path.exists(output)
        assert result["recipient"] == "María López"
        assert result["layers_injected"] == ["text", "custom_xml"]

        decoded = df.decode_document(output, test_key)
        assert decoded is not None
        assert decoded["recipient"] == "María López"
        assert decoded["layer_used"] in ("custom_xml", "text")

    def test_decode_detects_unmodified_doc(self, tmp_docx, test_key, tmp_path):
        output = str(tmp_path / "out.docx")
        df.encode_document(tmp_docx, "Pedro", output, test_key)
        decoded = df.decode_document(output, test_key)
        assert decoded["doc_intact"] is True

    def test_decode_returns_none_for_clean_doc(self, tmp_docx, test_key):
        decoded = df.decode_document(tmp_docx, test_key)
        assert decoded is None

    def test_decode_falls_back_to_layer1_if_layer2_missing(self, tmp_docx, test_key, tmp_path):
        output = str(tmp_path / "out_no_l2.docx")
        df.encode_document(tmp_docx, "Luisa", output, test_key)
        # Eliminar la capa 2 del ZIP resultante
        buf = io.BytesIO()
        with zipfile.ZipFile(output, "r") as zin, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if "fingerprint.xml" not in item.filename:
                    zout.writestr(item, zin.read(item.filename))
        stripped_path = str(tmp_path / "stripped.docx")
        with open(stripped_path, "wb") as f:
            f.write(buf.getvalue())

        decoded = df.decode_document(stripped_path, test_key)
        assert decoded is not None
        assert decoded["recipient"] == "Luisa"
        assert decoded["layer_used"] == "text"

    def test_legacy_doc_still_decodable(self, tmp_docx, tmp_path):
        """Documentos marcados con v1 (sin clave) siguen siendo decodificables."""
        output = str(tmp_path / "legacy.docx")
        # Usar el encode legacy (v1) directamente
        with tempfile.TemporaryDirectory() as tmpdir:
            df.extract_docx(tmp_docx, tmpdir)
            doc_xml = os.path.join(tmpdir, "word", "document.xml")
            with open(doc_xml, "r", encoding="utf-8") as f:
                xml = f.read()
            payload_v1 = df.encode_payload("Pepe Legacy")
            new_xml = df.inject_fingerprint_into_xml(xml, payload_v1)
            with open(doc_xml, "w", encoding="utf-8") as f:
                f.write(new_xml)
            df.pack_docx(tmpdir, output)

        decoded = df.decode_document(output, b"\x00" * 32)  # clave cualquiera
        assert decoded is not None
        assert decoded["recipient"] == "Pepe Legacy"
        assert decoded["layer_used"] == "legacy"
```

- [ ] **Step 2: Ejecutar tests — verificar que fallan**

```bash
pytest tests/test_fingerprint.py::TestEncodeDecode -v
```

Expected: `AttributeError: module 'docx_fingerprint' has no attribute 'encode_document'`

- [ ] **Step 3: Agregar hash_document_xml en docx_fingerprint.py**

Agregar después de la sección de Capa 2:

```python
# ─── Hash de integridad del documento ────────────────────────────────────────

def hash_document_xml(extract_dir: str) -> str:
    """SHA-256 hex de word/document.xml (antes de inyectar huellas)."""
    doc_path = os.path.join(extract_dir, "word", "document.xml")
    with open(doc_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()
```

- [ ] **Step 4: Implementar encode_document y decode_document en docx_fingerprint.py**

Agregar a continuación:

```python
# ─── Encode / Decode V2 ──────────────────────────────────────────────────────

def encode_document(docx_path: str, name: str, output_path: str, key: bytes) -> dict:
    """
    Genera una copia del docx con huella v2 en dos capas.
    Retorna dict con metadatos del registro.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        extract_docx(docx_path, tmpdir)
        doc_hash = hash_document_xml(tmpdir)
        payload_data = {
            "recipient": name,
            "timestamp": datetime.now().isoformat(),
            "doc_hash": doc_hash,
        }
        raw = encrypt_payload(payload_data, key)
        invisible = bytes_to_invisible(raw)

        layers = []
        modified = inject_layer1(tmpdir, invisible)
        if modified:
            layers.append("text")
        inject_layer2(tmpdir, raw)
        layers.append("custom_xml")

        pack_docx(tmpdir, output_path)

    mac = hmac_mod.new(key, raw, hashlib.sha256).hexdigest()[:16]
    return {
        "recipient": name,
        "output_file": output_path,
        "source_file": docx_path,
        "timestamp": payload_data["timestamp"],
        "doc_hash": doc_hash[:16],
        "payload_hmac": mac,
        "layers_injected": layers,
        "version": 2,
    }


def decode_document(docx_path: str, key: bytes) -> dict | None:
    """
    Intenta decodificar la huella probando: Capa 2 → Capa 1 → Legacy.
    Retorna dict con recipient, timestamp, doc_intact, layer_used — o None.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        extract_docx(docx_path, tmpdir)
        current_hash = hash_document_xml(tmpdir)

        # Capa 2 (custom XML)
        raw = extract_layer2(tmpdir)
        layer = "custom_xml"

        # Capa 1 (chars invisibles v2)
        if raw is None:
            raw = extract_layer1(tmpdir)
            layer = "text"

        if raw is not None:
            try:
                data = decrypt_payload(raw, key)
                return {
                    "recipient": data["recipient"],
                    "timestamp": data["timestamp"],
                    "doc_hash_original": data.get("doc_hash", ""),
                    "doc_intact": data.get("doc_hash", "") == current_hash,
                    "layer_used": layer,
                }
            except (ValueError, Exception):
                pass

        # Fallback legacy (v1 sin cifrado)
        doc_xml_path = os.path.join(tmpdir, "word", "document.xml")
        with open(doc_xml_path, "rb") as f:
            raw_xml = f.read().decode("utf-8")
        name_legacy = decode_payload(raw_xml)
        if name_legacy:
            return {
                "recipient": name_legacy,
                "timestamp": "",
                "doc_hash_original": "",
                "doc_intact": None,
                "layer_used": "legacy",
            }

    return None
```

- [ ] **Step 5: Ejecutar tests — verificar que pasan**

```bash
pytest tests/test_fingerprint.py::TestEncodeDecode -v
```

Expected: `5 passed`

- [ ] **Step 6: Ejecutar toda la suite**

```bash
pytest tests/ -v
```

Expected: todos los tests de tasks anteriores + los 5 nuevos pasan.

- [ ] **Step 7: Commit**

```bash
git add docx_fingerprint.py tests/test_fingerprint.py
git commit -m "feat: encode_document y decode_document v2 con fallback chain"
```

---

## Task 8: Registro V2 y CLI con flag `--key`

**Files:**
- Modify: `docx_fingerprint.py` — register_fingerprint_v2, cmd_encode, cmd_decode, argparse

- [ ] **Step 1: Agregar register_fingerprint_v2 en docx_fingerprint.py**

Agregar después de la función `register_fingerprint` existente (no eliminarla):

```python
def register_fingerprint_v2(entry: dict):
    """Guarda una entrada v2 en el registro. entry es el dict retornado por encode_document."""
    registry = load_registry()
    if "version" not in registry:
        registry["version"] = 2
    registry["fingerprints"].append(entry)
    save_registry(registry)
```

- [ ] **Step 2: Actualizar cmd_encode para usar encode_document + --key**

Reemplazar la función `cmd_encode` completa:

```python
def cmd_encode(args):
    docx_path = args.input
    name = args.name
    output_path = args.output or f"{Path(docx_path).stem}__{name.replace(' ', '_')}.docx"
    key_path = args.key or DEFAULT_KEY_FILE

    if not os.path.exists(docx_path):
        print(f"❌ No se encontró el archivo: {docx_path}")
        sys.exit(1)

    print(f"🔏 Codificando huella v2 para: '{name}'")
    print(f"   Fuente : {docx_path}")
    print(f"   Destino: {output_path}")
    print(f"   Clave  : {key_path}")

    key = load_or_create_key(key_path)
    entry = encode_document(docx_path, name, output_path, key)
    register_fingerprint_v2(entry)

    print(f"\n✅ Documento generado: {output_path}")
    print(f"   Capas inyectadas : {', '.join(entry['layers_injected'])}")
    print(f"   HMAC de huella   : {entry['payload_hmac']}")
    print(f"   Registro guardado: {REGISTRY_FILE}")
    print(f"\n💡 Envía '{output_path}' a {name}.")
    print(f"   Si aparece filtrado, usa: decode --key {key_path}")
```

- [ ] **Step 3: Actualizar cmd_decode para usar decode_document + --key**

Reemplazar la función `cmd_decode` completa:

```python
def cmd_decode(args):
    docx_path = args.input
    key_path = args.key or DEFAULT_KEY_FILE

    if not os.path.exists(docx_path):
        print(f"❌ No se encontró el archivo: {docx_path}")
        sys.exit(1)

    if not os.path.exists(key_path) and key_path == DEFAULT_KEY_FILE:
        print(f"⚠️  No se encontró clave en '{key_path}'.")
        print(f"   Intentando decodificación legacy (v1)...")
        key = b"\x00" * 32  # clave dummy, solo activa fallback legacy
    else:
        key = load_or_create_key(key_path)

    print(f"🔍 Analizando huella en: {docx_path}\n")

    result = decode_document(docx_path, key)

    if result:
        integrity = ""
        if result["doc_intact"] is True:
            integrity = "✅ Contenido íntegro"
        elif result["doc_intact"] is False:
            integrity = "⚠️  Contenido MODIFICADO desde el envío"
        else:
            integrity = "(documento v1 — verificación no disponible)"

        print(f"🎯 ¡HUELLA ENCONTRADA! (via {result['layer_used']})")
        print(f"   Destinatario : {result['recipient']}")
        if result["timestamp"]:
            print(f"   Fecha envío  : {result['timestamp'][:19].replace('T', ' ')}")
        print(f"   Integridad   : {integrity}")

        registry = load_registry()
        matches = [
            e for e in registry["fingerprints"]
            if e["recipient"].lower() == result["recipient"].lower()
        ]
        if matches:
            print(f"\n📋 Registros locales ({len(matches)}):")
            for m in matches:
                print(f"   • {m['output_file']}  [{m['timestamp'][:19].replace('T', ' ')}]")
        else:
            print(f"\n⚠️  Sin registro local para '{result['recipient']}'.")
    else:
        print("❓ No se encontró ninguna huella en este documento.")
```

- [ ] **Step 4: Actualizar argparse para agregar --key a encode y decode**

Localizar el bloque donde se crea `p_enc` y `p_dec` y agregar el argumento `--key`:

```python
    # encode
    p_enc = sub.add_parser("encode", help="Generar copia con huella para un destinatario")
    p_enc.add_argument("input", help="Archivo .docx original")
    p_enc.add_argument("name", help="Nombre del destinatario (ej: 'Pepe García')")
    p_enc.add_argument("--output", "-o", help="Nombre del archivo de salida (opcional)")
    p_enc.add_argument("--key", "-k", help=f"Archivo de clave (default: {DEFAULT_KEY_FILE})")

    # decode
    p_dec = sub.add_parser("decode", help="Identificar destinatario de un doc filtrado")
    p_dec.add_argument("input", help="Archivo .docx a analizar")
    p_dec.add_argument("--key", "-k", help=f"Archivo de clave (default: {DEFAULT_KEY_FILE})")
```

- [ ] **Step 5: Verificar CLI manualmente con un docx de prueba**

```bash
cd C:/Trabajo/Esteganografia
python docx_fingerprint.py --help
```

Expected: muestra ayuda con subcomandos encode, decode, list y flags --key.

- [ ] **Step 6: Ejecutar toda la suite de tests**

```bash
pytest tests/ -v
```

Expected: todos los tests pasan.

- [ ] **Step 7: Commit**

```bash
git add docx_fingerprint.py
git commit -m "feat: CLI v2 con --key flag y registro enriquecido"
```

---

## Task 9: Actualización de la GUI

**Files:**
- Modify: `docx_fingerprint_gui.py`

- [ ] **Step 1: Agregar campo de clave en setup_encode_tab**

Localizar el método `setup_encode_tab` y agregar la fila del campo de clave después de la fila "Guardar en (opcional)":

```python
    def setup_encode_tab(self):
        # ... (código existente sin cambios hasta la fila 2) ...

        ttk.Label(self.tab_encode, text="Archivo de clave (.key):", font=("Helvetica", 10, "bold")).grid(row=3, column=0, sticky='w', pady=5)
        self.enc_key_var = tk.StringVar(value=df.DEFAULT_KEY_FILE)
        ttk.Entry(self.tab_encode, textvariable=self.enc_key_var, width=50).grid(row=3, column=1, padx=10, pady=5, sticky='ew')
        ttk.Button(self.tab_encode, text="Explorar...", command=self.browse_enc_key).grid(row=3, column=2, pady=5)

        # Botón (mover de row=3 a row=4)
        btn_frame = ttk.Frame(self.tab_encode)
        btn_frame.grid(row=4, column=0, columnspan=3, pady=20)
        ttk.Button(btn_frame, text="✅ Generar Documento Seguro", command=self.generate_doc, width=30).pack(ipady=5)
```

- [ ] **Step 2: Agregar campo de clave en setup_decode_tab**

Localizar `setup_decode_tab` y agregar la fila de clave después del campo de archivo:

```python
    def setup_decode_tab(self):
        # ... fila 0 existente sin cambios ...

        ttk.Label(self.tab_decode, text="Archivo de clave (.key):", font=("Helvetica", 10, "bold")).grid(row=1, column=0, sticky='w', pady=5)
        self.dec_key_var = tk.StringVar(value=df.DEFAULT_KEY_FILE)
        ttk.Entry(self.tab_decode, textvariable=self.dec_key_var, width=50).grid(row=1, column=1, padx=10, pady=5, sticky='ew')
        ttk.Button(self.tab_decode, text="Explorar...", command=self.browse_dec_key).grid(row=1, column=2, pady=5)

        # Botón (mover de row=1 a row=2)
        btn_frame = ttk.Frame(self.tab_decode)
        btn_frame.grid(row=2, column=0, columnspan=3, pady=20)
        ttk.Button(btn_frame, text="🔍 Analizar Documento", command=self.analyze_doc, width=30).pack(ipady=5)

        ttk.Label(self.tab_decode, text="Resultados del Análisis:", font=("Helvetica", 10, "bold")).grid(row=3, column=0, sticky='w', pady=5, columnspan=3)
        self.dec_result_text = tk.Text(self.tab_decode, height=12, width=60, font=("Courier", 10), state=tk.DISABLED, bg="#f0f0f0")
        self.dec_result_text.grid(row=4, column=0, columnspan=3, pady=5, sticky='nsew')
        self.tab_decode.rowconfigure(4, weight=1)
```

- [ ] **Step 3: Agregar métodos browse_enc_key y browse_dec_key**

Agregar después de `browse_dec_file`:

```python
    def browse_enc_key(self):
        filename = filedialog.askopenfilename(title="Seleccionar archivo de clave", filetypes=[("Archivos de clave", "*.key"), ("Todos", "*.*")])
        if filename:
            self.enc_key_var.set(filename)

    def browse_dec_key(self):
        filename = filedialog.askopenfilename(title="Seleccionar archivo de clave", filetypes=[("Archivos de clave", "*.key"), ("Todos", "*.*")])
        if filename:
            self.dec_key_var.set(filename)
```

- [ ] **Step 4: Actualizar generate_doc para usar encode_document**

Reemplazar el método `generate_doc` completo:

```python
    def generate_doc(self):
        docx_path = self.enc_file_var.get()
        name = self.enc_name_var.get().strip()
        output_path = self.enc_out_var.get()
        key_path = self.enc_key_var.get().strip() or df.DEFAULT_KEY_FILE

        if not docx_path or not os.path.exists(docx_path):
            messagebox.showerror("Error", "Seleccione un documento válido (.docx).")
            return
        if not name:
            messagebox.showerror("Error", "Ingrese el nombre del destinatario.")
            return
        if not output_path:
            output_path = os.path.join(
                os.path.dirname(docx_path),
                f"{Path(docx_path).stem}__{name.replace(' ', '_')}.docx"
            )

        try:
            key = df.load_or_create_key(key_path)
            entry = df.encode_document(docx_path, name, output_path, key)
            df.register_fingerprint_v2(entry)
            messagebox.showinfo(
                "¡Éxito!",
                f"Documento generado para: '{name}'\n\n"
                f"Guardado como:\n{output_path}\n\n"
                f"Capas: {', '.join(entry['layers_injected'])}\n"
                f"HMAC: {entry['payload_hmac']}\n\n"
                "Registro guardado localmente."
            )
            self.enc_file_var.set("")
            self.enc_name_var.set("")
            self.enc_out_var.set("")
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Error crítico", f"Fallo al marcar el documento:\n{str(e)}")
```

- [ ] **Step 5: Actualizar analyze_doc para usar decode_document y mostrar integridad**

Reemplazar el método `analyze_doc` completo:

```python
    def analyze_doc(self):
        docx_path = self.dec_file_var.get()
        key_path = self.dec_key_var.get().strip() or df.DEFAULT_KEY_FILE

        if not docx_path or not os.path.exists(docx_path):
            messagebox.showerror("Error", "Seleccione un documento a analizar.")
            return

        self.log_result(f"🔍 Analizando:\n{os.path.basename(docx_path)}...\n\n")

        try:
            if os.path.exists(key_path):
                key = df.load_or_create_key(key_path)
            else:
                key = b"\x00" * 32  # fallback legacy

            result = df.decode_document(docx_path, key)

            if result:
                integrity = ""
                if result["doc_intact"] is True:
                    integrity = "✅ Contenido íntegro"
                elif result["doc_intact"] is False:
                    integrity = "⚠️  CONTENIDO MODIFICADO desde el envío"
                else:
                    integrity = "(documento v1 — verificación no disponible)"

                msg = "🎯 ¡HUELLA INVISIBLE ENCONTRADA!\n"
                msg += "=" * 40 + "\n"
                msg += f"👉 Destinatario   : {result['recipient']}\n"
                if result["timestamp"]:
                    msg += f"📅 Fecha de envío : {result['timestamp'][:19].replace('T', ' ')}\n"
                msg += f"🔒 Capa detectada : {result['layer_used']}\n"
                msg += f"📄 Integridad     : {integrity}\n"
                msg += "=" * 40 + "\n\n"

                registry = df.load_registry()
                matches = [e for e in registry["fingerprints"] if e["recipient"].lower() == result["recipient"].lower()]
                if matches:
                    msg += f"📋 Registros locales ({len(matches)}):\n"
                    for i, m in enumerate(matches, 1):
                        msg += f"  #{i}: {os.path.basename(m['output_file'])}  [{m['timestamp'][:19].replace('T', ' ')}]\n"
                else:
                    msg += f"⚠️  Sin registro local para '{result['recipient']}'.\n"

                self.log_result(msg)
                messagebox.showwarning("¡Alerta de Huella!", f"Marca detectada:\n'{result['recipient']}'")
            else:
                self.log_result("❓ No se encontró ninguna huella.\n\nEl documento puede ser un original limpio.")
                messagebox.showinfo("Resultado", "No se encontró marca de agua.")

        except Exception as e:
            traceback.print_exc()
            self.log_result(f"❌ ERROR:\n{str(e)}")
            messagebox.showerror("Error", f"Error al analizar:\n{str(e)}")
```

- [ ] **Step 6: Verificar que la GUI inicia sin errores**

```bash
python docx_fingerprint_gui.py
```

Expected: ventana abre con campos de clave visibles en ambas tabs. Cerrar la ventana.

- [ ] **Step 7: Ejecutar suite completa de tests**

```bash
pytest tests/ -v
```

Expected: todos los tests pasan.

- [ ] **Step 8: Commit final**

```bash
git add docx_fingerprint_gui.py
git commit -m "feat: GUI v2 con campo de clave e indicador de integridad del documento"
```

---

## Verificación Final

- [ ] Probar encode end-to-end: `python docx_fingerprint.py encode <tu_doc.docx> "Test Persona" --key fingerprint.key`
- [ ] Probar decode: `python docx_fingerprint.py decode <doc_generado.docx> --key fingerprint.key`
- [ ] Verificar que el resultado muestra recipient, timestamp e integridad
- [ ] Verificar que `fingerprint_registry.json` tiene entrada v2 con todos los campos
- [ ] Ejecutar `pytest tests/ -v` — todos los tests pasan

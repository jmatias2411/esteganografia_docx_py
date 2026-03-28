"""
docx_fingerprint.py — Esteganografía tipográfica para documentos Word
======================================================================
Incrusta una huella invisible en un .docx usando caracteres Unicode de
ancho cero. Cada destinatario recibe una copia visualmente idéntica pero
con una firma única que permite identificar filtraciones.

USO:
  # Codificar — generar copia con huella para "Pepe"
  python docx_fingerprint.py encode documento.docx "Pepe"

  # Codificar con output personalizado
  python docx_fingerprint.py encode documento.docx "María" --output maria_confidencial.docx

  # Decodificar — identificar a quién pertenece un doc filtrado
  python docx_fingerprint.py decode documento_filtrado.docx

  # Ver registro de todas las huellas generadas
  python docx_fingerprint.py list

CÓMO FUNCIONA:
  - Usa caracteres Unicode invisibles (U+200B, U+200C, U+200D) como bits 0, 1, 2
  - Codifica el nombre del destinatario en binario dentro del texto del doc
  - Los caracteres son completamente invisibles en Word, PDF, impresión
  - Sobrevive a copiar/pegar el texto (los caracteres van entre palabras)
  - Guarda un registro local en fingerprint_registry.json
"""

import argparse
import base64
import hashlib
import hmac as hmac_mod
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False


# ─── Caracteres invisibles usados como "bits" ───────────────────────────────
# Visualmente idénticos, pero distintos a nivel de bytes
ZWSP  = "\u200B"  # Zero Width Space       → bit 0
ZWNJ  = "\u200C"  # Zero Width Non-Joiner  → bit 1
ZWJ   = "\u200D"  # Zero Width Joiner      → bit 2 (usado como separador de byte)

REGISTRY_FILE = "fingerprint_registry.json"

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
    xml_path = os.path.join(extract_dir, _CUSTOM_XML_FILE)
    if not os.path.exists(xml_path):
        return None
    with open(xml_path, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r'<!\[CDATA\[([^\]]+)\]\]>', content)
    if not match:
        return None
    try:
        return base64.b64decode(match.group(1))
    except Exception:
        return None


# ─── Hash de integridad del documento ────────────────────────────────────────

def hash_document_xml(extract_dir: str) -> str:
    """SHA-256 hex de word/document.xml (antes de inyectar huellas)."""
    doc_path = os.path.join(extract_dir, "word", "document.xml")
    with open(doc_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


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


# ─── Codificación / Decodificación de payload ───────────────────────────────

def text_to_binary(text: str) -> str:
    """Convierte texto a cadena de bits (8 bits por carácter UTF-8)."""
    bits = []
    for byte in text.encode("utf-8"):
        bits.append(f"{byte:08b}")
    return "".join(bits)


def binary_to_text(bits: str) -> str:
    """Convierte cadena de bits de vuelta a texto (UTF-8)."""
    byte_vals = []
    for i in range(0, len(bits), 8):
        byte_str = bits[i:i+8]
        if len(byte_str) < 8:
            break
        byte_vals.append(int(byte_str, 2))
    return bytes(byte_vals).decode("utf-8")


def encode_payload(name: str) -> str:
    """
    Convierte el nombre en una secuencia de caracteres invisibles.
    Formato: [ZWJ como inicio] + bits como ZWSP/ZWNJ + [ZWJ como fin]
    """
    bits = text_to_binary(name)
    invisible = ZWJ  # marcador de inicio
    for bit in bits:
        invisible += ZWSP if bit == "0" else ZWNJ
    invisible += ZWJ  # marcador de fin
    return invisible


def decode_payload(text: str) -> str | None:
    """
    Extrae el nombre codificado de un texto con caracteres invisibles.
    Retorna None si no encuentra huella.
    """
    # Buscar todos los marcadores posibles (por si alguno está corrupto por edición)
    pattern = ZWJ + "([" + ZWSP + ZWNJ + "]+)" + ZWJ
    matches = re.finditer(pattern, text)
    
    for match in matches:
        invisible_bits = match.group(1)
        bits = ""
        for char in invisible_bits:
            if char == ZWSP:
                bits += "0"
            elif char == ZWNJ:
                bits += "1"

        try:
            byte_vals = []
            for i in range(0, len(bits), 8):
                chunk = bits[i:i+8]
                if len(chunk) == 8:
                    byte_vals.append(int(chunk, 2))
            
            # Si se logra decodificar y tiene texto, ¡lo encontramos!
            decoded_name = bytes(byte_vals).decode("utf-8")
            if decoded_name.strip():
                return decoded_name
        except Exception:
            # Si esta copia de la huella está rota (ej. cortaron el texto a la mitad),
            # ignoramos el error y probamos con la siguiente copia que haya encontrado.
            continue
            
    return None


# ─── Manejo del archivo DOCX (ZIP con XMLs) ─────────────────────────────────

def extract_docx(docx_path: str, extract_dir: str):
    """Extrae el contenido del .docx en un directorio temporal."""
    with zipfile.ZipFile(docx_path, "r") as z:
        z.extractall(extract_dir)


def pack_docx(extract_dir: str, output_path: str):
    """Reempaca el directorio en un nuevo .docx."""
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(extract_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, extract_dir)
                z.write(file_path, arcname)


def get_xml_text_content(xml_content: str) -> str:
    """Extrae todo el texto visible de un XML de Word."""
    return re.sub(r"<[^>]+>", "", xml_content)


def inject_fingerprint_into_xml(xml_content: str, payload: str) -> str:
    """
    Inyecta el payload invisible dentro de los elementos <w:t> del XML.
    Estrategia: Inyectar la huella en MÚLTIPLES lugares (redundancia)
    para que resista si borran o editan partes del documento.
    """
    # Encontrar todos los <w:t>texto</w:t> con texto no vacío
    pattern = r'(<w:t(?:\s[^>]*)?>)([^<]{3,})(<\/w:t>)'

    matches = list(re.finditer(pattern, xml_content))
    if not matches:
        return xml_content

    new_content = xml_content
    
    # Tomar hasta 10 secciones de texto diferentes a lo largo del archivo
    # Usamos reversed() para reemplazar de abajo hacia arriba.
    # Así no alteramos las posiciones (índices) en el string de los elementos anteriores.
    for match in reversed(matches[:10]):
        opening = match.group(1)
        text = match.group(2)
        closing = match.group(3)
        
        # Insertar payload después de la primera palabra del fragmento
        words = text.split(" ", 1)
        if len(words) == 2:
            new_text = words[0] + payload + " " + words[1]
        else:
            new_text = text + payload
            
        replacement = opening + new_text + closing
        
        # Reemplazar exactamente el pedazo en su posición original
        new_content = new_content[:match.start()] + replacement + new_content[match.end():]

    return new_content


def extract_all_text_from_docx(extract_dir: str) -> str:
    """Lee todo el texto del document.xml incluyendo caracteres invisibles."""
    doc_xml_path = os.path.join(extract_dir, "word", "document.xml")
    if not os.path.exists(doc_xml_path):
        return ""
    with open(doc_xml_path, "rb") as f:
        raw = f.read()
    return raw.decode("utf-8")


# ─── Registro de huellas ─────────────────────────────────────────────────────

def load_registry() -> dict:
    if os.path.exists(REGISTRY_FILE):
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"fingerprints": []}


def save_registry(registry: dict):
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)


def register_fingerprint(name: str, output_file: str, source_file: str):
    registry = load_registry()
    entry = {
        "recipient": name,
        "output_file": output_file,
        "source_file": source_file,
        "timestamp": datetime.now().isoformat(),
        "payload_hash": hashlib.sha256(name.encode()).hexdigest()[:12],
    }
    registry["fingerprints"].append(entry)
    save_registry(registry)
    return entry


def register_fingerprint_v2(entry: dict):
    """Guarda una entrada v2 en el registro. entry es el dict retornado por encode_document."""
    registry = load_registry()
    if "version" not in registry:
        registry["version"] = 2
    registry["fingerprints"].append(entry)
    save_registry(registry)


# ─── Comandos principales ────────────────────────────────────────────────────

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


def cmd_list(args):
    registry = load_registry()
    entries = registry.get("fingerprints", [])

    if not entries:
        print("📭 No hay huellas registradas aún.")
        print(f"   Usa 'encode' para generar tu primera copia marcada.")
        return

    print(f"📋 Registro de huellas generadas ({len(entries)} total):\n")
    print(f"  {'#':<4} {'Destinatario':<20} {'Archivo':<35} {'Fecha':<20} {'Hash'}")
    print(f"  {'-'*4} {'-'*20} {'-'*35} {'-'*20} {'-'*12}")
    for i, e in enumerate(entries, 1):
        fecha = e["timestamp"][:19].replace("T", " ")
        archivo = Path(e["output_file"]).name
        if len(archivo) > 33:
            archivo = archivo[:30] + "..."
        print(f"  {i:<4} {e['recipient']:<20} {archivo:<35} {fecha:<20} {e['payload_hash']}")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="🔏 Esteganografía tipográfica para documentos Word confidenciales",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python docx_fingerprint.py encode ley_sinasep.docx "Pepe García"
  python docx_fingerprint.py encode ley_sinasep.docx "María López" --output maria.docx
  python docx_fingerprint.py decode doc_filtrado.docx
  python docx_fingerprint.py list
        """,
    )
    sub = parser.add_subparsers(dest="command")

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

    # list
    sub.add_parser("list", help="Ver registro de todas las huellas generadas")

    args = parser.parse_args()

    if args.command == "encode":
        cmd_encode(args)
    elif args.command == "decode":
        cmd_decode(args)
    elif args.command == "list":
        cmd_list(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

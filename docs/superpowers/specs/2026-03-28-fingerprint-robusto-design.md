# Diseño: Sistema de Fingerprinting Esteganográfico Robusto

**Fecha:** 2026-03-28
**Proyecto:** docx_fingerprint
**Estado:** Aprobado

---

## Objetivo

Hacer el sistema de esteganografía tipográfica para `.docx` resistente a:
1. Pérdida accidental de la huella (edición, reformateo)
2. Eliminación deliberada por alguien que sabe que el doc tiene marca
3. Lectura o falsificación del payload por el destinatario

El sistema solo opera con archivos `.docx`. No se requiere supervivencia a conversión de formato.

---

## Arquitectura General

```
[Clave secreta fingerprint.key]
         │
         ▼
[Payload: nombre + timestamp + hash_doc]
         │
         ├─ AES-256-GCM cifrado
         ├─ HMAC-SHA256 firmado
         └─ base64 encoded
              │
              ├─► Capa 1: Chars invisibles en múltiples XML del docx
              └─► Capa 2: Custom XML Part silenciosa en el ZIP
```

**Archivos modificados/creados:**
- `docx_fingerprint.py` — lógica core (refactorizada con crypto y capas)
- `docx_fingerprint_gui.py` — GUI (campo de clave, resultado de integridad)
- `fingerprint.key` — generado automáticamente en primer uso (NO commitear)
- `fingerprint_registry.json` — entradas enriquecidas

**Dependencia nueva:** `cryptography` (`pip install cryptography`)

---

## Sección 1: Payload y Criptografía

### Estructura del payload (antes de cifrar)

```json
{
  "recipient": "Pepe García",
  "timestamp": "2026-03-28T10:30:00.000000",
  "doc_hash": "<sha256 de document.xml original>"
}
```

### Pipeline de cifrado

1. Serializar payload a JSON (UTF-8)
2. Cifrar con **AES-256-GCM** usando la clave del archivo `fingerprint.key`
   - IV/nonce de 12 bytes aleatorios por cada encoding
   - GCM provee autenticación integrada (AEAD)
3. Firmar `nonce + ciphertext + tag` con **HMAC-SHA256**
4. Serializar como base64: `nonce(12B) + hmac(32B) + ciphertext`
5. Convertir cada byte del base64 a chars invisibles Unicode

### Chars invisibles usados

| Char | Unicode | Valor |
|------|---------|-------|
| ZWSP | U+200B | bits `00` |
| ZWNJ | U+200C | bits `01` |
| ZWJ  | U+200D | bits `10` |
| WJ   | U+2060 | bits `11` |

4 símbolos = 2 bits por char → payload más compacto que el sistema anterior (1 bit/char).

Marcadores: `U+FEFF` (BOM) como inicio/fin del payload en cada punto de inyección.

### Decodificación

1. Extraer secuencia entre marcadores U+FEFF
2. Verificar HMAC — si falla: la huella fue alterada o la clave es incorrecta
3. Descifrar AES-GCM
4. Parsear JSON → obtener recipient, timestamp, doc_hash
5. Comparar doc_hash con SHA-256 actual del document.xml → indicar si fue modificado

---

## Sección 2: Capas de Inyección

### Capa 1 — Inyección en texto (múltiples XML)

**Archivos objetivo** (los que existan en el docx):
- `word/document.xml`
- `word/header1.xml`, `word/header2.xml`, `word/header3.xml`
- `word/footer1.xml`, `word/footer2.xml`, `word/footer3.xml`
- `word/footnotes.xml`
- `word/endnotes.xml`

**Estrategia por archivo:**
- Encontrar todos los `<w:t>` con texto ≥ 3 chars
- Seleccionar hasta 5 posiciones distribuidas uniformemente a lo largo del archivo
- Posición de inyección dentro del texto: aleatoria (no siempre después de la primera palabra)
- Usar `reversed()` para reemplazar de abajo a arriba (no altera índices)

**Resistencia:**
- Sobrevive edición parcial del documento
- Requiere eliminar manualmente chars invisibles de TODOS los segmentos afectados

### Capa 2 — Custom XML Part (silenciosa)

**Ruta dentro del ZIP:** `word/customXml/fingerprint.xml`

**Contenido:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<fingerprint xmlns="urn:fingerprint:v2">
  <data><![CDATA[BASE64_DEL_PAYLOAD_CIFRADO]]></data>
</fingerprint>
```

Word ignora completamente este archivo. No aparece en propiedades, paneles ni vistas.

**Para activarla**, se requiere además registrar la relación en `word/_rels/document.xml.rels` con tipo `http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml`. Esto asegura que el archivo permanezca intacto al guardar con Word.

**Resistencia:**
- Sobrevive cualquier edición del texto del documento
- Solo se elimina desarmando el ZIP y borrando el archivo manualmente

### Orden de decodificación

1. Intentar **Capa 2** primero (más confiable)
2. Si no está o HMAC inválido → intentar **Capa 1** (buscar en todos los XML)
3. Si ninguna → intentar decodificación legacy (compatibilidad con docs marcados con versión anterior)
4. Reportar qué capa fue usada para recuperar la huella

---

## Sección 3: Gestión de la Clave

### Archivo `fingerprint.key`

- 32 bytes aleatorios seguros (`os.urandom(32)`)
- Generado automáticamente en el primer uso si no existe
- Guardado en el directorio de trabajo (configurable vía `--key` flag)
- **No debe commitearse ni compartirse**

### Comportamiento ante clave ausente

- **Encode sin clave**: genera la clave automáticamente, avisa al usuario
- **Decode sin clave**: error claro — "No se puede leer la huella sin el archivo de clave"
- La clave no se embebe en ningún lugar del documento

### En la GUI

- Campo "Archivo de clave (.key):" en tabs Encode y Decode
- Botón "Explorar..." para seleccionar archivo
- Default: `fingerprint.key` en directorio del script
- Mensaje de advertencia visible si el archivo de clave no existe al abrir la GUI

---

## Sección 4: Registro y CLI/GUI

### Registro `fingerprint_registry.json`

```json
{
  "version": 2,
  "fingerprints": [
    {
      "recipient": "Pepe García",
      "output_file": "doc__Pepe_García.docx",
      "source_file": "documento_original.docx",
      "timestamp": "2026-03-28T10:30:00.000000",
      "doc_hash": "sha256 primeros 16 chars del document.xml original",
      "payload_hmac": "primeros 16 chars del HMAC",
      "layers_injected": ["text", "custom_xml"],
      "version": 2
    }
  ]
}
```

Entradas legacy (v1) se mantienen sin modificar para compatibilidad.

### CLI

```bash
# Encode
python docx_fingerprint.py encode doc.docx "Pepe García"
python docx_fingerprint.py encode doc.docx "Pepe García" --key /ruta/fingerprint.key
python docx_fingerprint.py encode doc.docx "Pepe García" --output pepe.docx

# Decode
python docx_fingerprint.py decode doc_filtrado.docx
python docx_fingerprint.py decode doc_filtrado.docx --key /ruta/fingerprint.key

# List (sin cambios)
python docx_fingerprint.py list
```

**Salida del decode enriquecida:**
```
🎯 ¡HUELLA ENCONTRADA! (via custom_xml)
   Destinatario : Pepe García
   Fecha envío  : 2026-03-28 10:30:00
   Integridad   : ✅ Contenido íntegro  |  ⚠️ Contenido modificado desde el envío
```

### GUI — cambios mínimos

- Agregar campo "Archivo de clave" + botón Explorar en ambas tabs
- En tab Decode: el área de resultados muestra integridad del doc además del destinatario
- Resto de la interfaz sin cambios

---

## Compatibilidad Legacy

El decode intenta en orden:
1. Capa 2 (custom XML, v2)
2. Capa 1 (chars invisibles, v2 con HMAC)
3. Legacy (chars invisibles, v1 sin cifrado)

Los documentos marcados con la versión anterior siguen siendo decodificables.

---

## Fuera de Alcance

- Supervivencia a conversión de formato (PDF, etc.)
- Registro centralizado / multi-usuario
- Gestión de múltiples claves
- Protección contra re-escritura manual completa del documento

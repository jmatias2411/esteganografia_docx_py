# DocxFingerprint — Sistema de Trazabilidad Documental

> Incrusta una huella invisible e infalsificable en documentos Word (.docx) para identificar el origen de filtraciones.

---

## ¿Para qué sirve?

Imagina que tienes un documento confidencial —un contrato, un informe interno, un borrador de ley— y debes enviárselo a varias personas. Si ese documento aparece filtrado públicamente, ¿cómo sabes quién lo filtró?

**DocxFingerprint resuelve ese problema.**

Genera una copia personalizada del documento para cada destinatario. A simple vista, todas las copias son **idénticas**: mismo texto, mismas imágenes, mismo formato. Sin embargo, cada una lleva una **huella microscópica e invisible** vinculada al nombre del receptor. Si el documento es filtrado, basta con analizarlo para saber exactamente a quién se le entregó esa copia.

### ¿Qué NO modifica?
- El texto visible del documento.
- El formato, fuentes o imágenes.
- La experiencia al leerlo en Word, PDF o al imprimirlo.

---

## Descarga y uso rápido (sin instalar nada)

1. Descarga `FingerprintDocx.exe` desde la sección [Releases](../../releases).
2. Ejecuta el archivo. No requiere instalar Python ni ninguna dependencia.
3. Usa la pestaña **"Generar Documento Marcado"** para crear copias selladas.
4. Usa la pestaña **"Auditar Documento"** para identificar al responsable de una filtración.

> **Importante:** La primera vez que generas un documento, se crea automáticamente un archivo `fingerprint.key` en la misma carpeta. **Guarda esta clave en un lugar seguro** — la necesitarás para auditar documentos filtrados. Sin ella, no podrás leer las huellas.

---

## Interfaz gráfica

### Pestaña: Generar Documento Marcado

| Campo | Descripción |
|---|---|
| Documento Original | El `.docx` que deseas proteger |
| Destinatario | Nombre de la persona a quien se lo enviarás |
| Guardar en | Ruta del archivo de salida (se genera automáticamente si se deja vacío) |
| Archivo de clave | La clave secreta `.key` (se crea automáticamente en el primer uso) |

### Pestaña: Auditar Documento

Carga cualquier `.docx` sospechoso y la herramienta extrae la huella, mostrando:

- **Destinatario** — a quién se le entregó esa copia.
- **Fecha de envío** — cuándo se generó el documento.
- **Integridad** — si el contenido fue modificado desde que se selló.
- **Registros locales** — historial de todos los documentos generados.

---

## Uso desde línea de comandos (CLI)

```bash
# Generar copia sellada para "María López"
python docx_fingerprint.py encode informe.docx "María López"

# Con ruta de salida personalizada
python docx_fingerprint.py encode informe.docx "Juan Pérez" --output juan_copia.docx

# Auditar un documento filtrado
python docx_fingerprint.py decode doc_filtrado.docx

# Ver todos los documentos generados
python docx_fingerprint.py list
```

---

## Cómo funciona (detalles técnicos)

### Codificación del payload

El nombre del destinatario, junto con la fecha y un hash del documento, se cifra usando **AES-256-GCM** y se firma con **HMAC-SHA256**. Este payload cifrado se convierte en una secuencia de caracteres Unicode de ancho cero (Zero Width Characters):

| Carácter Unicode | Nombre | Valor |
|---|---|---|
| `U+200B` | Zero Width Space | bits `00` |
| `U+200C` | Zero Width Non-Joiner | bits `01` |
| `U+200D` | Zero Width Joiner | bits `10` |
| `U+2060` | Word Joiner | bits `11` |

Cada byte del payload cifrado se codifica con 4 de estos caracteres (2 bits cada uno). Son completamente invisibles en cualquier visor de texto, Word, PDF o impresora.

### Doble capa de inyección

La huella se inyecta en **dos capas independientes** dentro del archivo `.docx` (que internamente es un ZIP con XMLs):

**Capa 1 — Texto invisible:**
Los caracteres de ancho cero se insertan entre palabras del XML principal (`word/document.xml`) y XMLs auxiliares (encabezados, pies de página, notas). Se distribuyen en hasta 5 posiciones por archivo para garantizar redundancia frente a ediciones parciales.

**Capa 2 — XML personalizado silencioso:**
Se crea un archivo `word/customXml/fingerprint.xml` dentro del `.docx` con el payload cifrado en Base64. Este archivo es completamente invisible para el usuario de Word pero persiste incluso si el texto del documento es reemplazado.

### Decodificación con prioridad

Al auditar un documento, el sistema prueba en este orden:
1. Capa 2 (custom XML) — más robusta frente a edición de texto.
2. Capa 1 (caracteres invisibles) — funciona si el custom XML fue eliminado.
3. Fallback legacy (v1) — compatibilidad con documentos generados con versiones anteriores.

### Verificación de integridad

Al generar el documento, se calcula el **SHA-256 de `word/document.xml`** y se incluye dentro del payload cifrado. Al auditar, se recalcula el hash y se compara: si no coincide, se reporta que el contenido fue modificado desde el envío.

### Criptografía

- **Cifrado:** AES-256-GCM (autenticado, con nonce aleatorio de 12 bytes).
- **Firma:** HMAC-SHA256 sobre `nonce + ciphertext`.
- **Formato del blob:** `nonce (12B) | hmac (32B) | ciphertext (variable)`.
- **Clave:** 256 bits generados con `os.urandom(32)`, almacenados en `fingerprint.key`.

---

## Instalación para desarrollo

```bash
git clone https://github.com/jmatias2411/esteganografia_docx_py.git
cd esteganografia_docx_py
pip install -r requirements.txt
```

### Compilar el ejecutable

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "FingerprintDocx" --add-data "docx_fingerprint.py;." docx_fingerprint_gui.py
# El .exe quedará en dist/FingerprintDocx.exe
```

### Ejecutar tests

```bash
pytest
```

---

## Estructura del proyecto

```
docx-fingerprint/
├── docx_fingerprint.py       # Motor principal (CLI + lógica core)
├── docx_fingerprint_gui.py   # Interfaz gráfica (Tkinter)
├── requirements.txt          # Dependencias (cryptography)
├── fingerprint.key           # Clave secreta (se genera en el primer uso, NO subir a git)
├── fingerprint_registry.json # Historial de documentos generados (NO subir a git)
└── tests/
    └── test_fingerprint.py   # Suite de tests
```

> **Nota de seguridad:** No subas `fingerprint.key` ni `fingerprint_registry.json` a repositorios públicos. Añádelos a `.gitignore`.

---

## Limitaciones conocidas

- **Conversión a PDF o reescritura completa del XML:** Si el documento es convertido a otro formato y luego vuelto a `.docx` mediante herramientas que regeneran el XML desde cero, la Capa 1 puede perderse. La Capa 2 también se elimina en este caso. Sin embargo, la impresión, el guardado normal en Word y el copiar/pegar del texto preservan los caracteres invisibles.
- **No es una solución DRM:** No impide que el documento sea compartido; solo permite identificar al responsable después del hecho.

---

## Licencia

MIT License — ver archivo `LICENSE` para más detalles.

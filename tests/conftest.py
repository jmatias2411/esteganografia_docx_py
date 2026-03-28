# tests/conftest.py
import io
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

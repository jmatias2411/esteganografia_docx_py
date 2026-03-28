# tests/test_fingerprint.py
import docx_fingerprint as df
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


import pytest


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


import io
import zipfile


class TestLayer1:
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

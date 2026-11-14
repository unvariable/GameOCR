import tempfile
from pathlib import Path

from gameocr.cache_store import CacheStore


def test_cache_store_put_and_lookup():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.sqlite"
        store = CacheStore(db_path, max_entries=10)
        store.set_lang_pair("EN", "TR")

        # Başlangıçta boş
        assert store.lookup("hello world", threshold=90) is None

        # Ekle
        store.put("EN", "TR", "hello world", "Hello, World!", "Merhaba Dünya!")

        # Birebir arama
        hit = store.lookup("hello world", threshold=90)
        assert hit == "Merhaba Dünya!"

        # Bulanık arama (8 karakterden uzun, ufak bir harf farkı)
        fuzzy_hit = store.lookup("hello worlt", threshold=85)
        assert fuzzy_hit == "Merhaba Dünya!"

        store.close()


def test_cache_store_lru_eviction():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_lru.sqlite"
        store = CacheStore(db_path, max_entries=3)
        store.set_lang_pair("EN", "TR")

        # 3 kayıt ekle
        store.put("EN", "TR", "one sentence", "one sentence", "bir")
        store.put("EN", "TR", "two sentence", "two sentence", "iki")
        store.put("EN", "TR", "three sentence", "three sentence", "üç")

        count, _ = store.stats()
        assert count == 3

        # 4. kaydı ekle -> en eski silinmeli ("one sentence")
        store.put("EN", "TR", "four sentence", "four sentence", "dört")

        count, _ = store.stats()
        assert count == 3
        assert store.lookup("one sentence", threshold=95) is None
        assert store.lookup("four sentence", threshold=95) == "dört"

        store.close()


def test_cache_store_clear():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_clear.sqlite"
        store = CacheStore(db_path, max_entries=10)
        store.set_lang_pair("EN", "TR")

        store.put("EN", "TR", "test entry", "test entry", "deneme")
        count, _ = store.stats()
        assert count == 1

        store.clear()
        count, _ = store.stats()
        assert count == 0
        assert store.lookup("test entry", threshold=90) is None

        store.close()

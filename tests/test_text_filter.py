import tempfile
import time
from pathlib import Path

from gameocr.cache_store import CacheStore
from gameocr.config import FilterConfig
from gameocr.text_filter import Action, TextFilter, normalize


def test_normalize():
    assert normalize("Hello, World!") == "hello world"
    assert normalize("| am here...") == "i am here"
    assert normalize("   Line   with   spaces   ") == "line with spaces"


def test_typewriter_debounce():
    cfg = FilterConfig(similarity_threshold=90, min_chars=3, clear_after_empty_frames=3, settle_time=0.2)
    filter_ = TextFilter(cfg)

    # 1. harf/kelime: "I have" -> yazılıyor -> IGNORE
    assert filter_.process("I have").action == Action.IGNORE

    # 2. kelime ekleniyor: "I have some time" -> uzuyor -> IGNORE
    assert filter_.process("I have some time").action == Action.IGNORE

    # 3. cümle tamamlanıyor: "...take a rest" -> uzuyor -> IGNORE
    full_sentence = "I have some time, so maybe I should take a rest"
    assert filter_.process(full_sentence).action == Action.IGNORE

    # Hemen ardından aynı kare gelirse henüz settle_time (0.2s) dolmadığı için IGNORE
    assert filter_.process(full_sentence).action == Action.IGNORE

    # 0.25 saniye sonra yazı duruldu ve aynı kaldı -> TRANSLATE tetiklenmeli!
    time.sleep(0.25)
    dec = filter_.process(full_sentence)
    assert dec.action == Action.TRANSLATE
    assert dec.text == full_sentence

    # Cümle ekranda kalmaya devam ettikçe artık tekrar çevrilmemeli -> IGNORE
    assert filter_.process(full_sentence).action == Action.IGNORE


def test_echo_protection():
    cfg = FilterConfig(similarity_threshold=85, min_chars=3, settle_time=0.1)
    filter_ = TextFilter(cfg)

    # Ekrana Türkçe çeviri yansıtıldı diyelim
    filter_.set_shown("Selam yolcu!")

    # OCR ekrandaki kendi çevirimizi okursa yankı koruması IGNORE etmeli
    dec = filter_.process("Selam yolcu")
    assert dec.action == Action.IGNORE


def test_empty_and_clear():
    cfg = FilterConfig(similarity_threshold=90, min_chars=3, clear_after_empty_frames=3, settle_time=0.1)
    filter_ = TextFilter(cfg)

    filter_.process("Active subtitle text")
    time.sleep(0.12)
    filter_.process("Active subtitle text")
    filter_.set_shown("Aktif altyazı metni")

    # 1. boş kare
    assert filter_.process("").action == Action.IGNORE
    # 2. boş kare
    assert filter_.process(" ").action == Action.IGNORE
    # 3. boş kare -> CLEAR sinyali verilmeli
    d3 = filter_.process("")
    assert d3.action == Action.CLEAR

    # 4. boş karede artık söndürüldüğü için tekrar CLEAR verilmez
    assert filter_.process("").action == Action.IGNORE


def test_with_cache():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "filter_cache.sqlite"
        store = CacheStore(db_path, max_entries=10)
        store.set_lang_pair("EN", "TR")
        store.put("EN", "TR", "follow me now", "Follow me now", "Beni hemen takip et")

        cfg = FilterConfig(similarity_threshold=90, min_chars=3, settle_time=0.1)
        filter_ = TextFilter(cfg, cache=store)

        filter_.process("Follow me now")
        time.sleep(0.12)
        dec = filter_.process("Follow me now")
        assert dec.action == Action.SHOW_CACHED
        assert dec.text == "Beni hemen takip et"

        store.close()


def test_typewriter_with_ui_suffix_and_check_pending():
    cfg = FilterConfig(similarity_threshold=90, min_chars=3, settle_time=0.2)
    filter_ = TextFilter(cfg)

    # 1. İlk kelime + UI butonu ("AUTO 411")
    assert filter_.process("All AUTO 411").action == Action.IGNORE

    # 2. Kelimeler akarken daktilo genişlemesi
    assert filter_.process("All this, just to block of AUTO 411").action == Action.IGNORE
    assert filter_.process("All this, just to block off the window? It seems like overkill... AUTO").action == Action.IGNORE

    # 3. Ekran değişmeyi bıraktı (ChangeGate kare göndermiyor).
    # Henüz 0.2s dolmadıysa check_pending IGNORE döner:
    assert filter_.check_pending().action == Action.IGNORE

    # 0.25 saniye sonra yazı durulduğunda check_pending tek bir TRANSLATE tetikler:
    time.sleep(0.25)
    dec = filter_.check_pending()
    assert dec.action == Action.TRANSLATE
    assert "overkill" in dec.text

    # Bir sonraki kontrolde tekrar istek atılmaz
    assert filter_.check_pending().action == Action.IGNORE


def test_check_pending_clears_on_idle_after_empty():
    cfg = FilterConfig(similarity_threshold=90, min_chars=3, clear_after_empty_frames=5, settle_time=0.1)
    filter_ = TextFilter(cfg)

    filter_.process("Some dialogue line")
    time.sleep(0.12)
    filter_.process("Some dialogue line")
    filter_.set_shown("Bir diyalog satırı")

    # Yalnızca 1 boş kare geldi (ChangeGate sonraki kareleri bloklasa bile)
    assert filter_.process("").action == Action.IGNORE

    # 0.8 saniye sonra ekran boş kalmaya devam ettiyse check_pending CLEAR dönmeli
    time.sleep(0.8)
    dec = filter_.check_pending()
    assert dec.action == Action.CLEAR
    # Artık cleared olduğu için tekrar CLEAR dönmemeli
    assert filter_.check_pending().action == Action.IGNORE


def test_is_sentence_complete():
    from gameocr.text_filter import is_sentence_complete

    assert is_sentence_complete("Oh! This might not be related, but-") is True
    assert is_sentence_complete("Wait... What happened?") is True
    assert is_sentence_complete("Yes, I think so.") is True
    assert is_sentence_complete("Look at that!") is True
    assert is_sentence_complete("She said, \"Run!\"") is True

    # Tamamlanmamış cümleler
    assert is_sentence_complete("Oh! Th") is False
    assert is_sentence_complete("Oh! This might not be related,") is False
    assert is_sentence_complete("Wait, because:") is False
    assert is_sentence_complete("") is False


def test_typewriter_active_flag_and_comma_pause():
    cfg = FilterConfig(similarity_threshold=90, min_chars=3, settle_time=0.2)
    filter_ = TextFilter(cfg)

    # 1. İlk parça
    assert filter_.process("Oh! Th").action == Action.IGNORE
    assert filter_._is_typing is False

    # 2. Daktilo uzantısı -> _is_typing aktifleşmeli
    assert filter_.process("Oh! This might not be related,").action == Action.IGNORE
    assert filter_._is_typing is True
    assert filter_._typewriter_updates >= 1

    # Virgülle bittiği için 0.22 saniye sonra check_pending henüz TRANSLATE vermemeli (1.8x gecikme koruması)
    time.sleep(0.22)
    assert filter_.check_pending().action == Action.IGNORE

    # 3. Replik sonu ekleniyor
    full = "Oh! This might not be related, but-"
    assert filter_.process(full).action == Action.IGNORE

    # Ekran duruldu ve terminal tire ile bitti -> settle_time (0.2s) sonra tek bir TRANSLATE tetiklenmeli
    time.sleep(0.25)
    dec = filter_.process(full, is_stable=True)
    assert dec.action == Action.TRANSLATE
    assert "related, but-" in dec.text


def test_translator_worker_drain_superseded():
    import queue
    import threading
    from unittest.mock import MagicMock
    from gameocr.config import Config
    from gameocr.messages import TranslateJob
    from gameocr.workers import TranslatorWorker

    trans_q = queue.Queue()
    worker = TranslatorWorker(
        translator=MagicMock(),
        cfg=Config(),
        cache_store=MagicMock(),
        translate_q=trans_q,
        ui_q=MagicMock(),
        filter_control_q=MagicMock(),
        control_q=MagicMock(),
        stop_event=threading.Event(),
    )

    # Kuyruğa daktilo sırasında arka arkaya gelen ara işler ekleniyor:
    job1 = TranslateJob(source="Oh! Th", norm_key="oh th", src_lang="EN", tgt_lang="TR")
    job2 = TranslateJob(source="Oh! This might not be related,", norm_key="oh this might not be related", src_lang="EN", tgt_lang="TR")
    job3 = TranslateJob(source="Oh! This might not be related, but-", norm_key="oh this might not be related but", src_lang="EN", tgt_lang="TR")

    trans_q.put(job2)
    trans_q.put(job3)

    # _drain_superseded job1'i alıp kuyruktaki en güncel ve kapsamlı job3'e atlamalı:
    freshest = worker._drain_superseded(job1)
    assert freshest == job3
    assert freshest.source == "Oh! This might not be related, but-"
    assert trans_q.empty()


def test_self_capture_echo_and_english_onnx_model_selection():
    """Aşama 17: Overlay çevirisinin ekran yakalamasına sızması (self-capture) durumunda
    geri besleme döngüsü engellenmeli, çözünürlük etiketleri temizlenmeli ve İngilizce
    ONNX tanıma modeli ('en_rec.onnx') otomatik bulunmalıdır.
    """
    from gameocr.ocr_engine import RapidOcrEngine
    from gameocr.text_filter import Action, FilterConfig, TextFilter, clean_game_text

    # 1. Çözünürlük etiketlerinin temizlenmesi
    cleaned = clean_game_text("Whatever is done for love - Friedrich Nietzsche 2240 × 1260")
    assert "2240" not in cleaned
    assert "Friedrich Nietzsche" in cleaned

    # 2. Öz-yakalama (self-capture) geri besleme döngüsü koruması
    tf = TextFilter(FilterConfig(settle_time=0.05))
    tf.set_shown("Bazen insanlar gerçeği duymak istemez çünkü illüzyonlarının yıkılmasını istemezler.")
    mixed_echo = "Sometimes people Bazen insanlar gerçeği duymak istemez çünkü illüzyonlarının yıkılmasını - Friedrich Nietzsche"
    dec = tf.process(mixed_echo, is_stable=True)
    assert dec.action == Action.IGNORE

    # 3. İngilizce ve Latin ONNX tanıma modellerinin bulunması
    en_pair = RapidOcrEngine._find_bundled_onnx_rec_model("en")
    tr_pair = RapidOcrEngine._find_bundled_onnx_rec_model("tr")
    assert en_pair is not None and en_pair[0].name == "en_rec.onnx"
    assert tr_pair is not None and tr_pair[0].name == "latin_rec.onnx"






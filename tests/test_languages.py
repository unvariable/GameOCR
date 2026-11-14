from gameocr.languages import (
    get_source_languages,
    get_source_name,
    get_target_languages,
    get_target_name,
    normalize_target_lang,
    source_to_paddle,
)


def test_source_languages_listing():
    sources = get_source_languages()
    assert len(sources) >= 5
    codes = [s.deepl_code for s in sources]
    assert "EN" in codes
    assert "JA" in codes
    assert "DE" in codes


def test_target_languages_listing():
    targets = get_target_languages()
    assert len(targets) >= 5
    codes = [t.deepl_code for t in targets]
    assert "TR" in codes
    assert "EN" in codes


def test_source_to_paddle_mapping():
    assert source_to_paddle("EN") == "en"
    assert source_to_paddle("TR") == "tr"
    assert source_to_paddle("de") == "german"
    assert source_to_paddle("JA") == "japan"
    assert source_to_paddle("ZH") == "ch"
    assert source_to_paddle("KO") == "korean"
    assert source_to_paddle("UNKNOWN_LANG") == "en"


def test_display_names():
    assert "İngilizce" in get_source_name("EN")
    assert "Türkçe" in get_target_name("TR")


def test_normalize_target_lang():
    assert normalize_target_lang("en") == "EN-US"
    assert normalize_target_lang("pt") == "PT-BR"
    assert normalize_target_lang("TR") == "TR"

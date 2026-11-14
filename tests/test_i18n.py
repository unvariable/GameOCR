from gameocr.i18n import AVAILABLE_LANGUAGES, TRANSLATIONS, get_language, set_language, t


def test_i18n_default_language():
    set_language("tr")
    assert get_language() == "tr"
    assert t("settings.title") == "GameOCR - Ayarlar"
    assert t("btn.save") == "💾 Kaydet"
    assert t("tab.translator") == "Çevirmen"


def test_i18n_english_switch():
    set_language("en")
    assert get_language() == "en"
    assert t("settings.title") == "GameOCR - Settings"
    assert t("btn.save") == "💾 Save"
    assert t("tab.translator") == "Translator"
    # Switch back to tr
    set_language("tr")


def test_i18n_formatting():
    set_language("tr")
    msg = t("settings.blur_level", v=7)
    assert "Seviye 7" in msg

    set_language("en")
    msg_en = t("settings.blur_level", v=7)
    assert "Level 7" in msg_en
    set_language("tr")


def test_i18n_missing_key_fallback():
    assert t("non_existent_key_xyz") == "non_existent_key_xyz"


def test_i18n_extensibility():
    # Adding a new language is trivial:
    TRANSLATIONS["de"] = {
        "btn.save": "Speichern",
        "btn.close": "Schließen",
    }
    AVAILABLE_LANGUAGES["de"] = "Deutsch"

    set_language("de")
    assert t("btn.save") == "Speichern"
    # Falls back to tr if key missing in de:
    assert t("settings.title") == "GameOCR - Ayarlar"

    # Cleanup
    del TRANSLATIONS["de"]
    del AVAILABLE_LANGUAGES["de"]
    set_language("tr")

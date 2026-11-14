"""Desteklenen diller ve OCR/Çeviri eşleştirmeleri.

DeepL dil kodları ile PaddleOCR dil modellerini bağlar ve Ayarlar arayüzü
için görünen adları (UI etiketlerini) sunar.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceLanguage:
    deepl_code: str
    paddle_lang: str
    display_name: str


@dataclass(frozen=True, slots=True)
class TargetLanguage:
    deepl_code: str
    display_name: str


# Kaynak diller (Oyunun altyazı dili): OCR modeli + DeepL çeviri kaynağı
SOURCE_LANGUAGES: list[SourceLanguage] = [
    SourceLanguage("EN", "en", "İngilizce (English)"),
    SourceLanguage("JA", "japan", "Japonca (日本語)"),
    SourceLanguage("ZH", "ch", "Çince (Basitleştirilmiş) (中文)"),
    SourceLanguage("KO", "korean", "Korece (한국어)"),
    SourceLanguage("DE", "german", "Almanca (Deutsch)"),
    SourceLanguage("FR", "french", "Fransızca (Français)"),
    SourceLanguage("ES", "es", "İspanyolca (Español)"),
    SourceLanguage("IT", "it", "İtalyanca (Italiano)"),
    SourceLanguage("RU", "ru", "Rusça (Русский)"),
    SourceLanguage("PT", "pt", "Portekizce (Português)"),
    SourceLanguage("PL", "pl", "Lehçe (Polski)"),
    SourceLanguage("TR", "tr", "Türkçe (Türkçe)"),
    SourceLanguage("AR", "ar", "Arapça (العربية)"),
    SourceLanguage("UK", "uk", "Ukraynaca (Українська)"),
    SourceLanguage("EL", "el", "Yunanca (Ελληνικά)"),
    SourceLanguage("NL", "nl", "Felemenkçe (Nederlands)"),
    SourceLanguage("SV", "sv", "İsveççe (Svenska)"),
]

# Hedef diller (Altyazının çevrileceği dil - DeepL hedefleri)
TARGET_LANGUAGES: list[TargetLanguage] = [
    TargetLanguage("TR", "Türkçe"),
    TargetLanguage("EN", "İngilizce (English)"),
    TargetLanguage("DE", "Almanca (Deutsch)"),
    TargetLanguage("FR", "Fransızca (Français)"),
    TargetLanguage("ES", "İspanyolca (Español)"),
    TargetLanguage("IT", "İtalyanca (Italiano)"),
    TargetLanguage("JA", "Japonca (日本語)"),
    TargetLanguage("ZH", "Çince (Basitleştirilmiş) (中文)"),
    TargetLanguage("KO", "Korece (한국어)"),
    TargetLanguage("RU", "Rusça (Русский)"),
    TargetLanguage("PT-PT", "Portekizce (Avrupa)"),
    TargetLanguage("PT-BR", "Portekizce (Brezilya)"),
    TargetLanguage("PL", "Lehçe (Polski)"),
    TargetLanguage("NL", "Felemenkçe (Nederlands)"),
    TargetLanguage("SV", "İsveççe (Svenska)"),
    TargetLanguage("UK", "Ukraynaca (Українська)"),
    TargetLanguage("AR", "Arapça (العربية)"),
    TargetLanguage("EL", "Yunanca (Ελληνικά)"),
]

_SRC_BY_CODE = {item.deepl_code.upper(): item for item in SOURCE_LANGUAGES}
_TGT_BY_CODE = {item.deepl_code.upper(): item for item in TARGET_LANGUAGES}


def get_source_languages() -> list[SourceLanguage]:
    return list(SOURCE_LANGUAGES)


def get_target_languages() -> list[TargetLanguage]:
    return list(TARGET_LANGUAGES)


def source_to_paddle(deepl_code: str) -> str:
    """DeepL kaynak dil kodunu PaddleOCR dil parametresine çevirir.
    Bilinmeyen diller için varsayılan 'en' döner.
    """
    code = deepl_code.strip().upper()
    info = _SRC_BY_CODE.get(code)
    if info is not None:
        return info.paddle_lang
    return "en"


def get_source_name(deepl_code: str) -> str:
    info = _SRC_BY_CODE.get(deepl_code.strip().upper())
    return info.display_name if info else deepl_code


def get_target_name(deepl_code: str) -> str:
    info = _TGT_BY_CODE.get(deepl_code.strip().upper())
    return info.display_name if info else deepl_code


def normalize_target_lang(tgt: str) -> str:
    """DeepL hedef dil kodunu standartlaştırır (örn. 'EN' -> 'EN-US' veya desteklenen biçim)."""
    t = tgt.strip().upper()
    if t == "EN":
        return "EN-US"
    if t == "PT":
        return "PT-BR"
    return t

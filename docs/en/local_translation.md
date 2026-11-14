# 🧠 Offline (Local) Translation Engine & Memory Management

GameOCR includes an offline neural translation engine (`gameocr/local_models.py`) alongside the DeepL cloud API, enabling zero-latency, quota-free subtitle translation without an internet connection.

---

## 1. Translation Engine Modes (`translator.translation_engine`)

Configured in `config.toml` or via **Settings -> Translation**:
- **`deepl`:** Uses the DeepL Cloud API (`deepl_api_key` required).
- **`local`:** Uses only the offline local translation engine (`LocalModelManager`). Requires no API key or internet connection.
- **`auto_fallback`:** Uses DeepL when available and automatically falls back to the local offline engine if the API key is missing, quota is exceeded, or the network disconnects.

---

## 2. Default Language Pack (`EN-TR`) & Download Manager

- **Pre-installed by Default:** Only the **English -> Turkish (`EN-TR`)** language pack is installed and ready out of the box (`is_default_installed=True`).
- **Additional Language Packs:** Users can download additional packs (`JA-TR`, `EN-DE`, `DE-TR`, `RU-TR`, `FR-TR`, `ES-TR`, `ZH-TR`) from **Settings -> Translation -> Local Language Packs**.
- **Non-Blocking Asynchronous Downloads:** Downloads run inside `ModelDownloadWorker(QThread)` and emit `progress(int)` and `finished_pack(str, bool, str)` Qt signals so the main GUI thread and subtitle overlay never freeze during model installation.

---

## 3. How Local Models Are Managed in Memory

1. **Lazy Initialization:** Models are not loaded into RAM/VRAM when GameOCR starts if `deepl` mode is active. `LocalModelManager.translate()` loads the active language pair (`EN-TR` by default) only on first use.
2. **Single Active Pair in RAM:** When switching language pairs (e.g., from `EN-TR` to `JA-TR`), `LocalModelManager` unloads the previous model or releases unused references via `unload_model()` + `gc.collect()`.
3. **CTranslate2 `int8` Quantization:** When CTranslate2 / Argos Translate models are loaded, `int8` compute quantization and 2 inter/intra threads are used to keep RAM usage under ~150–250 MB and CPU/GPU inference time around `5–18 ms` per subtitle line.
4. **Built-in Offline Game Dialogue Engine:** For `EN-TR` (and installed packs), `LocalModelManager` also includes a zero-dependency phrase, idiom, suffix, and vocabulary translator so offline translation works immediately even before external `.argosmodel` archives are downloaded.

---

## 4. Multi-Language OCR Pack Download Manager (`gameocr/ocr_models.py`)

In addition to translation language packs, GameOCR includes an **OCR Language Pack Manager (`OcrModelManager`)** under **Settings -> Detection & OCR**:
- **Pre-installed OCR Packs:** `EN` (English — `en_rec.onnx`) and `LATIN` (Turkish & European languages: `TR, DE, FR, ES, IT, PT, PL, NL, SV` — `latin_rec.onnx`).
- **Downloadable OCR Packs:** `JA` (Japanese), `KO` (Korean), `ZH` (Chinese), `RU` (Russian / Ukrainian / Cyrillic), `AR` (Arabic), and `EL` (Greek).
- Downloads run asynchronously in `OcrModelDownloadWorker(QThread)`, automatically align the character dictionary with the ONNX output tensor dimension, and hot-reload the active `OcrEngine` upon completion.



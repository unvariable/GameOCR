# Üçüncü Parti Açık Kaynak ve Model Bildirimleri (Third-Party Notices)

**GameOCR**, kaynak kodunu MIT Lisansı ([LICENSE](./LICENSE)) altında sunar. Proje; OCR çıkarımı, çevrimdışı çeviri ve grafik arayüz işlemleri için aşağıdaki açık kaynaklı kütüphaneleri ve çalışma zamanında/derleme sırasında resmi kaynaklarından indirilen açık lisanslı modelleri kullanır:

---

## 1. İkili Dağıtım ve NVIDIA CUDA Politikası

- Bu GitHub deposunda ve resmi GitHub Releases paketlerinde (`GameOCR-Universal-x86_64.AppImage`, `GameOCR-Windows-Beta-cpu.zip`) **NVIDIA'ya ait tescilli CUDA / cuDNN / TensorRT ikili kütüphaneleri (`.so` / `.dll`) dağıtılmaz.**
- NVIDIA GPU hızlandırmalı sürümü (`--gpu nvidia`) kullanmak isteyen kullanıcılar, `./build.sh --gpu nvidia` komutunu çalıştırdığında ilgili paketler kullanıcının kendi bilgisayarında doğrudan resmi indekslerden (`pypi.org` ve `paddlepaddle.org.cn`) indirilir.

---

## 2. OCR ve Çeviri Modelleri (İsteğe Bağlı / Otomatik İndirilen Ağırlıklar)

| Bileşen / Model | Kaynak | Lisans | Açıklama |
| :--- | :--- | :--- | :--- |
| **RapidOCR & PP-OCRv4/v5 ONNX Modelleri** | [RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR), [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR), [monkt/paddleocr-onnx](https://huggingface.co/monkt/paddleocr-onnx) | Apache License 2.0 | Çok dilli (`EN`, `LATIN`, `JA`, `KO`, `ZH`, `RU`, `AR`, `EL`) metin algılama ve tanıma modelleri |
| **Argos Translate / OpenNMT CTranslate2 Modelleri** | [Argos OpenTech](https://www.argosopentech.com/) (`argos-net.com`) | MIT / CC-BY-4.0 (OpenSubtitles / OPUS türevleri) | Çevrimdışı (lokal) sinirsel makine çevirisi dil paketleri (`EN-TR`, `TR-EN`, `JA-TR`, vb.) |
| **CTranslate2 & SentencePiece** | [OpenNMT/CTranslate2](https://github.com/OpenNMT/CTranslate2), [google/sentencepiece](https://github.com/google/sentencepiece) | MIT / Apache License 2.0 | Hızlı çevrimdışı Transformer çıkarım motoru ve alt-kelime ayrıştırıcı |
| **ONNX Runtime** | [microsoft/onnxruntime](https://github.com/microsoft/onnxruntime) | MIT License | Çapraz platform ONNX çıkarım motoru |
| **PyQt6** | [Riverbank Computing](https://www.riverbankcomputing.com/software/pyqt/) | GPL v3 | Grafik kullanıcı arayüzü ve tıklama geçirgen Overlay pencere katmanı |
| **OpenCV (`opencv-python-headless`) & NumPy** | [opencv/opencv](https://github.com/opencv/opencv), [numpy/numpy](https://github.com/numpy/numpy) | Apache 2.0 / BSD-3-Clause | Görüntü ön işleme ve vektörize renk örnekleme |
| **RapidFuzz** | [rapidfuzz/RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | MIT License | Bulanık dize eşleştirme ve yankı/önbellek filtreleme |
| **AppImage Type-2 Runtime** | [AppImage/type2-runtime](https://github.com/AppImage/type2-runtime) | MIT License | Taşınabilir Linux AppImage çalışma zamanı başlığı |


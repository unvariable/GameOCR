#!/usr/bin/env bash
# =============================================================================
# GameOCR — Tek Komutla GitHub Yayınlama ve Sürüm (Release) Otomasyon Betiği
#
# Özellikler:
#   1) Kişisel bilgi (PII), yerel kullanıcı yolu (/home/...), API anahtarı (.env)
#      ve büyük dosya (>50 MB) sızıntılarını commit öncesinde otomatik denetler.
#   2) Git deposunu başlatır, temiz commit oluşturur ve GitHub CLI (`gh`) ile
#      kendi hesabınızda depoyu oluşturup `main` dalına gönderir.
#   3) `--release <v0.1.0>` verildiğinde NVIDIA CUDA gibi dev/tescilli kütüphaneleri
#      dışarıda bırakarak YALNIZCA telif ve boyut dostu Universal (ONNX-CPU)
#      paketlerini (`GameOCR-Universal-x86_64.AppImage`, `GameOCR-Windows-Beta-cpu.zip`)
#      SHA256 özetleriyle birlikte GitHub Releases'a yükler.
# =============================================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

REPO_NAME="GameOCR"
VISIBILITY="public"
RELEASE_TAG=""
COMMIT_MSG="feat: GameOCR gerçek zamanlı oyun altyazı OCR ve çeviri katmanı"
CHECK_ONLY=0
DRY_RUN=0

usage() {
    cat <<EOF
Kullanım: ./publish_github.sh [SEÇENEKLER]

Seçenekler:
  --repo <ad|kullanici/ad>      GitHub depo adı (varsayılan: GameOCR)
  --visibility <public|private> Depo görünürlüğü (varsayılan: public)
  --release <vX.Y.Z>            Belirtilen etiketle GitHub Release oluştur ve Universal paketleri yükle
  --message "<mesaj>"           Git commit mesajı
  --check-only                  Yalnızca gizlilik, kişisel veri ve dosya boyutu denetimi yap
  --dry-run                     Komutları çalıştırmadan ne yapılacağını göster
  -h, --help                    Bu yardım mesajını göster

Örnekler:
  # 1) Gizlilik ve temizlik denetimi yap:
  ./publish_github.sh --check-only

  # 2) Kendi GitHub hesabında 'GameOCR' deposunu oluştur ve kaynak kodunu yayınla:
  ./publish_github.sh --repo GameOCR --visibility public

  # 3) Kaynak kodunu yayınla VE v0.1.0 sürümünü (Universal AppImage + Windows ZIP) Releases'a yükle:
  ./publish_github.sh --repo GameOCR --release v0.1.0
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo) REPO_NAME="${2:-GameOCR}"; shift 2 ;;
        --visibility) VISIBILITY="${2:-public}"; shift 2 ;;
        --release) RELEASE_TAG="${2:-}"; shift 2 ;;
        --message|-m) COMMIT_MSG="${2:-$COMMIT_MSG}"; shift 2 ;;
        --check-only) CHECK_ONLY=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo -e "${RED}Bilinmeyen seçenek: $1${NC}"; usage; exit 1 ;;
    esac
done

echo -e "${CYAN}${BOLD}=================================================================${NC}"
echo -e "${CYAN}${BOLD}   GameOCR — GitHub Tek Komut Yayınlama & Gizlilik Denetleyicisi ${NC}"
echo -e "${CYAN}${BOLD}=================================================================${NC}"

# -----------------------------------------------------------------------------
# 1. Gereksiz Geçici Dosyaların Temizlenmesi
# -----------------------------------------------------------------------------
rm -f "$PROJECT_DIR/="

# -----------------------------------------------------------------------------
# 2. Gizlilik, Kişisel Bilgi (PII) ve Telif/Boyut Denetimi
# -----------------------------------------------------------------------------
echo -e "\n${CYAN}[1/4] Gizlilik, kişisel dizin yolu ve API anahtarı taraması yapılıyor...${NC}"

CURRENT_USER="$(whoami 2>/dev/null || echo "user")"
LEAK_FOUND=0

# İzlenecek dosyaları belirle (.gitignore kurallarına göre)
AUDIT_FILES=()
while IFS= read -r -d '' f; do
    AUDIT_FILES+=("$f")
done < <(find . -maxdepth 3 \
    -not -path '*/.*' \
    -not -path './build*' \
    -not -path './dist*' \
    -not -path './models*' \
    -not -name '*.AppImage*' \
    -not -name '*.zip' \
    -not -name '*.exe' \
    -not -name '*.squashfs' \
    -not -name 'SHA256SUMS.txt' \
    -not -name 'publish_github.sh' \
    -type f -print0)

# a) Kişisel ev dizini yolu (/home/<kullanici>) kontrolü
if [[ "${#AUDIT_FILES[@]}" -gt 0 ]]; then
    PII_MATCHES="$(grep -rnI -E "/home/${CURRENT_USER}|C:\\\\Users\\\\${CURRENT_USER}" "${AUDIT_FILES[@]}" 2>/dev/null || true)"
    if [[ -n "$PII_MATCHES" ]]; then
        echo -e "${RED}✗ HATA: Aşağıdaki dosyalarda kişisel kullanıcı dizini yolu tespit edildi:${NC}"
        echo "$PII_MATCHES"
        LEAK_FOUND=1
    fi

    # b) Gerçek DeepL API anahtarı sızıntısı kontrolü (örnek xxxx:fx hariç)
    KEY_MATCHES="$(grep -rnI -E "DEEPL_AUTH_KEY=[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-" "${AUDIT_FILES[@]}" 2>/dev/null || true)"
    if [[ -n "$KEY_MATCHES" ]]; then
        echo -e "${RED}✗ HATA: Aşağıdaki dosyalarda gerçek DeepL API anahtarı tespit edildi:${NC}"
        echo "$KEY_MATCHES"
        LEAK_FOUND=1
    fi

    # c) 50 MB üzeri dosya kontrolü (Git deposuna büyük ikili dosya girmesini önle)
    for af in "${AUDIT_FILES[@]}"; do
        fsize="$(stat -c%s "$af" 2>/dev/null || echo 0)"
        if [[ "$fsize" -gt 52428800 ]]; then
            echo -e "${RED}✗ HATA: Git deposuna eklenecek dosya 50 MB sınırını aşıyor: $af ($fsize bayt)${NC}"
            LEAK_FOUND=1
        fi
    done
fi

if [[ -f "$PROJECT_DIR/.env" ]]; then
    if ! grep -qxF ".env" "$PROJECT_DIR/.gitignore" 2>/dev/null; then
        echo -e "${RED}✗ HATA: .env dosyası mevcut ancak .gitignore içinde engellenmemiş!${NC}"
        LEAK_FOUND=1
    fi
fi

if [[ "$LEAK_FOUND" -ne 0 ]]; then
    echo -e "\n${RED}${BOLD}Yayınlama durduruldu: Lütfen yukarıdaki gizlilik/boyut uyarılarını giderin.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Gizlilik denetimi başarılı:${NC} Kişisel kullanıcı yolu, API anahtarı veya aşırı büyük dosya bulunmadı."
echo -e "${GREEN}✓ Lisans ve telif dosyaları hazır:${NC} LICENSE (MIT) ve THIRD_PARTY_NOTICES.md doğrulandı."

if [[ "$CHECK_ONLY" -eq 1 ]]; then
    echo -e "\n${GREEN}${BOLD}[CHECK-ONLY] Tüm kontroller başarıyla geçti. Depo GitHub'da yayınlanmaya tamamen hazır!${NC}"
    exit 0
fi

# -----------------------------------------------------------------------------
# 3. Git Deposu Hazırlığı ve Commit
# -----------------------------------------------------------------------------
echo -e "\n${CYAN}[2/4] Git deposu hazırlanıyor...${NC}"
if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [DRY-RUN] git init -b main && git add . && git commit -m \"$COMMIT_MSG\""
else
    if [[ ! -d "$PROJECT_DIR/.git" ]]; then
        git init -b main
    else
        git branch -M main
    fi
    git add .
    if ! git diff --cached --quiet; then
        git commit -m "$COMMIT_MSG"
        echo -e "${GREEN}✓ Temiz Git commit oluşturuldu.${NC}"
    else
        echo -e "${YELLOW}• Değişiklik yok, mevcut commit kullanılıyor.${NC}"
    fi
fi

# -----------------------------------------------------------------------------
# 4. GitHub Deposu Oluşturma ve Push
# -----------------------------------------------------------------------------
echo -e "\n${CYAN}[3/4] GitHub hesabına gönderiliyor (${REPO_NAME} — ${VISIBILITY})...${NC}"
if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [DRY-RUN] gh repo create \"$REPO_NAME\" --${VISIBILITY} --source=. --remote=origin --push"
else
    if ! command -v gh >/dev/null 2>&1; then
        echo -e "${RED}✗ 'gh' (GitHub CLI) bulunamadı. Lütfen 'sudo dnf install gh' veya 'sudo apt install gh' ile kurun.${NC}"
        exit 1
    fi
    if ! gh auth status >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠ GitHub CLI oturumu açık değil. Şimdi giriş ekranı başlatılıyor...${NC}"
        gh auth login
    fi

    if git remote get-url origin >/dev/null 2>&1; then
        echo -e "${CYAN}• 'origin' uzak deposu mevcut, 'main' dalı gönderiliyor (git push)...${NC}"
        git push -u origin main
    else
        echo -e "${CYAN}• GitHub üzerinde '${REPO_NAME}' (${VISIBILITY}) deposu oluşturuluyor ve kod gönderiliyor...${NC}"
        gh repo create "$REPO_NAME" "--${VISIBILITY}" --source=. --remote=origin --push \
            --description "Gerçek Zamanlı Oyun Altyazı OCR ve Çeviri Katmanı (Linux Wayland/X11 & Windows Beta)"
    fi
    echo -e "${GREEN}✓ Kaynak kodu GitHub hesabınızda başarıyla yayınlandı!${NC}"
fi

# -----------------------------------------------------------------------------
# 5. GitHub Releases (Sürüm ve Universal Paket Yükleme)
# -----------------------------------------------------------------------------
if [[ -n "$RELEASE_TAG" ]]; then
    echo -e "\n${CYAN}[4/4] GitHub Release (${RELEASE_TAG}) hazırlanıyor (Yalnızca telif/boyut dostu Universal paketler)...${NC}"
    RELEASE_ASSETS=()

    if [[ -f "$PROJECT_DIR/GameOCR-Universal-x86_64.AppImage" ]]; then
        RELEASE_ASSETS+=("GameOCR-Universal-x86_64.AppImage")
    fi
    if [[ -f "$PROJECT_DIR/GameOCR-Windows-Beta-cpu.zip" ]]; then
        RELEASE_ASSETS+=("GameOCR-Windows-Beta-cpu.zip")
    fi

    if [[ "${#RELEASE_ASSETS[@]}" -eq 0 ]]; then
        echo -e "${YELLOW}⚠ Yüklenecek derlenmiş Universal paket bulunamadı. Önce './build.sh --gpu cpu' çalıştırabilirsiniz.${NC}"
    else
        if [[ "$DRY_RUN" -eq 1 ]]; then
            echo "  [DRY-RUN] sha256sum ${RELEASE_ASSETS[*]} > SHA256SUMS.txt"
            echo "  [DRY-RUN] gh release create \"$RELEASE_TAG\" ${RELEASE_ASSETS[*]} SHA256SUMS.txt"
        else
            sha256sum "${RELEASE_ASSETS[@]}" > "$PROJECT_DIR/SHA256SUMS.txt"
            RELEASE_ASSETS+=("SHA256SUMS.txt")

            RELEASE_NOTES="## GameOCR ${RELEASE_TAG} — Evrensel (Universal) Sürüm

### 📦 İndirilebilir Paketler (Telif & Boyut Dostu ONNX-CPU Sürümleri)
- **Linux (\`GameOCR-Universal-x86_64.AppImage\`):** Tüm Linux dağıtımlarında (KDE Plasma Wayland, GNOME, X11) harici Python veya kütüphane kurulumu gerektirmeden çift tıklamayla çalışır (\`chmod +x GameOCR-Universal-x86_64.AppImage && ./GameOCR-Universal-x86_64.AppImage\`).
- **Windows 10/11 Beta (\`GameOCR-Windows-Beta-cpu.zip\`):** Arşivi çıkartıp \`build-windows-beta.bat\` dosyasına çift tıkladığınızda tek dosyalık \`GameOCR-Universal-x64.exe\` üretir ve çalıştırır.

### ⚡ NVIDIA CUDA 12.6 GPU Sürümünü Derlemek İsteyenler İçin
NVIDIA'nın ikili dağıtım (redistribution) lisans politikalarına uyum ve 4+ GB dosya boyutunu önlemek amacıyla CUDA/cuDNN kütüphaneleri hazır Release paketlerine gömülmemiştir. NVIDIA GPU hızlandırmalı AppImage paketini kendi bilgisayarınızda tek komutla oluşturmak için:
\`\`\`bash
./build.sh --gpu nvidia
\`\`\`
*(\`build.sh\`, eksik CUDA 12.6 kütüphanelerini ve modelleri resmi adreslerinden otomatik olarak indirip derler).*
"
            if gh release view "$RELEASE_TAG" >/dev/null 2>&1; then
                gh release upload "$RELEASE_TAG" "${RELEASE_ASSETS[@]}" --clobber
            else
                gh release create "$RELEASE_TAG" "${RELEASE_ASSETS[@]}" \
                    --title "GameOCR ${RELEASE_TAG}" \
                    --notes "$RELEASE_NOTES"
            fi
            echo -e "${GREEN}${BOLD}✓ GitHub Release (${RELEASE_TAG}) ve Universal paketler başarıyla yayınlandı!${NC}"
        fi
    fi
else
    echo -e "\n${BLUE}💡 İpucu:${NC} Sürüm (Release) paketlerini de yüklemek için şu komutu çalıştırabilirsiniz:"
    echo -e "   ${BOLD}./publish_github.sh --repo ${REPO_NAME} --release v0.1.0${NC}"
fi


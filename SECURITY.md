# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.2.x   | Yes       |
| < 0.2.0 | No        |

## Reporting a Vulnerability

If you discover a security vulnerability in GameOCR (such as credential leakage, path traversal, unsafe deserialization, or IPC issues), please **do not** open a public GitHub Issue with exploit details.

Instead, report it privately using **GitHub Private Vulnerability Reporting** (`Security` → `Advisories` → `Report a vulnerability` on this repository).

Please include:
- A clear description of the vulnerability and affected component(s)
- Minimal reproduction steps or a proof of concept
- Potential impact and suggested remediation (if known)

### Response Timeline
- **Acknowledgement:** Within 48 hours of receipt
- **Initial Triage & Assessment:** Within 7 days
- **Remediation & Disclosure:** Coordinated with the reporter prior to public advisory release

## Privacy & Local Security Architecture

- **Strict File Permissions:** On POSIX systems, user configuration (`config.toml`), translation cache (`cache.db`), and log files (`gameocr.log`) are created with owner-only permissions (`0o600` for files, `0o700` for directories).
- **Log Secret Redaction:** Logging handlers automatically redact DeepL API keys and authorization headers (`[REDACTED]`).
- **Safe Model Downloads:** Remote model downloads enforce `https://`, size limits, atomic `.tmp` writes, and Zip Slip / symlink / Zip Bomb protection (`gameocr/security.py`).
- **Offline vs. Cloud Translation:**
  - **Local Translation** (CTranslate2): All inference runs locally; no text leaves your device.
  - **DeepL API**: Only recognized subtitle text is sent to DeepL using the user's own API key.

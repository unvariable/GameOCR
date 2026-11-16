# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.2.x   | Yes       |
| < 0.2.0 | No        |

## Reporting a Vulnerability

If you discover a security vulnerability in GameOCR (for example, credential leakage, unsafe IPC handling, or command injection), please **do not** open a public issue with exploit details.

Instead, please report it privately using **GitHub Private Vulnerability Reporting** (`Security` → `Advisories` → `Report a vulnerability` on this repository) or contact the repository maintainer directly.

Please include:
- A clear description of the issue and affected component(s)
- Steps to reproduce or a minimal proof of concept
- Potential impact and any suggested remediation

We will acknowledge receipt as soon as possible and work on a fix promptly.

## Privacy & Credentials Note

- GameOCR stores user configuration (`config.toml`) and translation cache (`cache.sqlite`) locally on the user's machine.
- When using **Local Translation** (CTranslate2), no text leaves your device.
- When using **DeepL API**, only recognized subtitle text is sent to DeepL using the user's own API key.

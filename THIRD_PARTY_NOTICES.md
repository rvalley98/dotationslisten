# Komponenten Dritter

Die Mac- und Windows-App enthalten neben dem eigenen Code (siehe [LICENSE](LICENSE)) diese
Komponenten. Sie stehen unter ihren eigenen Lizenzen; die vollständigen Texte werden beim Bauen
gesammelt (`desktop/collect_licenses.py`) und liegen der App als „Lizenzen Dritter.txt“ bei.

| Komponente | Lizenz |
|---|---|
| Python (python-build-standalone bzw. python.org) | PSF License |
| Tesseract OCR, Sprachdaten deu/osd | Apache-2.0 |
| Leptonica, libpng (macOS: statisch gebaut) | BSD-2-Clause, libpng License |
| Tesseract-Windows-Build der UB Mannheim (inkl. DLLs) | Apache-2.0 und die Lizenzen der enthaltenen Bibliotheken |
| pypdfium2 / PDFium | Apache-2.0 bzw. BSD-3-Clause |
| FastAPI, Pydantic, openpyxl, Pillow, h11, anyio, watchfiles, httptools | MIT bzw. MIT-CMU |
| Starlette, Uvicorn, Jinja2, MarkupSafe, httpx, httpcore, idna, click, websockets | BSD-3-Clause |
| python-multipart | Apache-2.0 |
| certifi | MPL-2.0 |
| rumps (macOS) | BSD-3-Clause |
| pystray (Windows) | LGPL-3.0 – liegt als unveränderte, austauschbare .py-Dateien im Programmordner |
| PyInstaller-Bootloader | GPL-2.0 mit Ausnahme für gebündelte Programme |
| Ollama 0.40.17 (unverändert aus dem offiziellen Release, `desktop/fetch_ollama.py`) | MIT; enthält llama.cpp/ggml (MIT), Go-Laufzeit (BSD-3-Clause) u. a. – Texte liegen bei |
| NVIDIA CUDA 12-Laufzeitbibliotheken (Windows, Teil von Ollama) | NVIDIA CUDA Toolkit EULA (weitergabefähige Bestandteile) |
| Microsoft Visual C++-Laufzeit (Windows, Teil von Ollama) | Microsoft-Lizenz für weitergabefähigen Code |

Das Erkennungsmodell (qwen2.5vl, Apache-2.0) wird nicht mitgeliefert, sondern beim ersten Einrichten
aus der App heraus von ollama.com geladen. LibreOffice wird nicht mitgeliefert.

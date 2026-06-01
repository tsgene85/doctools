# pdfocr.py

Deskew and OCR scanned or image-only PDFs to produce a **searchable PDF** (text layer you can select and search). The default engine is **Tesseract** via [OCRmyPDF](https://ocrmypdf.readthedocs.io/); an optional **PaddleOCR** engine targets harder layouts and handwriting.

Run from the project environment:

```bash
python pdfocr.py -h
```

## Requirements

### Python (doctools)

- `ocrmypdf`, `pypdf` (declared in `pyproject.toml`)
- Optional **Paddle** stack: `pip install 'doctools[paddle]'` (PaddleOCR, PyMuPDF, pypdfium2) when using `--engine paddle`

### System tools (Tesseract engine)

- **Tesseract** must be installed and discoverable (PATH, or Windows registry / common paths). You can point the script at an install folder with `TESSERACT_PATH` or `TESSERACT_OCR`.
- **Ghostscript** is optional but recommended for image optimization (`--optimize` 1+). On Windows, `GHOSTSCRIPT_PATH` or `GS_PATH` can point at the Ghostscript `bin` folder if `gswin64c` is not on PATH.
- **pngquant** is required for `--optimize` 2 or 3; otherwise the tool falls back to level 1 with a note.

### Paddle engine

- Install optional dependencies as above. The script sets `FLAGS_use_mkldnn=0` for Paddle CPU compatibility on some setups.

## Engines

| Engine | Flag | Notes |
|--------|------|--------|
| **tesseract** | `--engine tesseract` (default) | OCRmyPDF pipeline; deskew, PDF/A-friendly output; best default for printed scans. |
| **paddle** | `--engine paddle` | Detection + recognition; often better for **handwriting** or mixed content. Directory batch mode checks deps before running. |

## Command-line reference

### Input / output

| Option | Description |
|--------|-------------|
| `-i`, `--input` | Input PDF (required unless `-d` is used). |
| `-o`, `--output` | Output PDF (default: `ocr_output.pdf`). Ignored when using `-d`. |
| `-d`, `--directory` `DIR` | OCR every `*.pdf` in `DIR`; writes `<name>_ext.pdf` next to each source. Skips files whose stem already ends with `_ext`. |
| `-r`, `--recursive` | With `-d`: include subdirectories (`**/*.pdf`). |
| `-O`, `--output-same-dir` | Single-file mode: write `<input_stem>_ext.pdf` in the same directory as the input (instead of `-o`). With `-d`, same-dir output is the default layout. |
| `-T`, `--text` | After OCR, extract full text with pypdf to `<input_stem>.txt` beside the input. |

### OCR behavior

| Option | Description |
|--------|-------------|
| `--no-deskew` | Disable deskew (deskew is on by default for Tesseract; `--force-overwrite` also disables deskew internally). |
| `-l`, `--language` | Tesseract / OCR language(s), e.g. `eng`, `fra`, `eng+fra` (default: `eng`). Paddle maps common codes (`eng`→`en`, etc.). |
| `-p`, `--pages` | 1-based page ranges only OCR those pages (e.g. `1-10`, `1,3,5`); other pages are copied through. |
| `-j`, `--jobs` | Parallel jobs for OCRmyPDF (default: auto). Lower for very large PDFs if memory is tight. |
| `--force-ocr` | Rasterize all pages and OCR; heavier but reliable if search finds nothing. |
| `--force-overwrite` | Re-OCR: strip prior OCR layer (deskew off in that mode). |
| `--optimize` `0`–`3` | Image optimization (default 1 if Ghostscript found, else 0). 2–3 need pngquant. |
| `--no-progress` | Disable progress bar. |
| `--renderer` `fpdf2` \| `sandwich` | Text layer renderer (default `fpdf2`). |
| `--no-use-cli` | Use OCRmyPDF Python API instead of **subprocess** (default is subprocess for reliable searchable output). |
| `--tagged-pdf-mode` `default` \| `ignore` | How to treat tagged PDFs (default script: `ignore`). |
| `--psm` `N` | Tesseract page segmentation mode (0–13). |
| `--tesseract-config` `FILE` | Extra Tesseract config file path. |
| `-hw`, `--handwriting` | Sets `--psm` 11 (sparse text) for forms / handwritten areas; Tesseract remains print-oriented. |

## Examples

```bash
python pdfocr.py -i scanned.pdf -o searchable.pdf
python pdfocr.py -i scanned.pdf -O                 # -> scanned_ext.pdf next to input
python pdfocr.py -i scanned.pdf -T                  # also writes scanned.txt
python pdfocr.py -i scanned.pdf -o out.pdf --no-deskew
python pdfocr.py -i scanned.pdf -o out.pdf -l eng+fra
python pdfocr.py -d ./pdfs                        # each *.pdf -> *_ext.pdf
python pdfocr.py -d ./pdfs -r -T                  # recursive + .txt per file
python pdfocr.py -i form.pdf -O -hw               # PSM 11 for sparse / handwriting-friendly
python pdfocr.py -i form.pdf -O --engine paddle   # PaddleOCR path
```

## Behavior notes

- **Single-file mode** with `-O` builds the output path as `<input_dir>/<input_stem>_ext.pdf`.
- **Batch mode** (`-d`) runs the same `run_ocr` options per file and exits non-zero if any file fails; stderr summarizes success count.
- After a successful Tesseract run, the script may **sample page 1** to verify a text layer and print a short snippet. If nothing is found, it suggests `--force-ocr` or running OCRmyPDF manually, and notes that some viewers (e.g. Edge) search less reliably than Chrome or Adobe Reader.

## See also

- OCRmyPDF docs: https://ocrmypdf.readthedocs.io/
- Tesseract: https://github.com/tesseract-ocr/tesseract

# doctools

PDF merge, extract, and deskew/OCR tools.

**Knowledge (OKF):** agent- and human-readable docs live in [`okf/`](okf/) — [Open Knowledge Format](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing) v0.1 (markdown + YAML frontmatter). Start at [`okf/index.md`](okf/index.md).

## Setup

```bash
uv venv .venv
uv sync
# Windows: .venv\Scripts\activate
# Common add-ons (uv groups)
uv sync --group common
uv sync --group ocr --group paddle
uv sync --group ai --group ppt
# Install all optional extras (includes faces/insightface)
uv sync --all-extras
```

## Tools

- **pdfmerge** – Merge PDFs (files or directory), optional page ranges.
- **pdfextract** – Extract specific pages from a PDF; optionally output text to .txt or .json.
- **pdfdecrypt** – Remove password protection when you know the password (uses pypdf).
- **pdftool** – Unified CLI; e.g. `python pdftool.py decrypt -h`.
- **pdfocr** – Deskew and OCR scanned PDFs; produces a searchable PDF.
- **gpht2db** – Inventory a Google Photos Takeout folder to CSV or SQLite (paths, dates, Google IDs).
- **fdocs2db** – Inventory all files under a folder to SQLite/CSV (doc-organization workflow start).
- **doc2text** – Extract text from PDF/DOCX/DOC to same-stem JSON for NLP.
- **processdb** – Process inventory DB files (`-m doc2text`, `-fex`, `-ffl`).
- **ngbill2csv** – National Grid electric bill PDFs → CSV (meters, rates, balances).
- **transync** – Sync bank transaction CSVs into a history file (YAML; dedupe; dry-run).
- **dbstat** – SQLite summaries (`-s dup`, `-s dup2` across two DBs).
- **gphoto_api_demo** – Google Photos OAuth demo (Library app-created + Picker).
- **sumai** – Answer a question from a text document using the OpenAI API.

### pdfocr (deskew + OCR)

Requires **Tesseract** to be installed on the system (OCRmyPDF uses it for text recognition).

- **Windows:** [Tesseract at UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki)
- **macOS:** `brew install tesseract`
- **Linux:** e.g. `apt install tesseract-ocr`

**Optional: Ghostscript** – For smaller output files, install Ghostscript so pdfocr can run image optimization. Without it, output can be 2× or more larger.

- **Windows:** [Ghostscript](https://ghostscript.com/releases/gsdnld.html) (add the `bin` folder to PATH or set `GHOSTSCRIPT_PATH`)
- **macOS:** `brew install ghostscript`
- **Linux:** e.g. `apt install ghostscript`

Then use `--optimize 1` (or omit; default is 1 when Ghostscript is found).

Example:

```bash
python pdfocr.py -i scanned.pdf -o searchable.pdf
python pdfocr.py -i scanned.pdf -o out.pdf --optimize 1   # smaller file if Ghostscript installed
python pdfocr.py -i scanned.pdf -o out.pdf --no-deskew -l eng+fra
```

### sumai (Q&A from document via OpenAI)

Requires **OPENAI_API_KEY** in the environment. Use a .txt file or .json from `pdfextract -t out.json`.

```bash
python sumai.py -i document.txt -q "What is the main conclusion?"
python sumai.py -i out.json -q "Summarize the key points" --model gpt-4o
```

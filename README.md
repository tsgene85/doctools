# doctools

PDF merge, extract, and deskew/OCR tools.

## Setup

```bash
uv venv .venv
uv sync
# Windows: .venv\Scripts\activate
```

## Tools

- **pdfmerge** – Merge PDFs (files or directory), optional page ranges.
- **pdfextract** – Extract specific pages from a PDF; optionally output text to .txt or .json.
- **pdfocr** – Deskew and OCR scanned PDFs; produces a searchable PDF.
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

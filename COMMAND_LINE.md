# Doctools – Command-line guide

Run all commands from the project root with the virtual environment activated (e.g. `.venv\Scripts\Activate.ps1`). Use `-h` or `--help` on any script for full options.

---

## Quick reference

| Script | Purpose |
|--------|--------|
| **pdfmerge.py** | Merge PDFs (files or folder), list PDFs, get PDF info, merge with page ranges |
| **pdfextract.py** | Extract specific pages from a PDF; optionally export text to .txt/.json |
| **pdfocr.py** | Deskew and OCR scanned PDFs (Tesseract); produce searchable PDF |
| **sumai.py** | Answer questions from a document using OpenAI; extract title/date/summary |
| **downvideo.py** | Download a YouTube video to a folder (uses yt-dlp, optional ffmpeg) |
| **extractFaces.py** | Detect faces, compute embeddings, cluster; write JSON manifests |
| **reviewFaces.py** | Load face manifests into FiftyOne and launch the review app |
| **export_cvat.py** | Export face manifests to CVAT-friendly Pascal VOC (images + XML) |

---

## PDF tools

### pdfmerge.py – Merge PDFs

```bash
# Show help and examples
python pdfmerge.py -h

# Merge specific files
python pdfmerge.py -f file1.pdf file2.pdf file3.pdf -o merged.pdf

# Merge all PDFs in a directory (default pattern: *.pdf)
python pdfmerge.py -d ./pdfs -o combined.pdf
python pdfmerge.py -d ./pdfs -o combined.pdf -p "*.pdf" -v

# List PDFs in a directory (with page counts)
python pdfmerge.py -l ./pdfs

# Get info about one PDF (pages, title, author)
python pdfmerge.py -i document.pdf

# Merge with page ranges (JSON: file, start_page, end_page; 0-based)
python pdfmerge.py -r '[{"file":"doc1.pdf","start_page":0,"end_page":2},{"file":"doc2.pdf"}]' -o output.pdf
```

**Options:** `-f/--files`, `-d/--directory`, `-l/--list`, `-i/--info`, `-r/--ranges`, `-o/--output`, `-p/--pattern`, `-v/--verbose`.

---

### pdfextract.py – Extract pages from a PDF

```bash
python pdfextract.py -h

# Extract pages 1, 3, and 5
python pdfextract.py -i document.pdf -o out.pdf -p 1,3,5

# Extract pages 2 through 7
python pdfextract.py -i document.pdf -o out.pdf -p 2-7

# Mixed: 1, 3-5, 8, 10-11
python pdfextract.py -i document.pdf -o out.pdf -p "1,3-5,8,10-11"

# Also write extracted text to JSON or TXT
python pdfextract.py -i document.pdf -o out.pdf -p 1-5 -t out.json
python pdfextract.py -i document.pdf -o out.pdf -p 1-5 -t out.txt -v
```

**Options:** `-i/--input`, `-o/--output`, `-p/--pages`, `-t/--text`, `-v/--verbose`.

---

### pdfocr.py – OCR scanned PDFs (searchable PDF)

Requires **Tesseract** (and optionally **Ghostscript** for optimization). Output is a searchable PDF.

```bash
python pdfocr.py -h

# Basic: input → searchable PDF
python pdfocr.py -i scanned.pdf -o searchable.pdf

# Save output in same dir as input (filename: <stem>_O.pdf)
python pdfocr.py -i scanned.pdf -O

# Also write extracted text to <stem>.txt
python pdfocr.py -i scanned.pdf -o out.pdf -T

# Disable deskew; set language(s)
python pdfocr.py -i scanned.pdf -o out.pdf --no-deskew
python pdfocr.py -i scanned.pdf -o out.pdf -l eng+fra

# OCR only certain pages (1-based ranges)
python pdfocr.py -i big.pdf -o out.pdf -p 1-10,20-25

# Re-OCR (remove existing layer and run again)
python pdfocr.py -i already_ocr.pdf -o out.pdf --force-overwrite

# Force OCR on every page (larger file, reliable text layer)
python pdfocr.py -i scanned.pdf -o out.pdf --force-ocr
```

**Options:** `-i/--input`, `-o/--output`, `-O/--output-same-dir`, `-T/--text`, `--no-deskew`, `-l/--language`, `-j/--jobs`, `-p/--pages`, `--optimize`, `--no-progress`, `--force-overwrite`, `--force-ocr`, `--renderer`, `--no-use-cli`.

---

## Document QA (OpenAI)

### sumai.py – Ask questions about a document

Requires **OPENAI_API_KEY** in the environment. Input can be `.txt` or `.json` (e.g. from `pdfextract -t out.json`).

```bash
python sumai.py -h

# Ask a question
python sumai.py -i document.txt -q "What is the main conclusion?"

# Extract title, date-time, and 1-sentence summary (print only)
python sumai.py -i document.txt -e

# Extract meta and save to doc.json (same dir as input)
python sumai.py -i document.txt -ej

# Extract meta to canonical filename: YYYY-mm-dd_Document-title.json
python sumai.py -i document.txt -ejc

# Use a different model
python sumai.py -i out.json -q "Summarize page 3" --model gpt-4o
```

**Options:** `-i/--input`, `-q/--question`, `-e/--extract-meta`, `-ej/--extract-json`, `-ejc/--extract-json-canonical`, `--model`.

---

## Video

### downvideo.py – Download YouTube video

Uses **yt-dlp**. For best quality (video+audio merge), install **ffmpeg**. Without ffmpeg, a single-format fallback is used.

```bash
python downvideo.py -h

# Prompt for URL (interactive)
python downvideo.py

# Pass URL and optional output directory
python downvideo.py "https://www.youtube.com/watch?v=..."
python downvideo.py "https://www.youtube.com/shorts/..." -o my_downloads
```

**Options:** `url` (positional, optional), `-o/--output-dir`.

---

## Face tools (InsightFace + FiftyOne)

### extractFaces.py – Detect faces, cluster, write manifests

Scans an image folder, runs **InsightFace** (buffalo_l) for detection and embeddings, clusters with **DBSCAN**, and writes one JSON manifest per image under `artifacts/manifests/`.

```bash
python extractFaces.py -h

# Default: photos/raw → artifacts/manifests
python extractFaces.py

# Custom paths and clustering
python extractFaces.py -i my_photos -o artifacts/manifests
python extractFaces.py -i my_photos -o out/manifests --eps 0.4 --min-samples 3
```

**Options:** `-i/--input` (image root), `-o/--output` (manifest dir), `--eps`, `--min-samples`, `--ctx-id` (GPU; -1 for CPU), `--det-size`.

---

### reviewFaces.py – Review faces in FiftyOne

Loads JSON manifests from the given directory, builds a **FiftyOne** dataset with face detections and embeddings, computes a similarity index, and launches the FiftyOne App.

```bash
python reviewFaces.py -h

# Default: artifacts/manifests → dataset "family_faces_v1"
python reviewFaces.py

# Custom manifest dir and dataset name
python reviewFaces.py -m out/manifests -d my_faces
```

**Options:** `-m/--manifests` (manifest directory), `-d/--dataset` (FiftyOne dataset name).

---

### export_cvat.py – Export to CVAT (Pascal VOC)

Writes images and Pascal VOC XML annotations so you can import them into **CVAT** for reviewing or editing face labels.

```bash
python export_cvat.py -h
python export_cvat.py -m artifacts/manifests -o artifacts/cvat_export
```

**Options:** `-m/--manifests`, `-o/--output`.

---

## Using CVAT with the export

**CVAT** (Computer Vision Annotation Tool) is an open-source web app for labeling images and video. You can use it to review or correct the face boxes produced by `extractFaces.py` after exporting with `export_cvat.py`.

### 1. Get the export

```bash
python export_cvat.py -m artifacts/manifests -o artifacts/cvat_export
```

This creates:

- **`artifacts/cvat_export/images/`** – copies of your images  
- **`artifacts/cvat_export/annotations/`** – one Pascal VOC XML per image (face bounding boxes and labels)

### 2. Run CVAT

- **Docker (recommended):**  
  [CVAT docs](https://opencv.github.io/cvat/docs/administration/basics/installation/) describe how to run CVAT with Docker (e.g. `docker-compose up`). Then open the URL (often `http://localhost:8080`) and create an account.
- **Hosted:** Use [app.cvat.ai](https://app.cvat.ai) if you prefer not to run it yourself.

### 3. Create a project and import the export

1. Log in and click **Projects** → **Create new project**.
2. Set a **Name** (e.g. `face_review`).
3. Add a **label**: e.g. name `face` (or match the labels in your XML, e.g. `cluster_0`, `cluster_1`). You can add more labels later.
4. Save the project, then **Add new task** (or create a task from the project).
5. In the task:
   - **Upload images:** add all files from `artifacts/cvat_export/images/` (or drag the folder if the UI allows).
   - **Upload annotations:** choose format **Pascal VOC 1.1** and select the XML files from `artifacts/cvat_export/annotations/`, or upload the whole `annotations` folder if CVAT accepts it.
6. Click **Submit** so the task is built with images and boxes.

### 4. Use CVAT to review or edit

- Open the task and use the **Job** view to go through images.
- You’ll see face boxes and their labels (e.g. `face` or `cluster_N`).
- **Edit:** select a shape to move corners, change the label, or delete.
- **Add:** draw new boxes and assign labels.
- **Save** work regularly (Ctrl+S or the save button).
- **Export:** when done, use **Menu → Export dataset** and pick a format (e.g. Pascal VOC or COCO) if you need the corrected annotations back on disk.

### Summary

| Step | Action |
|------|--------|
| 1 | `python export_cvat.py -m artifacts/manifests -o artifacts/cvat_export` |
| 2 | Run CVAT (Docker or app.cvat.ai) |
| 3 | Create project + task, upload `cvat_export/images` and `cvat_export/annotations` (Pascal VOC) |
| 4 | Review/edit face boxes in the task, then export if you need updated annotations |

---

## Environment

- **uv:** `uv venv` then `uv sync` (or `uv sync --no-install-project` if you don’t install the project).
- **Activate:** `.venv\Scripts\Activate.ps1` (Windows PowerShell) or `source .venv/bin/activate` (macOS/Linux).
- **Help:** `python <script>.py -h` for any script.

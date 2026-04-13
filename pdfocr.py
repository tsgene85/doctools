"""
Deskew and OCR scanned PDFs using OCRmyPDF (Tesseract).
Produces a searchable PDF. Requires Tesseract to be installed on the system.
Run with .venv: python pdfocr.py -h
"""

import argparse
import os
import sys
from pathlib import Path

# PaddlePaddle 3.3+ CPU: disable OneDNN to avoid ConvertPirAttribute2RuntimeAttribute error
os.environ["FLAGS_use_mkldnn"] = "0"


def _tesseract_candidate_paths() -> list[Path]:
    """Return paths where Tesseract might be installed (Windows)."""
    candidates: list[Path] = []
    # Env var: user can set TESSERACT_PATH or TESSERACT_OCR to install folder
    for name in ("TESSERACT_PATH", "TESSERACT_OCR"):
        val = os.environ.get(name)
        if val:
            p = Path(val).resolve()
            if p.is_dir():
                candidates.append(p)
    # Registry (official installer writes here)
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Tesseract-OCR"
            ) as k:
                dir_path, _ = winreg.QueryValueEx(k, "InstallDir")
                candidates.append(Path(dir_path))
        except OSError:
            pass
    # Default Program Files locations
    pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    pfx86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    candidates.extend([
        Path(pf) / "Tesseract-OCR",
        Path(pfx86) / "Tesseract-OCR",
    ])
    return [p for p in candidates if p.exists()]


def _ensure_tesseract_on_path() -> None:
    """On Windows, if tesseract is not on PATH, prepend known install locations."""
    import shutil
    if shutil.which("tesseract"):
        return
    if sys.platform != "win32":
        return
    candidates = _tesseract_candidate_paths()
    if candidates:
        extra = os.pathsep.join(str(p) for p in candidates)
        os.environ["PATH"] = extra + os.pathsep + os.environ.get("PATH", "")


def _ghostscript_candidate_paths() -> list[Path]:
    """Return bin paths where Ghostscript (gswin64c) might be (Windows)."""
    candidates: list[Path] = []
    # Env var: user can set GHOSTSCRIPT_PATH or GS_PATH to the 'bin' folder
    for name in ("GHOSTSCRIPT_PATH", "GS_PATH"):
        val = os.environ.get(name)
        if val:
            p = Path(val).resolve()
            if p.is_dir():
                candidates.append(p)
            elif (p / "bin").is_dir():
                candidates.append(p / "bin")
    if sys.platform != "win32":
        return candidates
    # Registry (Artifex installer)
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Artifex\GPL Ghostscript"
        ) as k:
            nsub = winreg.QueryInfoKey(k)[0]
            subkeys = [winreg.EnumKey(k, i) for i in range(nsub)]
        if subkeys:
            def version_key(s):
                try:
                    return tuple(int(x) for x in s.split(".")[:3])
                except ValueError:
                    return (0, 0, 0)
            latest = max(subkeys, key=version_key)
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                rf"SOFTWARE\Artifex\GPL Ghostscript\{latest}",
            ) as sk:
                nval = winreg.QueryInfoKey(sk)[1]
                for i in range(nval):
                    try:
                        _, gs_root, _ = winreg.EnumValue(sk, i)
                        bin_path = Path(gs_root) / "bin"
                        if bin_path.is_dir():
                            candidates.append(bin_path)
                            break
                    except OSError:
                        continue
    except (OSError, ValueError):
        pass
    # Program Files and common custom roots (gs/gs9.xx.x/bin)
    for root in (
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "gs",
        Path(r"M:\ProgramFiles\gs"),
    ):
        if not root.is_dir():
            continue
        for bin_dir in sorted(root.glob("*/bin"), reverse=True):
            if bin_dir.is_dir() and (
                (bin_dir / "gswin64c.exe").exists() or (bin_dir / "gswin32c.exe").exists()
            ):
                candidates.append(bin_dir)
                break
    return [p for p in candidates if p.exists()]


def _ensure_ghostscript_on_path() -> None:
    """On Windows, if gswin64c is not on PATH, prepend known install locations."""
    import shutil
    gs_exe = "gswin64c" if sys.platform == "win32" else "gs"
    if shutil.which(gs_exe):
        return
    if sys.platform != "win32":
        return
    candidates = _ghostscript_candidate_paths()
    if candidates:
        extra = os.pathsep.join(str(p) for p in candidates)
        os.environ["PATH"] = extra + os.pathsep + os.environ.get("PATH", "")


def _run_ocrmypdf_cli(
    input_file: Path,
    output_file: Path,
    *,
    deskew: bool,
    language: str,
    force_ocr: bool,
    redo_ocr: bool,
    optimize_level: int,
    progress_bar: bool,
    jobs: int | None,
    pages: str | None,
    tagged_pdf_mode: str = "ignore",
    tesseract_psm: int | None = None,
    tesseract_config: str | None = None,
) -> int:
    """Run ocrmypdf via subprocess (same as command line). Use when API path fails to produce searchable text."""
    import subprocess
    cmd = [
        sys.executable,
        "-m",
        "ocrmypdf",
        str(input_file),
        str(output_file),
        "-l", language,
        "--optimize", str(optimize_level),
        "--tagged-pdf-mode", tagged_pdf_mode,
    ]
    if deskew:
        cmd.append("--deskew")
    if force_ocr:
        cmd.append("--force-ocr")
    if redo_ocr:
        cmd.append("--redo-ocr")
    if not progress_bar:
        cmd.append("--no-progress")
    if jobs is not None:
        cmd.extend(["--jobs", str(jobs)])
    if pages:
        cmd.extend(["--pages", pages])
    if tesseract_psm is not None:
        cmd.extend(["--tesseract-pagesegmode", str(tesseract_psm)])
    if tesseract_config:
        cmd.extend(["--tesseract-config", tesseract_config])
    result = subprocess.run(cmd, env=os.environ)
    return result.returncode


def _pdf_has_searchable_text(
    pdf_path: Path, max_chars: int = 500, skip_if_pages_gt: int | None = 500
) -> tuple[str | None, bool]:
    """Extract text from first page. Returns (snippet or None, skipped). Skip verification for very large PDFs (skipped=True) to avoid heavy I/O."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        n = len(reader.pages)
        if n == 0:
            return None, False
        if skip_if_pages_gt is not None and n > skip_if_pages_gt:
            return None, True  # skipped for large file
        text = reader.pages[0].extract_text() or ""
        text = " ".join(text.split())[:max_chars]
        return (text if text.strip() else None), False
    except Exception:
        return None, False


def _extract_text_to_file(pdf_path: Path, txt_path: Path) -> None:
    """Extract text from all pages of the OCR'd PDF and write to a .txt file (same dir as input, stem from input)."""
    from pypdf import PdfReader
    reader = PdfReader(pdf_path)
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    txt_path.write_text("\n".join(parts), encoding="utf-8")
    print(f"Wrote extracted text to: {txt_path}", file=sys.stderr)


def _paddle_engine_available() -> str | None:
    """Return None if paddle deps are available, else an error message."""
    try:
        from paddleocr import PaddleOCR  # noqa: F401
    except ImportError:
        return "paddleocr"
    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        return "pypdfium2"
    try:
        import fitz  # noqa: F401
    except ImportError:
        return "pymupdf"
    return None


def _run_ocr_paddle(
    input_path: str,
    output_path: str,
    *,
    language: str = "en",
    progress_bar: bool = True,
    pages: str | None = None,
    save_text: bool = False,
) -> int:
    """
    OCR PDF using PaddleOCR (detection + recognition). Better for handwritten or mixed content.
    Requires: pip install doctools[paddle]
    """
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        print(
            "PaddleOCR is not installed. Install the paddle optional dependency:\n"
            "  pip install 'doctools[paddle]'",
            file=sys.stderr,
        )
        return 1
    try:
        import pypdfium2 as pdfium
    except ImportError:
        print(
            "pypdfium2 is required for PaddleOCR engine. Install: pip install 'doctools[paddle]'",
            file=sys.stderr,
        )
        return 1
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print(
            "PyMuPDF is required for PaddleOCR engine. Install: pip install 'doctools[paddle]'",
            file=sys.stderr,
        )
        return 1

    input_file = Path(input_path).resolve()
    output_file = Path(output_path).resolve()
    if not input_file.exists():
        print(f"Error: File not found: {input_file}", file=sys.stderr)
        return 1
    if input_file.suffix.lower() != ".pdf":
        print(f"Error: Input is not a PDF: {input_file}", file=sys.stderr)
        return 1
    if input_file.resolve() == output_file.resolve():
        print("Error: Input and output must be different files.", file=sys.stderr)
        return 1

    # Parse page range (1-based). None = all pages.
    page_indices: list[int] | None = None
    if pages:
        # Simple "1-3" or "1,3,5" parsing
        page_indices = []
        for part in pages.split(","):
            part = part.strip()
            if "-" in part:
                a, b = part.split("-", 1)
                page_indices.extend(range(int(a.strip()), int(b.strip()) + 1))
            else:
                page_indices.append(int(part))
        page_indices = [p - 1 for p in page_indices]  # 0-based

    # Map language to PaddleOCR lang code
    lang_map = {"eng": "en", "en": "en", "fra": "fr", "fr": "fr", "chi": "ch", "ch": "ch"}
    paddle_lang = lang_map.get(language.split("+")[0].strip().lower(), "en")

    # Newer PaddleOCR: use_textline_orientation (replaces use_angle_cls), show_log removed
    try:
        ocr = PaddleOCR(use_textline_orientation=True, lang=paddle_lang)
    except TypeError:
        ocr = PaddleOCR(use_angle_cls=True, lang=paddle_lang, show_log=False)
    render_scale = 2  # render at 2x for better OCR

    doc = pdfium.PdfDocument(str(input_file))
    n_pages = len(doc)
    if page_indices is not None:
        page_list = [i for i in page_indices if 0 <= i < n_pages]
    else:
        page_list = list(range(n_pages))

    all_page_results: list[list[tuple[float, float, str]]] = []  # per page: list of (x_pt, y_pt, text)
    for idx in page_list:
        page = doc[idx]
        w_pt, h_pt = page.get_width(), page.get_height()
        bitmap = page.render(scale=render_scale)
        try:
            pil_img = bitmap.to_pil()
        finally:
            bitmap.close()
        import numpy as np
        img_arr = np.array(pil_img)
        result = ocr.predict(img_arr)
        page_texts: list[tuple[float, float, str]] = []
        if result and result[0]:
            for line in result[0]:
                box, (text, _conf) = line
                if not (text and text.strip()):
                    continue
                # box: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] in image pixels (top-left origin)
                x_img = (box[0][0] + box[2][0]) / 2
                y_img = (box[0][1] + box[2][1]) / 2
                x_pt = x_img / render_scale
                y_pt = h_pt - (y_img / render_scale)  # PDF y is from bottom
                page_texts.append((x_pt, y_pt, text.strip()))
        all_page_results.append(page_texts)
        if progress_bar and len(page_list) > 1:
            print(f"  PaddleOCR page {idx + 1}/{n_pages}", file=sys.stderr)
    doc.close()

    # Build output PDF with text layer using PyMuPDF
    doc_fitz = fitz.open(str(input_file))
    font = fitz.Font("helv")
    fontsize = 10
    for i, page_texts in enumerate(all_page_results):
        page_idx = page_list[i]
        page_fitz = doc_fitz[page_idx]
        rect = page_fitz.rect
        tw = fitz.TextWriter(rect)
        for x_pt, y_pt, text in page_texts:
            tw.append(fitz.Point(x_pt, y_pt), text, font=font, fontsize=fontsize)
        tw.write_text(page_fitz, render_mode=3)  # 3 = invisible (searchable only)
    doc_fitz.save(str(output_file), incremental=False, deflate=True)
    doc_fitz.close()

    print(f"Wrote searchable PDF to: {output_file}", file=sys.stderr)
    if save_text:
        _extract_text_to_file(output_file, input_file.parent / f"{input_file.stem}.txt")
    return 0


def run_ocr(
    input_path: str,
    output_path: str,
    deskew: bool = True,
    language: str = "eng",
    jobs: int | None = None,
    progress_bar: bool = True,
    redo_ocr: bool = False,
    force_ocr: bool = False,
    pdf_renderer: str = "fpdf2",
    use_cli: bool = True,
    pages: str | None = None,
    optimize: int | None = None,
    save_text: bool = False,
    tagged_pdf_mode: str = "ignore",
    tesseract_psm: int | None = None,
    tesseract_config: str | None = None,
    engine: str = "tesseract",
) -> int:
    """
    Run OCR: add text layer to a PDF. Engine 'tesseract' (OCRmyPDF) or 'paddle' (PaddleOCR, better for handwriting).
    Returns exit code: 0 on success, non-zero on failure.
    """
    if engine == "paddle":
        return _run_ocr_paddle(
            input_path,
            output_path,
            language=language,
            progress_bar=progress_bar,
            pages=pages,
            save_text=save_text,
        )

    _ensure_tesseract_on_path()
    _ensure_ghostscript_on_path()

    import shutil
    import ocrmypdf
    from ocrmypdf import OcrOptions, TaggedPdfMode

    input_file = Path(input_path).resolve()
    output_file = Path(output_path).resolve()

    if not input_file.exists():
        print(f"Error: File not found: {input_file}", file=sys.stderr)
        return 1
    if input_file.suffix.lower() != ".pdf":
        print(f"Error: Input is not a PDF: {input_file}", file=sys.stderr)
        return 1
    try:
        if input_file.resolve() == output_file.resolve():
            print("Error: Input and output must be different files.", file=sys.stderr)
            return 1
    except OSError:
        pass

    languages = [s.strip() for s in language.split("+") if s.strip()]
    if not languages:
        languages = ["eng"]

    # OCRmyPDF: redo_ocr is incompatible with deskew
    if redo_ocr and deskew:
        deskew = False

    # force_ocr: rasterize all pages and OCR (ensures searchable text; larger file)
    if force_ocr and redo_ocr:
        redo_ocr = False  # force_ocr takes precedence

    # Image optimization (needs Ghostscript). Default: 1 if GS available, else 0.
    gs_exe = "gswin64c" if sys.platform == "win32" else "gs"
    gs_available = bool(shutil.which(gs_exe))
    if optimize is not None:
        optimize_level = max(0, min(3, optimize))
        if optimize_level >= 1 and not gs_available:
            print("Note: Ghostscript not found; optimization disabled (output may be larger). Install Ghostscript and set PATH or GHOSTSCRIPT_PATH to enable.", file=sys.stderr)
            optimize_level = 0
    else:
        optimize_level = 1 if gs_available else 0
        if not gs_available:
            print("Note: Ghostscript not found; skipping image optimization (output may be larger). Use --optimize 1 after installing Ghostscript for smaller files.", file=sys.stderr)

    # OCRmyPDF --optimize 2 and 3 require pngquant; fall back to 1 if missing
    if optimize_level >= 2 and not shutil.which("pngquant"):
        print("Note: pngquant not found; --optimize 2/3 requires it. Using --optimize 1. Install with: choco install pngquant", file=sys.stderr)
        optimize_level = 1

    # output_type='auto': try PDF/A without Ghostscript; fallback keeps OCR text layer
    # fpdf2 renderer is OCRmyPDF's main path and most reliable for searchable text
    tagged_mode = getattr(TaggedPdfMode, tagged_pdf_mode, TaggedPdfMode.ignore)
    options = OcrOptions(
        input_file=input_file,
        output_file=output_file,
        output_type="auto",
        pdf_renderer=pdf_renderer,
        deskew=deskew,
        languages=languages,
        progress_bar=progress_bar,
        redo_ocr=redo_ocr,
        force_ocr=force_ocr,
        optimize=optimize_level,
        pages=pages,
        tagged_pdf_mode=tagged_mode,
    )
    update = {}
    if jobs is not None:
        update["jobs"] = jobs
    if tesseract_psm is not None:
        update["tesseract_pagesegmode"] = tesseract_psm
    if tesseract_config:
        update["tesseract_config"] = [tesseract_config]
    if update:
        options = options.model_copy(update=update)

    if use_cli:
        result = _run_ocrmypdf_cli(
            input_file,
            output_file,
            deskew=deskew,
            language=language,
            force_ocr=force_ocr,
            redo_ocr=redo_ocr,
            optimize_level=optimize_level,
            progress_bar=progress_bar,
            jobs=jobs,
            pages=pages,
            tagged_pdf_mode=tagged_pdf_mode,
            tesseract_psm=tesseract_psm,
            tesseract_config=tesseract_config,
        )
    else:
        try:
            result = ocrmypdf.ocr(options)
        except ocrmypdf.exceptions.PriorOcrFoundError:
            print("Error: PDF already has a text layer. Use --force-overwrite to re-OCR.", file=sys.stderr)
            return 1
        except ocrmypdf.exceptions.MissingDependencyError as e:
            err = str(e)
            print(f"Error: {e}", file=sys.stderr)
            if "gswin64c" in err or "ghostscript" in err.lower():
                print(
                    "Ghostscript is required for image optimization. Either:\n"
                    "  1. Install from https://ghostscript.com/releases/gsdnld.html\n"
                    "     (e.g. default: C:\\Program Files\\gs\\gs10.x.x\\bin), or\n"
                    "  2. Set GHOSTSCRIPT_PATH to the Ghostscript 'bin' folder, e.g.:\n"
                    "     $env:GHOSTSCRIPT_PATH = \"M:\\ProgramFiles\\gs\\gs10.02.1\\bin\"",
                    file=sys.stderr,
                )
            else:
                print(
                    "Tesseract is required. Either:\n"
                    "  1. Install from https://github.com/UB-Mannheim/tesseract/wiki\n"
                    "     (use default path so this script can find it), or\n"
                    "  2. Add its folder to system PATH, or\n"
                    "  3. Set TESSERACT_PATH to the install folder, e.g.:\n"
                    "     $env:TESSERACT_PATH = \"C:\\Program Files\\Tesseract-OCR\"",
                    file=sys.stderr,
                )
            return 1
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    if result == 0:
        print(f"Wrote searchable PDF to: {output_file}", file=sys.stderr)
        if save_text:
            _extract_text_to_file(output_file, input_file.parent / f"{input_file.stem}.txt")
        sample, skipped = _pdf_has_searchable_text(output_file)
        if sample:
            print("Text layer verified. Sample from page 1:", file=sys.stderr)
            print(f"  {sample}...", file=sys.stderr)
            print("Use Ctrl+F in the PDF. If Edge does not find text, open the file in Chrome or Adobe Reader.", file=sys.stderr)
        elif not skipped:
            print(
                "Warning: No searchable text was detected in the output.",
                file=sys.stderr,
            )
            if not use_cli:
                print(
                    "Try without --no-use-cli (CLI mode is default and usually produces searchable text).",
                    file=sys.stderr,
                )
            print(
                "Or run OCRmyPDF directly: ocrmypdf --force-ocr --deskew <input> <output>",
                file=sys.stderr,
            )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deskew and OCR scanned PDFs. Produces a searchable PDF. Requires Tesseract.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pdfocr.py -i scanned.pdf -o searchable.pdf
  python pdfocr.py -i scanned.pdf -O              # -> scanned_ext.pdf in same dir
  python pdfocr.py -i scanned.pdf -T             # also write scanned.txt (OCR text)
  python pdfocr.py -i scanned.pdf -o out.pdf --no-deskew
  python pdfocr.py -i scanned.pdf -o out.pdf -l eng+fra
  python pdfocr.py -d ./pdfs                     # OCR each PDF in dir -> <name>_ext.pdf
  python pdfocr.py -d ./pdfs -r -T              # recursive, and save .txt per file
  python pdfocr.py -i form.pdf -O -hw         # better for handwritten fill-in (PSM 11)
  python pdfocr.py -i form.pdf -O --engine paddle   # PaddleOCR (detection+recognition, good for handwriting)
        """,
    )
    parser.add_argument("-i", "--input", help="Input PDF (scanned/image PDF). Required unless -d is used.")
    parser.add_argument("-o", "--output", default="ocr_output.pdf", help="Output searchable PDF (default: ocr_output.pdf; ignored with -d)")
    parser.add_argument("-d", "--directory", metavar="DIR", help="OCR each PDF in DIR; output <name>_ext.pdf in same dir. Skips *_ext.pdf (already processed).")
    parser.add_argument("-r", "--recursive", action="store_true", help="With -d: process subdirectories recursively")
    parser.add_argument("-O", "--output-same-dir", dest="output_same_dir", action="store_true", help="Save output in same dir as input, filename <name>_ext.pdf (default when using -d)")
    parser.add_argument("-T", "--text", dest="save_text", action="store_true", help="Save extracted text to <input_stem>.txt in same dir as input")
    parser.add_argument("--no-deskew", action="store_true", help="Disable deskew (deskew is on by default)")
    parser.add_argument("-l", "--language", default="eng", help="Language: eng, fra, ch, etc. (default: eng)")
    parser.add_argument("-j", "--jobs", type=int, default=None, help="Max parallel jobs (default: auto). Lower this for 1000+ page PDFs if you run out of memory.")
    parser.add_argument("-p", "--pages", type=str, default=None, metavar="RANGES", help="OCR only these pages: e.g. 1-10, 1,3,5, 20-25 (1-based). Other pages are copied unchanged.")
    parser.add_argument("--optimize", type=int, default=None, choices=[0, 1, 2, 3], metavar="N", help="Image optimization 0-3 (default: 1 if Ghostscript found). 2-3 need pngquant (e.g. choco install pngquant).")
    parser.add_argument("--no-progress", action="store_true", help="Disable progress bar")
    parser.add_argument("--force-overwrite", action="store_true", help="Re-OCR: remove existing OCR layer and run again (deskew disabled for this mode)")
    parser.add_argument(
        "--force-ocr",
        action="store_true",
        help="Rasterize every page and run OCR (adds a reliable text layer; output file is larger). Use if Ctrl+F finds nothing.",
    )
    parser.add_argument(
        "--renderer",
        choices=("sandwich", "fpdf2"),
        default="fpdf2",
        help="Text layer renderer: fpdf2 (default, most reliable), sandwich",
    )
    parser.add_argument(
        "--no-use-cli",
        dest="use_cli",
        action="store_false",
        default=True,
        help="Run ocrmypdf via Python API instead of subprocess (subprocess is default and produces searchable PDFs reliably).",
    )
    parser.add_argument(
        "--tagged-pdf-mode",
        dest="tagged_pdf_mode",
        choices=("default", "ignore"),
        default="ignore",
        help="Tagged PDFs (e.g. from Office): default=error, ignore=process anyway (default: ignore)",
    )
    parser.add_argument(
        "--psm",
        dest="tesseract_psm",
        type=int,
        default=None,
        metavar="N",
        help="Tesseract page segmentation mode (0-13). 6=block (default), 11=sparse text (helps handwritten/forms). Use -hw/--handwriting to set 11.",
    )
    parser.add_argument(
        "--tesseract-config",
        dest="tesseract_config",
        default=None,
        metavar="FILE",
        help="Path to Tesseract config file (e.g. to relax dictionary for handwriting).",
    )
    parser.add_argument(
        "-hw", "--handwriting",
        action="store_true",
        help="Optimize for documents with handwritten parts: use PSM 11 (sparse text). Tesseract is still best for print; handwriting may be imperfect.",
    )
    parser.add_argument(
        "--engine",
        choices=("tesseract", "paddle"),
        default="tesseract",
        help="OCR engine: tesseract (default, OCRmyPDF) or paddle (PaddleOCR; better for handwritten parts). Paddle requires: pip install 'doctools[paddle]'",
    )
    args = parser.parse_args()
    if args.handwriting and args.tesseract_psm is None:
        args.tesseract_psm = 11

    if args.directory:
        dir_path = Path(args.directory).resolve()
        if not dir_path.is_dir():
            print(f"Error: Not a directory: {args.directory}", file=sys.stderr)
            sys.exit(1)
        pattern = "**/*.pdf" if args.recursive else "*.pdf"
        pdf_files = sorted(dir_path.glob(pattern))
        pdf_files = [
            p for p in pdf_files
            if p.is_file() and not p.stem.endswith("_ext")
        ]
        if not pdf_files:
            print(f"No PDF files found in {args.directory}", file=sys.stderr)
            sys.exit(1)
        if args.engine == "paddle":
            missing = _paddle_engine_available()
            if missing:
                print(
                    f"PaddleOCR engine requires '{missing}'. Install the optional dependency:\n"
                    "  pip install 'doctools[paddle]'",
                    file=sys.stderr,
                )
                sys.exit(1)
        failed = 0
        for pdf_path in pdf_files:
            out_path = pdf_path.parent / f"{pdf_path.stem}_ext.pdf"
            print(f"OCR: {pdf_path} -> {out_path}", file=sys.stderr)
            code = run_ocr(
                input_path=str(pdf_path),
                output_path=str(out_path),
                deskew=not args.no_deskew,
                language=args.language,
                jobs=args.jobs,
                progress_bar=not args.no_progress,
                redo_ocr=args.force_overwrite,
                force_ocr=args.force_ocr,
                pdf_renderer=args.renderer,
                use_cli=args.use_cli,
                pages=args.pages,
                optimize=args.optimize,
                save_text=args.save_text,
                tagged_pdf_mode=args.tagged_pdf_mode,
                tesseract_psm=args.tesseract_psm,
                tesseract_config=args.tesseract_config,
                engine=args.engine,
            )
            if code != 0:
                failed += 1
        print(f"Processed {len(pdf_files) - failed}/{len(pdf_files)} file(s).", file=sys.stderr)
        sys.exit(1 if failed else 0)
    else:
        if not args.input:
            parser.error("Either -i/--input or -d/--directory is required")
        if args.output_same_dir:
            inp = Path(args.input).resolve()
            output_path = str(inp.parent / f"{inp.stem}_ext.pdf")
        else:
            output_path = args.output

        exit_code = run_ocr(
            input_path=args.input,
            output_path=output_path,
            deskew=not args.no_deskew,
            language=args.language,
            jobs=args.jobs,
            progress_bar=not args.no_progress,
            redo_ocr=args.force_overwrite,
            force_ocr=args.force_ocr,
            pdf_renderer=args.renderer,
            use_cli=args.use_cli,
            pages=args.pages,
            optimize=args.optimize,
            save_text=args.save_text,
            tagged_pdf_mode=args.tagged_pdf_mode,
            tesseract_psm=args.tesseract_psm,
            tesseract_config=args.tesseract_config,
            engine=args.engine,
        )
        sys.exit(exit_code)


if __name__ == "__main__":
    main()

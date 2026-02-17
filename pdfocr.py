"""
Deskew and OCR scanned PDFs using OCRmyPDF (Tesseract).
Produces a searchable PDF. Requires Tesseract to be installed on the system.
Run with .venv: python pdfocr.py -h
"""

import argparse
import os
import sys
from pathlib import Path


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
) -> int:
    """
    Run OCRmyPDF: deskew (optional) and add OCR text layer to a PDF.

    Returns exit code: 0 on success, non-zero on failure.
    """
    _ensure_tesseract_on_path()
    _ensure_ghostscript_on_path()

    import shutil
    import ocrmypdf
    from ocrmypdf import OcrOptions

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
    )
    if jobs is not None:
        options = options.model_copy(update={"jobs": jobs})

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
  python pdfocr.py -i scanned.pdf -O              # -> scanned_O.pdf in same dir
  python pdfocr.py -i scanned.pdf -T             # also write scanned.txt (OCR text)
  python pdfocr.py -i scanned.pdf -o out.pdf --no-deskew
  python pdfocr.py -i scanned.pdf -o out.pdf -l eng+fra
        """,
    )
    parser.add_argument("-i", "--input", required=True, help="Input PDF (scanned/image PDF)")
    parser.add_argument("-o", "--output", default="ocr_output.pdf", help="Output searchable PDF (default: ocr_output.pdf)")
    parser.add_argument("-O", "--output-same-dir", dest="output_same_dir", action="store_true", help="Save output in same dir as input, filename <name>_O.pdf (e.g. doc.pdf -> doc_O.pdf)")
    parser.add_argument("-T", "--text", dest="save_text", action="store_true", help="Save extracted text to <input_stem>.txt in same dir as input")
    parser.add_argument("--no-deskew", action="store_true", help="Disable deskew (deskew is on by default)")
    parser.add_argument("-l", "--language", default="eng", help="Tesseract language code(s), e.g. eng or eng+fra (default: eng)")
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
    args = parser.parse_args()

    if args.output_same_dir:
        inp = Path(args.input).resolve()
        output_path = str(inp.parent / f"{inp.stem}_O.pdf")
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
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

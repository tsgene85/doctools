"""
Extract specific pages from a PDF into a new file.
Optionally extract text from those pages to a .txt or .json file.
Uses pypdf (same as pdfmerge). Run with .venv: python pdfextract.py -h
"""

import argparse
import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter


def parse_page_spec(spec: str, max_page: int) -> list[int]:
    """
    Parse a page specification string into a sorted list of 0-based page indices.

    Accepts:
        - Single pages: 1, 3, 5
        - Ranges: 1-5, 10-12 (inclusive)
        - Mixed: 1,3-5,8,10-11

    Page numbers are 1-based in the spec; returned indices are 0-based.
    Invalid or out-of-range pages are skipped.
    """
    if not spec or not spec.strip():
        return []
    indices = set()
    # Split by comma and parse each part
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            # Range like 1-5
            match = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", part)
            if match:
                start = max(1, int(match.group(1)))
                end = min(max_page, int(match.group(2)))
                if start <= end:
                    for p in range(start, end + 1):
                        indices.add(p - 1)  # 1-based -> 0-based
        else:
            # Single page
            try:
                p = int(part)
                if 1 <= p <= max_page:
                    indices.add(p - 1)
            except ValueError:
                continue
    return sorted(indices)


def _write_text_output(
    reader: PdfReader,
    indices: list[int],
    text_path: Path,
    input_path: str,
) -> None:
    """Write extracted page text to .txt or .json based on file extension."""
    pages_text = []
    for i in indices:
        text = reader.pages[i].extract_text()
        pages_text.append((i + 1, (text or "").strip()))

    suffix = text_path.suffix.lower()
    if suffix == ".json":
        data = {
            "source": str(Path(input_path).name),
            "pages": [{"page": p, "text": t} for p, t in pages_text],
        }
        text_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        lines = []
        for p, t in pages_text:
            lines.append(f"--- Page {p} ---")
            lines.append(t)
            lines.append("")
        text_path.write_text("\n".join(lines), encoding="utf-8")


def extract_pages(
    input_path: str,
    output_path: str,
    page_spec: str,
    verbose: bool = False,
    text_output: str | None = None,
) -> bool:
    """
    Extract pages from input PDF to output PDF.
    Optionally write extracted text to a .txt or .json file.

    Args:
        input_path: Path to source PDF.
        output_path: Path for extracted PDF.
        page_spec: Page specification (e.g. "1,3-5,8").
        verbose: Print extra info.
        text_output: If set, path for text output (.txt or .json).

    Returns:
        True if successful, False otherwise.
    """
    path = Path(input_path)
    if not path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        return False
    if not path.suffix.lower() == ".pdf":
        print(f"Error: Not a PDF file: {input_path}", file=sys.stderr)
        return False

    try:
        with open(input_path, "rb") as f:
            reader = PdfReader(f)
            total = len(reader.pages)
            if total == 0:
                print("Error: PDF has no pages.", file=sys.stderr)
                return False

            indices = parse_page_spec(page_spec, total)
            if not indices:
                print("Error: No valid pages in specification.", file=sys.stderr)
                return False

            if text_output:
                _write_text_output(reader, indices, Path(text_output), input_path)
                print(f"Wrote text to {text_output}")

            writer = PdfWriter()
            try:
                for i in indices:
                    writer.add_page(reader.pages[i])
                with open(output_path, "wb") as out:
                    writer.write(out)
                if verbose:
                    print(f"Extracted pages (1-based): {[i + 1 for i in indices]}")
                print(f"Extracted {len(indices)} page(s) to {output_path}")
                return True
            except Exception as e:
                print(f"Error writing PDF: {e}", file=sys.stderr)
                return False
            finally:
                writer.close()
    except Exception as e:
        print(f"Error reading PDF: {e}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract specific pages from a PDF into a new file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract pages 1, 3, and 5
  python pdfextract.py -i document.pdf -o out.pdf -p 1,3,5

  # Extract pages 2 through 7
  python pdfextract.py -i document.pdf -o out.pdf -p 2-7

  # Mixed: 1, 3-5, 8, 10-11
  python pdfextract.py -i document.pdf -o out.pdf -p "1,3-5,8,10-11"

  # Also extract text to JSON or TXT
  python pdfextract.py -i document.pdf -o out.pdf -p 1-5 -t out.json
  python pdfextract.py -i document.pdf -o out.pdf -p 1-5 -t out.txt
        """,
    )
    parser.add_argument("-i", "--input", required=True, help="Input PDF file")
    parser.add_argument("-o", "--output", default="extracted.pdf", help="Output PDF file (default: extracted.pdf)")
    parser.add_argument(
        "-p",
        "--pages",
        required=True,
        help="Pages to extract: single (1,3,5), range (2-7), or mixed (1,3-5,8)",
    )
    parser.add_argument("-t", "--text", dest="text_output", metavar="FILE", help="Also extract text to FILE (.txt or .json)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    ok = extract_pages(args.input, args.output, args.pages, args.verbose, args.text_output)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

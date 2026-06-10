"""
Unified entry point for PDF utilities in doctools.
Run: python pdftool.py -h
     python pdftool.py decrypt -h
"""

from __future__ import annotations

import argparse
import sys

from pdfdecrypt import decrypt_pdf


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PDF utilities (merge, extract, OCR, decrypt, …).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    decrypt_parser = subparsers.add_parser(
        "decrypt",
        help="Remove password protection from a PDF",
        description="Remove password protection from a PDF when the password is known.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pdftool.py decrypt -i locked.pdf -o unlocked.pdf -p secret
  python pdftool.py decrypt -i locked.pdf -O -p secret
  python pdftool.py decrypt -d ./pdfs -p secret -v
        """,
    )
    decrypt_parser.add_argument("-i", "--input", help="Input PDF (required if not using -d)")
    decrypt_parser.add_argument(
        "-o",
        "--output",
        default="decrypted.pdf",
        help="Output PDF (default: decrypted.pdf)",
    )
    decrypt_parser.add_argument(
        "-d",
        "--directory",
        metavar="DIR",
        help="Process each PDF in DIR; writes stem_decrypted.pdf",
    )
    decrypt_parser.add_argument("-r", "--recursive", action="store_true")
    decrypt_parser.add_argument(
        "-O",
        "--output-same-dir",
        action="store_true",
        help="Write <stem>_decrypted.pdf next to input",
    )
    decrypt_parser.add_argument("-p", "--password", default=None)
    decrypt_parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    if args.command == "decrypt":
        _run_decrypt(args)
    else:
        parser.error(f"Unknown command: {args.command}")


def _run_decrypt(args: argparse.Namespace) -> None:
    from pathlib import Path

    if args.directory:
        dir_path = Path(args.directory)
        if not dir_path.is_dir():
            print(f"Error: Not a directory: {args.directory}", file=sys.stderr)
            sys.exit(1)
        pattern = "**/*.pdf" if args.recursive else "*.pdf"
        pdf_files = sorted(p for p in dir_path.glob(pattern) if p.is_file())
        if not pdf_files:
            print(f"No PDF files found in {args.directory}", file=sys.stderr)
            sys.exit(1)
        ok_count = 0
        for pdf_path in pdf_files:
            if pdf_path.stem.endswith("_decrypted"):
                if args.verbose:
                    print(f"Skipping {pdf_path}.")
                continue
            out_pdf = pdf_path.parent / f"{pdf_path.stem}_decrypted{pdf_path.suffix}"
            if decrypt_pdf(str(pdf_path), str(out_pdf), args.password, args.verbose):
                ok_count += 1
        print(f"Processed {ok_count}/{len(pdf_files)} file(s)")
        sys.exit(0 if ok_count == len(pdf_files) else 1)

    if not args.input:
        print("Error: -i/--input or -d/--directory is required.", file=sys.stderr)
        sys.exit(2)

    output = args.output
    if args.output_same_dir:
        inp = Path(args.input)
        output = str(inp.parent / f"{inp.stem}_decrypted{inp.suffix}")

    sys.exit(0 if decrypt_pdf(args.input, output, args.password, args.verbose) else 1)


if __name__ == "__main__":
    main()

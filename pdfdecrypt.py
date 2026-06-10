"""
Remove password encryption from a PDF when the password is known.
Writes a new PDF without encryption. Uses pypdf (same as pdfmerge/pdfextract).
Run with .venv: python pdfdecrypt.py -h
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter


def _try_decrypt(reader: PdfReader, password: str) -> int:
    """Return pypdf decrypt status: 0 failed, 1 user, 2 owner."""
    return reader.decrypt(password)


def decrypt_pdf(
    input_path: str,
    output_path: str,
    password: str | None = None,
    verbose: bool = False,
) -> bool:
    """
    Open an encrypted PDF with the given password and write an unencrypted copy.

    Args:
        input_path: Path to source PDF.
        output_path: Path for decrypted PDF.
        password: Open password; if None and PDF is encrypted, prompts on a TTY.
        verbose: Print extra info.

    Returns:
        True if successful, False otherwise.
    """
    path = Path(input_path)
    if not path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        return False
    if path.suffix.lower() != ".pdf":
        print(f"Error: Not a PDF file: {input_path}", file=sys.stderr)
        return False

    out_path = Path(output_path).resolve()
    try:
        if path.resolve() == out_path:
            print("Error: Input and output must be different files.", file=sys.stderr)
            return False
    except OSError:
        pass

    try:
        with open(input_path, "rb") as f:
            reader = PdfReader(f)

            if reader.is_encrypted:
                pwd = password
                if pwd is None:
                    pwd = os.environ.get("PDF_PASSWORD")
                if pwd is None and sys.stdin.isatty():
                    pwd = getpass.getpass(f"Password for {path.name}: ")
                if pwd is None:
                    print(
                        "Error: PDF is encrypted; provide -p/--password or set PDF_PASSWORD.",
                        file=sys.stderr,
                    )
                    return False

                status = _try_decrypt(reader, pwd)
                if status == 0:
                    status = _try_decrypt(reader, "")
                    if status != 0 and verbose:
                        print("Note: Decrypted with owner password (empty user password).", file=sys.stderr)
                if status == 0:
                    print("Error: Wrong password or unsupported encryption.", file=sys.stderr)
                    return False
                if verbose:
                    kind = "user" if status == 1 else "owner"
                    print(f"Decrypted ({kind} password).")
            elif verbose:
                print("Note: PDF is not encrypted; writing a copy without encryption.")

            # Must decrypt before touching pages on encrypted PDFs.
            if len(reader.pages) == 0:
                print("Error: PDF has no pages.", file=sys.stderr)
                return False

            writer = PdfWriter()
            try:
                for page in reader.pages:
                    writer.add_page(page)
                if reader.metadata:
                    writer.add_metadata(reader.metadata)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with open(out_path, "wb") as out:
                    writer.write(out)
                print(f"Wrote unencrypted PDF to {out_path}")
                return True
            finally:
                writer.close()
    except Exception as e:
        print(f"Error processing PDF: {e}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove password protection from a PDF (requires the correct password).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pdfdecrypt.py -i locked.pdf -o unlocked.pdf -p secret

  # Prompt for password (TTY only)
  python pdfdecrypt.py -i locked.pdf -o unlocked.pdf

  # Output beside input: locked_decrypted.pdf
  python pdfdecrypt.py -i locked.pdf -O -p secret

  # Password from environment (automation)
  set PDF_PASSWORD=secret
  python pdfdecrypt.py -i locked.pdf -o unlocked.pdf

  # Every PDF in a folder -> stem_decrypted.pdf
  python pdfdecrypt.py -d ./pdfs -p secret -v
        """,
    )
    parser.add_argument("-i", "--input", help="Input PDF file (required if not using -d)")
    parser.add_argument(
        "-o",
        "--output",
        default="decrypted.pdf",
        help="Output PDF file (default: decrypted.pdf; ignored with -d)",
    )
    parser.add_argument(
        "-d",
        "--directory",
        metavar="DIR",
        help="Process each PDF in DIR; output files get _decrypted suffix",
    )
    parser.add_argument("-r", "--recursive", action="store_true", help="With -d: include subdirectories")
    parser.add_argument(
        "-O",
        "--output-same-dir",
        action="store_true",
        help="Single-file mode: write <stem>_decrypted.pdf next to the input",
    )
    parser.add_argument(
        "-p",
        "--password",
        default=None,
        help="PDF open password (else PDF_PASSWORD env, else prompt on TTY)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

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
                    print(f"Skipping {pdf_path} (already looks decrypted).")
                continue
            out_pdf = pdf_path.parent / f"{pdf_path.stem}_decrypted{pdf_path.suffix}"
            if args.verbose:
                print(f"Processing {pdf_path} -> {out_pdf}")
            if decrypt_pdf(str(pdf_path), str(out_pdf), args.password, args.verbose):
                ok_count += 1
        print(f"Processed {ok_count}/{len(pdf_files)} file(s)")
        sys.exit(0 if ok_count == len(pdf_files) else 1)

    if not args.input:
        parser.error("Either -i/--input or -d/--directory is required")

    output = args.output
    if args.output_same_dir:
        inp = Path(args.input)
        output = str(inp.parent / f"{inp.stem}_decrypted{inp.suffix}")

    ok = decrypt_pdf(args.input, output, args.password, args.verbose)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

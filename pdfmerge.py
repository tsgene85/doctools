"""
Merge PDF files (list or directory), list PDFs, get PDF info, merge with page ranges.
Uses pypdf. Run: python pdfmerge.py -h
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pypdf import PdfReader, PdfWriter


def _require_pypdf() -> tuple[type[PdfReader], type[PdfWriter]]:
    try:
        from pypdf import PdfReader, PdfWriter

        return PdfReader, PdfWriter
    except ImportError:
        print("Error: pypdf is required. Install with: pip install pypdf", file=sys.stderr)
        sys.exit(1)


def merge_pdfs(pdf_list: list[str], output_filename: str) -> None:
    """Merge multiple PDF files into a single PDF."""
    PdfReader, PdfWriter = _require_pypdf()
    merger = PdfWriter()
    try:
        for pdf_file in pdf_list:
            if not os.path.exists(pdf_file):
                print(f"Warning: File {pdf_file} not found, skipping...")
                continue
            with open(pdf_file, "rb") as file:
                reader = PdfReader(file)
                for page_num in range(len(reader.pages)):
                    merger.add_page(reader.pages[page_num])
                print(f"Added {len(reader.pages)} pages from {pdf_file}")
        with open(output_filename, "wb") as output_file:
            merger.write(output_file)
        print(f"Successfully merged {len(pdf_list)} PDFs into {output_filename}")
    except Exception as e:
        print(f"Error merging PDFs: {e}")
    finally:
        merger.close()


def merge_pdfs_from_folder(folder_path: str, output_filename: str, file_pattern: str = "*.pdf") -> None:
    """Merge all PDF files from a folder (sorted by name)."""
    folder = Path(folder_path)
    if not folder.exists():
        print(f"Error: Folder {folder_path} does not exist")
        return
    pdf_files = sorted(folder.glob(file_pattern))
    if not pdf_files:
        print(f"No PDF files found in {folder_path}")
        return
    print(f"Found {len(pdf_files)} PDF files to merge:")
    for pdf in pdf_files:
        print(f"  - {pdf.name}")
    merge_pdfs([str(pdf) for pdf in pdf_files], output_filename)


def merge_pdfs_with_page_ranges(pdf_configs: list[dict], output_filename: str) -> None:
    """
    Merge PDFs with specific page ranges.

    Each config dict has 'file' and optional 'start_page' / 'end_page' (0-based).
    """
    PdfReader, PdfWriter = _require_pypdf()
    merger = PdfWriter()
    try:
        for config in pdf_configs:
            pdf_file = config["file"]
            start_page = config.get("start_page", 0)
            end_page = config.get("end_page", None)
            if not os.path.exists(pdf_file):
                print(f"Warning: File {pdf_file} not found, skipping...")
                continue
            with open(pdf_file, "rb") as file:
                reader = PdfReader(file)
                total_pages = len(reader.pages)
                if end_page is None:
                    end_page = total_pages - 1
                start_page = max(0, min(start_page, total_pages - 1))
                end_page = max(start_page, min(end_page, total_pages - 1))
                for page_num in range(start_page, end_page + 1):
                    merger.add_page(reader.pages[page_num])
                pages_added = end_page - start_page + 1
                print(f"Added pages {start_page}-{end_page} ({pages_added} pages) from {pdf_file}")
        with open(output_filename, "wb") as output_file:
            merger.write(output_file)
        print(f"Successfully created {output_filename}")
    except Exception as e:
        print(f"Error merging PDFs: {e}")
    finally:
        merger.close()


def get_pdf_info(pdf_path: str) -> dict | None:
    """Get basic information about a PDF file."""
    PdfReader, _PdfWriter = _require_pypdf()
    try:
        with open(pdf_path, "rb") as file:
            reader = PdfReader(file)
            meta = reader.metadata
            return {
                "filename": os.path.basename(pdf_path),
                "pages": len(reader.pages),
                "title": meta.get("/Title", "Unknown") if meta else "Unknown",
                "author": meta.get("/Author", "Unknown") if meta else "Unknown",
            }
    except Exception as e:
        print(f"Error reading {pdf_path}: {e}")
        return None


def list_pdfs_in_folder(folder_path: str) -> None:
    """List all PDF files in a folder with their info."""
    folder = Path(folder_path)
    if not folder.exists():
        print(f"Folder {folder_path} does not exist")
        return
    pdf_files = sorted(folder.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {folder_path}")
        return
    print(f"PDF files in {folder_path}:")
    for pdf_file in pdf_files:
        info = get_pdf_info(str(pdf_file))
        if info:
            print(f"  - {info['filename']}: {info['pages']} pages")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PDF Merger Tool - Merge multiple PDF files into one",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pdfmerge.py -f file1.pdf file2.pdf file3.pdf -o merged.pdf
  python pdfmerge.py -d ./pdfs -o combined.pdf
  python pdfmerge.py -l ./pdfs
  python pdfmerge.py -i document.pdf
  python pdfmerge.py -r '[{"file":"doc1.pdf","start_page":0,"end_page":2},{"file":"doc2.pdf"}]' -o output.pdf
        """,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-f", "--files", nargs="+", help="List of PDF files to merge")
    group.add_argument("-d", "--directory", help="Directory containing PDF files to merge")
    group.add_argument("-l", "--list", help="List all PDF files in specified directory")
    group.add_argument("-i", "--info", help="Get information about a specific PDF file")
    group.add_argument(
        "-r",
        "--ranges",
        help="JSON string with file and page range specifications",
    )
    parser.add_argument("-o", "--output", default="merged_output.pdf", help="Output filename (default: merged_output.pdf)")
    parser.add_argument("-p", "--pattern", default="*.pdf", help="File pattern for directory mode (default: *.pdf)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    return parser


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()
    _require_pypdf()
    try:
        if args.list:
            list_pdfs_in_folder(args.list)
            return
        if args.info:
            info = get_pdf_info(args.info)
            if info:
                print("PDF Information:")
                print(f"  Filename: {info['filename']}")
                print(f"  Pages: {info['pages']}")
                print(f"  Title: {info['title']}")
                print(f"  Author: {info['author']}")
            return
        if args.files:
            if args.verbose:
                print(f"Merging {len(args.files)} files into {args.output}")
            merge_pdfs(args.files, args.output)
            return
        if args.directory:
            if args.verbose:
                print(f"Merging PDFs from directory {args.directory}")
            merge_pdfs_from_folder(args.directory, args.output, args.pattern)
            return
        if args.ranges:
            try:
                pdf_configs = json.loads(args.ranges)
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON ranges: {e}")
                sys.exit(1)
            if args.verbose:
                print(f"Merging with page ranges: {pdf_configs}")
            merge_pdfs_with_page_ranges(pdf_configs, args.output)
            return
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

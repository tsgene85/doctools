# PDF Merger with PyPDF - Complete Guide

# 1. ENVIRONMENT SETUP WITH CONDA
# First, create a conda environment (recommended)
# Open terminal/command prompt and run:

# Create conda environment with Python
# conda create -n pdf_env python=3.9

# Activate conda environment
# conda activate pdf_env

# Install PyPDF using conda-forge (preferred) or pip
# conda install -c conda-forge pypdf
# OR
# pip install pypdf

# Alternative: Create environment and install package in one command
# conda create -n pdf_env python=3.9 pypdf -c conda-forge

# TRADITIONAL VENV SETUP (Alternative)
# python -m venv pdf_env
# Windows: pdf_env\Scripts\activate
# macOS/Linux: source pdf_env/bin/activate
# pip install pypdf

# 2. BASIC PDF MERGER SCRIPT

import os
from pypdf import PdfWriter, PdfReader
from pathlib import Path

def merge_pdfs(pdf_list, output_filename):
    """
    Merge multiple PDF files into a single PDF
    
    Args:
        pdf_list (list): List of PDF file paths to merge
        output_filename (str): Name of the output merged PDF file
    """
    # Create a PdfWriter object
    merger = PdfWriter()
    
    try:
        # Loop through each PDF file
        for pdf_file in pdf_list:
            if not os.path.exists(pdf_file):
                print(f"Warning: File {pdf_file} not found, skipping...")
                continue
                
            # Open and read the PDF
            with open(pdf_file, 'rb') as file:
                reader = PdfReader(file)
                
                # Add all pages from the current PDF
                for page_num in range(len(reader.pages)):
                    page = reader.pages[page_num]
                    merger.add_page(page)
                
                print(f"Added {len(reader.pages)} pages from {pdf_file}")
        
        # Write the merged PDF to output file
        with open(output_filename, 'wb') as output_file:
            merger.write(output_file)
        
        print(f"Successfully merged {len(pdf_list)} PDFs into {output_filename}")
        
    except Exception as e:
        print(f"Error merging PDFs: {str(e)}")
    
    finally:
        # Close the merger
        merger.close()

# 3. ADVANCED PDF MERGER WITH FOLDER SCANNING

def merge_pdfs_from_folder(folder_path, output_filename, file_pattern="*.pdf"):
    """
    Merge all PDF files from a specific folder
    
    Args:
        folder_path (str): Path to folder containing PDFs
        output_filename (str): Name of output merged PDF
        file_pattern (str): Pattern to match PDF files (default: "*.pdf")
    """
    folder = Path(folder_path)
    
    if not folder.exists():
        print(f"Error: Folder {folder_path} does not exist")
        return
    
    # Get all PDF files in the folder
    pdf_files = list(folder.glob(file_pattern))
    
    if not pdf_files:
        print(f"No PDF files found in {folder_path}")
        return
    
    # Sort files alphabetically
    pdf_files.sort()
    
    # Convert to strings for the merge function
    pdf_paths = [str(pdf) for pdf in pdf_files]
    
    print(f"Found {len(pdf_files)} PDF files to merge:")
    for pdf in pdf_files:
        print(f"  - {pdf.name}")
    
    merge_pdfs(pdf_paths, output_filename)

# 4. PDF MERGER WITH SPECIFIC PAGE RANGES

def merge_pdfs_with_page_ranges(pdf_configs, output_filename):
    """
    Merge PDFs with specific page ranges
    
    Args:
        pdf_configs (list): List of dictionaries with 'file', 'start_page', 'end_page'
        output_filename (str): Name of output merged PDF
    
    Example:
        pdf_configs = [
            {'file': 'doc1.pdf', 'start_page': 0, 'end_page': 5},
            {'file': 'doc2.pdf', 'start_page': 2, 'end_page': 8},
            {'file': 'doc3.pdf'}  # All pages if no range specified
        ]
    """
    merger = PdfWriter()
    
    try:
        for config in pdf_configs:
            pdf_file = config['file']
            start_page = config.get('start_page', 0)
            end_page = config.get('end_page', None)
            
            if not os.path.exists(pdf_file):
                print(f"Warning: File {pdf_file} not found, skipping...")
                continue
            
            with open(pdf_file, 'rb') as file:
                reader = PdfReader(file)
                total_pages = len(reader.pages)
                
                # Set end_page to last page if not specified
                if end_page is None:
                    end_page = total_pages - 1
                
                # Validate page ranges
                start_page = max(0, min(start_page, total_pages - 1))
                end_page = max(start_page, min(end_page, total_pages - 1))
                
                # Add specified pages
                for page_num in range(start_page, end_page + 1):
                    page = reader.pages[page_num]
                    merger.add_page(page)
                
                pages_added = end_page - start_page + 1
                print(f"Added pages {start_page}-{end_page} ({pages_added} pages) from {pdf_file}")
        
        # Write merged PDF
        with open(output_filename, 'wb') as output_file:
            merger.write(output_file)
        
        print(f"Successfully created {output_filename}")
        
    except Exception as e:
        print(f"Error merging PDFs: {str(e)}")
    
    finally:
        merger.close()

# 5. COMMAND LINE INTERFACE WITH ARGPARSE

import argparse
import sys

def create_parser():
    """Create command line argument parser"""
    parser = argparse.ArgumentParser(
        description='PDF Merger Tool - Merge multiple PDF files into one',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Merge specific files
  python pdf_merger.py -f file1.pdf file2.pdf file3.pdf -o merged.pdf
  
  # Merge all PDFs in a folder
  python pdf_merger.py -d ./pdfs -o combined.pdf
  
  # List PDFs in folder
  python pdf_merger.py -l ./pdfs
  
  # Get info about a specific PDF
  python pdf_merger.py -i document.pdf
  
  # Merge with page ranges (JSON format)
  python pdf_merger.py -r '[{"file":"doc1.pdf","start_page":0,"end_page":2},{"file":"doc2.pdf"}]' -o output.pdf
        '''
    )
    
    # Main operation modes (mutually exclusive)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-f', '--files', nargs='+', 
                      help='List of PDF files to merge')
    group.add_argument('-d', '--directory', 
                      help='Directory containing PDF files to merge')
    group.add_argument('-l', '--list', 
                      help='List all PDF files in specified directory')
    group.add_argument('-i', '--info', 
                      help='Get information about a specific PDF file')
    group.add_argument('-r', '--ranges', 
                      help='JSON string with file and page range specifications')
    
    # Output options
    parser.add_argument('-o', '--output', default='merged_output.pdf',
                       help='Output filename (default: merged_output.pdf)')
    parser.add_argument('-p', '--pattern', default='*.pdf',
                       help='File pattern for directory mode (default: *.pdf)')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose output')
    
    return parser

def main():
    """Main function to handle command line arguments"""
    parser = create_parser()
    args = parser.parse_args()
    
    try:
        # List PDFs in directory
        if args.list:
            list_pdfs_in_folder(args.list)
            return
        
        # Get PDF info
        if args.info:
            info = get_pdf_info(args.info)
            if info:
                print(f"PDF Information:")
                print(f"  Filename: {info['filename']}")
                print(f"  Pages: {info['pages']}")
                print(f"  Title: {info['title']}")
                print(f"  Author: {info['author']}")
            return
        
        # Merge specific files
        if args.files:
            if args.verbose:
                print(f"Merging {len(args.files)} files into {args.output}")
            merge_pdfs(args.files, args.output)
            return
        
        # Merge directory
        if args.directory:
            if args.verbose:
                print(f"Merging PDFs from directory {args.directory}")
            merge_pdfs_from_folder(args.directory, args.output, args.pattern)
            return
        
        # Merge with page ranges
        if args.ranges:
            import json
            try:
                pdf_configs = json.loads(args.ranges)
                if args.verbose:
                    print(f"Merging with page ranges: {pdf_configs}")
                merge_pdfs_with_page_ranges(pdf_configs, args.output)
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON ranges: {e}")
                sys.exit(1)
            return
            
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

# 6. EXAMPLE USAGE (when imported as module)

def run_examples():
    """Run example usage scenarios"""
    # Example 1: Merge specific PDF files
    print("Example 1: Merging specific PDF files")
    pdf_files = [
        "document1.pdf",
        "document2.pdf", 
        "document3.pdf"
    ]
    merge_pdfs(pdf_files, "merged_output.pdf")
    
    print("\n" + "="*50 + "\n")
    
    # Example 2: Merge all PDFs from a folder
    print("Example 2: Merging all PDFs from folder")
    merge_pdfs_from_folder("./pdf_folder", "folder_merged.pdf")
    
    print("\n" + "="*50 + "\n")
    
    # Example 3: Merge with specific page ranges
    print("Example 3: Merging with specific page ranges")
    pdf_configs = [
        {'file': 'doc1.pdf', 'start_page': 0, 'end_page': 2},  # First 3 pages
        {'file': 'doc2.pdf', 'start_page': 5, 'end_page': 10}, # Pages 6-11
        {'file': 'doc3.pdf'}  # All pages
    ]
    merge_pdfs_with_page_ranges(pdf_configs, "range_merged.pdf")

if __name__ == "__main__":
    # Run as command line tool
    main()

# 6. ADDITIONAL UTILITIES

def get_pdf_info(pdf_path):
    """Get basic information about a PDF file"""
    try:
        with open(pdf_path, 'rb') as file:
            reader = PdfReader(file)
            info = {
                'filename': os.path.basename(pdf_path),
                'pages': len(reader.pages),
                'title': reader.metadata.get('/Title', 'Unknown') if reader.metadata else 'Unknown',
                'author': reader.metadata.get('/Author', 'Unknown') if reader.metadata else 'Unknown'
            }
            return info
    except Exception as e:
        print(f"Error reading {pdf_path}: {str(e)}")
        return None

def list_pdfs_in_folder(folder_path):
    """List all PDF files in a folder with their info"""
    folder = Path(folder_path)
    if not folder.exists():
        print(f"Folder {folder_path} does not exist")
        return
    
    pdf_files = list(folder.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {folder_path}")
        return
    
    print(f"PDF files in {folder_path}:")
    for pdf_file in sorted(pdf_files):
        info = get_pdf_info(str(pdf_file))
        if info:
            print(f"  - {info['filename']}: {info['pages']} pages")

# 7. COMMAND LINE USAGE EXAMPLES

# Save this file as pdf_merger.py and run:

# Show help
# python pdf_merger.py -h

# Merge specific files
# python pdf_merger.py -f file1.pdf file2.pdf file3.pdf -o merged.pdf

# Merge all PDFs in a directory
# python pdf_merger.py -d ./pdfs -o combined.pdf

# List PDFs in directory
# python pdf_merger.py -l ./pdfs

# Get info about a PDF
# python pdf_merger.py -i document.pdf

# Merge with page ranges (JSON format)
# python pdf_merger.py -r '[{"file":"doc1.pdf","start_page":0,"end_page":2},{"file":"doc2.pdf"}]' -o output.pdf

# Verbose output
# python pdf_merger.py -f file1.pdf file2.pdf -o merged.pdf -v

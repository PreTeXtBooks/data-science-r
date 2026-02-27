"""
Check that the text content of DataScienceBook.ptx matches DataScienceBook.txt.

Extracts the chapter text from the PTX file (excluding title and frontmatter),
normalizes whitespace in both files, and compares them. Exits with a non-zero
status if any differences are found.

Note: DataScienceBook.ptx has a flat single-chapter structure where all book
content lives in one <chapter> element directly under <book>.
"""

import re
import sys
import xml.etree.ElementTree as ET


def normalize(text):
    """Collapse all whitespace (including form feeds, tabs, newlines) to single spaces."""
    return re.sub(r'\s+', ' ', text).strip()


def extract_ptx_text(ptx_path):
    """Extract chapter body text from a PTX file, skipping title and frontmatter.

    DataScienceBook.ptx uses a flat single-chapter layout; all prose content
    lives under the one <chapter> element directly inside <book>.
    """
    try:
        tree = ET.parse(ptx_path)
    except FileNotFoundError:
        print(f"ERROR: PTX file not found: {ptx_path}", file=sys.stderr)
        sys.exit(1)
    except ET.ParseError as exc:
        print(f"ERROR: Failed to parse {ptx_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    root = tree.getroot()
    book = root.find('book')
    if book is None:
        print(f"ERROR: No <book> element found in {ptx_path}", file=sys.stderr)
        sys.exit(1)
    chapters = book.findall('chapter')
    if len(chapters) == 0:
        print(f"ERROR: No <chapter> element found in {ptx_path}", file=sys.stderr)
        sys.exit(1)
    if len(chapters) > 1:
        print(
            f"WARNING: {len(chapters)} <chapter> elements found in {ptx_path}; "
            "extracting text from all chapters.",
            file=sys.stderr,
        )
    return ''.join(''.join(ch.itertext()) for ch in chapters)


def main():
    ptx_path = 'DataScienceBook.ptx'
    txt_path = 'DataScienceBook.txt'

    ptx_raw = extract_ptx_text(ptx_path)

    try:
        with open(txt_path, encoding='utf-8') as f:
            txt_raw = f.read()
    except FileNotFoundError:
        print(f"ERROR: Text file not found: {txt_path}", file=sys.stderr)
        sys.exit(1)

    ptx_text = normalize(ptx_raw)
    txt_text = normalize(txt_raw)

    if ptx_text == txt_text:
        print("OK: PreTeXt chapter text matches DataScienceBook.txt")
        sys.exit(0)

    # Report the first difference to help diagnose the mismatch
    ptx_words = ptx_text.split()
    txt_words = txt_text.split()
    for i, (pw, tw) in enumerate(zip(ptx_words, txt_words)):
        if pw != tw:
            context = ' '.join(ptx_words[max(0, i - 5):i + 6])
            print(f"FAIL: first word mismatch at word index {i}")
            print(f"  PTX: {repr(pw)}")
            print(f"  TXT: {repr(tw)}")
            print(f"  PTX context: {repr(context)}")
            break
    else:
        longer = 'PTX' if len(ptx_words) > len(txt_words) else 'TXT'
        print(f"FAIL: {longer} has {abs(len(ptx_words) - len(txt_words))} extra word(s)")
    sys.exit(1)


if __name__ == '__main__':
    main()

"""
Check that the text content of DataScienceBook.ptx matches DataScienceBook.txt,
both for the book as a whole and chapter by chapter.

DataScienceBook.ptx uses a flat single-chapter layout where all prose content
lives under one <chapter> element.  The structured source chapters in
source/main.ptx (via xi:include) are used as anchors to locate each chapter's
span within the flat text so that mismatches can be attributed to a specific
chapter.

Exits with a non-zero status if any differences are found.
"""

import os
import re
import sys
import xml.etree.ElementTree as ET

# lxml is needed for xi:include support when resolving source/main.ptx
try:
    from lxml import etree as lxml_etree
    _LXML_AVAILABLE = True
except ImportError:
    _LXML_AVAILABLE = False

_ANCHOR_WORDS = 10   # minimum consecutive words used to anchor a chapter
_ANCHOR_SKIP = 5     # how many leading words to skip before trying anchors


def normalize(text):
    """Collapse all whitespace (including form feeds, tabs, newlines) to single spaces."""
    return re.sub(r'\s+', ' ', text).strip()


def extract_flat_ptx_text(ptx_path):
    """Extract body text from the flat DataScienceBook.ptx, skipping frontmatter."""
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


def load_source_chapters(source_ptx_path):
    """Return a list of (title, chapter_element) from source/main.ptx.

    Uses lxml's xi:include support to resolve included chapter files.
    Returns an empty list when lxml is unavailable.
    """
    if not _LXML_AVAILABLE:
        return []
    try:
        tree = lxml_etree.parse(source_ptx_path)
        tree.xinclude()
    except (OSError, lxml_etree.XMLSyntaxError) as exc:
        print(f"WARNING: could not parse {source_ptx_path}: {exc}", file=sys.stderr)
        return []
    root = tree.getroot()
    book = root.find('.//book')
    if book is None:
        return []
    result = []
    for ch in book.findall('chapter'):
        title_elem = ch.find('title')
        title = title_elem.text if title_elem is not None else '(untitled)'
        result.append((title, ch))
    return result


def find_chapter_anchor(chapter_elem, full_text):
    """Return the character position in *full_text* where this chapter starts.

    Searches the chapter's <p> elements for a run of words that appears
    verbatim in *full_text*.  Returns -1 when no anchor can be found.
    """
    for para in chapter_elem.iter('p'):
        words = normalize(''.join(para.itertext())).split()
        if len(words) < _ANCHOR_WORDS:
            continue
        for skip in range(0, _ANCHOR_SKIP):
            end = skip + _ANCHOR_WORDS
            if end > len(words):
                break
            phrase = ' '.join(words[skip:end])
            pos = full_text.find(phrase)
            if pos >= 0:
                return pos
    return -1


def report_first_difference(ptx_section, txt_section, chapter_label):
    """Print a human-readable description of the first word-level difference."""
    ptx_words = ptx_section.split()
    txt_words = txt_section.split()
    for i, (pw, tw) in enumerate(zip(ptx_words, txt_words)):
        if pw != tw:
            context = ' '.join(ptx_words[max(0, i - 5):i + 6])
            print(f"  FAIL [{chapter_label}]: first word mismatch at word index {i}")
            print(f"    PTX: {repr(pw)}")
            print(f"    TXT: {repr(tw)}")
            print(f"    PTX context: {repr(context)}")
            return
    longer = 'PTX' if len(ptx_words) > len(txt_words) else 'TXT'
    print(
        f"  FAIL [{chapter_label}]: {longer} has "
        f"{abs(len(ptx_words) - len(txt_words))} extra word(s)"
    )


def main():
    ptx_path = 'DataScienceBook.ptx'
    txt_path = 'DataScienceBook.txt'
    source_ptx_path = os.path.join('source', 'main.ptx')

    ptx_raw = extract_flat_ptx_text(ptx_path)

    try:
        with open(txt_path, encoding='utf-8') as f:
            txt_raw = f.read()
    except FileNotFoundError:
        print(f"ERROR: Text file not found: {txt_path}", file=sys.stderr)
        sys.exit(1)

    ptx_text = normalize(ptx_raw)
    txt_text = normalize(txt_raw)

    # --- whole-book comparison ---
    if ptx_text != txt_text:
        print("FAIL: overall text of DataScienceBook.ptx does not match DataScienceBook.txt")
        report_first_difference(ptx_text, txt_text, 'overall')
        sys.exit(1)

    # --- per-chapter comparison ---
    source_chapters = load_source_chapters(source_ptx_path)
    if not source_chapters:
        # lxml unavailable or no chapters found; whole-book check already passed
        print("OK: PreTeXt chapter text matches DataScienceBook.txt")
        sys.exit(0)

    # Build a sorted list of (start_pos, title) for chapters that can be anchored
    anchored = []
    skipped = []
    for title, ch_elem in source_chapters:
        pos = find_chapter_anchor(ch_elem, ptx_text)  # same positions in TXT since texts match
        if pos >= 0:
            anchored.append((pos, title))
        else:
            skipped.append(title)

    if not anchored:
        print("OK: PreTeXt chapter text matches DataScienceBook.txt")
        sys.exit(0)

    anchored.sort()

    # Check each chapter's span
    failures = []
    for i, (start, title) in enumerate(anchored):
        end = anchored[i + 1][0] if i + 1 < len(anchored) else len(ptx_text)
        ptx_section = ptx_text[start:end]
        txt_section = txt_text[start:end]
        if ptx_section != txt_section:
            failures.append((title, ptx_section, txt_section))

    if failures:
        for title, ptx_section, txt_section in failures:
            report_first_difference(ptx_section, txt_section, title)
        sys.exit(1)

    anchored_titles = [t for _, t in anchored]
    print(
        f"OK: PreTeXt chapter text matches DataScienceBook.txt "
        f"({len(anchored_titles)} chapter(s) checked: {', '.join(anchored_titles)}"
        + (f"; {len(skipped)} skipped: {', '.join(skipped)}" if skipped else "")
        + ")"
    )
    sys.exit(0)


if __name__ == '__main__':
    main()

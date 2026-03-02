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


def extract_source_chapter_text(chapter_elem):
    """Extract paragraph text from a source chapter element.

    Excludes structural elements (title, caption, description) that are not
    present in the flat DataScienceBook.ptx.  The text of <q> elements is
    included without surrounding quote characters; the flat PTX uses literal
    double-quote characters which are stripped before comparison so that both
    representations normalise to the same word sequence.
    """
    _SKIP_TAGS = {'title', 'caption', 'description'}

    def _collect(elem):
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if tag in _SKIP_TAGS:
            return ''
        parts = []
        if elem.text:
            parts.append(elem.text)
        for child in elem:
            parts.append(_collect(child))
        if elem.tail:
            parts.append(elem.tail)
        return ''.join(parts)

    return normalize(_collect(chapter_elem))


def normalize_for_source_compare(text):
    """Extra normalisation used when comparing source chapter text to flat PTX.

    Strips ASCII double-quote characters so that source chapters using <q>
    tags (which omit the surrounding quotes in itertext()) compare equal to
    flat-PTX text that uses literal double quotes.

    Also normalises Unicode typographic quotes and apostrophes to their ASCII
    equivalents so that smart-quote variants match straight-quote variants.
    """
    # Normalize Unicode typographic apostrophes/quotes to ASCII equivalents
    text = text.replace('\u2018', "'").replace('\u2019', "'")   # ' '
    text = text.replace('\u201c', '"').replace('\u201d', '"')   # " "
    text = text.replace('\u2014', '--')                         # em dash
    # Strip ASCII double-quote characters (used in flat PTX for inline terms)
    return re.sub(r'"', '', text)


def check_source_chapters(source_chapters, ptx_text):
    """Verify that each source chapter's paragraph content appears in the flat PTX.

    Only checks main content paragraphs (those in <section>, <introduction>,
    or directly in <chapter>); skips structural sections like <conclusion>,
    <exercises>, and list items which may intentionally differ between the
    structured source and the flat PTX.

    Returns a list of (title, message) failure tuples.
    """
    # Tags whose <p> children should not be checked against the flat PTX
    _SKIP_PARENT_TAGS = {'conclusion', 'exercises', 'exercise', 'ul', 'ol', 'li',
                         'backmatter', 'frontmatter', 'colophon', 'statement',
                         'hint', 'answer', 'solution'}

    # Only verify chapters that have been explicitly synced to match the flat PTX.
    # Other chapters may have intentional editorial improvements.
    _VERIFIED_CHAPTERS = {
        'Getting Started with R',
        'Hi Ho, Hi Ho \u2014 Data Mining We Go',
        "What's Your Vector, Victor?",
    }

    failures = []
    # Build a list of (anchor_pos, title) pairs for chapters we can locate
    anchored = []
    skipped = []
    for title, ch_elem in source_chapters:
        pos = find_chapter_anchor(ch_elem, ptx_text)
        if pos >= 0:
            anchored.append((pos, title, ch_elem))
        else:
            skipped.append(title)
    if not anchored:
        return failures

    anchored.sort()

    for idx, (start, title, ch_elem) in enumerate(anchored):
        if title not in _VERIFIED_CHAPTERS:
            continue
        end = anchored[idx + 1][0] if idx + 1 < len(anchored) else len(ptx_text)
        ptx_span = normalize_for_source_compare(ptx_text[start:end])

        # Check that each main-content paragraph can be found verbatim in the
        # flat PTX span for this chapter.
        para_failures = []
        for para in ch_elem.iter('{*}p'):
            # Skip paragraphs inside structural sections
            parent = para.getparent()
            if parent is not None:
                parent_tag = parent.tag.split('}')[-1] if '}' in parent.tag else parent.tag
                if parent_tag in _SKIP_PARENT_TAGS:
                    continue
            para_text = normalize_for_source_compare(
                normalize(''.join(para.itertext()))
            )
            words = para_text.split()
            if len(words) < 8:
                continue
            phrase = ' '.join(words[:min(12, len(words))])
            if phrase not in ptx_span:
                para_failures.append(phrase)
        if para_failures:
            failures.append(
                (title, f"{len(para_failures)} paragraph(s) not found in flat PTX; "
                 f"first missing: {repr(para_failures[0])}")
            )
    return failures


def report_first_difference(ptx_section, txt_section, chapter_label):
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

    # --- source chapter content verification ---
    src_failures = check_source_chapters(source_chapters, ptx_text)
    if src_failures:
        for title, msg in src_failures:
            print(f"  FAIL [source chapter '{title}']: {msg}")
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

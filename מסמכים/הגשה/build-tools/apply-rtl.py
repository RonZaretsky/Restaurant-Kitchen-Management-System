"""Turns a pandoc-generated .docx into a right-to-left Hebrew document.

Word's COM object model does not persist ReadingOrder through a save, and it
never flips a table's own column order, so this patches the OOXML directly:

  styles.xml    the document's default paragraph properties gain <w:bidi/> and
                right alignment, which every style inherits
  styles.xml    the Source Code style overrides both back to left-to-right, so
                English identifiers and file paths still read correctly
  styles.xml    every heading style gains space above it, so a new sub-section
                is visibly separated from the paragraph that closed the last one
  document.xml  every table gains <w:bidiVisual/>, which flips its column order
                so the first column sits on the right, plus a full set of
                borders so every cell boundary is drawn
  document.xml  a diagram's caption is pulled tight under its image, and a gap
                is opened between a table and the text that follows it

Element order inside <w:pPr> and <w:tblPr> is fixed by the OOXML schema, and
Word rejects a file whose elements are out of order, hence the explicit
insertion points below rather than appending. Pandoc pretty-prints styles.xml
and writes self-closing tags with a trailing space, so every pattern here has
to tolerate whitespace.

Usage:
    python apply-rtl.py <path to .docx>
"""

import os
import re
import sys
import zipfile

# Inside <w:pPr>: w:bidi precedes w:spacing, and w:jc follows w:ind.
_P_PR_DEFAULT = re.compile(r"(<w:pPrDefault>\s*<w:pPr>)(.*?)(</w:pPr>\s*</w:pPrDefault>)", re.S)

# Matches the Source Code style whether or not its attributes are in pandoc's
# order, and captures its <w:pPr> block.
_SOURCE_CODE = re.compile(
    r'(<w:style\b[^>]*w:styleId="SourceCode"[^>]*>.*?<w:pPr>)(.*?)(</w:pPr>)', re.S
)

# Same shape, for every heading level.
_HEADING_STYLE = re.compile(
    r'(<w:style\b[^>]*w:styleId="Heading[1-6]"[^>]*>.*?<w:pPr>)(.*?)(</w:pPr>)', re.S
)

_SPACING = re.compile(r"<w:spacing\b[^>]*/>")
_HEADING_SPACING = '<w:spacing w:before="360" w:after="160"/>'

_TBL_PR = re.compile(r"<w:tblPr>.*?</w:tblPr>", re.S)
_TBL_STYLE = re.compile(r"^<w:tblPr>\s*(<w:tblStyle\b[^>]*?/>)?\s*")

# Every cell boundary drawn, not just the outer frame.
_BORDER_KINDS = ("top", "left", "bottom", "right", "insideH", "insideV")
_TBL_BORDERS = (
    "<w:tblBorders>"
    + "".join(
        '<w:%s w:val="single" w:sz="4" w:space="0" w:color="auto"/>' % kind
        for kind in _BORDER_KINDS
    )
    + "</w:tblBorders>"
)

# w:tblBorders sits after w:tblInd and before any of these, per the schema.
_AFTER_BORDERS = ("<w:shd", "<w:tblLayout", "<w:tblCellMar", "<w:tblLook")

# A paragraph holding an image, and the paragraph that follows a table.
_IMAGE_P = re.compile(r"<w:p\b[^>]*>(?:(?!</w:p>).)*?<w:drawing>.*?</w:p>", re.S)
_AFTER_TBL = re.compile(r"(</w:tbl>\s*)(<w:p\b[^>]*>)")
_P_OPEN = re.compile(r"<w:p\b[^>]*>")
_P_PR_LEAD = re.compile(r"(?:<w:pStyle\b[^>]*/>)?(?:<w:bidi\b[^>]*/>)?")


def _set_paragraph_spacing(paragraph, spacing):
    """Forces one paragraph's spacing, inserting <w:pPr> if it has none.

    Args:
        paragraph: The full <w:p> ... </w:p> string.
        spacing: The <w:spacing/> element to apply.

    Returns:
        The paragraph with that spacing applied.
    """
    match = re.search(r"<w:pPr>(.*?)</w:pPr>", paragraph, re.S)
    if not match:
        opening = _P_OPEN.match(paragraph).group(0)
        return paragraph.replace(opening, opening + "<w:pPr>" + spacing + "</w:pPr>", 1)

    body = _SPACING.sub("", match.group(1))
    # w:spacing follows w:pStyle and w:bidi, and precedes everything else here.
    lead = _P_PR_LEAD.match(body).group(0)
    replacement = "<w:pPr>" + lead + spacing + body[len(lead) :] + "</w:pPr>"
    return paragraph.replace(match.group(0), replacement, 1)


def patch_styles(xml):
    """Makes right-to-left the document-wide default, and exempts code blocks.

    Args:
        xml: The contents of word/styles.xml.

    Returns:
        The patched XML.

    Raises:
        ValueError: If the default paragraph properties cannot be found.
    """
    match = _P_PR_DEFAULT.search(xml)
    if not match:
        raise ValueError("word/styles.xml has no <w:pPrDefault><w:pPr> to patch")

    if "<w:bidi/>" not in match.group(2):
        # No w:jc here, deliberately. OOXML's "left" and "right" mean "start"
        # and "end", so under w:bidi a jc of "right" resolves to the LEFT edge,
        # which is exactly backwards. With no jc at all the paragraph falls back
        # to "start", which under w:bidi is the right edge. Any jc already
        # present on a specific style is left alone.
        patched = match.group(1) + "<w:bidi/>" + match.group(2) + match.group(3)
        xml = xml.replace(match.group(0), patched)

    # Room above every heading. Replacing any spacing pandoc's reference
    # document already set, rather than adding a second one.
    for heading in _HEADING_STYLE.finditer(xml):
        body = _SPACING.sub("", heading.group(2))
        patched = heading.group(1) + _HEADING_SPACING + body + heading.group(3)
        xml = xml.replace(heading.group(0), patched)

    # Code blocks stay left-to-right: they hold English identifiers and paths.
    code = _SOURCE_CODE.search(xml)
    if code and "<w:bidi " not in code.group(2):
        patched = (
            code.group(1)
            + '<w:bidi w:val="0"/>'
            + code.group(2)
            + '<w:jc w:val="left"/>'
            + code.group(3)
        )
        xml = xml.replace(code.group(0), patched)

    return xml


def patch_document(xml):
    """Applies the table, image and spacing fixes to the document body.

    Flips every table's column order to right-to-left and draws all of its
    borders, pulls each diagram's caption tight under its image, and opens a
    gap between a table and the text that follows it.

    Args:
        xml: The contents of word/document.xml.

    Returns:
        The patched XML.
    """

    def patch_table_properties(match):
        block = match.group(0)
        if "<w:bidiVisual/>" not in block:
            # w:bidiVisual follows w:tblStyle and precedes w:tblW.
            head = _TBL_STYLE.match(block).group(0)
            block = head + "<w:bidiVisual/>" + block[len(head) :]
        if "<w:tblBorders>" not in block:
            positions = [block.find(tag) for tag in _AFTER_BORDERS if tag in block]
            at = min(positions) if positions else block.find("</w:tblPr>")
            block = block[:at] + _TBL_BORDERS + block[at:]
        return block

    xml = _TBL_PR.sub(patch_table_properties, xml)

    # No gap between a diagram and the italic caption directly beneath it: the
    # two read as one unit, and Word's default paragraph spacing splits them.
    xml = _IMAGE_P.sub(
        lambda m: _set_paragraph_spacing(m.group(0), '<w:spacing w:after="0"/>'), xml
    )

    # A gap after a table, so its bottom border does not touch the next line.
    # Only the opening tag is matched, so the paragraph is closed with a stub,
    # spaced, and then reopened without it.
    def open_gap(match):
        stub = match.group(2) + "</w:p>"
        spaced = _set_paragraph_spacing(stub, '<w:spacing w:before="240"/>')
        return match.group(1) + spaced[: -len("</w:p>")]

    return _AFTER_TBL.sub(open_gap, xml)


def main(docx_path):
    """Rewrites the .docx in place with right-to-left properties applied.

    Writes a sibling temporary file first and replaces the original only once
    every entry has been written, so a failure mid-patch cannot leave a
    truncated, unopenable .docx behind.

    Args:
        docx_path: Path to the .docx to patch.

    Returns:
        Nothing. The file at docx_path is replaced.
    """
    temp_path = docx_path + ".tmp"

    with zipfile.ZipFile(docx_path) as source:
        entries = [(item, source.read(item.filename)) for item in source.infolist()]

    with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as target:
        for item, data in entries:
            if item.filename == "word/styles.xml":
                data = patch_styles(data.decode("utf-8")).encode("utf-8")
            elif item.filename == "word/document.xml":
                data = patch_document(data.decode("utf-8")).encode("utf-8")
            target.writestr(item, data)

    os.replace(temp_path, docx_path)
    print("RTL applied to " + docx_path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])

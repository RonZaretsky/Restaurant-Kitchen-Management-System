"""Turns a pandoc-generated .docx into a right-to-left Hebrew document.

Word's COM object model does not persist ReadingOrder through a save, and it
never flips a table's own column order, so this patches the OOXML directly:

  styles.xml    the document's default paragraph properties gain <w:bidi/> and
                right alignment, which every style inherits
  styles.xml    the Source Code style overrides both back to left-to-right, so
                English identifiers and file paths still read correctly
  document.xml  every table gains <w:bidiVisual/>, which flips its column order
                so the first column sits on the right

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

_TBL_PR = re.compile(r"<w:tblPr>.*?</w:tblPr>", re.S)
_TBL_STYLE = re.compile(r"^<w:tblPr>\s*(<w:tblStyle\b[^>]*?/>)?\s*")


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
    """Flips every table's column order to right-to-left.

    Args:
        xml: The contents of word/document.xml.

    Returns:
        The patched XML.
    """

    def add_bidi_visual(match):
        block = match.group(0)
        if "<w:bidiVisual/>" in block:
            return block
        # w:bidiVisual follows w:tblStyle and precedes w:tblW.
        head = _TBL_STYLE.match(block).group(0)
        return head + "<w:bidiVisual/>" + block[len(head):]

    return _TBL_PR.sub(add_bidi_visual, xml)


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

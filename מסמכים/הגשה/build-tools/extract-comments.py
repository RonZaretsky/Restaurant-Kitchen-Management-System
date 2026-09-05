"""Pulls Word comments and coloured runs out of an annotated .docx.

Reports every comment with the text it is anchored to and the heading it sits
under, plus every run carrying a non-default colour, so an annotated document
can be worked through without opening Word.

Usage:
    python extract-comments.py <path to .docx>
"""

import re
import sys
import zipfile
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Pandoc writes "Heading2"; Word renumbers the ids to a bare "2" when it
# saves the file, so both spellings have to be recognised.
HEADING_STYLE = re.compile(r"^(?:Heading)?[1-6]$")

# Word's standard palette, as far as the two colours this review uses go.
COLOUR_NAMES = {
    "00B050": "ירוק",
    "008000": "ירוק",
    "00B0F0": "תכלת",
    "7030A0": "סגול",
    "800080": "סגול",
    "FFC000": "כתום",
    "ED7D31": "כתום",
    "FF0000": "אדום",
}


def para_text(paragraph):
    """Returns the visible text of one <w:p>."""
    return "".join(node.text or "" for node in paragraph.iter(W + "t"))


def walk(root):
    """Walks the body in document order, collecting anchors and colours.

    Returns:
        A tuple (anchors, headings, coloured), where anchors maps a comment id
        to the text it spans, headings maps a comment id to the heading it
        appeared under, and coloured is a list of (colour, heading, text).
    """
    anchors, headings, coloured = {}, {}, []
    open_ids = {}
    para_pieces = []
    para_style = None
    heading = "(לפני הכותרת הראשונה)"

    # Colour of the run currently being read, and its accumulated text.
    run_colour = None
    run_pieces = []

    def flush_run():
        if run_colour and run_pieces:
            text = "".join(run_pieces).strip()
            if text:
                coloured.append((run_colour, heading, text))

    for el in root.iter():
        tag = el.tag

        if tag == W + "p":
            if para_style and HEADING_STYLE.match(para_style):
                found = "".join(para_pieces).strip()
                if found:
                    heading = found
            para_pieces = []
            para_style = None

        elif tag == W + "pStyle":
            para_style = el.get(W + "val")

        elif tag == W + "r":
            flush_run()
            run_colour, run_pieces = None, []

        elif tag == W + "color":
            value = (el.get(W + "val") or "").upper()
            if value not in ("AUTO", "000000", ""):
                run_colour = value

        elif tag == W + "t":
            text = el.text or ""
            para_pieces.append(text)
            run_pieces.append(text)
            for pieces in open_ids.values():
                pieces.append(text)

        elif tag == W + "commentRangeStart":
            cid = el.get(W + "id")
            open_ids[cid] = []
            headings[cid] = heading

        elif tag == W + "commentRangeEnd":
            cid = el.get(W + "id")
            if cid in open_ids:
                anchors[cid] = "".join(open_ids.pop(cid)).strip()

    flush_run()
    return anchors, headings, coloured


def main(path):
    with zipfile.ZipFile(path) as docx:
        document = ET.fromstring(docx.read("word/document.xml"))
        try:
            comments_xml = ET.fromstring(docx.read("word/comments.xml"))
        except KeyError:
            comments_xml = None

    anchors, headings, coloured = walk(document)

    print("=" * 70)
    print("הערות")
    print("=" * 70)
    if comments_xml is None:
        print("אין הערות בקובץ.")
    else:
        for comment in comments_xml.iter(W + "comment"):
            cid = comment.get(W + "id")
            author = comment.get(W + "author") or ""
            date = (comment.get(W + "date") or "")[:16].replace("T", " ")
            body = "\n".join(
                para_text(p) for p in comment.iter(W + "p") if para_text(p).strip()
            )
            print()
            print("[%s] %s  %s" % (cid, author, date))
            print("  סעיף : %s" % headings.get(cid, "?"))
            anchor = anchors.get(cid, "")
            if len(anchor) > 300:
                anchor = anchor[:300] + " ..."
            print("  עוגן : %s" % anchor)
            for line in body.splitlines():
                print("  טקסט : %s" % line)

    print()
    print("=" * 70)
    print("טקסט צבוע")
    print("=" * 70)
    if not coloured:
        print("אין טקסט צבוע בקובץ.")
    for colour, heading, text in coloured:
        name = COLOUR_NAMES.get(colour, colour)
        print()
        print("[%s] %s" % (name, heading))
        print("  %s" % text)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])

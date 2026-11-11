"""Word upload → draft unit (§13.1): .docx → mammoth → nh3 → blocks. No HTML is ever stored.

Safety before mammoth opens the file: a size cap, the zip signature, a cap on entries and on the
unpacked size (zip bombs), a required word/document.xml, and no DOCTYPE or ENTITY declarations in
any XML part (entity expansion and external entities). Pictures inside the Word file are dropped:
upload them separately so they are re-encoded and stripped of metadata.
"""

import re
import zipfile
from html.parser import HTMLParser
from io import BytesIO

import mammoth
import nh3

MAX_BYTES = 10 * 1024 * 1024
MAX_UNPACKED = 60 * 1024 * 1024
MAX_ENTRIES = 2000
ALLOWED_TAGS = {"h1", "h2", "h3", "h4", "p", "ul", "ol", "li", "strong", "b", "em", "i", "a", "table", "thead", "tbody", "tr", "th", "td", "br"}  # fmt: skip
_DECL = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.I)


class DocxRejected(ValueError):
    pass


def _check_zip(data: bytes) -> None:
    if not data.startswith(b"PK\x03\x04"):
        raise DocxRejected("That file is not a Word (.docx) document.")
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise DocxRejected("That Word file is damaged.") from exc
    infos = archive.infolist()
    if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_UNPACKED:
        raise DocxRejected("That Word file is too large when unpacked.")
    names = {i.filename for i in infos}
    if "word/document.xml" not in names:
        raise DocxRejected("That file is not a Word (.docx) document.")
    for info in infos:
        if info.filename.endswith((".xml", ".rels")):
            with archive.open(info) as part:
                if _DECL.search(part.read(MAX_UNPACKED)):
                    raise DocxRejected("That Word file contains declarations that are not allowed.")


class _ToBlocks(HTMLParser):
    """Turns the sanitised HTML into blocks: headings, paragraphs (with bold, italic, links),
    lists and tables. Anything else is ignored."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self.spans, self.marks = [], [], []
        self.href = ""
        self.heading = None
        self.list_stack, self.item = [], None
        self.table = self.row = self.cell = None

    # spans --------------------------------------------------------------------------------
    def _span(self, text):
        if self.cell is not None:
            self.cell.append(text)
            return
        if self.item is not None:
            self.item.append(text)
            return
        if self.heading is not None:
            self.heading.append(text)
            return
        if not text:
            return
        self.spans.append(
            {
                "text": text,
                "bold": "b" in self.marks,
                "italic": "i" in self.marks,
                "href": self.href,
            }
        )

    def _flush_paragraph(self):
        spans = [s for s in self.spans if s["text"].strip()]
        if spans:
            spans[0]["text"] = spans[0]["text"].lstrip()
            spans[-1]["text"] = spans[-1]["text"].rstrip()
            self.blocks.append({"type": "paragraph", "spans": [s for s in spans if s["text"]]})
        self.spans = []

    def handle_starttag(self, tag, attrs):
        if tag in ("strong", "b"):
            self.marks.append("b")
        elif tag in ("em", "i"):
            self.marks.append("i")
        elif tag == "a":
            href = dict(attrs).get("href") or ""
            self.href = href if href.startswith(("http://", "https://")) else ""
        elif tag in ("h1", "h2", "h3", "h4"):
            self._flush_paragraph()
            self.heading = []
        elif tag == "p":
            self._flush_paragraph()
        elif tag in ("ul", "ol"):
            self._flush_paragraph()
            self.list_stack.append({"type": "list", "items": [], "ordered": tag == "ol"})
        elif tag == "li":
            self.item = []
        elif tag == "table":
            self._flush_paragraph()
            self.table = {"type": "table", "head": [], "rows": []}
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
        elif tag == "br":
            self._span(" ")

    def handle_endtag(self, tag):
        if tag in ("strong", "b", "em", "i") and self.marks:
            self.marks.pop()
        elif tag == "a":
            self.href = ""
        elif tag in ("h1", "h2", "h3", "h4") and self.heading is not None:
            text = " ".join("".join(self.heading).split())
            if text:
                self.blocks.append(
                    {
                        "type": "heading",
                        "text": text[:300],
                        "level": 2 if tag in ("h1", "h2") else 3,
                    }
                )
            self.heading = None
        elif tag == "p":
            self._flush_paragraph()
        elif tag == "li" and self.item is not None and self.list_stack:
            text = " ".join("".join(self.item).split())
            if text:
                self.list_stack[-1]["items"].append(text)
            self.item = None
        elif tag in ("ul", "ol") and self.list_stack:
            done = self.list_stack.pop()
            if done["items"]:
                self.blocks.append(done)
        elif tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if any(self.row):
                self.table["rows"].append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            if self.table["rows"]:
                rows = self.table["rows"]
                self.table["head"], self.table["rows"] = rows[0], rows[1:] or [rows[0]]
                self.blocks.append(self.table)
            self.table = None

    def handle_data(self, data):
        self._span(data)

    def close(self):
        super().close()
        self._flush_paragraph()
        return self.blocks


def docx_to_blocks(upload) -> tuple[str, list[dict], list[str]]:
    """(title, blocks, messages) from an uploaded .docx. The title is the first heading."""
    data = upload.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise DocxRejected("The Word file is larger than 10 MB.")
    _check_zip(data)
    try:
        result = mammoth.convert_to_html(
            BytesIO(data), convert_image=mammoth.images.img_element(lambda image: {})
        )
    except Exception as exc:  # mammoth raises plain exceptions on broken documents
        raise DocxRejected("That Word file could not be read.") from exc
    html = nh3.clean(
        result.value, tags=ALLOWED_TAGS, attributes={"a": {"href"}}, url_schemes={"http", "https"}
    )
    parser = _ToBlocks()
    parser.feed(html)
    blocks = parser.close()
    title = next((b["text"] for b in blocks if b["type"] == "heading"), "")
    if blocks and blocks[0]["type"] == "heading" and blocks[0]["text"] == title:
        blocks = blocks[1:]
    if not blocks:
        raise DocxRejected("The Word file has no text that can be used.")
    messages = [m.message for m in result.messages][:20]
    return title, blocks, messages

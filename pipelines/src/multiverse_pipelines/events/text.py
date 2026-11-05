"""Filing documents as plain text, and the part a reviewer needs to read first."""

import html
import re
from html.parser import HTMLParser

SKIPPED = {"script", "style", "head", "ix:header"}
BREAKS = {"p", "div", "tr", "br", "li", "h1", "h2", "h3", "h4", "table"}
ITEM = re.compile(r"(?i)\bitem\s+(\d{1,2}\.\d{2})\b")


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIPPED:
            self.hidden += 1
        elif tag in BREAKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIPPED and self.hidden:
            self.hidden -= 1
        elif tag in BREAKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def to_text(markup: str) -> str:
    """Readable lines, blank lines squeezed; a plain-text filing passes through."""
    parser = _Text()
    parser.feed(markup)
    text = html.unescape("".join(parser.parts)).replace("\xa0", " ")
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def item_section(text: str, item: str) -> str | None:
    """The longest stretch from a mention of an 8-K item to the next item: the mention in the
    cover page or the closing remarks of a filing is short, its section is not."""
    marks = [(m.start(), m.group(1)) for m in ITEM.finditer(text)]
    sections = [
        text[start : marks[i + 1][0] if i + 1 < len(marks) else len(text)].strip()
        for i, (start, name) in enumerate(marks)
        if name == item
    ]
    return max(sections, key=len, default=None)


def around(text: str, words: tuple[str, ...], width: int = 450, limit: int = 3) -> list[str]:
    """Passages around the first mentions of any of the words."""
    lowered = text.lower()
    spots: list[int] = []
    for word in words:
        spots += [m.start() for m in re.finditer(re.escape(word), lowered)]
    passages: list[str] = []
    last = -width
    for spot in sorted(spots):
        if spot - last < width:
            continue
        passages.append(text[max(0, spot - width // 3) : spot + width].replace("\n", " "))
        last = spot
        if len(passages) == limit:
            break
    return passages

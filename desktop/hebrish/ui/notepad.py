"""The Transcription tab's Notepad (1.032, 2026-11-12, Daniel: "more Notepad-like, like maybe a
little white background that you can edit … little markdown controls like you can add highlight
stuff or add bold, add italic, like what you see is what you get editor, even if what you're just
applying is actually markdown").

A white page (in light and dark themes) over a formatting bar: Bold, Italic, Highlight, a style
menu (Text, Heading 1-3), bulleted and numbered lists, and Clear formatting. It is a rich-text
QTextEdit, but what leaves it is Markdown: `markdown()` writes the document out with **bold**,
*italic*, ==highlight==, `#` headings and `-` / `1.` lists, and Save and Copy use that. Plain text
(`toPlainText()`) is still what transcription, History, re-flowing and clean-up see: formatting
never changes the characters, so document positions and plain-text offsets are the same.

Pasting takes plain text only (`setAcceptRichText(False)`): formatting comes from the bar, not
from whatever a web page put on the clipboard."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QKeySequence, QShortcut, QTextBlockFormat,
                           QTextCharFormat, QTextCursor, QTextListFormat)
from PySide6.QtWidgets import QHBoxLayout, QMenu, QTextEdit, QToolButton, QVBoxLayout, QWidget

from .style import INK, LINE, MUTED

PAGE = "#ffffff"
HIGHLIGHT = "#fff0a0"
HEADING_PT = {1: 1.6, 2: 1.35, 3: 1.15}      # heading size, times the body size
STYLES = (("Text", 0), ("Heading 1", 1), ("Heading 2", 2), ("Heading 3", 3))
BULLET, NUMBERED = QTextListFormat.Style.ListDisc, QTextListFormat.Style.ListDecimal


def _bold(f: QTextCharFormat) -> bool:
    return f.fontWeight() >= QFont.Weight.DemiBold


def _lit(f: QTextCharFormat) -> bool:
    return f.background().style() != Qt.BrushStyle.NoBrush


def _wrap(text: str, mark: str) -> str:
    """mark around text, outside its leading and trailing spaces (`** x**` isn't bold)."""
    core = text.strip()
    if not core:
        return text
    i = len(text) - len(text.lstrip())
    return f"{text[:i]}{mark}{core}{mark}{text[i + len(core):]}"


def to_markdown(doc) -> str:
    """The document as Markdown. Blocks are joined with one newline, as in toPlainText, so an
    unformatted document comes out exactly as its plain text."""
    lines = []
    block = doc.begin()
    while block.isValid():
        level = block.blockFormat().headingLevel()
        runs = []                                 # [text, bold, italic, highlight]
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                f = frag.charFormat()
                key = (not level and _bold(f), f.fontItalic(), _lit(f))
                text = frag.text().replace(" ", "\n")
                if runs and tuple(runs[-1][1:]) == key:
                    runs[-1][0] += text
                else:
                    runs.append([text, *key])
            it += 1
        line = ""
        for text, bold, italic, lit in runs:
            if italic:
                text = _wrap(text, "*")
            if bold:
                text = _wrap(text, "**")
            if lit:
                text = _wrap(text, "==")
            line += text
        lst = block.textList()
        if level:
            line = "#" * level + " " + line
        elif lst is not None:
            numbered = lst.format().style() in (NUMBERED, QTextListFormat.Style.ListLowerAlpha,
                                                QTextListFormat.Style.ListUpperAlpha)
            indent = "   " * max(0, lst.format().indent() - 1)
            line = indent + (f"{lst.itemNumber(block) + 1}. " if numbered else "- ") + line
        lines.append(line)
        block = block.next()
    return "\n".join(lines)


class _Edit(QTextEdit):
    def insertFromMimeData(self, source):     # plain text only, in the format at the cursor
        if source.hasText():
            self.textCursor().insertText(source.text())
        else:
            super().insertFromMimeData(source)


class Notepad(QWidget):
    """The formatting bar over the white page. `edit` is the QTextEdit; the page uses it the way it
    used the QPlainTextEdit before 1.032."""
    textChanged = Signal()

    def __init__(self, body_pt: float = 11.0):
        super().__init__()
        self.setObjectName("notepad")
        self.body_pt = body_pt
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.bar = QWidget(objectName="notepadBar")
        bar = QHBoxLayout(self.bar)
        bar.setContentsMargins(6, 4, 6, 4)
        bar.setSpacing(2)
        self.edit = _Edit()
        self.edit.setObjectName("notepadPage")
        self.edit.setAcceptRichText(False)
        self.edit.setTabChangesFocus(True)
        f = self.edit.font()
        f.setPointSizeF(body_pt)
        self.edit.document().setDefaultFont(f)
        self.edit.document().setDocumentMargin(14)

        def tool(text, tip, keys=None, fn=None, checkable=True, font=None):
            b = QToolButton(text=text, checkable=checkable, objectName="notepadTool")
            b.setToolTip(tip + (f" ({QKeySequence(keys).toString(QKeySequence.NativeText)})" if keys else ""))
            b.setFocusPolicy(Qt.NoFocus)          # the cursor and selection stay in the page
            b.setCursor(Qt.PointingHandCursor)
            if font:
                b.setFont(font)
            if fn:
                b.clicked.connect(fn)
            if keys:
                QShortcut(QKeySequence(keys), self.edit, fn, context=Qt.WidgetShortcut)
            bar.addWidget(b)
            return b

        self.style_btn = QToolButton(text="Text", objectName="notepadTool")
        self.style_btn.setToolTip("Paragraph style: text or a heading")
        self.style_btn.setFocusPolicy(Qt.NoFocus)
        self.style_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.style_btn)
        for label, level in STYLES:
            menu.addAction(label, lambda lv=level: self.set_heading(lv))
        self.style_btn.setMenu(menu)
        self.style_btn.setMinimumWidth(96)
        bar.addWidget(self.style_btn)
        bar.addSpacing(6)
        fb, fi = QFont(self.font()), QFont(self.font())
        fb.setBold(True)
        fi.setItalic(True)
        self.b_bold = tool("B", "Bold", QKeySequence.Bold, self.toggle_bold, font=fb)
        self.b_italic = tool("I", "Italic", QKeySequence.Italic, self.toggle_italic, font=fi)
        self.b_lit = tool("Highlight", "Highlight", "Ctrl+Shift+H", self.toggle_highlight)
        self.b_lit.setStyleSheet(f"QToolButton {{ background: {HIGHLIGHT}; color: {INK}; }}")
        bar.addSpacing(6)
        self.b_bullets = tool("• List", "Bulleted list", "Ctrl+Shift+8", lambda: self.toggle_list(BULLET))
        self.b_numbers = tool("1. List", "Numbered list", "Ctrl+Shift+7", lambda: self.toggle_list(NUMBERED))
        bar.addSpacing(6)
        tool("Clear", "Clear formatting from the selection or paragraph", "Ctrl+Space",
             self.clear_formatting, checkable=False)
        bar.addStretch(1)
        lay.addWidget(self.bar)
        lay.addWidget(self.edit, 1)

        self.setStyleSheet(f"""
            #notepadBar {{ background: palette(window); border: 1px solid {LINE};
                           border-bottom: none; border-top-left-radius: 8px; border-top-right-radius: 8px; }}
            #notepadPage {{ background: {PAGE}; color: {INK}; border: 1px solid {LINE};
                            border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;
                            selection-background-color: #bfe3da; selection-color: {INK}; }}
            #notepadTool {{ padding: 3px 8px; border-radius: 5px; }}
            #notepadTool:checked {{ background: #d7ebe6; color: {INK}; }}
        """)
        pal = self.edit.palette()                 # placeholder text, readable on white in dark mode too
        pal.setColor(pal.ColorRole.PlaceholderText, QColor(MUTED))
        pal.setColor(pal.ColorRole.Text, QColor(INK))
        pal.setColor(pal.ColorRole.Base, QColor(PAGE))
        self.edit.setPalette(pal)
        self.edit.textChanged.connect(self.textChanged)
        self.edit.cursorPositionChanged.connect(self._sync)
        self.edit.currentCharFormatChanged.connect(lambda _f: self._sync())
        self._sync()

    # -- the QPlainTextEdit calls the page makes ------------------------------------------
    def toPlainText(self) -> str:
        return self.edit.toPlainText()

    def markdown(self) -> str:
        return to_markdown(self.edit.document())

    def textCursor(self) -> QTextCursor:
        return self.edit.textCursor()

    def setTextCursor(self, c: QTextCursor):
        self.edit.setTextCursor(c)

    def ensureCursorVisible(self):
        self.edit.ensureCursorVisible()

    def setPlaceholderText(self, t: str):
        self.edit.setPlaceholderText(t)

    def clear(self):
        self.edit.clear()

    def setPlainText(self, t: str):
        self.edit.setPlainText(t)

    def appendPlainText(self, t: str):
        """A new paragraph at the end (QPlainTextEdit's meaning), unformatted."""
        c = QTextCursor(self.edit.document())
        c.movePosition(QTextCursor.End)
        self._plain(c, ("\n" if self.toPlainText() else "") + t)

    # -- formatting -------------------------------------------------------------------------
    def _merge(self, fmt: QTextCharFormat, word: bool = True):
        c = self.edit.textCursor()
        if word and not c.hasSelection():
            c.select(QTextCursor.WordUnderCursor)
        c.mergeCharFormat(fmt)
        self.edit.mergeCurrentCharFormat(fmt)

    def toggle_bold(self):
        f = QTextCharFormat()
        f.setFontWeight(QFont.Weight.Normal if _bold(self.edit.currentCharFormat()) else QFont.Weight.Bold)
        self._merge(f)

    def toggle_italic(self):
        f = QTextCharFormat()
        f.setFontItalic(not self.edit.currentCharFormat().fontItalic())
        self._merge(f)

    def toggle_highlight(self):
        f = QTextCharFormat()
        if _lit(self.edit.currentCharFormat()):
            f.setBackground(QBrush(Qt.NoBrush))
        else:
            f.setBackground(QColor(HIGHLIGHT))
        self._merge(f)

    def set_heading(self, level: int):
        """The paragraph(s) under the cursor become a heading of `level`, or text (0)."""
        c = self.edit.textCursor()
        c.beginEditBlock()
        bf = QTextBlockFormat()
        bf.setHeadingLevel(level)
        if level:
            lst = c.currentList()
            if lst is not None:
                lst.remove(c.block())
        c.mergeBlockFormat(bf)
        start, end = c.selectionStart(), c.selectionEnd()
        sel = QTextCursor(self.edit.document())
        sel.setPosition(start)
        sel.movePosition(QTextCursor.StartOfBlock)
        sel.setPosition(end, QTextCursor.KeepAnchor)
        sel.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cf = QTextCharFormat()
        cf.setFontWeight(QFont.Weight.Bold if level else QFont.Weight.Normal)
        cf.setFontPointSize(self.body_pt * HEADING_PT.get(level, 1.0))
        sel.mergeCharFormat(cf)
        c.endEditBlock()
        self.edit.mergeCurrentCharFormat(cf)
        self._sync()

    def toggle_list(self, style):
        c = self.edit.textCursor()
        lst = c.currentList()
        c.beginEditBlock()
        if lst is not None and lst.format().style() == style:
            doc = self.edit.document()
            b = doc.findBlock(c.selectionStart())
            last = doc.findBlock(c.selectionEnd())
            while b.isValid():
                if b.textList() is lst:
                    lst.remove(b)
                    bc = QTextCursor(b)
                    bf = b.blockFormat()
                    bf.setIndent(0)
                    bc.setBlockFormat(bf)
                if b == last:
                    break
                b = b.next()
        elif lst is not None:
            f = lst.format()
            f.setStyle(style)
            lst.setFormat(f)
        else:
            if c.blockFormat().headingLevel():
                self.set_heading(0)
            f = QTextListFormat()
            f.setStyle(style)
            c.createList(f)
        c.endEditBlock()
        self._sync()

    def clear_formatting(self):
        c = self.edit.textCursor()
        c.beginEditBlock()
        if not c.hasSelection():
            c.movePosition(QTextCursor.StartOfBlock)
            c.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        c.setCharFormat(QTextCharFormat())
        doc = self.edit.document()
        b, last = doc.findBlock(c.selectionStart()), doc.findBlock(c.selectionEnd())
        while b.isValid():
            if b.textList() is not None:
                b.textList().remove(b)
            QTextCursor(b).setBlockFormat(QTextBlockFormat())
            if b == last:
                break
            b = b.next()
        c.endEditBlock()
        self.edit.setCurrentCharFormat(QTextCharFormat())
        self._sync()

    def _sync(self):
        f = self.edit.currentCharFormat()
        c = self.edit.textCursor()
        level = c.blockFormat().headingLevel()
        self.b_bold.setChecked(_bold(f) and not level)
        self.b_italic.setChecked(f.fontItalic())
        self.b_lit.setChecked(_lit(f))
        lst = c.currentList()
        style = lst.format().style() if lst is not None else None
        self.b_bullets.setChecked(style == BULLET)
        self.b_numbers.setChecked(style == NUMBERED)
        self.style_btn.setText(dict((lv, label) for label, lv in STYLES).get(level, "Text"))

    # -- text from the app ----------------------------------------------------------------
    # Every insert is unformatted: a transcript after a bold word or a heading isn't bold or a
    # heading. A block made by insertText takes the block format it was split from, so new
    # paragraphs are made with insertBlock and plain formats instead.
    def _plain(self, c: QTextCursor, text: str):
        for i, para in enumerate(text.split("\n")):
            if i:
                c.insertBlock(QTextBlockFormat(), QTextCharFormat())
            if para:
                c.insertText(para, QTextCharFormat())

    def replace_all(self, text: str):
        """The page becomes `text` (one undo step)."""
        c = self.edit.textCursor()
        c.beginEditBlock()
        c.select(QTextCursor.Document)
        c.removeSelectedText()
        c.setBlockFormat(QTextBlockFormat())
        c.setCharFormat(QTextCharFormat())
        self._plain(c, text)
        c.endEditBlock()
        self.edit.setTextCursor(c)

    def append(self, text: str) -> int:
        """`text` as new paragraph(s) after what is there, trailing blank lines replaced by one
        empty line (one undo step). Returns where it starts."""
        head = len(self.toPlainText().rstrip())
        c = self.edit.textCursor()
        c.beginEditBlock()
        c.setPosition(head)
        c.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        c.removeSelectedText()
        if head:
            self._plain(c, "\n\n")
        start = c.position()
        self._plain(c, text)
        c.endEditBlock()
        self.edit.setTextCursor(c)
        return start

    def replace_from(self, pos: int, text: str):
        """Everything from `pos` to the end becomes `text` (a re-flowed transcript)."""
        c = self.edit.textCursor()
        c.beginEditBlock()
        c.setPosition(pos)
        c.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        c.removeSelectedText()
        self._plain(c, text)
        c.endEditBlock()
        self.edit.setTextCursor(c)

    def insert_at_cursor(self, text: str):
        """Dictated text at the page's cursor, replacing a selection, with a space between it and
        a word right before it."""
        c = self.edit.textCursor()
        c.beginEditBlock()
        c.removeSelectedText()
        doc, pos = self.edit.document(), c.position()
        before = doc.characterAt(pos - 1) if pos > 0 else ""
        text = text.strip()
        if before and not before.isspace() and before not in "\u2029(\"'":
            text = " " + text
        after = doc.characterAt(pos)
        if after and not after.isspace() and after not in "\u2029.,;:!?)":
            text += " "
        c.insertText(text, self.edit.currentCharFormat())   # typed text: the format at the cursor
        c.endEditBlock()
        self.edit.setTextCursor(c)
        self.edit.ensureCursorVisible()

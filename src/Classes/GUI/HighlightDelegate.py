import html
from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QPainter, QTextDocument, QTextOption, QFont
from PySide6.QtWidgets import QStyledItemDelegate, QLineEdit, QStyle



class HighlightDelegate(QStyledItemDelegate):
    ICON_SIZE = 32
    ITEM_HEIGHT = 36
    ICON_PADDING = 2
    TEXT_PADDING = 6


    def __init__(self, search_widget: QLineEdit, parent=None):
        super().__init__(parent)
        self.search_widget = search_widget
        self._current_query = ""


    def paint(self, painter: QPainter, option, index):
        data = index.data(Qt.UserRole)
        if not data:
            return super().paint(painter, option, index)

        self._current_query = self.search_widget.text().lower()
        
        painter.save()
        self._draw_background(painter, option)
        
        icon = data.get("icon")
        icon_rect, text_rect = self._get_layout_rects(option.rect, icon)

        if icon:
            icon.paint(painter, icon_rect)

        html_text = self._build_html(data, option)
        self._draw_text(painter, option, text_rect, html_text)
        painter.restore()


    def _draw_background(self, painter, option):
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())


    def _get_layout_rects(self, rect, icon):
        if icon:
            icon_rect = QRectF(
                rect.left() + self.ICON_PADDING,
                rect.top() + self.ICON_PADDING,
                self.ICON_SIZE,
                self.ICON_SIZE
            ).toRect()

            text_rect = QRectF(
                rect.left() + self.ICON_SIZE + self.TEXT_PADDING,
                rect.top(),
                rect.width() - self.ICON_SIZE - self.TEXT_PADDING,
                rect.height()
            )
        else:
            icon_rect = None
            text_rect = QRectF(rect)

        return icon_rect, text_rect


    def _draw_text(self, painter, option, rect, html_text):
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        
        text_option = QTextOption()
        text_option.setWrapMode(QTextOption.NoWrap)
        doc.setDefaultTextOption(text_option)
        
        doc.setHtml(html_text)
        doc.setTextWidth(2000)

        painter.translate(rect.topLeft())
        doc.drawContents(painter, QRectF(0, 0, 2000, self.ITEM_HEIGHT))


    def _build_html(self, data, option):
        name = f"{data['name']}: {data['appid']}"
        suffix = ""
        if not data.get("initialized", True):
            suffix = " - <span style='color:red'>[Not Initialized]</span>"

        query = self._current_query
        if not query:
            return html.escape(name) + suffix

        highlighted = self._highlight_text(name, query, option)
        return highlighted + suffix


    def _highlight_text(self, text, query, option):
        result = ""
        i = 0
        lower = text.lower()
        query_len = len(query)

        color = (
            option.palette.highlightedText().color().name()
            if option.state & QStyle.State_Selected
            else option.palette.text().color().name()
        )

        while i < len(text):
            if lower[i:i+query_len] == query:
                match = text[i:i+query_len]
                result += f"<span style='font-weight:bold;text-decoration:underline;color:{color}'>{html.escape(match)}</span>"
                i += query_len
            else:
                result += html.escape(text[i])
                i += 1

        return result


    def sizeHint(self, option, index):
        data = index.data(Qt.UserRole)
        if not data:
            return super().sizeHint(option, index)

        text = f"{data['name']}: {data['appid']}"
        width = option.fontMetrics.horizontalAdvance(text)
        total_width = width + self.ICON_SIZE + self.TEXT_PADDING + 10
        return QSize(total_width, self.ITEM_HEIGHT)
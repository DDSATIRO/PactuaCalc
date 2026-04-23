from __future__ import annotations

from pathlib import Path


PAGE_WIDTH = 842.0
PAGE_HEIGHT = 595.0
MARGIN_X = 24.0
MARGIN_Y = 20.0


class SimplePdf:
    def __init__(self) -> None:
        self.pages: list[list[str]] = []
        self.new_page()

    def new_page(self) -> None:
        self.current_page: list[str] = []
        self.pages.append(self.current_page)

    def _emit(self, command: str) -> None:
        self.current_page.append(command)

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        fill: tuple[float, float, float] | None = None,
        stroke: tuple[float, float, float] | None = (0, 0, 0),
        line_width: float = 1.0,
    ) -> None:
        commands: list[str] = ["q", f"{line_width:.2f} w"]
        if fill:
            commands.append(f"{fill[0]:.3f} {fill[1]:.3f} {fill[2]:.3f} rg")
        if stroke:
            commands.append(f"{stroke[0]:.3f} {stroke[1]:.3f} {stroke[2]:.3f} RG")
        commands.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re")
        if fill and stroke:
            commands.append("B")
        elif fill:
            commands.append("f")
        else:
            commands.append("S")
        commands.append("Q")
        self._emit("\n".join(commands))

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        color: tuple[float, float, float] = (0, 0, 0),
        line_width: float = 1.0,
    ) -> None:
        self._emit(
            f"q\n{line_width:.2f} w\n{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} RG\n"
            f"{x1:.2f} {y1:.2f} m\n{x2:.2f} {y2:.2f} l\nS\nQ"
        )

    def text(
        self,
        x: float,
        y: float,
        text: str,
        size: float = 10.0,
        font: str = "F1",
        color: tuple[float, float, float] = (0, 0, 0),
    ) -> None:
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        self._emit(
            "BT\n"
            f"/{font} {size:.2f} Tf\n"
            f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg\n"
            f"1 0 0 1 {x:.2f} {y:.2f} Tm\n"
            f"({escaped}) Tj\n"
            "ET"
        )

    def save(self, target: Path) -> Path:
        font_objects = {
            "F1": "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            "F2": "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
            "F3": "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique /Encoding /WinAnsiEncoding >>",
        }
        objects: list[bytes] = []

        def add_object(body: bytes) -> int:
            objects.append(body)
            return len(objects)

        font_refs = {name: add_object(defn.encode("ascii")) for name, defn in font_objects.items()}
        page_entries: list[int] = []
        for commands in self.pages:
            stream = "\n".join(commands).encode("cp1252", errors="replace")
            content_obj = add_object(
                b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"
            )
            page_obj = add_object(
                (
                    "<< /Type /Page /Parent PAGES_REF 0 R "
                    f"/MediaBox [0 0 {PAGE_WIDTH:.2f} {PAGE_HEIGHT:.2f}] "
                    f"/Resources << /Font << /F1 {font_refs['F1']} 0 R /F2 {font_refs['F2']} 0 R /F3 {font_refs['F3']} 0 R >> >> "
                    f"/Contents {content_obj} 0 R >>"
                ).encode("ascii")
            )
            page_entries.append(page_obj)

        pages_obj = add_object(
            ("<< /Type /Pages /Count %d /Kids [%s] >>" % (
                len(page_entries),
                " ".join(f"{page_obj} 0 R" for page_obj in page_entries),
            )).encode("ascii")
        )
        catalog_obj = add_object(f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode("ascii"))

        fixed_objects: list[bytes] = []
        for body in objects:
            if b"PAGES_REF" in body:
                body = body.replace(b"PAGES_REF", str(pages_obj).encode("ascii"))
            fixed_objects.append(body)

        output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for index, body in enumerate(fixed_objects, start=1):
            offsets.append(len(output))
            output.extend(f"{index} 0 obj\n".encode("ascii"))
            output.extend(body)
            output.extend(b"\nendobj\n")
        xref_pos = len(output)
        output.extend(f"xref\n0 {len(fixed_objects) + 1}\n".encode("ascii"))
        output.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
        output.extend(
            (
                f"trailer\n<< /Size {len(fixed_objects) + 1} /Root {catalog_obj} 0 R >>\n"
                f"startxref\n{xref_pos}\n%%EOF"
            ).encode("ascii")
        )
        target.write_bytes(bytes(output))
        return target


class ProposalPdfLayout:
    def __init__(self, pdf: SimplePdf) -> None:
        self.pdf = pdf
        self.cursor_y = PAGE_HEIGHT - MARGIN_Y

    def ensure_space(self, height: float) -> None:
        if self.cursor_y - height < MARGIN_Y:
            self.pdf.new_page()
            self.cursor_y = PAGE_HEIGHT - MARGIN_Y

    @staticmethod
    def estimate_width(text: str, font_size: float) -> float:
        return len(text) * font_size * 0.54

    def wrap(self, text: str, width: float, font_size: float) -> list[str]:
        words = text.split()
        if not words:
            return [""]
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            if self.estimate_width(trial, font_size) <= width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def block_title(self, title: str, fill: tuple[float, float, float], height: float = 18.0) -> None:
        self.ensure_space(height + 8)
        y = self.cursor_y - height
        self.pdf.rect(MARGIN_X, y, PAGE_WIDTH - (MARGIN_X * 2), height, fill=fill, stroke=(0.4, 0.4, 0.4))
        self.pdf.text(MARGIN_X + 6, y + 5, title, size=12, font="F2")
        self.cursor_y = y - 6

    def paragraph(
        self,
        text: str,
        size: float = 9.0,
        font: str = "F1",
        color: tuple[float, float, float] = (0, 0, 0),
        leading: float = 12.0,
        indent: float = 0.0,
        justify: bool = False,
    ) -> None:
        width = PAGE_WIDTH - (MARGIN_X * 2) - indent
        lines = self.wrap(text, width, size)
        self.ensure_space(len(lines) * leading + 2)
        for index, line in enumerate(lines):
            rendered = line
            if justify and index < len(lines) - 1:
                rendered = self.justified_text(line, width, size)
            self.pdf.text(MARGIN_X + indent, self.cursor_y - size, rendered, size=size, font=font, color=color)
            self.cursor_y -= leading

    def key_value_grid(self, items: list[tuple[str, str] | tuple[str, str, tuple[float, float, float]]]) -> None:
        col_width = (PAGE_WIDTH - (MARGIN_X * 2)) / 2
        row_height = 16
        extra_gap = 6
        self.ensure_space((((len(items) + 1) // 2) * row_height) + 6)
        x_positions = [MARGIN_X, MARGIN_X + col_width]
        for idx, item in enumerate(items):
            if len(item) == 3:
                label, value, value_color = item
            else:
                label, value = item
                value_color = (0, 0, 0)
            row = idx // 2
            col = idx % 2
            y = self.cursor_y - (row * row_height)
            label_text = f"{label}: "
            label_width = self.estimate_width(label_text, 9)
            self.pdf.text(x_positions[col], y - 10, label_text, size=9, font="F2")
            self.pdf.text(x_positions[col] + label_width + extra_gap, y - 10, value, size=9, font="F2" if value_color != (0,0,0) else "F1", color=value_color)
        self.cursor_y -= (((len(items) + 1) // 2) * row_height) + 4

    def justified_text(self, text: str, width: float, font_size: float) -> str:
        words = text.split()
        if len(words) < 2:
            return text
        current_width = self.estimate_width(" ".join(words), font_size)
        extra_width = max(width - current_width, 0)
        if extra_width <= 0:
            return text
        extra_spaces = int(extra_width / max(font_size * 0.30, 1))
        gaps = len(words) - 1
        if gaps <= 0 or extra_spaces <= 0:
            return text
        base_extra = extra_spaces // gaps
        remainder = extra_spaces % gaps
        chunks: list[str] = []
        for index, word in enumerate(words[:-1]):
            chunks.append(word)
            spaces = 1 + base_extra + (1 if index < remainder else 0)
            chunks.append(" " * spaces)
        chunks.append(words[-1])
        return "".join(chunks)

    def highlighted_total(self, label: str, value: str) -> None:
        box_height = 28
        self.ensure_space(box_height + 8)
        y = self.cursor_y - box_height
        self.pdf.rect(MARGIN_X, y, PAGE_WIDTH - (MARGIN_X * 2), box_height, fill=(0.89, 0.95, 0.87), stroke=(0.25, 0.45, 0.25))
        self.pdf.text(MARGIN_X + 8, y + 8, label, size=12, font="F2", color=(0.07, 0.32, 0.14))
        width = self.estimate_width(value, 16)
        self.pdf.text(PAGE_WIDTH - MARGIN_X - width - 8, y + 6, value, size=16, font="F2", color=(0.07, 0.32, 0.14))
        self.cursor_y = y - 8

    def callout(
        self,
        title: str,
        body: str,
        accent_text: str | None = None,
        fill: tuple[float, float, float] = (1.0, 0.96, 0.84),
        stroke: tuple[float, float, float] = (0.70, 0.50, 0.12),
        accent_first: bool = False,
        bottom_prefix: str | None = None,
        bottom_accent: str | None = None,
    ) -> None:
        title_lines = self.wrap(title, PAGE_WIDTH - (MARGIN_X * 2) - 16, 11)
        body_lines = self.wrap(body, PAGE_WIDTH - (MARGIN_X * 2) - 16, 10)
        accent_lines = self.wrap(accent_text or "", PAGE_WIDTH - (MARGIN_X * 2) - 16, 13) if accent_text else []
        content_height = 14 + (len(title_lines) * 14) + (len(body_lines) * 12) + (len(accent_lines) * 16) + (28 if bottom_prefix else 0) + 10
        self.ensure_space(content_height + 10)
        y = self.cursor_y - content_height
        self.pdf.rect(MARGIN_X, y, PAGE_WIDTH - (MARGIN_X * 2), content_height, fill=fill, stroke=stroke, line_width=1.2)
        line_y = self.cursor_y - 16
        if accent_first:
            for line in accent_lines:
                self.pdf.text(MARGIN_X + 8, line_y, line, size=13, font="F2", color=(0.76, 0.08, 0.08))
                line_y -= 16
        for line in title_lines:
            self.pdf.text(MARGIN_X + 8, line_y, line, size=11, font="F2", color=(0.33, 0.20, 0.02))
            line_y -= 14
        for line in body_lines:
            self.pdf.text(MARGIN_X + 8, line_y, line, size=10, font="F1", color=(0.20, 0.18, 0.16))
            line_y -= 12
        if not accent_first:
            for line in accent_lines:
                self.pdf.text(MARGIN_X + 8, line_y, line, size=13, font="F2", color=(0.76, 0.08, 0.08))
                line_y -= 16
        if bottom_prefix and bottom_accent:
            self.pdf.text(MARGIN_X + 8, line_y, bottom_prefix, size=11, font="F2", color=(0.20, 0.18, 0.16))
            line_y -= 14
            self.pdf.text(MARGIN_X + 24, line_y, bottom_accent, size=12, font="F2", color=(0.76, 0.08, 0.08))
            line_y -= 14
        self.cursor_y = y - 10

    def table(
        self,
        headers: list[str],
        rows: list[list[str]],
        widths: list[float],
        header_fill: tuple[float, float, float],
        row_fill: tuple[float, float, float] | None = None,
        font_size: float = 8.4,
        row_padding: float = 4.0,
        total_row_indices: set[int] | None = None,
    ) -> None:
        total_row_indices = total_row_indices or set()
        x_positions = [MARGIN_X]
        for width in widths[:-1]:
            x_positions.append(x_positions[-1] + width)

        def row_height(row: list[str], is_header: bool = False) -> float:
            max_lines = 1
            for text, width in zip(row, widths):
                wrapped = self.wrap(text, width - 6, font_size + (0.2 if is_header else 0.0))
                max_lines = max(max_lines, len(wrapped))
            return (max_lines * (font_size + 2.2)) + row_padding

        header_height = row_height(headers, is_header=True)
        all_row_heights = [row_height(row) for row in rows]
        self.ensure_space(header_height + sum(all_row_heights) + 6)

        current_y = self.cursor_y
        self.pdf.rect(MARGIN_X, current_y - header_height, sum(widths), header_height, fill=header_fill, stroke=(0.5, 0.5, 0.5))
        for x in x_positions[1:]:
            self.pdf.line(x, current_y, x, current_y - header_height, color=(0.6, 0.6, 0.6), line_width=0.6)
        for idx, header in enumerate(headers):
            wrapped = self.wrap(header, widths[idx] - 6, font_size + 0.2)
            line_y = current_y - 10
            for line in wrapped:
                self.pdf.text(x_positions[idx] + 3, line_y, line, size=font_size + 0.2, font="F2")
                line_y -= font_size + 2.2
        current_y -= header_height

        for row_index, (row, height) in enumerate(zip(rows, all_row_heights)):
            fill = (0.97, 0.97, 0.97) if row_index in total_row_indices else row_fill
            self.pdf.rect(MARGIN_X, current_y - height, sum(widths), height, fill=fill, stroke=(0.75, 0.75, 0.75), line_width=0.5)
            for x in x_positions[1:]:
                self.pdf.line(x, current_y, x, current_y - height, color=(0.82, 0.82, 0.82), line_width=0.4)
            for idx, cell in enumerate(row):
                wrapped = self.wrap(cell, widths[idx] - 6, font_size)
                line_y = current_y - 10
                font = "F2" if row_index in total_row_indices else "F1"
                for line in wrapped:
                    self.pdf.text(x_positions[idx] + 3, line_y, line, size=font_size, font=font)
                    line_y -= font_size + 2.2
            current_y -= height
        self.cursor_y = current_y - 6

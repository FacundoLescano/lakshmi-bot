import io
import os

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as pdfcanvas

# Template PDF — place it at chatbot/static/voucher_template.pdf
_HERE = os.path.dirname(__file__)
TEMPLATE_PATH = os.path.join(_HERE, "static", "voucher_template.pdf")

# Coordinates for overlay text (points from bottom-left of page).
# Adjust these if the text doesn't land exactly over the dotted lines.
PARA_X = 95    # x where the recipient name starts (after "Para ")
PARA_Y = 175   # y of the "Para / Código" row
CODIGO_X = 455 # x where the voucher code value starts (after "Código: ")


def _build_overlay(para_nombre: str, codigo: str) -> bytes:
    """Create a transparent PDF with only the dynamic text."""
    buffer = io.BytesIO()
    w, h = A4
    c = pdfcanvas.Canvas(buffer, pagesize=(w, h))

    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(colors.HexColor("#333333"))

    c.drawString(PARA_X, PARA_Y, para_nombre)
    c.drawString(CODIGO_X, PARA_Y, codigo)

    c.save()
    return buffer.getvalue()


def generate_voucher_pdf(para_nombre: str, codigo: str, duracion: int = 60, es_pareja: bool = False) -> bytes:
    """
    Overlay the recipient name and voucher code onto the template PDF.
    Returns the merged PDF as bytes.

    Place the template at: chatbot/static/voucher_template.pdf
    Adjust PARA_X, PARA_Y, CODIGO_X at the top of this file if positioning is off.
    """
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(
            f"Voucher template not found at {TEMPLATE_PATH}. "
            "Place the template PDF there and try again."
        )

    overlay_bytes = _build_overlay(para_nombre, codigo)

    template_reader = PdfReader(TEMPLATE_PATH)
    overlay_reader = PdfReader(io.BytesIO(overlay_bytes))

    writer = PdfWriter()
    page = template_reader.pages[0]
    page.merge_page(overlay_reader.pages[0])
    writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()

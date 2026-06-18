import io
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph

from reportlab.pdfgen import canvas as pdfcanvas

# Lakshmi brand blue (matching the PDF header color)
LAKSHMI_BLUE = colors.HexColor("#4BACC6")
DARK_GRAY = colors.HexColor("#333333")
MID_GRAY = colors.HexColor("#666666")

# Path to Lakshmi image — place the image at chatbot/static/lakshmi.jpg
_HERE = os.path.dirname(__file__)
LAKSHMI_IMAGE_PATH = os.path.join(_HERE, "static", "lakshmi.jpg")

DURATION_LABELS = {
    60: "1:00 hora",
    90: "1:30 horas",
    120: "2:00 horas",
}

VOUCHER_DESCRIPTIONS = {
    # (es_pareja, duracion): (title_line, ritual_name, body_right, body_full)
    (True, 90): (
        "VOUCHER PARA PAREJAS",
        "ritual prema",
        (
            "Iniciamos este ritual con un masaje corporal californiano relajante y descontracturante. "
            "El blend de aceites está compuesto por Sándalo y Patchouli, aromas que nos conectan con "
            "nuestro deseo, y una intención amorosa y bella hacia nosotros mismos o nuestra pareja. "
            "Es un ritual ideal para tomarlo en compañía de nuestro amor o solo/a antes de un "
            "encuentro o salida de pareja."
        ),
        (
            "El ritual se completa con un masaje reflexológico de pies con una fresca crema de menta "
            "para preparar tus pies para lo que viene. El ritual finaliza con un masaje vibracional."
        ),
    ),
    (False, 60): (
        "VOUCHER INDIVIDUAL",
        "masaje relajante",
        (
            "Un espacio de descanso y reconexión diseñado solo para vos. "
            "El blend de aceites está seleccionado para acompañar tu energía del momento, "
            "con aromas que invitan a soltar tensiones y conectar con tu centro. "
            "Ideal para regalar un momento de bienestar genuino."
        ),
        (
            "La sesión finaliza con un breve trabajo reflexológico en pies para cerrar el circuito "
            "energético y dejarte en un estado de plena calma."
        ),
    ),
    (False, 90): (
        "VOUCHER INDIVIDUAL",
        "ritual pleno",
        (
            "Iniciamos con un masaje corporal californiano relajante y descontracturante. "
            "El blend de aceites está compuesto por aromas que nos conectan con nuestro interior "
            "y promueven una profunda sensación de bienestar. "
            "Ideal para regalarse un momento de reconexión genuina."
        ),
        (
            "El ritual se completa con un masaje reflexológico de pies con crema de menta "
            "y finaliza con un masaje vibracional para integrar la experiencia."
        ),
    ),
    (False, 120): (
        "VOUCHER INDIVIDUAL",
        "masaje full",
        (
            "Una experiencia completa de relajación profunda que incluye masaje corporal californiano, "
            "trabajo con piedras calientes y aromaterapia personalizada. "
            "El tiempo extra permite un trabajo más profundo y consciente sobre cada zona del cuerpo."
        ),
        (
            "La sesión incluye reflexología de pies y cierra con un masaje vibracional. "
            "Una experiencia transformadora para regalar o regalarse."
        ),
    ),
    (True, 60): (
        "VOUCHER PARA PAREJAS",
        "ritual duo",
        (
            "Un espacio compartido de relajación y conexión para dos. "
            "El blend de aceites con aromas cálidos acompaña una experiencia de bienestar en pareja, "
            "ideal para reconectar y crear un momento especial juntos."
        ),
        (
            "La sesión finaliza con reflexología de pies para ambos, "
            "cerrando el ritual en un estado de calma y conexión compartida."
        ),
    ),
    (True, 120): (
        "VOUCHER PARA PAREJAS",
        "ritual prema full",
        (
            "La versión más completa de nuestro ritual en pareja. "
            "Masaje corporal californiano con blend de Sándalo y Patchouli, "
            "trabajo con piedras calientes y aromaterapia para dos. "
            "Una experiencia profunda de conexión y bienestar compartido."
        ),
        (
            "El ritual se completa con reflexología de pies con crema de menta "
            "y cierra con un masaje vibracional para integrar todo lo vivido juntos."
        ),
    ),
}

# Default fallback
_DEFAULT_DESC = (
    "VOUCHER LAKSHMI",
    "ritual lakshmi",
    (
        "Un espacio especial diseñado para el descanso, la reconexión y el bienestar. "
        "Nuestros terapeutas preparan cada sesión con aceites seleccionados y una intención "
        "personalizada para que la experiencia sea única y memorable."
    ),
    "El ritual finaliza con un masaje vibracional para integrar la experiencia.",
)


def _get_description(es_pareja: bool, duracion: int):
    return VOUCHER_DESCRIPTIONS.get((es_pareja, duracion), _DEFAULT_DESC)


def generate_voucher_pdf(para_nombre: str, codigo: str, duracion: int, es_pareja: bool) -> bytes:
    """
    Generate a voucher PDF matching the Lakshmi template design.
    Returns the PDF as bytes.
    """
    buffer = io.BytesIO()
    w, h = A4  # 595 x 842 points

    c = pdfcanvas.Canvas(buffer, pagesize=A4)

    # ── Voucher bounding box (dashed border) ─────────────────
    margin = 28
    box_x = margin
    box_y = 120
    box_w = w - 2 * margin
    box_h = h - box_y - margin

    c.setDash(4, 4)
    c.setStrokeColor(MID_GRAY)
    c.setLineWidth(0.8)
    c.rect(box_x, box_y, box_w, box_h)
    c.setDash()  # reset dash

    # ── Header: "Lakshmi [lotus] Masajes   (X:XX horas)" ─────
    duration_label = DURATION_LABELS.get(duracion, f"{duracion} min")
    header_y = box_y + box_h - 32

    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(LAKSHMI_BLUE)
    c.drawString(box_x + 14, header_y, "Lakshmi")
    lk_w = c.stringWidth("Lakshmi", "Helvetica-Bold", 18)

    # Lotus symbol between words
    c.setFont("Helvetica", 14)
    c.drawString(box_x + 14 + lk_w + 4, header_y, "✿")
    lotus_w = c.stringWidth("✿", "Helvetica", 14)

    c.setFont("Helvetica-Bold", 18)
    c.drawString(box_x + 14 + lk_w + 4 + lotus_w + 4, header_y, "Masajes")
    masajes_w = c.stringWidth("Masajes", "Helvetica-Bold", 18)

    # Duration in gray, right-aligned
    c.setFont("Helvetica", 11)
    c.setFillColor(MID_GRAY)
    dur_text = f"({duration_label})"
    dur_w = c.stringWidth(dur_text, "Helvetica", 11)
    c.drawString(box_x + box_w - 14 - dur_w, header_y, dur_text)

    # Thin horizontal line under header
    c.setStrokeColor(MID_GRAY)
    c.setLineWidth(0.5)
    c.line(box_x + 8, header_y - 8, box_x + box_w - 8, header_y - 8)

    # ── Content area ──────────────────────────────────────────
    content_top = header_y - 20
    title_line, ritual_name, body_right, body_full = _get_description(es_pareja, duracion)

    img_x = box_x + 10
    img_y = content_top - 145
    img_w = 140
    img_h = 140

    # Lakshmi image (optional — skip if file not found)
    if os.path.exists(LAKSHMI_IMAGE_PATH):
        c.drawImage(LAKSHMI_IMAGE_PATH, img_x, img_y, width=img_w, height=img_h,
                    preserveAspectRatio=True, mask="auto")
    else:
        # Placeholder box
        c.setFillColor(colors.HexColor("#F0F0F0"))
        c.rect(img_x, img_y, img_w, img_h, fill=1, stroke=0)

    # Right column for title + description
    right_x = img_x + img_w + 12
    right_w = box_x + box_w - right_x - 10
    text_top = content_top

    # "VOUCHER PARA PAREJAS" / "VOUCHER INDIVIDUAL"
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(DARK_GRAY)
    c.drawString(right_x, text_top, title_line)

    # Ritual name (large italic)
    c.setFont("Helvetica-Oblique", 22)
    c.setFillColor(DARK_GRAY)
    c.drawString(right_x, text_top - 24, ritual_name)

    # Description paragraph on the right
    style = ParagraphStyle(
        "desc",
        fontName="Helvetica",
        fontSize=7.5,
        leading=11,
        textColor=DARK_GRAY,
    )
    p = Paragraph(body_right, style)
    p.wrapOn(c, right_w, 120)
    p.drawOn(c, right_x, text_top - 24 - 10 - p.height)

    # ── Full-width body text ───────────────────────────────────
    full_text_y = img_y - 10
    full_style = ParagraphStyle(
        "full",
        fontName="Helvetica",
        fontSize=7.5,
        leading=11,
        textColor=DARK_GRAY,
    )
    p2 = Paragraph(body_full, full_style)
    available_w = box_w - 20
    p2.wrapOn(c, available_w, 60)
    p2.drawOn(c, box_x + 10, full_text_y - p2.height)

    # ── Reminder line ─────────────────────────────────────────
    reminder_y = full_text_y - p2.height - 10
    c.setFont("Helvetica", 6.5)
    c.setFillColor(MID_GRAY)
    reminder = (
        "*Recordá reservar tu masaje por WhatsApp: 11-5324-5088  "
        "— CANCELACIONES CON 24 HS DE ANTICIPACIÓN —"
    )
    c.drawCentredString(w / 2, reminder_y, reminder)

    # ── Para / Código row ────────────────────────────────────
    para_y = box_y + 52

    # "Para" label
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(LAKSHMI_BLUE)
    c.drawString(box_x + 14, para_y, "Para")
    para_label_w = c.stringWidth("Para", "Helvetica-Bold", 14)

    # Recipient name
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(DARK_GRAY)
    c.drawString(box_x + 14 + para_label_w + 6, para_y, para_nombre)
    name_w = c.stringWidth(para_nombre, "Helvetica-Bold", 14)

    # Dotted line between name and "Código"
    dot_x_start = box_x + 14 + para_label_w + 6 + name_w + 6
    codigo_label = "Código:"
    c.setFont("Helvetica-Bold", 14)
    codigo_label_w = c.stringWidth(codigo_label, "Helvetica-Bold", 14)
    codigo_value_w = c.stringWidth(codigo, "Helvetica-Bold", 14)
    dot_x_end = box_x + box_w - 14 - codigo_label_w - 8 - codigo_value_w - 4

    c.setStrokeColor(MID_GRAY)
    c.setDash(1, 3)
    c.setLineWidth(0.8)
    c.line(dot_x_start, para_y + 3, dot_x_end, para_y + 3)
    c.setDash()

    # "Código:" label
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(LAKSHMI_BLUE)
    c.drawString(box_x + box_w - 14 - codigo_label_w - 8 - codigo_value_w, para_y, codigo_label)

    # Código value
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(DARK_GRAY)
    c.drawString(box_x + box_w - 14 - codigo_value_w, para_y, codigo)

    # Horizontal separator above footer
    sep_y = box_y + 36
    c.setStrokeColor(MID_GRAY)
    c.setLineWidth(0.5)
    c.line(box_x + 8, sep_y, box_x + box_w - 8, sep_y)

    # ── Footer ─────────────────────────────────────────────────
    footer_y = box_y + 14

    # Pin icon substitute + address
    c.setFillColor(colors.HexColor("#C0392B"))
    c.circle(box_x + 22, footer_y + 5, 5, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(box_x + 22, footer_y + 3, "●")

    c.setFont("Helvetica", 7.5)
    c.setFillColor(DARK_GRAY)
    c.drawString(box_x + 32, footer_y + 7, "Nos encontramos en Fitz Roy 1925 - Piso 602")
    c.drawString(box_x + 32, footer_y - 1, "Palermo Hollywood, Buenos Aires")

    # Website (right side, large)
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(MID_GRAY)
    site = "www.lakshmimasajes.com"
    site_w = c.stringWidth(site, "Helvetica-Bold", 14)
    c.drawString(box_x + box_w - 14 - site_w, footer_y + 3, site)

    c.save()
    return buffer.getvalue()

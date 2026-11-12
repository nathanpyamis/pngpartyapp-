"""
Member ID card PDFs with WeasyPrint.

Photos and QR codes are embedded as data: URIs, so rendering never depends on
WeasyPrint fetching URLs (works the same with local media or private S3/R2).
"""
import base64
import io

import qrcode
from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from qrcode.image.pil import PilImage
from weasyprint import HTML

from .models import Member

CARD_W, CARD_H = 85.6, 54.0  # CR80, mm
A4_W, A4_H = 210.0, 297.0

# per_page -> (cols, rows, col_gap_mm, row_gap_mm)
BATCH_LAYOUTS = {
    10: (2, 5, 0.0, 0.0),   # edge-to-edge grid: one cut line between cards
    8:  (2, 4, 6.0, 8.0),   # gutters: easier to hand-cut and laminate
}


def _data_uri(raw: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def verify_url(member: Member) -> str:
    return f"{settings.PUBLIC_BASE_URL}/verify/{member.pk}/"


def qr_data_uri(text: str) -> str:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=1)
    qr.add_data(text)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(image_factory=PilImage).save(buf, format="PNG")
    return _data_uri(buf.getvalue(), "image/png")


def photo_data_uri(member: Member):
    if not member.photo:
        return None
    try:
        with member.photo.open("rb") as f:
            return _data_uri(f.read(), "image/jpeg")
    except (FileNotFoundError, OSError):
        return None


def card_context(member: Member) -> dict:
    return {
        "m": member,
        "province": member.electorate.province,
        "qr": qr_data_uri(verify_url(member)),
        "photo": photo_data_uri(member),
        "issued": timezone.localdate(),
    }


def batch_positions(per_page: int):
    cols, rows, cgap, rgap = BATCH_LAYOUTS[per_page]
    block_w = cols * CARD_W + (cols - 1) * cgap
    block_h = rows * CARD_H + (rows - 1) * rgap
    left0, top0 = (A4_W - block_w) / 2, (A4_H - block_h) / 2
    return [
        (round(left0 + c * (CARD_W + cgap), 2), round(top0 + r * (CARD_H + rgap), 2))
        for r in range(rows) for c in range(cols)
    ]


def render_cards_pdf(members, layout="single", per_page=10) -> bytes:
    cards = [card_context(m) for m in members]
    if layout == "single":
        html = render_to_string("members/idcard_single.html", {"cards": cards})
    else:
        positions = batch_positions(per_page)
        pages = []
        for i in range(0, len(cards), per_page):
            chunk = cards[i:i + per_page]
            pages.append([
                {**card, "left": positions[j][0], "top": positions[j][1]}
                for j, card in enumerate(chunk)
            ])
        html = render_to_string("members/idcard_batch.html", {
            "pages": pages, "per_page": per_page, "card_w": CARD_W, "card_h": CARD_H,
        })
    return HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()


def card_pdf_response(members, layout="single", per_page=10, filename="cards.pdf"):
    pdf = render_cards_pdf(members, layout=layout, per_page=per_page)
    now = timezone.now()
    Member.objects.filter(pk__in=[m.pk for m in members]).update(
        id_card_printed=True, id_card_printed_at=now
    )
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return resp

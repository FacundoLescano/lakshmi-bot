import logging
import os

import requests

logger = logging.getLogger(__name__)

WHATSAPP_API_URL = "https://graph.facebook.com/v21.0/{phone_id}/messages"
WHATSAPP_MEDIA_URL = "https://graph.facebook.com/v21.0/{phone_id}/media"


def send_interactive_buttons(to, body_text, buttons):
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    token = os.getenv("WHATSAPP_ACCESS_TOKEN")

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body_text},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": btn["id"], "title": btn["title"]},
                    }
                    for btn in buttons
                ]
            },
        },
    }

    response = requests.post(
        WHATSAPP_API_URL.format(phone_id=phone_id),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
    )
    if not response.ok:
        logger.error(
            "WhatsApp API error %s: %s (body_len=%d, buttons=%d)",
            response.status_code, response.text,
            len(body_text), len(buttons),
        )
    response.raise_for_status()
    return response.json()


def send_text_message(to, text):
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    token = os.getenv("WHATSAPP_ACCESS_TOKEN")

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }

    response = requests.post(
        WHATSAPP_API_URL.format(phone_id=phone_id),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
    )
    if not response.ok:
        logger.error("WhatsApp API error %s: %s", response.status_code, response.text)
    response.raise_for_status()
    return response.json()


def upload_media(pdf_bytes: bytes, filename: str) -> str:
    """Upload a PDF to WhatsApp Media API. Returns the media_id."""
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    token = os.getenv("WHATSAPP_ACCESS_TOKEN")

    response = requests.post(
        WHATSAPP_MEDIA_URL.format(phone_id=phone_id),
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (filename, pdf_bytes, "application/pdf")},
        data={"messaging_product": "whatsapp"},
    )
    if not response.ok:
        logger.error("WhatsApp Media upload error %s: %s", response.status_code, response.text)
    response.raise_for_status()
    return response.json()["id"]


def send_document_message(to: str, media_id: str, filename: str, caption: str = "") -> dict:
    """Send a previously uploaded document using its media_id."""
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    token = os.getenv("WHATSAPP_ACCESS_TOKEN")

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "document",
        "document": {
            "id": media_id,
            "filename": filename,
            "caption": caption,
        },
    }

    response = requests.post(
        WHATSAPP_API_URL.format(phone_id=phone_id),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
    )
    if not response.ok:
        logger.error("WhatsApp API error %s: %s", response.status_code, response.text)
    response.raise_for_status()
    return response.json()

import json
import logging
import os

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .whatsapp import send_interactive_buttons, send_text_message

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def webhook(request):
    if request.method == "GET":
        return verify_webhook(request)
    return handle_message(request)


def verify_webhook(request):
    mode = request.GET.get("hub.mode")
    token = request.GET.get("hub.verify_token")
    challenge = request.GET.get("hub.challenge")

    if mode == "subscribe" and token == os.getenv("WHATSAPP_VERIFY_TOKEN"):
        return HttpResponse(challenge, status=200)

    return HttpResponse("Forbidden", status=403)


def handle_message(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    entry = body.get("entry", [])
    if not entry:
        return HttpResponse("OK", status=200)

    changes = entry[0].get("changes", [])
    if not changes:
        return HttpResponse("OK", status=200)

    value = changes[0].get("value", {})
    messages = value.get("messages", [])
    if not messages:
        return HttpResponse("OK", status=200)

    message = messages[0]
    from_number = message["from"]
    msg_type = message.get("type")

    if msg_type == "text":
        send_interactive_buttons(
            to=from_number,
            body_text=(
                "Hola, gracias por contactarte con Lakshmi, "
                "hacemos todo tipo de masajes"
            ),
            buttons=[
                {"id": "btn_reserva", "title": "Reserva"},
                {"id": "btn_info", "title": "Más información"},
            ],
        )

    elif msg_type == "interactive":
        interactive = message.get("interactive", {})
        button_reply = interactive.get("button_reply", {})
        button_id = button_reply.get("id", "")

        if button_id == "btn_reserva":
            send_text_message(to=from_number, text="Reserva")
        elif button_id == "btn_info":
            send_text_message(to=from_number, text="Más información")

    return HttpResponse("OK", status=200)

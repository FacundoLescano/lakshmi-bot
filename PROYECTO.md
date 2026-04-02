# Lakshmi Bot — Documentación del Proyecto

## Descripción General

**Lakshmi Bot** es un chatbot de WhatsApp construido con Django que gestiona dos servicios principales:

1. **Lakshmi Masajes** — Sistema de reservas de masajes con gestión de horarios, camillas, sucursales, vouchers y regalos.
2. **Intencionate** — Servicio de bienestar emocional/espiritual con planes de suscripción y experiencias diarias generadas por IA.

El sistema recibe mensajes de WhatsApp mediante un webhook de la API de Meta, los procesa de forma asíncrona, y responde al usuario guiándolo por flujos conversacionales.

---

## Stack Tecnológico

| Componente | Tecnología |
|---|---|
| Backend framework | Django 6.0.3 |
| REST API | Django REST Framework 3.17.0 |
| Base de datos | SQLite (dev) / PostgreSQL (prod) |
| Cache de sesiones | Django Cache (tabla en DB) |
| CORS | django-cors-headers |
| LLM / IA | OpenAI API (gpt-4o-mini por defecto) |
| WhatsApp | Meta WhatsApp Cloud API v21.0 |
| Parseo de fechas | dateparser |
| Timezones | pytz / America/Argentina/Buenos_Aires |

---

## Estructura de Directorios

```
lakshmi-bot/
├── lakshmi/                    # Configuración principal del proyecto Django
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── chatbot/                    # App principal: webhook WhatsApp + lógica del bot
│   ├── models.py               # 4 modelos: Reserva, Memoria, Intencionate, Precio
│   ├── views.py                # Entry point del webhook y toda la lógica conversacional
│   ├── urls.py
│   ├── admin.py
│   ├── availability.py         # Lógica de disponibilidad de camillas y horarios
│   ├── conversation.py         # Gestión de sesiones en caché
│   ├── llm_router.py           # Clasificación de mensajes con OpenAI
│   ├── llm_chat.py             # Generación de respuestas con OpenAI
│   ├── intencionate.py         # Lógica del bot Intencionate
│   ├── whatsapp.py             # Wrapper de la API de WhatsApp
│   └── management/
│       └── commands/
│           ├── send_daily_messages.py       # Cron: mensajes matutinos
│           └── send_integration_messages.py # Cron: mensajes vespertinos
├── api/                        # App REST API para administración externa
│   ├── models.py               # (vacío, usa modelos de chatbot)
│   ├── views.py                # ViewSets CRUD
│   ├── serializers.py
│   ├── urls.py
│   └── admin.py
├── requirements.txt
├── .env                        # Variables de entorno
└── API.md                      # Documentación original de la API
```

---

## Variables de Entorno (.env)

```env
# WhatsApp Meta API
WHATSAPP_ACCESS_TOKEN=...
WHATSAPP_PHONE_NUMBER_ID=...
WHATSAPP_VERIFY_TOKEN=test123

# Django
DJANGO_SECRET_KEY=...
DEBUG=True

# Base de datos
DATABASE_URL=              # URL PostgreSQL (opcional, por defecto SQLite)

# OpenAI / LLM
OPENAI_API_KEY=...
OPENAI_BASE_URL=           # Opcional, para providers alternativos
OPENAI_MODEL=gpt-4o-mini
```

---

## URLs Principales

```
/admin/            → Panel de administración de Django
/webhook/          → Endpoint del webhook de WhatsApp (chatbot/)
/api/              → REST API (api/)
```

---

## App: `chatbot`

### Modelos (`chatbot/models.py`)

#### `Reserva`
Representa una reserva de masaje.

| Campo | Tipo | Descripción |
|---|---|---|
| `nombre` | CharField(200) | Nombre del cliente |
| `es_pareja` | BooleanField | Si es reserva doble |
| `duracion` | PositiveIntegerField | Duración en minutos: 60, 90 o 120 |
| `horario` | DateTimeField (nullable) | Fecha y hora del turno. `NULL` = regalo sin fecha asignada |
| `sucursal` | CharField (choices) | `sucursal_1`, `sucursal_2`, `sucursal_3` |
| `camilla` | PositiveSmallIntegerField (nullable) | Número de camilla (1-4 por sucursal) |
| `voucher` | CharField(20, unique) | Código de voucher único (hex de 8 chars) |
| `es_regalo` | BooleanField | Si fue comprada como regalo |
| `telefono` | CharField(20) | Teléfono del cliente (sin `+`, solo dígitos) |

**Constraint único:** `(horario, sucursal, camilla)` cuando los tres campos son no-nulos — evita doble booking.

---

#### `Memoria`
Almacena el contexto conversacional de cada usuario (respuestas al cuestionario, preferencias, etc.).

| Campo | Tipo | Descripción |
|---|---|---|
| `id_user` | CharField(20, indexed) | Teléfono del usuario |
| `context` | CharField(200) | Texto del mensaje o respuesta guardada |
| `reserva` | ForeignKey → Reserva (nullable) | Reserva asociada, si aplica |
| `created_at` | DateTimeField (auto) | Fecha de creación |

**Meta:** ordenado por `-created_at` (más reciente primero).

---

#### `Intencionate`
Representa una suscripción al servicio Intencionate.

| Campo | Tipo | Descripción |
|---|---|---|
| `nombre` | CharField(200) | Nombre del suscriptor |
| `lugar_nacimiento` | CharField(200) | Lugar de nacimiento |
| `fecha_nacimiento` | CharField(50) | Fecha de nacimiento (ej: `15/03/1990`) |
| `date` | DateTimeField (auto) | Fecha de alta en el sistema |
| `activo` | BooleanField | Si la suscripción está activa |
| `fecha_pago` | DateTimeField (nullable) | Fecha en que se verificó el pago |
| `tipo_plan` | CharField (choices) | `basico`, `intermedio`, `premium` |
| `hora_integrar` | CharField(10) | Hora para enviar mensajes diarios (ej: `"21"`) |
| `satisfaccion_cliente` | CharField(50) | Feedback del cliente |
| `telefono` | CharField (unique, indexed) | Teléfono del suscriptor |

**Meta:** ordenado por `-date`.

**Planes disponibles:**
| Plan | Precio | Experiencias diarias |
|---|---|---|
| Básico | $15.000 ARS | 1 |
| Intermedio | $25.000 ARS | 3 |
| Premium | $40.000 ARS | 5 |

---

#### `Precio`
Precios configurables por duración. Si no hay registro en la DB, se usan valores por defecto.

| Campo | Tipo | Descripción |
|---|---|---|
| `duracion` | PositiveIntegerField (unique) | 60, 90 o 120 minutos |
| `precio` | PositiveIntegerField | Precio en ARS |

**Método de clase `get_prices()`:** retorna `{60: X, 90: Y, 120: Z}`. Si no hay precios cargados, retorna `{60: 50000, 90: 65000, 120: 80000}`.

---

### Gestión de Sesiones (`chatbot/conversation.py`)

Las sesiones se almacenan en la **caché de Django** (tabla `django_cache`) con un timeout de **1 hora**.

```python
get_session(phone)         # Retorna dict o None
set_session(phone, data)   # Guarda/actualiza sesión
clear_session(phone)       # Elimina sesión
```

**Clave de caché:** `wa_session_{phone}`

**Estructura típica de sesión:**
```json
{
    "bot": "lakshmi",
    "step": "awaiting_horario",
    "pareja": false,
    "duracion": 60,
    "horario": "2026-04-05T15:00:00",
    "nombre": "Juan Pérez",
    "es_regalo": false,
    "reserva_ids": [42]
}
```

---

### Sistema de Disponibilidad (`chatbot/availability.py`)

**Constantes:**
- Horario de atención: 9:00 a 23:00 hs
- Camillas por sucursal: 4
- 3 sucursales → 12 camillas en total

**Funciones principales:**

| Función | Descripción |
|---|---|
| `is_available(dt)` | `True` si existe al menos una camilla libre en ese `datetime` |
| `get_free_camillas(dt)` | Lista de `(sucursal, camilla)` libres para ese horario |
| `get_consecutive_pairs(dt)` | Pares de camillas consecutivas libres (para reservas de pareja) |
| `assign_camilla(dt, pareja)` | Asigna aleatoriamente una o un par de camillas. Lanza `ValueError` si no hay disponibilidad |
| `suggest_alternatives(dt, pareja)` | Sugiere hasta 2 horarios alternativos (±1h, ±2h) dentro del horario de atención |

**Lógica de disponibilidad:**
- La disponibilidad se determina restando las reservas existentes del pool total de camillas.
- Si no hay camillas libres en el horario solicitado, se sugieren alternativas.

---

### LLM Router (`chatbot/llm_router.py`)

Clasifica cada mensaje entrante cuando el usuario no tiene sesión activa.

```python
route_message(text: str) → "lakshmi" | "intencionate" | "saludo"
```

Usa la API de OpenAI con un system prompt que instruye la clasificación en 3 categorías. Si no puede determinar la intención, retorna `"saludo"`.

---

### LLM Chat (`chatbot/llm_chat.py`)

Genera respuestas personalizadas para el servicio Intencionate.

| Función | Descripción | Temperatura |
|---|---|---|
| `generate_daily_message(user_info, memories)` | Mensaje matutino motivacional personalizado | 0.8 |
| `deepen_message(original_message, user_info, memories)` | Profundiza el mensaje diario con más insights | 0.8 |
| `chat_response(user_message, user_info, memories)` | Responde al texto libre del usuario con tono empático | 0.8 |
| `generate_integration_message(user_info, memories)` | Mensaje vespertino de integración | 0.8 |

Todos usan contexto del usuario: `nombre`, `fecha_nacimiento`, `lugar_nacimiento` + historial de memorias.

---

### WhatsApp API Wrapper (`chatbot/whatsapp.py`)

**Endpoint base:** `https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages`

| Función | Tipo de mensaje | Descripción |
|---|---|---|
| `send_text_message(to, text)` | `text` | Envía texto plano |
| `send_interactive_buttons(to, body_text, buttons)` | `interactive → button` | Envía hasta 3 botones interactivos |

**Formato de botones:**
```python
buttons = [
    {"id": "btn_reserva", "title": "Reservar"},
    {"id": "btn_voucher", "title": "Tengo un voucher"},
    {"id": "btn_cambiar", "title": "Cambiar horario"},
]
```

**Limitación de WhatsApp:** máximo 3 botones por mensaje.

---

### Flujos Conversacionales del Bot

#### Flujo Principal: Reserva

```
Usuario envía mensaje
    └── Sin sesión → LLM clasifica → "lakshmi"
        └── send_welcome() → Menú de 3 botones

[Reservar]
    └── ¿Es pareja? (si/no)
        └── ¿Duración? (60/90/120 min)
            └── ¿Es regalo? (si/no)
                ├── [Regalo = SÍ]
                │   └── Nombre del destinatario
                │       └── Mostrar CBU para pago
                │           └── Usuario sube comprobante (imagen/doc)
                │               └── Crear Reserva(es_regalo=True, horario=NULL)
                │                   └── Generar y enviar voucher
                │
                └── [Regalo = NO]
                    └── Ingresar horario (lenguaje natural)
                        └── Verificar disponibilidad
                            ├── [No disponible] → Sugerir alternativas
                            └── [Disponible] → Asignar camilla
                                └── Nombre del cliente
                                    └── Confirmar reserva (resumen)
                                        └── Guardar Reserva(s)
                                            └── Mostrar CBU para pago
                                                └── Ofrecer cuestionario Intencionate
```

#### Flujo: Cambiar Horario

```
[Cambiar horario]
    └── Buscar reservas activas del teléfono
        ├── [1 reserva] → Continuar directamente
        └── [2+ reservas] → Mostrar botones para elegir
            └── Ingresar nuevo horario
                └── Verificar disponibilidad → Asignar camilla
                    └── Actualizar Reserva(horario, sucursal, camilla)
```

#### Flujo: Voucher

```
[Tengo un voucher]
    └── Ingresar código
        └── Buscar Reserva(voucher=código, horario__isnull=True)
            ├── [No encontrado] → Error
            └── [Encontrado] → Cargar duracion, pareja del voucher
                └── Ingresar horario → Verificar → Asignar camilla
                    └── Actualizar Reserva(horario, sucursal, camilla)
```

#### Flujo: Suscripción Intencionate

```
Usuario → LLM clasifica → "intencionate"
    └── send_welcome_intencionate() → Mostrar planes
        └── ¿Suscribir? (si/no)
            └── [SÍ]
                ├── [Ya completó cuestionario en flujo masaje] → Ir a planes
                └── [No tiene datos] → Cuestionario completo:
                    1. Nombre
                    2. Lugar de nacimiento
                    3. Fecha de nacimiento
                    4-9. 6 preguntas emocionales
                    └── Seleccionar plan (Básico/Intermedio/Premium)
                        └── Mostrar CBU → Usuario sube comprobante
                            └── Crear Intencionate(activo=True)
```

#### Cuestionario de Intencionate (8 preguntas)

1. ¿Cuál es tu lugar de nacimiento?
2. ¿Cuál es tu fecha de nacimiento? (ej: 15/03/1990)
3. ¿Qué estás atravesando hoy?
4. ¿Qué es lo que más te mueve o te preocupa de esto?
5. ¿Cómo te estás sintiendo frente a esto?
6. ¿Dónde lo sentís en el cuerpo?
7. ¿Cómo está tu energía hoy?
8. Si esto se ordenara, ¿qué te gustaría que pase?

#### Flujo: Experiencia Diaria Intencionate

```
Cron 8am → send_daily_messages
    └── Para cada Intencionate(activo=True):
        └── generate_daily_message(user_info, memorias)
            └── Enviar mensaje + opciones [Profundizar] [Finalizar]

Usuario responde
    └── Verificar límite diario según plan (1/3/5 experiencias)
        ├── [Límite alcanzado] → Informar
        └── [Disponible] → chat_response() → Enviar respuesta
            └── Guardar en Memoria
                └── Opciones: [Profundizar] → deepen_message()
```

#### Panel Admin (via WhatsApp)

Acceso enviando el texto exacto: **`"Usuario admin intencionate 27326"`**

**Funciones:**
1. **Cancelar Reserva** → Busca por teléfono → Elige reserva → Elimina de DB → Notifica al cliente
2. **Modificar Precios** → Muestra precios actuales → Elige duración (60/90/120) → Ingresa nuevo precio → `Precio.objects.update_or_create()`

---

### Webhook Entry Point (`chatbot/views.py`)

```
GET /webhook/
    └── Verificación de Meta: comprueba hub.verify_token

POST /webhook/
    └── Parsear JSON body
        └── Extraer from_number (normalizado)
            └── Thread asíncrono: process_message()
                └── Retorna 200 OK inmediatamente (requerido por Meta en < 10s)
```

**Lógica de `process_message()`:**
```
¿Tiene sesión activa?
    ├── SÍ → Rutear al bot correcto (lakshmi / intencionate)
    └── NO
        ├── ¿Botón interactivo? → Manejar botones de enrutamiento
        └── ¿Texto? → LLM route_message() → Iniciar bot correspondiente
```

---

## App: `api`

### Endpoints REST

**Base:** `/api/`

Todos los endpoints usan `AllowAny` — **no requieren autenticación**.

---

#### Reservas — `/api/reservas/`

**`GET /api/reservas/`** — Listar reservas
```json
Response 200:
[
    {
        "id": 1,
        "nombre": "Juan Pérez",
        "es_pareja": false,
        "duracion": 60,
        "horario": "2026-04-05T15:00:00",
        "sucursal": "sucursal_1",
        "camilla": 2,
        "voucher": "a3f9c1b2",
        "es_regalo": false,
        "telefono": "5491123456789",
        "memorias": [
            {"id": 5, "id_user": "5491123456789", "context": "Juan", "reserva": 1, "created_at": "..."}
        ]
    }
]
```

**`POST /api/reservas/`** — Crear reserva
```json
Request body:
{
    "nombre": "María García",
    "es_pareja": true,
    "duracion": 90,
    "horario": "2026-04-10T18:00:00",
    "sucursal": "sucursal_2",
    "camilla": 1,
    "voucher": "b2e8d4a1",
    "es_regalo": false,
    "telefono": "5491198765432"
}

Response 201:
{ ...objeto creado... }
```

**`GET /api/reservas/{id}/`** — Detalle de una reserva

**`PUT/PATCH /api/reservas/{id}/`** — Actualizar reserva

**`DELETE /api/reservas/{id}/`** — Eliminar reserva

---

#### Memorias — `/api/memorias/`

**`GET /api/memorias/`** — Listar memorias (orden: `-id`)
```json
Response 200:
[
    {
        "id": 10,
        "id_user": "5491123456789",
        "context": "Cuál es tu lugar de nacimiento? → Buenos Aires",
        "reserva": 1,
        "created_at": "2026-04-02T10:30:00"
    }
]
```

**`POST /api/memorias/`** — Crear memoria
```json
Request body:
{
    "id_user": "5491123456789",
    "context": "Texto del contexto a guardar",
    "reserva": null
}
```

**`GET/PUT/PATCH/DELETE /api/memorias/{id}/`** — Operaciones por ID

---

#### Intencionate — `/api/intencionate/`

**`GET /api/intencionate/`** — Listar suscripciones (orden: `-date`)
```json
Response 200:
[
    {
        "id": 3,
        "nombre": "Ana López",
        "lugar_nacimiento": "Córdoba",
        "fecha_nacimiento": "15/03/1990",
        "date": "2026-04-01T09:00:00",
        "activo": true,
        "fecha_pago": "2026-04-01T10:00:00",
        "tipo_plan": "intermedio",
        "hora_integrar": "21",
        "satisfaccion_cliente": "",
        "telefono": "5491155443322"
    }
]
```

**`POST /api/intencionate/`** — Crear suscripción
```json
Request body:
{
    "nombre": "Carlos Rodríguez",
    "lugar_nacimiento": "Rosario",
    "fecha_nacimiento": "20/07/1985",
    "activo": true,
    "tipo_plan": "basico",
    "hora_integrar": "21",
    "telefono": "5491177889900"
}
```

**`GET/PUT/PATCH/DELETE /api/intencionate/{id}/`** — Operaciones por ID

---

#### Precios — `/api/precios/`

**`GET /api/precios/`** — Listar precios (orden: `duracion`)
```json
Response 200:
[
    {"id": 1, "duracion": 60, "precio": 50000},
    {"id": 2, "duracion": 90, "precio": 65000},
    {"id": 3, "duracion": 120, "precio": 80000}
]
```

**`POST /api/precios/`** — Crear precio
```json
Request body:
{
    "duracion": 60,
    "precio": 55000
}
```

**`GET/PUT/PATCH/DELETE /api/precios/{id}/`** — Operaciones por ID

---

## Commands de Management

### `send_daily_messages`
```bash
python manage.py send_daily_messages
```
Consulta todos los `Intencionate(activo=True)` y envía el mensaje matutino generado por LLM. Diseñado para ejecutarse a las 8am con un cron job.

### `send_integration_messages`
```bash
python manage.py send_integration_messages
```
Envía el mensaje vespertino de integración. Diseñado para ejecutarse en la tarde (hora configurable por suscriptor en `hora_integrar`).

---

## Arquitectura de Sesiones y Estado

El bot es **stateless** en cada request — todo el estado de la conversación vive en la caché de Django.

```
Request WhatsApp
    ↓
webhook() → Thread async
    ↓
get_session(phone) → dict con step actual
    ↓
Función handler correspondiente (handle_horario, handle_nombre, etc.)
    ↓
set_session(phone, nuevo_estado)
    ↓
send_text_message() o send_interactive_buttons()
```

**Timeout de sesión:** 1 hora de inactividad → sesión limpiada → próximo mensaje inicia flujo desde cero.

---

## Setup Inicial

```bash
# Instalar dependencias
pip install -r requirements.txt

# Migraciones
python manage.py migrate

# Crear tabla de caché (obligatorio)
python manage.py createcachetable

# Levantar servidor
python manage.py runserver
```

---

## Notas Importantes

- **Pago:** Los datos bancarios (CBU, titular) son placeholders (`0000000000000000000000`) y deben configurarse antes de producción.
- **Sin autenticación en API:** Todos los endpoints REST son públicos (`AllowAny`). Se recomienda agregar autenticación antes de exponer en producción.
- **Race condition:** No hay transaction locking en la asignación de camillas. Si dos usuarios intentan reservar la misma camilla simultáneamente, es posible un conflicto. La constraint `unique_together` en `Reserva` lo detectará a nivel DB pero no está manejado gracefully.
- **Procesamiento asíncrono:** El webhook lanza un thread por cada mensaje y retorna 200 inmediatamente. Esto cumple el requisito de Meta (respuesta < 10s) pero no usa una cola de tareas robusta (Celery, etc.).
- **Timezone:** Todo el sistema opera en `America/Argentina/Buenos_Aires` con `USE_TZ = False` en Django.
- **Botones WhatsApp:** Límite de 3 por mensaje. Cuando hay más de 3 reservas para mostrar, solo se muestran las primeras 3.

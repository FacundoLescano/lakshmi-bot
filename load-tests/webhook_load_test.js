/**
 * k6 Load Test — Lakshmi Bot (WhatsApp Webhook)
 *
 * Objetivo: determinar cuántos usuarios concurrentes soporta el bot
 *           en un VPS de 2 GB de RAM corriendo Django + Gunicorn.
 *
 * Uso:
 *   # Test de rampa (recomendado para encontrar el límite)
 *   k6 run webhook_load_test.js
 *
 *   # Apuntando a un host distinto
 *   k6 run -e BASE_URL=http://TU_VPS_IP:8000 webhook_load_test.js
 *
 *   # Solo el escenario de smoke (1 VU, 30 s)
 *   k6 run --env SCENARIO=smoke webhook_load_test.js
 *
 *   # Solo el escenario de breakpoint (rampa agresiva hasta 300 VU)
 *   k6 run --env SCENARIO=breakpoint webhook_load_test.js
 *
 * Instalar k6: https://k6.io/docs/get-started/installation/
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";
import { randomIntBetween } from "https://jslib.k6.io/k6-utils/1.4.0/index.js";

// ─── Configuración ────────────────────────────────────────────────────────────

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const SCENARIO  = __ENV.SCENARIO  || "ramp"; // smoke | ramp | soak | breakpoint

// ─── Métricas personalizadas ──────────────────────────────────────────────────

const webhookErrors   = new Counter("webhook_errors");
const webhookOkRate   = new Rate("webhook_ok_rate");
const webhookDuration = new Trend("webhook_duration_ms", true);
const apiDuration     = new Trend("api_duration_ms", true);

// ─── Escenarios ───────────────────────────────────────────────────────────────

const SCENARIOS = {
  /**
   * Smoke: verifica que el bot responde correctamente con carga mínima.
   * 1 VU durante 30 s.
   */
  smoke: {
    smoke: {
      executor: "constant-vus",
      vus: 1,
      duration: "30s",
    },
  },

  /**
   * Ramp: sube gradualmente para encontrar el punto de saturación.
   * Perfecto para un VPS de 2 GB — empieza suave y va aumentando.
   *
   * Patrón:
   *  0 →  2 min: 0  → 10 VU  (calentamiento)
   *  2 →  5 min: 10 → 50 VU  (carga normal esperada)
   *  5 →  8 min: 50 → 100 VU (carga alta)
   *  8 → 11 min: 100 → 150 VU (estrés)
   * 11 → 13 min: 150 → 0 VU  (enfriamiento)
   */
  ramp: {
    ramp: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "2m",  target: 10  },
        { duration: "3m",  target: 50  },
        { duration: "3m",  target: 100 },
        { duration: "3m",  target: 150 },
        { duration: "2m",  target: 0   },
      ],
      gracefulRampDown: "30s",
    },
  },

  /**
   * Soak: carga sostenida para detectar memory leaks y degradación.
   * 40 VU durante 20 minutos (carga realista para un VPS de 2 GB).
   */
  soak: {
    soak: {
      executor: "constant-vus",
      vus: 40,
      duration: "20m",
    },
  },

  /**
   * Breakpoint: rampa agresiva hasta encontrar el límite absoluto.
   * Sube hasta 300 VU en 10 minutos.
   * ⚠️  Puede tumbar el servidor — usar solo en entorno controlado.
   */
  breakpoint: {
    breakpoint: {
      executor: "ramping-arrival-rate",
      startRate: 1,
      timeUnit: "1s",
      preAllocatedVUs: 50,
      maxVUs: 300,
      stages: [
        { duration: "2m",  target: 10  },
        { duration: "3m",  target: 50  },
        { duration: "3m",  target: 100 },
        { duration: "2m",  target: 200 },
      ],
    },
  },
};

export const options = {
  scenarios: SCENARIOS[SCENARIO],

  thresholds: {
    // El webhook debe responder en < 2 s el 95% de las veces
    // (recuerda que devuelve 200 de inmediato y procesa en thread)
    webhook_duration_ms: ["p(95)<2000", "p(99)<5000"],

    // API REST: < 3 s el 95% de las veces
    api_duration_ms: ["p(95)<3000"],

    // Menos del 5% de errores HTTP
    webhook_ok_rate: ["rate>0.95"],

    // http_req_failed es el failsafe global de k6
    http_req_failed: ["rate<0.05"],
  },
};

// ─── Payloads de WhatsApp ─────────────────────────────────────────────────────

/**
 * Genera un número de teléfono argentino simulado único por VU.
 */
function fakePhone(vuId) {
  // Formato: 54911XXXXXXXX  (11 dígitos después de 54)
  const base = 90000000 + (vuId % 10000000);
  return `5491${base}`;
}

/**
 * Payload de mensaje de texto (el más común).
 */
function textMessagePayload(phone, text) {
  return JSON.stringify({
    object: "whatsapp_business_account",
    entry: [
      {
        id: "ENTRY_ID",
        changes: [
          {
            value: {
              messaging_product: "whatsapp",
              metadata: {
                display_phone_number: "5491187654321",
                phone_number_id: "PHONE_NUMBER_ID",
              },
              messages: [
                {
                  from: phone,
                  id: `wamid.${Date.now()}_${Math.random().toString(36).slice(2)}`,
                  timestamp: Math.floor(Date.now() / 1000).toString(),
                  type: "text",
                  text: { body: text },
                },
              ],
            },
            field: "messages",
          },
        ],
      },
    ],
  });
}

/**
 * Payload de respuesta a botón interactivo.
 */
function buttonReplyPayload(phone, buttonId, buttonTitle) {
  return JSON.stringify({
    object: "whatsapp_business_account",
    entry: [
      {
        id: "ENTRY_ID",
        changes: [
          {
            value: {
              messaging_product: "whatsapp",
              metadata: {
                display_phone_number: "5491187654321",
                phone_number_id: "PHONE_NUMBER_ID",
              },
              messages: [
                {
                  from: phone,
                  id: `wamid.${Date.now()}_${Math.random().toString(36).slice(2)}`,
                  timestamp: Math.floor(Date.now() / 1000).toString(),
                  type: "interactive",
                  interactive: {
                    type: "button_reply",
                    button_reply: {
                      id: buttonId,
                      title: buttonTitle,
                    },
                  },
                },
              ],
            },
            field: "messages",
          },
        ],
      },
    ],
  });
}

/**
 * Flujos de conversación simulados.
 * Cada array representa los mensajes que envía un usuario típico.
 */
const CONVERSATION_FLOWS = [
  // Flujo 1: consulta de reserva simple
  [
    (phone) => textMessagePayload(phone, "hola"),
    (phone) => textMessagePayload(phone, "quiero reservar un masaje"),
    (phone) => textMessagePayload(phone, "mañana a las 15"),
    (phone) => buttonReplyPayload(phone, "dur_60", "60 minutos"),
  ],
  // Flujo 2: consulta de precios
  [
    (phone) => textMessagePayload(phone, "hola"),
    (phone) => textMessagePayload(phone, "cuánto cuesta el masaje"),
  ],
  // Flujo 3: Intencionate
  [
    (phone) => textMessagePayload(phone, "hola"),
    (phone) => textMessagePayload(phone, "quiero saber del intencionate"),
  ],
  // Flujo 4: mensaje ambiguo (routing LLM)
  [
    (phone) => textMessagePayload(phone, "necesito ayuda"),
  ],
  // Flujo 5: solo texto de bienvenida
  [
    (phone) => textMessagePayload(phone, "buenos días"),
  ],
];

// ─── Headers comunes ──────────────────────────────────────────────────────────

const WEBHOOK_HEADERS = {
  "Content-Type": "application/json",
  // Meta suele enviar este header; Django no lo verifica por defecto
  // pero tenerlo hace la simulación más realista
  "X-Hub-Signature-256": "sha256=fakesignature",
};

const API_HEADERS = {
  "Content-Type": "application/json",
  Accept: "application/json",
};

// ─── Función principal (VU loop) ──────────────────────────────────────────────

export default function () {
  const phone = fakePhone(__VU);

  // Elegir un flujo de conversación aleatoriamente
  const flow = CONVERSATION_FLOWS[randomIntBetween(0, CONVERSATION_FLOWS.length - 1)];

  // ── 1. Enviar cada mensaje del flujo ──────────────────────────────────────
  for (const buildPayload of flow) {
    const payload = buildPayload(phone);

    const res = http.post(`${BASE_URL}/webhook/`, payload, {
      headers: WEBHOOK_HEADERS,
      timeout: "10s",
    });

    webhookDuration.add(res.timings.duration);

    const ok = check(res, {
      "webhook status 200": (r) => r.status === 200,
      "webhook body OK":    (r) => r.body === "OK" || r.body.includes("OK"),
    });

    webhookOkRate.add(ok);
    if (!ok) {
      webhookErrors.add(1);
      console.error(`[VU ${__VU}] Webhook error: ${res.status} — ${res.body.slice(0, 200)}`);
    }

    // Pausa entre mensajes del mismo usuario (simula tiempo de escritura)
    sleep(randomIntBetween(1, 3));
  }

  // ── 2. Ocasionalmente consultar la API REST ────────────────────────────────
  // Solo 1 de cada 5 VUs consulta la API en cada iteración
  if (__VU % 5 === 0) {
    const apiRes = http.get(`${BASE_URL}/api/reservas/`, {
      headers: API_HEADERS,
      timeout: "10s",
    });

    apiDuration.add(apiRes.timings.duration);

    check(apiRes, {
      "api reservas status 200": (r) => r.status === 200,
      "api reservas json":        (r) => {
        try { JSON.parse(r.body); return true; } catch { return false; }
      },
    });
  }

  // Pausa entre iteraciones del mismo VU (simula tiempo entre conversaciones)
  sleep(randomIntBetween(2, 5));
}

// ─── Setup: verificar que el servidor responde ────────────────────────────────

export function setup() {
  console.log(`\n🚀 Iniciando load test contra: ${BASE_URL}`);
  console.log(`   Escenario: ${SCENARIO}\n`);

  // Verificar que el webhook responde al GET de verificación
  const verifyRes = http.get(
    `${BASE_URL}/webhook/?hub.mode=subscribe&hub.verify_token=test123&hub.challenge=CHALLENGE_123`
  );

  if (verifyRes.status !== 200) {
    console.warn(
      `⚠️  El endpoint de verificación retornó ${verifyRes.status}. ` +
      `Asegurate de que WHATSAPP_VERIFY_TOKEN=test123 en .env`
    );
  } else {
    console.log("✅ Verificación de webhook OK");
  }

  // Verificar API
  const apiRes = http.get(`${BASE_URL}/api/reservas/`, { headers: API_HEADERS });
  if (apiRes.status === 200) {
    console.log("✅ API REST OK");
  } else {
    console.warn(`⚠️  API REST retornó ${apiRes.status}`);
  }

  return { baseUrl: BASE_URL };
}

// ─── Teardown: resumen final ──────────────────────────────────────────────────

export function teardown(data) {
  console.log(`\n✅ Test finalizado contra ${data.baseUrl}`);
  console.log("   Revisá el resumen de métricas arriba para determinar el límite de usuarios.");
  console.log("\n   Indicadores clave:");
  console.log("   • webhook_ok_rate > 95%  → el servidor está respondiendo bien");
  console.log("   • webhook_duration_ms p(95) < 2000 ms → latencia aceptable");
  console.log("   • Si ves errores 502/503/504 → el servidor está saturado");
  console.log("   • Monitorear RAM con: watch -n1 free -h  (en el VPS)");
}

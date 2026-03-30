# Load Tests — Lakshmi Bot

Tests de carga con [k6](https://k6.io) para determinar cuántos usuarios concurrentes
soporta el bot en un VPS de **2 GB de RAM**.

## Instalación de k6

```bash
# Ubuntu/Debian
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
  --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
  | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install k6

# macOS
brew install k6
```

## Cómo correr los tests

Asegurate de tener el servidor corriendo:

```bash
# En el VPS (o local)
gunicorn lakshmi.wsgi:application --bind 0.0.0.0:8000 --workers 4
# o simplemente:
python manage.py runserver 0.0.0.0:8000
```

### Smoke test (1 VU, 30 s) — verificar que todo funciona

```bash
k6 run --env SCENARIO=smoke --env BASE_URL=http://TU_VPS_IP:8000 webhook_load_test.js
```

### Ramp test (0 → 150 VU en 13 min) — encontrar el punto de saturación

```bash
k6 run --env SCENARIO=ramp --env BASE_URL=http://TU_VPS_IP:8000 webhook_load_test.js
```

### Soak test (40 VU × 20 min) — detectar memory leaks

```bash
k6 run --env SCENARIO=soak --env BASE_URL=http://TU_VPS_IP:8000 webhook_load_test.js
```

### Breakpoint test (rampa agresiva hasta 300 VU) — límite absoluto

> ⚠️ Puede tumbar el servidor. Usar solo en entorno de pruebas.

```bash
k6 run --env SCENARIO=breakpoint --env BASE_URL=http://TU_VPS_IP:8000 webhook_load_test.js
```

### Exportar resultados a JSON

```bash
k6 run --env SCENARIO=ramp \
       --env BASE_URL=http://TU_VPS_IP:8000 \
       --out json=results.json \
       webhook_load_test.js
```

## Monitoreo en el VPS mientras corre el test

Abrí otra terminal en el VPS y ejecutá:

```bash
# RAM en tiempo real
watch -n1 free -h

# CPU + procesos
htop

# Conexiones activas al puerto 8000
watch -n1 "ss -s && echo '---' && ss -tn state established '( dport = :8000 )' | wc -l"

# Logs de Gunicorn/Django
tail -f /var/log/gunicorn/error.log
```

## Qué significan los resultados

| Métrica | Umbral saludable | Señal de alerta |
|---|---|---|
| `webhook_ok_rate` | > 95 % | < 90 % → saturación |
| `webhook_duration_ms p(95)` | < 2 000 ms | > 5 000 ms → cuello de botella |
| `http_req_failed` | < 5 % | > 10 % → el servidor cae |
| RAM libre en VPS | > 400 MB | < 200 MB → riesgo de OOM kill |

## Expectativas para un VPS de 2 GB

Con Django + Gunicorn en 2 GB RAM, la configuración típica es:

| Workers Gunicorn | VUs concurrentes esperados | RAM aprox. |
|---|---|---|
| 2 workers | 10–30 VU | ~600 MB |
| 4 workers | 20–60 VU | ~900 MB |
| 6 workers | 30–80 VU | ~1.2 GB |

> **Nota**: El webhook del bot retorna `200 OK` inmediatamente y procesa en un
> thread daemon, por lo que la latencia HTTP será baja incluso bajo carga.
> El límite real lo pondrá la RAM cuando se llenen los threads de procesamiento
> y los workers de Gunicorn.

## Configuración recomendada de Gunicorn para 2 GB

```bash
gunicorn lakshmi.wsgi:application \
  --workers 4 \
  --threads 2 \
  --worker-class gthread \
  --max-requests 1000 \
  --max-requests-jitter 100 \
  --timeout 30 \
  --bind 0.0.0.0:8000
```

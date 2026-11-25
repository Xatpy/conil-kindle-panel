"""Tiempo y mareas de Conil, renderizados para el Paperwhite 4 (1072 × 1448)."""
from __future__ import annotations

import argparse
import copy
import io
import json
import logging
import math
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
TZ = ZoneInfo("Europe/Madrid")
UTC = timezone.utc
SIZE = (1072, 1448)
IHM = "https://ideihm.covam.es/api-ihm/getmarea"
WEATHER = "https://api.open-meteo.com/v1/forecast"
LOG = logging.getLogger("conil")
MONTHS = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()
DAYS = "lunes martes miércoles jueves viernes sábado domingo".split()


def get_text(url):
    request = urllib.request.Request(url, headers={"User-Agent": "ConilPanel/0.1 (personal e-ink dashboard)"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read(3_000_000).decode("utf-8")


def parse_tides(html):
    match = re.search(r'<script\b[^>]*\bid=[\"\']datos-marea[\"\'][^>]*>(.*?)</script>', html, re.S | re.I)
    if not match:
        raise ValueError("IHM no devolvió la serie de mareas esperada")
    data = json.loads(match.group(1))
    if data.get("utc") is not True:
        raise ValueError("No se puede confirmar la zona horaria de IHM")
    for ts, height, kind in data["eventos"]:
        if kind not in ("pleamar", "bajamar") or not math.isfinite(float(height)):
            raise ValueError("Evento de marea inválido")
        datetime.fromtimestamp(ts, UTC)
    if not data.get("serie") or not data.get("eventos"):
        raise ValueError("Predicción IHM vacía")
    for ts, height in data["serie"]:
        if not math.isfinite(float(height)):
            raise ValueError("Altura inválida")
    return data


def fetch_weather():
    params = {
        "latitude": 36.2772, "longitude": -6.0885,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m",
        "hourly": "temperature_2m,precipitation_probability,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,sunrise,sunset",
        "timezone": "Europe/Madrid", "timeformat": "unixtime", "forecast_days": 3,
        "wind_speed_unit": "kmh",
    }
    data = json.loads(get_text(WEATHER + "?" + urllib.parse.urlencode(params)))
    return validate_weather(data)


def validate_weather(data):
    current = data["current"]
    for key in ("time", "temperature_2m", "apparent_temperature", "weather_code", "wind_speed_10m", "wind_direction_10m"):
        if not isinstance(current.get(key), (int, float)) or not math.isfinite(current[key]):
            raise ValueError("Open-Meteo: dato ausente o inválido: " + key)
    for section, fields in (("hourly", ("temperature_2m", "precipitation_probability")),
                            ("daily", ("temperature_2m_min", "temperature_2m_max", "sunrise", "sunset"))):
        times = data[section]["time"]
        if not times or not all(isinstance(ts, (int, float)) and math.isfinite(ts) for ts in times):
            raise ValueError("Open-Meteo: horas inválidas")
        for field in fields:
            values = data[section][field]
            if len(values) != len(times):
                raise ValueError("Open-Meteo: serie incompleta")
            if field != "precipitation_probability" and not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
                raise ValueError("Open-Meteo: valores incompletos")
            if field == "precipitation_probability" and not all(v is None or isinstance(v, (int, float)) and math.isfinite(v) for v in values):
                raise ValueError("Open-Meteo: precipitación inválida")
    return data


def fetch_tides(now):
    # El día IHM es UTC. Incluimos los adyacentes para cubrir la medianoche local.
    day = now.astimezone(UTC).date()
    def fetch(offset):
        date = day + timedelta(days=offset)
        query = urllib.parse.urlencode(dict(request="gettide", id=46, format="gra", date=date.strftime("%Y%m%d")))
        return parse_tides(get_text(IHM + "?" + query))
    with ThreadPoolExecutor(max_workers=3) as pool:
        days = list(pool.map(fetch, (-1, 0, 1)))
    events = sorted({tuple(event) for data in days for event in data["eventos"]})
    series = sorted({tuple(point) for data in days for point in data["serie"]})
    return {"events": events, "series": series, "utc_day": str(day), "port": "Conil", "port_id": 46}


def local_events(tides, day):
    return [e for e in tides["events"] if datetime.fromtimestamp(e[0], TZ).date() == day]


def weather_label(code):
    if code == 0: return "Despejado"
    if code in (1, 2): return "Nubes y claros"
    if code == 3: return "Cubierto"
    if code in (45, 48): return "Niebla"
    if code in (51, 53, 55, 56, 57): return "Llovizna"
    if code in (61, 63, 65, 66, 67, 80, 81, 82): return "Lluvia"
    if code in (71, 73, 75, 77, 85, 86): return "Nieve"
    if code in (95, 96, 99): return "Tormenta"
    return "Previsión"


class Store:
    def __init__(self, cache=HERE / ".cache/data.json"):
        self.path = Path(cache)
        self.lock = threading.Lock()
        try: self.data = json.loads(self.path.read_text())
        except (OSError, ValueError): self.data = {}

    def snapshot(self):
        with self.lock: return copy.deepcopy(self.data)

    def refresh(self):
        now = datetime.now(UTC)
        for name, loader in (("weather", fetch_weather), ("tides", lambda: fetch_tides(now))):
            try:
                value = loader()
                with self.lock: self.data[name] = {"fetched": now.timestamp(), "value": value}
                LOG.info("%s actualizado", name)
            except Exception:
                LOG.exception("No se pudo actualizar %s; se conserva la última respuesta", name)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.snapshot(), ensure_ascii=False))
        temp.replace(self.path)


def font(size, bold=False):
    custom = os.environ.get("CONIL_FONT_BOLD" if bold else "CONIL_FONT")
    names = [custom] if custom else []
    names += [
        f"/Library/Fonts/SF-Pro-Display-{'Bold' if bold else 'Regular'}.otf",
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
        f"/usr/share/fonts/truetype/liberation2/LiberationSans{'-Bold' if bold else '-Regular'}.ttf",
    ]
    for name in names:
        try: return ImageFont.truetype(name, size)
        except OSError: pass
    raise RuntimeError("Instala DejaVu Sans o define CONIL_FONT y CONIL_FONT_BOLD")


def render(snapshot, now=None):
    now = (now or datetime.now(TZ)).astimezone(TZ)
    image = Image.new("L", SIZE, 255)
    draw = ImageDraw.Draw(image)
    def text(x, y, value, size=28, bold=False, fill=0):
        draw.text((x, y), str(value), font=font(size, bold), fill=fill)
    def rule(y): draw.line((56, y, 1016, y), fill=0, width=2)
    def centered(x, y, value, size=28, bold=False):
        f = font(size, bold)
        draw.text((x, y), value, font=f, fill=0, anchor="mt")

    text(56, 45, "CONIL", 92, True)
    text(60, 150, "DE LA FRONTERA · CÁDIZ", 24)
    text(60, 200, f"{DAYS[now.weekday()].capitalize()}, {now.day} de {MONTHS[now.month-1]}", 32)
    text(60, 245, f"Panel generado · {now:%d/%m/%Y %H:%M} ({now.tzname()})", 23)
    rule(291)

    weather = snapshot.get("weather")
    warnings = []
    if weather:
        w = weather["value"]; current = w["current"]
        observed = datetime.fromtimestamp(current["time"], TZ)
        stale = now.timestamp() - current["time"] > 7200
        text(56, 318, "PREVISIÓN METEOROLÓGICA" + (" · ANTIGUA" if stale else ""), 23, True)
        text(52, 348, f"{current['temperature_2m']:.0f}°", 140, True)
        text(310, 369, weather_label(current.get("weather_code")), 36, True)
        text(312, 425, f"Sensación {current['apparent_temperature']:.0f}° · Datos {observed:%H:%M}", 27)
        degrees = current["wind_direction_10m"]
        direction = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"][int((degrees + 22.5) // 45) % 8]
        text(58, 520, f"VIENTO  {direction} · {current['wind_speed_10m']:.0f} km/h", 32, True)
        d = w["daily"]
        index = next((i for i, ts in enumerate(d["time"]) if datetime.fromtimestamp(ts, TZ).date() == now.date()), None)
        if index is not None:
            rise = datetime.fromtimestamp(d["sunrise"][index], TZ)
            sunset = datetime.fromtimestamp(d["sunset"][index], TZ)
            text(58, 575, f"Hoy {d['temperature_2m_min'][index]:.0f}° / {d['temperature_2m_max'][index]:.0f}°   ·   Sol {rise:%H:%M} — {sunset:%H:%M}", 29)
        h = w["hourly"]
        indexes = [i for i, ts in enumerate(h["time"]) if ts >= now.timestamp()][::3][:4]
        for column, i in enumerate(indexes):
            x = 170 + column * 242
            centered(x, 650, datetime.fromtimestamp(h["time"][i], TZ).strftime("%H:%M"), 26)
            centered(x, 691, f"{h['temperature_2m'][i]:.0f}°", 40, True)
            rain = h["precipitation_probability"][i]
            centered(x, 746, f"Lluvia {rain:.0f}%" if rain is not None else "Lluvia —", 24)
        if stale: warnings.append("Tiempo sin actualizar: consulta la hora de los datos.")
    else:
        text(58, 370, "Tiempo no disponible", 44, True)
        text(58, 440, "Se actualizará cuando vuelva la conexión.", 28)
        warnings.append("Sin datos meteorológicos.")
    rule(804)
    text(58, 831, "MAREAS · PUERTO DE CONIL", 27, True)
    tide = snapshot.get("tides")
    if tide:
        t = tide["value"]
        events = local_events(t, now.date())
        future = [e for e in t["events"] if e[0] > now.timestamp()]
        if future and events:
            nxt = future[0]
            state = "Subiendo" if nxt[2] == "pleamar" else "Bajando"
            at = datetime.fromtimestamp(nxt[0], TZ)
            day_label = "mañana " if at.date() > now.date() else ""
            text(58, 882, f"{state} · próxima {nxt[2]} {day_label}{at:%H:%M}", 30)
        else:
            text(58, 882, "Sin predicción para este día", 30)
        start = datetime.combine(now.date(), datetime.min.time(), TZ).timestamp()
        end = datetime.combine(now.date()+timedelta(days=1), datetime.min.time(), TZ).timestamp()
        points = [(ts, height) for ts, height in t["series"] if start <= ts <= end]
        if len(points) > 2 and events:
            low = min(h for _, h in points); high = max(h for _, h in points)
            def xy(ts, height):
                return (70 + (ts-start)/(end-start)*932, 1127-(height-low)/max(high-low, .1)*145)
            for hour in (0, 6, 12, 18, 24):
                stamp = start if hour == 0 else end if hour == 24 else datetime.combine(now.date(), datetime.min.time(), TZ).replace(hour=hour).timestamp()
                x, _ = xy(stamp, low)
                draw.line((x, 961, x, 1135), fill=210, width=1)
                centered(x, 1143, f"{hour:02d}h", 22)
            draw.line([xy(ts, height) for ts, height in points], fill=0, width=4)
            if start <= now.timestamp() <= end:
                x, _ = xy(now.timestamp(), low)
                draw.line((x, 948, x, 1135), fill=100, width=2)
        for i, event in enumerate(events[:5]):
            at = datetime.fromtimestamp(event[0], TZ)
            x = 60 + i * (960 / max(4, len(events)))
            text(x, 1190, "ALTA" if event[2] == "pleamar" else "BAJA", 22, True)
            text(x, 1226, at.strftime("%H:%M"), 35, True)
            text(x, 1275, f"{event[1]:.2f} m", 25)
        if not events: warnings.append("Mareas sin datos para hoy; no se muestra una curva antigua.")
    else:
        text(58, 906, "Predicción de mareas no disponible", 33)
        warnings.append("Sin datos de mareas.")
    rule(1326)
    text(58, 1344, "Open-Meteo · IHM, puerto de Conil · Horas locales", 22)
    text(58, 1380, warnings[0] if warnings else "Marea astronómica prevista · Alturas referidas al cero IHM", 20)
    return image


def save_png(image, path):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    image.save(temp, format="PNG", optimize=True)
    temp.replace(path)


def serve(store, host, port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urllib.parse.urlparse(self.path).path
            if path not in ("/", "/conil.png", "/health"):
                self.send_error(404); return
            if path == "/health":
                data = json.dumps({"sources": list(store.snapshot())}).encode(); kind = "application/json"
            else:
                buffer = io.BytesIO(); render(store.snapshot()).save(buffer, format="PNG", optimize=True)
                data = buffer.getvalue(); kind = "image/png"
            self.send_response(200); self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(data)))
            self.end_headers(); self.wfile.write(data)
    stop = threading.Event()
    def updater():
        while not stop.wait(900): store.refresh()
    thread = threading.Thread(target=updater, daemon=True); thread.start()
    server = ThreadingHTTPServer((host, port), Handler)
    LOG.info("Panel disponible en http://%s:%s/conil.png", host, port)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: stop.set(); server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("render", "serve"))
    parser.add_argument("--output", type=Path, default=HERE / "output/conil.png")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8789)
    parser.add_argument("--offline", action="store_true", help="Usar exclusivamente la caché local")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    store = Store()
    if not args.offline: store.refresh()
    save_png(render(store.snapshot()), args.output)
    if args.command == "serve": serve(store, args.host, args.port)
    else: print(args.output)


if __name__ == "__main__": main()

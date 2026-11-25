"""Build the public artifact, refusing to replace it with an incomplete fetch."""
import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path

from panel import HERE, TZ, Store, render, save_png
from stoic import quote_for


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "output/site")
    args = parser.parse_args()
    store = Store()
    started = datetime.now(timezone.utc).timestamp()
    store.refresh()
    snapshot = store.snapshot()
    if any(snapshot.get(source, {}).get("fetched", 0) < started - 1 for source in ("weather", "tides")):
        raise SystemExit("No se publica: falta una respuesta nueva de alguna fuente; se conserva el despliegue anterior.")
    args.output.mkdir(parents=True, exist_ok=True)
    now = datetime.now(TZ)
    save_png(render(snapshot, now), args.output / "conil.png")
    generated = now.astimezone(timezone.utc).isoformat()
    status = {
        "generated_at": generated,
        "valid_date": now.date().isoformat(),
        "weather_retrieved_at": datetime.fromtimestamp(snapshot["weather"]["fetched"], timezone.utc).isoformat(),
        "quote": {**quote_for(now.date()), "note": "Versión libre en español, no cita literal"},
        "tides_port": "Conil", "tides_port_id": 46,
    }
    (args.output / "status.json").write_text(json.dumps(status, indent=2) + "\n")
    (args.output / "index.html").write_text('''<!doctype html>
<html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Conil · Tiempo y mareas</title>
<style>body{margin:0;background:#eee;font-family:system-ui;text-align:center}img{width:100%;max-width:536px;height:auto;background:white}footer{padding:1rem;font-size:.85rem;color:#444}</style>
<img src="conil.png" alt="Previsión meteorológica y mareas del puerto de Conil de la Frontera">
<footer>Open-Meteo · Instituto Hidrográfico de la Marina<br>
Actualizado ''' + html.escape(generated) + ''' · Boletín diario, renovado cada mañana.<br>
<a href="conil.png">Imagen para Kindle</a> · <a href="status.json">Fecha de los datos</a>
</footer></html>''', encoding="utf-8")
    print(args.output)


if __name__ == "__main__": main()

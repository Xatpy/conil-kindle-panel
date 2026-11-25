import json
import io
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from panel import TZ, Store, local_events, parse_tides, render, validate_weather, daily_forecast, font, wrap_text, png_bytes
from stoic import QUOTES, quote_for


def forecast_fixture():
    day = datetime(2026, 11, 25, tzinfo=TZ)
    return {"hourly": {
        "time": [day.replace(hour=h).timestamp() for h in (9, 12, 15, 18)],
        "temperature_2m": [12, 16, 17, 14], "precipitation_probability": [0, 10, 20, 5],
        "wind_speed_10m": [10, 15, 20, 12], "wind_direction_10m": [0, 90, 180, 270],
    }, "daily": {"time": [day.timestamp()], "temperature_2m_min": [10], "temperature_2m_max": [18],
                 "weather_code": [2], "precipitation_probability_max": [20],
                 "sunrise": [day.replace(hour=8).timestamp()], "sunset": [day.replace(hour=18).timestamp()]}}


class PanelTests(unittest.TestCase):
    def test_null_temperature_is_rejected_before_caching(self):
        data = forecast_fixture()
        data["daily"]["temperature_2m_max"][0] = None
        with self.assertRaises(ValueError):
            validate_weather(data)

    def test_daily_forecast_has_fixed_slots_and_rejects_wrong_day(self):
        data = forecast_fixture()
        forecast = daily_forecast(data, date(2026, 11, 25))
        self.assertEqual([slot["hour"] for slot in forecast["slots"]], [9, 12, 15, 18])
        self.assertEqual([slot["direction"] for slot in forecast["slots"]], ["N", "E", "S", "O"])
        self.assertEqual((forecast["low"], forecast["high"]), (10, 18))
        self.assertIsNone(daily_forecast(data, date(2026, 11, 26)))

    def test_quote_is_stable_within_day_and_changes_tomorrow(self):
        today = date(2026, 11, 25)
        self.assertEqual(quote_for(today), quote_for(today))
        self.assertNotEqual(quote_for(today), quote_for(date(2026, 11, 26)))
        for quote in QUOTES:
            lines = wrap_text(quote["text"], font(26), 436)
            self.assertLessEqual(len(lines), 4)
            self.assertLessEqual(font(16).getlength(quote["author"] + " · " + quote["reference"]), 436)

    def test_png_carries_valid_day_for_daily_download_guard(self):
        data = {"weather": {"fetched": datetime(2026, 11, 25, tzinfo=TZ).timestamp(), "value": forecast_fixture()}}
        image = render(data, datetime(2026, 11, 25, 22, tzinfo=TZ))
        loaded = Image.open(io.BytesIO(png_bytes(image)))
        self.assertEqual(loaded.info["ConilDate"], "2026-11-25")
        self.assertEqual(loaded.size, (1072, 1448))

    def test_utc_to_local_winter_and_summer(self):
        self.assertEqual(datetime(2026, 11, 24, 1, 5, tzinfo=timezone.utc).astimezone(TZ).strftime("%H:%M"), "02:05")
        self.assertEqual(datetime(2026, 7, 24, 1, 5, tzinfo=timezone.utc).astimezone(TZ).strftime("%H:%M"), "03:05")

    def test_previous_utc_day_event_belongs_to_local_day(self):
        event = [datetime(2026, 11, 23, 23, 30, tzinfo=timezone.utc).timestamp(), 3.0, "pleamar"]
        self.assertEqual(local_events({"events": [event]}, date(2026, 11, 24)), [event])
        self.assertEqual(local_events({"events": [event]}, date(2026, 11, 23)), [])

    def test_ihm_timezone_must_be_explicit(self):
        with self.assertRaises(ValueError): parse_tides('<script id="datos-marea">{"utc": false}</script>')
        with self.assertRaises(ValueError): parse_tides("<html>Servicio no disponible</html>")

    def test_parse_official_graph_payload(self):
        data = {"utc": True, "eventos": [[1795482300, 3.065, "pleamar"]], "serie": [[1795482300, 3.065]]}
        self.assertEqual(parse_tides('<script type="application/json" id="datos-marea">' + json.dumps(data) + '</script>'), data)

    def test_missing_sources_render_valid_grayscale_png(self):
        image = render({}, datetime(2026, 11, 24, 12, tzinfo=TZ))
        self.assertEqual(image.size, (1072, 1448))
        self.assertEqual(image.mode, "L")

    def test_network_failure_preserves_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "data.json")
            store.data = {"weather": {"fetched": 1, "value": {"sentinel": True}}}
            with patch("panel.fetch_weather", side_effect=OSError("offline")), patch("panel.fetch_tides", side_effect=OSError("offline")):
                with self.assertLogs("conil", level="ERROR"): store.refresh()
            self.assertEqual(store.snapshot()["weather"]["fetched"], 1)
            self.assertNotIn("tides", store.snapshot())


if __name__ == "__main__": unittest.main()

import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from panel import TZ, Store, local_events, parse_tides, render, validate_weather


class PanelTests(unittest.TestCase):
    def test_null_temperature_is_rejected_before_caching(self):
        with self.assertRaises(ValueError):
            validate_weather({"current": {"time": 1, "temperature_2m": None}})

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

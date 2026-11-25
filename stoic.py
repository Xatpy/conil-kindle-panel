"""Short Spanish free renderings of public-domain Stoic passages, not verbatim quotes."""
import json
from pathlib import Path

QUOTES = json.loads((Path(__file__).parent / "stoic_quotes.json").read_text())


def quote_for(day):
    return QUOTES[day.toordinal() % len(QUOTES)]

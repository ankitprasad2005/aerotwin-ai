"""respx helpers for the batched weather fetchers (one request per batch of Indian airports)."""
import json
from pathlib import Path

import httpx
import respx

from app.datasets import weather

FIXTURES = Path(__file__).parent / "fixtures" / "datasets"
INDIA_FORECAST = json.loads((FIXTURES / "open_meteo_forecast_india.json").read_text())


def mock_list_batches(urls: list[str], first: httpx.Response | bytes, rest: bytes = b"[]") -> None:
    """The first batch answers `first`, every other batch `rest` (an empty list)."""
    for index, url in enumerate(urls):
        answer = first if index == 0 else rest
        respx.get(url).mock(return_value=answer if isinstance(answer, httpx.Response) else httpx.Response(200, content=answer))


def mock_all_batches(urls: list[str], response: httpx.Response) -> None:
    for url in urls:
        respx.get(url).mock(return_value=response)


def india_forecast_batches() -> list[bytes]:
    """The Open-Meteo answer of each forecast batch, from the real 128-airport capture."""
    sizes = [len(group) for group in weather.forecast_batches()]
    bodies, start = [], 0
    for size in sizes:
        bodies.append(json.dumps(INDIA_FORECAST[start : start + size]).encode())
        start += size
    return bodies


def mock_forecast(first_only: bytes | None = None) -> None:
    """Answer every forecast batch from the capture (or, with `first_only`, the first from that body)."""
    bodies = india_forecast_batches()
    for index, url in enumerate(weather.forecast_urls()):
        respx.get(url).mock(return_value=httpx.Response(200, content=bodies[index]))

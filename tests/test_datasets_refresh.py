from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import select

from app.datasets import airworthiness, brent, common, dgca, eia, openflights, weather, world_bank
from app.datasets.refresh import FETCHERS, SOURCE_INFO, format_summary, parse_args, refresh_all, run_cli, validate_sources
from app.models.external import SNAPSHOT_FAILED, SNAPSHOT_FALLBACK, SNAPSHOT_SUCCESS, DatasetSnapshot, FuelPrice

FIXTURES = Path(__file__).parent / "fixtures" / "datasets"


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    async def fake_sleep(_):
        return None

    monkeypatch.setattr(common, "_sleep", fake_sleep)


@pytest.fixture
def datasets_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "get_settings", lambda: type("S", (), {"datasets_dir": str(tmp_path)})())
    return tmp_path


WORLD_BANK_FIXTURES = {
    world_bank.PASSENGERS: "worldbank_ind_passengers.json",
    world_bank.FREIGHT: "worldbank_ind_freight.json",
    world_bank.GDP_GROWTH: "worldbank_ind_gdp_growth.json",
}


def _mock_all(*, fail: set[str] = frozenset()):
    def reply(name, content):
        if name in fail:
            return httpx.Response(500)
        return httpx.Response(200, content=content)

    respx.get(openflights.ROUTES_URL).mock(return_value=reply("openflights", (FIXTURES / "routes_excerpt.dat").read_bytes()))
    respx.get(openflights.AIRLINES_URL).mock(return_value=reply("openflights", (FIXTURES / "airlines_excerpt.dat").read_bytes()))
    respx.get(eia.URL).mock(return_value=reply("eia_jet_fuel", (FIXTURES / "eia_jet_fuel_excerpt.xls").read_bytes()))
    respx.get(brent.URL).mock(return_value=reply("eia_brent", (FIXTURES / "eia_brent_excerpt.xls").read_bytes()))
    respx.get(url__regex=r"https://api\.frankfurter\.dev/v1/.*").mock(
        return_value=reply("fx", (FIXTURES / "frankfurter_usd_inr.json").read_bytes())
    )
    respx.get(dgca.PAGE_URL).mock(return_value=reply("dgca", b"<html>no links</html>"))
    respx.get(weather.metar_url()).mock(
        return_value=reply("aviation_weather", (FIXTURES / "aviation_weather_metar.json").read_bytes())
    )
    respx.get(weather.forecast_url()).mock(
        return_value=reply("open_meteo", (FIXTURES / "open_meteo_forecast.json").read_bytes())
    )
    respx.get(weather.taf_url()).mock(
        return_value=reply("aviation_weather_taf", (FIXTURES / "aviation_weather_taf.json").read_bytes())
    )
    respx.get(url__startswith=airworthiness.API_URL).mock(
        return_value=reply("faa_airworthiness_directives", (FIXTURES / "federal_register_ad_b737.json").read_bytes())
    )
    for code, fixture in WORLD_BANK_FIXTURES.items():
        respx.get(world_bank.indicator_url(code)).mock(return_value=reply("world_bank", (FIXTURES / fixture).read_bytes()))


def test_validate_sources():
    assert validate_sources(None) == list(FETCHERS)
    assert validate_sources([]) == list(FETCHERS)
    assert validate_sources(["fx", "fx", "dgca"]) == ["fx", "dgca"]
    with pytest.raises(ValueError, match="nope"):
        validate_sources(["fx", "nope"])


def test_source_info_covers_every_fetcher():
    assert set(SOURCE_INFO) == set(FETCHERS)
    assert {"openflights", "eia_jet_fuel", "eia_brent", "fx", "dgca", "aviation_weather", "open_meteo", "faa_airworthiness_directives", "aviation_weather_taf", "world_bank", "airport_charges"} <= set(FETCHERS)
    assert all({"title", "description", "license", "source_url"} <= set(v) for v in SOURCE_INFO.values())
    assert "ODbL" in SOURCE_INFO["openflights"]["license"]


@respx.mock
async def test_refresh_all_runs_every_source_independently(db_session, datasets_tmp):
    _mock_all(fail={"eia_jet_fuel"})

    snapshots = await refresh_all(db_session)

    by_source = {s.source: s for s in snapshots}
    assert [s.source for s in snapshots] == list(FETCHERS)
    assert by_source["eia_jet_fuel"].status == SNAPSHOT_FAILED
    assert by_source["openflights"].status == SNAPSHOT_SUCCESS
    assert by_source["fx"].status == SNAPSHOT_SUCCESS
    assert by_source["aviation_weather"].status == by_source["open_meteo"].status == SNAPSHOT_SUCCESS
    assert by_source["aviation_weather_taf"].status == SNAPSHOT_SUCCESS
    assert "faa_airworthiness_directives" in by_source  # its outcome depends on today's date (365-day window)
    assert by_source["world_bank"].status == SNAPSHOT_SUCCESS and by_source["world_bank"].row_count == 14
    # The curated AERA charges need no download: loaded from the CSV, reported as FALLBACK.
    assert by_source["airport_charges"].status == SNAPSHOT_FALLBACK and by_source["airport_charges"].row_count > 90
    # DGCA found no PDF and the shipped fallback CSV has no rows, so it fails rather than inventing data.
    assert by_source["dgca"].status == SNAPSHOT_FAILED
    assert (await db_session.execute(select(FuelPrice))).scalars().all() == []


@respx.mock
async def test_refresh_all_with_a_subset_and_a_supplied_client(db_session, datasets_tmp):
    _mock_all()
    async with httpx.AsyncClient() as client:
        snapshots = await refresh_all(db_session, ["fx"], client=client)
        assert not client.is_closed
    assert [s.source for s in snapshots] == ["fx"]
    assert len((await db_session.execute(select(DatasetSnapshot))).scalars().all()) == 1


async def test_refresh_all_rejects_unknown_sources_before_doing_any_work(db_session):
    with pytest.raises(ValueError):
        await refresh_all(db_session, ["bogus"])
    assert (await db_session.execute(select(DatasetSnapshot))).scalars().all() == []


def test_format_summary():
    ok = DatasetSnapshot(source="fx", status="SUCCESS", row_count=5, error=None)
    bad = DatasetSnapshot(source="eia_jet_fuel", status="FAILED", row_count=0, error="boom")
    text = format_summary([ok, bad])
    assert "fx" in text and "rows=5" in text and "(boom)" in text
    assert format_summary([]) == ""


def test_parse_args():
    assert parse_args([]).sources is None
    assert parse_args(["--source", "fx", "--source", "dgca"]).sources == ["fx", "dgca"]
    with pytest.raises(SystemExit):
        parse_args(["--source", "bogus"])


@respx.mock
async def test_run_cli_prints_summary_and_exit_code(db_session, datasets_tmp, capsys):
    _mock_all()

    class Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *exc):
            return False

    assert await run_cli(["--source", "fx"], session_factory=Factory()) == 0
    assert "fx" in capsys.readouterr().out

    _mock_all(fail={"fx"})
    assert await run_cli(["--source", "fx"], session_factory=Factory()) == 1
    assert "FAILED" in capsys.readouterr().out


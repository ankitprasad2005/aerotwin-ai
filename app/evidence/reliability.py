# How far each evidence source can be trusted, 0-1. The twin's own data is not evidence: it stays in
# `entities` and is implicitly 1.0.
SOURCE_RELIABILITY: dict[str, float] = {
    "dgca": 0.9,
    "eia_jet_fuel": 0.9,
    "eia_brent": 0.9,
    "fx": 0.95,
    "openflights": 0.7,
    "web": 0.4,
    "aviation_weather": 0.9,
    "open_meteo": 0.8,
    "faa_airworthiness_directives": 0.95,
    "world_bank": 0.85,
    "india_holidays": 0.95,
    "iocl": 0.95,
    "ppac": 0.9,
}

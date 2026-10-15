# How far each evidence source can be trusted, 0-1. The twin's own data is not evidence: it stays in
# `entities` and is implicitly 1.0.
SOURCE_RELIABILITY: dict[str, float] = {
    "dgca": 0.9,
    "eia_jet_fuel": 0.9,
    "fx": 0.95,
    "openflights": 0.7,
    "web": 0.4,
}

AIRPORTS = [
    {"code": "BOM", "name": "Chhatrapati Shivaji Maharaj Intl", "city": "Mumbai", "country": "India"},
    {"code": "DEL", "name": "Indira Gandhi Intl", "city": "Delhi", "country": "India"},
    {"code": "BLR", "name": "Kempegowda Intl", "city": "Bengaluru", "country": "India"},
    {"code": "MAA", "name": "Chennai Intl", "city": "Chennai", "country": "India"},
    {"code": "HYD", "name": "Rajiv Gandhi Intl", "city": "Hyderabad", "country": "India"},
    {"code": "CCU", "name": "Netaji Subhas Chandra Bose Intl", "city": "Kolkata", "country": "India"},
]

AIRCRAFT = [
    {"tail_number": "VT-AER1", "aircraft_type": "A320", "location": "BOM", "status": "AVAILABLE", "fuel_level_pct": 72.0, "flight_hours": 4281.0, "maintenance_status": "NORMAL"},
    {"tail_number": "VT-AER2", "aircraft_type": "A320", "location": "DEL", "status": "AVAILABLE", "fuel_level_pct": 88.0, "flight_hours": 2110.0, "maintenance_status": "NORMAL"},
    {"tail_number": "VT-AER3", "aircraft_type": "B737", "location": "BLR", "status": "MAINTENANCE", "fuel_level_pct": 40.0, "flight_hours": 9100.0, "maintenance_status": "SCHEDULED"},
    {"tail_number": "VT-AER4", "aircraft_type": "A321", "location": "MAA", "status": "AVAILABLE", "fuel_level_pct": 95.0, "flight_hours": 640.0, "maintenance_status": "NORMAL"},
]

# Economics are illustrative USD figures: average one-way fare, and the full operating cost of
# one flight (fuel, crew, fees, aircraft ownership). Keep in sync with the backfill in
# alembic/versions/5c1e9a7d3b20_add_route_economics.py for already-seeded databases.
ROUTES = [
    {"origin": "BOM", "destination": "DEL", "distance_km": 1150, "current_frequency": 7, "seats_per_flight": 180, "average_fare_usd": 95.0, "operating_cost_per_flight_usd": 9000.0},
    {"origin": "DEL", "destination": "BOM", "distance_km": 1150, "current_frequency": 7, "seats_per_flight": 180, "average_fare_usd": 95.0, "operating_cost_per_flight_usd": 9000.0},
    {"origin": "BOM", "destination": "BLR", "distance_km": 840, "current_frequency": 5, "seats_per_flight": 180, "average_fare_usd": 70.0, "operating_cost_per_flight_usd": 7000.0},
    {"origin": "BLR", "destination": "HYD", "distance_km": 500, "current_frequency": 3, "seats_per_flight": 180, "average_fare_usd": 50.0, "operating_cost_per_flight_usd": 4800.0},
    {"origin": "MAA", "destination": "CCU", "distance_km": 1360, "current_frequency": 2, "seats_per_flight": 180, "average_fare_usd": 85.0, "operating_cost_per_flight_usd": 10500.0},
]

DEMAND = [
    {"route": ("BOM", "DEL"), "period": "2026-Q3", "demand": 18000, "historical_load_factor": 0.81},
    {"route": ("DEL", "BOM"), "period": "2026-Q3", "demand": 17500, "historical_load_factor": 0.79},
    {"route": ("BOM", "BLR"), "period": "2026-Q3", "demand": 9200, "historical_load_factor": 0.68},
    {"route": ("BLR", "HYD"), "period": "2026-Q3", "demand": 4100, "historical_load_factor": 0.55},
    {"route": ("MAA", "CCU"), "period": "2026-Q3", "demand": 3300, "historical_load_factor": 0.61},
]

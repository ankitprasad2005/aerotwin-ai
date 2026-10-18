import pytest

from app.context.engine import build_context_payload
from app.context.proposal import parse_proposed_change, proposed_change_for
from app.agents.registry import AGENT_REGISTRY
from app.seed.seed import run_seed

ROUTES = {"BOM-DEL", "DEL-BOM", "BOM-BLR", "BLR-HYD", "MAA-CCU"}
ALIASES = {"BOM": "BOM", "DEL": "DEL", "BLR": "BLR", "MAA": "MAA", "HYD": "HYD", "CCU": "CCU",
           "MUMBAI": "BOM", "DELHI": "DEL", "BENGALURU": "BLR", "BANGALORE": "BLR", "CHENNAI": "MAA",
           "HYDERABAD": "HYD", "KOLKATA": "CCU"}


def _parse(objective):
    return parse_proposed_change(objective, routes=ROUTES, aliases=ALIASES)


@pytest.mark.parametrize("objective,expected", [
    ("Should we add a weekly flight on DEL-BOM?", {"route": "DEL-BOM", "action": "INCREASE_FREQUENCY"}),
    ("Should we increase frequency on BOM-DEL given current fuel prices and demand?",
     {"route": "BOM-DEL", "action": "INCREASE_FREQUENCY"}),
    ("Is it worth adding a third daily BLR-HYD flight this winter?", {"route": "BLR-HYD", "action": "INCREASE_FREQUENCY"}),
    ("Should we cut a weekly flight on BOM-BLR?", {"route": "BOM-BLR", "action": "DECREASE_FREQUENCY"}),
    ("Reduce MAA CCU frequency", {"route": "MAA-CCU", "action": "DECREASE_FREQUENCY"}),
    ("Add another flight from Mumbai to Delhi", {"route": "BOM-DEL", "action": "INCREASE_FREQUENCY"}),
    ("Should we drop a flight between Chennai and Kolkata?", {"route": "MAA-CCU", "action": "DECREASE_FREQUENCY"}),
])
def test_a_route_and_a_direction_make_a_proposal(objective, expected):
    assert _parse(objective) == expected


def test_the_reverse_of_an_unknown_direction_is_used_when_only_it_exists():
    # Only MAA-CCU exists in the twin, so "CCU to MAA" means that route.
    assert _parse("Add a flight CCU to MAA") == {"route": "MAA-CCU", "action": "INCREASE_FREQUENCY"}


@pytest.mark.parametrize("objective", [
    "Improve airline profitability while maintaining passenger capacity",   # no route
    "What should we do on BOM-DEL?",                                        # no direction
    "Should we add or cut a flight on BOM-DEL?",                            # both directions
    "Add a flight from Mumbai to Chennai",                                  # no such route either way
    "Add more capacity on BOM",                                             # one airport only
])
def test_no_proposal_without_exactly_one_route_and_one_direction(objective):
    assert _parse(objective) is None


def test_words_inside_other_words_do_not_count():
    # "address" contains "add" and "reduced" is a past-tense mention, not a proposal verb on its own.
    assert _parse("Address BOM-DEL demand") is None


async def test_proposed_change_for_reads_routes_and_city_names_from_the_twin(db_session):
    await run_seed(db_session)
    assert await proposed_change_for(db_session, "Add a flight from Hyderabad to Bengaluru") == {
        "route": "BLR-HYD", "action": "INCREASE_FREQUENCY",
    }
    assert await proposed_change_for(db_session, "Improve profitability") is None


async def test_only_the_network_agent_context_carries_the_proposal(db_session):
    await run_seed(db_session)
    objective = "Should we add a weekly flight on MAA-CCU?"
    network = await build_context_payload(db_session, objective=objective, spec=AGENT_REGISTRY["NETWORK"])
    crew = await build_context_payload(db_session, objective=objective, spec=AGENT_REGISTRY["CREW"])
    assert network["proposed_change"] == {"route": "MAA-CCU", "action": "INCREASE_FREQUENCY"}
    assert "proposed_change" not in crew


async def test_network_context_has_no_proposal_for_an_open_objective(db_session):
    await run_seed(db_session)
    network = await build_context_payload(db_session, objective="Improve profitability", spec=AGENT_REGISTRY["NETWORK"])
    assert "proposed_change" not in network


KNOWN = {"BOM", "DEL", "BLR", "MAA", "HYD", "CCU", "GOI", "PNQ"}


def _parse_known(objective):
    return parse_proposed_change(objective, routes=ROUTES, aliases=ALIASES, known_codes=KNOWN)


def test_an_explicit_route_code_wins_over_city_names_mentioned_earlier():
    assert _parse_known("As the network planner of a Mumbai-based airline, should we add a weekly A320 rotation on DEL-BOM?") == {
        "route": "DEL-BOM", "action": "INCREASE_FREQUENCY",
    }


def test_an_explicit_route_the_network_does_not_fly_is_a_proposal_outside_the_network():
    assert _parse_known("Our Mumbai crew base is short of A320 first officers; should we still add a BOM-GOI daily flight?") == {
        "route": "BOM-GOI", "action": "INCREASE_FREQUENCY", "in_network": False,
    }
    # Asking about a route the network does not fly is flagged even without an add/cut verb.
    assert _parse_known("Pull aircraft off the DEL-BLR route for a heavy C-check next month") == {
        "route": "DEL-BLR", "action": None, "in_network": False,
    }


def test_explicit_codes_must_be_real_airports_and_upper_case():
    assert _parse_known("Add a flight on the ABC-XYZ route") is None
    assert _parse_known("add a flight on del-bom") == {"route": "DEL-BOM", "action": "INCREASE_FREQUENCY"}  # via city/code aliases


async def test_proposed_change_for_knows_indian_airports_outside_the_twin(db_session):
    from app.models.external import IndiaAirport

    await run_seed(db_session)
    db_session.add(IndiaAirport(ident="VOGO", icao_code="VOGO", iata_code="GOI", name="Goa", airport_type="medium_airport"))
    await db_session.flush()
    assert await proposed_change_for(db_session, "Add a BOM-GOI flight") == {
        "route": "BOM-GOI", "action": "INCREASE_FREQUENCY", "in_network": False,
    }

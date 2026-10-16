import pytest
from sqlalchemy import select

from app.models.digital_twin import Aircraft, CrewMember
from app.seed.seed import run_seed
from app.tools.digital_twin_tools import (
    AIRCRAFT_REPOSITIONING_COST_USD,
    CREW_REPOSITIONING_COST_USD_PER_MEMBER,
    query_crew_status,
    query_fleet_status,
)

ALL_SEED_ROUTES = ["BOM-DEL", "DEL-BOM", "BOM-BLR", "BLR-HYD", "MAA-CCU"]
NO_CREW_NEEDED = {
    "crew_availability": "SUFFICIENT", "assignment_action": "NO_CHANGE",
    "assigned_crew": [], "expected_cost_impact": 0.0, "aircraft_type": None,
}
NO_CREW_FOUND = {
    "crew_availability": "INSUFFICIENT", "assignment_action": "NO_CHANGE",
    "assigned_crew": [], "expected_cost_impact": 0.0, "aircraft_type": None,
}
NO_AIRCRAFT_NEEDED = {
    "aircraft_tail_number": "NONE", "assignment_action": "NO_CHANGE",
    "aircraft_availability": "AVAILABLE", "expected_cost_impact": 0.0,
}
NO_AIRCRAFT_FOUND = {**NO_AIRCRAFT_NEEDED, "aircraft_availability": "UNAVAILABLE"}


def test_cost_constants():
    assert CREW_REPOSITIONING_COST_USD_PER_MEMBER == 300.0
    assert AIRCRAFT_REPOSITIONING_COST_USD == 4000.0


def _by_route(result):
    return {a["route"]: a for a in result["route_assessments"]}


async def _crew_increase(db_session, route):
    return _by_route(await query_crew_status(db_session))[route]["if_increase_by_one_weekly_flight"]


async def _fleet_increase(db_session, route):
    return _by_route(await query_fleet_status(db_session))[route]["if_increase_by_one_weekly_flight"]


async def _set_crew(db_session, code, **fields):
    member = (await db_session.execute(select(CrewMember).where(CrewMember.employee_code == code))).scalar_one()
    for key, value in fields.items():
        setattr(member, key, value)
    await db_session.flush()


async def _set_aircraft(db_session, tail, **fields):
    unit = (await db_session.execute(select(Aircraft).where(Aircraft.tail_number == tail))).scalar_one()
    for key, value in fields.items():
        setattr(unit, key, value)
    await db_session.flush()


# ---- crew ----


async def test_crew_status_keeps_members_and_assesses_every_route_in_both_directions(db_session):
    await run_seed(db_session)

    result = await query_crew_status(db_session)

    assert len(result["crew"]) == 9
    assert [a["route"] for a in result["route_assessments"]] == ALL_SEED_ROUTES
    for assessment in result["route_assessments"]:
        assert assessment["if_decrease_by_one_weekly_flight"] == NO_CREW_NEEDED


@pytest.mark.parametrize(
    "route, expected",
    [
        ("BOM-DEL", ("SUFFICIENT", "ASSIGN_ADDITIONAL_CREW", ["CR-001", "CR-003"], 0.0, "A320")),
        ("BOM-BLR", ("SUFFICIENT", "ASSIGN_ADDITIONAL_CREW", ["CR-001", "CR-003"], 0.0, "A320")),
        # DEL has captain CR-004 but its first officer CR-005 is ON_LEAVE: only the BOM pair can fly it.
        ("DEL-BOM", ("SUFFICIENT", "REPOSITION_CREW", ["CR-001", "CR-003"], 600.0, "A320")),
        # BLR's only aircraft is grounded: A320 family fallback, and the A320 pair is based at BOM.
        ("BLR-HYD", ("SUFFICIENT", "REPOSITION_CREW", ["CR-001", "CR-003"], 600.0, "A320")),
        # MAA flies the A321: captain CR-007 is SICK and first officer CR-008 has no duty hours left.
        ("MAA-CCU", ("INSUFFICIENT", "NO_CHANGE", [], 0.0, "A321")),
    ],
)
async def test_crew_increase_for_seed_routes(db_session, route, expected):
    await run_seed(db_session)

    got = await _crew_increase(db_session, route)

    assert (
        got["crew_availability"], got["assignment_action"], got["assigned_crew"],
        got["expected_cost_impact"], got["aircraft_type"],
    ) == expected


async def test_crew_increase_pair_at_origin_is_assigned_free(db_session):
    await run_seed(db_session)
    await _set_crew(db_session, "CR-005", status="AVAILABLE", weekly_duty_hours=5.0)

    got = await _crew_increase(db_session, "DEL-BOM")

    assert (got["assignment_action"], got["assigned_crew"], got["expected_cost_impact"]) == (
        "ASSIGN_ADDITIONAL_CREW", ["CR-004", "CR-005"], 0.0,
    )


async def test_crew_increase_pair_sharing_another_base_moves_together(db_session):
    await run_seed(db_session)
    await _set_crew(db_session, "CR-005", status="AVAILABLE", weekly_duty_hours=5.0)
    await _set_crew(db_session, "CR-004", status="ON_LEAVE")

    got = await _crew_increase(db_session, "DEL-BOM")

    # FO CR-005 is at DEL but there is no DEL captain: the BOM pair moves rather than splitting up.
    assert (got["assignment_action"], got["assigned_crew"], got["expected_cost_impact"]) == (
        "REPOSITION_CREW", ["CR-001", "CR-003"], 600.0,
    )


async def test_crew_increase_picks_the_other_base_with_most_combined_duty_hours(db_session):
    await run_seed(db_session)
    from app.models.digital_twin import Airport

    blr = (await db_session.execute(select(Airport).where(Airport.code == "BLR"))).scalar_one()
    await _set_crew(db_session, "CR-006", qualified_aircraft_type="A320", weekly_duty_hours=0.0, base_id=blr.id)
    db_session.add(
        CrewMember(
            employee_code="CR-100", name="Test FO", role="FIRST_OFFICER", base_id=blr.id,
            qualified_aircraft_type="A320", status="AVAILABLE", weekly_duty_hours=0.0, max_weekly_duty_hours=40.0,
        )
    )
    await db_session.flush()

    got = await _crew_increase(db_session, "DEL-BOM")

    # BLR pair has 40+40 hours left, BOM pair 18+22: the fresher BLR pair is chosen.
    assert got["assigned_crew"] == ["CR-006", "CR-100"]


async def test_crew_increase_with_no_shared_base_keeps_the_member_already_at_the_origin(db_session):
    await run_seed(db_session)
    await _set_crew(db_session, "CR-005", status="AVAILABLE", weekly_duty_hours=5.0)
    await _set_crew(db_session, "CR-004", status="ON_LEAVE")
    await _set_crew(db_session, "CR-003", status="ON_LEAVE")

    got = await _crew_increase(db_session, "DEL-BOM")

    assert (got["assignment_action"], got["assigned_crew"], got["expected_cost_impact"]) == (
        "REPOSITION_CREW", ["CR-001", "CR-005"], 300.0,
    )


async def test_crew_increase_prefers_most_remaining_duty_hours(db_session):
    await run_seed(db_session)
    await _set_crew(db_session, "CR-002", weekly_duty_hours=5.0)  # 35h left, more than CR-001's 18h

    got = await _crew_increase(db_session, "BOM-DEL")

    assert got["assigned_crew"] == ["CR-002", "CR-003"]


async def test_crew_increase_never_assigns_limited_crew(db_session):
    await run_seed(db_session)
    await _set_crew(db_session, "CR-001", weekly_duty_hours=35.0)  # 5h left: LIMITED, like CR-002
    await _set_crew(db_session, "CR-004", status="ON_LEAVE")  # the only other A320 captain

    assert await _crew_increase(db_session, "BOM-DEL") == {**NO_CREW_FOUND, "aircraft_type": "A320"}


async def test_crew_increase_uses_the_type_of_a_non_grounded_aircraft_at_the_origin(db_session):
    await run_seed(db_session)
    # VT-AER1 (A320, BOM) becomes the only candidate; the B737 captain CR-006 is irrelevant.
    got = await _crew_increase(db_session, "BOM-BLR")
    assert got["aircraft_type"] == "A320"


async def test_crew_increase_ignores_grounded_aircraft_at_the_origin(db_session):
    await run_seed(db_session)
    await _set_aircraft(db_session, "VT-AER1", flight_hours=5000.0)  # overdue A-check: GROUNDED

    got = await _crew_increase(db_session, "BOM-DEL")

    # No flyable aircraft at BOM any more: A320-family fallback, A320 crew still based at BOM.
    assert (got["aircraft_type"], got["assignment_action"], got["expected_cost_impact"]) == ("A320", "ASSIGN_ADDITIONAL_CREW", 0.0)


async def test_crew_increase_tries_other_family_types_when_the_first_has_no_pair(db_session):
    await run_seed(db_session)
    await _set_crew(db_session, "CR-003", status="ON_LEAVE")  # no A320 pair left anywhere
    await _set_crew(db_session, "CR-007", status="AVAILABLE", weekly_duty_hours=0.0)
    await _set_crew(db_session, "CR-008", weekly_duty_hours=0.0)

    got = await _crew_increase(db_session, "BLR-HYD")

    # The A320 has no pair, so the A321 family member is tried: its MAA crew is repositioned to BLR.
    assert (got["aircraft_type"], got["assigned_crew"], got["assignment_action"], got["expected_cost_impact"]) == (
        "A321", ["CR-007", "CR-008"], "REPOSITION_CREW", 600.0,
    )


async def test_crew_increase_without_any_flyable_a320_family_aircraft_is_insufficient(db_session):
    await run_seed(db_session)
    for tail in ("VT-AER1", "VT-AER2", "VT-AER4"):
        await _set_aircraft(db_session, tail, status="MAINTENANCE")

    assert await _crew_increase(db_session, "BOM-DEL") == NO_CREW_FOUND


async def test_crew_assessments_empty_without_routes(db_session):
    assert await query_crew_status(db_session) == {"crew": [], "route_assessments": []}


# ---- fleet ----


async def test_fleet_status_keeps_aircraft_and_assesses_every_route_in_both_directions(db_session):
    await run_seed(db_session)

    result = await query_fleet_status(db_session)

    assert len(result["aircraft"]) == 4
    assert [a["route"] for a in result["route_assessments"]] == ALL_SEED_ROUTES
    for assessment in result["route_assessments"]:
        assert assessment["if_decrease_by_one_weekly_flight"] == NO_AIRCRAFT_NEEDED


@pytest.mark.parametrize(
    "route, tail, cost",
    [
        ("BOM-DEL", "VT-AER1", 0.0),  # DUE_SOON, but at the origin: beats repositioning another aircraft
        ("BOM-BLR", "VT-AER1", 0.0),
        ("DEL-BOM", "VT-AER2", 0.0),
        ("MAA-CCU", "VT-AER4", 0.0),
        # BLR's own VT-AER3 is grounded; VT-AER2 (SERVICEABLE) beats DUE_SOON VT-AER1 and VT-AER4 on tail order.
        ("BLR-HYD", "VT-AER2", 4000.0),
    ],
)
async def test_fleet_increase_for_seed_routes(db_session, route, tail, cost):
    await run_seed(db_session)

    assert await _fleet_increase(db_session, route) == {
        "aircraft_tail_number": tail, "assignment_action": "ASSIGN_ADDITIONAL_AIRCRAFT",
        "aircraft_availability": "AVAILABLE", "expected_cost_impact": cost,
    }


async def test_fleet_increase_prefers_serviceable_when_nothing_is_at_the_origin(db_session):
    await run_seed(db_session)
    await _set_aircraft(db_session, "VT-AER2", status="MAINTENANCE")

    got = await _fleet_increase(db_session, "BLR-HYD")

    # VT-AER1 (DUE_SOON) sorts before VT-AER4 by tail, but SERVICEABLE VT-AER4 must win.
    assert got["aircraft_tail_number"] == "VT-AER4"


async def test_fleet_increase_takes_a_due_soon_aircraft_when_it_is_the_only_option(db_session):
    await run_seed(db_session)
    await _set_aircraft(db_session, "VT-AER2", status="MAINTENANCE")
    await _set_aircraft(db_session, "VT-AER4", status="MAINTENANCE")

    got = await _fleet_increase(db_session, "BLR-HYD")

    assert (got["aircraft_tail_number"], got["expected_cost_impact"]) == ("VT-AER1", 4000.0)


async def test_fleet_increase_skips_overdue_aircraft_even_when_status_is_available(db_session):
    await run_seed(db_session)
    await _set_aircraft(db_session, "VT-AER4", flight_hours=1100.0)  # past its A-check due at 1000 h

    got = await _fleet_increase(db_session, "MAA-CCU")

    assert (got["aircraft_tail_number"], got["expected_cost_impact"]) == ("VT-AER2", 4000.0)


async def test_fleet_increase_without_any_flyable_aircraft_is_unavailable(db_session):
    await run_seed(db_session)
    for tail in ("VT-AER1", "VT-AER2", "VT-AER4"):
        await _set_aircraft(db_session, tail, status="MAINTENANCE")

    for assessment in (await query_fleet_status(db_session))["route_assessments"]:
        assert assessment["if_increase_by_one_weekly_flight"] == NO_AIRCRAFT_FOUND
        assert assessment["if_decrease_by_one_weekly_flight"] == NO_AIRCRAFT_NEEDED


def test_agent_instructions_tell_the_llm_to_copy_the_precomputed_assessment():
    from app.agents.crew_agent import CREW_AGENT_SPEC
    from app.agents.fleet_agent import FLEET_AGENT_SPEC

    for spec in (CREW_AGENT_SPEC, FLEET_AGENT_SPEC):
        assert "route_assessments" in spec.system_instructions
        assert "if_increase_by_one_weekly_flight" in spec.system_instructions
        assert "if_decrease_by_one_weekly_flight" in spec.system_instructions

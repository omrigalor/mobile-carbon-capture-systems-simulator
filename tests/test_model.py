import pytest

from model import (RouteSegment, SystemDesign, capture_efficiency, depot_schedule,
                   engine_co2_rate_kg_h, example_route, pareto_designs, simulate)


def test_emissions_increase_with_load():
    assert engine_co2_rate_kg_h(.8, 80) > engine_co2_rate_kg_h(.2, 80)


def test_mass_accounting_and_capacity():
    design = SystemDesign(buffer_capacity_kg=20)
    out = simulate(example_route(), design)
    assert out.captured_kg <= 20
    assert out.captured_kg + out.vented_kg <= out.emitted_kg
    assert out.peak_buffer_kg <= design.buffer_capacity_kg


def test_heat_recovery_improves_net_avoidance():
    low = simulate(example_route(), SystemDesign(heat_recovery_fraction=.1))
    high = simulate(example_route(), SystemDesign(heat_recovery_fraction=.8))
    assert high.net_avoided_kg > low.net_avoided_kg


def test_depot_offload_can_increase_capture():
    d = SystemDesign(buffer_capacity_kg=12)
    direct = simulate(example_route(), d)
    scheduled = depot_schedule(example_route(), d, {1})
    assert scheduled.captured_kg >= direct.captured_kg


def test_efficiency_is_bounded():
    e = capture_efficiency(SystemDesign(), RouteSegment(10, .5, 40))
    assert 0 <= e <= .95


def test_invalid_route_rejected():
    with pytest.raises(ValueError):
        simulate([RouteSegment(-1, .5, 40)])


def test_pareto_front_is_nonempty():
    designs = [SystemDesign(system_mass_kg=m, base_capture_fraction=f)
               for m, f in ((300, .35), (500, .55), (700, .7))]
    assert pareto_designs(example_route(), designs)

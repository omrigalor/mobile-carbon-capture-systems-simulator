"""Transient mass-and-energy model for onboard heavy-vehicle CO2 capture."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import math


@dataclass(frozen=True)
class RouteSegment:
    minutes: float
    engine_load: float
    speed_kph: float
    ambient_c: float = 20.0


@dataclass(frozen=True)
class SystemDesign:
    capture_capacity_kg_h: float = 18.0
    buffer_capacity_kg: float = 160.0
    system_mass_kg: float = 520.0
    heat_recovery_fraction: float = 0.45
    base_capture_fraction: float = 0.55


@dataclass(frozen=True)
class RouteResult:
    emitted_kg: float
    captured_kg: float
    vented_kg: float
    fuel_penalty_kg: float
    net_avoided_kg: float
    peak_buffer_kg: float
    capture_fraction: float


def engine_co2_rate_kg_h(load: float, speed_kph: float) -> float:
    if not 0 <= load <= 1 or speed_kph < 0:
        raise ValueError("invalid route state")
    idle = 8.0
    traction = 52.0 * load * (0.55 + 0.45 * min(speed_kph, 100) / 100)
    return idle + traction


def capture_efficiency(design: SystemDesign, segment: RouteSegment) -> float:
    thermal_window = math.exp(-((segment.ambient_c - 22) / 28) ** 2)
    transient_factor = 0.72 + 0.28 * math.sqrt(max(0, segment.engine_load))
    return min(0.95, max(0.0, design.base_capture_fraction * thermal_window * transient_factor))


def simulate(route: list[RouteSegment], design: SystemDesign = SystemDesign()) -> RouteResult:
    if not route or min(design.capture_capacity_kg_h, design.buffer_capacity_kg,
                        design.system_mass_kg) <= 0:
        raise ValueError("route and positive design capacities are required")
    emitted = captured = vented = buffer = peak = penalty = 0.0
    for segment in route:
        if segment.minutes <= 0:
            raise ValueError("segment duration must be positive")
        hours = segment.minutes / 60
        raw = engine_co2_rate_kg_h(segment.engine_load, segment.speed_kph) * hours
        potential = raw * capture_efficiency(design, segment)
        throughput = design.capture_capacity_kg_h * hours
        storage = design.buffer_capacity_kg - buffer
        accepted = max(0.0, min(potential, throughput, storage))
        captured += accepted
        vented += potential - accepted
        buffer += accepted
        peak = max(peak, buffer)
        emitted += raw
        thermal_duty = accepted * 0.11 * (1 - design.heat_recovery_fraction)
        mass_duty = raw * design.system_mass_kg / 40_000 * 0.018
        penalty += thermal_duty + mass_duty
    penalty_co2 = penalty * 3.16
    net = captured - penalty_co2
    return RouteResult(emitted, captured, vented, penalty, net, peak,
                       captured / emitted if emitted else 0.0)


def depot_schedule(route: list[RouteSegment], design: SystemDesign,
                   offload_after_segments: set[int]) -> RouteResult:
    """Simulate depot offloads while preserving route-level mass accounting."""
    totals = dict(emitted_kg=0.0, captured_kg=0.0, vented_kg=0.0,
                  fuel_penalty_kg=0.0, net_avoided_kg=0.0, peak_buffer_kg=0.0)
    batch: list[RouteSegment] = []
    for i, segment in enumerate(route):
        batch.append(segment)
        if i in offload_after_segments or i == len(route) - 1:
            out = simulate(batch, design)
            for key in totals:
                if key == "peak_buffer_kg":
                    totals[key] = max(totals[key], getattr(out, key))
                else:
                    totals[key] += getattr(out, key)
            batch = []
    return RouteResult(**totals, capture_fraction=totals["captured_kg"] / totals["emitted_kg"])


def pareto_designs(route: list[RouteSegment], designs: list[SystemDesign]) -> list[tuple[SystemDesign, RouteResult]]:
    evaluated = [(d, simulate(route, d)) for d in designs]
    return [(d, r) for d, r in evaluated if not any(
        other.net_avoided_kg >= r.net_avoided_kg and od.system_mass_kg <= d.system_mass_kg and
        (other.net_avoided_kg > r.net_avoided_kg or od.system_mass_kg < d.system_mass_kg)
        for od, other in evaluated
    )]


def example_route() -> list[RouteSegment]:
    return [RouteSegment(20, .35, 35), RouteSegment(110, .72, 92),
            RouteSegment(35, .9, 65), RouteSegment(15, .2, 18)]


if __name__ == "__main__":
    print(json.dumps(asdict(simulate(example_route())), indent=2))

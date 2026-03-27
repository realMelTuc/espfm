"""Tests for EVE Online fuel burn rate calculations."""
import pytest
import sys
import os

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

# Import calculation functions directly — no DB needed
from db import (
    calculate_burn_rate,
    calculate_days_remaining,
    calculate_monthly_fuel_cost,
    STRUCTURE_BASE_BURN,
    SERVICE_PER_HOUR,
    STRUCTURE_TYPES,
)


# ─── Base burn rates ───────────────────────────────────────────────

class TestBaseBurnRates:
    def test_astrahus_base_burn(self):
        assert calculate_burn_rate('Astrahus', 0) == 24

    def test_fortizar_base_burn(self):
        assert calculate_burn_rate('Fortizar', 0) == 48

    def test_keepstar_base_burn(self):
        assert calculate_burn_rate('Keepstar', 0) == 96

    def test_raitaru_base_burn(self):
        assert calculate_burn_rate('Raitaru', 0) == 24

    def test_azbel_base_burn(self):
        assert calculate_burn_rate('Azbel', 0) == 48

    def test_sotiyo_base_burn(self):
        assert calculate_burn_rate('Sotiyo', 0) == 96

    def test_athanor_base_burn(self):
        assert calculate_burn_rate('Athanor', 0) == 24

    def test_tatara_base_burn(self):
        assert calculate_burn_rate('Tatara', 0) == 48

    def test_ansiblex_base_burn(self):
        assert calculate_burn_rate('Ansiblex Jump Gate', 0) == 30

    def test_pharolux_base_burn(self):
        assert calculate_burn_rate('Pharolux Cyno Beacon', 0) == 10

    def test_tenebrex_base_burn(self):
        assert calculate_burn_rate('Tenebrex Cyno Jammer', 0) == 30

    def test_custom_base_burn_zero(self):
        assert calculate_burn_rate('Custom', 0) == 0

    def test_unknown_type_returns_zero(self):
        """Unknown structure types return 0 base burn (graceful handling)."""
        assert calculate_burn_rate('Nonexistent Structure', 0) == 0


# ─── Service module modifiers ────────────────────────────────────────────

class TestServiceModifiers:
    def test_one_online_service_adds_10(self):
        base = STRUCTURE_BASE_BURN['Astrahus']
        assert calculate_burn_rate('Astrahus', 1) == base + 10

    def test_three_services_adds_30(self):
        base = STRUCTURE_BASE_BURN['Raitaru']
        assert calculate_burn_rate('Raitaru', 3) == base + 30

    def test_five_services(self):
        base = STRUCTURE_BASE_BURN['Fortizar']
        assert calculate_burn_rate('Fortizar', 5) == base + 50

    def test_zero_services_no_change(self):
        assert calculate_burn_rate('Keepstar', 0) == 96

    def test_service_per_hour_constant(self):
        assert SERVICE_PER_HOUR == 10

    def test_service_burn_formula(self):
        """burn_rate = base + services * 10"""
        for t, base in STRUCTURE_BASE_BURN.items():
            for n in range(6):
                expected = base + n * 10
                assert calculate_burn_rate(t, n) == expected, \
                    f'{t} with {n} services: expected {expected}'


# ─── Days remaining ─────────────────────────────────────────────────

class TestDaysRemaining:
    def test_basic_days(self):
        # 24 blocks/hr * 24h = 576/day; 576 blocks = 1 day
        result = calculate_days_remaining(576, 24)
        assert result == pytest.approx(1.0, rel=1e-3)

    def test_zero_burn_rate_returns_9999(self):
        assert calculate_days_remaining(10000, 0) == 9999.0

    def test_negative_burn_rate_returns_9999(self):
        assert calculate_days_remaining(10000, -5) == 9999.0

    def test_large_stock(self):
        # 50000 blocks at 24/hr → 50000/24/24 ≈ 86.8 days
        result = calculate_days_remaining(50000, 24)
        assert result == pytest.approx(50000 / 24 / 24, rel=1e-3)

    def test_zero_fuel_returns_zero(self):
        assert calculate_days_remaining(0, 24) == 0.0

    def test_fractional_days(self):
        # 12 blocks at 1/hr → 12/1/24 = 0.5 days
        result = calculate_days_remaining(12, 1)
        assert result == pytest.approx(0.5, rel=1e-3)

    def test_fortizar_five_services_30_days(self):
        # Fortizar (48/hr) + 5 services (50/hr) = 98/hr
        # 98*24 = 2352/day; for 30 days need 70560 blocks
        burn = calculate_burn_rate('Fortizar', 5)
        days = calculate_days_remaining(burn * 24 * 30, burn)
        assert days == pytest.approx(30.0, rel=1e-3)

    def test_astrahus_fuel_calculation_14_days(self):
        burn = calculate_burn_rate('Astrahus', 2)  # 24+20=44/hr
        fuel_needed = burn * 24 * 14
        days = calculate_days_remaining(fuel_needed, burn)
        assert days == pytest.approx(14.0, rel=1e-3)


# ─── Monthly fuel cost ─────────────────────────────────────────────

class TestMonthlyFuelCost:
    def test_zero_price_is_zero(self):
        assert calculate_monthly_fuel_cost(24, 0) == 0.0

    def test_basic_calculation(self):
        # 24 blocks/hr * 720 hrs/mo * 17500 ISK
        expected = 24 * 720 * 17500
        result = calculate_monthly_fuel_cost(24, 17500)
        assert result == pytest.approx(expected, rel=1e-6)

    def test_fortizar_with_services(self):
        burn = calculate_burn_rate('Fortizar', 3)  # 48+30 = 78
        cost = calculate_monthly_fuel_cost(burn, 20000)
        expected = 78 * 720 * 20000
        assert cost == pytest.approx(expected, rel=1e-6)

    def test_zero_burn_is_zero(self):
        assert calculate_monthly_fuel_cost(0, 100000) == 0.0

    def test_30_day_month(self):
        """Monthly cost uses 30-day month (720 hours)."""
        cost = calculate_monthly_fuel_cost(1, 1)
        assert cost == 720.0

    def test_high_value(self):
        # Keepstar + 10 services = 196/hr at 18000 ISK/block
        burn = calculate_burn_rate('Keepstar', 10)  # 96+100=196
        cost = calculate_monthly_fuel_cost(burn, 18000)
        assert cost == pytest.approx(196 * 720 * 18000, rel=1e-6)

    def test_result_is_rounded(self):
        """Result should be rounded to 2 decimal places."""
        cost = calculate_monthly_fuel_cost(1, 3)
        assert cost == round(1 * 720 * 3, 2)


# ─── Structure types completeness ───────────────────────────────────────

class TestStructureTypeConstants:
    def test_all_types_in_list(self):
        for t in ['Astrahus', 'Fortizar', 'Keepstar', 'Raitaru', 'Azbel', 'Sotiyo',
                  'Athanor', 'Tatara', 'Ansiblex Jump Gate', 'Pharolux Cyno Beacon',
                  'Tenebrex Cyno Jammer', 'Custom']:
            assert t in STRUCTURE_BASE_BURN, f'{t} missing from STRUCTURE_BASE_BURN'

    def test_structure_types_list_not_empty(self):
        assert len(STRUCTURE_TYPES) > 0

    def test_all_burn_values_non_negative(self):
        for t, v in STRUCTURE_BASE_BURN.items():
            assert v >= 0, f'{t} has negative burn rate'

    def test_xl_structures_burn_more_than_medium(self):
        assert STRUCTURE_BASE_BURN['Keepstar'] > STRUCTURE_BASE_BURN['Fortizar']
        assert STRUCTURE_BASE_BURN['Fortizar'] > STRUCTURE_BASE_BURN['Astrahus']
        assert STRUCTURE_BASE_BURN['Sotiyo'] > STRUCTURE_BASE_BURN['Azbel']
        assert STRUCTURE_BASE_BURN['Azbel'] > STRUCTURE_BASE_BURN['Raitaru']

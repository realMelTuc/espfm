"""Tests for profitability calculation logic."""
import pytest
import sys
import os

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from db import calculate_profitability, calculate_monthly_fuel_cost, calculate_burn_rate


class TestProfitabilityStatus:
    def test_profitable_when_income_exceeds_cost(self):
        status, profit = calculate_profitability(100_000_000, 500_000_000)
        assert status == 'profitable'
        assert profit == pytest.approx(400_000_000)

    def test_loss_when_cost_exceeds_income(self):
        status, profit = calculate_profitability(500_000_000, 100_000_000)
        assert status == 'loss'
        assert profit == pytest.approx(-400_000_000)

    def test_break_even_within_5_percent(self):
        # cost=100M, income=97M → deficit is 3% of cost → break_even
        status, profit = calculate_profitability(100_000_000, 97_000_000)
        assert status == 'break_even'
        assert profit == pytest.approx(-3_000_000)

    def test_break_even_exact_zero(self):
        status, profit = calculate_profitability(100_000_000, 100_000_000)
        assert status == 'profitable'
        assert profit == 0.0

    def test_idle_when_no_fuel_cost(self):
        status, profit = calculate_profitability(0, 0)
        assert status == 'idle'

    def test_idle_when_fuel_cost_zero_with_income(self):
        status, profit = calculate_profitability(0, 500_000_000)
        assert status == 'idle'

    def test_loss_exceeds_5_percent_threshold(self):
        # cost=100M, income=90M → 10% deficit → loss
        status, _ = calculate_profitability(100_000_000, 90_000_000)
        assert status == 'loss'

    def test_profit_value_is_signed(self):
        _, profit = calculate_profitability(200, 100)
        assert profit < 0

        _, profit = calculate_profitability(100, 200)
        assert profit > 0

    def test_large_isk_values(self):
        """Works with realistic EVE ISK amounts (billions)."""
        monthly_burn = calculate_burn_rate('Keepstar', 5) * 24 * 30  # blocks/mo
        monthly_cost = monthly_burn * 18000  # 18k ISK/block
        income = 10_000_000_000
        status, profit = calculate_profitability(monthly_cost, income)
        assert status == 'profitable'
        assert profit > 0

    def test_break_even_boundary_exactly_5_percent(self):
        # cost=1000, income=950 → 50/1000 = 5% exactly → loss (not < 0.05)
        status, _ = calculate_profitability(1000, 950)
        assert status == 'loss'

    def test_break_even_just_under_5_percent(self):
        # cost=1000, income=951 → abs(profit)=49, 49/1000=4.9% < 5% → break_even
        status, _ = calculate_profitability(1000, 951)
        assert status == 'break_even'

    def test_return_type_is_tuple(self):
        result = calculate_profitability(100, 200)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_profit_rounded_to_2_decimals(self):
        _, profit = calculate_profitability(100.3333, 200.6666)
        assert profit == round(200.6666 - 100.3333, 2)


class TestProfitabilityIntegration:
    """End-to-end profit calculations using real burn rates."""

    def test_astrahus_market_hub_scenario(self):
        """Astrahus market hub: 3 services, 500M/mo market tax."""
        burn = calculate_burn_rate('Astrahus', 3)  # 24 + 30 = 54/hr
        cost = calculate_monthly_fuel_cost(burn, 17_500)
        income = 500_000_000
        status, profit = calculate_profitability(cost, income)
        # Expected cost: 54 * 720 * 17500 = 680_400_000
        # That's more than 500M income → loss
        assert status == 'loss'

    def test_fortizar_high_tax_scenario(self):
        """Fortizar with 2 services, 2B/mo industry tax → profitable."""
        burn = calculate_burn_rate('Fortizar', 2)  # 48+20=68/hr
        cost = calculate_monthly_fuel_cost(burn, 17_500)
        income = 2_000_000_000
        status, profit = calculate_profitability(cost, income)
        assert status == 'profitable'
        assert profit > 0

    def test_athanor_no_services(self):
        """Athanor moon drill, no services, marginal income."""
        burn = calculate_burn_rate('Athanor', 0)  # 24/hr
        cost = calculate_monthly_fuel_cost(burn, 17_500)
        # cost = 24 * 720 * 17500 = 302_400_000
        # 300M income → slight loss but close to break_even
        status, _ = calculate_profitability(cost, 302_400_000)
        assert status in ('profitable', 'break_even')

    def test_keepstar_expensive_operation(self):
        """Keepstar + 8 services should always be expensive."""
        burn = calculate_burn_rate('Keepstar', 8)  # 96+80=176/hr
        cost = calculate_monthly_fuel_cost(burn, 20_000)
        # 176 * 720 * 20000 = 2,534,400,000 per month
        assert cost > 2_000_000_000

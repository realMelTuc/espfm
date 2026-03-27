"""Tests for structure validation and blueprint routes."""
import pytest
import sys
import os
import json
import unittest.mock as mock

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)


class TestStructureValidation:
    """Test the _validate() function from the structures blueprint."""

    def _validate(self, data):
        sys.path.insert(0, os.path.join(ROOT, 'blueprints'))
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'structures_bp', os.path.join(ROOT, 'blueprints', 'structures.py'))
        mod = importlib.util.module_from_spec(spec)
        with mock.patch.dict('sys.modules', {'db': mock.MagicMock(
            STRUCTURE_TYPES=['Astrahus','Fortizar','Keepstar','Raitaru','Azbel',
                             'Sotiyo','Athanor','Tatara','Ansiblex Jump Gate',
                             'Pharolux Cyno Beacon','Tenebrex Cyno Jammer','Custom'],
            FUEL_BLOCK_TYPES=['Caldari Fuel Blocks'],
            SECURITY_CLASSES=['highsec','lowsec','nullsec'],
            STRUCTURE_STATES=['online','offline'],
            calculate_burn_rate=lambda *a: 0,
            calculate_days_remaining=lambda *a: 0,
            calculate_monthly_fuel_cost=lambda *a: 0,
            calculate_profitability=lambda *a: ('loss', 0),
        )}):
            spec.loader.exec_module(mod)
        return mod._validate(data)

    def test_empty_name_is_invalid(self):
        errors = self._validate({'name': '', 'current_fuel': 0, 'fuel_bay_capacity': 50000})
        assert any('name' in e.lower() for e in errors)

    def test_whitespace_name_is_invalid(self):
        errors = self._validate({'name': '   ', 'current_fuel': 0, 'fuel_bay_capacity': 50000})
        assert any('name' in e.lower() for e in errors)

    def test_valid_minimal_structure(self):
        errors = self._validate({'name': 'Test', 'current_fuel': 0, 'fuel_bay_capacity': 50000})
        assert errors == []

    def test_negative_fuel_is_invalid(self):
        errors = self._validate({'name': 'Test', 'current_fuel': -1, 'fuel_bay_capacity': 50000})
        assert any('negative' in e.lower() or 'fuel' in e.lower() for e in errors)

    def test_non_numeric_fuel_is_invalid(self):
        errors = self._validate({'name': 'Test', 'current_fuel': 'lots', 'fuel_bay_capacity': 50000})
        assert len(errors) > 0

    def test_zero_capacity_is_invalid(self):
        errors = self._validate({'name': 'Test', 'current_fuel': 0, 'fuel_bay_capacity': 0})
        assert any('capacity' in e.lower() for e in errors)

    def test_negative_capacity_is_invalid(self):
        errors = self._validate({'name': 'Test', 'current_fuel': 0, 'fuel_bay_capacity': -100})
        assert len(errors) > 0

    def test_unknown_type_is_invalid(self):
        errors = self._validate({'name': 'Test', 'type_name': 'Battleship', 'current_fuel': 0, 'fuel_bay_capacity': 1})
        assert any('type' in e.lower() for e in errors)

    def test_known_type_is_valid(self):
        errors = self._validate({'name': 'Test', 'type_name': 'Astrahus', 'current_fuel': 0, 'fuel_bay_capacity': 1})
        assert errors == []

    def test_multiple_errors_returned(self):
        errors = self._validate({'name': '', 'current_fuel': -5, 'fuel_bay_capacity': 0})
        assert len(errors) >= 2


class TestAPIRoutes:
    """Test that API routes return correct HTTP status codes."""

    @pytest.fixture(autouse=True)
    def setup_app(self):
        os.environ['SUPABASE_DB_HOST'] = 'localhost'
        os.environ['SUPABASE_DB_NAME'] = 'test'
        os.environ['SUPABASE_DB_USER'] = 'test'
        os.environ['SUPABASE_DB_PASSWORD'] = 'test'
        os.environ['SECRET_KEY'] = 'test'

    def _make_client(self):
        import importlib.util
        fake_db = mock.MagicMock()
        fake_db.calculate_burn_rate = lambda *a: 24
        fake_db.calculate_days_remaining = lambda *a: 30.0
        fake_db.calculate_monthly_fuel_cost = lambda *a: 10_000_000
        fake_db.calculate_profitability = lambda *a: ('profitable', 5_000_000)
        fake_db.serialize_row = lambda r: dict(r)
        fake_db.STRUCTURE_TYPES = ['Astrahus', 'Fortizar']
        fake_db.FUEL_BLOCK_TYPES = ['Caldari Fuel Blocks']
        fake_db.SECURITY_CLASSES = ['highsec']
        fake_db.STRUCTURE_STATES = ['online']
        fake_db.INCOME_TYPES = ['industry_tax', 'other']
        fake_db.SERVICE_PER_HOUR = 10
        fake_db.STRUCTURE_BASE_BURN = {'Astrahus': 24}

        with mock.patch.dict('sys.modules', {'db': fake_db, 'pg8000': mock.MagicMock()}):
            spec = importlib.util.spec_from_file_location('app', os.path.join(ROOT, 'app.py'))
            app_mod = importlib.util.module_from_spec(spec)
            sys.modules['app'] = app_mod
            with mock.patch('dotenv.load_dotenv'):
                spec.loader.exec_module(app_mod)
            app_mod.app.config['TESTING'] = True
            return app_mod.app.test_client()

    def test_health_returns_200(self):
        client = self._make_client()
        r = client.get('/api/health')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data['status'] == 'ok'

    def test_debug_returns_200(self):
        client = self._make_client()
        r = client.get('/api/debug')
        assert r.status_code == 200

    def test_landing_page_returns_200(self):
        client = self._make_client()
        r = client.get('/')
        assert r.status_code == 200

    def test_app_shell_returns_200(self):
        client = self._make_client()
        r = client.get('/app/')
        assert r.status_code == 200

    def test_structures_meta_route_exists(self):
        client = self._make_client()
        r = client.get('/api/structures/meta')
        assert r.status_code == 200
        data = json.loads(r.data)
        assert 'types' in data

    def test_income_types_route_exists(self):
        client = self._make_client()
        r = client.get('/api/income/types')
        assert r.status_code == 200

    def test_service_types_route_exists(self):
        client = self._make_client()
        r = client.get('/api/services/types')
        assert r.status_code == 200

    def test_settings_constants_route_exists(self):
        client = self._make_client()
        r = client.get('/api/settings/constants')
        assert r.status_code == 200

    def test_partial_dashboard_returns_200(self):
        client = self._make_client()
        r = client.get('/dashboard/')
        assert r.status_code == 200

    def test_partial_structures_returns_200(self):
        client = self._make_client()
        r = client.get('/structures/')
        assert r.status_code == 200

    def test_partial_fuel_returns_200(self):
        client = self._make_client()
        r = client.get('/fuel/')
        assert r.status_code == 200

    def test_partial_income_returns_200(self):
        client = self._make_client()
        r = client.get('/income/')
        assert r.status_code == 200

    def test_partial_services_returns_200(self):
        client = self._make_client()
        r = client.get('/services/')
        assert r.status_code == 200

    def test_partial_profitability_returns_200(self):
        client = self._make_client()
        r = client.get('/profitability/')
        assert r.status_code == 200

    def test_partial_calendar_returns_200(self):
        client = self._make_client()
        r = client.get('/calendar/')
        assert r.status_code == 200

    def test_partial_settings_returns_200(self):
        client = self._make_client()
        r = client.get('/settings/')
        assert r.status_code == 200

    def test_partial_changelog_returns_200(self):
        client = self._make_client()
        r = client.get('/changelog/')
        assert r.status_code == 200

    def test_partial_support_returns_200(self):
        client = self._make_client()
        r = client.get('/support/')
        assert r.status_code == 200

    def test_structure_create_missing_name_returns_422(self):
        client = self._make_client()
        r = client.post('/api/structures',
            data=json.dumps({'name': '', 'fuel_bay_capacity': 50000}),
            content_type='application/json')
        assert r.status_code == 422

    def test_income_create_missing_struct_returns_422(self):
        client = self._make_client()
        r = client.post('/api/income',
            data=json.dumps({'amount': 1000000}),
            content_type='application/json')
        assert r.status_code == 422

    def test_service_create_missing_name_returns_422(self):
        client = self._make_client()
        r = client.post('/api/services',
            data=json.dumps({'structure_id': 1, 'name': ''}),
            content_type='application/json')
        assert r.status_code == 422

import sys
import os
import importlib.util
import pytest

# Add project root to path
ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)


def _load_module(name, rel_path):
    """Load a module from a file path, stubbing db so no connection is needed."""
    abs_path = os.path.join(ROOT, rel_path)
    spec = importlib.util.spec_from_file_location(name, abs_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope='session')
def db_module():
    """Load db.py with environment stubs (no real connection)."""
    os.environ.setdefault('SUPABASE_DB_HOST', 'localhost')
    os.environ.setdefault('SUPABASE_DB_NAME', 'test')
    os.environ.setdefault('SUPABASE_DB_USER', 'test')
    os.environ.setdefault('SUPABASE_DB_PASSWORD', 'test')
    return _load_module('db', 'db.py')


@pytest.fixture(scope='session')
def flask_app():
    """Create a Flask test app — blueprints loaded but db calls are not executed."""
    import unittest.mock as mock

    # Stub out pg8000 and dotenv so app.py imports cleanly
    with mock.patch.dict('os.environ', {
        'SUPABASE_DB_HOST': 'localhost',
        'SUPABASE_DB_NAME': 'test',
        'SUPABASE_DB_USER': 'test',
        'SUPABASE_DB_PASSWORD': 'test',
        'SECRET_KEY': 'test-secret',
    }):
        import pg8000
        with mock.patch.object(pg8000, 'connect', side_effect=Exception('no db in tests')):
            app_mod = _load_module('app', 'app.py')

    app_mod.app.config['TESTING'] = True
    return app_mod.app


@pytest.fixture
def client(flask_app):
    with flask_app.test_client() as c:
        yield c

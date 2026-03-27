import os
import sys
import traceback

try:
    from dotenv import load_dotenv
    from flask import Flask, jsonify, render_template, request
    from db import get_db, serialize_row
    load_dotenv('.env.espfm')
    _BOOT_ERROR = None
except Exception as _e:
    _BOOT_ERROR = traceback.format_exc()
    from flask import Flask, jsonify
    def get_db(): raise RuntimeError('DB not available')
    def render_template(*a, **kw): return f'<pre>Boot error:\n{_BOOT_ERROR}</pre>'
    def serialize_row(r): return r
    class _R:
        path = ''
        method = ''
        endpoint = ''
        headers = {}
        remote_addr = ''
    request = _R()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'espfm-dev-key')

if _BOOT_ERROR:
    @app.route('/')
    @app.route('/<path:p>')
    def boot_error(p=''):
        return f'<pre style="background:#0d1117;color:#ef4444;padding:20px;font-family:monospace">ESPFM Boot Error:\n\n{_BOOT_ERROR}</pre>', 500

@app.errorhandler(Exception)
def handle_global_error(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    error_msg = str(e)
    tb = traceback.format_exc()
    print(f"Error: {error_msg}\n{tb}", file=sys.stderr)
    if request.path.startswith('/api/'):
        return jsonify({'error': error_msg}), 500
    return f'<pre style="background:#0d1117;color:#ef4444;padding:20px">{error_msg}</pre>', 500

blueprints_dir = os.path.join(os.path.dirname(__file__), 'blueprints')
sys.path.insert(0, os.path.dirname(__file__))

_bp_errors = []
if not _BOOT_ERROR:
    import importlib.util
    for filename in sorted(os.listdir(blueprints_dir)):
        if filename.endswith('.py') and filename != '__init__.py':
            module_name = filename[:-3]
            try:
                spec = importlib.util.spec_from_file_location(
                    module_name, os.path.join(blueprints_dir, filename))
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                if hasattr(module, 'bp'):
                    app.register_blueprint(module.bp)
            except Exception as e:
                _bp_errors.append(f'{filename}: {e}')


@app.route('/')
def index():
    return render_template('landing.html')


@app.route('/app/')
def app_shell():
    return render_template('shell.html')


@app.route('/api/health')
def health_check():
    return jsonify({'status': 'ok', 'app': 'ESPFM', 'python': sys.version})


@app.route('/api/debug')
def debug_info():
    return jsonify({
        'boot_error': _BOOT_ERROR,
        'blueprint_errors': _bp_errors,
        'python': sys.version,
        'app': 'ESPFM'
    })


@app.route('/api/migrate', methods=['POST'])
def migrate():
    """Create all ESPFM tables if they don't exist."""
    conn = get_db()
    try:
        cur = conn.cursor()
        statements = [
            """CREATE TABLE IF NOT EXISTS espfm_structures (
                id SERIAL PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                type_name VARCHAR(100) NOT NULL DEFAULT 'Astrahus',
                system VARCHAR(100),
                region VARCHAR(100),
                security_class VARCHAR(20) DEFAULT 'highsec',
                owner_corp VARCHAR(200),
                state VARCHAR(20) DEFAULT 'online',
                fuel_type VARCHAR(50) DEFAULT 'Caldari Fuel Blocks',
                current_fuel INTEGER DEFAULT 0,
                fuel_bay_capacity INTEGER DEFAULT 50000,
                fuel_price_per_block NUMERIC(16,2) DEFAULT 0,
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS espfm_service_modules (
                id SERIAL PRIMARY KEY,
                structure_id INTEGER REFERENCES espfm_structures(id) ON DELETE CASCADE,
                name VARCHAR(200) NOT NULL,
                module_type VARCHAR(100),
                online BOOLEAN DEFAULT TRUE,
                extra_fuel_per_hour INTEGER DEFAULT 10,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS espfm_rigs (
                id SERIAL PRIMARY KEY,
                structure_id INTEGER REFERENCES espfm_structures(id) ON DELETE CASCADE,
                name VARCHAR(200) NOT NULL,
                rig_type VARCHAR(100),
                attribute_name VARCHAR(100),
                attribute_value NUMERIC(10,4) DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS espfm_fuel_snapshots (
                id SERIAL PRIMARY KEY,
                structure_id INTEGER REFERENCES espfm_structures(id) ON DELETE CASCADE,
                snapshot_date DATE DEFAULT CURRENT_DATE,
                fuel_amount INTEGER NOT NULL,
                burn_rate_per_hour NUMERIC(10,2),
                days_remaining NUMERIC(10,2),
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS espfm_income_entries (
                id SERIAL PRIMARY KEY,
                structure_id INTEGER REFERENCES espfm_structures(id) ON DELETE CASCADE,
                entry_date DATE DEFAULT CURRENT_DATE,
                amount NUMERIC(20,2) NOT NULL,
                income_type VARCHAR(50) DEFAULT 'other',
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS espfm_tax_entries (
                id SERIAL PRIMARY KEY,
                structure_id INTEGER REFERENCES espfm_structures(id) ON DELETE CASCADE,
                tax_type VARCHAR(100) NOT NULL,
                tax_rate NUMERIC(8,4),
                effective_date DATE DEFAULT CURRENT_DATE,
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS espfm_profitability_snapshots (
                id SERIAL PRIMARY KEY,
                structure_id INTEGER REFERENCES espfm_structures(id) ON DELETE CASCADE,
                snapshot_date DATE DEFAULT CURRENT_DATE,
                monthly_fuel_cost NUMERIC(20,2) DEFAULT 0,
                monthly_income NUMERIC(20,2) DEFAULT 0,
                monthly_profit NUMERIC(20,2) DEFAULT 0,
                status VARCHAR(20) DEFAULT 'loss',
                created_at TIMESTAMP DEFAULT NOW()
            )""",
        ]
        for stmt in statements:
            cur.execute(stmt)
        conn.commit()
        return jsonify({'ok': True, 'tables': 7})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5010, debug=os.environ.get('FLASK_DEBUG', '0') == '1', use_reloader=False)

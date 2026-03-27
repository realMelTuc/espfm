import os
import re
from dotenv import load_dotenv

load_dotenv('.env.espfm')

import pg8000


class DictCursor:
    """Wraps pg8000 cursor to return dict rows."""

    def __init__(self, conn):
        self._conn = conn
        self._cursor = conn.cursor()
        self._description = None

    def execute(self, query, params=None):
        if params and isinstance(params, dict):
            keys = []
            def replacer(m):
                key = m.group(1)
                keys.append(key)
                return f'${len(keys)}'
            query = re.sub(r'%\((\w+)\)s', replacer, query)
            params = tuple(params[k] for k in keys)
        elif params:
            counter = [0]
            def pos_replacer(m):
                counter[0] += 1
                return f'${counter[0]}'
            query = re.sub(r'(?<!%)%s', pos_replacer, query)
            if isinstance(params, (list, tuple)):
                params = tuple(params)
            else:
                params = (params,)

        if params:
            self._cursor.execute(query, params)
        else:
            self._cursor.execute(query)
        self._description = self._cursor.description

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return self._make_dict(row)

    def fetchall(self):
        rows = self._cursor.fetchall()
        return [self._make_dict(r) for r in rows]

    def _make_dict(self, row):
        if self._description:
            cols = [d[0] for d in self._description]
            return dict(zip(cols, row))
        return row

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def close(self):
        self._cursor.close()


class Connection:
    """Wraps pg8000 connection to provide psycopg2-compatible interface."""

    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return DictCursor(self._conn)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def get_db():
    """Get a database connection. Caller must call conn.close() when done."""
    import ssl
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    conn = pg8000.connect(
        host=os.environ['SUPABASE_DB_HOST'],
        database=os.environ['SUPABASE_DB_NAME'],
        user=os.environ['SUPABASE_DB_USER'],
        password=os.environ['SUPABASE_DB_PASSWORD'],
        port=int(os.environ.get('SUPABASE_DB_PORT', 5432)),
        ssl_context=ssl_context,
    )
    return Connection(conn)


def serialize_row(row):
    """Convert a database row to a JSON-safe dict."""
    from datetime import datetime, date
    from decimal import Decimal
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
        elif isinstance(v, date):
            d[k] = v.isoformat()
        elif isinstance(v, Decimal):
            d[k] = float(v)
    return d


# ─── EVE Online fuel burn constants ───

STRUCTURE_BASE_BURN = {
    'Astrahus': 24,
    'Fortizar': 48,
    'Keepstar': 96,
    'Raitaru': 24,
    'Azbel': 48,
    'Sotiyo': 96,
    'Athanor': 24,
    'Tatara': 48,
    'Ansiblex Jump Gate': 30,
    'Pharolux Cyno Beacon': 10,
    'Tenebrex Cyno Jammer': 30,
    'Custom': 0,
}

STRUCTURE_TYPES = list(STRUCTURE_BASE_BURN.keys())

FUEL_BLOCK_TYPES = [
    'Caldari Fuel Blocks',
    'Minmatar Fuel Blocks',
    'Amarr Fuel Blocks',
    'Gallente Fuel Blocks',
]

SECURITY_CLASSES = ['highsec', 'lowsec', 'nullsec', 'wormhole', 'pochven']

STRUCTURE_STATES = ['online', 'offline', 'abandoned', 'reinforced']

INCOME_TYPES = [
    'industry_tax',
    'market_tax',
    'reprocessing_tax',
    'moon_rental',
    'office_rental',
    'other',
]

SERVICE_PER_HOUR = 10  # fuel blocks per online service module


def calculate_burn_rate(type_name, online_service_count):
    """Fuel blocks per hour for a structure."""
    base = STRUCTURE_BASE_BURN.get(type_name, 0)
    return base + (online_service_count * SERVICE_PER_HOUR)


def calculate_days_remaining(current_fuel, burn_rate_per_hour):
    """Days of fuel left given current stock and burn rate."""
    if burn_rate_per_hour <= 0:
        return 9999.0
    return round(current_fuel / burn_rate_per_hour / 24, 2)


def calculate_monthly_fuel_cost(burn_rate_per_hour, fuel_price_per_block):
    """Monthly ISK cost of fuel (30-day month)."""
    monthly_blocks = burn_rate_per_hour * 24 * 30
    return round(monthly_blocks * fuel_price_per_block, 2)


def calculate_profitability(monthly_fuel_cost, monthly_income):
    """Returns (status, profit_isk)."""
    profit = monthly_income - monthly_fuel_cost
    if monthly_fuel_cost <= 0:
        status = 'idle'
    elif profit >= 0:
        status = 'profitable'
    elif monthly_fuel_cost > 0 and abs(profit) / monthly_fuel_cost < 0.05:
        status = 'break_even'
    else:
        status = 'loss'
    return status, round(profit, 2)

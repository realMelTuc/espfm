from flask import Blueprint, render_template, jsonify, request
from db import get_db, serialize_row, calculate_burn_rate, calculate_days_remaining

bp = Blueprint('fuel', __name__)


@bp.route('/fuel/')
def index():
    return render_template('partials/fuel/index.html')


@bp.route('/api/fuel/summary')
def api_summary():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT s.id, s.name, s.type_name, s.system, s.state,
                   s.current_fuel, s.fuel_bay_capacity, s.fuel_type,
                   s.fuel_price_per_block,
                   COALESCE(svc.online_count, 0) AS online_service_count
            FROM espfm_structures s
            LEFT JOIN (
                SELECT structure_id, COUNT(*) FILTER (WHERE online) AS online_count
                FROM espfm_service_modules
                GROUP BY structure_id
            ) svc ON svc.structure_id = s.id
            WHERE s.state = 'online'
            ORDER BY s.name
        """)
        rows = cur.fetchall()
        result = []
        for r in rows:
            s = serialize_row(r)
            burn = calculate_burn_rate(s['type_name'], s['online_service_count'])
            days = calculate_days_remaining(s['current_fuel'], burn)
            cap = s['fuel_bay_capacity'] or 1
            fill_pct = round(min(s['current_fuel'] / cap * 100, 100), 1)
            s['burn_rate'] = burn
            s['days_remaining'] = days
            s['fill_pct'] = fill_pct
            s['daily_burn'] = burn * 24
            s['weekly_burn'] = burn * 24 * 7
            result.append(s)
        return jsonify(result)
    finally:
        conn.close()


@bp.route('/api/fuel/<int:struct_id>/snapshots')
def api_snapshots(struct_id):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM espfm_fuel_snapshots
            WHERE structure_id = %s
            ORDER BY snapshot_date DESC
            LIMIT 60
        """, [struct_id])
        return jsonify([serialize_row(r) for r in cur.fetchall()])
    finally:
        conn.close()


@bp.route('/api/fuel/<int:struct_id>/snapshot', methods=['POST'])
def api_record_snapshot(struct_id):
    data = request.get_json(force=True) or {}
    conn = get_db()
    try:
        # Get structure to compute burn rate
        cur = conn.cursor()
        cur.execute("""
            SELECT s.type_name,
                   COALESCE(svc.online_count, 0) AS online_service_count
            FROM espfm_structures s
            LEFT JOIN (
                SELECT structure_id, COUNT(*) FILTER (WHERE online) AS online_count
                FROM espfm_service_modules
                GROUP BY structure_id
            ) svc ON svc.structure_id = s.id
            WHERE s.id = %s
        """, [struct_id])
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Structure not found'}), 404

        fuel_amount = int(data.get('fuel_amount', 0))
        burn = calculate_burn_rate(row['type_name'], row['online_service_count'])
        days = calculate_days_remaining(fuel_amount, burn)

        cur.execute("""
            INSERT INTO espfm_fuel_snapshots
                (structure_id, snapshot_date, fuel_amount, burn_rate_per_hour, days_remaining)
            VALUES (%s, CURRENT_DATE, %s, %s, %s)
            RETURNING id
        """, [struct_id, fuel_amount, burn, days])
        row2 = cur.fetchone()

        # Also update current_fuel on the structure
        cur.execute(
            'UPDATE espfm_structures SET current_fuel=%s, updated_at=NOW() WHERE id=%s',
            [fuel_amount, struct_id]
        )
        conn.commit()
        return jsonify({'ok': True, 'id': row2['id'], 'burn_rate': burn, 'days_remaining': days})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@bp.route('/api/fuel/<int:struct_id>/burnrate')
def api_burnrate(struct_id):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT s.type_name, s.current_fuel,
                   COALESCE(svc.online_count, 0) AS online_service_count
            FROM espfm_structures s
            LEFT JOIN (
                SELECT structure_id, COUNT(*) FILTER (WHERE online) AS online_count
                FROM espfm_service_modules
                GROUP BY structure_id
            ) svc ON svc.structure_id = s.id
            WHERE s.id = %s
        """, [struct_id])
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404

        burn = calculate_burn_rate(row['type_name'], row['online_service_count'])
        days = calculate_days_remaining(row['current_fuel'], burn)
        return jsonify({
            'burn_rate_per_hour': burn,
            'burn_rate_per_day': burn * 24,
            'burn_rate_per_week': burn * 24 * 7,
            'burn_rate_per_month': burn * 24 * 30,
            'days_remaining': days,
            'current_fuel': row['current_fuel'],
        })
    finally:
        conn.close()


@bp.route('/api/fuel/calendar')
def api_calendar():
    """Returns fuel run-out dates for all online structures."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT s.id, s.name, s.system, s.current_fuel,
                   COALESCE(svc.online_count, 0) AS online_service_count,
                   s.type_name
            FROM espfm_structures s
            LEFT JOIN (
                SELECT structure_id, COUNT(*) FILTER (WHERE online) AS online_count
                FROM espfm_service_modules
                GROUP BY structure_id
            ) svc ON svc.structure_id = s.id
            WHERE s.state = 'online'
        """)
        import datetime
        today = datetime.date.today()
        events = []
        for r in cur.fetchall():
            s = serialize_row(r)
            burn = calculate_burn_rate(s['type_name'], s['online_service_count'])
            days = calculate_days_remaining(s['current_fuel'], burn)
            if days < 9999:
                runout = today + datetime.timedelta(days=days)
                events.append({
                    'structure_id': s['id'],
                    'name': s['name'],
                    'system': s['system'],
                    'days_remaining': days,
                    'runout_date': runout.isoformat(),
                    'alert': days < 7,
                })
        events.sort(key=lambda x: x['days_remaining'])
        return jsonify(events)
    finally:
        conn.close()

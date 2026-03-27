from flask import Blueprint, render_template, jsonify
from db import get_db, serialize_row, calculate_burn_rate, calculate_days_remaining

bp = Blueprint('calendar_view', __name__)


@bp.route('/calendar/')
def index():
    return render_template('partials/calendar/index.html')


@bp.route('/api/calendar/events')
def api_events():
    """Fuel run-out dates + replenishment schedule for calendar view."""
    import datetime
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT s.id, s.name, s.system, s.type_name,
                   s.current_fuel, s.fuel_bay_capacity,
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
        today = datetime.date.today()
        events = []
        for r in cur.fetchall():
            s = serialize_row(r)
            burn = calculate_burn_rate(s['type_name'], s['online_service_count'])
            days = calculate_days_remaining(s['current_fuel'], burn)

            if days < 9999:
                runout = today + datetime.timedelta(days=days)
                # Alert at 7 days prior
                alert_date = runout - datetime.timedelta(days=7)
                events.append({
                    'type': 'runout',
                    'structure_id': s['id'],
                    'name': s['name'],
                    'system': s['system'],
                    'date': runout.isoformat(),
                    'days_remaining': round(days, 1),
                    'severity': 'danger' if days < 3 else ('warning' if days < 7 else 'info'),
                })
                if alert_date >= today:
                    events.append({
                        'type': 'alert',
                        'structure_id': s['id'],
                        'name': s['name'],
                        'system': s['system'],
                        'date': alert_date.isoformat(),
                        'days_remaining': round(days, 1),
                        'severity': 'warning',
                    })

        events.sort(key=lambda x: x['date'])
        return jsonify(events)
    finally:
        conn.close()

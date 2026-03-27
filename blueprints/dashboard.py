from flask import Blueprint, render_template, jsonify
from db import get_db, serialize_row, calculate_burn_rate, calculate_days_remaining, calculate_monthly_fuel_cost, calculate_profitability

bp = Blueprint('dashboard', __name__)


@bp.route('/dashboard/')
def index():
    return render_template('partials/dashboard/index.html')


@bp.route('/api/dashboard/summary')
def api_summary():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT s.*,
                   COALESCE(svc.online_count, 0) AS online_service_count,
                   COALESCE(inc.monthly_income, 0) AS monthly_income
            FROM espfm_structures s
            LEFT JOIN (
                SELECT structure_id, COUNT(*) FILTER (WHERE online) AS online_count
                FROM espfm_service_modules
                GROUP BY structure_id
            ) svc ON svc.structure_id = s.id
            LEFT JOIN (
                SELECT structure_id,
                       SUM(amount) AS monthly_income
                FROM espfm_income_entries
                WHERE entry_date >= CURRENT_DATE - INTERVAL '30 days'
                GROUP BY structure_id
            ) inc ON inc.structure_id = s.id
            ORDER BY s.name
        """)
        structures = [serialize_row(r) for r in cur.fetchall()]

        enriched = []
        total_structures = len(structures)
        at_risk = 0
        offline_count = 0
        total_monthly_cost = 0.0

        for s in structures:
            burn = calculate_burn_rate(s['type_name'], s['online_service_count'])
            days = calculate_days_remaining(s['current_fuel'], burn)
            monthly_cost = calculate_monthly_fuel_cost(burn, float(s['fuel_price_per_block'] or 0))
            status, profit = calculate_profitability(monthly_cost, float(s['monthly_income'] or 0))

            s['burn_rate'] = burn
            s['days_remaining'] = days
            s['monthly_fuel_cost'] = monthly_cost
            s['monthly_profit'] = profit
            s['profit_status'] = status

            if s['state'] in ('offline', 'abandoned'):
                offline_count += 1
            elif days < 7:
                at_risk += 1

            total_monthly_cost += monthly_cost
            enriched.append(s)

        at_risk_list = sorted(
            [s for s in enriched if s['state'] == 'online' and s['days_remaining'] < 14],
            key=lambda x: x['days_remaining']
        )
        profitable_list = sorted(
            [s for s in enriched if s['profit_status'] == 'profitable'],
            key=lambda x: x['monthly_profit'],
            reverse=True
        )[:5]

        return jsonify({
            'total_structures': total_structures,
            'at_risk': at_risk,
            'offline': offline_count,
            'total_monthly_cost': round(total_monthly_cost, 2),
            'structures': enriched,
            'at_risk_list': at_risk_list[:10],
            'top_profitable': profitable_list,
        })
    finally:
        conn.close()

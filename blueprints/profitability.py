from flask import Blueprint, render_template, jsonify, request
from db import (get_db, serialize_row, calculate_burn_rate,
                calculate_monthly_fuel_cost, calculate_profitability)

bp = Blueprint('profitability', __name__)


@bp.route('/profitability/')
def index():
    return render_template('partials/profitability/index.html')


@bp.route('/api/profitability/summary')
def api_summary():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT s.id, s.name, s.type_name, s.system, s.state,
                   s.fuel_price_per_block,
                   COALESCE(svc.online_count, 0) AS online_service_count,
                   COALESCE(inc.monthly_income, 0) AS monthly_income
            FROM espfm_structures s
            LEFT JOIN (
                SELECT structure_id, COUNT(*) FILTER (WHERE online) AS online_count
                FROM espfm_service_modules
                GROUP BY structure_id
            ) svc ON svc.structure_id = s.id
            LEFT JOIN (
                SELECT structure_id, SUM(amount) AS monthly_income
                FROM espfm_income_entries
                WHERE entry_date >= CURRENT_DATE - INTERVAL '30 days'
                GROUP BY structure_id
            ) inc ON inc.structure_id = s.id
            ORDER BY s.name
        """)
        rows = cur.fetchall()
        result = []
        for r in rows:
            s = serialize_row(r)
            burn = calculate_burn_rate(s['type_name'], s['online_service_count'])
            monthly_cost = calculate_monthly_fuel_cost(burn, float(s['fuel_price_per_block'] or 0))
            income = float(s['monthly_income'] or 0)
            status, profit = calculate_profitability(monthly_cost, income)
            result.append({
                'id': s['id'],
                'name': s['name'],
                'type_name': s['type_name'],
                'system': s['system'],
                'state': s['state'],
                'burn_rate': burn,
                'monthly_fuel_cost': monthly_cost,
                'monthly_income': income,
                'monthly_profit': profit,
                'profit_status': status,
                'margin_pct': round(profit / monthly_cost * 100, 1) if monthly_cost > 0 else 0,
            })
        return jsonify(result)
    finally:
        conn.close()


@bp.route('/api/profitability/<int:struct_id>/snapshot', methods=['POST'])
def api_snapshot(struct_id):
    """Record current profitability as a snapshot."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT s.type_name, s.fuel_price_per_block,
                   COALESCE(svc.online_count, 0) AS online_service_count,
                   COALESCE(inc.monthly_income, 0) AS monthly_income
            FROM espfm_structures s
            LEFT JOIN (
                SELECT structure_id, COUNT(*) FILTER (WHERE online) AS online_count
                FROM espfm_service_modules
                GROUP BY structure_id
            ) svc ON svc.structure_id = s.id
            LEFT JOIN (
                SELECT structure_id, SUM(amount) AS monthly_income
                FROM espfm_income_entries
                WHERE entry_date >= CURRENT_DATE - INTERVAL '30 days'
                GROUP BY structure_id
            ) inc ON inc.structure_id = s.id
            WHERE s.id = %s
        """, [struct_id])
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404

        burn = calculate_burn_rate(row['type_name'], row['online_service_count'])
        cost = calculate_monthly_fuel_cost(burn, float(row['fuel_price_per_block'] or 0))
        income = float(row['monthly_income'] or 0)
        status, profit = calculate_profitability(cost, income)

        cur.execute("""
            INSERT INTO espfm_profitability_snapshots
                (structure_id, snapshot_date, monthly_fuel_cost, monthly_income, monthly_profit, status)
            VALUES (%s, CURRENT_DATE, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            RETURNING id
        """, [struct_id, cost, income, profit, status])
        r2 = cur.fetchone()
        conn.commit()
        return jsonify({
            'ok': True,
            'id': r2['id'] if r2 else None,
            'monthly_fuel_cost': cost,
            'monthly_income': income,
            'monthly_profit': profit,
            'status': status,
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@bp.route('/api/profitability/<int:struct_id>/history')
def api_history(struct_id):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM espfm_profitability_snapshots
            WHERE structure_id = %s
            ORDER BY snapshot_date DESC
            LIMIT 90
        """, [struct_id])
        return jsonify([serialize_row(r) for r in cur.fetchall()])
    finally:
        conn.close()

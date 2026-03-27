from flask import Blueprint, render_template, jsonify, request
from db import get_db, serialize_row, INCOME_TYPES

bp = Blueprint('income', __name__)


@bp.route('/income/')
def index():
    return render_template('partials/income/index.html')


@bp.route('/api/income', methods=['GET'])
def api_list():
    conn = get_db()
    try:
        cur = conn.cursor()
        struct_id = request.args.get('structure_id')
        if struct_id:
            cur.execute("""
                SELECT e.*, s.name AS structure_name
                FROM espfm_income_entries e
                JOIN espfm_structures s ON s.id = e.structure_id
                WHERE e.structure_id = %s
                ORDER BY e.entry_date DESC, e.id DESC
                LIMIT 200
            """, [int(struct_id)])
        else:
            cur.execute("""
                SELECT e.*, s.name AS structure_name
                FROM espfm_income_entries e
                JOIN espfm_structures s ON s.id = e.structure_id
                ORDER BY e.entry_date DESC, e.id DESC
                LIMIT 200
            """)
        return jsonify([serialize_row(r) for r in cur.fetchall()])
    finally:
        conn.close()


@bp.route('/api/income/summary')
def api_summary():
    """Monthly income totals by structure and type."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT s.id, s.name AS structure_name,
                   e.income_type,
                   SUM(e.amount) AS total_amount,
                   COUNT(*) AS entry_count
            FROM espfm_income_entries e
            JOIN espfm_structures s ON s.id = e.structure_id
            WHERE e.entry_date >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY s.id, s.name, e.income_type
            ORDER BY s.name, e.income_type
        """)
        return jsonify([serialize_row(r) for r in cur.fetchall()])
    finally:
        conn.close()


@bp.route('/api/income/trend')
def api_trend():
    """Daily income totals for the last 90 days."""
    conn = get_db()
    try:
        cur = conn.cursor()
        struct_id = request.args.get('structure_id')
        if struct_id:
            cur.execute("""
                SELECT entry_date, SUM(amount) AS daily_total, income_type
                FROM espfm_income_entries
                WHERE structure_id = %s
                  AND entry_date >= CURRENT_DATE - INTERVAL '90 days'
                GROUP BY entry_date, income_type
                ORDER BY entry_date
            """, [int(struct_id)])
        else:
            cur.execute("""
                SELECT entry_date, SUM(amount) AS daily_total
                FROM espfm_income_entries
                WHERE entry_date >= CURRENT_DATE - INTERVAL '90 days'
                GROUP BY entry_date
                ORDER BY entry_date
            """)
        return jsonify([serialize_row(r) for r in cur.fetchall()])
    finally:
        conn.close()


@bp.route('/api/income', methods=['POST'])
def api_create():
    data = request.get_json(force=True) or {}
    errors = []
    if not data.get('structure_id'):
        errors.append('Structure is required.')
    try:
        amount = float(data.get('amount', 0))
        if amount <= 0:
            errors.append('Amount must be greater than zero.')
    except (ValueError, TypeError):
        errors.append('Amount must be a number.')
    if data.get('income_type') and data['income_type'] not in INCOME_TYPES:
        errors.append(f"Unknown income type: {data['income_type']}")
    if errors:
        return jsonify({'errors': errors}), 422

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO espfm_income_entries
                (structure_id, entry_date, amount, income_type, notes)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, [
            int(data['structure_id']),
            data.get('entry_date') or 'CURRENT_DATE',
            amount,
            data.get('income_type', 'other'),
            data.get('notes', ''),
        ])
        row = cur.fetchone()
        conn.commit()
        return jsonify({'ok': True, 'id': row['id']}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@bp.route('/api/income/<int:entry_id>', methods=['DELETE'])
def api_delete(entry_id):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute('DELETE FROM espfm_income_entries WHERE id=%s', [entry_id])
        conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@bp.route('/api/income/types')
def api_types():
    return jsonify(INCOME_TYPES)

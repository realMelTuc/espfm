from flask import Blueprint, render_template, jsonify, request
from db import (get_db, serialize_row, STRUCTURE_TYPES, FUEL_BLOCK_TYPES,
                SECURITY_CLASSES, STRUCTURE_STATES,
                calculate_burn_rate, calculate_days_remaining,
                calculate_monthly_fuel_cost, calculate_profitability)

bp = Blueprint('structures', __name__)


@bp.route('/structures/')
def index():
    return render_template('partials/structures/index.html')


@bp.route('/api/structures', methods=['GET'])
def api_list():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT s.*,
                   COALESCE(svc.online_count, 0) AS online_service_count,
                   COALESCE(svc.total_count, 0) AS total_service_count
            FROM espfm_structures s
            LEFT JOIN (
                SELECT structure_id,
                       COUNT(*) AS total_count,
                       COUNT(*) FILTER (WHERE online) AS online_count
                FROM espfm_service_modules
                GROUP BY structure_id
            ) svc ON svc.structure_id = s.id
            ORDER BY s.name
        """)
        rows = cur.fetchall()
        result = []
        for r in rows:
            s = serialize_row(r)
            burn = calculate_burn_rate(s['type_name'], s['online_service_count'])
            days = calculate_days_remaining(s['current_fuel'], burn)
            s['burn_rate'] = burn
            s['days_remaining'] = days
            result.append(s)
        return jsonify(result)
    finally:
        conn.close()


@bp.route('/api/structures/<int:struct_id>', methods=['GET'])
def api_get(struct_id):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT s.*,
                   COALESCE(svc.online_count, 0) AS online_service_count,
                   COALESCE(svc.total_count, 0) AS total_service_count
            FROM espfm_structures s
            LEFT JOIN (
                SELECT structure_id,
                       COUNT(*) AS total_count,
                       COUNT(*) FILTER (WHERE online) AS online_count
                FROM espfm_service_modules
                GROUP BY structure_id
            ) svc ON svc.structure_id = s.id
            WHERE s.id = %s
        """, [struct_id])
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        s = serialize_row(row)
        burn = calculate_burn_rate(s['type_name'], s['online_service_count'])
        s['burn_rate'] = burn
        s['days_remaining'] = calculate_days_remaining(s['current_fuel'], burn)
        return jsonify(s)
    finally:
        conn.close()


@bp.route('/api/structures', methods=['POST'])
def api_create():
    data = request.get_json(force=True) or {}
    errors = _validate(data)
    if errors:
        return jsonify({'errors': errors}), 422

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO espfm_structures
                (name, type_name, system, region, security_class, owner_corp,
                 state, fuel_type, current_fuel, fuel_bay_capacity,
                 fuel_price_per_block, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, [
            data['name'].strip(),
            data.get('type_name', 'Astrahus'),
            data.get('system', ''),
            data.get('region', ''),
            data.get('security_class', 'highsec'),
            data.get('owner_corp', ''),
            data.get('state', 'online'),
            data.get('fuel_type', 'Caldari Fuel Blocks'),
            int(data.get('current_fuel', 0)),
            int(data.get('fuel_bay_capacity', 50000)),
            float(data.get('fuel_price_per_block', 0)),
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


@bp.route('/api/structures/<int:struct_id>', methods=['PUT'])
def api_update(struct_id):
    data = request.get_json(force=True) or {}
    errors = _validate(data)
    if errors:
        return jsonify({'errors': errors}), 422

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE espfm_structures SET
                name=%s, type_name=%s, system=%s, region=%s,
                security_class=%s, owner_corp=%s, state=%s,
                fuel_type=%s, current_fuel=%s, fuel_bay_capacity=%s,
                fuel_price_per_block=%s, notes=%s, updated_at=NOW()
            WHERE id=%s
        """, [
            data['name'].strip(),
            data.get('type_name', 'Astrahus'),
            data.get('system', ''),
            data.get('region', ''),
            data.get('security_class', 'highsec'),
            data.get('owner_corp', ''),
            data.get('state', 'online'),
            data.get('fuel_type', 'Caldari Fuel Blocks'),
            int(data.get('current_fuel', 0)),
            int(data.get('fuel_bay_capacity', 50000)),
            float(data.get('fuel_price_per_block', 0)),
            data.get('notes', ''),
            struct_id,
        ])
        conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@bp.route('/api/structures/<int:struct_id>', methods=['DELETE'])
def api_delete(struct_id):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute('DELETE FROM espfm_structures WHERE id=%s', [struct_id])
        conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@bp.route('/api/structures/meta')
def api_meta():
    return jsonify({
        'types': STRUCTURE_TYPES,
        'fuel_blocks': FUEL_BLOCK_TYPES,
        'security_classes': SECURITY_CLASSES,
        'states': STRUCTURE_STATES,
    })


def _validate(data):
    errors = []
    if not data.get('name', '').strip():
        errors.append('Structure name is required.')
    if data.get('type_name') and data['type_name'] not in STRUCTURE_TYPES:
        errors.append(f"Unknown structure type: {data['type_name']}")
    try:
        fuel = int(data.get('current_fuel', 0))
        if fuel < 0:
            errors.append('Current fuel cannot be negative.')
    except (ValueError, TypeError):
        errors.append('Current fuel must be a number.')
    try:
        cap = int(data.get('fuel_bay_capacity', 50000))
        if cap <= 0:
            errors.append('Fuel bay capacity must be positive.')
    except (ValueError, TypeError):
        errors.append('Fuel bay capacity must be a number.')
    return errors

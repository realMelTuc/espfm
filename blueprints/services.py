from flask import Blueprint, render_template, jsonify, request
from db import get_db, serialize_row

bp = Blueprint('services', __name__)

SERVICE_MODULE_TYPES = [
    'Standup Reprocessing Facility I',
    'Standup Manufacturing Plant I',
    'Standup Research Lab I',
    'Standup Market Hub I',
    'Standup Moon Drill I',
    'Standup Cloning Center I',
    'Standup Accelerator I',
    'Standup Hyasyoda Research Center',
    'Standup Invention Lab I',
    'Standup Copy Lab I',
    'Standup Material Efficiency Research Lab I',
    'Standup Time Efficiency Research Lab I',
    'Standup Blueprint Library I',
    'Custom Service Module',
]


@bp.route('/services/')
def index():
    return render_template('partials/services/index.html')


@bp.route('/api/services')
def api_list_all():
    """List all service modules grouped by structure."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT m.*, s.name AS structure_name, s.type_name AS structure_type
            FROM espfm_service_modules m
            JOIN espfm_structures s ON s.id = m.structure_id
            ORDER BY s.name, m.name
        """)
        return jsonify([serialize_row(r) for r in cur.fetchall()])
    finally:
        conn.close()


@bp.route('/api/services/<int:struct_id>')
def api_list(struct_id):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM espfm_service_modules
            WHERE structure_id = %s
            ORDER BY name
        """, [struct_id])
        return jsonify([serialize_row(r) for r in cur.fetchall()])
    finally:
        conn.close()


@bp.route('/api/services', methods=['POST'])
def api_create():
    data = request.get_json(force=True) or {}
    errors = []
    if not data.get('structure_id'):
        errors.append('Structure is required.')
    if not data.get('name', '').strip():
        errors.append('Module name is required.')
    if errors:
        return jsonify({'errors': errors}), 422

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO espfm_service_modules
                (structure_id, name, module_type, online, extra_fuel_per_hour)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, [
            int(data['structure_id']),
            data['name'].strip(),
            data.get('module_type', 'Custom Service Module'),
            bool(data.get('online', True)),
            int(data.get('extra_fuel_per_hour', 10)),
        ])
        row = cur.fetchone()
        conn.commit()
        return jsonify({'ok': True, 'id': row['id']}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@bp.route('/api/services/<int:module_id>', methods=['PUT'])
def api_update(module_id):
    data = request.get_json(force=True) or {}
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE espfm_service_modules
            SET name=%s, module_type=%s, online=%s, extra_fuel_per_hour=%s
            WHERE id=%s
        """, [
            data.get('name', '').strip() or None,
            data.get('module_type', 'Custom Service Module'),
            bool(data.get('online', True)),
            int(data.get('extra_fuel_per_hour', 10)),
            module_id,
        ])
        conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@bp.route('/api/services/<int:module_id>/toggle', methods=['POST'])
def api_toggle(module_id):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE espfm_service_modules
            SET online = NOT online
            WHERE id=%s
            RETURNING online
        """, [module_id])
        row = cur.fetchone()
        conn.commit()
        return jsonify({'ok': True, 'online': row['online'] if row else None})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@bp.route('/api/services/<int:module_id>', methods=['DELETE'])
def api_delete(module_id):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute('DELETE FROM espfm_service_modules WHERE id=%s', [module_id])
        conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@bp.route('/api/services/types')
def api_types():
    return jsonify(SERVICE_MODULE_TYPES)

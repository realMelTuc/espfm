from flask import Blueprint, render_template, jsonify, request
from db import get_db, serialize_row, STRUCTURE_BASE_BURN, SERVICE_PER_HOUR

bp = Blueprint('settings', __name__)


@bp.route('/settings/')
def index():
    return render_template('partials/settings/index.html')


@bp.route('/api/settings/constants')
def api_constants():
    return jsonify({
        'structure_base_burn': STRUCTURE_BASE_BURN,
        'service_per_hour': SERVICE_PER_HOUR,
    })


@bp.route('/api/settings/bulk-fuel-price', methods=['POST'])
def api_bulk_fuel_price():
    """Set fuel price per block across all structures."""
    data = request.get_json(force=True) or {}
    try:
        price = float(data.get('fuel_price_per_block', 0))
        if price < 0:
            return jsonify({'error': 'Price cannot be negative.'}), 422
    except (ValueError, TypeError):
        return jsonify({'error': 'Price must be a number.'}), 422

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute('UPDATE espfm_structures SET fuel_price_per_block=%s', [price])
        conn.commit()
        return jsonify({'ok': True, 'updated': cur.rowcount, 'price': price})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

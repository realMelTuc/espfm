from flask import Blueprint, render_template

bp = Blueprint('support', __name__)


@bp.route('/support/')
def index():
    return render_template('partials/support/index.html')

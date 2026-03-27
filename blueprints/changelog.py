from flask import Blueprint, render_template

bp = Blueprint('changelog', __name__)


@bp.route('/changelog/')
def index():
    return render_template('partials/changelog/index.html')

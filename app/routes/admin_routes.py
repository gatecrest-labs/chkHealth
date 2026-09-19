from flask import Blueprint, render_template
from app.decorators import admin_required

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/")
@admin_required
def admin_page():
    return render_template("admin/index.html")

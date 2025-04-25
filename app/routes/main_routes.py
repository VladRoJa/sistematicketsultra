#C:\Users\Vladimir\Documents\Sistema tickets\app\routes\main_routes.pyapp/routes/main_routes.py


from flask import Blueprint, render_template

# ------------------------------------------------------------------------------
# BLUEPRINT: RUTA PRINCIPAL
# ------------------------------------------------------------------------------


main_bp = Blueprint('main', __name__)

# ------------------------------------------------------------------------------
# RUTA: Página de inicio
# ------------------------------------------------------------------------------
@main_bp.route('/')
def index():
    return render_template('index.html')
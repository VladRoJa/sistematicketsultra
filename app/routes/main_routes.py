#app/routes/main_routes.py


from flask import Blueprint, render_template

main_bp = Blueprint('main', __name__)

@main_bp.route('/')  # Define la ruta para la raíz "/"
def index():
    return render_template ('index.html') # O renderiza un template HTML
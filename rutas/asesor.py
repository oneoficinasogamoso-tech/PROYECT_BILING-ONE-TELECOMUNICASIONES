from flask import Blueprint, render_template, session, redirect, url_for, flash

asesor_bp = Blueprint('asesor', __name__, url_prefix='/asesor')


def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Debe iniciar sesión primero', 'error')
            return redirect(url_for('login.login'))
        if session.get('rol') != 'ASESOR':
            flash('No tiene permisos para acceder a esta página', 'error')
            return redirect(url_for('login.login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@asesor_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('asesor/dashboard.html', nombre=session.get('nombre'))
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import mysql.connector
from config import Config
import bcrypt

login_bp = Blueprint('login', __name__)

# Función para conectar a la base de datos
def get_db_connection():
    connection = mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB
    )
    return connection

@login_bp.route('/')
@login_bp.route('/login')
def login():
    return render_template('login.html')

@login_bp.route('/login', methods=['POST'])
def login_post():
    usuario = request.form.get('usuario')
    contraseña = request.form.get('contraseña')
    
    if not usuario or not contraseña:
        flash('Por favor complete todos los campos', 'error')
        return redirect(url_for('login.login'))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Buscar usuario en la base de datos
        query = "SELECT * FROM usuarios WHERE usuario = %s"
        cursor.execute(query, (usuario,))
        user = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if user and user['contraseña'] == contraseña:  # Por ahora sin hash
            # Guardar información en la sesión
            session['user_id'] = user['id']
            session['nombre'] = user['nombre']
            session['usuario'] = user['usuario']
            session['rol'] = user['rol']
            
            # Redirigir según el rol
            if user['rol'] == 'ADMIN':
                return redirect(url_for('admin.dashboard'))
            elif user['rol'] == 'AUXILIAR':
                return redirect(url_for('auxiliar.dashboard'))
            elif user['rol'] == 'ASESOR':
                return redirect(url_for('asesor.dashboard'))
        else:
            flash('Usuario o contraseña incorrectos', 'error')
            return redirect(url_for('login.login'))
            
    except mysql.connector.Error as err:
        flash(f'Error de base de datos: {err}', 'error')
        return redirect(url_for('login.login'))

@login_bp.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión correctamente', 'success')
    return redirect(url_for('login.login'))
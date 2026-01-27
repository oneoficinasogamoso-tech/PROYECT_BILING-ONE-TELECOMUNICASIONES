from flask import Blueprint, render_template, session, redirect, url_for, flash, request, send_file, jsonify
import mysql.connector
from config import Config
from utils import (verificar_documento_identidad, verificar_firma_manual, 
                   digitalizar_firma, guardar_archivo, allowed_file)
import os
from datetime import datetime

asesor_bp = Blueprint('asesor', __name__)

def get_db_connection():
    connection = mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB
    )
    return connection

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
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Obtener estadísticas
        asesor_id = session.get('user_id')
        
        # Total de contratos
        cursor.execute("SELECT COUNT(*) as total FROM contratos WHERE asesor_id = %s", (asesor_id,))
        total_contratos = cursor.fetchone()['total']
        
        # Contratos por revisar
        cursor.execute("SELECT COUNT(*) as total FROM contratos WHERE asesor_id = %s AND estado = 'POR_REVISAR'", (asesor_id,))
        por_revisar = cursor.fetchone()['total']
        
        # Contratos instalados
        cursor.execute("SELECT COUNT(*) as total FROM contratos WHERE asesor_id = %s AND estado = 'INSTALADO'", (asesor_id,))
        instalados = cursor.fetchone()['total']
        
        cursor.close()
        conn.close()
        
        return render_template('asesor/dashboard.html', 
                             nombre=session.get('nombre'),
                             total_contratos=total_contratos,
                             por_revisar=por_revisar,
                             instalados=instalados)
    except Exception as e:
        flash(f'Error al cargar dashboard: {str(e)}', 'error')
        return render_template('asesor/dashboard.html', nombre=session.get('nombre'))

@asesor_bp.route('/crear-contrato')
@login_required
def crear_contrato():
    try:
        # Obtener planes disponibles
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM planes WHERE activo = TRUE")
        planes = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return render_template('asesor/crear_contrato.html', 
                             nombre=session.get('nombre'),
                             planes=planes)
    except Exception as e:
        flash(f'Error al cargar formulario: {str(e)}', 'error')
        return redirect(url_for('asesor.dashboard'))

@asesor_bp.route('/crear-contrato', methods=['POST'])
@login_required
def crear_contrato_post():
    try:
        # Obtener datos del formulario
        datos = {
            'nombre_cliente': request.form.get('nombre_cliente'),
            'numero_documento': request.form.get('numero_documento'),
            'correo_electronico': request.form.get('correo_electronico'),
            'telefono_contacto1': request.form.get('telefono_contacto1'),
            'telefono_contacto2': request.form.get('telefono_contacto2'),
            'barrio': request.form.get('barrio'),
            'departamento': request.form.get('departamento'),
            'municipio': request.form.get('municipio'),
            'direccion': request.form.get('direccion'),
            'plan': request.form.get('plan'),
            'tipo_contrato': request.form.get('tipo_contrato'),
            'fecha_contrato': request.form.get('fecha_contrato')
        }
        
        # Validar campos requeridos
        campos_requeridos = ['nombre_cliente', 'numero_documento', 'telefono_contacto1', 
                            'barrio', 'departamento', 'municipio', 'direccion', 
                            'plan', 'tipo_contrato', 'fecha_contrato']
        
        for campo in campos_requeridos:
            if not datos.get(campo):
                flash(f'El campo {campo.replace("_", " ")} es requerido', 'error')
                return redirect(url_for('asesor.crear_contrato'))
        
        # Validar archivos
        if 'foto_cc_frontal' not in request.files or 'foto_cc_trasera' not in request.files or 'foto_firma' not in request.files:
            flash('Debe subir todas las fotos requeridas', 'error')
            return redirect(url_for('asesor.crear_contrato'))
        
        foto_cc_frontal = request.files['foto_cc_frontal']
        foto_cc_trasera = request.files['foto_cc_trasera']
        foto_firma = request.files['foto_firma']
        
        if not foto_cc_frontal.filename or not foto_cc_trasera.filename or not foto_firma.filename:
            flash('Debe subir todas las fotos requeridas', 'error')
            return redirect(url_for('asesor.crear_contrato'))
        
        # Guardar foto CC frontal
        folder_frontal = os.path.join(Config.UPLOAD_FOLDER, 'cc_frontal')
        filename_frontal = guardar_archivo(foto_cc_frontal, folder_frontal, 'cc_frontal')
        
        if not filename_frontal:
            flash('Error al guardar foto de CC frontal. Formato no válido', 'error')
            return redirect(url_for('asesor.crear_contrato'))
        
        # Verificar CC frontal
        path_frontal = os.path.join(folder_frontal, filename_frontal)
        es_valido, confianza, texto = verificar_documento_identidad(path_frontal)
        
        if not es_valido:
            os.remove(path_frontal)
            flash('La foto de la cédula frontal no es legible o no es un documento de identidad válido', 'error')
            return redirect(url_for('asesor.crear_contrato'))
        
        # Guardar foto CC trasera
        folder_trasera = os.path.join(Config.UPLOAD_FOLDER, 'cc_trasera')
        filename_trasera = guardar_archivo(foto_cc_trasera, folder_trasera, 'cc_trasera')
        
        if not filename_trasera:
            os.remove(path_frontal)
            flash('Error al guardar foto de CC trasera. Formato no válido', 'error')
            return redirect(url_for('asesor.crear_contrato'))
        
        # Verificar CC trasera
        path_trasera = os.path.join(folder_trasera, filename_trasera)
        es_valido_trasera, _, _ = verificar_documento_identidad(path_trasera)
        
        if not es_valido_trasera:
            os.remove(path_frontal)
            os.remove(path_trasera)
            flash('La foto de la cédula trasera no es legible o no es un documento de identidad válido', 'error')
            return redirect(url_for('asesor.crear_contrato'))
        
        # Guardar foto firma
        folder_firma = os.path.join(Config.UPLOAD_FOLDER, 'firmas')
        filename_firma = guardar_archivo(foto_firma, folder_firma, 'firma')
        
        if not filename_firma:
            os.remove(path_frontal)
            os.remove(path_trasera)
            flash('Error al guardar foto de firma. Formato no válido', 'error')
            return redirect(url_for('asesor.crear_contrato'))
        
        # Verificar firma
        path_firma = os.path.join(folder_firma, filename_firma)
        firma_valida, mensaje_firma = verificar_firma_manual(path_firma)
        
        if not firma_valida:
            os.remove(path_frontal)
            os.remove(path_trasera)
            os.remove(path_firma)
            flash(f'Firma no válida: {mensaje_firma}', 'error')
            return redirect(url_for('asesor.crear_contrato'))
        
        # Digitalizar firma
        folder_digitalizada = os.path.join(Config.UPLOAD_FOLDER, 'firmas_digitalizadas')
        filename_digitalizada = f'digitalizada_{filename_firma}'.replace('.jpg', '.png').replace('.jpeg', '.png')
        path_digitalizada = os.path.join(folder_digitalizada, filename_digitalizada)
        
        exito_digitalizacion, mensaje_digitalizacion = digitalizar_firma(path_firma, path_digitalizada)
        
        if not exito_digitalizacion:
            os.remove(path_frontal)
            os.remove(path_trasera)
            os.remove(path_firma)
            flash(f'Error al digitalizar firma: {mensaje_digitalizacion}', 'error')
            return redirect(url_for('asesor.crear_contrato'))
        
        # Guardar en base de datos
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
        INSERT INTO contratos (asesor_id, nombre_cliente, numero_documento, correo_electronico,
                              telefono_contacto1, telefono_contacto2, barrio, departamento, municipio,
                              direccion, plan, tipo_contrato, fecha_contrato, foto_cc_frontal,
                              foto_cc_trasera, foto_firma, firma_digitalizada, estado)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'POR_REVISAR')
        """
        
        valores = (
            session.get('user_id'),
            datos['nombre_cliente'],
            datos['numero_documento'],
            datos['correo_electronico'],
            datos['telefono_contacto1'],
            datos['telefono_contacto2'],
            datos['barrio'],
            datos['departamento'],
            datos['municipio'],
            datos['direccion'],
            datos['plan'],
            datos['tipo_contrato'],
            datos['fecha_contrato'],
            filename_frontal,
            filename_trasera,
            filename_firma,
            filename_digitalizada
        )
        
        cursor.execute(query, valores)
        conn.commit()
        cursor.close()
        conn.close()
        
        flash('Contrato creado exitosamente y en estado de revisión', 'success')
        return redirect(url_for('asesor.ver_contratos'))
        
    except mysql.connector.IntegrityError:
        flash('El número de documento ya existe en el sistema', 'error')
        return redirect(url_for('asesor.crear_contrato'))
    except Exception as e:
        flash(f'Error al crear contrato: {str(e)}', 'error')
        return redirect(url_for('asesor.crear_contrato'))

@asesor_bp.route('/ver-contratos')
@login_required
def ver_contratos():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Obtener filtros
        fecha_inicio = request.args.get('fecha_inicio')
        fecha_fin = request.args.get('fecha_fin')
        municipio = request.args.get('municipio')
        barrio = request.args.get('barrio')
        estado = request.args.get('estado')
        
        # Construir query base
        query = "SELECT * FROM contratos WHERE asesor_id = %s"
        params = [session.get('user_id')]
        
        # Agregar filtros
        if fecha_inicio:
            query += " AND fecha_contrato >= %s"
            params.append(fecha_inicio)
        
        if fecha_fin:
            query += " AND fecha_contrato <= %s"
            params.append(fecha_fin)
        
        if municipio:
            query += " AND municipio = %s"
            params.append(municipio)
        
        if barrio:
            query += " AND barrio = %s"
            params.append(barrio)
        
        if estado:
            query += " AND estado = %s"
            params.append(estado)
        
        query += " ORDER BY created_at DESC"
        
        cursor.execute(query, params)
        contratos = cursor.fetchall()
        
        # Obtener municipios únicos para el filtro
        cursor.execute("SELECT DISTINCT municipio FROM contratos WHERE asesor_id = %s ORDER BY municipio", 
                      (session.get('user_id'),))
        municipios = [row['municipio'] for row in cursor.fetchall()]
        
        # Obtener barrios únicos para el filtro
        cursor.execute("SELECT DISTINCT barrio FROM contratos WHERE asesor_id = %s ORDER BY barrio", 
                      (session.get('user_id'),))
        barrios = [row['barrio'] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return render_template('asesor/ver_contratos.html',
                             nombre=session.get('nombre'),
                             contratos=contratos,
                             municipios=municipios,
                             barrios=barrios)
    except Exception as e:
        flash(f'Error al cargar contratos: {str(e)}', 'error')
        return redirect(url_for('asesor.dashboard'))

@asesor_bp.route('/descargar-contrato-pdf')
@login_required
def descargar_contrato_pdf():
    try:
        # Ruta del PDF predefinido
        pdf_path = os.path.join(Config.CONTRATOS_FOLDER, 'contrato.pdf')
        
        if not os.path.exists(pdf_path):
            flash('El archivo contrato.pdf no existe. Por favor colócalo en la carpeta contratos_pdf/', 'error')
            return redirect(url_for('asesor.dashboard'))
        
        return send_file(pdf_path, 
                        as_attachment=True,
                        download_name='contrato.pdf',
                        mimetype='application/pdf')
    except Exception as e:
        flash(f'Error al descargar contrato: {str(e)}', 'error')
        return redirect(url_for('asesor.dashboard'))
from flask import Blueprint, render_template, session, redirect, url_for, flash, request, send_file, jsonify
import mysql.connector
from config import Config
from utils import (verificar_documento_identidad, verificar_recibo, verificar_firma_manual, 
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
        
        # ========== OBTENER PRECIO DEL PLAN SELECCIONADO ==========
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Buscar el precio del plan seleccionado
        cursor.execute("SELECT precio FROM planes WHERE nombre_plan = %s", (datos['plan'],))
        plan_info = cursor.fetchone()
        
        if not plan_info:
            cursor.close()
            conn.close()
            flash('Error: Plan no encontrado en la base de datos', 'error')
            return redirect(url_for('asesor.crear_contrato'))
        
        precio_plan = plan_info['precio']
        # ========== FIN OBTENCIÓN PRECIO ==========
        
        # Validar campos requeridos
        campos_requeridos = ['nombre_cliente', 'numero_documento', 'telefono_contacto1', 
                            'barrio', 'departamento', 'municipio', 'direccion', 
                            'plan', 'tipo_contrato', 'fecha_contrato']
        
        for campo in campos_requeridos:
            if not datos.get(campo):
                cursor.close()
                conn.close()
                flash(f'El campo {campo.replace("_", " ")} es requerido', 'error')
                return redirect(url_for('asesor.crear_contrato'))
        
        # Validar archivos
        if 'foto_cc_frontal' not in request.files or 'foto_cc_trasera' not in request.files or 'foto_firma' not in request.files or 'foto_recibo' not in request.files:
            cursor.close()
            conn.close()
            flash('Debe subir todas las fotos requeridas (CC frontal, CC trasera, Firma y Recibo)', 'error')
            return redirect(url_for('asesor.crear_contrato'))
        
        foto_cc_frontal = request.files['foto_cc_frontal']
        foto_cc_trasera = request.files['foto_cc_trasera']
        foto_firma = request.files['foto_firma']
        foto_recibo = request.files['foto_recibo']
        
        if not foto_cc_frontal.filename or not foto_cc_trasera.filename or not foto_firma.filename or not foto_recibo.filename:
            cursor.close()
            conn.close()
            flash('Debe subir todas las fotos requeridas', 'error')
            return redirect(url_for('asesor.crear_contrato'))
        
        # ========== GUARDAR Y VERIFICAR CC FRONTAL ==========
        folder_frontal = os.path.join(Config.UPLOAD_FOLDER, 'cc_frontal')
        filename_frontal = guardar_archivo(foto_cc_frontal, folder_frontal, 'cc_frontal')
        
        if not filename_frontal:
            cursor.close()
            conn.close()
            flash('Error al guardar foto de CC frontal. Formato no válido (solo JPG, JPEG o PNG)', 'error')
            return redirect(url_for('asesor.crear_contrato'))
        
        # Verificar CC frontal
        path_frontal = os.path.join(folder_frontal, filename_frontal)
        es_valido, confianza, mensaje = verificar_documento_identidad(path_frontal)
        
        if not es_valido:
            os.remove(path_frontal)
            cursor.close()
            conn.close()
            flash(f'Cédula frontal rechazada: {mensaje}', 'error')
            return redirect(url_for('asesor.crear_contrato'))
        
        # ========== GUARDAR Y VERIFICAR CC TRASERA ==========
        folder_trasera = os.path.join(Config.UPLOAD_FOLDER, 'cc_trasera')
        filename_trasera = guardar_archivo(foto_cc_trasera, folder_trasera, 'cc_trasera')
        
        if not filename_trasera:
            os.remove(path_frontal)
            cursor.close()
            conn.close()
            flash('Error al guardar foto de CC trasera. Formato no válido (solo JPG, JPEG o PNG)', 'error')
            return redirect(url_for('asesor.crear_contrato'))
        
        # Verificar CC trasera
        path_trasera = os.path.join(folder_trasera, filename_trasera)
        es_valido_trasera, _, mensaje_trasera = verificar_documento_identidad(path_trasera)
        
        if not es_valido_trasera:
            os.remove(path_frontal)
            os.remove(path_trasera)
            cursor.close()
            conn.close()
            flash(f'Cédula trasera rechazada: {mensaje_trasera}', 'error')
            return redirect(url_for('asesor.crear_contrato'))
        
        # ========== GUARDAR Y VERIFICAR RECIBO ==========
        folder_recibo = os.path.join(Config.UPLOAD_FOLDER, 'recibos')
        filename_recibo = guardar_archivo(foto_recibo, folder_recibo, 'recibo')
        
        if not filename_recibo:
            os.remove(path_frontal)
            os.remove(path_trasera)
            cursor.close()
            conn.close()
            flash('Error al guardar foto de recibo. Formato no válido (solo JPG, JPEG o PNG)', 'error')
            return redirect(url_for('asesor.crear_contrato'))
        
        # Verificar recibo (MUY FLEXIBLE)
        path_recibo = os.path.join(folder_recibo, filename_recibo)
        recibo_valido, mensaje_recibo = verificar_recibo(path_recibo)
        
        if not recibo_valido:
            os.remove(path_frontal)
            os.remove(path_trasera)
            os.remove(path_recibo)
            cursor.close()
            conn.close()
            flash(f'Recibo rechazado: {mensaje_recibo}', 'error')
            return redirect(url_for('asesor.crear_contrato'))
        
        # ========== GUARDAR Y VERIFICAR FIRMA ==========
        folder_firma = os.path.join(Config.UPLOAD_FOLDER, 'firmas')
        filename_firma = guardar_archivo(foto_firma, folder_firma, 'firma')
        
        if not filename_firma:
            os.remove(path_frontal)
            os.remove(path_trasera)
            os.remove(path_recibo)
            cursor.close()
            conn.close()
            flash('Error al guardar foto de firma. Formato no válido (solo JPG, JPEG o PNG)', 'error')
            return redirect(url_for('asesor.crear_contrato'))
        
        # Verificar firma (SÚPER PERMISIVO)
        path_firma = os.path.join(folder_firma, filename_firma)
        firma_valida, confianza_firma, mensaje_firma = verificar_firma_manual(path_firma)
        
        if not firma_valida:
            os.remove(path_frontal)
            os.remove(path_trasera)
            os.remove(path_recibo)
            os.remove(path_firma)
            cursor.close()
            conn.close()
            flash(f'Firma rechazada: {mensaje_firma}', 'error')
            return redirect(url_for('asesor.crear_contrato'))
        
        # ========== DIGITALIZAR FIRMA (REMOVER FONDO) ==========
        folder_digitalizadas = os.path.join(Config.UPLOAD_FOLDER, 'firmas_digitalizadas')
        os.makedirs(folder_digitalizadas, exist_ok=True)
        
        # Generar nombre para firma digitalizada
        base_name = os.path.splitext(filename_firma)[0]
        filename_digitalizada = f"{base_name}_digital.png"
        path_digitalizada = os.path.join(folder_digitalizadas, filename_digitalizada)
        
        # Digitalizar (remover fondo blanco/líneas de cuaderno)
        exito_digitalizacion = digitalizar_firma(path_firma, path_digitalizada)
        
        if not exito_digitalizacion:
            os.remove(path_frontal)
            os.remove(path_trasera)
            os.remove(path_recibo)
            os.remove(path_firma)
            cursor.close()
            conn.close()
            flash('Error al procesar la firma. Por favor intente con otra foto', 'error')
            return redirect(url_for('asesor.crear_contrato'))
        
        # ========== GUARDAR EN BASE DE DATOS CON EL PRECIO ==========
        try:
            query = """
            INSERT INTO contratos 
            (asesor_id, nombre_cliente, numero_documento, correo_electronico, 
            telefono_contacto1, telefono_contacto2, barrio, departamento, 
            municipio, direccion, plan, precio, tipo_contrato, fecha_contrato, 
            foto_cc_frontal, foto_cc_trasera, foto_firma, foto_recibo, firma_digitalizada)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                precio_plan,  # ← AQUÍ SE GUARDA EL PRECIO
                datos['tipo_contrato'],
                datos['fecha_contrato'],
                filename_frontal,
                filename_trasera,
                filename_firma,
                filename_recibo,
                filename_digitalizada
            )
            
            cursor.execute(query, valores)
            conn.commit()
            cursor.close()
            conn.close()
            
            flash('✅ Contrato creado exitosamente con firma digitalizada', 'success')
            return redirect(url_for('asesor.ver_contratos'))
            
        except Exception as e:
            # Limpiar archivos si falla la BD
            os.remove(path_frontal)
            os.remove(path_trasera)
            os.remove(path_recibo)
            os.remove(path_firma)
            os.remove(path_digitalizada)
            cursor.close()
            conn.close()
            raise e
        
        flash('✅ Contrato creado exitosamente', 'success')
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





@asesor_bp.route('/generar-contrato/<int:contrato_id>')
@login_required
def generar_contrato(contrato_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Obtener datos del contrato y verificar que pertenece al asesor
        query = """
        SELECT c.*, u.nombre as asesor_nombre 
        FROM contratos c
        JOIN usuarios u ON c.asesor_id = u.id
        WHERE c.id = %s AND c.asesor_id = %s
        """
        cursor.execute(query, (contrato_id, session.get('user_id')))
        contrato = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if not contrato:
            flash('Contrato no encontrado o no tiene permisos para acceder', 'error')
            return redirect(url_for('asesor.ver_contratos'))
        
        # ============================================================
        # VALIDACIÓN CRÍTICA: VERIFICAR QUE TENGA FIRMA DIGITALIZADA
        # ============================================================
        if not contrato.get('firma_digitalizada'):
            flash('❌ ERROR: Este contrato no tiene firma digitalizada. No se puede generar el PDF.', 'error')
            return redirect(url_for('asesor.ver_contratos'))
        
        # Verificar que el archivo existe
        firma_path = os.path.join(Config.UPLOAD_FOLDER, 'firmas_digitalizadas', contrato['firma_digitalizada'])
        if not os.path.exists(firma_path):
            flash('❌ ERROR: El archivo de firma digitalizada no existe. No se puede generar el PDF.', 'error')
            return redirect(url_for('asesor.ver_contratos'))
        
        # Preparar datos para el contrato INCLUYENDO EL PRECIO
        datos_contrato = {
            'nombre_cliente': contrato['nombre_cliente'],
            'numero_documento': contrato['numero_documento'],
            'correo_electronico': contrato['correo_electronico'] or 'N/A',
            'telefono_contacto1': contrato['telefono_contacto1'],
            'telefono_contacto2': contrato['telefono_contacto2'] or 'N/A',
            'barrio': contrato['barrio'],
            'departamento': contrato['departamento'],
            'municipio': contrato['municipio'],
            'direccion': contrato['direccion'],
            'plan': contrato['plan'],
            'precio': contrato['precio'],  # ← AGREGAR EL PRECIO
            'tipo_contrato': contrato['tipo_contrato'],
            'fecha_contrato': contrato['fecha_contrato'],  # Pasar el objeto datetime directamente
            'asesor_nombre': contrato['asesor_nombre'],
            'firma_digitalizada_path': firma_path  # Ruta completa de la firma
        }
        
        # ============================================================
        # SELECCIONAR PLANTILLA SEGÚN EL PLAN
        # Si es "Solo TV" usa plantilla diferente (precio cápsula diferente)
        # ============================================================
        if contrato['plan'] == 'Solo TV':
            plantilla_nombre = 'plantilla_contrato_solo_tv.docx'
        else:
            plantilla_nombre = 'plantilla_contrato_asesor.docx'
        
        plantilla_path = os.path.join(Config.PLANTILLAS_FOLDER, plantilla_nombre)
        
        if not os.path.exists(plantilla_path):
            flash(f'Plantilla de contrato no encontrada. Coloque el archivo "{plantilla_nombre}" en la carpeta plantillas/', 'error')
            return redirect(url_for('asesor.ver_contratos'))
        
        # Generar el contrato PDF
        from utils import generar_contrato_word_pdf
        exito, mensaje, pdf_path = generar_contrato_word_pdf(
            datos_contrato, 
            plantilla_path, 
            Config.CONTRATOS_GENERADOS_FOLDER
        )
        
        if not exito:
            flash(mensaje, 'error')
            return redirect(url_for('asesor.ver_contratos'))
        
        # Enviar el PDF para descargar
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f"Contrato_{contrato['numero_documento']}.pdf",
            mimetype='application/pdf'
        )
        
    except Exception as e:
        flash(f'Error al generar contrato: {str(e)}', 'error')
        return redirect(url_for('asesor.ver_contratos'))
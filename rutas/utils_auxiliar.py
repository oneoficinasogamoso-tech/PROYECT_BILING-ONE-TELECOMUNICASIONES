from flask import Blueprint, render_template, session, redirect, url_for, flash, request, send_file, jsonify
import mysql.connector
from config import Config
import os
from datetime import datetime, timedelta
from utils_auxiliar import (generar_contrato_auxiliar_pdf, obtener_estadisticas_ventas, 
                              obtener_resumen_mensual_por_asesor)
import calendar

auxiliar_bp = Blueprint('auxiliar', __name__, url_prefix='/auxiliar')

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
        if session.get('rol') != 'AUXILIAR':
            flash('No tiene permisos para acceder a esta página', 'error')
            return redirect(url_for('login.login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@auxiliar_bp.route('/dashboard')
@login_required
def dashboard():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Estadísticas generales
        cursor.execute("SELECT COUNT(*) as total FROM contratos")
        total_contratos = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as total FROM contratos WHERE estado = 'INSTALADO'")
        instalados = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as total FROM contratos WHERE estado = 'POR_REVISAR'")
        por_revisar = cursor.fetchone()['total']
        
        # Total de asesores activos
        cursor.execute("SELECT COUNT(*) as total FROM usuarios WHERE rol = 'ASESOR'")
        total_asesores = cursor.fetchone()['total']
        
        cursor.close()
        conn.close()
        
        return render_template('auxiliar/dashboard.html', 
                             nombre=session.get('nombre'),
                             total_contratos=total_contratos,
                             instalados=instalados,
                             por_revisar=por_revisar,
                             total_asesores=total_asesores)
    except Exception as e:
        flash(f'Error al cargar dashboard: {str(e)}', 'error')
        return render_template('auxiliar/dashboard.html', nombre=session.get('nombre'))


@auxiliar_bp.route('/ver-contratos')
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
        asesor_id = request.args.get('asesor_id')
        
        # Construir query base con información del asesor
        query = """
        SELECT c.*, u.nombre as asesor_nombre 
        FROM contratos c
        JOIN usuarios u ON c.asesor_id = u.id
        WHERE 1=1
        """
        params = []
        
        # Agregar filtros
        if fecha_inicio:
            query += " AND c.fecha_contrato >= %s"
            params.append(fecha_inicio)
        
        if fecha_fin:
            query += " AND c.fecha_contrato <= %s"
            params.append(fecha_fin)
        
        if municipio:
            query += " AND c.municipio = %s"
            params.append(municipio)
        
        if barrio:
            query += " AND c.barrio = %s"
            params.append(barrio)
        
        if estado:
            query += " AND c.estado = %s"
            params.append(estado)
        
        if asesor_id:
            query += " AND c.asesor_id = %s"
            params.append(asesor_id)
        
        query += " ORDER BY c.created_at DESC"
        
        cursor.execute(query, params)
        contratos = cursor.fetchall()
        
        # Obtener listas para filtros
        cursor.execute("SELECT DISTINCT municipio FROM contratos ORDER BY municipio")
        municipios = [row['municipio'] for row in cursor.fetchall()]
        
        cursor.execute("SELECT DISTINCT barrio FROM contratos ORDER BY barrio")
        barrios = [row['barrio'] for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, nombre FROM usuarios WHERE rol = 'ASESOR' ORDER BY nombre")
        asesores = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template('auxiliar/ver_contratos.html',
                             nombre=session.get('nombre'),
                             contratos=contratos,
                             municipios=municipios,
                             barrios=barrios,
                             asesores=asesores)
    except Exception as e:
        flash(f'Error al cargar contratos: {str(e)}', 'error')
        return redirect(url_for('auxiliar.dashboard'))


@auxiliar_bp.route('/editar-contrato/<int:contrato_id>')
@login_required
def editar_contrato(contrato_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Obtener datos del contrato
        cursor.execute("SELECT * FROM contratos WHERE id = %s", (contrato_id,))
        contrato = cursor.fetchone()
        
        if not contrato:
            cursor.close()
            conn.close()
            flash('Contrato no encontrado', 'error')
            return redirect(url_for('auxiliar.ver_contratos'))
        
        # Obtener planes disponibles
        cursor.execute("SELECT * FROM planes WHERE activo = TRUE")
        planes = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template('auxiliar/editar_contrato.html',
                             nombre=session.get('nombre'),
                             contrato=contrato,
                             planes=planes)
    except Exception as e:
        flash(f'Error al cargar contrato: {str(e)}', 'error')
        return redirect(url_for('auxiliar.ver_contratos'))


@auxiliar_bp.route('/editar-contrato/<int:contrato_id>', methods=['POST'])
@login_required
def editar_contrato_post(contrato_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
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
            'fecha_contrato': request.form.get('fecha_contrato'),
            'observaciones': request.form.get('observaciones', ''),
            'estado': request.form.get('estado')
        }
        
        # Obtener precio del plan
        cursor.execute("SELECT precio FROM planes WHERE nombre_plan = %s", (datos['plan'],))
        plan_info = cursor.fetchone()
        
        if not plan_info:
            cursor.close()
            conn.close()
            flash('Error: Plan no encontrado', 'error')
            return redirect(url_for('auxiliar.editar_contrato', contrato_id=contrato_id))
        
        precio_plan = plan_info['precio']
        
        # Actualizar contrato
        query = """
        UPDATE contratos SET
            nombre_cliente = %s,
            numero_documento = %s,
            correo_electronico = %s,
            telefono_contacto1 = %s,
            telefono_contacto2 = %s,
            barrio = %s,
            departamento = %s,
            municipio = %s,
            direccion = %s,
            plan = %s,
            precio = %s,
            tipo_contrato = %s,
            fecha_contrato = %s,
            observaciones = %s,
            estado = %s,
            updated_at = NOW()
        WHERE id = %s
        """
        
        cursor.execute(query, (
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
            precio_plan,
            datos['tipo_contrato'],
            datos['fecha_contrato'],
            datos['observaciones'],
            datos['estado'],
            contrato_id
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        flash('✅ Contrato actualizado exitosamente', 'success')
        return redirect(url_for('auxiliar.ver_contratos'))
        
    except Exception as e:
        flash(f'Error al actualizar contrato: {str(e)}', 'error')
        return redirect(url_for('auxiliar.editar_contrato', contrato_id=contrato_id))


@auxiliar_bp.route('/descargar-contrato/<int:contrato_id>')
@login_required
def descargar_contrato(contrato_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Obtener datos del contrato con información del asesor
        query = """
        SELECT c.*, u.nombre as asesor_nombre 
        FROM contratos c
        JOIN usuarios u ON c.asesor_id = u.id
        WHERE c.id = %s
        """
        cursor.execute(query, (contrato_id,))
        contrato = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if not contrato:
            flash('Contrato no encontrado', 'error')
            return redirect(url_for('auxiliar.ver_contratos'))
        
        # Validar que tenga firma digitalizada
        if not contrato.get('firma_digitalizada'):
            flash('❌ ERROR: Este contrato no tiene firma digitalizada', 'error')
            return redirect(url_for('auxiliar.ver_contratos'))
        
        # Rutas de archivos
        firma_path = os.path.join(Config.UPLOAD_FOLDER, 'firmas_digitalizadas', contrato['firma_digitalizada'])
        cc_frontal_path = os.path.join(Config.UPLOAD_FOLDER, 'cc_frontal', contrato['foto_cc_frontal'])
        cc_trasera_path = os.path.join(Config.UPLOAD_FOLDER, 'cc_trasera', contrato['foto_cc_trasera'])
        recibo_path = os.path.join(Config.UPLOAD_FOLDER, 'recibos', contrato['foto_recibo'])
        
        # Validar que existan todos los archivos
        if not os.path.exists(firma_path):
            flash('❌ ERROR: No se encontró la firma digitalizada', 'error')
            return redirect(url_for('auxiliar.ver_contratos'))
        
        if not os.path.exists(cc_frontal_path):
            flash('❌ ERROR: No se encontró la CC frontal', 'error')
            return redirect(url_for('auxiliar.ver_contratos'))
        
        if not os.path.exists(cc_trasera_path):
            flash('❌ ERROR: No se encontró la CC trasera', 'error')
            return redirect(url_for('auxiliar.ver_contratos'))
        
        if not os.path.exists(recibo_path):
            flash('❌ ERROR: No se encontró el recibo', 'error')
            return redirect(url_for('auxiliar.ver_contratos'))
        
        # Preparar datos para el contrato
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
            'precio': contrato['precio'],
            'observaciones': contrato.get('observaciones', ''),
            'tipo_contrato': contrato['tipo_contrato'],
            'fecha_contrato': contrato['fecha_contrato'],
            'asesor_nombre': contrato['asesor_nombre'],
            'firma_digitalizada_path': firma_path
        }
        
        # Seleccionar plantilla del auxiliar (sin marca de agua)
        if contrato['plan'] == 'Solo TV':
            plantilla_nombre = 'plantilla_contrato_auxiliar_solo_tv.docx'
        else:
            plantilla_nombre = 'plantilla_contrato_auxiliar.docx'
        
        plantilla_path = os.path.join(Config.PLANTILLAS_FOLDER, plantilla_nombre)
        
        if not os.path.exists(plantilla_path):
            flash(f'Plantilla de contrato no encontrada: {plantilla_nombre}', 'error')
            return redirect(url_for('auxiliar.ver_contratos'))
        
        # Generar el contrato PDF con CC y recibo
        exito, mensaje, pdf_path = generar_contrato_auxiliar_pdf(
            datos_contrato, 
            plantilla_path, 
            Config.CONTRATOS_GENERADOS_FOLDER,
            cc_frontal_path,
            cc_trasera_path,
            recibo_path
        )
        
        if not exito:
            flash(mensaje, 'error')
            return redirect(url_for('auxiliar.ver_contratos'))
        
        # Enviar el PDF para descargar
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f"Contrato_{contrato['numero_documento']}_Auxiliar.pdf",
            mimetype='application/pdf'
        )
        
    except Exception as e:
        flash(f'Error al generar contrato: {str(e)}', 'error')
        return redirect(url_for('auxiliar.ver_contratos'))


@auxiliar_bp.route('/resumen-mensual')
@login_required
def resumen_mensual():
    try:
        # Obtener mes y año de los parámetros (por defecto mes actual)
        hoy = datetime.now()
        mes = request.args.get('mes', hoy.month, type=int)
        anio = request.args.get('anio', hoy.year, type=int)
        
        conn = get_db_connection()
        resumen = obtener_resumen_mensual_por_asesor(conn, mes, anio)
        conn.close()
        
        # Nombre del mes
        nombre_mes = calendar.month_name[mes]
        
        return render_template('auxiliar/resumen_mensual.html',
                             nombre=session.get('nombre'),
                             resumen=resumen,
                             mes=mes,
                             anio=anio,
                             nombre_mes=nombre_mes)
    except Exception as e:
        flash(f'Error al cargar resumen mensual: {str(e)}', 'error')
        return redirect(url_for('auxiliar.dashboard'))


@auxiliar_bp.route('/analisis-ventas')
@login_required
def analisis_ventas():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Obtener asesores para filtro
        cursor.execute("SELECT id, nombre FROM usuarios WHERE rol = 'ASESOR' ORDER BY nombre")
        asesores = cursor.fetchall()
        
        # Obtener municipios para filtro
        cursor.execute("SELECT DISTINCT municipio FROM contratos ORDER BY municipio")
        municipios = [row['municipio'] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return render_template('auxiliar/analisis_ventas.html',
                             nombre=session.get('nombre'),
                             asesores=asesores,
                             municipios=municipios)
    except Exception as e:
        flash(f'Error al cargar análisis: {str(e)}', 'error')
        return redirect(url_for('auxiliar.dashboard'))


@auxiliar_bp.route('/api/estadisticas-ventas')
@login_required
def api_estadisticas_ventas():
    """API para obtener estadísticas de ventas en formato JSON"""
    try:
        # Obtener filtros
        fecha_inicio = request.args.get('fecha_inicio')
        fecha_fin = request.args.get('fecha_fin')
        asesor_id = request.args.get('asesor_id', type=int)
        municipio = request.args.get('municipio')
        periodo = request.args.get('periodo', 'mes')  # dia, semana, mes
        
        # Si no hay fechas, usar el periodo especificado
        if not fecha_inicio or not fecha_fin:
            hoy = datetime.now()
            if periodo == 'dia':
                fecha_inicio = hoy.strftime('%Y-%m-%d')
                fecha_fin = hoy.strftime('%Y-%m-%d')
            elif periodo == 'semana':
                fecha_inicio = (hoy - timedelta(days=7)).strftime('%Y-%m-%d')
                fecha_fin = hoy.strftime('%Y-%m-%d')
            else:  # mes
                fecha_inicio = hoy.replace(day=1).strftime('%Y-%m-%d')
                fecha_fin = hoy.strftime('%Y-%m-%d')
        
        conn = get_db_connection()
        estadisticas = obtener_estadisticas_ventas(conn, fecha_inicio, fecha_fin, asesor_id, municipio)
        conn.close()
        
        # Convertir decimales a float para JSON
        for item in estadisticas.get('por_municipio', []):
            item['ingresos'] = float(item['ingresos'])
        
        for item in estadisticas.get('por_asesor', []):
            item['ingresos'] = float(item['ingresos'])
        
        for item in estadisticas.get('por_plan', []):
            item['ingresos'] = float(item['ingresos'])
        
        return jsonify(estadisticas)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@auxiliar_bp.route('/api/contratos-diarios')
@login_required
def api_contratos_diarios():
    """API para obtener contratos por día (últimos 30 días)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        asesor_id = request.args.get('asesor_id', type=int)
        municipio = request.args.get('municipio')
        
        where_clauses = ["fecha_contrato >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)"]
        params = []
        
        if asesor_id:
            where_clauses.append("asesor_id = %s")
            params.append(asesor_id)
        
        if municipio:
            where_clauses.append("municipio = %s")
            params.append(municipio)
        
        where_sql = " AND ".join(where_clauses)
        
        query = f"""
        SELECT DATE(fecha_contrato) as fecha, COUNT(*) as cantidad, COALESCE(SUM(precio), 0) as ingresos
        FROM contratos
        WHERE {where_sql}
        GROUP BY DATE(fecha_contrato)
        ORDER BY fecha
        """
        
        cursor.execute(query, params)
        resultados = cursor.fetchall()
        
        # Convertir fechas a string y decimales a float
        datos = []
        for row in resultados:
            datos.append({
                'fecha': row['fecha'].strftime('%Y-%m-%d'),
                'cantidad': row['cantidad'],
                'ingresos': float(row['ingresos'])
            })
        
        cursor.close()
        conn.close()
        
        return jsonify(datos)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
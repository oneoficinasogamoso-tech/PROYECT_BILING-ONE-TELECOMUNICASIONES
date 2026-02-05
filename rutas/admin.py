from flask import Blueprint, render_template, session, redirect, url_for, flash, request, send_file, jsonify
import mysql.connector
from config import Config
import os
from datetime import datetime, timedelta
from utils_auxiliar import (generar_contrato_auxiliar_pdf, obtener_estadisticas_ventas, 
                              obtener_resumen_mensual_por_asesor)
from werkzeug.security import generate_password_hash
import calendar
import traceback

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

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
        if session.get('rol') != 'ADMIN':
            flash('No tiene permisos para acceder a esta página', 'error')
            return redirect(url_for('login.login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function


# ============================================================
# DASHBOARD
# ============================================================
@admin_bp.route('/dashboard')
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
        
        # Total de auxiliares activos
        cursor.execute("SELECT COUNT(*) as total FROM usuarios WHERE rol = 'AUXILIAR'")
        total_auxiliares = cursor.fetchone()['total']
        
        # Total de usuarios
        cursor.execute("SELECT COUNT(*) as total FROM usuarios")
        total_usuarios = cursor.fetchone()['total']
        
        cursor.close()
        conn.close()
        
        return render_template('admin/dashboard.html', 
                             nombre=session.get('nombre'),
                             total_contratos=total_contratos,
                             instalados=instalados,
                             por_revisar=por_revisar,
                             total_asesores=total_asesores,
                             total_auxiliares=total_auxiliares,
                             total_usuarios=total_usuarios)
    except Exception as e:
        flash(f'Error al cargar dashboard: {str(e)}', 'error')
        return render_template('admin/dashboard.html', nombre=session.get('nombre'))


# ============================================================
# GESTIÓN DE CONTRATOS (igual que auxiliar)
# ============================================================
@admin_bp.route('/ver-contratos')
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
        
        return render_template('admin/ver_contratos.html',
                             nombre=session.get('nombre'),
                             contratos=contratos,
                             municipios=municipios,
                             barrios=barrios,
                             asesores=asesores)
    except Exception as e:
        flash(f'Error al cargar contratos: {str(e)}', 'error')
        return redirect(url_for('admin.dashboard'))


@admin_bp.route('/editar-contrato/<int:contrato_id>')
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
            return redirect(url_for('admin.ver_contratos'))
        
        # Obtener planes disponibles
        cursor.execute("SELECT * FROM planes WHERE activo = TRUE")
        planes = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template('admin/editar_contrato.html',
                             nombre=session.get('nombre'),
                             contrato=contrato,
                             planes=planes)
    except Exception as e:
        flash(f'Error al cargar contrato: {str(e)}', 'error')
        return redirect(url_for('admin.ver_contratos'))


@admin_bp.route('/editar-contrato/<int:contrato_id>', methods=['POST'])
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
            return redirect(url_for('admin.editar_contrato', contrato_id=contrato_id))
        
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
        return redirect(url_for('admin.ver_contratos'))
        
    except Exception as e:
        flash(f'Error al actualizar contrato: {str(e)}', 'error')
        return redirect(url_for('admin.editar_contrato', contrato_id=contrato_id))


@admin_bp.route('/descargar-contrato/<int:contrato_id>')
@login_required
def descargar_contrato(contrato_id):
    """Descargar PDF del contrato (igual que auxiliar)"""
    print(f"\n{'='*60}")
    print(f"ADMIN - Descarga de contrato ID: {contrato_id}")
    print(f"{'='*60}")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

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
            print("❌ ERROR: Contrato no encontrado en BD")
            flash('Contrato no encontrado en la base de datos.', 'error')
            return redirect(url_for('admin.ver_contratos'))

        print(f"✅ Contrato encontrado: {contrato['nombre_cliente']}")

        # Validar carpetas
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(Config.PLANTILLAS_FOLDER, exist_ok=True)
        os.makedirs(Config.CONTRATOS_GENERADOS_FOLDER, exist_ok=True)

        # Firma digitalizada (obligatoria)
        if not contrato.get('firma_digitalizada'):
            print("❌ ERROR: No hay firma digitalizada en BD")
            flash('Este contrato no tiene firma digitalizada. No se puede generar el PDF.', 'error')
            return redirect(url_for('admin.ver_contratos'))

        firma_path = os.path.join(Config.UPLOAD_FOLDER, 'firmas_digitalizadas', contrato['firma_digitalizada'])
        
        if not os.path.exists(firma_path):
            print(f"❌ ERROR: Archivo de firma no encontrado")
            flash(f'Archivo de firma no encontrado: {firma_path}', 'error')
            return redirect(url_for('admin.ver_contratos'))

        # CC Y RECIBO (opcionales)
        cc_frontal_path = None
        cc_trasera_path = None
        recibo_path = None

        if contrato.get('foto_cc_frontal'):
            ruta = os.path.join(Config.UPLOAD_FOLDER, 'cc_frontal', contrato['foto_cc_frontal'])
            if os.path.exists(ruta):
                cc_frontal_path = ruta

        if contrato.get('foto_cc_trasera'):
            ruta = os.path.join(Config.UPLOAD_FOLDER, 'cc_trasera', contrato['foto_cc_trasera'])
            if os.path.exists(ruta):
                cc_trasera_path = ruta

        if contrato.get('foto_recibo'):
            ruta = os.path.join(Config.UPLOAD_FOLDER, 'recibos', contrato['foto_recibo'])
            if os.path.exists(ruta):
                recibo_path = ruta

        # Plantilla
        if contrato['plan'] == 'Solo TV':
            plantilla_nombre = 'plantilla_contrato_solo_tv_auxiliar.docx'
        else:
            plantilla_nombre = 'plantilla_contrato_auxiliar.docx'

        plantilla_path = os.path.join(Config.PLANTILLAS_FOLDER, plantilla_nombre)

        if not os.path.exists(plantilla_path):
            print(f"❌ ERROR: Plantilla no encontrada")
            flash(f'❌ Plantilla no encontrada: "{plantilla_nombre}" en carpeta plantillas/.', 'error')
            return redirect(url_for('admin.ver_contratos'))

        # Preparar datos
        datos_contrato = {
            'nombre_cliente':      contrato['nombre_cliente'],
            'numero_documento':    contrato['numero_documento'],
            'correo_electronico':  contrato['correo_electronico'] or 'N/A',
            'telefono_contacto1':  contrato['telefono_contacto1'],
            'telefono_contacto2':  contrato['telefono_contacto2'] or 'N/A',
            'barrio':              contrato['barrio'],
            'departamento':        contrato['departamento'],
            'municipio':           contrato['municipio'],
            'direccion':           contrato['direccion'],
            'plan':                contrato['plan'],
            'precio':              contrato['precio'],
            'observaciones':       contrato.get('observaciones', ''),
            'tipo_contrato':       contrato['tipo_contrato'],
            'fecha_contrato':      contrato['fecha_contrato'],
            'asesor_nombre':       contrato['asesor_nombre'],
            'firma_digitalizada_path': firma_path
        }

        # Generar PDF
        exito, mensaje, pdf_path = generar_contrato_auxiliar_pdf(
            datos_contrato,
            plantilla_path,
            Config.CONTRATOS_GENERADOS_FOLDER,
            cc_frontal_path,
            cc_trasera_path,
            recibo_path
        )

        if not exito:
            print(f"❌ ERROR en generación: {mensaje}")
            flash(f'❌ {mensaje}', 'error')
            return redirect(url_for('admin.ver_contratos'))

        print(f"✅ PDF generado exitosamente: {pdf_path}")
        
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f"Contrato_{contrato['numero_documento']}_Admin.pdf",
            mimetype='application/pdf'
        )

    except Exception as e:
        print(f"\n❌ EXCEPCIÓN: {str(e)}")
        traceback.print_exc()
        flash(f'❌ Error inesperado al generar contrato: {str(e)}', 'error')
        return redirect(url_for('admin.ver_contratos'))


# ============================================================
# RESUMEN MENSUAL
# ============================================================
@admin_bp.route('/resumen-mensual')
@login_required
def resumen_mensual():
    try:
        hoy = datetime.now()
        mes = request.args.get('mes', hoy.month, type=int)
        anio = request.args.get('anio', hoy.year, type=int)
        
        conn = get_db_connection()
        resumen = obtener_resumen_mensual_por_asesor(conn, mes, anio)
        conn.close()
        
        nombre_mes = calendar.month_name[mes]
        
        return render_template('admin/resumen_mensual.html',
                             nombre=session.get('nombre'),
                             resumen=resumen,
                             mes=mes,
                             anio=anio,
                             nombre_mes=nombre_mes)
    except Exception as e:
        flash(f'Error al cargar resumen mensual: {str(e)}', 'error')
        return redirect(url_for('admin.dashboard'))


# ============================================================
# ANÁLISIS DE VENTAS
# ============================================================
@admin_bp.route('/analisis-ventas')
@login_required
def analisis_ventas():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT id, nombre FROM usuarios WHERE rol = 'ASESOR' ORDER BY nombre")
        asesores = cursor.fetchall()
        
        cursor.execute("SELECT DISTINCT municipio FROM contratos ORDER BY municipio")
        municipios = [row['municipio'] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return render_template('admin/analisis_ventas.html',
                             nombre=session.get('nombre'),
                             asesores=asesores,
                             municipios=municipios)
    except Exception as e:
        flash(f'Error al cargar análisis: {str(e)}', 'error')
        return redirect(url_for('admin.dashboard'))


@admin_bp.route('/api/estadisticas-contratos')
@login_required
def api_estadisticas_contratos():
    """API para obtener estadísticas de contratos"""
    try:
        fecha_inicio = request.args.get('fecha_inicio')
        fecha_fin = request.args.get('fecha_fin')
        asesor_id = request.args.get('asesor_id', type=int)
        municipio = request.args.get('municipio')
        estado = request.args.get('estado')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        where_clauses = []
        params = []
        
        if fecha_inicio:
            where_clauses.append("DATE(fecha_contrato) >= %s")
            params.append(fecha_inicio)
        
        if fecha_fin:
            where_clauses.append("DATE(fecha_contrato) <= %s")
            params.append(fecha_fin)
        
        if asesor_id:
            where_clauses.append("asesor_id = %s")
            params.append(asesor_id)
        
        if municipio:
            where_clauses.append("municipio = %s")
            params.append(municipio)
        
        if estado and estado != 'todos':
            where_clauses.append("estado = %s")
            params.append(estado.upper())
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # Total de contratos
        query = f"SELECT COUNT(*) as total FROM contratos WHERE {where_sql}"
        cursor.execute(query, params)
        total_contratos = cursor.fetchone()['total']
        
        # Por municipio
        query = f"""
        SELECT municipio, COUNT(*) as cantidad
        FROM contratos
        WHERE {where_sql}
        GROUP BY municipio
        ORDER BY cantidad DESC
        """
        cursor.execute(query, params)
        por_municipio = cursor.fetchall()
        
        # Por estado
        query = f"""
        SELECT estado, COUNT(*) as cantidad
        FROM contratos
        WHERE {where_sql}
        GROUP BY estado
        """
        cursor.execute(query, params)
        por_estado = cursor.fetchall()
        
        # Por asesor
        query = f"""
        SELECT u.nombre as asesor, COUNT(*) as cantidad
        FROM contratos c
        JOIN usuarios u ON c.asesor_id = u.id
        WHERE {where_sql}
        GROUP BY u.nombre
        ORDER BY cantidad DESC
        """
        cursor.execute(query, params)
        por_asesor = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'total_contratos': total_contratos,
            'por_municipio': por_municipio,
            'por_estado': por_estado,
            'por_asesor': por_asesor
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/api/contratos-tendencia')
@login_required
def api_contratos_tendencia():
    """API para tendencias"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        fecha_inicio = request.args.get('fecha_inicio')
        fecha_fin = request.args.get('fecha_fin')
        asesor_id = request.args.get('asesor_id', type=int)
        municipios = request.args.getlist('municipios[]')
        
        if not fecha_inicio or not fecha_fin:
            hoy = datetime.now()
            fecha_fin = hoy.strftime('%Y-%m-%d')
            fecha_inicio = (hoy - timedelta(days=30)).strftime('%Y-%m-%d')
        
        where_clauses = ["DATE(fecha_contrato) BETWEEN %s AND %s"]
        params = [fecha_inicio, fecha_fin]
        
        if asesor_id:
            where_clauses.append("asesor_id = %s")
            params.append(asesor_id)
        
        if municipios:
            placeholders = ','.join(['%s'] * len(municipios))
            where_clauses.append(f"municipio IN ({placeholders})")
            params.extend(municipios)
        
        where_sql = " AND ".join(where_clauses)
        
        query = f"""
        SELECT 
            DATE(fecha_contrato) as fecha,
            estado,
            COUNT(*) as cantidad
        FROM contratos
        WHERE {where_sql}
        GROUP BY DATE(fecha_contrato), estado
        ORDER BY fecha, estado
        """
        
        cursor.execute(query, params)
        resultados = cursor.fetchall()
        
        datos = {}
        for row in resultados:
            fecha_str = row['fecha'].strftime('%Y-%m-%d')
            estado = row['estado']
            
            if fecha_str not in datos:
                datos[fecha_str] = {
                    'fecha': fecha_str,
                    'INSTALADO': 0,
                    'POR_REVISAR': 0,
                    'RECHAZADO': 0,
                    'total': 0
                }
            
            datos[fecha_str][estado] = row['cantidad']
            datos[fecha_str]['total'] += row['cantidad']
        
        cursor.close()
        conn.close()
        
        return jsonify(list(datos.values()))
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
# GESTIÓN DE USUARIOS
# ============================================================
@admin_bp.route('/usuarios')
@login_required
def usuarios():
    """Ver lista de usuarios"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Filtro por rol
        rol_filtro = request.args.get('rol')
        
        if rol_filtro:
            query = "SELECT * FROM usuarios WHERE rol = %s ORDER BY nombre"
            cursor.execute(query, (rol_filtro,))
        else:
            query = "SELECT * FROM usuarios ORDER BY nombre"
            cursor.execute(query)
        
        usuarios = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template('admin/usuarios.html',
                             nombre=session.get('nombre'),
                             usuarios=usuarios)
    except Exception as e:
        flash(f'Error al cargar usuarios: {str(e)}', 'error')
        return redirect(url_for('admin.dashboard'))


@admin_bp.route('/crear-usuario')
@login_required
def crear_usuario():
    """Mostrar formulario para crear usuario"""
    return render_template('admin/crear_usuario.html',
                         nombre=session.get('nombre'))


@admin_bp.route('/crear-usuario', methods=['POST'])
@login_required
def crear_usuario_post():
    """Crear nuevo usuario"""
    try:
        nombre = request.form.get('nombre')
        usuario = request.form.get('usuario')
        password = request.form.get('password')
        rol = request.form.get('rol')
        
        # Validaciones
        if not all([nombre, usuario, password, rol]):
            flash('Todos los campos son requeridos', 'error')
            return redirect(url_for('admin.crear_usuario'))
        
        if rol not in ['ASESOR', 'AUXILIAR']:
            flash('Rol inválido. Solo se pueden crear Asesores o Auxiliares', 'error')
            return redirect(url_for('admin.crear_usuario'))
        
        if len(password) < 4:
            flash('La contraseña debe tener al menos 4 caracteres', 'error')
            return redirect(url_for('admin.crear_usuario'))
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Verificar si el usuario ya existe
        cursor.execute("SELECT id FROM usuarios WHERE usuario = %s", (usuario,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            flash('El nombre de usuario ya existe', 'error')
            return redirect(url_for('admin.crear_usuario'))
        
        # Hash de la contraseña
        password_hash = generate_password_hash(password)
        
        # Insertar usuario
        query = """
        INSERT INTO usuarios (nombre, usuario, password, rol)
        VALUES (%s, %s, %s, %s)
        """
        cursor.execute(query, (nombre, usuario, password_hash, rol))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        flash(f'✅ Usuario {nombre} creado exitosamente como {rol}', 'success')
        return redirect(url_for('admin.usuarios'))
        
    except Exception as e:
        flash(f'Error al crear usuario: {str(e)}', 'error')
        return redirect(url_for('admin.crear_usuario'))


@admin_bp.route('/eliminar-usuario/<int:user_id>', methods=['POST'])
@login_required
def eliminar_usuario(user_id):
    """Eliminar usuario"""
    try:
        # No permitir eliminar al admin logueado
        if user_id == session.get('user_id'):
            flash('No puedes eliminar tu propia cuenta', 'error')
            return redirect(url_for('admin.usuarios'))
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Verificar que el usuario existe y no es ADMIN
        cursor.execute("SELECT nombre, rol FROM usuarios WHERE id = %s", (user_id,))
        usuario = cursor.fetchone()
        
        if not usuario:
            cursor.close()
            conn.close()
            flash('Usuario no encontrado', 'error')
            return redirect(url_for('admin.usuarios'))
        
        if usuario['rol'] == 'ADMIN':
            cursor.close()
            conn.close()
            flash('No se pueden eliminar administradores', 'error')
            return redirect(url_for('admin.usuarios'))
        
        # Eliminar usuario
        cursor.execute("DELETE FROM usuarios WHERE id = %s", (user_id,))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        flash(f'✅ Usuario {usuario["nombre"]} eliminado exitosamente', 'success')
        return redirect(url_for('admin.usuarios'))
        
    except Exception as e:
        flash(f'Error al eliminar usuario: {str(e)}', 'error')
        return redirect(url_for('admin.usuarios'))


@admin_bp.route('/editar-usuario/<int:user_id>')
@login_required
def editar_usuario(user_id):
    """Mostrar formulario para editar usuario"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT * FROM usuarios WHERE id = %s", (user_id,))
        usuario = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if not usuario:
            flash('Usuario no encontrado', 'error')
            return redirect(url_for('admin.usuarios'))
        
        return render_template('admin/editar_usuario.html',
                             nombre=session.get('nombre'),
                             usuario=usuario)
    except Exception as e:
        flash(f'Error al cargar usuario: {str(e)}', 'error')
        return redirect(url_for('admin.usuarios'))


@admin_bp.route('/editar-usuario/<int:user_id>', methods=['POST'])
@login_required
def editar_usuario_post(user_id):
    """Actualizar usuario"""
    try:
        nombre = request.form.get('nombre')
        usuario = request.form.get('usuario')
        password = request.form.get('password')
        rol = request.form.get('rol')
        
        if not all([nombre, usuario, rol]):
            flash('Nombre, usuario y rol son requeridos', 'error')
            return redirect(url_for('admin.editar_usuario', user_id=user_id))
        
        if rol not in ['ASESOR', 'AUXILIAR', 'ADMIN']:
            flash('Rol inválido', 'error')
            return redirect(url_for('admin.editar_usuario', user_id=user_id))
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Verificar si el usuario ya existe (excluyendo el actual)
        cursor.execute("SELECT id FROM usuarios WHERE usuario = %s AND id != %s", (usuario, user_id))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            flash('El nombre de usuario ya existe', 'error')
            return redirect(url_for('admin.editar_usuario', user_id=user_id))
        
        # Actualizar
        if password:  # Si se proporciona nueva contraseña
            if len(password) < 4:
                flash('La contraseña debe tener al menos 4 caracteres', 'error')
                return redirect(url_for('admin.editar_usuario', user_id=user_id))
            
            password_hash = generate_password_hash(password)
            query = """
            UPDATE usuarios SET nombre = %s, usuario = %s, password = %s, rol = %s
            WHERE id = %s
            """
            cursor.execute(query, (nombre, usuario, password_hash, rol, user_id))
        else:  # No cambiar contraseña
            query = """
            UPDATE usuarios SET nombre = %s, usuario = %s, rol = %s
            WHERE id = %s
            """
            cursor.execute(query, (nombre, usuario, rol, user_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        flash(f'✅ Usuario {nombre} actualizado exitosamente', 'success')
        return redirect(url_for('admin.usuarios'))
        
    except Exception as e:
        flash(f'Error al actualizar usuario: {str(e)}', 'error')
        return redirect(url_for('admin.editar_usuario', user_id=user_id))
"""
Utilidades específicas para el rol AUXILIAR
Incluye generación de PDFs con plantilla sin marca de agua
y funciones para insertar CC (frontal y trasera) y recibo en el documento Word
"""

import os
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Inches
from datetime import datetime, timedelta
from utils import convertir_word_a_pdf, formatear_fecha_contrato


def generar_contrato_auxiliar_pdf(datos_contrato, plantilla_path, output_folder, 
                                   cc_frontal_path=None, cc_trasera_path=None, recibo_path=None,
                                   tamanio_firma_pulgadas=2.0,     
                                   tamanio_cc_pulgadas=4.0,        
                                   tamanio_recibo_pulgadas=4.0):   
    """
    Genera contrato PDF para el auxiliar.
    
    CC frontal, CC trasera y recibo son OPCIONALES:
    - Si la ruta es None o el archivo no existe, simplemente no se inserta esa imagen
    - La plantilla debe tener las variables {{ cc_frontal }}, {{ cc_trasera }}, {{ recibo }}
      pero si no se proporcionan, se pasan como texto vacío y no rompen nada
    
    Retorna: (exito: bool, mensaje: str, pdf_path: str o None)
    """
    try:
        # --- Validar plantilla ---
        if not os.path.exists(plantilla_path):
            return False, f"Plantilla no encontrada: {plantilla_path}", None

        # --- Validar firma (obligatoria) ---
        firma_path = datos_contrato.get('firma_digitalizada_path')
        if not firma_path:
            return False, "No hay ruta de firma digitalizada en los datos del contrato.", None
        if not os.path.exists(firma_path):
            return False, f"Archivo de firma no encontrado: {firma_path}", None

        # --- Crear carpeta de salida ---
        os.makedirs(output_folder, exist_ok=True)

        # --- Cargar plantilla ---
        doc = DocxTemplate(plantilla_path)

        # --- Formatear fechas ---
        fecha_contrato_obj = datos_contrato.get('fecha_contrato')
        formatos_fecha = formatear_fecha_contrato(fecha_contrato_obj)

        # --- Tipo contrato ---
        tipo_contrato = datos_contrato.get('tipo_contrato', '').upper()
        es_residencial = 'X' if tipo_contrato == 'RESIDENCIAL' else ''
        es_corporativo = 'X' if tipo_contrato == 'CORPORATIVO' else ''

        # --- Contexto base (mismo que el asesor) ---
        context = {
            'nombre_cliente':      datos_contrato.get('nombre_cliente', ''),
            'numero_documento':    datos_contrato.get('numero_documento', ''),
            'correo_electronico':  datos_contrato.get('correo_electronico', 'N/A'),
            'telefono_contacto1':  datos_contrato.get('telefono_contacto1', ''),
            'telefono_contacto2':  datos_contrato.get('telefono_contacto2', 'N/A'),
            'barrio':              datos_contrato.get('barrio', ''),
            'departamento':        datos_contrato.get('departamento', ''),
            'municipio':           datos_contrato.get('municipio', ''),
            'direccion':           datos_contrato.get('direccion', ''),
            'plan':                datos_contrato.get('plan', ''),
            'precio':              datos_contrato.get('precio', 0),
            'observaciones':       datos_contrato.get('observaciones', ''),
            'tipo_contrato':       datos_contrato.get('tipo_contrato', ''),
            'marca_residencial':   es_residencial,
            'marca_corporativo':   es_corporativo,

            # Fechas
            'fecha_mes_anio_espaciado':      formatos_fecha['mes_anio_espaciado'],
            'fecha_mes_anio_guion':          formatos_fecha['mes_anio_guion'],
            'fecha_completa':                formatos_fecha['fecha_completa_slash'],
            'fecha_mes_nombre':              formatos_fecha['mes_nombre'],
            'fecha_dia':                     formatos_fecha['dia'],
            'fecha_mes':                     formatos_fecha['mes_numero'],
            'fecha_anio':                    formatos_fecha['anio'],
            'fecha_anio_corto':              formatos_fecha['anio_corto'],
            'fecha_finalizacion':            formatos_fecha['finalizacion_mes_anio_espaciado'],
            'fecha_contrato':                datos_contrato.get('fecha_contrato', ''),

            # Asesor
            'asesor_nombre':       datos_contrato.get('asesor_nombre', ''),

            # Generación
            'fecha_generacion':    datetime.now().strftime('%d/%m/%Y'),
            'hora_generacion':     datetime.now().strftime('%H:%M:%S'),

            # Imágenes opcionales — por defecto texto vacío
            'cc_frontal': '',
            'cc_trasera': '',
            'recibo': '',
        }

        # --- Insertar firma (obligatoria) ---
        firma_img = InlineImage(doc, firma_path, width=Inches(tamanio_firma_pulgadas))
        context['firma_cliente'] = firma_img

        # --- Insertar CC frontal si existe ---
        if cc_frontal_path and os.path.exists(cc_frontal_path):
            context['cc_frontal'] = InlineImage(doc, cc_frontal_path, width=Inches(tamanio_cc_pulgadas))

        # --- Insertar CC trasera si existe ---
        if cc_trasera_path and os.path.exists(cc_trasera_path):
            context['cc_trasera'] = InlineImage(doc, cc_trasera_path, width=Inches(tamanio_cc_pulgadas))

        # --- Insertar recibo si existe ---
        if recibo_path and os.path.exists(recibo_path):
            context['recibo'] = InlineImage(doc, recibo_path, width=Inches(tamanio_recibo_pulgadas))

        # --- Renderizar ---
        doc.render(context)

        # --- Guardar Word temporal ---
        numero_doc = datos_contrato.get('numero_documento', 'sin_documento')
        temp_docx = os.path.join(output_folder, f"{numero_doc}_auxiliar_temp.docx")
        doc.save(temp_docx)

        # --- Convertir a PDF ---
        output_pdf = os.path.join(output_folder, f"{numero_doc}_auxiliar.pdf")
        exito_conversion = convertir_word_a_pdf(temp_docx, output_pdf)

        # Limpiar temporal
        try:
            os.remove(temp_docx)
        except:
            pass

        if not exito_conversion:
            return False, "Error al convertir Word a PDF. Verifique que Microsoft Word esté instalado y no esté ocupado.", None

        if not os.path.exists(output_pdf):
            return False, f"El PDF se generó pero no se encontró en: {output_pdf}", None

        return True, "Contrato generado exitosamente", output_pdf

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"Error interno al generar contrato: {str(e)}", None


def obtener_estadisticas_ventas(conn, fecha_inicio=None, fecha_fin=None, asesor_id=None, municipio=None):
    """
    Obtiene estadísticas de ventas filtradas
    
    Retorna dict con:
        - total_contratos
        - total_ingresos
        - por_estado
        - por_municipio
        - por_asesor
        - por_plan
    """
    cursor = conn.cursor(dictionary=True)
    
    # Construir query base
    where_clauses = []
    params = []
    
    if fecha_inicio:
        where_clauses.append("fecha_contrato >= %s")
        params.append(fecha_inicio)
    
    if fecha_fin:
        where_clauses.append("fecha_contrato <= %s")
        params.append(fecha_fin)
    
    if asesor_id:
        where_clauses.append("asesor_id = %s")
        params.append(asesor_id)
    
    if municipio:
        where_clauses.append("municipio = %s")
        params.append(municipio)
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    # Total contratos e ingresos
    query = f"SELECT COUNT(*) as total, COALESCE(SUM(precio), 0) as ingresos FROM contratos WHERE {where_sql}"
    cursor.execute(query, params)
    resultado = cursor.fetchone()
    total_contratos = resultado['total']
    total_ingresos = float(resultado['ingresos'])
    
    # Por estado
    query = f"SELECT estado, COUNT(*) as cantidad FROM contratos WHERE {where_sql} GROUP BY estado"
    cursor.execute(query, params)
    por_estado = cursor.fetchall()
    
    # Por municipio
    query = f"SELECT municipio, COUNT(*) as cantidad, COALESCE(SUM(precio), 0) as ingresos FROM contratos WHERE {where_sql} GROUP BY municipio ORDER BY cantidad DESC"
    cursor.execute(query, params)
    por_municipio = cursor.fetchall()
    
    # Por asesor
    query = f"""
    SELECT u.nombre as asesor, COUNT(*) as cantidad, COALESCE(SUM(c.precio), 0) as ingresos 
    FROM contratos c
    JOIN usuarios u ON c.asesor_id = u.id
    WHERE {where_sql}
    GROUP BY u.nombre
    ORDER BY cantidad DESC
    """
    cursor.execute(query, params)
    por_asesor = cursor.fetchall()
    
    # Por plan
    query = f"SELECT plan, COUNT(*) as cantidad, COALESCE(SUM(precio), 0) as ingresos FROM contratos WHERE {where_sql} GROUP BY plan ORDER BY cantidad DESC"
    cursor.execute(query, params)
    por_plan = cursor.fetchall()
    
    cursor.close()
    
    return {
        'total_contratos': total_contratos,
        'total_ingresos': total_ingresos,
        'por_estado': por_estado,
        'por_municipio': por_municipio,
        'por_asesor': por_asesor,
        'por_plan': por_plan
    }


def obtener_resumen_mensual_por_asesor(conn, mes, anio):
    """
    Obtiene un resumen de contratos por asesor para un mes específico
    Retorna lista de dict con información de cada asesor
    """
    cursor = conn.cursor(dictionary=True)
    
    query = """
    SELECT 
        u.id as asesor_id,
        u.nombre as asesor_nombre,
        COUNT(c.id) as total_contratos,
        COALESCE(SUM(c.precio), 0) as ingresos_total,
        SUM(CASE WHEN c.estado = 'INSTALADO' THEN 1 ELSE 0 END) as instalados,
        SUM(CASE WHEN c.estado = 'POR_REVISAR' THEN 1 ELSE 0 END) as por_revisar,
        SUM(CASE WHEN c.estado = 'RECHAZADO' THEN 1 ELSE 0 END) as rechazados
    FROM usuarios u
    LEFT JOIN contratos c ON u.id = c.asesor_id 
        AND MONTH(c.fecha_contrato) = %s 
        AND YEAR(c.fecha_contrato) = %s
    WHERE u.rol = 'ASESOR'
    GROUP BY u.id, u.nombre
    ORDER BY total_contratos DESC
    """
    
    cursor.execute(query, (mes, anio))
    resumen = cursor.fetchall()
    cursor.close()
    
    return resumen
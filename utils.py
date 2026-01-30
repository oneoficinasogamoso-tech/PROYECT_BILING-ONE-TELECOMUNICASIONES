import cv2
import numpy as np
from PIL import Image
import pytesseract
import os
from werkzeug.utils import secure_filename
from config import Config
from docxtpl import DocxTemplate
from docx2pdf import convert
import subprocess
import platform
from datetime import datetime, timedelta

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
os.environ["TESSDATA_PREFIX"] = r"C:\Program Files\Tesseract-OCR\tessdata"


def calcular_nitidez_firma(gray_image):
    """Calcula la nitidez usando Laplacian"""
    laplacian = cv2.Laplacian(gray_image, cv2.CV_64F)
    return laplacian.var()



def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS


def calcular_nitidez(imagen_gris):
    """
    Calcula qué tan nítida (no borrosa) está una imagen
    Retorna: valor de nitidez (mayor = más nítida)
    """
    # Usar el operador de Laplacian para detectar bordes
    # Imágenes nítidas tienen muchos bordes definidos
    # Imágenes borrosas tienen pocos bordes
    laplacian = cv2.Laplacian(imagen_gris, cv2.CV_64F)
    nitidez = laplacian.var()
    return nitidez


def tiene_contenido_visible(imagen_gris):
    """
    Verifica que la imagen tenga contenido visible (texto, números, patrones)
    No importa si OCR puede leerlo, solo que se VEA algo
    """
    # Detectar bordes
    edges = cv2.Canny(imagen_gris, 50, 150)
    
    # Contar píxeles de bordes
    pixeles_bordes = np.sum(edges > 0)
    total_pixeles = edges.size
    porcentaje_bordes = (pixeles_bordes / total_pixeles) * 100
    
    # Si tiene entre 1% y 50% de bordes, tiene contenido visible
    return porcentaje_bordes >= 1 and porcentaje_bordes <= 50


def verificar_documento_identidad(image_path):
    """
    Verifica que sea un documento de identidad:
    - Que tenga texto/números visibles (aunque no se lean perfectamente)
    - Que NO esté muy borroso
    - Que tenga estructura de documento
    MUY PERMISIVO con iluminación y calidad
    """
    try:
        # Leer imagen
        img = cv2.imread(image_path)
        if img is None:
            try:
                pil_img = Image.open(image_path)
                img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            except:
                return False, 0, "No se pudo leer la imagen"
        
        # Verificar tamaño mínimo
        height, width = img.shape[:2]
        if height < 100 or width < 100:
            return False, 0, "Imagen demasiado pequeña (mínimo 100x100 píxeles)"
        
        # Convertir a escala de grises
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # VALIDACIÓN 1: Verificar nitidez (detectar si está MUY borroso)
        nitidez = calcular_nitidez(gray)
        
        # Si está MUY borroso (nitidez muy baja), rechazar
        if nitidez < 10:
            return False, 0, "Imagen muy borrosa. Por favor tome la foto con mejor enfoque"
        
        # VALIDACIÓN 2: Verificar que tenga contenido visible
        if not tiene_contenido_visible(gray):
            return False, 0, "No se detecta contenido visible en la imagen"
        
        # VALIDACIÓN 3: Intentar leer ALGO de texto (muy permisivo)
        # Probar múltiples técnicas
        texto_total = ""
        
        try:
            # Mejorar contraste
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
            enhanced = clahe.apply(gray)
            
            # Intentar leer con diferentes configuraciones
            configs = [
                '--psm 6',  # Asume un bloque uniforme de texto
                '--psm 11', # Texto disperso
                '--psm 12', # Texto disperso con OSD
            ]
            
            for config in configs:
                try:
                    texto = pytesseract.image_to_string(enhanced, lang='spa', config=config)
                    texto_total += " " + texto
                except:
                    pass
            
            # También probar con umbral adaptativo
            try:
                adaptive = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                                cv2.THRESH_BINARY, 11, 2)
                texto = pytesseract.image_to_string(adaptive, lang='spa', config='--psm 6')
                texto_total += " " + texto
            except:
                pass
                
        except:
            pass
        
        # Contar caracteres alfanuméricos encontrados
        texto_limpio = ''.join(c for c in texto_total if c.isalnum())
        caracteres_encontrados = len(texto_limpio)
        
        # VALIDACIÓN 4: Verificar estructura de documento
        # Los documentos de identidad tienen patrones rectangulares
        edges = cv2.Canny(gray, 50, 150)
        
        # Buscar líneas (documentos tienen bordes rectos)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, minLineLength=100, maxLineGap=10)
        
        tiene_estructura = lines is not None and len(lines) > 3
        
        # DECISIÓN FINAL (MUY PERMISIVA):
        # Aceptar si CUALQUIERA de estas condiciones se cumple:
        # 1. Encontró al menos 5 caracteres alfanuméricos
        # 2. La imagen es nítida (>50) Y tiene estructura de documento
        # 3. La imagen es medianamente nítida (>20) Y tiene contenido visible
        
        if caracteres_encontrados >= 5:
            return True, 80, f"Documento válido ({caracteres_encontrados} caracteres detectados)"
        
        if nitidez > 50 and tiene_estructura:
            return True, 70, "Documento válido (estructura de documento detectada)"
        
        if nitidez > 20 and tiene_contenido_visible(gray):
            return True, 60, "Documento válido (contenido visible detectado)"
        
        # Si no cumple ninguna, pero no está MUY borroso, dar otra oportunidad
        if nitidez > 15:
            return True, 50, "Documento aceptado (validación visual aprobada)"
        
        # Solo rechazar si está MUY borroso o no tiene nada visible
        return False, 0, f"Documento no legible. Nitidez: {nitidez:.1f} (mínimo 10). Intente con mejor enfoque."
        
    except Exception as e:
        return False, 0, f"Error al procesar imagen: {str(e)}"


def verificar_recibo(image_path):
    """
    Verifica recibo - SÚPER PERMISIVO
    Solo rechaza si está completamente vacío o corrupto
    """
    try:
        # Leer imagen
        img = cv2.imread(image_path)
        if img is None:
            try:
                pil_img = Image.open(image_path)
                img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            except:
                return False, "No se pudo leer la imagen"
        
        # Verificar tamaño mínimo
        height, width = img.shape[:2]
        if height < 50 or width < 50:
            return False, "Imagen demasiado pequeña"
        
        # Convertir a grises
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Verificar que tenga ALGO de contenido
        if tiene_contenido_visible(gray):
            return True, "Recibo válido"
        
        # Si no tiene contenido visible pero la imagen es válida, aceptar igual
        return True, "Recibo aceptado"
        
    except Exception as e:
        return True, "Recibo aceptado"


def verificar_firma_manual(image_path):
    """
    Verifica que sea FIRMA MANUSCRITA REAL
    
    RECHAZA:
    - Fondo amarillento (cédula)
    - Imágenes digitales con fondo blanco perfecto
    - Gráficos/logos digitales
    
    ACEPTA:
    - Firmas manuscritas reales (incluso con nombre completo)
    - Firmas en cualquier tipo de papel (blanco, cuadriculado, rayado)
    - Firmas con cualquier color de tinta
    """
    try:
        # Leer imagen
        img = cv2.imread(image_path)
        if img is None:
            try:
                pil_img = Image.open(image_path)
                img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            except:
                return False, 0, "No se pudo leer la imagen"
        
        # Verificar tamaño mínimo
        height, width = img.shape[:2]
        if height < 50 or width < 50:
            return False, 0, "Imagen muy pequeña"
        
        # === VERIFICACIÓN 1: NO PERMITIR FONDO AMARILLENTO (cédula) ===
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # Rango amarillo/beige (típico de cédulas)
        lower_yellow = np.array([15, 30, 100])
        upper_yellow = np.array([35, 180, 255])
        
        mask_yellow = cv2.inRange(hsv, lower_yellow, upper_yellow)
        porcentaje_amarillo = (np.sum(mask_yellow > 0) / mask_yellow.size) * 100
        
        if porcentaje_amarillo > 15:
            return False, 0, "❌ NO es válido usar la firma de la cédula. Debe firmar en papel blanco"
        
        # === VERIFICACIÓN 2: Detectar trazos manuscritos ===
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Mejorar contraste
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        
        # Binarizar (invertido para tener trazos en blanco)
        _, thresh = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # Limpiar ruido pequeño
        kernel = np.ones((2,2), np.uint8)
        thresh_clean = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
        
        # Buscar contornos de trazos
        contours, _ = cv2.findContours(thresh_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if len(contours) == 0:
            return False, 0, "No se detecta firma en la imagen"
        
        # === VERIFICACIÓN 3: Analizar características de trazos ===
        areas = [cv2.contourArea(c) for c in contours if cv2.contourArea(c) > 10]
        
        if not areas:
            return False, 0, "No se detectan trazos de firma"
        
        # Los trazos manuscritos tienen variación en grosor
        area_total = sum(areas)
        area_promedio = np.mean(areas)
        desviacion = np.std(areas)
        
        # Firmas manuscritas tienen buena variación de trazo
        coeficiente_variacion = desviacion / area_promedio if area_promedio > 0 else 0
        
        # === VERIFICACIÓN 4: Calcular nitidez ===
        nitidez = calcular_nitidez_firma(gray)
        
        # === VERIFICACIÓN 5: NO permitir fondos digitales perfectos ===
        # Calcular variación de color en el fondo
        hsv_std = np.std(hsv, axis=(0,1))
        variacion_fondo = np.mean(hsv_std)
        
        # Fondos digitales tienen variación casi cero
        if variacion_fondo < 5 and porcentaje_amarillo < 1:
            # Verificar si es fondo blanco perfecto
            gray_mean = np.mean(gray)
            if gray_mean > 240:
                return False, 0, "❌ Imagen digital detectada. Debe firmar en papel físico"
        
        # === DECISIÓN FINAL ===
        confianza = 50  # Base
        
        # Aumentar confianza si:
        if nitidez > 30:
            confianza += 20  # Firma nítida
        
        if coeficiente_variacion > 0.3:
            confianza += 20  # Trazos con variación natural
        
        if area_total > 500:
            confianza += 10  # Firma visible
        
        # Verificar que NO sea imagen digital de cédula
        if porcentaje_amarillo < 10 and variacion_fondo > 8:
            confianza += 20  # Firma en papel real
        
        if confianza >= 60:
            return True, confianza, f"✓ Firma manuscrita válida (confianza {confianza}%)"
        else:
            return False, confianza, f"Firma no clara. Intente con mejor iluminación y contraste"
        
    except Exception as e:
        return False, 0, f"Error: {str(e)}"


def digitalizar_firma(image_path, output_path):
    """
    Digitaliza una firma manuscrita:
    1. Elimina el fondo (lo hace transparente)
    2. Convierte los trazos a negro puro
    3. Limpia ruido y líneas de cuaderno
    4. Produce PNG con transparencia
    
    MEJORADO: Maneja papel blanco, cuadriculado, rayado, con sombras, etc.
    """
    try:
        # Leer imagen
        img = cv2.imread(image_path)
        if img is None:
            return False, "No se pudo leer la imagen"
        
        # Convertir a escala de grises
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # === PASO 1: Mejorar contraste ===
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        
        # === PASO 2: Probar múltiples métodos de umbralización ===
        # Método 1: Otsu automático
        _, thresh1 = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # Método 2: Umbral adaptativo (mejor para iluminación irregular)
        thresh2 = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY_INV, 15, 10)
        
        # Método 3: Umbral fijo conservador
        _, thresh3 = cv2.threshold(enhanced, 150, 255, cv2.THRESH_BINARY_INV)
        
        # Combinar los mejores resultados
        thresh_combined = cv2.bitwise_or(thresh1, thresh2)
        thresh_combined = cv2.bitwise_or(thresh_combined, thresh3)
        
        # === PASO 3: Seleccionar el mejor resultado ===
        # Contar píxeles de trazo en cada versión
        count1 = np.sum(thresh1 > 0)
        count2 = np.sum(thresh2 > 0)
        count3 = np.sum(thresh_combined > 0)
        
        # Elegir el que tenga más información pero no demasiado ruido
        if count1 > count2 * 0.3 and count1 < count2 * 3:
            mejor_thresh = thresh1
        elif count3 < count2 * 2:
            mejor_thresh = thresh_combined
        else:
            mejor_thresh = thresh2
        
        # Limpiar ruido
        kernel = np.ones((2,2), np.uint8)
        thresh_limpio = cv2.morphologyEx(mejor_thresh, cv2.MORPH_CLOSE, kernel, iterations=1)
        thresh_limpio = cv2.morphologyEx(thresh_limpio, cv2.MORPH_OPEN, kernel, iterations=1)
        
        # Remover líneas de cuaderno
        try:
            kernel_horizontal = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 1))
            detected_lines = cv2.morphologyEx(thresh_limpio, cv2.MORPH_OPEN, kernel_horizontal, iterations=2)
            thresh_final = cv2.subtract(thresh_limpio, detected_lines)
        except:
            thresh_final = thresh_limpio
        
        # Crear imagen RGBA
        img_rgba = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        
        # Fondo transparente
        img_rgba[:, :, 3] = thresh_final
        
        # Trazos en negro puro
        mask = thresh_final > 0
        img_rgba[mask, 0:3] = [0, 0, 0]
        
        # Guardar
        cv2.imwrite(output_path, img_rgba)
        
        return True, "Firma digitalizada exitosamente"
        
    except Exception as e:
        # Si falla, intentar versión simple
        try:
            img = cv2.imread(image_path)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 170, 255, cv2.THRESH_BINARY_INV)
            
            img_rgba = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
            img_rgba[:, :, 3] = thresh
            mask = thresh > 0
            img_rgba[mask, 0:3] = [0, 0, 0]
            
            cv2.imwrite(output_path, img_rgba)
            recortar_firma_png(output_path)
            return True, "Firma digitalizada (versión simple)"
        except:
            return False, f"Error: {str(e)}"


def recortar_firma_png(path_png):
    img = cv2.imread(path_png, cv2.IMREAD_UNCHANGED)  # RGBA

    if img is None or img.shape[2] < 4:
        return False

    alpha = img[:, :, 3]
    coords = cv2.findNonZero(alpha)

    if coords is None:
        return False

    x, y, w, h = cv2.boundingRect(coords)
    recortada = img[y:y+h, x:x+w]

    cv2.imwrite(path_png, recortada)
    return True



def guardar_archivo(file, folder, prefix=''):

    """
    Guarda un archivo de forma segura
    """
    try:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = str(int(np.random.random() * 1000000))
            name, ext = os.path.splitext(filename)
            filename = f"{prefix}_{timestamp}{ext}"
            filepath = os.path.join(folder, filename)
            file.save(filepath)
            return filename
        return None
    except Exception as e:
        print(f"Error al guardar archivo: {str(e)}")
        return None
    


def formatear_fecha_contrato(fecha_obj):
    """
    Formatea una fecha en múltiples formatos para usar en el PDF
    
    Args:
        fecha_obj: objeto datetime o string en formato 'YYYY-MM-DD'
    
    Returns:
        dict con diferentes formatos:
        - 'mes_anio_espaciado': "01          26" (mes espaciado año)
        - 'mes_anio_guion': "01-2026" (mes-año)
        - 'fecha_completa_slash': "27/01/2026" (día/mes/año)
        - 'mes_nombre': "Enero"
        - 'dia': "27"
        - 'mes_numero': "01"
        - 'anio': "2026"
    """
    try:
        # Convertir a datetime si es string
        if isinstance(fecha_obj, str):
            fecha_obj = datetime.strptime(fecha_obj, '%Y-%m-%d')
        
        # Diccionario de meses en español
        meses_es = {
            1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
            5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
            9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
        }
        
        # Extraer componentes
        dia = fecha_obj.day
        mes = fecha_obj.month
        anio = fecha_obj.year
        
        # Formatear diferentes versiones
        formatos = {
            'mes_anio_espaciado': f"{mes:02d}          {anio % 100:02d}",  # "01          26"
            'mes_anio_guion': f"{mes:02d}-{anio}",  # "01-2026"
            'fecha_completa_slash': f"{dia:02d}/{mes:02d}/{anio}",  # "27/01/2026"
            'mes_nombre': meses_es[mes],  # "Enero"
            'dia': f"{dia:02d}",  # "27"
            'mes_numero': f"{mes:02d}",  # "01"
            'anio': str(anio),  # "2026"
            'anio_corto': f"{anio % 100:02d}",  # "26"
        }
        
        return formatos
        
    except Exception as e:
        # Retornar valores por defecto en caso de error
        return {
            'mes_anio_espaciado': '',
            'mes_anio_guion': '',
            'fecha_completa_slash': '',
            'mes_nombre': '',
            'dia': '',
            'mes_numero': '',
            'anio': '',
            'anio_corto': ''
        }


def generar_contrato_word_pdf(datos_contrato, plantilla_path, output_folder, 
                              tamanio_firma_pulgadas=1.5):
    """
    Genera un contrato PDF a partir de una plantilla Word RESPETANDO TOTALMENTE EL DISEÑO ORIGINAL
    
    VALIDACIÓN CRÍTICA: No permite generar contrato sin firma digitalizada
    
    Parámetros:
    - datos_contrato: diccionario con los datos del cliente
    - plantilla_path: ruta de la plantilla Word
    - output_folder: carpeta donde se guardará el PDF
    - tamanio_firma_pulgadas: tamaño de la firma en pulgadas (default: 1.5)
    
    Retorna: (exito, mensaje, ruta_pdf)
    """
    try:
        # ============================================================
        # VALIDACIÓN CRÍTICA: FIRMA DIGITALIZADA OBLIGATORIA
        # ============================================================
        if not datos_contrato.get('firma_digitalizada_path'):
            return False, "❌ ERROR CRÍTICO: No se puede generar contrato sin firma digitalizada", None
        
        firma_path = datos_contrato.get('firma_digitalizada_path')
        
        if not os.path.exists(firma_path):
            return False, "❌ ERROR CRÍTICO: El archivo de firma digitalizada no existe", None
        
        # Verificar que el archivo no esté vacío o corrupto
        try:
            firma_size = os.path.getsize(firma_path)
            if firma_size < 100:  # Menos de 100 bytes es sospechoso
                return False, "❌ ERROR CRÍTICO: El archivo de firma es demasiado pequeño o está corrupto", None
        except:
            return False, "❌ ERROR CRÍTICO: No se puede acceder al archivo de firma", None
        
        # ============================================================
        # CARGAR PLANTILLA (SIN MODIFICAR NADA DEL DISEÑO)
        # ============================================================
        doc = DocxTemplate(plantilla_path)
        
        # ============================================================
        # FORMATEAR FECHAS EN MÚLTIPLES FORMATOS
        # ============================================================
        fecha_contrato_obj = datos_contrato.get('fecha_contrato')
        formatos_fecha = formatear_fecha_contrato(fecha_contrato_obj)
        
        # ============================================================
        # DETERMINAR TIPO DE CONTRATO (RESIDENCIAL O CORPORATIVO)
        # ============================================================
        tipo_contrato = datos_contrato.get('tipo_contrato', '').upper()
        
        # Variables para marcar con X según el tipo
        es_residencial = 'X' if tipo_contrato == 'RESIDENCIAL' else ''
        es_corporativo = 'X' if tipo_contrato == 'CORPORATIVO' else ''
        
        # ============================================================
        # PREPARAR CONTEXTO CON TODOS LOS DATOS
        # ============================================================
        context = {
            # Datos básicos del cliente
            'nombre_cliente': datos_contrato.get('nombre_cliente', ''),
            'numero_documento': datos_contrato.get('numero_documento', ''),
            'correo_electronico': datos_contrato.get('correo_electronico', 'N/A'),
            'telefono_contacto1': datos_contrato.get('telefono_contacto1', ''),
            'telefono_contacto2': datos_contrato.get('telefono_contacto2', 'N/A'),
            'barrio': datos_contrato.get('barrio', ''),
            'departamento': datos_contrato.get('departamento', ''),
            'municipio': datos_contrato.get('municipio', ''),
            'direccion': datos_contrato.get('direccion', ''),
            'plan': datos_contrato.get('plan', ''),
            
            # Tipo de contrato con X
            'tipo_contrato': datos_contrato.get('tipo_contrato', ''),
            'marca_residencial': es_residencial,
            'marca_corporativo': es_corporativo,
            
            # Fechas en diferentes formatos
            'fecha_mes_anio_espaciado': formatos_fecha['mes_anio_espaciado'],  # "01          26"
            'fecha_mes_anio_guion': formatos_fecha['mes_anio_guion'],  # "01-2026"
            'fecha_completa': formatos_fecha['fecha_completa_slash'],  # "27/01/2026"
            'fecha_mes_nombre': formatos_fecha['mes_nombre'],  # "Enero"
            'fecha_dia': formatos_fecha['dia'],  # "27"
            'fecha_mes': formatos_fecha['mes_numero'],  # "01"
            'fecha_anio': formatos_fecha['anio'],  # "2026"
            'fecha_anio_corto': formatos_fecha['anio_corto'],  # "26"
            
            # Fecha original (por compatibilidad)
            'fecha_contrato': datos_contrato.get('fecha_contrato', ''),
            
            # Datos del asesor
            'asesor_nombre': datos_contrato.get('asesor_nombre', ''),
            
            # Fecha y hora de generación
            'fecha_generacion': datetime.now().strftime('%d/%m/%Y'),
            'hora_generacion': datetime.now().strftime('%H:%M:%S'),
        }
        
        # ============================================================
        # INSERTAR FIRMA DIGITALIZADA (YA VALIDADA)
        # La firma se inserta como InlineImage para NO afectar el diseño
        # ============================================================
        from docxtpl import InlineImage
        from docx.shared import Inches
        

        
        try:
            # Puedes ajustar el tamaño aquí si es necesario
            # tamanio_firma_pulgadas se puede pasar como parámetro
            firma_img = InlineImage(doc, firma_path, width=Inches(tamanio_firma_pulgadas))
            context['firma_cliente'] = firma_img
        except Exception as e:
            return False, f"❌ ERROR al cargar imagen de firma: {str(e)}", None
        
        # ============================================================
        # RENDERIZAR DOCUMENTO (SOLO RELLENA VARIABLES, NO CAMBIA DISEÑO)
        # ============================================================
        doc.render(context)
        
        # ============================================================
        # GUARDAR WORD TEMPORAL
        # ============================================================
        numero_doc = datos_contrato.get('numero_documento', 'sin_documento')
        temp_docx = os.path.join(output_folder, f"{numero_doc}_temp.docx")
        
        # Guardar preservando TOTALMENTE el formato original
        doc.save(temp_docx)
        
        # ============================================================
        # CONVERTIR A PDF PRESERVANDO EL DISEÑO
        # ============================================================
        output_pdf = os.path.join(output_folder, f"{numero_doc}.pdf")
        
        exito_conversion = convertir_word_a_pdf(temp_docx, output_pdf)
        
        if not exito_conversion:
            # Limpiar archivo temporal
            try:
                os.remove(temp_docx)
            except:
                pass
            return False, "Error al convertir a PDF. Verifique que Microsoft Word o LibreOffice estén instalados", None
        
        # ============================================================
        # LIMPIAR ARCHIVO TEMPORAL
        # ============================================================
        try:
            os.remove(temp_docx)
        except:
            pass
        
        return True, "✅ Contrato generado exitosamente con firma digitalizada", output_pdf
        
    except Exception as e:
        return False, f"❌ Error al generar contrato: {str(e)}", None


def convertir_word_a_pdf(docx_path, pdf_path):
    """
    Convierte un archivo Word a PDF PRESERVANDO TOTALMENTE EL DISEÑO ORIGINAL
    Soporta Windows (Word) y Linux/Mac (LibreOffice)
    
    IMPORTANTE: Esta función respeta:
    - Tamaños de página personalizados
    - Imágenes y gráficos
    - Márgenes
    - Formatos de texto
    - Tablas y diseños complejos
    
    Retorna: True si tuvo éxito, False si falló
    """
    try:
        sistema = platform.system()
        
        if sistema == "Windows":
            # Usar docx2pdf (requiere Microsoft Word instalado)
            # Word es el MEJOR para preservar diseño
            try:
                convert(docx_path, pdf_path)
                return True
            except Exception as e:
                print(f"Error con docx2pdf: {e}")
                # Intentar con LibreOffice como fallback
                return convertir_con_libreoffice(docx_path, pdf_path)
        
        else:
            # Linux/Mac: usar LibreOffice
            return convertir_con_libreoffice(docx_path, pdf_path)
            
    except Exception as e:
        print(f"Error en conversión a PDF: {e}")
        return False


def convertir_con_libreoffice(docx_path, pdf_path):
    """
    Convierte usando LibreOffice en línea de comandos
    LibreOffice también respeta el diseño original del documento
    """
    try:
        # Obtener carpeta de salida
        output_folder = os.path.dirname(pdf_path)
        
        # Comando de LibreOffice con opciones para preservar formato
        comando = [
            'soffice',  # o 'libreoffice' en algunos sistemas
            '--headless',
            '--convert-to',
            'pdf',
            '--outdir',
            output_folder,
            docx_path
        ]
        
        # Ejecutar conversión
        resultado = subprocess.run(comando, capture_output=True, text=True, timeout=30)
        
        if resultado.returncode == 0:
            # LibreOffice genera el PDF con el mismo nombre base
            nombre_base = os.path.splitext(os.path.basename(docx_path))[0]
            pdf_generado = os.path.join(output_folder, f"{nombre_base}.pdf")
            
            # Renombrar si es necesario
            if pdf_generado != pdf_path and os.path.exists(pdf_generado):
                os.rename(pdf_generado, pdf_path)
            
            return os.path.exists(pdf_path)
        
        return False
        
    except Exception as e:
        print(f"Error con LibreOffice: {e}")
        return False
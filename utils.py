import cv2
import numpy as np
from PIL import Image
import pytesseract
import os
from werkzeug.utils import secure_filename
from config import Config



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
    - Papel blanco con cuadrículas
    - Trazos naturales e irregulares
    """
    try:
        img = cv2.imread(image_path)
        if img is None:
            try:
                pil_img = Image.open(image_path)
                img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            except:
                return False, "No se pudo leer la imagen"
        
        height, width = img.shape[:2]
        if height < 30 or width < 30:
            return False, "Imagen demasiado pequeña"
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # ========== VALIDACIÓN 1: FONDO DE CÉDULA (AMARILLENTO + PATRONES) ==========
        
        # 1.1 Analizar color GENERAL de la imagen (no solo píxeles >200)
        # Cédulas pueden ser fotos oscuras pero mantienen el tono amarillento
        
        # Analizar áreas más claras de la imagen (top 50-70% de brillos)
        umbral_adaptativo = int(np.percentile(gray, 30))  # Umbral del 30% más claro
        mask_areas_claras = gray > umbral_adaptativo
        
        es_amarillento = False
        tiene_variacion_cedula = False
        
        if np.sum(mask_areas_claras) > (gray.size * 0.2):  # Al menos 20% de la imagen
            pixeles_claros = img[mask_areas_claras]
            
            if len(pixeles_claros) > 100:
                # Análisis HSV
                fondo_hsv = cv2.cvtColor(pixeles_claros.reshape(1, -1, 3), cv2.COLOR_BGR2HSV)
                hue = np.mean(fondo_hsv[:, :, 0])
                sat = np.mean(fondo_hsv[:, :, 1])
                val = np.mean(fondo_hsv[:, :, 2])
                
                # Detectar amarillo/beige característico de cédula
                # Hue 25-45 = amarillo/beige, Sat 15-60 = sutil, Val > 140
                if 25 <= hue <= 45 and 15 <= sat <= 60 and val >= 140:
                    es_amarillento = True
                
                # Análisis BGR - característica clave de amarillo
                fondo_bgr = pixeles_claros.reshape(-1, 3)
                mean_b = np.mean(fondo_bgr[:, 0])
                mean_g = np.mean(fondo_bgr[:, 1])
                mean_r = np.mean(fondo_bgr[:, 2])
                
                # Amarillo/beige: G y R mayores que B
                if mean_b > 0 and mean_g > mean_b and mean_r > mean_b:
                    ratio_amarillo = (mean_g + mean_r) / (2 * mean_b)
                    
                    # Ratio > 1.05 indica tono amarillento
                    if ratio_amarillo > 1.05:
                        es_amarillento = True
                
                # Variación característica de cédula (textura sutil)
                std_b = np.std(fondo_bgr[:, 0])
                std_g = np.std(fondo_bgr[:, 1])
                std_r = np.std(fondo_bgr[:, 2])
                
                # Cédulas tienen variación sutil (8-35)
                # Papel blanco puro < 8 o papel fotografiado > 35
                if 8 < std_b < 35 and 8 < std_g < 35 and 8 < std_r < 35:
                    tiene_variacion_cedula = True
        
        # 1.2 Detección directa de fondo amarillento evidente
        _, mask_fondo_claro = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        pixeles_muy_claros = img[mask_fondo_claro == 255]
        
        if len(pixeles_muy_claros) > 100:
            fondo_hsv = cv2.cvtColor(pixeles_muy_claros.reshape(1, -1, 3), cv2.COLOR_BGR2HSV)
            hue = np.mean(fondo_hsv[:, :, 0])
            sat = np.mean(fondo_hsv[:, :, 1])
            val = np.mean(fondo_hsv[:, :, 2])
            
            # Amarillo evidente
            if 15 <= hue <= 45 and sat > 25 and val >= 170:
                return False, "Fondo amarillento de cédula detectado. No use firma de cédula"
        
        # 1.3 Si es amarillento + tiene variación de cédula = RECHAZAR
        if es_amarillento and tiene_variacion_cedula:
            return False, "Características de papel de cédula detectadas. No use firma de cédula"
        
        # 1.4 Solo amarillento pero sin variación característica (puede ser iluminación)
        if es_amarillento:
            # Verificar si es amarillo fuerte o solo iluminación
            img_hsv_completa = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            sat_general = np.mean(img_hsv_completa[:, :, 1])
            
            if sat_general > 20:  # Saturación significativa en toda la imagen
                return False, "Tono amarillento detectado. Verifique que no sea firma de cédula"
        
        # ========== VALIDACIÓN 2: FONDO BLANCO DEMASIADO PERFECTO (IMAGEN DIGITAL) ==========
        # Analizar uniformidad del fondo blanco
        pixeles_blancos = gray[gray > 230]
        
        if len(pixeles_blancos) > (gray.size * 0.7):  # Más del 70% es muy blanco
            # Calcular variación del fondo blanco
            std_fondo_blanco = np.std(pixeles_blancos)
            mean_fondo_blanco = np.mean(pixeles_blancos)
            
            # Fondo digital tiene MUY poca variación (casi todos 255)
            # Fondo real (foto de papel) tiene más variación por iluminación/textura
            if std_fondo_blanco < 3.0 and mean_fondo_blanco > 250:
                return False, "Fondo blanco demasiado perfecto. Parece imagen digital, no foto real"
        
        # ========== VALIDACIÓN 3: DETECTAR BORDES DEMASIADO DEFINIDOS ==========
        # Analizar contraste extremo (típico de gráficos digitales)
        pixeles_oscuros = gray[gray < 100]
        pixeles_claros = gray[gray > 200]
        
        total_pixeles = gray.size
        porcentaje_extremos = (len(pixeles_oscuros) + len(pixeles_claros)) / total_pixeles
        
        # Si más del 95% son extremos (muy negro o muy blanco) = digital
        if porcentaje_extremos > 0.95:
            # Calcular gradiente para ver si hay transiciones suaves
            gradiente = cv2.Sobel(gray, cv2.CV_64F, 1, 1, ksize=3)
            gradiente_std = np.std(gradiente)
            
            # Gráficos digitales tienen transiciones muy abruptas
            if gradiente_std > 50:
                return False, "Bordes muy definidos. Parece gráfico digital, no firma real"
        
        # ========== VALIDACIÓN 4: NITIDEZ ==========
        nitidez = calcular_nitidez_firma(gray)
        if nitidez < 3:
            return False, "Firma muy borrosa"
        
        # ========== EXTRAER TRAZOS ==========
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        
        mejor_thresh = None
        mejor_porcentaje = 0
        
        for umbral in [120, 140, 160, 180, 200]:
            _, thresh_temp = cv2.threshold(enhanced, umbral, 255, cv2.THRESH_BINARY_INV)
            pixeles = np.sum(thresh_temp > 0)
            porcentaje = (pixeles / thresh_temp.size) * 100
            
            if 0.2 <= porcentaje <= 45:
                if mejor_thresh is None or abs(porcentaje - 8) < abs(mejor_porcentaje - 8):
                    mejor_porcentaje = porcentaje
                    mejor_thresh = thresh_temp
        
        if mejor_thresh is None:
            mejor_thresh = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                                 cv2.THRESH_BINARY_INV, 11, 2)
            pixeles = np.sum(mejor_thresh > 0)
            porcentaje = (pixeles / mejor_thresh.size) * 100
        else:
            porcentaje = mejor_porcentaje
        
        if porcentaje < 0.15:
            return False, "No se detectan trazos de firma"
        
        if porcentaje > 50:
            return False, "Imagen muy oscura"
        
        # ========== PREPARAR ==========
        kernel = np.ones((2,2), np.uint8)
        thresh_limpio = cv2.morphologyEx(mejor_thresh, cv2.MORPH_CLOSE, kernel, iterations=1)
        
        # Remover líneas de cuaderno (esto está bien, las cuadrículas no afectan)
        try:
            kernel_horiz = cv2.getStructuringElement(cv2.MORPH_RECT, (60, 1))
            lineas = cv2.morphologyEx(thresh_limpio, cv2.MORPH_OPEN, kernel_horiz, iterations=2)
            thresh_limpio = cv2.subtract(thresh_limpio, lineas)
        except:
            pass
        
        # ========== OBTENER CONTORNOS ==========
        contornos, _ = cv2.findContours(thresh_limpio, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contornos_validos = [c for c in contornos if cv2.contourArea(c) > 20]
        
        if len(contornos_validos) < 1:
            return False, "No se detectan trazos de firma"
        
        # ========== VALIDACIÓN 5: ANALIZAR NATURALIDAD DE TRAZOS ==========
        # Firmas reales tienen variación de grosor y bordes irregulares
        # Gráficos digitales son muy uniformes
        
        trazos_muy_uniformes = 0
        total_trazos = 0
        
        for contorno in contornos_validos:
            area = cv2.contourArea(contorno)
            if area < 50:
                continue
            
            total_trazos += 1
            
            # Analizar perímetro vs área
            perimetro = cv2.arcLength(contorno, True)
            if perimetro > 0:
                compacidad = (4 * np.pi * area) / (perimetro ** 2)
                
                # Trazos muy circulares/perfectos = digital
                # Trazos alargados/irregulares = manuscrito
                if compacidad > 0.7:  # Muy circular
                    trazos_muy_uniformes += 1
        
        # Si muchos trazos son muy uniformes/circulares = posible digital
        if total_trazos >= 3 and trazos_muy_uniformes >= total_trazos * 0.7:
            return False, "Trazos muy uniformes. Parece gráfico digital"
        
        # ========== VALIDACIÓN 6: ANALIZAR TEXTURA DEL PAPEL ==========
        # Fotos reales de papel tienen textura/ruido
        # Imágenes digitales son muy limpias
        
        # Tomar muestra del fondo
        muestra_fondo = gray[gray > 200]
        
        if len(muestra_fondo) > 100:
            # Calcular entropía (complejidad) del fondo
            hist, _ = np.histogram(muestra_fondo, bins=20, range=(200, 256))
            hist = hist / hist.sum()
            entropia = -np.sum(hist * np.log2(hist + 1e-10))
            
            # Fondo digital tiene muy baja entropía (casi todos píxeles iguales)
            # Fondo real tiene más variación
            if entropia < 1.5:
                # Verificar también uniformidad extrema
                std_muestra = np.std(muestra_fondo)
                if std_muestra < 2.5:
                    return False, "Fondo muy uniforme. Parece imagen digital"
        
        # ========== TODO OK - FIRMA REAL ACEPTADA ==========
        return True, "Firma manuscrita válida"
        
    except Exception as e:
        # Fallback: Si hay error, ser permisivo con firmas que parecen reales
        try:
            # Análisis simplificado
            _, thresh = cv2.threshold(gray, 170, 255, cv2.THRESH_BINARY_INV)
            pixeles = np.sum(thresh > 0)
            porcentaje = (pixeles / thresh.size) * 100
            
            # Si tiene una cantidad razonable de tinta = probablemente firma real
            if 0.5 <= porcentaje <= 30:
                return True, "Firma aceptada (análisis simplificado)"
        except:
            pass
        
        return False, f"Error en análisis: {str(e)}"



def digitalizar_firma(image_path, output_path):
    """
    Digitaliza la firma removiendo el fondo
    Maneja cuadernos con líneas y diferentes iluminaciones
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
        
        # Convertir a escala de grises
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Mejorar contraste
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        
        # Encontrar mejor umbral
        mejor_thresh = None
        mejor_porcentaje = 0
        
        for umbral in [140, 160, 180]:
            _, thresh_temp = cv2.threshold(enhanced, umbral, 255, cv2.THRESH_BINARY_INV)
            pixeles = np.sum(thresh_temp > 0)
            porcentaje = (pixeles / thresh_temp.size) * 100
            
            if 1 <= porcentaje <= 35:
                if abs(porcentaje - 10) < abs(mejor_porcentaje - 10):
                    mejor_porcentaje = porcentaje
                    mejor_thresh = thresh_temp
        
        if mejor_thresh is None:
            mejor_thresh = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                                 cv2.THRESH_BINARY_INV, 11, 2)
        
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
            return True, "Firma digitalizada (versión simple)"
        except:
            return False, f"Error: {str(e)}"


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
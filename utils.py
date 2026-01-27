import cv2
import numpy as np
from PIL import Image
import pytesseract
import os
from werkzeug.utils import secure_filename
from config import Config

# Configurar la ruta de Tesseract (ajusta según tu instalación)
# Windows: pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

def verificar_documento_identidad(image_path):
    """
    Verifica si la imagen es legible y contiene texto de documento de identidad
    Retorna: (es_valido, confianza, texto_extraido)
    """
    try:
        # Leer imagen
        img = cv2.imread(image_path)
        if img is None:
            return False, 0, "No se pudo leer la imagen"
        
        # Convertir a escala de grises
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Mejorar contraste
        gray = cv2.equalizeHist(gray)
        
        # Aplicar umbral adaptativo
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                       cv2.THRESH_BINARY, 11, 2)
        
        # Extraer texto con OCR
        texto = pytesseract.image_to_string(thresh, lang='spa')
        
        # Palabras clave de documentos de identidad colombianos
        palabras_clave = ['cedula', 'ciudadania', 'republica', 'colombia', 
                          'identificacion', 'documento', 'nombre', 'apellido']
        
        texto_lower = texto.lower()
        coincidencias = sum(1 for palabra in palabras_clave if palabra in texto_lower)
        
        # Calcular confianza
        confianza = (coincidencias / len(palabras_clave)) * 100
        
        # Verificar que tenga suficiente texto (al menos 20 caracteres)
        es_valido = len(texto.strip()) > 20 and confianza > 15
        
        return es_valido, confianza, texto
        
    except Exception as e:
        return False, 0, f"Error: {str(e)}"

def verificar_firma_manual(image_path):
    """
    Verifica que la firma sea manual, en fondo blanco y con trazos negros
    Retorna: (es_valida, mensaje)
    """
    try:
        # Leer imagen
        img = cv2.imread(image_path)
        if img is None:
            return False, "No se pudo leer la imagen"
        
        # Convertir a HSV para análisis de color
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # Verificar que el fondo sea mayormente blanco
        # Contar píxeles blancos (alta luminosidad)
        v_channel = hsv[:,:,2]
        pixeles_blancos = np.sum(v_channel > 200)
        total_pixeles = v_channel.size
        porcentaje_blanco = (pixeles_blancos / total_pixeles) * 100
        
        if porcentaje_blanco < 60:
            return False, "El fondo debe ser completamente blanco"
        
        # Convertir a escala de grises
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Umbralizar para separar firma del fondo
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
        
        # Contar píxeles de la firma
        pixeles_firma = np.sum(thresh > 0)
        porcentaje_firma = (pixeles_firma / total_pixeles) * 100
        
        # Verificar que haya suficiente tinta (firma visible)
        if porcentaje_firma < 1:
            return False, "No se detecta una firma visible"
        
        if porcentaje_firma > 40:
            return False, "Demasiada tinta, asegúrate de usar fondo blanco limpio"
        
        # Buscar contornos para verificar que sean trazos continuos
        contornos, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if len(contornos) < 2:
            return False, "La firma parece ser muy simple o impresa"
        
        # Verificar variación en grosor de líneas (característica de firma manual)
        areas = [cv2.contourArea(c) for c in contornos]
        if len(areas) > 0 and max(areas) > 0:
            variacion = np.std(areas) / np.mean(areas) if np.mean(areas) > 0 else 0
            if variacion < 0.3:
                return False, "La firma parece ser impresa o digital"
        
        return True, "Firma válida"
        
    except Exception as e:
        return False, f"Error al verificar firma: {str(e)}"

def digitalizar_firma(image_path, output_path):
    """
    Digitaliza la firma removiendo el fondo y dejando solo los trazos
    Retorna: (exito, mensaje)
    """
    try:
        # Leer imagen
        img = cv2.imread(image_path)
        if img is None:
            return False, "No se pudo leer la imagen"
        
        # Convertir a escala de grises
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Umbralizar para separar firma del fondo
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
        
        # Aplicar operaciones morfológicas para limpiar
        kernel = np.ones((2,2), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        
        # Crear imagen con canal alpha
        img_rgba = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        
        # Hacer el fondo transparente
        img_rgba[:, :, 3] = thresh
        
        # Hacer los trazos negros puros
        mask = thresh > 0
        img_rgba[mask, 0:3] = [0, 0, 0]  # Negro puro
        
        # Guardar como PNG con transparencia
        cv2.imwrite(output_path, img_rgba)
        
        return True, "Firma digitalizada exitosamente"
        
    except Exception as e:
        return False, f"Error al digitalizar firma: {str(e)}"

def guardar_archivo(file, folder, prefix=''):
    """
    Guarda un archivo de forma segura
    Retorna: nombre del archivo guardado
    """
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Agregar timestamp para evitar sobrescrituras
        timestamp = str(int(np.random.random() * 1000000))
        name, ext = os.path.splitext(filename)
        filename = f"{prefix}_{timestamp}{ext}"
        filepath = os.path.join(folder, filename)
        file.save(filepath)
        return filename
    return None
import os


class Config:
    SECRET_KEY = '678908766789087'

    # Database configuration
    MYSQL_HOST = 'bodcmkeu41vr5guf9yyv-mysql.services.clever-cloud.com'
    MYSQL_USER = 'uoixtnvnmtvpmkel'
    MYSQL_PASSWORD = 'zZpEqgGz8gRWbaOs4zN'
    MYSQL_DB = 'bodcmkeu41vr5guf9yyv'
    MYSQL_PORT = 21324


    MYSQL_CURSORCLASS = 'DictCursor'
    MYSQL_CONNECT_TIMEOUT = 10

    PLANTILLAS_FOLDER = "plantillas"
    CONTRATOS_GENERADOS_FOLDER = "contratos_generados"

    # Configuración de archivos
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    CONTRATOS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'contratos_pdf')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    
    # Crear carpetas si no existen
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_FOLDER, 'cc_frontal'), exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_FOLDER, 'cc_trasera'), exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_FOLDER, 'firmas'), exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_FOLDER, 'firmas_digitalizadas'), exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_FOLDER, 'recibos'), exist_ok=True)
    os.makedirs(CONTRATOS_FOLDER, exist_ok=True)
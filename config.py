import os


class Config:
    SECRET_KEY = '678908766789087'

    # Database configuration
    MYSQL_HOST = 'bayhr8qklsiu6zqznnwh-mysql.services.clever-cloud.com'
    MYSQL_USER = 'uwioqepbquygtlkr'
    MYSQL_PASSWORD = '7INuvP2DNU3FpRcJCdoc'
    MYSQL_DB = 'bayhr8qklsiu6zqznnwh'
    MYSQL_PORT = 3306


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
from flask import Flask
from config import Config



def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # register blueprints and other setup here
    from rutas.login import login_bp
    from rutas.admin import admin_bp
    from rutas.asesor import asesor_bp
    from rutas.auxiliar import auxiliar_bp

    app.register_blueprint(login_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(asesor_bp)
    app.register_blueprint(auxiliar_bp)

    return app
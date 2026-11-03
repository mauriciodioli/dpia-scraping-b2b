"""Punto de entrada de la aplicación Flask DPIA."""
from flask import Flask

import config
from model import ma
from routes import auth_bp, main_bp
from routes.catalog_routes import catalog_bp
from routes.query_routes import query_bp
from utils.db import db


def create_app():
    app = Flask(__name__)
    app.config.from_object(config)

    db.init_app(app)
    ma.init_app(app)

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(query_bp)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=app.config["DEBUG"], host=app.config["HOST"], port=app.config["PORT"])

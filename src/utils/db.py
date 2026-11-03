"""Instancia única de SQLAlchemy compartida por toda la aplicación."""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

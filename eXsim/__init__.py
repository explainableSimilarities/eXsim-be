from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from waitress import serve
from paste.translogger import TransLogger

import os
load_dotenv()

db = SQLAlchemy()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('USER_DB_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = os.environ.get('SQLALCHEMY_TRACK_MODIFICATIONS')
CORS(app)

db.init_app(app)

from eXsim import router
serve(TransLogger(app), host='0.0.0.0', port=8080)
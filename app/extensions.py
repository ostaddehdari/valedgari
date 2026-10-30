from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect


db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate(compare_type=True, render_as_batch=True)


login_manager.login_view = "auth.login"
login_manager.login_message = "برای ادامه لطفاً وارد حساب والدین شوید."
login_manager.login_message_category = "warning"


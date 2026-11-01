import os

from dotenv import load_dotenv

from app import create_app, init_db
from config import DevelopmentConfig, ProductionConfig

# Load environment variables from .env
load_dotenv()

# Determine configuration
env = os.getenv('FLASK_ENV', 'production').strip().lower()
if env not in {'production', 'development'}:
    raise RuntimeError('FLASK_ENV must be production or development')
config_class = DevelopmentConfig if env == 'development' else ProductionConfig

# Create the Flask application using the factory
app = create_app(config_class)

# Ensure database tables exist even when running under WSGI servers (gunicorn)
with app.app_context():
    init_db()

# Run database initialization then start the server
if __name__ == '__main__':
    debug = app.config.get('DEBUG', False)
    host = app.config.get('HOST', '0.0.0.0')
    port = int(app.config.get('PORT', 5001))
    app.run(host=host, port=port, debug=debug)

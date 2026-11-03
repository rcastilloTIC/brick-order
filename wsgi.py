"""Alternative WSGI entry point; identical to the Docker one (run:app)."""
from run import app  # noqa: F401  (loads .env, selects config, initialises the DB)

if __name__ == "__main__":
    app.run()

"""Entry point for Gunicorn (Render) and `flask --app wsgi run` (local)."""
from edwom import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)

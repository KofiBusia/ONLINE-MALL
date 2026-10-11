"""Command-line tasks: `flask --app wsgi setup`, `seed-demo`, `create-admin`."""
import click

from .extensions import db
from .models import User
from .seed import ensure_admin, seed_demo
from .utils import valid_password


def register_cli(app):
    @app.cli.command("setup")
    def setup_cmd():
        """Run after `flask db upgrade`: ensure the super admin exists and load demo data if enabled."""
        click.echo(ensure_admin())
        if app.config["SEED_DEMO"]:
            click.echo("Demo shops loaded." if seed_demo() else "Shops exist; demo data skipped.")

    @app.cli.command("seed-demo")
    def seed_demo_cmd():
        """Load demo shops and products (only when there are no shops)."""
        click.echo("Demo data loaded." if seed_demo() else "Shops already exist; nothing loaded.")

    @app.cli.command("create-admin")
    @click.argument("email")
    @click.password_option()
    def create_admin(email, password):
        """Create a super admin or promote an existing account."""
        if msg := valid_password(password):
            raise click.BadParameter(msg)
        email = email.strip().lower()
        user = User.query.filter_by(email=email).first() or User(email=email, name="Edwom Super Admin")
        user.role = "admin"
        user.is_active_account = True
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Super admin ready: {email}")

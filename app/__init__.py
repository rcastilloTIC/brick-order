# app/__init__.py

import os
from flask import Flask, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from app.i18n import init_app as init_i18n

# Initialize extensions (no app context yet)
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)

def create_app(config_class=None):
    """Application factory."""
    base_dir = os.path.abspath(os.path.dirname(__file__))
    template_folder = os.path.abspath(os.path.join(base_dir, "..", "templates"))
    static_folder = os.path.abspath(os.path.join(base_dir, "..", "static"))
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
    # Load the effective configuration BEFORE making security decisions.  The
    # previous implementation read app.config before from_object/from_pyfile,
    # making TRUSTED_PROXY_COUNT ineffective even when explicitly configured.
    if config_class:
        app.config.from_object(config_class)
    else:
        app.config.from_pyfile('config.py')

    # Only honour forwarded headers from a correctly configured trusted proxy.
    # Direct connections must leave TRUSTED_PROXY_COUNT set to zero.
    proxy_count = app.config.get('TRUSTED_PROXY_COUNT', 0)
    if type(proxy_count) is not int or not 0 <= proxy_count <= 2:
        raise ValueError('TRUSTED_PROXY_COUNT must be an integer from 0 to 2')
    if proxy_count:
        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=proxy_count, x_proto=proxy_count,
            x_host=proxy_count, x_port=proxy_count,
        )

    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    storage_uri = app.config.get('RATELIMIT_STORAGE_URI')
    if storage_uri and hasattr(limiter, "storage_uri"):
        limiter.storage_uri = storage_uri
    limiter.init_app(app)
    init_i18n(app)

    # Login manager settings
    login_manager.login_view = 'auth.login'
    login_manager.session_protection = 'strong'
    login_manager.login_message_category = 'warning'

    # Register Blueprints
    from .auth.routes import auth_bp
    from .main.routes import main_bp
    from products.routes import products_bp
    from orders.routes import orders_bp

    app.register_blueprint(auth_bp)                  # no prefix -> root for auth routes
    from .main.translation_admin import translations_bp
    app.register_blueprint(translations_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(products_bp, url_prefix='/products')
    app.register_blueprint(orders_bp, url_prefix='/orders')

    @app.cli.command('capture-insights')
    def capture_insights_command():
        """Capture one observed point for the active campaign; schedule externally."""
        from app.services.active_campaign import current_campaign
        from app.services.order_insights import build_insights, capture_snapshot
        campaign = current_campaign()
        if campaign is None:
            print('SKIPPED: no active campaign; no snapshot needed')
            return
        stats = build_insights()
        changed = capture_snapshot(campaign.id, stats, minimum_minutes=0)
        print('Snapshot saved' if changed else 'No changes since last snapshot')

    @app.cli.command('check-shortage')
    def check_shortage_command():
        from app.services.shortage import reconcile
        result=reconcile()
        print(result if result else 'No active shortage window')

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    os.makedirs(app.config['DECLARATION_UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['ORDER_EXPORT_FOLDER'], exist_ok=True)
    backup_folder = app.config.get('BACKUP_FOLDER')
    if backup_folder:
        os.makedirs(backup_folder, exist_ok=True)

    from flask import request, redirect, url_for
    from flask_login import current_user

    @app.before_request
    def enforce_supported_campaign_phase():
        from flask import abort
        from app.services.campaign_phase import get_campaign_phase, PHASES
        if get_campaign_phase() not in PHASES:
            abort(409, description='Unsupported campaign phase; administrator must correct campaign state.')

    @app.before_request
    def enforce_user_onboarding():
        access_password = app.config.get("SITE_ACCESS_PASSWORD")
        if access_password:
            allowed = {"auth.site_access", "static"}
            if not session.get("site_access_granted") and (request.endpoint not in allowed):
                return redirect(url_for("auth.site_access", next=request.url))

        if not current_user.is_authenticated:
            return
        endpoint = request.endpoint or ""
        exempt = {
            "auth.logout",
            "auth.change_password",
            "auth.upload_declaration",
            "auth.declaration_pending",
            "auth.download_commitment",
            "static",
        }
        if current_user.must_change_password and endpoint not in exempt:
            return redirect(url_for("auth.change_password"))
        if current_user.is_admin:
            return
        from .models import Config
        from .services.active_campaign import current_campaign, current_membership
        # An enrolled participant must hold an approval for the CURRENT campaign.
        # Prior-year approvals in User are never sufficient once annual enrolment exists.
        campaign = current_campaign()
        if campaign is not None:
            membership = current_membership(current_user.id)
            if membership is None:
                if endpoint == 'auth.logout':
                    return
                from flask import abort
                abort(403, description='You are not enrolled in the active campaign.')
            if membership.status != 'approved' or not membership.signed_document:
                document_routes = {'auth.upload_declaration', 'auth.download_commitment',
                                   'auth.declaration_pending', 'auth.logout', 'static'}
                if endpoint not in document_routes:
                    target = ('auth.declaration_pending' if membership.signed_document
                              else 'auth.upload_declaration')
                    return redirect(url_for(target))
                # The legacy account-level gate below must not override campaign state.
                return
            # Annual approval is authoritative; the legacy account flags are not.
            return
        # No account-level fallback: the participant cannot use a previous year's
        # approval if the active campaign has not been registered yet.
        # Administrative routes are handled above; all other authenticated user
        # requests must wait for annual campaign registration.
        if endpoint not in {"auth.logout", "static"}:
            from flask import abort
            abort(409, description="No hay una campaña activa registrada.")


    @app.before_request
    def block_cancelled_campaign_mutations():
        from flask import request, abort
        from flask_login import current_user
        if request.method not in {'POST','PUT','PATCH','DELETE'}:
            return
        if not current_user.is_authenticated:
            return
        if request.endpoint in {'auth.logout','main.shortage_admin'}:
            return
        from app.services.shortage import window_for_active
        row=window_for_active()
        if row and row.status=='cancelled':
            abort(409, description='El pedido ha sido cancelado.')

    @app.context_processor
    def inject_app_env():
        return {
            "app_env": app.config.get("APP_ENV", "production"),
            "source_code_url": app.config.get("SOURCE_CODE_URL", ""),
        }

    return app

def init_db():
    """Create database tables and default records."""
    # Validate required credentials before *any* schema or data mutation.
    # A missing/placeholder password must not leave a partially initialized DB.
    admin_username = os.getenv('ADMIN_USERNAME', 'admin')
    admin_password = os.getenv('ADMIN_PASSWORD')
    if not admin_password or len(admin_password) < 12 or admin_password.startswith('REPLACE_'):
        raise RuntimeError('Set ADMIN_PASSWORD to a unique password of at least 12 characters')

    # Assumes an application context is active.
    db.create_all()
    _ensure_schema()

    # Create default admin user if not exists.
    from app.models import User
    if not User.query.filter_by(username=admin_username).first():
        admin = User(username=admin_username, is_admin=True)
        admin.set_password(admin_password)
        admin.must_change_password = False
        admin.declaration_validated = True
        db.session.add(admin)
        db.session.commit()


def _ensure_schema() -> None:
    """Backfill missing columns without full migrations."""
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    # Database-level protection against concurrent administrators creating
    # multiple operational campaigns. Existing databases receive the indexes
    # during init_db; invalid registries cause startup to fail closed.
    if db.engine.dialect.name == "sqlite" and "campaign" in inspector.get_table_names():
        with db.engine.begin() as conn:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_campaign_single_active "
                              "ON campaign ((1)) WHERE status = 'legacy_active'"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_campaign_single_draft "
                              "ON campaign ((1)) WHERE status = 'draft'"))
            # Reject invalid statuses at the database boundary, including writes
            # performed outside Flask. Do not rewrite legacy records silently.
            invalid = conn.execute(text(
                "SELECT COUNT(*) FROM campaign WHERE status IS NULL OR "
                "status NOT IN ('legacy_active', 'draft', 'archived', 'closed')"
            )).scalar()
            if invalid:
                raise RuntimeError('Campaign registry contains unknown statuses')
            # A draft and an active campaign must never coexist. The partial
            # indexes above only enforce uniqueness within each status.
            overlap = conn.execute(text(
                "SELECT COUNT(*) FROM campaign WHERE status = 'legacy_active'"
            )).scalar() and conn.execute(text(
                "SELECT COUNT(*) FROM campaign WHERE status = 'draft'"
            )).scalar()
            if overlap:
                raise RuntimeError('Active campaign and draft coexist')
            for operation in ('INSERT', 'UPDATE'):
                trigger_name = f'campaign_active_draft_exclusion_{operation.lower()}'
                conn.execute(text(f"""CREATE TRIGGER IF NOT EXISTS {trigger_name}
                    BEFORE {operation} ON campaign
                    WHEN NEW.status IN ('legacy_active', 'draft') AND EXISTS (
                        SELECT 1 FROM campaign AS other
                        WHERE other.id != NEW.id AND other.status IN ('legacy_active', 'draft')
                    )
                    BEGIN SELECT RAISE(ABORT, 'Active campaign and draft cannot coexist'); END"""))
            conn.execute(text("""CREATE TRIGGER IF NOT EXISTS campaign_status_insert_guard
                BEFORE INSERT ON campaign
                WHEN NEW.status IS NULL OR NEW.status NOT IN
                    ('legacy_active', 'draft', 'archived', 'closed')
                BEGIN SELECT RAISE(ABORT, 'Invalid campaign status'); END"""))
            conn.execute(text("""CREATE TRIGGER IF NOT EXISTS campaign_status_update_guard
                BEFORE UPDATE OF status ON campaign
                WHEN NEW.status IS NULL OR NEW.status NOT IN
                    ('legacy_active', 'draft', 'archived', 'closed')
                BEGIN SELECT RAISE(ABORT, 'Invalid campaign status'); END"""))

    # Enforce product ownership at the SQLite boundary, even for raw SQL writes.
    # Nullable campaign IDs are tolerated only for legacy migration records;
    # they cannot be used to link a scoped order/vote to another year.
    tables = set(inspector.get_table_names())
    if db.engine.dialect.name == "sqlite" and "product" in tables:
        with db.engine.begin() as conn:
            for table in ("order", "user_vote", "user_favorite"):
                if table not in tables:
                    continue
                cols = {c["name"] for c in inspector.get_columns(table)}
                if not {"campaign_id", "product_id"}.issubset(cols):
                    continue
                # Pre-existing inconsistent rows must be repaired explicitly,
                # rather than silently retained under newly installed guards.
                invalid = conn.execute(text(f"""SELECT COUNT(*) FROM "{table}" AS r
                    WHERE r.campaign_id IS NOT NULL AND NOT EXISTS (
                        SELECT 1 FROM product AS p
                        WHERE p.id = r.product_id AND p.campaign_id = r.campaign_id
                    )""")).scalar()
                if invalid:
                    raise RuntimeError(f"Cross-campaign product links in {table}: {invalid}")
                for operation in ("INSERT", "UPDATE"):
                    trigger = f"bom_{table}_product_scope_{operation.lower()}"
                    conn.execute(text(f"""CREATE TRIGGER IF NOT EXISTS {trigger}
                        BEFORE {operation} ON "{table}"
                        WHEN NEW.campaign_id IS NOT NULL AND
                          NOT EXISTS (SELECT 1 FROM product p
                            WHERE p.id = NEW.product_id AND
                                  p.campaign_id = NEW.campaign_id)
                        BEGIN SELECT RAISE(ABORT, 'Cross-campaign product link'); END"""))
            # Build the reverse guard only from tables and columns actually
            # present. Older databases can lack optional favourite tables.
            # Referencing a missing table in a SQLite trigger otherwise makes
            # product updates fail with "no such table" at runtime.
            linked_product_tables = []
            for linked_table in ("order", "user_vote", "user_favorite"):
                if linked_table not in tables:
                    continue
                linked_columns = {c["name"] for c in inspector.get_columns(linked_table)}
                if {"product_id", "campaign_id"}.issubset(linked_columns):
                    linked_product_tables.append(linked_table)
            if linked_product_tables:
                product_references = " OR ".join(
                    f'EXISTS (SELECT 1 FROM "{linked_table}" r '
                    'WHERE r.product_id = OLD.id AND r.campaign_id IS NOT NULL '
                    'AND (NEW.campaign_id IS NULL OR r.campaign_id != NEW.campaign_id))'
                    for linked_table in linked_product_tables
                )
                conn.execute(text(f"""CREATE TRIGGER IF NOT EXISTS bom_product_campaign_move_guard
                    BEFORE UPDATE OF campaign_id ON product
                    WHEN {product_references}
                    BEGIN SELECT RAISE(ABORT, 'Product campaign has linked records'); END"""))

    # A vote, favourite or order must belong to an enrolled user in that year.
    # Existing legacy rows are diagnosed by annual_readiness; do not destroy them.
    if db.engine.dialect.name == "sqlite" and "campaign_participation" in tables:
        with db.engine.begin() as conn:
            for table in ("order", "user_vote", "user_favorite"):
                if table not in tables:
                    continue
                columns = {column["name"] for column in inspector.get_columns(table)}
                if not {"campaign_id", "user_id"}.issubset(columns):
                    continue
                for operation in ("INSERT", "UPDATE"):
                    trigger = f"bom_{table}_annual_member_{operation.lower()}"
                    conn.execute(text(f"""CREATE TRIGGER IF NOT EXISTS {trigger}
                        BEFORE {operation} ON \"{table}\"
                        WHEN NEW.campaign_id IS NOT NULL AND NOT EXISTS (
                            SELECT 1 FROM campaign_participation cp
                            WHERE cp.campaign_id = NEW.campaign_id
                              AND cp.user_id = NEW.user_id)
                        BEGIN SELECT RAISE(ABORT, 'Missing annual membership'); END"""))


    # A membership cannot be removed or reassigned while the participant has
    # historical orders, votes or favourites for that annual campaign. This
    # closes the reverse direction of the membership guards above.
    if db.engine.dialect.name == "sqlite" and "campaign_participation" in tables:
        linked_tables = []
        for table in ("order", "user_vote", "user_favorite"):
            if table in tables:
                columns = {col["name"] for col in inspector.get_columns(table)}
                if {"campaign_id", "user_id"}.issubset(columns):
                    linked_tables.append(table)
        if linked_tables:
            references = " OR ".join(
                f'EXISTS (SELECT 1 FROM "{table}" r WHERE '
                'r.campaign_id = OLD.campaign_id AND r.user_id = OLD.user_id)'
                for table in linked_tables
            )
            with db.engine.begin() as conn:
                conn.execute(text(f"""CREATE TRIGGER IF NOT EXISTS bom_membership_delete_link_guard
                    BEFORE DELETE ON campaign_participation
                    WHEN {references}
                    BEGIN SELECT RAISE(ABORT, 'Annual membership has linked records'); END"""))
                conn.execute(text(f"""CREATE TRIGGER IF NOT EXISTS bom_membership_move_link_guard
                    BEFORE UPDATE OF campaign_id, user_id ON campaign_participation
                    WHEN (NEW.campaign_id != OLD.campaign_id OR NEW.user_id != OLD.user_id)
                         AND ({references})
                    BEGIN SELECT RAISE(ABORT, 'Annual membership has linked records'); END"""))

    if "product" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("product")}
        if "color_bl" not in columns:
            with db.engine.begin() as conn:
                conn.execute(text("ALTER TABLE product ADD COLUMN color_bl VARCHAR(255)"))
        if "main_group" not in columns:
            with db.engine.begin() as conn:
                conn.execute(text("ALTER TABLE product ADD COLUMN main_group VARCHAR(100)"))
        if "main_group_sub" not in columns:
            with db.engine.begin() as conn:
                conn.execute(text("ALTER TABLE product ADD COLUMN main_group_sub VARCHAR(100)"))
        if "present_in_2025" not in columns:
            with db.engine.begin() as conn:
                conn.execute(text("ALTER TABLE product ADD COLUMN present_in_2025 BOOLEAN DEFAULT 1"))

    if "user_vote" in inspector.get_table_names():
        vote_columns = {col["name"] for col in inspector.get_columns("user_vote")}
        if "initial_quantity" not in vote_columns:
            with db.engine.begin() as conn:
                conn.execute(text("ALTER TABLE user_vote ADD COLUMN initial_quantity INTEGER"))
            with db.engine.begin() as conn:
                conn.execute(text("UPDATE user_vote SET initial_quantity = quantity WHERE initial_quantity IS NULL AND phase = 'first'"))

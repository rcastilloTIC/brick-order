# app/auth/routes.py

import os
import hmac
from datetime import datetime
from uuid import uuid4
from flask import send_file, abort

from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, session
from flask_login import current_user, login_user, login_required, logout_user
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
from urllib.parse import urljoin, urlparse

from app import db, limiter
from app.models import Product, User, UserVote
from app.services.declarations import clear_declaration_issue, get_declaration_issue
from app.services.activity_log import log_user_action
from app.services.campaign_data import active_campaign_id

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit(lambda: current_app.config.get('LOGIN_RATE_LIMIT', '30 per minute'))
def login():
    if current_user.is_authenticated:
        destination = 'main.admin_dashboard' if current_user.is_admin else 'main.user_dashboard'
        return redirect(url_for(destination))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()

        if not user:
            flash('Usuario o contraseña incorrectos', 'danger')
            return redirect(url_for('auth.login'))

        if not user.active:
            flash('Usuario desactivado, contacta con el administrador.', 'warning')
            return redirect(url_for('auth.login'))

        if not check_password_hash(user.password_hash, password):
            flash('Usuario o contraseña incorrectos', 'danger')
            return redirect(url_for('auth.login'))

        remember_me = bool(request.form.get('remember'))
        login_user(user, remember=remember_me)
        log_user_action(user.id, "login", detail="Inicio de sesión correcto.", commit=True)
        flash(f'Bienvenido, {user.username}', 'success')
        return _next_destination_after_login(user)

    return render_template('auth/login.html')


@auth_bp.route('/access', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def site_access():
    required_password = current_app.config.get('SITE_ACCESS_PASSWORD')
    if not required_password:
        return redirect(url_for('auth.login'))
    # Do not show the password gate again to an already authorized session.
    if request.method == 'GET' and session.get('site_access_granted'):
        if current_user.is_authenticated and current_user.is_admin:
            return redirect(url_for('main.campaign_registry'))
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        provided = request.form.get('access_password', '')
        if hmac.compare_digest(provided.encode('utf-8'), required_password.encode('utf-8')):
            session['site_access_granted'] = True
            flash('Acceso concedido.', 'success')
            next_url = request.args.get('next')
            if next_url and _is_safe_redirect(next_url):
                return redirect(next_url)
            return redirect(url_for('auth.login'))
        flash('Contraseña incorrecta.', 'danger')

    return render_template('auth/site_access.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('site_access_granted', None)
    flash('Sesión cerrada correctamente', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        if len(new_password) < 8:
            flash('La nueva contraseña debe tener al menos 8 caracteres.', 'warning')
            return redirect(url_for('auth.change_password'))
        if new_password != confirm_password:
            flash('Las contraseñas no coinciden.', 'warning')
            return redirect(url_for('auth.change_password'))
        current_user.set_password(new_password)
        current_user.must_change_password = False
        log_user_action(current_user.id, "password_change", detail="Cambio desde formulario de contraseña.")
        db.session.commit()
        flash('Contraseña actualizada correctamente.', 'success')
        return _next_destination_after_login(current_user)
    return render_template('auth/change_password.html')


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if current_user.is_admin:
        return redirect(url_for('main.admin_dashboard'))
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        dni = request.form.get('dni', '').strip().upper()
        age = request.form.get('age', type=int)
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if age and age < 14:
            flash('La edad mínima es 14 años.', 'warning')
            return redirect(url_for('auth.profile'))

        if dni and not _validate_spanish_id(dni):
            flash('El DNI/NIE no es válido.', 'danger')
            return redirect(url_for('auth.profile'))

        if new_password:
            if new_password != confirm_password:
                flash('Las contraseñas no coinciden.', 'warning')
                return redirect(url_for('auth.profile'))
            if len(new_password) < 8:
                flash('La nueva contraseña debe tener al menos 8 caracteres.', 'warning')
                return redirect(url_for('auth.profile'))
            current_user.set_password(new_password)
            current_user.must_change_password = False
            log_user_action(current_user.id, "password_change", detail="Cambio desde perfil.")

        current_user.first_name = first_name or current_user.first_name
        current_user.last_name = last_name or current_user.last_name
        current_user.dni = dni or current_user.dni
        current_user.age = age or current_user.age

        db.session.commit()
        flash('Perfil actualizado correctamente.', 'success')
        return redirect(url_for('auth.profile'))

    user_votes, total_order = _collect_profile_votes(current_user.id)
    return render_template('auth/profile.html', user_votes=user_votes, total_order=total_order)


@auth_bp.route('/upload-declaration', methods=['GET', 'POST'])
@login_required
def upload_declaration():
    if current_user.is_admin:
        return redirect(url_for('main.admin_dashboard'))
    if current_user.must_change_password:
        return redirect(url_for('auth.change_password'))
    from app.services.campaign_settings import get_annual_setting
    if not get_annual_setting('commitment_pdf'):
        return render_template('auth/commitment_unavailable.html'), 503
    if request.method == 'POST':
        file = request.files.get('declaration_pdf')
        if not file or not file.filename:
            flash('Debes seleccionar un archivo PDF.', 'warning')
            return redirect(url_for('auth.upload_declaration'))
        if not _allowed_pdf(file.filename):
            flash('Sólo se permite subir archivos PDF.', 'warning')
            return redirect(url_for('auth.upload_declaration'))
        # Validate the actual PDF header, not just the user-controlled filename.
        content = file.stream.read(5)
        file.stream.seek(0)
        if content != b"%PDF-":
            flash('El archivo no es un PDF válido.', 'danger')
            return redirect(url_for('auth.upload_declaration'))
        from app.services.active_campaign import current_membership
        membership = current_membership(current_user.id)
        if membership is None:
            abort(403, description='Not enrolled in this campaign')
        filename = f"signed-{current_user.id}-{uuid4().hex}.pdf"
        upload_folder = current_app.config['DECLARATION_UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
        # Never delete earlier signed PDFs: historic memberships may reference them.
        current_user.declaration_file = filename
        current_user.declaration_validated = False
        from app.services.active_campaign import current_campaign, current_membership
        from app.services.campaign_participation import submit_signed_document
        if current_campaign() is not None:
            membership = current_membership(current_user.id)
            if membership is None:
                abort(403, description='Not enrolled in this campaign')
            submit_signed_document(membership, filename)
        db.session.commit()
        log_user_action(current_user.id, 'document_uploaded', detail='Signed document submitted', commit=True)
        clear_declaration_issue(current_user.id)
        flash('Declaración jurada subida correctamente.', 'success')
        return redirect(url_for('auth.declaration_pending'))
    warning = get_declaration_issue(current_user.id)
    return render_template('auth/upload_declaration.html', declaration_issue=warning)


@auth_bp.route('/declaration-pending')
@login_required
def declaration_pending():
    if current_user.is_admin:
        return redirect(url_for('main.admin_dashboard'))
    from app.services.active_campaign import current_campaign, current_membership
    if current_campaign() is not None:
        membership = current_membership(current_user.id)
        if membership is None:
            abort(403)
        if membership.status == 'approved' and membership.signed_document:
            return redirect(url_for('main.user_dashboard'))
    elif current_user.declaration_validated:
        return redirect(url_for('main.user_dashboard'))
    return render_template('auth/declaration_pending.html')


def _is_safe_redirect(target: str) -> bool:
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in {"http", "https"} and ref_url.netloc == test_url.netloc


def _next_destination_after_login(user: User):
    next_url = request.args.get('next')
    if next_url and _is_safe_redirect(next_url):
        return redirect(next_url)
    if user.is_admin:
        return redirect(url_for('main.admin_dashboard'))
    if user.must_change_password:
        return redirect(url_for('auth.change_password'))
    from app.services.active_campaign import current_campaign, current_membership
    if current_campaign() is not None:
        membership = current_membership(user.id)
        if membership is None:
            return redirect(url_for('auth.declaration_pending'))
        if not membership.signed_document:
            return redirect(url_for('auth.upload_declaration'))
        if membership.status != 'approved':
            return redirect(url_for('auth.declaration_pending'))
    else:
        return redirect(url_for('auth.declaration_pending'))
    return redirect(url_for('main.user_dashboard'))


def _allowed_pdf(filename: str) -> bool:
    return (
        '.' in filename
        and filename.rsplit('.', 1)[1].lower()
        in {ext.lower() for ext in current_app.config.get('ALLOWED_DECLARATION_EXTENSIONS', {'pdf'})}
    )


def _validate_spanish_id(value: str) -> bool:
    letters = "TRWAGMYFPDXBNJZSQVHLCKE"
    value = value.upper().replace("-", "").replace(" ", "")

    if len(value) < 9:
        return False

    if value[0].isalpha() and value[0] in "XYZ":
        mapping = {"X": "0", "Y": "1", "Z": "2"}
        numeric = mapping[value[0]] + value[1:-1]
    elif value[0].isalpha():
        numeric = value[1:-1]
    else:
        numeric = value[:-1]

    if not numeric.isdigit():
        return False

    expected_letter = letters[int(numeric) % 23]
    return value[-1] == expected_letter


def _collect_profile_votes(user_id: int):
    rows = (
        db.session.query(UserVote, Product)
        .join(Product, Product.id == UserVote.product_id)
        .filter(UserVote.user_id == user_id)
        .filter(UserVote.campaign_id == active_campaign_id())
        .filter(Product.campaign_id == active_campaign_id())
        .all()
    )
    votes = {}
    total = 0.0
    for vote, product in rows:
        price = float((product.price if product else 0) or 0)
        votes[vote.product_id] = {
            "vote": vote,
            "price": price,
            "name": product.name if product else "",
            "reference": product.reference if product else vote.product_id,
        }
        total += price * vote.quantity
    return votes, total


@auth_bp.route('/commitment/download', methods=['GET'])
@login_required
def download_commitment():
    """Download the blank commitment assigned to the current campaign."""
    from app.services.campaign_settings import get_annual_setting
    name = get_annual_setting('commitment_pdf')
    if not name:
        abort(404)
    folder = current_app.config['DECLARATION_UPLOAD_FOLDER']
    return send_file(os.path.join(folder, os.path.basename(name)), as_attachment=True,
                     download_name='compromiso.pdf', mimetype='application/pdf')

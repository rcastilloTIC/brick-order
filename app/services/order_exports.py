"""Utilities to build the final order context and export files."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime
from app.time_utils import utc_now
from decimal import Decimal
import base64
import zipfile

from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests
from fpdf import FPDF
from flask import current_app
from openpyxl import Workbook
from sqlalchemy import func

from app import db
from app.models import Config, Order, Product, User, UserVote
from app.services.campaign_data import active_campaign_id, products_query
from app.services.campaign_phase import get_campaign_phase
from app.services.order_materialization import assert_selected_commitments_materialized


def build_final_order_context() -> Dict[str, object]:
    """
    Aggregate selected references from votes before ordering, orders afterwards.

    Returns a dictionary with per-product summaries, per-user breakdowns,
    and the total amount contributed by the promoted items.
    """
    promoted_products = (
        products_query().filter(Product.final_selected.is_(True))
        .filter(Product.final_disabled.is_(False))
        .all()
    )
    product_map = {product.id: product for product in promoted_products}
    if not product_map:
        return {
            "products": [],
            "participants": {},
            "base_total": 0.0,
            "product_count": 0,
            "participant_count": 0,
        }

    # Voting history remains authoritative before orders are opened. Once
    # materialized, Order rows are authoritative and include later increases.
    # Never add the two sources: that would double count the vote floor.
    phase = get_campaign_phase() or "first"
    use_orders = phase in {"order"}
    quantity_model = Order if use_orders else UserVote
    quantity_rows = (
        db.session.query(
            quantity_model.product_id.label("product_id"),
            User.id.label("user_id"),
            User.username.label("username"),
            User.first_name.label("first_name"),
            User.last_name.label("last_name"),
            func.sum(quantity_model.quantity).label("quantity"),
        )
        .join(User, User.id == quantity_model.user_id)
        .filter(quantity_model.product_id.in_(product_map.keys()))
        .filter(quantity_model.campaign_id == active_campaign_id())
        .group_by(
            quantity_model.product_id, User.id, User.username,
            User.first_name, User.last_name,
        )
        .having(func.sum(quantity_model.quantity) > 0)
        .all()
    )

    product_voters: Dict[int, List[Dict[str, object]]] = {
        product_id: [] for product_id in product_map
    }
    participants: Dict[int, Dict[str, object]] = {}
    base_total = 0.0

    for row in quantity_rows:
        product = product_map[row.product_id]
        quantity = int(row.quantity or 0)
        if quantity <= 0:
            continue
        unit_price = float(product.price or 0.0)
        amount = quantity * unit_price
        base_total += amount
        display_name = _build_display_name(row.first_name, row.last_name, row.username)
        voter_entry = {
            "user_id": row.user_id,
            "username": row.username,
            "display_name": display_name,
            "quantity": quantity,
            "amount": amount,
        }
        product_voters[row.product_id].append(voter_entry)

        participant = participants.setdefault(
            row.user_id,
            {
                "user_id": row.user_id,
                "username": row.username,
                "display_name": display_name,
                "lines": [],
                "subtotal": 0.0,
                "total_quantity": 0,
            },
        )
        participant["lines"].append(
            {
                "product": product,
                "quantity": quantity,
                "amount": amount,
            }
        )
        participant["subtotal"] += amount
        participant["total_quantity"] += quantity

    product_summaries: List[Dict[str, object]] = []
    for product_id, voters in product_voters.items():
        total_quantity = sum(voter["quantity"] for voter in voters)
        if total_quantity <= 0:
            continue
        product = product_map[product_id]
        total_amount = sum(voter["amount"] for voter in voters)
        product_summaries.append(
            {
                "product": product,
                "total_quantity": total_quantity,
                "total_amount": total_amount,
                "voters": sorted(voters, key=lambda entry: entry["display_name"]),
            }
        )

    product_summaries.sort(key=lambda entry: entry["product"].reference or "")
    for participant in participants.values():
        participant["lines"].sort(
            key=lambda entry: entry["product"].reference or ""
        )

    return {
        "products": product_summaries,
        "participants": participants,
        "base_total": base_total,
        "product_count": len(product_summaries),
        "participant_count": len(participants),
    }


def _summary_fingerprint(summary):
    """Canonical quantities in the export, independent of display ordering.

    Product and participant identifiers are checked separately: identical totals
    distributed to different participants must not pass the comparison.
    """
    products = {}
    participants = {}
    for row in summary["products"]:
        pid = int(row["product"].id)
        if pid in products:
            raise ValueError("Referencia duplicada en el resumen del pedido")
        products[pid] = (int(row["total_quantity"]), Decimal(str(row["product"].price or 0)), row["product"].reference)
    for user_id, user in summary["participants"].items():
        for line in user["lines"]:
            key = (int(user_id), int(line["product"].id))
            if key in participants:
                raise ValueError("Linea duplicada en el resumen del pedido")
            participants[key] = int(line["quantity"])
    if any(fields[0] <= 0 or not fields[1].is_finite() or fields[1] < 0 for fields in products.values()) or any(quantity <= 0 for quantity in participants.values()):
        raise ValueError("Cantidad no valida en el resumen del pedido")
    totals = {}
    for (_user_id, pid), quantity in participants.items():
        totals[pid] = totals.get(pid, 0) + quantity
    if totals != {pid: fields[0] for pid, fields in products.items()}:
        raise ValueError("El resumen por participante no coincide con los totales por referencia")
    return products, participants


def assert_current_export_summary(summary, current):
    """Reject a stale or forged export summary before writing any files."""
    if _summary_fingerprint(summary) != _summary_fingerprint(current):
        raise ValueError("El pedido ha cambiado. Actualice el resumen antes de exportar.")


def generate_order_files(
    summary: Dict[str, object],
    tax_amount: float,
    shipping_amount: float,
    payment_iban: str | None = None,
    payment_due_date: str | None = None,
) -> Dict[str, str]:
    """
    Persist the Excel and PDF exports for the final order.

    Returns the filenames (relative to the export folder) for later download.
    """
    # Final exports must never omit selected voting commitments.
    if (get_campaign_phase() or "first") in {"order"}:
        assert_selected_commitments_materialized()
    # The caller can hold an outdated in-memory summary. Re-read the active
    # campaign after the commitment floor check, before creating any files.
    assert_current_export_summary(summary, build_final_order_context())
    if not summary["products"]:
        raise ValueError("No hay referencias promovidas con votos para generar el pedido.")

    folder = current_app.config["ORDER_EXPORT_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    timestamp = utc_now().strftime("%Y%m%d_%H%M%S")

    excel_name = f"pedido_total_{timestamp}.xlsx"
    piece_pdf_name = f"pedido_por_pieza_imprimir_{timestamp}.pdf"
    user_pdf_name = f"pedido_por_usuario_imprimir_{timestamp}.pdf"
    piece_zip_name = f"pedido_por_pieza_{timestamp}.zip"
    user_zip_name = f"pedido_por_usuario_{timestamp}.zip"

    _write_excel(os.path.join(folder, excel_name), summary)
    _write_piece_pdf(os.path.join(folder, piece_pdf_name), summary)
    _write_user_pdf(
        os.path.join(folder, user_pdf_name),
        summary,
        tax_amount,
        shipping_amount,
        payment_iban,
        payment_due_date,
    )
    _write_piece_zip(
        os.path.join(folder, piece_zip_name),
        piece_pdf_name,
        summary,
    )
    _write_user_zip(
        os.path.join(folder, user_zip_name),
        user_pdf_name,
        summary,
        tax_amount,
        shipping_amount,
        payment_iban,
        payment_due_date,
    )

    return {
        "excel": excel_name,
        "piece_pdf": piece_zip_name,
        "user_pdf": user_zip_name,
    }


def _write_excel(path: str, summary: Dict[str, object]) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Pedido"
    worksheet.append(
        [
            "Referencia",
            "Nombre",
            "Color",
            "Precio unitario",
            "Cantidad total",
            "Importe total",
        ]
    )

    for entry in summary["products"]:
        product: Product = entry["product"]
        worksheet.append(
            [
                product.reference,
                product.name,
                product.colour_id,
                float(product.price or 0.0),
                entry["total_quantity"],
                entry["total_amount"],
            ]
        )

    worksheet.append(["", "", "", "", "Total", summary["base_total"]])
    workbook.save(path)


def _write_piece_pdf(path: str, summary: Dict[str, object]) -> None:
    pdf = _base_pdf(title="Pedido por referencia")
    temp_files: List[str] = []
    image_cache: Dict[int, Optional[str]] = {}
    try:
        for entry in summary["products"]:
            _append_piece_entry(pdf, entry, temp_files, image_cache)
    finally:
        for file_path in temp_files:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)

    pdf.output(path)


def _write_user_pdf(
    path: str,
    summary: Dict[str, object],
    tax_amount: float,
    shipping_amount: float,
    payment_iban: str | None = None,
    payment_due_date: str | None = None,
) -> None:
    pdf = _base_pdf(title="Pedido por usuario")
    extras_total = tax_amount + shipping_amount
    base_total = float(summary.get("base_total", 0.0) or 0.0)

    temp_files: List[str] = []
    image_cache: Dict[int, Optional[str]] = {}
    try:
        for participant in sorted(
            summary["participants"].values(), key=lambda entry: entry["display_name"]
        ):
            _append_user_document(
                pdf,
                participant,
                temp_files,
                image_cache,
                extras_total,
                base_total,
                payment_iban,
                payment_due_date,
            )
    finally:
        for file_path in temp_files:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)

    pdf.output(path)


def _write_piece_zip(path: str, combined_pdf_name: str, summary: Dict[str, object]) -> None:
    temp_files: List[str] = []
    image_cache: Dict[int, Optional[str]] = {}
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            combined_pdf_path = os.path.join(current_app.config["ORDER_EXPORT_FOLDER"], combined_pdf_name)
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(combined_pdf_path, arcname=combined_pdf_name)
                used_piece_names = {combined_pdf_name}
                for entry in summary["products"]:
                    product: Product = entry["product"]
                    filename = _unique_arcname(
                        f"{_safe_filename_part(product.reference or 'sin_referencia')}_{_safe_filename_part(product.name or 'pieza')}.pdf",
                        used_piece_names, product.id)
                    item_path = os.path.join(temp_dir, filename)
                    _write_single_piece_pdf(item_path, entry, temp_files, image_cache)
                    archive.write(item_path, arcname=filename)
    finally:
        for file_path in temp_files:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)


def _write_user_zip(
    path: str,
    combined_pdf_name: str,
    summary: Dict[str, object],
    tax_amount: float,
    shipping_amount: float,
    payment_iban: str | None,
    payment_due_date: str | None,
) -> None:
    temp_files: List[str] = []
    image_cache: Dict[int, Optional[str]] = {}
    extras_total = tax_amount + shipping_amount
    base_total = float(summary.get("base_total", 0.0) or 0.0)
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            combined_pdf_path = os.path.join(current_app.config["ORDER_EXPORT_FOLDER"], combined_pdf_name)
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(combined_pdf_path, arcname=combined_pdf_name)
                used_names = {combined_pdf_name}
                for participant in sorted(
                    summary["participants"].values(), key=lambda entry: entry["display_name"]
                ):
                    filename = participant_pdf_name(participant["user_id"], participant["username"])
                    if filename in used_names:
                        raise ValueError(f"PDF de participante duplicado: {filename}")
                    used_names.add(filename)
                    user_path = os.path.join(temp_dir, filename)
                    _write_single_user_pdf(
                        user_path,
                        participant,
                        extras_total,
                        base_total,
                        payment_iban,
                        payment_due_date,
                        temp_files,
                        image_cache,
                    )
                    archive.write(user_path, arcname=filename)
    finally:
        for file_path in temp_files:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)


def _write_single_piece_pdf(
    path: str,
    entry: Dict[str, object],
    temp_files: List[str],
    image_cache: Dict[int, Optional[str]],
) -> None:
    pdf = _base_pdf(title="Pedido por referencia")
    _append_piece_entry(pdf, entry, temp_files, image_cache)
    pdf.output(path)


def _write_single_user_pdf(
    path: str,
    participant: Dict[str, object],
    extras_total: float,
    base_total: float,
    payment_iban: str | None,
    payment_due_date: str | None,
    temp_files: List[str],
    image_cache: Dict[int, Optional[str]],
) -> None:
    pdf = _base_pdf(title=f"Pedido {participant['username']}")
    _append_user_document(
        pdf,
        participant,
        temp_files,
        image_cache,
        extras_total,
        base_total,
        payment_iban,
        payment_due_date,
    )
    pdf.output(path)


def _append_piece_entry(
    pdf: FPDF,
    entry: Dict[str, object],
    temp_files: List[str],
    image_cache: Dict[int, Optional[str]],
) -> None:
    product: Product = entry["product"]
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    header = f"{product.reference or 's/n'} - {product.name or ''}"
    _write_line(pdf, header, line_height=8)

    img_path = _resolve_product_image(product, temp_files, image_cache)
    if img_path:
        current_y = pdf.get_y() + 2
        pdf.image(img_path, x=pdf.l_margin, y=current_y, w=60)
        pdf.set_y(current_y + 65)
    else:
        pdf.ln(4)

    pdf.set_font("Helvetica", "", 11)
    _write_line(
        pdf,
        f"Color: {product.colour_id or '-'}    Precio: {float(product.price or 0.0):.2f} EUR",
    )
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    _write_line(pdf, "Participantes:")
    pdf.set_font("Helvetica", "", 11)
    for voter in entry["voters"]:
        line = f"- {voter['display_name']} ({voter['username']}): {voter['quantity']} uds"
        _write_line(pdf, line)
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    _write_line(
        pdf,
        f"Total referencia: {entry['total_quantity']} uds | {entry['total_amount']:.2f} EUR",
    )


def _append_user_document(
    pdf: FPDF,
    participant: Dict[str, object],
    temp_files: List[str],
    image_cache: Dict[int, Optional[str]],
    extras_total: float,
    base_total: float,
    payment_iban: str | None,
    payment_due_date: str | None,
) -> None:
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    _write_line(
        pdf,
        f"Usuario: {participant['display_name']} ({participant['username']})",
        line_height=8,
    )
    pdf.set_font("Helvetica", "", 11)
    pdf.ln(2)
    if payment_iban and payment_due_date:
        _write_line(
            pdf,
            "Realiza una transferencia a la cuenta de Valbrick indicada abajo, "
            "indicando como concepto DONATIVO. La fecha limite de pago es la indicada.",
        )
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 11)
        _write_line(pdf, f"IBAN: {payment_iban}")
        _write_line(pdf, f"Fecha limite: {_format_due_date(payment_due_date)}")
        pdf.set_font("Helvetica", "", 11)
        pdf.ln(3)

    _write_line(pdf, "Detalle del pedido final:")
    pdf.ln(2)
    for item in participant["lines"]:
        product: Product = item["product"]
        price = float(product.price or 0.0)
        line = (
            f"{product.reference or 's/n'} - {product.name or ''} | "
            f"{item['quantity']} uds | {price:.2f} EUR | {item['amount']:.2f} EUR"
        )
        img_path = _resolve_product_image(product, temp_files, image_cache)
        if img_path:
            row_height = 22
            if pdf.get_y() + row_height > pdf.page_break_trigger:
                pdf.add_page()
            row_top = pdf.get_y()
            pdf.image(img_path, x=pdf.l_margin, y=row_top, w=20, h=20)
            text_x = pdf.l_margin + 24
            text_width = pdf.w - pdf.r_margin - text_x
            text_line = _truncate_text(pdf, line, text_width)
            pdf.set_xy(text_x, row_top)
            pdf.cell(text_width, 6, text_line)
            pdf.set_y(row_top + row_height)
        else:
            _write_line(pdf, _truncate_text(pdf, line, pdf.w - pdf.l_margin - pdf.r_margin))
            pdf.ln(2)
    subtotal = float(participant["subtotal"] or 0.0)
    proportional_extra = extras_total * (subtotal / base_total) if base_total > 0 else 0.0
    _write_line(pdf, f"Subtotal usuario: {subtotal:.2f} EUR")
    _write_line(pdf, f"Impuestos + transporte: {proportional_extra:.2f} EUR")
    pdf.set_font("Helvetica", "B", 12)
    _write_line(pdf, f"Total a pagar: {(subtotal + proportional_extra):.2f} EUR", line_height=7)
    pdf.set_font("Helvetica", "", 11)


def _base_pdf(title: str) -> FPDF:
    pdf = FPDF()
    pdf.set_title(title)
    pdf.set_author("Sistema brick order manager")
    pdf.set_auto_page_break(auto=True, margin=15)
    return pdf


def _download_image(url: Optional[str], temp_files: List[str]) -> Optional[str]:
    if not url:
        return None
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
    except Exception:
        return None

    parsed = urlparse(url)
    _, ext = os.path.splitext(parsed.path)
    suffix = ext if ext in {".png", ".jpg", ".jpeg"} else ".jpg"
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp.write(response.content)
    temp.flush()
    temp.close()
    temp_files.append(temp.name)
    return temp.name


def _build_display_name(
    first_name: Optional[str],
    last_name: Optional[str],
    fallback: str,
) -> str:
    parts = [part for part in [first_name, last_name] if part]
    return " ".join(parts).strip() or fallback


def _write_line(pdf: FPDF, text: str, line_height: float = 6) -> None:
    """
    Helper to ensure we always start from the left margin before writing.

    Avoids layout errors when the cursor is positioned near the right edge.
    """
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, line_height, text or "")


def _truncate_text(pdf: FPDF, text: str, max_width: float) -> str:
    if not text:
        return ""
    if pdf.get_string_width(text) <= max_width:
        return text
    ellipsis = "..."
    available = max_width - pdf.get_string_width(ellipsis)
    if available <= 0:
        return ellipsis
    trimmed = text
    while trimmed and pdf.get_string_width(trimmed) > available:
        trimmed = trimmed[:-1]
    return f"{trimmed}{ellipsis}"


PARTICIPANT_PDF_PREFIX = "usuario_"


def participant_pdf_name(user_id: int, username: str | None) -> str:
    """Entry name of one participant's PDF inside the per-user ZIP.

    The numeric id makes the name unique: sanitised usernames can collide
    ("ana.garcia" and "ana_garcia"), which previously let one participant
    download another participant's order.  The username is only a readable
    suffix for administrators and is never used for lookup.
    """
    return f"{PARTICIPANT_PDF_PREFIX}{int(user_id)}_{_safe_filename_part(username or '')}.pdf"


def find_participant_pdf(names: List[str], user_id: int) -> Optional[str]:
    """Return the single ZIP entry for this user id, or None (fail closed)."""
    prefix = f"{PARTICIPANT_PDF_PREFIX}{int(user_id)}_"
    matches = [n for n in names
               if n.startswith(prefix) and n.lower().endswith(".pdf") and "/" not in n and "\\" not in n]
    return matches[0] if len(matches) == 1 else None


def _unique_arcname(filename: str, used: set, discriminator: object) -> str:
    """Never write two ZIP entries with the same name (readers return only one)."""
    if filename not in used:
        used.add(filename)
        return filename
    stem, dot, ext = filename.rpartition(".")
    candidate = f"{stem}_{discriminator}.{ext}" if dot else f"{filename}_{discriminator}"
    if candidate in used:
        raise ValueError(f"Nombre duplicado en el ZIP de exportación: {filename}")
    used.add(candidate)
    return candidate


def _safe_filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())
    return cleaned.strip("_") or "archivo"


def _format_due_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y")
    except ValueError:
        return value


def _truncate_text(pdf: FPDF, text: str, max_width: float) -> str:
    if not text:
        return ""
    if pdf.get_string_width(text) <= max_width:
        return text
    ellipsis = "..."
    available = max_width - pdf.get_string_width(ellipsis)
    if available <= 0:
        return ellipsis
    trimmed = text
    while trimmed and pdf.get_string_width(trimmed) > available:
        trimmed = trimmed[:-1]
    return f"{trimmed}{ellipsis}"


# Always keep this fallback PNG decodable by Pillow / fpdf2.
# Some LEGO references have no image, so export generation must not fail.
PLACEHOLDER_IMAGE_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAIAAADYYG7QAAABN0lEQVR4nO3ZMQvCMBAF4FT8P25O"
    "glOn/l4nJ8HJzR8jgpODUqU1uXfvHSRI3ySUtF9rmgvX7nZ/pJayTikdjqfajHeGfr+qbZhmPf4a"
    "+n1Fx/gvNfeEFpCVOqDz5Zo7VAIVhil5nTZ38iyoPEzUpJR2240PNA4INJmaEijchGgMUKAJ1Nig"
    "EBOugUCiyaVBQbTJq3GACBOh8YFcJk7jBoEmWsOATJOiIUEFk6jhQT9NukYCTUwhGhU0v7yoSX+4"
    "Y8xNajoS6HveRO0LeNB8FoeYSFDundJNDKj8hosmNwhZbxSTD4SvfrTJAfKuxZwJBXGVgTBBIKVO"
    "eU02SK+aLpMBiqrhuAlqNug1HDcZzYYoDW4ymg2BGtAENRtiU77VOhs0sh1TJQvIyqeT38gXj+ae"
    "UNfa56knSoTIYo5WC7QAAAAASUVORK5CYII="
)


def _resolve_product_image(
    product: Product, temp_files: List[str], cache: Dict[int, Optional[str]]
) -> Optional[str]:
    if product.id in cache:
        return cache[product.id]

    path = _download_image(product.image_url, temp_files)
    if not path:
        path = _create_placeholder_image(temp_files)

    cache[product.id] = path
    return path


def _create_placeholder_image(temp_files: List[str]) -> str:
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    temp.write(PLACEHOLDER_IMAGE_BYTES)
    temp.flush()
    temp.close()
    temp_files.append(temp.name)
    return temp.name

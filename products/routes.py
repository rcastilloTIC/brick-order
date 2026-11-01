# products/routes.py

from flask import Blueprint, render_template
from flask_login import login_required

from app.models import Product
from app.services.campaign_data import products_query

products_bp = Blueprint("products", __name__, template_folder="templates/products")


@products_bp.route("/", methods=["GET"])
@login_required
def list_products():
    products = products_query().order_by(Product.id.asc()).all()
    return render_template("products/list.html", products=products)


@products_bp.route("/<int:product_id>", methods=["GET"])
@login_required
def product_detail(product_id):
    product = products_query().filter_by(id=product_id).first_or_404(product_id)
    return render_template("products/detail.html", product=product)

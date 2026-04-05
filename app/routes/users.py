import csv
import datetime
import io

from flask import Blueprint, jsonify, request
from peewee import IntegrityError
from playhouse.shortcuts import model_to_dict

from app.database import db
from app.models.event import Event
from app.models.url import URL
from app.models.user import User
from app.utils.validators import validate_email

users_bp = Blueprint("users", __name__)


@users_bp.route("/users/bulk", methods=["POST"])
def bulk_create_users():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    stream = io.StringIO(file.stream.read().decode("utf-8"))
    reader = csv.DictReader(stream)

    count = 0
    for row in reader:
        try:
            with db.atomic():
                User.create(
                    username=row.get("username", "").strip(),
                    email=row.get("email", "").strip(),
                    created_at=row.get("created_at", datetime.datetime.utcnow()),
                )
                count += 1
        except IntegrityError:
            continue

    return jsonify({"imported": count, "count": count}), 201


@users_bp.route("/users", methods=["GET"])
def list_users():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    per_page = min(per_page, 100)
    users = User.select().order_by(User.id).paginate(page, per_page)
    return jsonify([model_to_dict(u) for u in users])


@users_bp.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    try:
        user = User.get_by_id(user_id)
    except User.DoesNotExist:
        return jsonify({"error": "User not found"}), 404
    return jsonify(model_to_dict(user))


@users_bp.route("/users", methods=["POST"])
def create_user():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    username = data.get("username", "")
    if isinstance(username, str):
        username = username.strip()
    if not username or not isinstance(username, str):
        return jsonify({"error": "username is required"}), 400
    if len(username) > 255:
        return jsonify({"error": "username must be 255 characters or fewer"}), 400

    email = data.get("email", "")
    if isinstance(email, str):
        email = email.strip()
    if not email or not isinstance(email, str):
        return jsonify({"error": "email is required"}), 400
    if len(email) > 255:
        return jsonify({"error": "email must be 255 characters or fewer"}), 400

    if not validate_email(email):
        return jsonify({"error": "Invalid email format"}), 400

    try:
        user = User.create(
            username=username,
            email=email,
            created_at=datetime.datetime.utcnow(),
        )
    except IntegrityError as e:
        error_msg = str(e).lower()
        if "username" in error_msg:
            return jsonify({"error": "Username already exists"}), 409
        if "email" in error_msg:
            return jsonify({"error": "Email already exists"}), 409
        return jsonify({"error": "User already exists"}), 409

    return jsonify(model_to_dict(user)), 201


@users_bp.route("/users/<int:user_id>", methods=["PUT"])
def update_user(user_id):
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    try:
        user = User.get_by_id(user_id)
    except User.DoesNotExist:
        return jsonify({"error": "User not found"}), 404

    if "username" in data:
        username = data["username"]
        if not username or not isinstance(username, str) or not username.strip():
            return jsonify({"error": "username cannot be empty"}), 400
        if len(username.strip()) > 255:
            return jsonify({"error": "username must be 255 characters or fewer"}), 400
        user.username = username.strip()

    if "email" in data:
        email = data["email"]
        if not email or not isinstance(email, str) or not email.strip():
            return jsonify({"error": "email cannot be empty"}), 400
        if len(email.strip()) > 255:
            return jsonify({"error": "email must be 255 characters or fewer"}), 400
        if not validate_email(email.strip()):
            return jsonify({"error": "Invalid email format"}), 400
        user.email = email.strip()

    try:
        user.save()
    except IntegrityError:
        return jsonify({"error": "Username or email already exists"}), 409

    return jsonify(model_to_dict(user))


@users_bp.route("/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    try:
        user = User.get_by_id(user_id)
    except User.DoesNotExist:
        return jsonify({"error": "User not found"}), 404

    with db.atomic():
        # Nullify foreign keys referencing this user before deleting
        Event.update(user_id=None).where(Event.user_id == user_id).execute()
        URL.update(user_id=None).where(URL.user_id == user_id).execute()
        user.delete_instance()

    return "", 204

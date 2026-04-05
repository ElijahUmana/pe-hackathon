import datetime
import json

from flask import Blueprint, jsonify, request
from playhouse.shortcuts import model_to_dict

from app.models.event import Event
from app.models.url import URL
from app.models.user import User

events_bp = Blueprint("events", __name__)


def _serialize_event(event):
    """Serialize an event, parsing the details JSON string into a dict."""
    d = model_to_dict(event, backrefs=False, recurse=False)
    if isinstance(d.get("details"), str):
        try:
            d["details"] = json.loads(d["details"])
        except (json.JSONDecodeError, TypeError):
            pass
    return d


@events_bp.route("/events", methods=["GET"])
def list_events():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    per_page = min(per_page, 100)

    query = Event.select().order_by(Event.id.desc())

    # Filter by event_type (accept both "type" and "event_type" param names)
    event_type = request.args.get("event_type") or request.args.get("type")
    if event_type:
        query = query.where(Event.event_type == event_type)

    # Filter by url_id
    url_id_filter = request.args.get("url_id", type=int)
    if url_id_filter is not None:
        query = query.where(Event.url_id == url_id_filter)

    # Filter by user_id
    user_id_filter = request.args.get("user_id", type=int)
    if user_id_filter is not None:
        query = query.where(Event.user_id == user_id_filter)

    events = query.paginate(page, per_page)
    return jsonify([_serialize_event(e) for e in events])


@events_bp.route("/events", methods=["POST"])
def create_event():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    url_id = data.get("url_id")
    if url_id is None:
        return jsonify({"error": "url_id is required"}), 400
    try:
        url_id = int(url_id)
        URL.get_by_id(url_id)
    except (TypeError, ValueError):
        return jsonify({"error": "url_id must be an integer"}), 400
    except URL.DoesNotExist:
        return jsonify({"error": "URL not found"}), 404

    event_type = data.get("event_type")
    if not event_type or not isinstance(event_type, str):
        return jsonify({"error": "event_type is required"}), 400

    user_id = data.get("user_id")
    if user_id is not None:
        try:
            user_id = int(user_id)
            User.get_by_id(user_id)
        except (TypeError, ValueError):
            return jsonify({"error": "user_id must be an integer"}), 400
        except User.DoesNotExist:
            return jsonify({"error": "User not found"}), 404

    details = data.get("details")
    if details is not None and not isinstance(details, dict):
        return jsonify({"error": "details must be a JSON object"}), 400
    details_str = json.dumps(details) if details is not None else None

    event = Event.create(
        url_id=url_id,
        user_id=user_id,
        event_type=event_type,
        timestamp=datetime.datetime.utcnow(),
        details=details_str,
    )

    return jsonify(_serialize_event(event)), 201


@events_bp.route("/urls/<int:url_id>/events", methods=["GET"])
def url_events(url_id):
    try:
        URL.get_by_id(url_id)
    except URL.DoesNotExist:
        return jsonify({"error": "URL not found"}), 404

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    per_page = min(per_page, 100)

    events = (
        Event.select()
        .where(Event.url_id == url_id)
        .order_by(Event.id.desc())
        .paginate(page, per_page)
    )
    return jsonify([_serialize_event(e) for e in events])

from flask import Blueprint, jsonify, request
from playhouse.shortcuts import model_to_dict

from app.models.event import Event
from app.models.url import URL

events_bp = Blueprint("events", __name__)


@events_bp.route("/events", methods=["GET"])
def list_events():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    per_page = min(per_page, 100)

    query = Event.select().order_by(Event.id.desc())

    event_type = request.args.get("type")
    if event_type:
        query = query.where(Event.event_type == event_type)

    events = query.paginate(page, per_page)
    return jsonify([model_to_dict(e, backrefs=False) for e in events])


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
    return jsonify([model_to_dict(e, backrefs=False) for e in events])

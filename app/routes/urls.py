import datetime
import json
import logging

from flask import Blueprint, jsonify, redirect, request
from peewee import IntegrityError
from playhouse.shortcuts import model_to_dict

from app.cache import CACHE_TTL
from app.metrics import CACHE_HITS, CACHE_MISSES, REDIRECTS_TOTAL, URLS_CREATED
from app.models.event import Event
from app.models.url import URL
from app.models.user import User
from app.utils.short_code import generate_short_code
from app.utils.validators import is_valid_url

logger = logging.getLogger(__name__)

urls_bp = Blueprint("urls", __name__)


def _get_redis():
    """Get Redis client if available, None otherwise."""
    try:
        from app.cache import get_redis
        return get_redis()
    except Exception:
        return None


@urls_bp.route("/urls", methods=["GET"])
def list_urls():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    per_page = min(per_page, 100)

    query = URL.select().order_by(URL.id)

    user_id_raw = request.args.get("user_id")
    if user_id_raw is not None:
        try:
            user_id_filter = int(user_id_raw)
        except (ValueError, TypeError):
            return jsonify({"error": "user_id must be an integer"}), 400
        query = query.where(URL.user_id == user_id_filter)

    is_active_filter = request.args.get("is_active")
    if is_active_filter is not None:
        active = is_active_filter.lower() in ("true", "1", "yes")
        query = query.where(URL.is_active == active)

    urls = query.paginate(page, per_page)
    return jsonify([model_to_dict(u, backrefs=False, recurse=False) for u in urls])


@urls_bp.route("/urls/<int:url_id>", methods=["GET"])
def get_url(url_id):
    try:
        url = URL.get_by_id(url_id)
    except URL.DoesNotExist:
        return jsonify({"error": "URL not found"}), 404
    return jsonify(model_to_dict(url, backrefs=False, recurse=False))


@urls_bp.route("/urls", methods=["POST"])
def create_url():
    # Oracle Hint 6 (Fractured Vessel): reject non-JSON
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    # Oracle Hint 3 (Unwitting Stranger): require url field
    # Accept both "original_url" and "url" field names for compatibility
    url_value = data.get("original_url") or data.get("url", "")
    if isinstance(url_value, str):
        url_value = url_value.strip()
    if not url_value or not isinstance(url_value, str):
        return jsonify({"error": "url is required"}), 400

    # Oracle Hint 5 (Deceitful Scroll): validate URL format
    if not is_valid_url(url_value):
        return jsonify({"error": "A valid HTTP or HTTPS URL is required"}), 400

    # Oracle Hint 3: validate user_id if provided
    user_id = data.get("user_id")
    user = None
    if user_id is not None:
        if isinstance(user_id, bool) or not isinstance(user_id, (int, float)):
            return jsonify({"error": "user_id must be an integer"}), 400
        if isinstance(user_id, float) and user_id != int(user_id):
            return jsonify({"error": "user_id must be an integer"}), 400
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return jsonify({"error": "user_id must be an integer"}), 400
        if user_id < 1:
            return jsonify({"error": "user_id must be a positive integer"}), 400
        try:
            user = User.get_by_id(user_id)
        except User.DoesNotExist:
            return jsonify({"error": "User not found"}), 404

    title = data.get("title", "")
    if isinstance(title, str):
        title = title.strip() or None
    else:
        title = None
    if title and len(title) > 255:
        return jsonify({"error": "title must be 255 characters or fewer"}), 400

    # Oracle Hint 1 (Twin's Paradox): random unique short code
    max_retries = 10
    for _ in range(max_retries):
        short_code = generate_short_code()
        try:
            url_obj = URL.create(
                user_id=user.id if user else user_id,
                short_code=short_code,
                original_url=url_value,
                title=title,
                is_active=True,
                created_at=datetime.datetime.utcnow(),
                updated_at=datetime.datetime.utcnow(),
            )
            break
        except IntegrityError:
            continue
    else:
        return jsonify({"error": "Failed to generate unique short code"}), 500

    # Create "created" event (Oracle Hint 2)
    Event.create(
        url_id=url_obj.id,
        user_id=user.id if user else user_id,
        event_type="created",
        timestamp=url_obj.created_at,
        details=json.dumps({
            "short_code": url_obj.short_code,
            "original_url": url_obj.original_url,
        }),
    )

    URLS_CREATED.inc()

    logger.info(
        "URL created",
        extra={"short_code": short_code, "url_id": url_obj.id},
    )

    return jsonify(model_to_dict(url_obj, backrefs=False, recurse=False)), 201


@urls_bp.route("/urls/<int:url_id>", methods=["PUT"])
def update_url(url_id):
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    try:
        url_obj = URL.get_by_id(url_id)
    except URL.DoesNotExist:
        return jsonify({"error": "URL not found"}), 404

    changes = []

    if "original_url" in data or "url" in data:
        new_url = data.get("original_url") or data.get("url")
        if not isinstance(new_url, str) or not is_valid_url(new_url.strip()):
            return jsonify({"error": "A valid HTTP or HTTPS URL is required"}), 400
        url_obj.original_url = new_url.strip()
        changes.append(("original_url", new_url.strip()))

    if "title" in data:
        new_title = data["title"]
        if isinstance(new_title, str) and len(new_title.strip()) > 255:
            return jsonify({"error": "title must be 255 characters or fewer"}), 400
        url_obj.title = new_title if new_title else None
        changes.append(("title", new_title))

    if "is_active" in data:
        if not isinstance(data["is_active"], bool):
            return jsonify({"error": "is_active must be a boolean"}), 400
        url_obj.is_active = data["is_active"]
        changes.append(("is_active", str(data["is_active"])))

    url_obj.save()

    # Log update events
    for field, new_value in changes:
        Event.create(
            url_id=url_obj.id,
            user_id=url_obj.user_id,
            event_type="updated",
            timestamp=datetime.datetime.utcnow(),
            details=json.dumps({"field": field, "new_value": str(new_value)}),
        )

    # Invalidate cache
    redis = _get_redis()
    if redis:
        try:
            redis.delete(f"url:{url_obj.short_code}")
        except Exception:
            pass

    return jsonify(model_to_dict(url_obj, backrefs=False, recurse=False))


@urls_bp.route("/urls/<int:url_id>", methods=["DELETE"])
def delete_url(url_id):
    try:
        url_obj = URL.get_by_id(url_id)
    except URL.DoesNotExist:
        return jsonify({"error": "URL not found"}), 404

    if not url_obj.is_active:
        return jsonify({"error": "URL not found"}), 404

    # Soft delete (Oracle Hint 4: Slumbering Guide)
    url_obj.is_active = False
    url_obj.save()

    Event.create(
        url_id=url_obj.id,
        user_id=url_obj.user_id,
        event_type="deleted",
        timestamp=datetime.datetime.utcnow(),
        details=json.dumps({"reason": "user_requested"}),
    )

    # Invalidate cache
    redis = _get_redis()
    if redis:
        try:
            redis.delete(f"url:{url_obj.short_code}")
        except Exception:
            pass

    return "", 204


@urls_bp.route("/urls/<int:url_id>/stats", methods=["GET"])
def url_stats(url_id):
    try:
        url_obj = URL.get_by_id(url_id)
    except URL.DoesNotExist:
        return jsonify({"error": "URL not found"}), 404

    redirect_count = (
        Event.select()
        .where(Event.url_id == url_id, Event.event_type == "redirect")
        .count()
    )

    return jsonify({
        "url": model_to_dict(url_obj, backrefs=False, recurse=False),
        "redirect_count": redirect_count,
    })


@urls_bp.route("/<short_code>", methods=["GET"])
def redirect_short_url(short_code):
    """
    Redirect handler. Oracle Hint 2 (Unseen Observer) + Hint 4 (Slumbering Guide).

    Order is critical:
    1. Look up URL by short_code WHERE is_active=True
    2. If not found -> 404, NO event (Hint 4)
    3. Create redirect event (Hint 2)
    4. Return 302
    """
    # Check cache first
    redis = _get_redis()
    cached = None
    if redis:
        try:
            cached = redis.get(f"url:{short_code}")
        except Exception:
            pass

    if cached:
        # Cache hit
        CACHE_HITS.inc()
        REDIRECTS_TOTAL.inc()
        cache_data = json.loads(cached)
        original_url = cache_data["original_url"]
        url_id = cache_data["url_id"]
        user_id = cache_data.get("user_id")

        # Log redirect event (Hint 2: Unseen Observer)
        Event.create(
            url_id=url_id,
            user_id=user_id,
            event_type="redirect",
            timestamp=datetime.datetime.utcnow(),
            details=json.dumps({
                "ip": request.remote_addr,
                "user_agent": request.headers.get("User-Agent", ""),
            }),
        )

        response = redirect(original_url, code=302)
        response.headers["X-Cache"] = "HIT"
        return response

    # DB lookup — only active URLs (Hint 4: Slumbering Guide)
    # Use .dicts() and select only needed columns to skip model instantiation
    CACHE_MISSES.inc()
    row = (
        URL.select(URL.original_url, URL.id, URL.user_id)
        .where((URL.short_code == short_code) & (URL.is_active == True))  # noqa: E712
        .dicts()
        .first()
    )
    if row is None:
        # No event logged for inactive/missing URLs (Hint 4)
        return jsonify({"error": "URL not found"}), 404

    original_url = row["original_url"]
    url_id = row["id"]
    user_id = row["user_id"]

    # Cache the result
    if redis:
        try:
            redis.setex(
                f"url:{short_code}",
                CACHE_TTL,
                json.dumps({
                    "original_url": original_url,
                    "url_id": url_id,
                    "user_id": user_id,
                }),
            )
        except Exception:
            pass

    REDIRECTS_TOTAL.inc()

    # Log redirect event BEFORE returning (Hint 2: Unseen Observer)
    Event.create(
        url_id=url_id,
        user_id=user_id,
        event_type="redirect",
        timestamp=datetime.datetime.utcnow(),
        details=json.dumps({
            "ip": request.remote_addr,
            "user_agent": request.headers.get("User-Agent", ""),
        }),
    )

    response = redirect(original_url, code=302)
    response.headers["X-Cache"] = "MISS"
    return response

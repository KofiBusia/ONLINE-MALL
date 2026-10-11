"""Template filters and values available in every template."""
from flask import current_app, url_for

from . import payments, services
from .data import (APPLICATION_STATUSES, AWNINGS, CATEGORIES, CAT_LABELS, PAY_METHODS, REGIONS, SORTS,
                   STATUS_FLOW, STATUS_LABELS)
from .utils import cedi, mask_phone, momo_network


def media_url(key, size="thumb"):
    return url_for("main.media", key=key, size=size) if key else ""


def register_filters(app):
    app.add_template_filter(cedi, "cedi")
    app.add_template_filter(mask_phone, "mask_phone")
    app.add_template_filter(momo_network, "network")
    app.add_template_filter(lambda c: CAT_LABELS.get(c, c), "cat_label")
    app.add_template_filter(lambda s: STATUS_LABELS.get(s, s), "status_label")
    app.add_template_filter(lambda d: d.strftime("%d %b %Y, %H:%M") if d else "", "dt")
    app.add_template_filter(lambda d: d.strftime("%d %b %Y") if d else "", "date")
    app.add_template_global(media_url, "media_url")

    @app.context_processor
    def globals_():
        cfg = current_app.config
        return {
            "cart_count": services.cart_count(),
            "current_region": services.current_region(),
            "regions": REGIONS, "categories": CATEGORIES, "sorts": SORTS, "pay_methods": PAY_METHODS,
            "status_flow": STATUS_FLOW, "status_labels": STATUS_LABELS, "awnings": AWNINGS,
            "application_statuses": APPLICATION_STATUSES,
            "paystack_enabled": payments.enabled(),
            "auto_release_hours": cfg["AUTO_RELEASE_HOURS"],
            "commission_pct": f"{cfg['COMMISSION_RATE'] * 100:g}",
            "max_photos": cfg["MAX_PHOTOS_PER_PRODUCT"],
            "max_photo_mb": cfg["MAX_PHOTO_MB"],
        }

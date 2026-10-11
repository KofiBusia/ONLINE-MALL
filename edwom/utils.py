"""Small helpers: validation, money, codes and safe redirects."""
import re
import secrets
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from flask import redirect, request, url_for

_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_code(prefix: str, length: int = 6) -> str:
    return prefix + "-" + "".join(secrets.choice(_CODE_CHARS) for _ in range(length))


def clean_phone(value: str) -> str:
    phone = re.sub(r"[\s\-().]", "", value or "")
    if phone.startswith("+233"):
        phone = "0" + phone[4:]
    elif phone.startswith("233") and len(phone) == 12:
        phone = "0" + phone[3:]
    return phone


def valid_phone(phone: str) -> bool:
    return bool(re.fullmatch(r"0[2-5]\d{8}", phone or ""))


def valid_gps(code: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{2}-\d{3,4}-\d{4}", (code or "").upper()))


def valid_ghana_card(number: str) -> bool:
    return bool(re.fullmatch(r"GHA-\d{9}-\d", (number or "").upper()))


def valid_email(email: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}", email or ""))


def momo_network(phone: str) -> str:
    prefix = (phone or "")[:3]
    if prefix in {"024", "054", "055", "059", "025", "053"}:
        return "MTN MoMo"
    if prefix in {"020", "050"}:
        return "Telecel Cash"
    if prefix in {"026", "056", "027", "057"}:
        return "AT Money"
    return "Mobile Money"


def to_pesewas(text: str):
    """'1,250.50' -> 125050. Returns None when invalid."""
    try:
        amount = Decimal((text or "").replace(",", "").strip())
    except InvalidOperation:
        return None
    if amount <= 0 or amount > Decimal("1000000"):
        return None
    return int((amount * 100).quantize(Decimal("1")))


def cedi(pesewas) -> str:
    return f"GH₵{(pesewas or 0) / 100:,.2f}"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:70] or "shop"


def mask_phone(phone: str) -> str:
    return f"{phone[:3]} ••• {phone[-4:]}" if phone and len(phone) >= 7 else ""


def to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_next(target: str):
    """Allow only same-site relative paths."""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


def redirect_back(default_endpoint: str = "main.index", **kwargs):
    target = safe_next(request.form.get("next") or request.args.get("next"))
    if not target and request.referrer:
        ref = urlparse(request.referrer)
        if ref.netloc == request.host:
            target = ref.path + (f"?{ref.query}" if ref.query else "")
    return redirect(target or url_for(default_endpoint, **kwargs))


def temp_password() -> str:
    """Readable one-time password, e.g. 'Kente-4827-Moro'."""
    words = ["Kente", "Adinkra", "Akwaaba", "Sankofa", "Volta", "Ashanti", "Kakum", "Mole", "Makola", "Osu"]
    return f"{secrets.choice(words)}-{secrets.randbelow(9000) + 1000}-{secrets.choice(words)}"


def valid_password(password: str) -> str:
    """Return an error message, or '' when the password is acceptable."""
    if len(password or "") < 10:
        return "Use at least 10 characters."
    if password.isdigit() or password.isalpha():
        return "Mix letters with numbers or symbols."
    return ""

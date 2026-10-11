"""Paystack integration (Mobile Money + cards in GHS).

Set PAYSTACK_SECRET_KEY to switch from demo payments to real ones.
Docs: https://paystack.com/docs/api/transaction/
"""
import hashlib
import hmac

import requests
from flask import current_app

API = "https://api.paystack.co"


class PaymentError(Exception):
    pass


def enabled() -> bool:
    return bool(current_app.config.get("PAYSTACK_SECRET_KEY"))


def _headers() -> dict:
    return {"Authorization": f"Bearer {current_app.config['PAYSTACK_SECRET_KEY']}",
            "Content-Type": "application/json"}


def initialize(email: str, amount: int, reference: str, callback_url: str, metadata: dict) -> str:
    """Start a payment and return the Paystack page to send the buyer to. amount is in pesewas."""
    payload = {"email": email, "amount": amount, "currency": "GHS", "reference": reference,
               "callback_url": callback_url, "channels": ["mobile_money", "card"], "metadata": metadata}
    try:
        resp = requests.post(f"{API}/transaction/initialize", json=payload, headers=_headers(), timeout=20)
        body = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise PaymentError(str(exc)) from exc
    if resp.status_code != 200 or not body.get("status"):
        raise PaymentError(body.get("message", "Paystack rejected the request"))
    return body["data"]["authorization_url"]


def verify(reference: str, expected_amount: int) -> bool:
    """True only if Paystack says the payment succeeded for the full amount in GHS."""
    try:
        resp = requests.get(f"{API}/transaction/verify/{reference}", headers=_headers(), timeout=20)
        body = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise PaymentError(str(exc)) from exc
    data = body.get("data") or {}
    return (body.get("status") is True and data.get("status") == "success"
            and data.get("currency") == "GHS" and int(data.get("amount", 0)) >= expected_amount)


def valid_signature(raw_body: bytes, signature: str) -> bool:
    secret = current_app.config["PAYSTACK_SECRET_KEY"].encode()
    digest = hmac.new(secret, raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(digest, signature or "")

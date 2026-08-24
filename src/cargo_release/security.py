from __future__ import annotations

import hashlib
import hmac
import json

from cargo_release.models import PartnerReceipt


class ReceiptSecurityError(ValueError):
    pass


def canonical_receipt(receipt: PartnerReceipt) -> bytes:
    return json.dumps(
        receipt.unsigned(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()


def sign_receipt(receipt: PartnerReceipt, secret: str) -> PartnerReceipt:
    signature = hmac.new(secret.encode(), canonical_receipt(receipt), hashlib.sha256).hexdigest()
    return receipt.model_copy(update={"signature": signature})


def verify_receipt(receipt: PartnerReceipt, secret: str) -> str:
    expected = hmac.new(secret.encode(), canonical_receipt(receipt), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, receipt.signature):
        raise ReceiptSecurityError("Partner receipt signature is invalid")
    return hashlib.sha256(canonical_receipt(receipt)).hexdigest()

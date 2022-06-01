import hashlib
import hmac
import time

from enum import Enum


class VerificationStatus(Enum):
    VERIFIED = 1
    BAD_SIGNATURE = 2
    OUTDATED_REQUEST = 3


def verify_signature(
    secret: str,
    body: str,
    req_sig: str,
    req_ts: int
) -> VerificationStatus:
    """Perform request signature verification.

    Requires the signing secret from your Slack application.
    The other parameters are the raw request body (from Slack), request
    signature, and  the request timestamp.

    See https://api.slack.com/authentication/verifying-requests-from-slack"""
    if abs(int(time.time()) - req_ts) > 300:
        # request timestamp is old, so ignore this request as it could be
        # a replay
        VerificationStatus.OUTDATED_REQUEST

    bs = f"v0:{req_ts}:{body}"
    hsh = hmac.new(
            bytes(secret, "utf-8"),
            msg=bytes(bs, "utf-8"),
            digestmod=hashlib.sha256).hexdigest()

    signature = f"v0={hsh}"
    if hmac.compare_digest(signature, req_sig):
        return VerificationStatus.VERIFIED
    return VerificationStatus.BAD_SIGNATURE

"""Meta (WhatsApp Cloud API) error codes, grouped by whether retrying can help.

Values are the strings Meta returns in `error.code`, which `send_task` stores
on `message_logs.error_code`.
"""

# Failures a retry can never clear: the rejection describes the recipient's
# permanent state, not a transient condition on our side or Meta's. Copying
# these into a retry campaign burns a send that is guaranteed to fail again.
#
#   131026  Undeliverable — recipient is not a reachable WhatsApp user.
#   131050  Recipient opted out of marketing messages from this business.
#   130472  Recipient is in a Meta experiment group excluded from delivery.
#
# 131049 (per-user marketing engagement cap) is deliberately NOT listed. That
# cap is a rolling window that clears over time — 1,614 of the 2,411 capped
# numbers observed in production have been delivered to successfully at other
# points — so a later retry is a legitimate attempt, not wasted quota.
NON_RETRYABLE_ERROR_CODES = frozenset({"131026", "131050", "130472"})

# Shared match fragment for "failed messages that are worth retrying". Spread
# it alongside a job_id filter so the count that decides whether to spawn a
# retry and the query that populates it can never diverge:
#
#     {"job_id": oid, **RETRYABLE_FAILED_MATCH}
#
# A missing or null error_code still matches — an unclassified failure is
# treated as retryable rather than silently dropped.
RETRYABLE_FAILED_MATCH: dict = {
    "status": "failed",
    "error_code": {"$nin": sorted(NON_RETRYABLE_ERROR_CODES)},
}

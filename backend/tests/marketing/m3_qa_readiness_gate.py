"""Read-only GO/NO-GO evidence gate for Campaign V2 M3 QA.

This module has no Flask app, provider imports, HTTP calls or write operations.
A passing result means READY_FOR_HUMAN_APPROVAL, never permission to submit.
Input must be a sanitized preflight response plus independently reviewed evidence.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

FINGERPRINT_VERSION = "campaign-v2-dispatch-v3"
HEX_64 = re.compile(r"^[0-9a-fA-F]{64}$")
REVIEW_FLAGS = (
    "frozen_export_reviewed",
    "sendable_export_reviewed",
    "qa_only_recipients_verified",
    "template_content_reviewed",
    "channel_ownership_reviewed",
    "fingerprint_reviewed",
)


def evaluate_m3_qa_readiness(preflight: Any, manifest: Any) -> dict[str, Any]:
    """Fail closed, emit only non-PII counts, codes and review status."""
    errors: list[str] = []

    def block(code: str) -> None:
        if code not in errors:
            errors.append(code)

    if not isinstance(preflight, dict) or not isinstance(manifest, dict):
        return {
            "status": "BLOCKED", "errors": ["INVALID_INPUT"],
            "send_authorized": False, "campaign_id": None,
            "batch_count": 0, "sendable_count": 0,
        }

    cid = preflight.get("campaign_id")
    expected_id = manifest.get("expected_campaign_id")
    if type(cid) is not int or cid <= 0 or type(expected_id) is not int or cid != expected_id:
        block("CAMPAIGN_ID_MISMATCH")

    if preflight.get("provider") != "IVENTAS":
        block("PROVIDER_MISMATCH")
    if preflight.get("ready") is not True:
        block("PREFLIGHT_NOT_READY")

    expected_mode = manifest.get("expected_mode")
    if expected_mode not in ("IMMEDIATE", "SCHEDULED") or preflight.get("mode") != expected_mode:
        block("DISPATCH_MODE_MISMATCH")
    schedule = preflight.get("schedule")
    if expected_mode == "IMMEDIATE" and schedule is not None:
        block("UNEXPECTED_SCHEDULE")
    if expected_mode == "SCHEDULED":
        if not isinstance(schedule, dict) or any(
            not isinstance(schedule.get(key), str) or not schedule.get(key)
            for key in ("timezone", "local_datetime", "scheduled_for_utc", "provider_send_at")
        ):
            block("SCHEDULE_INCOMPLETE")
        elif (
            schedule["timezone"] != manifest.get("expected_timezone")
            or schedule["local_datetime"] != manifest.get("expected_local_datetime")
        ):
            block("SCHEDULE_MISMATCH")

    fingerprint = preflight.get("dispatch_fingerprint")
    if (
        preflight.get("dispatch_fingerprint_version") != FINGERPRINT_VERSION
        or not isinstance(fingerprint, str)
        or HEX_64.fullmatch(fingerprint) is None
        or manifest.get("reviewed_dispatch_fingerprint") != fingerprint
    ):
        block("FINGERPRINT_UNCONFIRMED")

    for name in ("frozen_export_sha256", "sendable_export_sha256"):
        digest = manifest.get(name)
        if not isinstance(digest, str) or HEX_64.fullmatch(digest) is None:
            block("EXPORT_HASH_MISSING")

    for name in REVIEW_FLAGS:
        if manifest.get(name) is not True:
            block("MANUAL_REVIEW_MISSING")

    frozen = preflight.get("frozen_count")
    sendable = preflight.get("sendable_count")
    total_expected = manifest.get("expected_sendable_count")
    limit = manifest.get("max_qa_recipients")
    if (
        type(frozen) is not int or type(sendable) is not int
        or frozen <= 0 or sendable <= 0 or sendable > frozen
        or type(total_expected) is not int or sendable != total_expected
        or type(limit) is not int or limit <= 0 or sendable > limit
    ):
        block("AUDIENCE_COUNT_MISMATCH")

    suppressed = preflight.get("suppressed")
    if (
        not isinstance(suppressed, dict)
        or type(suppressed.get("blacklist")) is not int
        or suppressed["blacklist"] < 0
        or type(frozen) is not int or type(sendable) is not int
        or suppressed["blacklist"] > frozen - sendable
    ):
        block("SUPPRESSION_COUNT_INCONSISTENT")

    blocked = preflight.get("blocked")
    if not isinstance(blocked, dict) or not blocked or any(
        type(v) is not int or v != 0 for v in blocked.values()
    ):
        block("PREFLIGHT_HAS_BLOCKERS")

    batches = preflight.get("batches")
    expected_branches = manifest.get("expected_provider_channels")
    if (
        not isinstance(batches, list) or not batches
        or not isinstance(expected_branches, dict) or not expected_branches
        or preflight.get("provider_campaign_count") != len(batches)
        or len(batches) != len(expected_branches)
    ):
        block("BATCH_COUNT_MISMATCH")
        batches = batches if isinstance(batches, list) else []
        expected_branches = expected_branches if isinstance(expected_branches, dict) else {}
    seen: set[str] = set()
    batch_sum = 0
    expected_template = manifest.get("expected_template_id")
    for batch in batches:
        if not isinstance(batch, dict):
            block("INVALID_BATCH")
            continue
        branch = batch.get("sucursal_canon")
        if not isinstance(branch, str) or not branch or branch in seen or branch not in expected_branches:
            block("BRANCH_MISMATCH")
        else:
            seen.add(branch)
            if batch.get("provider_channel_id") != expected_branches[branch]:
                block("CHANNEL_MISMATCH")
        count = batch.get("recipient_count")
        if type(count) is not int or count <= 0:
            block("INVALID_BATCH_RECIPIENT_COUNT")
        else:
            batch_sum += count
        if type(expected_template) is not int or batch.get("template_id") != expected_template:
            block("TEMPLATE_MISMATCH")
        if batch.get("ready") is not True or batch.get("blocked_reasons") != []:
            block("BATCH_HAS_BLOCKERS")
        if type(batch.get("sucursal_id")) is not int or batch["sucursal_id"] <= 0:
            block("INVALID_BRANCH_ID")
        if not isinstance(batch.get("provider_channel_id"), str) or not batch["provider_channel_id"]:
            block("CHANNEL_MISSING")

    if seen != set(expected_branches):
        block("BRANCH_MISMATCH")
    if type(sendable) is not int or batch_sum != sendable:
        block("BATCH_TOTAL_MISMATCH")
    if not isinstance(preflight.get("template"), dict) or preflight["template"].get("id") != expected_template:
        block("TEMPLATE_MISMATCH")

    return {
        "status": "BLOCKED" if errors else "READY_FOR_HUMAN_APPROVAL",
        "errors": sorted(errors),
        "send_authorized": False,
        "campaign_id": cid if type(cid) is int else None,
        "batch_count": len(batches),
        "sendable_count": sendable if type(sendable) is int else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline M3 QA evidence check; never sends.")
    parser.add_argument("--input", required=True, help="Private local JSON with preflight and manifest")
    args = parser.parse_args()
    try:
        value = json.loads(Path(args.input).read_text(encoding="utf-8"))
        result = evaluate_m3_qa_readiness(value.get("preflight"), value.get("manifest"))
    except (OSError, ValueError, AttributeError):
        result = {
            "status": "BLOCKED", "errors": ["INVALID_INPUT"],
            "send_authorized": False, "campaign_id": None,
            "batch_count": 0, "sendable_count": 0,
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "READY_FOR_HUMAN_APPROVAL" else 2


if __name__ == "__main__":
    raise SystemExit(main())

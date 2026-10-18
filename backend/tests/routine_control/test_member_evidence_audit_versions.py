"""Audit contract compatibility for routine member/evidence links."""

import unittest

from app.routine_control.domain.commands import LinkRoutineMemberEvidenceCommand
from app.routine_control.domain.exceptions import (
    RoutineControlMemberEvidenceValidationError,
)
from app.routine_control.services.member_evidence_service import (
    _validate_link_command,
)


class RoutineMemberEvidenceAuditVersionTestCase(unittest.TestCase):
    def _command(self, version, corroborator, method="EMAIL"):
        return LinkRoutineMemberEvidenceCommand(
            member_id=1,
            evidence_id=2,
            match_method=method,
            identity_corroborator=corroborator,
            temporal_delta_days=13,
            matching_contract_version=version,
        )

    def test_legacy_v2_audit_is_still_accepted(self):
        _validate_link_command(self._command(
            "IDENTITY_TEMPORAL_V2", "EMAIL_AND_NAME"
        ))

    def test_v3_variants_have_distinct_audit_labels(self):
        for label in (
            "EMAIL_NAME_PREFIX", "EMAIL_NAME_INITIAL",
            "EMAIL_SURNAME_SWAP", "EMAIL_FIRST_NAME_INSERTION",
        ):
            with self.subTest(label=label):
                _validate_link_command(self._command("IDENTITY_TEMPORAL_V3", label))

    def test_v3_audit_cannot_be_falsely_labeled_v2(self):
        with self.assertRaises(RoutineControlMemberEvidenceValidationError):
            _validate_link_command(self._command(
                "IDENTITY_TEMPORAL_V2", "EMAIL_NAME_PREFIX"
            ))

    def test_external_id_route_does_not_allow_name_variant(self):
        with self.assertRaises(RoutineControlMemberEvidenceValidationError):
            _validate_link_command(self._command(
                "IDENTITY_TEMPORAL_V3", "EMAIL_NAME_PREFIX", "EXTERNAL_ID"
            ))

    def test_unknown_version_is_rejected(self):
        with self.assertRaises(RoutineControlMemberEvidenceValidationError):
            _validate_link_command(self._command("IDENTITY_TEMPORAL_V4", "EMAIL_AND_NAME"))


if __name__ == "__main__":
    unittest.main()

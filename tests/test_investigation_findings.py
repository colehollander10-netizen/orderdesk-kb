import unittest

from skill.scripts.investigation_findings import derive_cross_source_findings


def evidence_records():
    commit = "2222222222222222222222222222222222222222"
    return [
        {
            "id": "notion-retry-policy",
            "claim_key": "provider_rejection_retry_policy",
            "claim_value": "explicit_rejections_should_retry_once",
            "summary": "The current Support process says an explicit provider rejection should receive one bounded retry.",
            "source_type": "notion",
            "safe_reference": "synthetic-notion-retry-policy",
            "source_date": "2026-07-21",
            "retrieved_at": "2026-07-22T17:00:00Z",
            "authority": "authoritative",
            "claim_supported": "The intended process requires one bounded retry for explicit provider rejections.",
            "coverage": "Approved Support-profile page; current process section.",
        },
        {
            "id": "code-submission-handler",
            "claim_key": "provider_rejection_retry_policy",
            "claim_value": "explicit_rejections_are_not_automatically_retried",
            "summary": "The submission handler records an explicit provider rejection as failed without enqueuing an automatic retry.",
            "source_type": "code_context",
            "safe_reference": f"synthetic/orderdesk-v3:src/Fulfillment/SubmissionHandler.php:120-146@{commit}",
            "source_date": "2026-07-21",
            "retrieved_at": "2026-07-22T17:00:00Z",
            "authority": "supporting",
            "claim_supported": "Explicit provider rejections enter the failed-submission path.",
            "coverage": "Approved default-branch snapshot; bounded handler passage.",
        },
        {
            "id": "code-retry-selector",
            "claim_key": "provider_rejection_retry_policy",
            "claim_value": "explicit_rejections_are_not_automatically_retried",
            "summary": "The retry selector includes transient transport failures but excludes explicit provider rejections.",
            "source_type": "code_context",
            "safe_reference": f"synthetic/orderdesk-v3:src/Jobs/RetryFailedSubmission.php:44-68@{commit}",
            "source_date": "2026-07-21",
            "retrieved_at": "2026-07-22T17:00:00Z",
            "authority": "supporting",
            "claim_supported": "Only transient transport failures are selected for automatic retry.",
            "coverage": "Approved default-branch snapshot; bounded retry-selector passage.",
        },
    ]


def slack_notion_records():
    return [
        {
            "id": "slack-recent-workaround",
            "claim_key": "provider_connection_retry_process",
            "claim_value": "refresh_then_retry_immediately",
            "summary": "A recent Slack thread recommends refreshing the provider connection and retrying immediately.",
            "source_type": "slack",
            "safe_reference": "synthetic-slack-recent-workaround",
            "source_date": "2026-07-22",
            "retrieved_at": "2026-07-22T18:00:00Z",
            "authority": "supporting",
            "claim_supported": "A recent informal workaround recommends an immediate refresh and retry.",
            "coverage": "Message-only Slack search, 14-day window, one of at most ten results.",
        },
        {
            "id": "notion-current-retry-process",
            "claim_key": "provider_connection_retry_process",
            "claim_value": "verify_connection_then_retry_once",
            "summary": "The current Support process requires verifying connection state before one bounded retry.",
            "source_type": "notion",
            "safe_reference": "synthetic-notion-current-retry-process",
            "source_date": "2026-07-21",
            "retrieved_at": "2026-07-22T18:00:00Z",
            "authority": "authoritative",
            "claim_supported": "The intended process requires connection verification before one bounded retry.",
            "coverage": "Approved Support-profile page; owner-backed current process section.",
        },
    ]


class InvestigationFindingsTests(unittest.TestCase):
    def test_derives_intent_implementation_mismatch_without_global_source_winner(self):
        findings = derive_cross_source_findings(evidence_records())

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding["findingType"], "intended_vs_implemented")
        self.assertEqual(finding["claimKey"], "provider_rejection_retry_policy")
        self.assertEqual(finding["relationship"], "mismatch")
        self.assertEqual(finding["intended"]["sourceIds"], ["notion-retry-policy"])
        self.assertEqual(
            finding["implemented"]["sourceIds"],
            ["code-retry-selector", "code-submission-handler"],
        )
        self.assertTrue(finding["implemented"]["commitPinned"])
        self.assertNotIn("preferredSourceId", finding)
        self.assertEqual(
            finding["notEstablished"],
            ["deployed_commit", "runtime_path", "correct_remediation"],
        )
        self.assertEqual(finding["route"], "Likely code change")
        self.assertEqual(
            finding["nextStep"],
            "Ask Engineering to verify the deployed commit and reconcile the cited implementation with the authoritative intended process",
        )

    def test_requires_both_claim_roles_and_does_not_invent_a_mismatch(self):
        records = evidence_records()
        self.assertEqual(derive_cross_source_findings(records[:1]), [])
        self.assertEqual(derive_cross_source_findings(records[1:]), [])
        aligned = [dict(item, claim_value="one_bounded_retry") for item in records]
        finding = derive_cross_source_findings(aligned)[0]
        self.assertEqual(finding["relationship"], "aligned")
        self.assertNotEqual(finding["route"], "Likely code change")

    def test_non_authoritative_notion_cannot_create_an_engineering_route(self):
        records = evidence_records()
        records[0] = dict(records[0], authority="supporting")
        self.assertEqual(derive_cross_source_findings(records), [])
        records = evidence_records()
        records[1:] = [dict(item, authority="unknown") for item in records[1:]]
        self.assertEqual(derive_cross_source_findings(records), [])

    def test_derives_informal_intended_mismatch_with_process_route(self):
        finding = derive_cross_source_findings(slack_notion_records())[0]

        self.assertEqual(finding["findingType"], "informal_vs_intended")
        self.assertEqual(finding["claimKey"], "provider_connection_retry_process")
        self.assertEqual(finding["relationship"], "mismatch")
        self.assertEqual(finding["informal"]["sourceIds"], ["slack-recent-workaround"])
        self.assertEqual(finding["intended"]["sourceIds"], ["notion-current-retry-process"])
        self.assertNotIn("preferredSourceId", finding)
        self.assertEqual(finding["notEstablished"], ["runtime_outcome", "workaround_approval"])
        self.assertEqual(finding["route"], "Store configuration / Rule Builder")
        self.assertEqual(
            finding["nextStep"],
            "Follow the authoritative process and send the informal workaround to the process owner for review",
        )

    def test_informal_intended_finding_requires_supporting_slack_and_authoritative_notion(self):
        records = slack_notion_records()
        records[0] = dict(records[0], authority="unknown")
        self.assertEqual(derive_cross_source_findings(records), [])
        records = slack_notion_records()
        records[1] = dict(records[1], authority="supporting")
        self.assertEqual(derive_cross_source_findings(records), [])


if __name__ == "__main__":
    unittest.main()

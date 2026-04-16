from django.test import SimpleTestCase

from helpers.utils.document_actions import build_document_action_flags


class DocumentActionFlagsTests(SimpleTestCase):
    def test_build_document_action_flags_for_confirmed_document(self):
        flags = build_document_action_flags(
            status_value=2,
            draft_status=1,
            confirmed_status=2,
            posted_status=3,
            cancelled_status=4,
            status_name="Confirmed",
            allow_edit_confirmed=True,
            allow_unpost_posted=False,
            include_reverse=True,
            include_rebuild_tax_summary=True,
            can_delete=False,
        )

        self.assertTrue(flags["can_edit"])
        self.assertFalse(flags["can_confirm"])
        self.assertTrue(flags["can_post"])
        self.assertTrue(flags["can_cancel"])
        self.assertFalse(flags["can_unpost"])
        self.assertFalse(flags["can_reverse"])
        self.assertTrue(flags["can_rebuild_tax_summary"])
        self.assertFalse(flags["can_delete"])
        self.assertEqual(flags["status_name"], "Confirmed")

    def test_build_document_action_flags_for_posted_document(self):
        flags = build_document_action_flags(
            status_value=3,
            draft_status=1,
            confirmed_status=2,
            posted_status=3,
            cancelled_status=4,
            status_name="Posted",
            allow_edit_confirmed=False,
            allow_unpost_posted=True,
        )

        self.assertFalse(flags["can_edit"])
        self.assertFalse(flags["can_post"])
        self.assertTrue(flags["can_unpost"])
        self.assertFalse(flags["can_cancel"])

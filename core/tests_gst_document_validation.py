from django.test import SimpleTestCase

from core.gst_document_validation import gst_classification_error


class GstDocumentClassificationTests(SimpleTestCase):
    def test_goods_hsn_accepts_standard_lengths(self):
        for code in ("8471", "847130", "84713010"):
            with self.subTest(code=code):
                self.assertIsNone(gst_classification_error(code, is_service=False))

    def test_goods_hsn_rejects_missing_non_numeric_and_wrong_length(self):
        for code in ("", "84A1", "123", "12345", "1234567"):
            with self.subTest(code=code):
                self.assertIsNotNone(gst_classification_error(code, is_service=False))

    def test_service_sac_requires_six_digits(self):
        self.assertIsNone(gst_classification_error("998314", is_service=True))
        self.assertIsNotNone(gst_classification_error("9983", is_service=True))
        self.assertIsNotNone(gst_classification_error("99831A", is_service=True))

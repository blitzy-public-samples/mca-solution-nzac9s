import unittest
from unittest.mock import patch, MagicMock
from services.email_processing import EmailProcessingService
from services.ocr import OCRService
from services.data_extraction import DataExtractionService
from services.webhook import WebhookService

class TestEmailProcessingService(unittest.TestCase):
    def setUp(self):
        self.email_service = EmailProcessingService()

    def test_process_email(self):
        mock_email = MagicMock()
        mock_email.attachments = [MagicMock()]
        result = self.email_service.process_email(mock_email)
        self.assertIsNotNone(result)

    def test_extract_attachments(self):
        mock_email = MagicMock()
        mock_email.attachments = [MagicMock(), MagicMock()]
        attachments = self.email_service.extract_attachments(mock_email)
        self.assertEqual(len(attachments), 2)

class TestOCRService(unittest.TestCase):
    def setUp(self):
        self.ocr_service = OCRService()

    @patch('services.ocr.pytesseract')
    def test_perform_ocr(self, mock_pytesseract):
        mock_pytesseract.image_to_string.return_value = "Test OCR Result"
        mock_image = MagicMock()
        result = self.ocr_service.perform_ocr(mock_image)
        self.assertEqual(result, "Test OCR Result")

class TestDataExtractionService(unittest.TestCase):
    def setUp(self):
        self.data_extraction_service = DataExtractionService()

    def test_extract_data(self):
        mock_text = "Invoice #12345\nTotal: $100.00"
        result = self.data_extraction_service.extract_data(mock_text)
        self.assertIn('invoice_number', result)
        self.assertIn('total_amount', result)

class TestWebhookService(unittest.TestCase):
    def setUp(self):
        self.webhook_service = WebhookService()

    @patch('services.webhook.requests')
    def test_send_webhook(self, mock_requests):
        mock_requests.post.return_value.status_code = 200
        result = self.webhook_service.send_webhook("http://example.com", {"key": "value"})
        self.assertTrue(result)

    @patch('services.webhook.requests')
    def test_send_webhook_failure(self, mock_requests):
        mock_requests.post.return_value.status_code = 500
        result = self.webhook_service.send_webhook("http://example.com", {"key": "value"})
        self.assertFalse(result)

if __name__ == '__main__':
    unittest.main()
from unittest.mock import MagicMock, patch


def test_send_calls_resend_with_expected_payload():
    from engine.mailer import Mailer

    with patch("engine.mailer.resend") as mock_resend, \
         patch("engine.mailer.EmailConfig") as mock_config:
        mock_config.RESEND_API_KEY = "test-key"
        mock_config.MAIL_FROM = "from@example.com"
        mock_resend.Emails = MagicMock()

        Mailer().send(recipient="to@example.com", subject="Hi", body="Body text")

        assert mock_resend.api_key == "test-key"
        mock_resend.Emails.send.assert_called_once_with({
            "from": "from@example.com",
            "to": "to@example.com",
            "subject": "Hi",
            "text": "Body text",
        })

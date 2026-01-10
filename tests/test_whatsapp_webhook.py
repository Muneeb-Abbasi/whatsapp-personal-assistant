"""
Integration tests for WhatsApp webhook endpoint.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app


class TestWhatsAppWebhook:
    """Tests for the WhatsApp webhook endpoint."""
    
    @pytest.fixture
    def client(self):
        """Create a test client."""
        return TestClient(app)
    
    @pytest.fixture
    def valid_webhook_data(self):
        """Valid webhook form data."""
        return {
            "Body": "Remind me to pay bills tomorrow at 9am",
            "From": "whatsapp:+923001234567",
            "MessageSid": "SM123456789abcdef",
            "NumMedia": "0",
        }
    
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")
        
        assert response.status_code == 200
        assert "WhatsApp Personal Assistant" in response.json()["name"]
    
    @patch("app.api.whatsapp_webhook.is_message_processed", new_callable=AsyncMock)
    @patch("app.api.whatsapp_webhook.mark_message_processed", new_callable=AsyncMock)
    @patch("app.api.whatsapp_webhook.parse_user_message", new_callable=AsyncMock)
    @patch("app.api.whatsapp_webhook.send_whatsapp_message", new_callable=AsyncMock)
    def test_webhook_processes_text_message(
        self,
        mock_send,
        mock_parse,
        mock_mark,
        mock_is_processed,
        client,
        valid_webhook_data,
        sample_parsed_intent
    ):
        """Test that webhook processes a text message."""
        mock_is_processed.return_value = False
        mock_parse.return_value = sample_parsed_intent
        mock_send.return_value = True
        
        with patch("app.api.whatsapp_webhook.DatabaseSession") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session
            
            with patch("app.api.whatsapp_webhook.ReminderService") as mock_service:
                mock_service_instance = MagicMock()
                mock_service_instance.handle_intent = AsyncMock(return_value="Reminder created!")
                mock_service.return_value = mock_service_instance
                
                response = client.post(
                    "/webhook/whatsapp",
                    data=valid_webhook_data
                )
        
        assert response.status_code == 200
        mock_mark.assert_called_once_with("SM123456789abcdef")
    
    @patch("app.api.whatsapp_webhook.is_message_processed", new_callable=AsyncMock)
    def test_webhook_skips_duplicate_message(
        self,
        mock_is_processed,
        client,
        valid_webhook_data
    ):
        """Test that webhook skips already processed messages."""
        mock_is_processed.return_value = True
        
        response = client.post(
            "/webhook/whatsapp",
            data=valid_webhook_data
        )
        
        assert response.status_code == 200
    
    @patch("app.api.whatsapp_webhook.is_message_processed", new_callable=AsyncMock)
    @patch("app.api.whatsapp_webhook.mark_message_processed", new_callable=AsyncMock)
    def test_webhook_skips_empty_message(
        self,
        mock_mark,
        mock_is_processed,
        client
    ):
        """Test that webhook skips empty messages."""
        mock_is_processed.return_value = False
        
        data = {
            "Body": "",
            "From": "whatsapp:+923001234567",
            "MessageSid": "SM123456789",
            "NumMedia": "0",
        }
        
        response = client.post("/webhook/whatsapp", data=data)
        
        assert response.status_code == 200
    
    @patch("app.api.whatsapp_webhook.is_message_processed", new_callable=AsyncMock)
    @patch("app.api.whatsapp_webhook.mark_message_processed", new_callable=AsyncMock)
    @patch("app.api.whatsapp_webhook.download_and_transcribe_audio", new_callable=AsyncMock)
    @patch("app.api.whatsapp_webhook.parse_user_message", new_callable=AsyncMock)
    @patch("app.api.whatsapp_webhook.send_whatsapp_message", new_callable=AsyncMock)
    def test_webhook_processes_audio_message(
        self,
        mock_send,
        mock_parse,
        mock_transcribe,
        mock_mark,
        mock_is_processed,
        client,
        sample_parsed_intent
    ):
        """Test that webhook processes audio messages."""
        mock_is_processed.return_value = False
        mock_transcribe.return_value = "Remind me to call mom"
        mock_parse.return_value = sample_parsed_intent
        mock_send.return_value = True
        
        data = {
            "Body": "",
            "From": "whatsapp:+923001234567",
            "MessageSid": "SM123456789audio",
            "NumMedia": "1",
            "MediaUrl0": "https://api.twilio.com/media/123",
            "MediaContentType0": "audio/ogg",
        }
        
        with patch("app.api.whatsapp_webhook.DatabaseSession") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session
            
            with patch("app.api.whatsapp_webhook.ReminderService") as mock_service:
                mock_service_instance = MagicMock()
                mock_service_instance.handle_intent = AsyncMock(return_value="Done!")
                mock_service.return_value = mock_service_instance
                
                response = client.post("/webhook/whatsapp", data=data)
        
        assert response.status_code == 200
        mock_transcribe.assert_called_once()
    
    @patch("app.api.whatsapp_webhook.is_message_processed", new_callable=AsyncMock)
    @patch("app.api.whatsapp_webhook.mark_message_processed", new_callable=AsyncMock)
    @patch("app.api.whatsapp_webhook.download_and_transcribe_audio", new_callable=AsyncMock)
    @patch("app.api.whatsapp_webhook.send_error_message", new_callable=AsyncMock)
    def test_webhook_handles_failed_transcription(
        self,
        mock_send_error,
        mock_transcribe,
        mock_mark,
        mock_is_processed,
        client
    ):
        """Test that webhook handles transcription failure gracefully."""
        mock_is_processed.return_value = False
        mock_transcribe.return_value = None  # Transcription failed
        mock_send_error.return_value = True
        
        data = {
            "Body": "",
            "From": "whatsapp:+923001234567",
            "MessageSid": "SM123456789fail",
            "NumMedia": "1",
            "MediaUrl0": "https://api.twilio.com/media/123",
            "MediaContentType0": "audio/ogg",
        }
        
        response = client.post("/webhook/whatsapp", data=data)
        
        assert response.status_code == 200
        mock_send_error.assert_called_once()


class TestProcessedMessageDeduplication:
    """Tests for message deduplication using SQLite."""
    
    @pytest.mark.asyncio
    async def test_is_message_processed_returns_false_for_new(self, test_session):
        """Test that new messages are not marked as processed."""
        from app.api.whatsapp_webhook import is_message_processed
        
        with patch("app.api.whatsapp_webhook.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__.return_value = test_session
            
            result = await is_message_processed("NEW_MESSAGE_SID")
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_mark_and_check_processed(self, test_session):
        """Test marking a message as processed and checking it."""
        from app.api.whatsapp_webhook import mark_message_processed, is_message_processed
        from app.domain.processed_message import ProcessedMessage
        
        # Manually add a processed message to the test session
        processed = ProcessedMessage(
            message_sid="TEST_SID_123",
            processed_at=datetime.utcnow()
        )
        test_session.add(processed)
        await test_session.commit()
        
        with patch("app.api.whatsapp_webhook.async_session_factory") as mock_factory:
            mock_factory.return_value.__aenter__.return_value = test_session
            
            result = await is_message_processed("TEST_SID_123")
            
            assert result is True

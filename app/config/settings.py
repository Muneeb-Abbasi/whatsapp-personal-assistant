"""
Application settings and configuration.
All secrets are loaded from environment variables.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Twilio Configuration
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_number: str  # Format: whatsapp:+14155238886
    twilio_phone_number: str  # For voice calls
    
    # OpenAI Configuration
    openai_api_key: str
    
    # User Configuration (Single User)
    user_whatsapp_number: str  # Format: whatsapp:+923001234567
    user_phone_number: str  # For receiving calls
    
    # Database - Use DATA_DIR for Railway persistent volume
    data_dir: str = "."
    
    @property
    def database_url(self) -> str:
        """Database URL with support for Railway persistent volumes."""
        return f"sqlite+aiosqlite:///{self.data_dir}/reminders.db"
    
    # Application Settings
    debug: bool = False
    validate_twilio_signature: bool = True
    
    # Timezone (Pakistan Standard Time)
    timezone: str = "Asia/Karachi"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

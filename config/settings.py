# app/config/settings.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    AWS_REGION: str = "us-east-1"
    S3_BUCKET: str = "loan-documents-123"
    KNOWLEDGE_BASE_ID: str = "SSEVRJKTXH"
    DATA_SOURCE_ID: str = "9M0ZTJMEN1"
    MODEL_ID: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    
    class Config:
        env_file = ".env"

settings = Settings()
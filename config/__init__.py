
# app/config/__init__.py
from config.aws_config import (
    bedrock_agent_runtime_client,
    s3_client,
    bedrock_agent,
    bucket,
    model_arn,
    bedrock_client,
    KNOWLEDGE_BASE_ID,
    DATA_SOURCE_ID
)
from config.settings import settings
from config.logging_config import logger
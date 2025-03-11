# app/config/__init__.py
from config.aws_config import (
    DATA_SOURCE_ID,
    KNOWLEDGE_BASE_ID,
    bedrock_agent,
    bedrock_agent_runtime_client,
    bedrock_client,
    bucket,
    model_arn,
    s3_client,
)
from config.dynamodb_config import (
    SCHEMAS_TABLE_NAME,
    get_dynamodb_resource,
    get_schemas_table,
    get_table,
)
from config.logging_config import logger
from config.settings import settings

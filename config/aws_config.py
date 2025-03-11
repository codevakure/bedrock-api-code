import os

import boto3
from botocore.config import Config
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get configuration from environment variables
region = os.getenv("AWS_REGION", "us-east-1")
bucket = os.getenv("S3_BUCKET")
model_id = os.getenv("MODEL_ID")
KNOWLEDGE_BASE_ID = os.getenv("KNOWLEDGE_BASE_ID")
DATA_SOURCE_ID = os.getenv("DATA_SOURCE_ID")

# Construct model ARN
model_arn = f"arn:aws:bedrock:{region}::foundation-model/{model_id}"

# AWS Config
config = Config(region_name=region, retries=dict(max_attempts=3, mode="standard"))

# Initialize AWS clients
bedrock_agent_runtime_client = boto3.client("bedrock-agent-runtime", config=config)
s3_client = boto3.client("s3")
bedrock_agent = boto3.client("bedrock-agent", config=config)
bedrock_client = boto3.client("bedrock", config=config)
bedrock_runtime = boto3.client("bedrock-runtime", config=config)
cloudwatch_client = boto3.client("cloudwatch", region_name=region)

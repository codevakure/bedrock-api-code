#!/usr/bin/env python
"""
DynamoDB Initialization Script

This script initializes all required DynamoDB tables for the application.
It's designed to be run as part of the deployment pipeline before
starting the application.

Usage:
    python init_dynamodb.py [--local]

Options:
    --local    Initialize using DynamoDB local instance
"""

import argparse
import logging
import os
import sys

import boto3
from botocore.exceptions import ClientError

# Add the project root to path so imports work correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Table definitions
SCHEMAS_TABLE = {
    "name": os.environ.get("DYNAMODB_SCHEMAS_TABLE", "database_schemas"),
    "schema": [
        {"AttributeName": "connection_id", "KeyType": "HASH"},  # Partition key
        {"AttributeName": "version", "KeyType": "RANGE"},  # Sort key
    ],
    "attributes": [
        {"AttributeName": "connection_id", "AttributeType": "S"},
        {"AttributeName": "version", "AttributeType": "S"},
    ],
    "indexes": [],  # Global secondary indexes if needed
}

# Add more table definitions as needed
TABLES = [SCHEMAS_TABLE]


def get_dynamodb_client(local=False):
    """Get DynamoDB client based on environment"""
    region = os.environ.get("AWS_REGION", "us-east-1")

    if local:
        endpoint = os.environ.get("DYNAMODB_ENDPOINT", "http://localhost:8000")
        logger.info(f"Using local DynamoDB at {endpoint}")
        return boto3.client(
            "dynamodb",
            endpoint_url=endpoint,
            region_name=region,
            aws_access_key_id="dummy",
            aws_secret_access_key="dummy",
        )
    else:
        logger.info(f"Using AWS DynamoDB in region {region}")
        return boto3.client("dynamodb", region_name=region)


def create_table(client, table_def):
    """Create a DynamoDB table from definition"""
    table_name = table_def["name"]

    try:
        # Check if table exists
        client.describe_table(TableName=table_name)
        logger.info(f"Table {table_name} already exists")
        return False
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            logger.error(f"Error checking table {table_name}: {e}")
            raise e

        # Table doesn't exist, create it
        try:
            logger.info(f"Creating table {table_name}...")

            create_params = {
                "TableName": table_name,
                "KeySchema": table_def["schema"],
                "AttributeDefinitions": table_def["attributes"],
                "BillingMode": "PAY_PER_REQUEST",  # On-demand capacity for production
            }

            # Add GSIs if defined
            if table_def.get("indexes"):
                create_params["GlobalSecondaryIndexes"] = table_def["indexes"]

            client.create_table(**create_params)

            # Wait for table to be created
            logger.info(f"Waiting for table {table_name} to be active...")
            waiter = client.get_waiter("table_exists")
            waiter.wait(TableName=table_name)

            logger.info(f"Table {table_name} created successfully")
            return True

        except ClientError as e:
            logger.error(f"Error creating table {table_name}: {e}")
            raise e


def initialize_tables(local=False):
    """Initialize all tables defined in TABLES"""
    client = get_dynamodb_client(local)
    created_tables = []

    for table_def in TABLES:
        table_name = table_def["name"]
        try:
            created = create_table(client, table_def)
            if created:
                created_tables.append(table_name)
        except Exception as e:
            logger.error(f"Failed to initialize table {table_name}: {e}")
            logger.error("Initialization failed, exiting.")
            sys.exit(1)

    if created_tables:
        logger.info(f"Created tables: {', '.join(created_tables)}")
    else:
        logger.info("No new tables created, all tables already exist")

    return created_tables


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Initialize DynamoDB tables")
    parser.add_argument("--local", action="store_true", help="Use local DynamoDB instance")
    return parser.parse_args()


def main():
    """Main entry point"""
    args = parse_arguments()

    logger.info("Starting DynamoDB initialization")
    try:
        created_tables = initialize_tables(local=args.local)
        logger.info("DynamoDB initialization completed successfully")
        return 0
    except Exception as e:
        logger.error(f"Unhandled exception during initialization: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

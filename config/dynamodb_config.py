"""
DynamoDB Configuration

This module provides configuration and connection management for DynamoDB.
It centralizes DynamoDB resources and connections for the application.
"""

import os
import logging
from typing import Dict, Any

import boto3
from boto3.resources.base import ServiceResource

logger = logging.getLogger(__name__)

# Table names - read from environment variables with defaults
SCHEMAS_TABLE_NAME = os.environ.get("DYNAMODB_SCHEMAS_TABLE", "database_schemas")

# Connection cache
_dynamodb_resource = None
_table_cache = {}


def get_dynamodb_resource() -> ServiceResource:
    """
    Get or create a DynamoDB resource with appropriate configuration.
    
    Returns:
        boto3.resources.base.ServiceResource: The DynamoDB resource
    """
    global _dynamodb_resource
    
    if _dynamodb_resource is not None:
        return _dynamodb_resource
    
    region = os.environ.get("AWS_REGION", "us-east-1")
    use_local = os.environ.get("USE_LOCAL_DYNAMODB", "").lower() in ("true", "1", "yes")
    
    if use_local:
        endpoint_url = os.environ.get("DYNAMODB_ENDPOINT", "http://localhost:8000")
        logger.info(f"Connecting to local DynamoDB at {endpoint_url}")
        
        _dynamodb_resource = boto3.resource(
            "dynamodb",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id="dummy",
            aws_secret_access_key="dummy",
        )
    else:
        logger.info(f"Connecting to AWS DynamoDB in region {region}")
        _dynamodb_resource = boto3.resource("dynamodb", region_name=region)
    
    return _dynamodb_resource


def get_schemas_table() -> Any:
    """
    Get a reference to the database schemas table.
    
    Returns:
        boto3.dynamodb.table.TableResource: The schemas table
    """
    return get_table(SCHEMAS_TABLE_NAME)


def get_table(table_name: str) -> Any:
    """
    Get a reference to a DynamoDB table, with caching.
    
    Args:
        table_name (str): The name of the table
        
    Returns:
        boto3.dynamodb.table.TableResource: The DynamoDB table
    """
    global _table_cache
    
    if table_name in _table_cache:
        return _table_cache[table_name]
    
    dynamodb = get_dynamodb_resource()
    table = dynamodb.Table(table_name)
    _table_cache[table_name] = table
    
    return table


def create_schemas_table(dynamodb: ServiceResource = None) -> Any:
    """
    Create the schemas table if it doesn't exist.
    
    Args:
        dynamodb (ServiceResource, optional): DynamoDB resource to use
        
    Returns:
        Table: The created or existing table
    """
    if dynamodb is None:
        dynamodb = get_dynamodb_resource()
    
    # Table definition constants (matching initialization script)
    key_schema = [
        {"AttributeName": "connection_id", "KeyType": "HASH"},
        {"AttributeName": "version", "KeyType": "RANGE"},
    ]
    attribute_defs = [
        {"AttributeName": "connection_id", "AttributeType": "S"},
        {"AttributeName": "version", "AttributeType": "S"},
    ]
    
    # Check if table exists
    existing_tables = [table.name for table in dynamodb.tables.all()]
    
    if SCHEMAS_TABLE_NAME not in existing_tables:
        logger.info(f"Creating table {SCHEMAS_TABLE_NAME}...")
        table = dynamodb.create_table(
            TableName=SCHEMAS_TABLE_NAME,
            KeySchema=key_schema,
            AttributeDefinitions=attribute_defs,
            BillingMode="PAY_PER_REQUEST",  # On-demand capacity
        )
        
        # Wait for table to be created
        table.meta.client.get_waiter("table_exists").wait(TableName=SCHEMAS_TABLE_NAME)
        logger.info(f"Table {SCHEMAS_TABLE_NAME} created successfully")
    else:
        logger.info(f"Table {SCHEMAS_TABLE_NAME} already exists")
        table = dynamodb.Table(SCHEMAS_TABLE_NAME)
    
    # Add to cache
    _table_cache[SCHEMAS_TABLE_NAME] = table
    
    return table
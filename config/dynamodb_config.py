"""
DynamoDB Configuration and Operations for Database Schema Management

This module provides functions and configurations for interacting with DynamoDB
to store and retrieve database connection details and schema information.
"""

import os
import uuid
from datetime import datetime

import boto3
from boto3.dynamodb.conditions import Attr, Key

# DynamoDB configuration
REGION = os.environ.get("AWS_REGION", "us-east-1")
DYNAMODB_TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "database_schemas")
DYNAMODB_ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT")  # Optional for local development


def get_dynamodb_resource():
    """
    Get a DynamoDB resource object based on configuration.

    Returns:
        boto3.resource: DynamoDB resource
    """
    if DYNAMODB_ENDPOINT:
        # For local development with DynamoDB local
        return boto3.resource("dynamodb", endpoint_url=DYNAMODB_ENDPOINT, region_name=REGION)
    else:
        # For production with AWS DynamoDB
        return boto3.resource("dynamodb", region_name=REGION)


def get_dynamodb_table():
    """
    Get the DynamoDB table for database schemas.

    Returns:
        boto3.dynamodb.table.Table: DynamoDB table resource
    """
    dynamodb = get_dynamodb_resource()
    return dynamodb.Table(DYNAMODB_TABLE_NAME)


def create_schemas_table():
    """
    Create the database schemas table if it doesn't exist.

    Returns:
        dict: Response from DynamoDB create_table operation
    """
    dynamodb = get_dynamodb_resource()

    # Check if table already exists
    existing_tables = dynamodb.meta.client.list_tables()["TableNames"]
    if DYNAMODB_TABLE_NAME in existing_tables:
        print(f"Table {DYNAMODB_TABLE_NAME} already exists.")
        return {"TableStatus": "ACTIVE", "TableName": DYNAMODB_TABLE_NAME}

    # Create table
    table = dynamodb.create_table(
        TableName=DYNAMODB_TABLE_NAME,
        KeySchema=[
            {"AttributeName": "connection_id", "KeyType": "HASH"},  # Partition key
            {"AttributeName": "version", "KeyType": "RANGE"},  # Sort key
        ],
        AttributeDefinitions=[
            {"AttributeName": "connection_id", "AttributeType": "S"},
            {"AttributeName": "version", "AttributeType": "S"},
        ],
        ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
    )

    # Wait for table to be created
    table.meta.client.get_waiter("table_exists").wait(TableName=DYNAMODB_TABLE_NAME)
    return table.meta.client.describe_table(TableName=DYNAMODB_TABLE_NAME)["Table"]


def store_database_schema(
    connection_info, schema_info, table_descriptions=None, connection_id=None
):
    """
    Store database connection and schema information in DynamoDB.

    Args:
        connection_info: Database connection details
        schema_info: The analyzed schema information
        table_descriptions: Optional descriptions of tables and their purposes
        connection_id: Optional existing connection ID for updates

    Returns:
        dict: Information about the stored record
    """
    table = get_dynamodb_table()

    # Create a new connection_id if not provided
    if not connection_id:
        connection_id = str(uuid.uuid4())

    # Generate version timestamp
    version = datetime.now().isoformat()

    # Ensure password is not stored directly in plaintext
    connection_info_safe = connection_info.copy()
    if "password" in connection_info_safe:
        connection_info_safe["password"] = "********"  # Redact password

    # Prepare the item for DynamoDB
    item = {
        "connection_id": connection_id,
        "version": version,
        "connection_name": connection_info.get(
            "name",
            f"{connection_info.get('host', 'unknown')}-{connection_info.get('database', 'db')}",
        ),
        "connection_info": connection_info_safe,
        "db_type": connection_info.get("db_type", "unknown"),
        "host": connection_info.get("host", "unknown"),
        "database_name": connection_info.get("database", "unknown"),
        "schema_info": schema_info,
        "created_at": version,
        "schema_stats": {
            "schema_count": len(schema_info),
            "total_tables": sum(len(tables) for tables in schema_info.values()),
        },
    }

    # Add table descriptions if provided
    if table_descriptions:
        item["table_descriptions"] = table_descriptions

    # Store in DynamoDB
    table.put_item(Item=item)

    return {
        "connection_id": connection_id,
        "version": version,
        "connection_name": item["connection_name"],
        "db_type": item["db_type"],
        "host": item["host"],
        "database_name": item["database_name"],
        "created_at": version,
        "schema_stats": item["schema_stats"],
    }


def get_database_schemas(connection_id=None, db_type=None, latest_only=True):
    """
    Retrieve database schema information from DynamoDB.

    Args:
        connection_id: Optional connection ID to filter results
        db_type: Optional database type to filter results
        latest_only: If True, return only the latest version of each connection

    Returns:
        list: List of schema records
    """
    table = get_dynamodb_table()

    if connection_id:
        # Get specific connection with all versions
        response = table.query(
            KeyConditionExpression=Key("connection_id").eq(connection_id),
            ScanIndexForward=False,  # Sort descending by version
        )

        items = response.get("Items", [])

        # If latest_only is True, return only the first item (latest version)
        if latest_only and items:
            return [items[0]]
        return items

    # If no connection_id, scan the table
    scan_kwargs = {}
    if db_type:
        scan_kwargs["FilterExpression"] = Attr("db_type").eq(db_type)

    response = table.scan(**scan_kwargs)
    items = response.get("Items", [])

    # If latest_only is True, group by connection_id and keep only the latest version
    if latest_only:
        # Group by connection_id
        grouped = {}
        for item in items:
            conn_id = item["connection_id"]
            if conn_id not in grouped or item["version"] > grouped[conn_id]["version"]:
                grouped[conn_id] = item

        # Return only the latest version of each connection
        return list(grouped.values())

    return items


def get_database_schema_by_id(connection_id, version=None):
    """
    Get a specific database schema by ID and optionally version.

    Args:
        connection_id: The connection ID
        version: Optional specific version to retrieve

    Returns:
        dict: The database schema record or None if not found
    """
    table = get_dynamodb_table()

    if version:
        # Get specific version
        response = table.get_item(Key={"connection_id": connection_id, "version": version})
        return response.get("Item")

    # Get latest version
    response = table.query(
        KeyConditionExpression=Key("connection_id").eq(connection_id),
        ScanIndexForward=False,  # Sort descending by version
        Limit=1,  # Get only the first (latest) item
    )

    items = response.get("Items", [])
    if items:
        return items[0]
    return None


def update_table_descriptions(connection_id, table_descriptions, version=None):
    """
    Update table descriptions for an existing database schema.

    Args:
        connection_id: The connection ID
        table_descriptions: Descriptions for tables and their purposes
        version: Optional specific version to update

    Returns:
        dict: Updated schema record
    """
    # Get the schema to update
    schema_record = get_database_schema_by_id(connection_id, version)
    if not schema_record:
        raise ValueError(f"Schema with connection_id {connection_id} not found")

    # Create a new version
    new_version = datetime.now().isoformat()

    # Copy the schema record with the new version
    new_record = schema_record.copy()
    new_record["version"] = new_version
    new_record["updated_at"] = new_version
    new_record["table_descriptions"] = table_descriptions

    # Store the updated record
    table = get_dynamodb_table()
    table.put_item(Item=new_record)

    return {
        "connection_id": connection_id,
        "version": new_version,
        "connection_name": new_record.get("connection_name"),
        "updated_at": new_version,
        "message": "Table descriptions updated successfully",
    }


def delete_database_schema(connection_id, version=None):
    """
    Delete a database schema from DynamoDB.

    Args:
        connection_id: The connection ID to delete
        version: Optional specific version to delete

    Returns:
        dict: Result of the delete operation
    """
    table = get_dynamodb_table()

    if version:
        # Delete specific version
        response = table.delete_item(
            Key={"connection_id": connection_id, "version": version}, ReturnValues="ALL_OLD"
        )
        deleted_item = response.get("Attributes")

        return {
            "connection_id": connection_id,
            "version": version,
            "deleted": True if deleted_item else False,
            "connection_name": deleted_item.get("connection_name") if deleted_item else None,
        }

    # Delete all versions of this connection_id
    # First get all versions
    versions = table.query(
        KeyConditionExpression=Key("connection_id").eq(connection_id),
        ProjectionExpression="version",
    ).get("Items", [])

    # Then delete each version
    for item in versions:
        table.delete_item(Key={"connection_id": connection_id, "version": item["version"]})

    return {"connection_id": connection_id, "deleted": True, "versions_deleted": len(versions)}


def initialize_dynamodb():
    """
    Initialize DynamoDB: ensure the table exists.

    Returns:
        dict: Status of the table
    """
    return create_schemas_table()


# Initialize on module import if needed
if __name__ == "__main__":
    table_info = initialize_dynamodb()
    print(f"DynamoDB table status: {table_info.get('TableStatus')}")

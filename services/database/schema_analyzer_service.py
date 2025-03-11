"""
Database Schema Service

This service handles extraction, storage, and retrieval of database schema information.
It provides methods to analyze database schemas and store them in DynamoDB for
use with LLMs to generate accurate SQL queries.
"""

import datetime
import json
import logging
from typing import Dict, List, Any, Optional, Union, Tuple

from botocore.exceptions import ClientError

# Database drivers
try:
    import psycopg2
    import psycopg2.extras
    POSTGRES_AVAILABLE = True
    logging.info("PostgreSQL driver (psycopg2) is available")
except ImportError:
    POSTGRES_AVAILABLE = False
    logging.error("PostgreSQL driver (psycopg2) is NOT available - please install it")
    
# Application imports
from config import get_schemas_table

# Configure logging
logger = logging.getLogger(__name__)


class SchemaAnalyzerService:
    """Service for managing database schema information."""
    
    def __init__(self):
        """Initialize the schema service."""
        logger.info("Initializing SchemaAnalyzerService")
        try:
            self.schema_table = get_schemas_table()
            logger.info(f"Successfully initialized DynamoDB schema table: {self.schema_table}")
        except Exception as e:
            logger.error(f"Failed to initialize DynamoDB schema table: {e}", exc_info=True)
            raise
    
    def save_schema(self, connection_id: str, schema_data: Dict[str, Any]) -> bool:
        """
        Save a database schema to DynamoDB.
        
        Args:
            connection_id (str): Unique identifier for the database connection
            schema_data (Dict[str, Any]): The schema information to store
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Saving schema for connection: {connection_id}")
        try:
            # Generate a version timestamp
            version = datetime.datetime.utcnow().isoformat()
            
            # Prepare the item to store
            item = {
                "connection_id": connection_id,
                "version": version,
                "schema": schema_data,
                "created_at": version
            }
            
            # Add metadata fields if provided
            if "db_type" in schema_data:
                item["db_type"] = schema_data["db_type"]
            if "db_name" in schema_data:
                item["db_name"] = schema_data["db_name"]
            
            logger.debug(f"Prepared DynamoDB item structure for {connection_id}")
            
            # Store in DynamoDB
            logger.info(f"Writing schema to DynamoDB for connection {connection_id}")
            self.schema_table.put_item(Item=item)
            logger.info(f"Successfully saved schema for connection {connection_id} version {version}")
            return True
            
        except ClientError as e:
            logger.error(f"DynamoDB ClientError saving schema: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Unexpected error saving schema: {e}", exc_info=True)
            return False
    
    def get_schema(self, connection_id: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieve a database schema from DynamoDB.
        
        Args:
            connection_id (str): Unique identifier for the database connection
            version (Optional[str]): Specific version to retrieve, latest if None
            
        Returns:
            Optional[Dict[str, Any]]: The schema data or None if not found
        """
        logger.info(f"Getting schema for connection: {connection_id}, version: {version if version else 'latest'}")
        try:
            if version:
                # Get specific version
                logger.info(f"Retrieving specific version {version} for connection {connection_id}")
                response = self.schema_table.get_item(
                    Key={"connection_id": connection_id, "version": version}
                )
                if "Item" in response:
                    logger.info(f"Found schema for connection {connection_id}, version {version}")
                    return response["Item"]
            else:
                # Get latest version (using query + sort)
                logger.info(f"Retrieving latest version for connection {connection_id}")
                response = self.schema_table.query(
                    KeyConditionExpression="connection_id = :id",
                    ExpressionAttributeValues={":id": connection_id},
                    ScanIndexForward=False,  # descending order (newest first)
                    Limit=1
                )
                if response["Items"]:
                    logger.info(f"Found latest schema for connection {connection_id}")
                    return response["Items"][0]
            
            logger.warning(f"No schema found for connection {connection_id}")
            return None
            
        except ClientError as e:
            logger.error(f"DynamoDB ClientError retrieving schema: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error retrieving schema: {e}", exc_info=True)
            return None
    
    def delete_schema(self, connection_id: str, version: Optional[str] = None) -> bool:
        """
        Delete a schema from DynamoDB.
        
        Args:
            connection_id (str): Unique identifier for the database connection
            version (Optional[str]): Specific version to delete, all versions if None
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Deleting schema for connection: {connection_id}, version: {version if version else 'all'}")
        try:
            if version:
                # Delete specific version
                logger.info(f"Deleting specific version {version} for connection {connection_id}")
                self.schema_table.delete_item(
                    Key={"connection_id": connection_id, "version": version}
                )
                logger.info(f"Successfully deleted schema for connection {connection_id} version {version}")
                return True
            else:
                # Delete all versions (query and batch delete)
                logger.info(f"Querying all versions for connection {connection_id} for deletion")
                response = self.schema_table.query(
                    KeyConditionExpression="connection_id = :id",
                    ExpressionAttributeValues={":id": connection_id},
                    ProjectionExpression="connection_id, version"
                )
                
                items = response.get("Items", [])
                if not items:
                    logger.warning(f"No schemas found for connection {connection_id}")
                    return False
                
                logger.info(f"Found {len(items)} schema versions to delete for connection {connection_id}")
                
                # Delete in batches (DynamoDB limits batch operations)
                batch_size = 25
                for i in range(0, len(items), batch_size):
                    batch = items[i:i+batch_size]
                    logger.info(f"Deleting batch of {len(batch)} items for connection {connection_id}")
                    
                    with self.schema_table.batch_writer() as batch_writer:
                        for item in batch:
                            batch_writer.delete_item(
                                Key={
                                    "connection_id": item["connection_id"],
                                    "version": item["version"]
                                }
                            )
                
                logger.info(f"Successfully deleted {len(items)} schema versions for connection {connection_id}")
                return True
                
        except ClientError as e:
            logger.error(f"DynamoDB ClientError deleting schema: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting schema: {e}", exc_info=True)
            return False
    
    def list_connections(self) -> List[Dict[str, Any]]:
        """
        List all database connections with their latest schema version.
        
        Returns:
            List[Dict[str, Any]]: List of connection information
        """
        logger.info("Listing all database connections with schema information")
        try:
            # Scan the table to get unique connection_ids
            logger.info("Scanning DynamoDB table for connections")
            response = self.schema_table.scan(
                ProjectionExpression="connection_id, db_name, db_type"
            )
            
            connections = {}
            for item in response.get("Items", []):
                connection_id = item["connection_id"]
                # Only keep one entry per connection_id
                if connection_id not in connections:
                    connections[connection_id] = {
                        "connection_id": connection_id,
                        "db_name": item.get("db_name", "Unknown"),
                        "db_type": item.get("db_type", "Unknown")
                    }
            
            logger.info(f"Found {len(connections)} unique database connections")
            return list(connections.values())
            
        except ClientError as e:
            logger.error(f"DynamoDB ClientError listing connections: {e}", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing connections: {e}", exc_info=True)
            return []
    
    def analyze_postgres_schema(
        self, connection_id: str, connection_params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze a PostgreSQL database and extract its schema information.
        """
        logger.info(f"Starting PostgreSQL schema analysis for connection: {connection_id}")
        
        # Debug output to verify parameters (mask the password in production)
        logger.debug(f"Connection parameters: host={connection_params.get('host')}, "
                    f"port={connection_params.get('port')}, "
                    f"user={connection_params.get('user')}, "
                    f"database={connection_params.get('database')}, "
                    f"password_provided={'Yes' if connection_params.get('password') else 'No'}")
        
        if not POSTGRES_AVAILABLE:
            logger.error("PostgreSQL driver (psycopg2) not available. Please install psycopg2.")
            return None
            
        # Validate required parameters
        required_params = ["host", "user", "password", "database"]
        for param in required_params:
            if param not in connection_params or not connection_params[param]:
                logger.error(f"Missing required connection parameter: {param}")
                return None
                
        conn = None
        try:
            if not connection_params.get("password"):
                logger.error(f"No password provided for PostgreSQL connection {connection_id}")
                return None
            
            # Connect to the database
            logger.info(f"Connecting to PostgreSQL database for {connection_id}")
            conn = psycopg2.connect(
                host=connection_params.get("host", "localhost"),
                port=connection_params.get("port", 5432),
                user=connection_params.get("user"),
                password=connection_params.get("password"),
                database=connection_params.get("database"),
            )
            logger.info(f"Successfully connected to PostgreSQL for {connection_id}")
            
            schema_info = {
                "tables": [],
                "relationships": [],
                "metadata": {
                    "created_at": datetime.datetime.utcnow().isoformat(),
                    "db_version": "",
                    "db_type": "postgres",
                    "db_name": connection_params.get("database", "")
                }
            }
            
            # Get database version
            logger.info("Retrieving PostgreSQL database version")
            with conn.cursor() as cursor:
                cursor.execute("SELECT version();")
                version = cursor.fetchone()[0]
                schema_info["metadata"]["db_version"] = version
                logger.info(f"PostgreSQL version: {version}")
            
            # Get tables
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # Get all tables in the public schema
                logger.info("Retrieving table list from public schema")
                cursor.execute("""
                    SELECT 
                        table_name 
                    FROM 
                        information_schema.tables 
                    WHERE 
                        table_schema = 'public' 
                        AND table_type = 'BASE TABLE'
                    ORDER BY table_name;
                """)
                
                tables = cursor.fetchall()
                logger.info(f"Found {len(tables)} tables in the public schema")
                
                # Process each table
                for table_row in tables:
                    table_name = table_row['table_name']
                    logger.info(f"Processing table: {table_name}")
                    
                    # Get table description from comments if available
                    try:
                        logger.debug(f"Retrieving description for table {table_name}")
                        cursor.execute("""
                            SELECT 
                                obj_description(pg_class.oid) as table_description
                            FROM pg_class
                            JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
                            WHERE pg_class.relname = %s
                                AND pg_namespace.nspname = 'public';
                        """, (table_name,))
                        
                        table_desc_row = cursor.fetchone()
                        table_description = table_desc_row['table_description'] if table_desc_row and table_desc_row['table_description'] else ""
                        logger.debug(f"Table {table_name} description: {table_description[:50]}{'...' if len(table_description) > 50 else ''}")
                    except Exception as e:
                        logger.warning(f"Error retrieving description for table {table_name}: {e}")
                        table_description = ""
                    
                    # Get columns for this table
                    try:
                        logger.debug(f"Retrieving columns for table {table_name}")
                        cursor.execute("""
                            SELECT 
                                column_name, 
                                data_type, 
                                is_nullable, 
                                column_default,
                                character_maximum_length,
                                numeric_precision,
                                numeric_scale
                            FROM 
                                information_schema.columns 
                            WHERE 
                                table_schema = 'public' 
                                AND table_name = %s
                            ORDER BY ordinal_position;
                        """, (table_name,))
                        
                        columns_data = cursor.fetchall()
                        logger.debug(f"Found {len(columns_data)} columns for table {table_name}")
                    except Exception as e:
                        logger.error(f"Error retrieving columns for table {table_name}: {e}", exc_info=True)
                        columns_data = []
                        
                    columns = []
                    
                    # Get primary key information
                    try:
                        logger.debug(f"Retrieving primary key info for table {table_name}")
                        cursor.execute("""
                            SELECT 
                                kcu.column_name
                            FROM information_schema.table_constraints AS tc
                            JOIN information_schema.key_column_usage AS kcu
                                ON tc.constraint_name = kcu.constraint_name
                                AND tc.table_schema = kcu.table_schema
                            WHERE tc.constraint_type = 'PRIMARY KEY'
                                AND tc.table_schema = 'public'
                                AND tc.table_name = %s
                            ORDER BY kcu.ordinal_position;
                        """, (table_name,))
                        
                        primary_keys = [row['column_name'] for row in cursor.fetchall()]
                        logger.debug(f"Primary keys for table {table_name}: {primary_keys}")
                    except Exception as e:
                        logger.error(f"Error retrieving primary keys for table {table_name}: {e}", exc_info=True)
                        primary_keys = []
                    
                    # Process each column
                    for col in columns_data:
                        col_name = col['column_name']
                        logger.debug(f"Processing column {col_name} in table {table_name}")
                        
                        # Get column description from comments if available
                        try:
                            cursor.execute("""
                                SELECT 
                                    pg_description.description
                                FROM pg_description
                                JOIN pg_class ON pg_description.objoid = pg_class.oid
                                JOIN pg_namespace ON pg_class.relnamespace = pg_namespace.oid
                                JOIN pg_attribute ON pg_attribute.attrelid = pg_class.oid
                                    AND pg_description.objsubid = pg_attribute.attnum
                                WHERE pg_class.relname = %s
                                    AND pg_namespace.nspname = 'public'
                                    AND pg_attribute.attname = %s;
                            """, (table_name, col_name))
                            
                            col_desc_row = cursor.fetchone()
                            column_description = col_desc_row['description'] if col_desc_row and 'description' in col_desc_row else ""
                        except Exception as e:
                            logger.warning(f"Error retrieving description for column {col_name}: {e}")
                            column_description = ""
                        
                        # Build full data type string
                        data_type = col['data_type']
                        if col['character_maximum_length'] is not None:
                            data_type += f"({col['character_maximum_length']})"
                        elif col['numeric_precision'] is not None and col['numeric_scale'] is not None:
                            data_type += f"({col['numeric_precision']},{col['numeric_scale']})"
                        
                        columns.append({
                            "column_name": col_name,
                            "data_type": data_type,
                            "is_nullable": col['is_nullable'] == 'YES',
                            "is_primary_key": col_name in primary_keys,
                            "default_value": col['column_default'],
                            "description": column_description
                        })
                    
                    # Add table to schema
                    schema_info["tables"].append({
                        "table_name": table_name,
                        "schema": "public",
                        "description": table_description,
                        "columns": columns
                    })
                
                # Get foreign key relationships
                logger.info("Retrieving foreign key relationships")
                try:
                    cursor.execute("""
                        SELECT
                            tc.table_name AS source_table,
                            kcu.column_name AS source_column,
                            ccu.table_name AS target_table,
                            ccu.column_name AS target_column,
                            tc.constraint_name
                        FROM information_schema.table_constraints AS tc
                        JOIN information_schema.key_column_usage AS kcu
                            ON tc.constraint_name = kcu.constraint_name
                            AND tc.table_schema = kcu.table_schema
                        JOIN information_schema.constraint_column_usage AS ccu
                            ON ccu.constraint_name = tc.constraint_name
                            AND ccu.table_schema = tc.table_schema
                        WHERE tc.constraint_type = 'FOREIGN KEY'
                            AND tc.table_schema = 'public';
                    """)
                    
                    relationships = cursor.fetchall()
                    logger.info(f"Found {len(relationships)} foreign key relationships")
                    
                    for rel in relationships:
                        schema_info["relationships"].append({
                            "source_table": rel["source_table"],
                            "source_column": rel["source_column"],
                            "target_table": rel["target_table"],
                            "target_column": rel["target_column"],
                            "constraint_name": rel["constraint_name"],
                            "relationship_type": "many-to-one"  # Assumed default
                        })
                except Exception as e:
                    logger.error(f"Error retrieving relationships: {e}", exc_info=True)
            
            # Save the schema to DynamoDB
            logger.info(f"Schema analysis complete for {connection_id}. Saving to DynamoDB.")
            logger.debug(f"Schema has {len(schema_info['tables'])} tables and {len(schema_info['relationships'])} relationships")
            
            if self.save_schema(connection_id, schema_info):
                logger.info(f"Successfully saved schema for {connection_id}")
                return schema_info
            else:
                logger.error(f"Failed to save schema for {connection_id}")
                return None
                
        except psycopg2.OperationalError as e:
            logger.error(f"PostgreSQL connection error: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Error analyzing PostgreSQL schema: {e}", exc_info=True)
            return None
            
        finally:
            # Close connection
            if conn:
                logger.info("Closing PostgreSQL connection")
                conn.close()
    
    def get_llm_context(self, connection_id: str) -> str:
        """
        Generate a context string for LLM prompt from the schema information.
        
        Args:
            connection_id (str): The database connection ID
            
        Returns:
            str: Context string for LLM prompt
        """
        logger.info(f"Generating LLM context for connection: {connection_id}")
        schema_data = self.get_schema(connection_id)
        if not schema_data or "schema" not in schema_data:
            logger.warning(f"No schema information available for connection {connection_id}")
            return "No schema information available for this database."
        
        logger.info(f"Building LLM context from schema for {connection_id}")
        schema = schema_data["schema"]
        
        # Build context string
        context = []
        
        # Database info
        db_name = schema["metadata"].get("db_name", "Database")
        db_type = schema["metadata"].get("db_type", "PostgreSQL")
        context.append(f"## Database: {db_name} ({db_type})")
        context.append("")
        
        # Tables
        context.append("## Tables")
        context.append("")
        
        for table in schema.get("tables", []):
            table_name = table["table_name"]
            description = table.get("description", "")
            
            if description:
                context.append(f"### {table_name}: {description}")
            else:
                context.append(f"### {table_name}")
            
            # Columns
            context.append("| Column | Type | Nullable | PK | Description |")
            context.append("|--------|------|----------|----| ----------- |")
            
            for column in table.get("columns", []):
                col_name = column["column_name"]
                data_type = column["data_type"]
                nullable = "Y" if column.get("is_nullable") else "N"
                pk = "PK" if column.get("is_primary_key") else ""
                description = column.get("description", "")
                
                context.append(f"| {col_name} | {data_type} | {nullable} | {pk} | {description} |")
            
            context.append("")
        
        # Relationships
        if schema.get("relationships"):
            context.append("## Relationships")
            context.append("")
            context.append("| Source Table | Source Column | Target Table | Target Column |")
            context.append("|-------------|---------------|-------------|---------------|")
            
            for rel in schema.get("relationships", []):
                source_table = rel["source_table"]
                source_column = rel["source_column"]
                target_table = rel["target_table"]
                target_column = rel["target_column"]
                
                context.append(f"| {source_table} | {source_column} | {target_table} | {target_column} |")
            
            context.append("")
        
        logger.info(f"LLM context generation complete for {connection_id}")
        return "\n".join(context)
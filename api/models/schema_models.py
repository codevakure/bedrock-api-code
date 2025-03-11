"""
Schema-related data models for the API
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DatabaseConnection(BaseModel):
    """Database connection parameters model"""

    host: str = Field(..., description="Database host address")
    port: int = Field(..., description="Database port")
    user: str = Field(..., description="Database username")
    password: str = Field(..., description="Database password", exclude=True)
    database: str = Field(..., description="Database name")


class SchemaRequest(BaseModel):
    """Request model for schema extraction"""

    connection_id: str = Field(..., description="Unique identifier for the database connection")
    connection_params: DatabaseConnection = Field(..., description="Database connection parameters")


class SchemaResponse(BaseModel):
    """Response model after schema extraction"""

    connection_id: str = Field(..., description="Database connection identifier")
    version: str = Field(..., description="Schema version (timestamp)")
    tables_count: int = Field(..., description="Number of tables in the schema")
    relationships_count: int = Field(..., description="Number of relationships in the schema")


class ColumnInfo(BaseModel):
    """Information about a database column"""

    column_name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool
    default_value: Optional[str] = None
    description: Optional[str] = None


class TableInfo(BaseModel):
    """Information about a database table"""

    table_name: str
    schema: str
    description: Optional[str] = None
    columns: List[ColumnInfo]


class RelationshipInfo(BaseModel):
    """Information about a relationship between tables"""

    source_table: str
    source_column: str
    target_table: str
    target_column: str
    constraint_name: Optional[str] = None
    relationship_type: str = "many-to-one"  # Default relationship type


class SchemaMetadata(BaseModel):
    """Metadata about the schema"""

    created_at: str
    db_version: Optional[str] = None
    db_type: str
    db_name: str


class SchemaInfo(BaseModel):
    """Complete schema information model"""

    tables: List[TableInfo]
    relationships: List[RelationshipInfo]
    metadata: SchemaMetadata


class SchemaDetailResponse(BaseModel):
    """Detailed schema information response"""

    connection_id: str
    version: str
    schema: SchemaInfo
    created_at: str


class ConnectionInfo(BaseModel):
    """Basic information about a database connection"""

    connection_id: str
    db_name: str
    db_type: str

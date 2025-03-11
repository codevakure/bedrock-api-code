"""
API routes for database schema extraction and management
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException

from api.models.schema_models import (
    SchemaRequest,
    SchemaResponse,
    ConnectionInfo,
    SchemaDetailResponse
)
from services.database.schema_analyzer_service import SchemaAnalyzerService

# Schema router
schema_router = APIRouter(prefix="/schema", tags=["Database Schema"])

schema_service = SchemaAnalyzerService()

@schema_router.post("", response_model=SchemaResponse)
async def extract_schema(request: SchemaRequest):
    """
    Extract and store database schema information from a PostgreSQL database
    """
    try:
        connection_params = {
            "host": request.connection_params.host,
            "port": request.connection_params.port,
            "user": request.connection_params.user,
            "password": request.connection_params.password,  # Explicitly get the password
            "database": request.connection_params.database
        }
        
        # Log for debugging (redact in production)
        print(f"Connection params: {connection_params}")
        
        # Extract schema using the service
        schema_info = schema_service.analyze_postgres_schema(
            request.connection_id, 
            connection_params
        )
        
        if not schema_info:
            raise HTTPException(status_code=500, detail="Failed to extract schema information")
            
        return {
            "connection_id": request.connection_id,
            "version": schema_info["metadata"]["created_at"],
            "tables_count": len(schema_info["tables"]),
            "relationships_count": len(schema_info["relationships"])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@schema_router.get("/connections", response_model=List[ConnectionInfo])
async def list_connections():
    """
    List all database connections with schema information
    """
    try:
        connections = schema_service.list_connections()
        return connections
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@schema_router.get("/{connection_id}", response_model=SchemaDetailResponse)
async def get_schema(connection_id: str, version: Optional[str] = None):
    """
    Get schema information for a specific database connection
    """
    try:
        schema = schema_service.get_schema(connection_id, version)
        if not schema:
            raise HTTPException(status_code=404, detail=f"Schema not found for connection {connection_id}")
        return schema
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@schema_router.delete("/{connection_id}")
async def delete_schema(connection_id: str, version: Optional[str] = None):
    """
    Delete schema information for a specific database connection
    """
    try:
        success = schema_service.delete_schema(connection_id, version)
        if not success:
            raise HTTPException(status_code=404, detail=f"Schema not found for connection {connection_id}")
        return {"message": f"Schema for connection {connection_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@schema_router.get("/{connection_id}/context")
async def get_schema_context(connection_id: str):
    """
    Get formatted schema context for LLM prompts
    """
    try:
        context = schema_service.get_llm_context(connection_id)
        return {"context": context}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
from fastapi import APIRouter, File, UploadFile, Query, Request
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Optional
from datetime import datetime
from api.models.models import QueryRequest
from services.document_service import DocumentService
from typing import List, Dict, Any
from fastapi import HTTPException
from services.query_service import QueryService
from api.models.models import GenerationSettings
from services.sync_service import SyncService
from services.knowledgebase_service import KnowledgebaseService
from services.knowledgebase_metrics import KnowledgebaseMetricsService
from api.routes.schema_routes import schema_router

# Parent router with a common prefix
api_router = APIRouter(prefix="/ai")

# Feature routers with updated prefixes
document_router = APIRouter(prefix="/documents", tags=["Documents"])
knowledgebase_router = APIRouter(prefix="/knowledgebase", tags=["knowledgebase"])
query_router = APIRouter(prefix="", tags=["Query"])
sync_router = APIRouter(prefix="/sync", tags=["Sync"])
health_router = APIRouter(prefix="/health", tags=["Health"])

# Document routes
@document_router.get("")
async def list_documents(
   request: Request,
   file_type: Optional[str] = Query(None, description="Filter by file type (e.g., 'pdf')")
):
   return await DocumentService.list_documents(file_type)

@document_router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
   return await DocumentService.upload_document(file)

@document_router.get("/{document_key}")
async def get_document(document_key: str):
   doc = await DocumentService.get_document(document_key)
   return StreamingResponse(
       iter([doc['content']]),
       media_type=doc['content_type'],
       headers={
           'Content-Disposition': f'attachment; filename="{document_key}"'
       }
   )

@document_router.get("/details/{document_key}")
async def get_document_details(document_key: str):
   return await DocumentService.get_document_details(document_key)

@document_router.delete("/{document_key}")
async def delete_document(document_key: str):
   return await DocumentService.delete_document(document_key)

# Query routes
@query_router.post("/query")
async def query(request: QueryRequest):
    return StreamingResponse(
        QueryService.stream_generate(
            request.prompt,
            request.document_id,
            request.settings,
            request.system_prompt,
            request.knowledge_base_id,
            request.model_arn
        ),
        #media_type="application/json"
        media_type="text/event-stream"
    )
    
@knowledgebase_router.get("/models")
async def list_models():
    """Get list of available Bedrock models for the knowledge base"""
    return await KnowledgebaseService.list_models()

@knowledgebase_router.get("/all")
def get_knowledge_bases():
    """
    Get list of all knowledge bases
    """
    try:
        # Call the service method directly (no await needed since it's synchronous)
        return KnowledgebaseService.list_knowledgebases()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@knowledgebase_router.get("/metrics")
def get_ai_metrics():
    """
    Get detailed AI service metrics including model-wise and monthly costs
    """
    try:
        metrics = KnowledgebaseMetricsService.get_ai_usage_metrics()
        return metrics
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch AI metrics: {str(e)}"
        )
 
# Sync routes
@sync_router.post("")
async def start_sync():
   return await SyncService.start_sync()

@sync_router.get("/status")
async def get_sync_status():
   return await SyncService.get_sync_status()

@sync_router.get("/debug/list-jobs")
async def list_all_jobs():
   return await SyncService.list_all_jobs()

# Health check route
@health_router.get("")
async def health_check():
   return JSONResponse({
       "status": "healthy",
       "service": "bedrock-api",
       "timestamp": datetime.now().isoformat()
   })


# Include all routers in parent router
api_router.include_router(document_router)
api_router.include_router(query_router)
api_router.include_router(sync_router)
api_router.include_router(health_router)
api_router.include_router(knowledgebase_router)
api_router.include_router(schema_router) 
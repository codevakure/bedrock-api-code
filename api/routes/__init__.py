# app/api/routes/__init__.py
from api.routes.routes import (
    document_router,
    query_router,
    sync_router,
    health_router,
    schema_router
)

from api.routes.schema_routes import (
    schema_router
)

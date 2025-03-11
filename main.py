from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.routes import api_router
from middleware.error_handler import aws_error_handler

app = FastAPI(
    title="Bedrock API",
    description="API for interacting with AWS Bedrock and Document Management",
    version="1.0.0",
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(aws_error_handler)

# Including routers
app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)

# uvicorn main:app --host=0.0.0.0 --port=5000

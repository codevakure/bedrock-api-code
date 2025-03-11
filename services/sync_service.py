from botocore.exceptions import ClientError
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from config.aws_config import DATA_SOURCE_ID, KNOWLEDGE_BASE_ID, bedrock_agent


class SyncService:
    @staticmethod
    async def start_sync():
        """Start knowledge base synchronization"""
        try:
            # Get data source
            data_sources = bedrock_agent.list_data_sources(knowledgeBaseId=KNOWLEDGE_BASE_ID)

            if not data_sources.get("dataSourceSummaries"):
                raise HTTPException(
                    status_code=404, detail="No data sources found for knowledge base"
                )

            data_source_id = data_sources["dataSourceSummaries"][0]["dataSourceId"]

            # Check for existing in-progress sync
            in_progress_jobs = bedrock_agent.list_ingestion_jobs(
                knowledgeBaseId=KNOWLEDGE_BASE_ID,
                dataSourceId=data_source_id,
                filters=[{"attribute": "STATUS", "operator": "EQ", "values": ["IN_PROGRESS"]}],
            )

            if in_progress_jobs.get("ingestionJobSummaries"):
                return JSONResponse(
                    {
                        "error": "Sync already in progress",
                        "job_id": in_progress_jobs["ingestionJobSummaries"][0]["ingestionJobId"],
                        "started_at": in_progress_jobs["ingestionJobSummaries"][0][
                            "startedAt"
                        ].isoformat(),
                    },
                    status_code=409,
                )

            # Start new sync
            new_job = bedrock_agent.start_ingestion_job(
                knowledgeBaseId=KNOWLEDGE_BASE_ID, dataSourceId=data_source_id
            )

            return JSONResponse(
                {
                    "message": "Sync started successfully",
                    "job_id": new_job["ingestionJob"]["ingestionJobId"],
                    "started_at": new_job["ingestionJob"]["startedAt"].isoformat(),
                }
            )

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"]["Message"]

            if error_code == "ThrottlingException":
                return JSONResponse(
                    {
                        "error": "Rate limit exceeded. Please try again later.",
                        "details": error_message,
                    },
                    status_code=429,
                )
            elif error_code == "ValidationException":
                return JSONResponse(
                    {"error": "Invalid request", "details": error_message}, status_code=400
                )
            else:
                print(f"AWS Error in start_sync: {error_code} - {error_message}")
                raise HTTPException(status_code=500, detail=str(e))

        except Exception as e:
            print(f"Unexpected error in start_sync: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @staticmethod
    async def get_sync_status():
        """Get current sync status"""
        try:
            data_sources = bedrock_agent.list_data_sources(knowledgeBaseId=KNOWLEDGE_BASE_ID)

            if "dataSourceSummaries" in data_sources and data_sources["dataSourceSummaries"]:
                data_source_id = data_sources["dataSourceSummaries"][0]["dataSourceId"]

                # First check for any in-progress jobs
                in_progress_jobs = bedrock_agent.list_ingestion_jobs(
                    knowledgeBaseId=KNOWLEDGE_BASE_ID,
                    dataSourceId=data_source_id,
                    filters=[{"attribute": "STATUS", "operator": "EQ", "values": ["IN_PROGRESS"]}],
                )

                # If there's an in-progress job, return its status
                if (
                    "ingestionJobSummaries" in in_progress_jobs
                    and in_progress_jobs["ingestionJobSummaries"]
                ):
                    in_progress_job = in_progress_jobs["ingestionJobSummaries"][0]
                    # Convert UTC to local timezone
                    local_start = in_progress_job["startedAt"].astimezone()
                    return JSONResponse(
                        {
                            "is_syncing": True,
                            "status": "In Progress",
                            "last_sync_start": local_start.isoformat(),
                            "last_sync_complete": None,
                            "error_message": None,
                        }
                    )

                # If no in-progress job, get the latest completed job
                latest_jobs = bedrock_agent.list_ingestion_jobs(
                    knowledgeBaseId=KNOWLEDGE_BASE_ID,
                    dataSourceId=data_source_id,
                    sortBy={"attribute": "STARTED_AT", "order": "DESCENDING"},
                    maxResults=1,
                )

                if "ingestionJobSummaries" in latest_jobs and latest_jobs["ingestionJobSummaries"]:
                    latest_job = latest_jobs["ingestionJobSummaries"][0]

                    # Convert UTC to local timezone
                    local_start = latest_job["startedAt"].astimezone()
                    local_complete = latest_job["updatedAt"].astimezone()
                    return JSONResponse(
                        {
                            "is_syncing": False,
                            "status": (
                                "Completed"
                                if latest_job["status"] == "COMPLETE"
                                else latest_job["status"]
                            ),
                            "last_sync_start": local_start.isoformat(),
                            "last_sync_complete": local_complete.isoformat(),
                            "error_message": (
                                None
                                if latest_job["status"] == "COMPLETE"
                                else f"Sync failed with status: {latest_job['status']}"
                            ),
                        }
                    )

                # If no jobs found, return default sync status
                return JSONResponse(
                    {
                        "is_syncing": False,
                        "status": "No sync jobs found",
                        "last_sync_start": None,
                        "last_sync_complete": None,
                        "error_message": None,
                    }
                )

            return JSONResponse(
                {
                    "is_syncing": False,
                    "status": "No data sources found",
                    "last_sync_start": None,
                    "last_sync_complete": None,
                    "error_message": None,
                }
            )

        except Exception as e:
            print(f"Error in get_sync_status: {e}")
            return JSONResponse(
                {
                    "is_syncing": False,
                    "status": "Error",
                    "last_sync_start": None,
                    "last_sync_complete": None,
                    "error_message": str(e),
                }
            )

    @staticmethod
    async def list_all_jobs():
        """List all ingestion jobs (debug endpoint)"""
        try:
            response = bedrock_agent.list_ingestion_jobs(
                knowledgeBaseId=KNOWLEDGE_BASE_ID, dataSourceId=DATA_SOURCE_ID
            )
            return JSONResponse(response)
        except Exception as e:
            return JSONResponse({"error": str(e)})

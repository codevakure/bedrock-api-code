import re
from datetime import datetime, timedelta
from typing import Dict, Optional

from api.models.kb_model_config import KBModelConfigs
from config.aws_config import bedrock_agent, bedrock_client


class KnowledgebaseService:
    @staticmethod
    async def list_models():
        """Get list of available Bedrock models for the knowledge base"""
        try:
            # 1. Get models from AWS Bedrock
            response = bedrock_client.list_foundation_models()

            # 2. Dictionary to track unique models
            unique_models = {}

            # 3. Process each model from the response
            for model in response.get("modelSummaries", []):
                model_arn = model["modelArn"]

                # 4. Extract base ARN and token count
                base_arn_match = re.match(r"(.+?:\d+):(\d+[kKmM]?)$", model_arn)
                if base_arn_match:
                    base_arn = base_arn_match.group(1)
                    token_count = base_arn_match.group(2)
                else:
                    base_arn = model_arn
                    token_count = ""

                # 5. Extract and format model name
                match = re.search(r"foundation-model/([a-zA-Z0-9\-\.]+)", base_arn)
                model_name = match.group(1) if match else "Unknown"
                model_prefix = model_name.split(".")[0] if model_name != "Unknown" else "Unknown"
                formatted_name = model_name.replace("-", " ").replace(".", " ").title()

                # 6. Create base model info dictionary
                model_info = {
                    "model_arn": base_arn,
                    "model_max_token": token_count,
                    "model_name": formatted_name,
                    "model": model_prefix.capitalize(),
                    "description": model.get("modelDescription", ""),
                }

                # 7. Check if we've seen this base model before
                if base_arn not in unique_models:
                    # 8. Enrich with config and pricing using KBModelConfigs
                    enriched_model = KBModelConfigs.enrich_model_info(model_info)
                    unique_models[base_arn] = enriched_model

            # 9. Return final results
            return {"models": list(unique_models.values())}

        except Exception as e:
            print(f"Error in list_models: {str(e)}")
            raise

    @staticmethod
    def list_knowledgebases(
        max_results: int = 10, next_token: Optional[str] = None, status_filter: str = "ACTIVE"
    ) -> Dict:
        """
        Get a list of active knowledge bases with mapped fields.
        """
        try:
            # Prepare parameters for listing knowledge bases
            list_params = {"maxResults": max_results}
            if next_token:
                list_params["nextToken"] = next_token

            # Fetch list of knowledge bases
            response = bedrock_agent.list_knowledge_bases(**list_params)
            print(f"List knowledge bases response: {response}")

            knowledgebases = []

            # Iterate through knowledge bases
            for kb in response.get("knowledgeBaseSummaries", []):
                if status_filter and kb.get("status") != status_filter:
                    continue

                kb_id = kb.get("knowledgeBaseId")
                print(f"Processing knowledge base: {kb_id}")

                # Fetch detailed knowledge base information
                try:
                    kb_detail_response = bedrock_agent.get_knowledge_base(knowledgeBaseId=kb_id)
                    kb_detail = kb_detail_response.get("knowledgeBase", {})
                    print(f"Details for KB {kb_id}: {kb_detail}")
                except Exception as e:
                    print(f"Error getting details for KB {kb_id}: {str(e)}")
                    kb_detail = {}

                # Extract necessary fields
                storage_config = kb_detail.get("storageConfiguration", {})
                vector_field = (
                    storage_config.get("opensearchServerlessConfiguration", {})
                    .get("fieldMapping", {})
                    .get("vectorField")
                )
                description_field = (
                    storage_config.get("opensearchServerlessConfiguration", {})
                    .get("fieldMapping", {})
                    .get("metadataField")
                )

                # Fetch data sources using `list_data_sources`
                data_sources = []
                try:
                    data_sources_response = bedrock_agent.list_data_sources(knowledgeBaseId=kb_id)
                    print(f"Data sources response for KB {kb_id}: {data_sources_response}")

                    for ds in data_sources_response.get("dataSourceSummaries", []):
                        data_sources.append(
                            {
                                "data_source_id": ds.get("dataSourceId"),
                                "knowledge_base_id": ds.get("knowledgeBaseId"),
                                "name": ds.get("name"),
                                "description": ds.get("description"),
                                "status": ds.get("status"),
                                "last_updated": (
                                    ds.get("updatedAt").isoformat() if ds.get("updatedAt") else None
                                ),
                            }
                        )
                except Exception as e:
                    print(f"Error getting data sources for KB {kb_id}: {str(e)}")

                # Construct knowledge base info
                kb_info = {
                    "knowledge_base_id": kb_id,
                    "name": kb.get("name"),
                    "description": kb_detail.get("description"),
                    "status": kb.get("status"),
                    "creation_time": (
                        kb_detail.get("createdAt").isoformat()
                        if kb_detail.get("createdAt")
                        else None
                    ),
                    "last_updated_time": (
                        kb.get("updatedAt").isoformat() if kb.get("updatedAt") else None
                    ),
                    "storage_capacity": kb_detail.get("storageConfiguration"),
                    "data_source_count": len(data_sources),
                    "vector_field": vector_field,
                    "description_field": description_field,
                    "data_sources": data_sources,
                }

                knowledgebases.append(kb_info)

            # Prepare final result
            result = {
                "knowledgebases": knowledgebases,
                "total_count": len(knowledgebases),
            }

            if "nextToken" in response:
                result["next_token"] = response["nextToken"]

            return result

        except Exception as e:
            print(f"Error in list_knowledgebases: {str(e)}")
            raise

    @staticmethod
    def get_usage_stats(kb_id: str) -> Dict:
        """
        Get detailed usage statistics for a knowledgebase.

        Args:
            kb_id (str): Knowledgebase ID

        Returns:
            Dict containing usage statistics
        """
        try:
            # Get metrics for the last 24 hours
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=1)

            # Get knowledge base details
            kb_details = bedrock_agent.get_knowledge_base(knowledgeBaseId=kb_id)

            # Get associated data sources
            data_sources = bedrock_agent.list_knowledge_base_data_sources(knowledgeBaseId=kb_id)

            return {
                "status": kb_details.get("status"),
                "data_sources": len(data_sources.get("dataSourceSummaries", [])),
                "last_updated": kb_details.get("lastUpdatedTime"),
                "storage": {
                    "capacity": kb_details.get("storageCapacity"),
                    "used": kb_details.get("storageUsed", 0),
                },
                "time_period": "24h",
                "retrieved_at": end_time.isoformat(),
            }

        except Exception as e:
            print(f"Error getting Bedrock metrics: {str(e)}")
            return {
                "status": "ERROR",
                "error": str(e),
                "data_sources": 0,
                "last_updated": None,
                "storage": {"capacity": 0, "used": 0},
                "time_period": "24h",
                "retrieved_at": datetime.utcnow().isoformat(),
            }

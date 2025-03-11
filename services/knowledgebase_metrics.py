import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Set

import boto3
from dateutil.relativedelta import relativedelta

from config.aws_config import cloudwatch_client
from config.logging_config import logging


class KnowledgebaseMetricsService:
    @staticmethod
    def get_ai_usage_metrics() -> Dict:
        """Get detailed AI service usage metrics with dynamic model detection"""
        try:
            ce_client = boto3.client("ce")

            end_date = datetime.utcnow().strftime("%Y-%m-%d")
            start_date = (
                (datetime.utcnow() - relativedelta(months=12)).replace(day=1).strftime("%Y-%m-%d")
            )

            logging.info(f"Fetching AI costs from {start_date} to {end_date}")

            # Get costs for all services first
            response = ce_client.get_cost_and_usage(
                TimePeriod={"Start": start_date, "End": end_date},
                Granularity="MONTHLY",
                Metrics=["UnblendedCost", "UsageQuantity"],
                GroupBy=[
                    {"Type": "DIMENSION", "Key": "SERVICE"},
                    {"Type": "DIMENSION", "Key": "USAGE_TYPE"},
                ],
            )

            processed_data = KnowledgebaseMetricsService._process_ai_costs(response)

            return {
                "status": "success",
                "data": processed_data,
                "time_range": {"start": start_date, "end": end_date},
            }

        except Exception as e:
            logging.error(f"Error getting AI metrics: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "time_range": {"start": start_date, "end": end_date},
            }

    @staticmethod
    def _is_ai_service(service: str) -> bool:
        """Check if a service is an AI/ML service"""
        ai_service_keywords = [
            "bedrock",
            "claude",
            "sagemaker",
            "rekognition",
            "comprehend",
            "textract",
            "transcribe",
            "polly",
            "forecast",
            "personalize",
            "lex",
            "deeplearning",
        ]
        return any(keyword in service.lower() for keyword in ai_service_keywords)

    @staticmethod
    def _extract_model_info(usage_type: str, service: str) -> Dict:
        """Extract model name and token type from usage type"""
        model_info = {"model_name": None, "token_type": None, "region": None}

        # Extract region if present
        region_match = re.match(r"([A-Z]+\d+)-", usage_type)
        if region_match:
            model_info["region"] = region_match.group(1)
            usage_type = usage_type[len(region_match.group(0)) :]

        # Bedrock models
        if "Bedrock" in service:
            # Handle Titan models
            if "Titan" in usage_type:
                if "EmbeddingV2" in usage_type:
                    model_info["model_name"] = "Titan-Embedding-v2"
                elif "Text-Premier" in usage_type:
                    model_info["model_name"] = "Titan-Text-Premier"
            # Handle Claude models
            elif "Claude" in usage_type:
                if "Claude-3" in usage_type:
                    model_info["model_name"] = usage_type.split("-")[0]
                else:
                    model_info["model_name"] = "Claude"

            # Determine token type
            if "input" in usage_type.lower():
                model_info["token_type"] = "input"
            elif "output" in usage_type.lower():
                model_info["token_type"] = "output"

        # Claude service
        elif "Claude" in service:
            model_info["model_name"] = service.replace(" (Amazon Bedrock Edition)", "")
            if "InputTokenCount" in usage_type:
                model_info["token_type"] = "input"
            elif "OutputTokenCount" in usage_type:
                model_info["token_type"] = "output"

        # SageMaker
        elif "SageMaker" in service:
            if "Canvas" in usage_type:
                model_info["model_name"] = "SageMaker-Canvas"
            elif "Studio" in usage_type:
                model_info["model_name"] = "SageMaker-Studio"
            else:
                model_info["model_name"] = "SageMaker-Other"

        return model_info

    @staticmethod
    def _process_ai_costs(response: Dict) -> Dict:
        """Process AI services cost data with dynamic model detection"""

        # Initialize data structures
        model_costs = defaultdict(
            lambda: {
                "total_cost": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "regions": defaultdict(float),
                "usage_types": defaultdict(float),
            }
        )

        monthly_costs = defaultdict(
            lambda: {
                "total_cost": 0.0,
                "models": defaultdict(float),
                "services": defaultdict(float),
            }
        )

        total_metrics = {
            "total_cost": 0.0,
            "services": defaultdict(float),
            "models": defaultdict(float),
            "regions": defaultdict(float),
        }

        # Process each time period
        for time_period in response.get("ResultsByTime", []):
            month = time_period["TimePeriod"]["Start"][:7]  # YYYY-MM format

            for group in time_period.get("Groups", []):
                service, usage_type = group["Keys"]

                # Skip if not an AI service
                if not KnowledgebaseMetricsService._is_ai_service(service):
                    continue

                metrics = group["Metrics"]
                cost = float(metrics["UnblendedCost"]["Amount"])
                usage = float(metrics["UsageQuantity"]["Amount"])

                # Skip if no cost and no usage
                if cost == 0 and usage == 0:
                    continue

                # Extract model information
                model_info = KnowledgebaseMetricsService._extract_model_info(usage_type, service)
                model_name = model_info["model_name"]
                token_type = model_info["token_type"]
                region = model_info["region"]

                # If no specific model identified, use service name
                if not model_name:
                    model_name = service.replace("Amazon ", "")

                # Update monthly costs
                monthly_costs[month]["total_cost"] += cost
                monthly_costs[month]["services"][service] += cost
                monthly_costs[month]["models"][model_name] += cost

                # Update total metrics
                total_metrics["total_cost"] += cost
                total_metrics["services"][service] += cost
                total_metrics["models"][model_name] += cost
                if region:
                    total_metrics["regions"][region] += cost

                # Update model-specific metrics
                model_costs[model_name]["total_cost"] += cost
                if region:
                    model_costs[model_name]["regions"][region] += cost
                model_costs[model_name]["usage_types"][usage_type] = usage

                # Track token usage if applicable
                if token_type == "input":
                    model_costs[model_name]["input_tokens"] += usage
                elif token_type == "output":
                    model_costs[model_name]["output_tokens"] += usage

                model_costs[model_name]["total_tokens"] = (
                    model_costs[model_name]["input_tokens"]
                    + model_costs[model_name]["output_tokens"]
                )

        # Calculate percentages
        total_cost = total_metrics["total_cost"]
        if total_cost > 0:
            for service in total_metrics["services"]:
                service_cost = total_metrics["services"][service]
                total_metrics["services"][service] = {
                    "cost": round(service_cost, 4),
                    "percentage": round((service_cost / total_cost) * 100, 2),
                }

            for model in total_metrics["models"]:
                model_cost = total_metrics["models"][model]
                total_metrics["models"][model] = {
                    "cost": round(model_cost, 4),
                    "percentage": round((model_cost / total_cost) * 100, 2),
                }

            for region in total_metrics["regions"]:
                region_cost = total_metrics["regions"][region]
                total_metrics["regions"][region] = {
                    "cost": round(region_cost, 4),
                    "percentage": round((region_cost / total_cost) * 100, 2),
                }

        # Sort monthly data
        monthly_costs = dict(sorted(monthly_costs.items()))

        return {"total": total_metrics, "monthly": monthly_costs, "models": model_costs}

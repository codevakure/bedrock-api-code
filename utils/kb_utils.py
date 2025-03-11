import json
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import HTTPException

from api.models.kb_model_config import (
    KBModelConfig,
    KBModelConfigs,
    ModelFamilyMapper,
    ModelProvider,
)
from api.models.models import GenerationSettings
from config.logging_config import logger


class KBUtils:
    @staticmethod
    def _prepare_request_body(prompt: str, settings: GenerationSettings, model_arn: str) -> Dict:
        """Prepare request body based on model provider"""
        try:
            # Get model configuration
            model_config = KBModelConfigs.get_config(model_arn)

            # Update config with request settings if provided
            if settings:
                model_config.update_from_settings(settings)

            # Format request based on provider
            if model_config.provider == ModelProvider.ANTHROPIC:
                return {
                    "anthropic_version": "bedrock-2023-05-31",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": model_config.temperature,
                    "top_p": model_config.top_p,
                    "top_k": model_config.top_k,
                    "max_tokens": model_config.max_tokens,
                    "stop_sequences": model_config.stop_sequences,
                }
            elif model_config.provider == ModelProvider.META:
                return {
                    "prompt": prompt,
                    "temperature": model_config.temperature,
                    "top_p": model_config.top_p,
                    "max_tokens": model_config.max_tokens,
                    "stop_sequences": model_config.stop_sequences,
                }
            elif model_config.provider == ModelProvider.COHERE:
                return {
                    "message": prompt,
                    "temperature": model_config.temperature,
                    "p": model_config.top_p,
                    "k": model_config.top_k,
                    "max_tokens": model_config.max_tokens,
                    "stop_sequences": model_config.stop_sequences,
                }
            elif model_config.provider == ModelProvider.MISTRAL:
                return {
                    "inputs": prompt,
                    "parameters": {
                        "temperature": model_config.temperature,
                        "top_p": model_config.top_p,
                        "max_tokens": model_config.max_tokens,
                        "stop": model_config.stop_sequences,
                    },
                }
            elif model_config.provider == ModelProvider.AMAZON:
                # Handle different Amazon models (Nova vs Titan)
                model_family = ModelFamilyMapper.get_family(model_config.model_id)

                if "nova" in model_family:
                    return {
                        "messages": [{"role": "user", "content": [{"text": prompt}]}],
                        "temperature": model_config.temperature,
                        "top_p": model_config.top_p,
                        "max_tokens": model_config.max_tokens,
                        "stop": model_config.stop_sequences,
                    }
                else:  # Titan models
                    return {
                        "inputText": prompt,
                        "textGenerationConfig": {
                            "maxTokenCount": model_config.max_tokens,
                            "temperature": model_config.temperature,
                            "topP": model_config.top_p,
                            "topK": model_config.top_k,
                            "stopSequences": model_config.stop_sequences,
                        },
                    }
            else:
                # Default format for unknown providers
                return {
                    "prompt": prompt,
                    "temperature": model_config.temperature,
                    "top_p": model_config.top_p,
                    "top_k": model_config.top_k,
                    "max_tokens": model_config.max_tokens,
                    "stop_sequences": model_config.stop_sequences,
                }

        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error preparing request: {str(e)}")

    @staticmethod
    def _extract_generated_text(response_body: Dict, model_config: KBModelConfig) -> str:
        """Extract generated text from response based on model provider"""
        try:
            if model_config.provider == ModelProvider.ANTHROPIC:
                return response_body["content"][0]["text"]
            elif model_config.provider == ModelProvider.META:
                return response_body.get("generation", "")
            elif model_config.provider == ModelProvider.COHERE:
                return response_body.get("text", "")
            elif model_config.provider == ModelProvider.AMAZON:
                model_family = ModelFamilyMapper.get_family(model_config.model_id)
                if "nova" in model_family:
                    message = response_body["output"].get("message", {})
                    content = message.get("content", [])
                    return content[0]["text"] if content else ""
                else:  # Titan
                    return response_body.get("results", [{}])[0].get("outputText", "")
            elif model_config.provider == ModelProvider.MISTRAL:
                if "outputs" in response_body and response_body["outputs"]:
                    return response_body["outputs"][0].get("text", "").strip()
                return ""
            else:
                return response_body.get("completion", "")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error extracting response: {str(e)}")

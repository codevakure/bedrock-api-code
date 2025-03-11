from decimal import ROUND_HALF_UP, Decimal
from typing import Dict

from api.models.kb_model_config import KBModelConfigs, ModelProvider
from config.logging_config import logger


class KBCostMetrics:
    # Default pricing if model config not found ($ per 1000 tokens)
    DEFAULT_INPUT_COST = KBModelConfigs.DEFAULT_CONFIG.pricing.input_cost  # $0.0001 per 1K tokens
    DEFAULT_OUTPUT_COST = KBModelConfigs.DEFAULT_CONFIG.pricing.output_cost  # $0.0003 per 1K tokens

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Rough estimate of token count based on text length."""
        if not text:
            return 1
        # A rough estimate - assume 4 characters per token on average
        return max(1, len(text) // 4)

    @staticmethod
    def calculate_chunk_costs(chunks: list, model: str = None) -> Dict[str, str]:
        """Calculate costs from a list of text chunks."""
        total_input_tokens = 0
        total_output_tokens = 0

        # First pass: collect all text to get total input tokens
        all_text = ""
        for chunk in chunks:
            if isinstance(chunk, dict):
                chunk_text = chunk.get("chunk", "")
                all_text += chunk_text

                # If it's the final chunk with metadata
                if chunk.get("is_final") and "metadata" in chunk:
                    metadata = chunk.get("metadata", {})
                    cost_metrics = metadata.get("cost_metrics", {})

                    # If there are existing non-zero costs, use those
                    if any(float(cost.strip("$")) > 0 for cost in cost_metrics.values()):
                        return cost_metrics

        # Calculate input tokens from total text
        total_input_tokens = KBCostMetrics.estimate_tokens(all_text)

        # Ensure minimum token count of 1 if total_input_tokens is 0
        if total_input_tokens == 0:
            total_input_tokens = 1

        # Calculate output tokens as a proportion of input tokens
        # Assuming output is typically around 70% of input size for this type of content
        total_output_tokens = max(1, int(total_input_tokens * 0.7))

        # Calculate costs using default pricing
        input_cost = (total_input_tokens / 1000) * KBCostMetrics.DEFAULT_INPUT_COST
        output_cost = (total_output_tokens / 1000) * KBCostMetrics.DEFAULT_OUTPUT_COST
        total_cost = input_cost + output_cost

        # Ensure minimum cost is not zero
        if total_cost < 0.000001:
            input_cost = 0.000001  # Set to a small non-zero value if costs are too low
            output_cost = 0.000001
            total_cost = input_cost + output_cost

        # Format costs
        def format_cost(value: float) -> str:
            decimal_value = Decimal(str(value)).quantize(
                Decimal("0.000000"), rounding=ROUND_HALF_UP
            )
            return f"${decimal_value:,.6f}"

        costs = {
            "input_cost": format_cost(input_cost),
            "output_cost": format_cost(output_cost),
            "total_cost": format_cost(total_cost),
        }

        logger.debug(
            f"Calculated costs for chunks - Input tokens: {total_input_tokens}, Output tokens: {total_output_tokens}"
        )
        return costs

    @staticmethod
    def calculate_cost(
        model: str = None, input_tokens: int = 0, output_tokens: int = 0
    ) -> Dict[str, str]:
        """Calculate cost based on model pricing and token usage in dollars."""
        # Ensure minimum token counts
        input_tokens = max(1, int(input_tokens))
        output_tokens = max(1, int(output_tokens))

        # Use default pricing
        input_price = KBCostMetrics.DEFAULT_INPUT_COST
        output_price = KBCostMetrics.DEFAULT_OUTPUT_COST

        if model:
            try:
                model_config = KBModelConfigs.get_config(model)
                if model_config and model_config.pricing:
                    input_price = model_config.pricing.input_cost
                    output_price = model_config.pricing.output_cost
            except Exception as e:
                logger.warning(f"Error getting model config, using default pricing: {str(e)}")

        # Calculate costs
        input_cost = (input_tokens / 1000) * input_price
        output_cost = (output_tokens / 1000) * output_price
        total_cost = input_cost + output_cost

        # Ensure minimum cost is not zero
        if total_cost < 0.000001:
            input_cost = 0.000001
            output_cost = 0.000001
            total_cost = input_cost + output_cost

        def format_cost(value: float) -> str:
            decimal_value = Decimal(str(value)).quantize(
                Decimal("0.000000"), rounding=ROUND_HALF_UP
            )
            return f"${decimal_value:,.6f}"

        return {
            "input_cost": format_cost(input_cost),
            "output_cost": format_cost(output_cost),
            "total_cost": format_cost(total_cost),
        }

    @staticmethod
    def get_token_usage(
        response_body: Dict, provider: str = None, model: str = None
    ) -> Dict[str, int]:
        """Extract token usage from response based on provider."""
        usage = {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}  # Minimum values

        if not response_body:
            return usage

        try:
            # Convert provider string to ModelProvider enum if possible
            provider_enum = ModelProvider.UNKNOWN
            if provider:
                try:
                    provider_enum = ModelProvider(provider.lower())
                except ValueError:
                    pass

            # Print debug info about the response structure
            print(
                f"DEBUG - Response structure keys: {list(response_body.keys() if isinstance(response_body, dict) else [])}"
            )

            # Handle Bedrock's retrieve_and_generate API response
            if provider_enum == ModelProvider.AMAZON or (
                isinstance(provider, str) and "amazon" in provider.lower()
            ):
                # The Bedrock retrieve_and_generate API might have a different structure

                # Check for metrics in retrieveAndGenerateResponse (for newer API versions)
                if "retrieveAndGenerateResponse" in response_body and isinstance(
                    response_body["retrieveAndGenerateResponse"], dict
                ):
                    metrics = response_body["retrieveAndGenerateResponse"].get("metrics", {})

                    if isinstance(metrics, dict):
                        if "promptTokenCount" in metrics and "completionTokenCount" in metrics:
                            usage["input_tokens"] = max(1, metrics.get("promptTokenCount", 1))
                            usage["output_tokens"] = max(1, metrics.get("completionTokenCount", 1))
                            print(
                                f"DEBUG - Found token usage in retrieveAndGenerateResponse.metrics: {usage}"
                            )
                            return usage

                # Check for usage directly in the response
                if "usage" in response_body and isinstance(response_body["usage"], dict):
                    if (
                        "inputTokens" in response_body["usage"]
                        and "outputTokens" in response_body["usage"]
                    ):
                        usage["input_tokens"] = max(1, response_body["usage"].get("inputTokens", 1))
                        usage["output_tokens"] = max(
                            1, response_body["usage"].get("outputTokens", 1)
                        )
                        print(
                            f"DEBUG - Found token usage in usage (inputTokens/outputTokens): {usage}"
                        )
                        return usage

                    if (
                        "prompt_tokens" in response_body["usage"]
                        and "completion_tokens" in response_body["usage"]
                    ):
                        usage["input_tokens"] = max(
                            1, response_body["usage"].get("prompt_tokens", 1)
                        )
                        usage["output_tokens"] = max(
                            1, response_body["usage"].get("completion_tokens", 1)
                        )
                        print(
                            f"DEBUG - Found token usage in usage (prompt_tokens/completion_tokens): {usage}"
                        )
                        return usage

                # Check for responseMetadata
                if "responseMetadata" in response_body and isinstance(
                    response_body["responseMetadata"], dict
                ):
                    if "tokenUsage" in response_body["responseMetadata"]:
                        token_usage = response_body["responseMetadata"]["tokenUsage"]
                        if isinstance(token_usage, dict):
                            if "promptTokens" in token_usage and "completionTokens" in token_usage:
                                usage["input_tokens"] = max(1, token_usage.get("promptTokens", 1))
                                usage["output_tokens"] = max(
                                    1, token_usage.get("completionTokens", 1)
                                )
                                print(
                                    f"DEBUG - Found token usage in responseMetadata.tokenUsage: {usage}"
                                )
                                return usage

                # For Bedrock, if we still can't find token usage, estimate based on text length
                if "output" in response_body and "text" in response_body["output"]:
                    output_text = response_body["output"]["text"]
                    output_tokens = KBCostMetrics.estimate_tokens(output_text)
                    # Estimate input tokens as roughly proportional to output tokens
                    input_tokens = max(
                        1, int(output_tokens * 0.5)
                    )  # Assume input is about half the size of output

                    usage["output_tokens"] = max(1, output_tokens)
                    usage["input_tokens"] = max(1, input_tokens)
                    usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]

                    print(f"DEBUG - Estimated token usage from text length: {usage}")
                    return usage

            # Original provider-specific handling
            if provider_enum == ModelProvider.ANTHROPIC:
                usage["input_tokens"] = max(
                    1, response_body.get("usage", {}).get("input_tokens", 1)
                )
                usage["output_tokens"] = max(
                    1, response_body.get("usage", {}).get("output_tokens", 1)
                )
            elif provider_enum == ModelProvider.AMAZON and model and "nova" in model.lower():
                usage["input_tokens"] = max(1, response_body.get("usage", {}).get("inputTokens", 1))
                usage["output_tokens"] = max(
                    1, response_body.get("usage", {}).get("outputTokens", 1)
                )
            elif provider_enum == ModelProvider.COHERE:
                usage["total_tokens"] = max(
                    2, response_body.get("meta", {}).get("billed_tokens", 2)
                )
                if "tokens" in response_body.get("meta", {}):
                    usage["input_tokens"] = max(
                        1, response_body["meta"]["tokens"].get("prompt_tokens", 1)
                    )
                    usage["output_tokens"] = max(
                        1, response_body["meta"]["tokens"].get("completion_tokens", 1)
                    )
                else:
                    # Fall back to approximate split if detailed token info not available
                    usage["input_tokens"] = max(1, int(usage["total_tokens"] * 0.3))
                    usage["output_tokens"] = max(1, usage["total_tokens"] - usage["input_tokens"])
            elif provider_enum == ModelProvider.MISTRAL:
                usage["input_tokens"] = max(
                    1, response_body.get("usage", {}).get("prompt_tokens", 1)
                )
                usage["output_tokens"] = max(
                    1, response_body.get("usage", {}).get("completion_tokens", 1)
                )
            else:
                # For unknown providers, estimate from text content if available
                if isinstance(response_body, dict) and "text" in response_body:
                    total_tokens = KBCostMetrics.estimate_tokens(response_body["text"])
                    usage["input_tokens"] = max(1, int(total_tokens * 0.3))
                    usage["output_tokens"] = max(1, total_tokens - usage["input_tokens"])

            # Calculate total tokens if not already set
            usage["total_tokens"] = max(2, usage["input_tokens"] + usage["output_tokens"])

            # If we're still using minimum values, make a more significant estimate
            if usage["input_tokens"] == 1 and usage["output_tokens"] == 1:
                # This is a fallback - use the prompt length to estimate input tokens
                # For Bedrock retrieve_and_generate, if we can find the input text
                if (
                    isinstance(response_body, dict)
                    and "input" in response_body
                    and "text" in response_body["input"]
                ):
                    input_text = response_body["input"]["text"]
                    input_tokens = KBCostMetrics.estimate_tokens(input_text)
                    usage["input_tokens"] = max(1, input_tokens)

                    # If we can find the output text
                    if "output" in response_body and "text" in response_body["output"]:
                        output_text = response_body["output"]["text"]
                        output_tokens = KBCostMetrics.estimate_tokens(output_text)
                        usage["output_tokens"] = max(1, output_tokens)
                    else:
                        # Estimate output tokens as proportional to input
                        usage["output_tokens"] = max(
                            1, int(input_tokens * 1.5)
                        )  # Assume output is larger than input

                    usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
                    print(f"DEBUG - Estimated token usage from input/output text: {usage}")

            return usage

        except Exception as e:
            logger.error(f"Error getting token usage: {str(e)}")
            return usage

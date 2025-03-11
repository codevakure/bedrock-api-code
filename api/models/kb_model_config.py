import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from config.logging_config import logger


class GuardrailSettings(BaseModel):
    guardrailIdentifier: str = "e1xjb1vcaxah"
    guardrailVersion: str = "DRAFT"


class GenerationSettings(BaseModel):
    temperature: float = Field(
        default=0.2, ge=0, le=1, description="Controls randomness in the output"
    )
    top_p: float = Field(default=0.999, ge=0, le=1, description="Nucleus sampling parameter")
    top_k: int = Field(default=250, ge=0, description="Top-k sampling parameter")
    max_tokens: int = Field(default=2048, ge=0, description="Maximum number of tokens to generate")
    stop_sequences: Optional[List[str]] = Field(
        default=None, description="Sequences that will stop generation"
    )
    guardrails: Optional[GuardrailSettings] = None


class ModelProvider(Enum):
    AMAZON = "amazon"
    ANTHROPIC = "anthropic"
    COHERE = "cohere"
    META = "meta"
    MISTRAL = "mistral"
    STABILITY = "stability"
    AI21 = "ai21"
    UNKNOWN = "unknown"


@dataclass
class KBModelPricing:
    """Represents the pricing for an LLM model."""

    input_cost: float
    output_cost: float

    def to_dict(self) -> Dict[str, float]:
        return {"input_cost": self.input_cost, "output_cost": self.output_cost}


class ModelIdentifier:
    """Helper class for parsing and normalizing model identifiers."""

    def __init__(self, model_arn: str):
        self.original_arn = model_arn
        self.base_arn, self.token_count = self._parse_arn()
        self.model_name = self._extract_model_name()
        self.provider = self._determine_provider()

    def _parse_arn(self) -> Tuple[str, str]:
        """Parse ARN into base and token count."""
        base_arn_match = re.match(r"(.+?:\d+):(\d+[kKmM]?)$", self.original_arn)
        if base_arn_match:
            return base_arn_match.group(1), base_arn_match.group(2)
        return self.original_arn, ""

    def _extract_model_name(self) -> str:
        """Extract model name from ARN."""
        match = re.search(r"foundation-model/([a-zA-Z0-9\-\.]+)", self.base_arn)
        return match.group(1) if match else "unknown"

    def _determine_provider(self) -> ModelProvider:
        """Determine the model provider."""
        provider_match = re.search(r"foundation-model/([^\.]+)\.", self.base_arn)
        if provider_match:
            try:
                return ModelProvider(provider_match.group(1).lower())
            except ValueError:
                pass
        return ModelProvider.UNKNOWN

    def normalize_name(self) -> str:
        """Normalize model name for consistent matching."""
        return self.model_name.lower().replace("_", "-").replace(" ", "-")


class KBModelConfig:
    """Represents the configuration for an LLM model."""

    def __init__(
        self,
        model_id: str,
        provider: ModelProvider,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        top_p: float = 0.999,
        top_k: int = 250,
        stop_sequences: Optional[List[str]] = None,
        supports_query_decomposition: bool = False,
        pricing: Optional[KBModelPricing] = None,
        guardrails: Optional[GuardrailSettings] = None,
    ):
        self.model_id = model_id
        self.provider = provider
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.stop_sequences = stop_sequences or []
        self.supports_query_decomposition = supports_query_decomposition
        self.pricing = pricing or KBModelPricing(0.0001, 0.0003)
        self.guardrails = guardrails or GuardrailSettings()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider": self.provider.value,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "stop_sequences": self.stop_sequences,
            "supports_query_decomposition": self.supports_query_decomposition,
            "pricing": self.pricing.to_dict(),
            "guardrails": (
                {
                    "guardrailIdentifier": self.guardrails.guardrailIdentifier,
                    "guardrailVersion": self.guardrails.guardrailVersion,
                }
                if self.guardrails
                else None
            ),
        }

    def get_generation_settings(self) -> GenerationSettings:
        """Get the current generation settings for this model."""
        return GenerationSettings(
            temperature=self.temperature,
            top_p=self.top_p,
            top_k=self.top_k,
            max_tokens=self.max_tokens,
            stop_sequences=self.stop_sequences,
            guardrails=self.guardrails,
        )

    def update_from_settings(self, settings: GenerationSettings) -> None:
        """Update configuration from GenerationSettings."""
        self.temperature = settings.temperature
        self.top_p = settings.top_p
        self.top_k = settings.top_k
        self.max_tokens = settings.max_tokens
        self.stop_sequences = settings.stop_sequences
        self.guardrails = settings.guardrails or self.guardrails


class ModelFamilyMapper:
    """Handles mapping of model names to families."""

    # Define model family patterns
    _FAMILY_PATTERNS = {
        # Amazon models
        r"titan-text-premier": "titan-text-g1-premier",
        r"nova-pro": "nova-pro",
        r"nova-lite": "nova-lite",
        r"nova-micro": "nova-micro",
        r"titan-embed-text-v\d": "titan-embed-text",
        r"titan-embed-image-v\d": "titan-embed-image",
        # Anthropic models
        r"claude-instant-v\d": "claude-instant",
        r"claude-v2(?::\d+)?": "claude-v2",
        r"claude-3-sonnet-\d{8}": "claude-3-sonnet",
        r"claude-3-haiku-\d{8}": "claude-3-haiku",
        r"claude-3\.5-sonnet-\d{8}": "claude-3.5-sonnet",
        r"claude-3-5-sonnet-\d{8}": "claude-3.5-sonnet",
        # Cohere models
        r"command-r-plus": "command-r-plus",
        r"command-r(?!-plus)": "command-r",
        r"command-light": "command-light",
        # Meta models
        r"llama3-70b": "llama-3-70b-instruct",
        r"llama3-\d+b": "llama-3-other",
        # Mistral models
        r"mistral-large-\d{4}": "mistral-large",
        r"mistral-small-\d{4}": "mistral-small",
        r"mixtral-8x7b": "mixtral",
    }

    @classmethod
    def get_family(cls, model_name: str) -> str:
        """Get model family from model name."""
        normalized_name = model_name.lower().replace("_", "-")

        for pattern, family in cls._FAMILY_PATTERNS.items():
            if re.search(pattern, normalized_name):
                return family

        # logger.warning(f"Unknown model family for {model_name}")
        return "unknown"


class KBModelConfigs:
    """Manages configurations for different LLM models."""

    # Default configuration
    DEFAULT_CONFIG = KBModelConfig(
        model_id="unknown",
        provider=ModelProvider.UNKNOWN,
        max_tokens=2048,
        temperature=0.2,
        top_p=0.999,
        top_k=250,
        supports_query_decomposition=False,
        pricing=KBModelPricing(0.0001, 0.0003),
        guardrails=GuardrailSettings(),
    )

    # Model family pricing
    _MODEL_PRICING = {
        "titan-text-g1-premier": KBModelPricing(0.0008, 0.0016),
        "nova-pro": KBModelPricing(0.00125, 0.00375),
        "nova-lite": KBModelPricing(0.0003, 0.0009),
        "nova-micro": KBModelPricing(0.0001, 0.0003),
        "claude-instant": KBModelPricing(0.00080, 0.00240),
        "claude-v2": KBModelPricing(0.00800, 0.02400),
        "claude-3-sonnet": KBModelPricing(0.00300, 0.00900),
        "claude-3-haiku": KBModelPricing(0.00025, 0.00075),
        "claude-3.5-sonnet": KBModelPricing(0.00300, 0.00900),
        "command-r": KBModelPricing(0.00015, 0.00020),
        "command-r-plus": KBModelPricing(0.00300, 0.00600),
        "llama-3-70b-instruct": KBModelPricing(0.00070, 0.00090),
        "mistral-large": KBModelPricing(0.00250, 0.00750),
        "mistral-small": KBModelPricing(0.00030, 0.00090),
    }

    @classmethod
    def get_config(cls, model_arn: str) -> KBModelConfig:
        """Get configuration for a model based on its ARN."""
        try:
            identifier = ModelIdentifier(model_arn)
            model_family = ModelFamilyMapper.get_family(identifier.model_name)

            # Get pricing for the model family
            pricing = cls._MODEL_PRICING.get(model_family, cls.DEFAULT_CONFIG.pricing)

            # Create config with appropriate values
            return KBModelConfig(
                model_id=identifier.model_name,
                provider=identifier.provider,
                max_tokens=cls._get_max_tokens(identifier),
                temperature=cls.DEFAULT_CONFIG.temperature,
                top_p=cls.DEFAULT_CONFIG.top_p,
                supports_query_decomposition=cls._supports_decomposition(identifier),
                pricing=pricing,
            )
        except Exception as e:
            logger.error(f"Error creating config for {model_arn}: {str(e)}")
            return cls.DEFAULT_CONFIG

    @classmethod
    def _get_max_tokens(cls, identifier: ModelIdentifier) -> int:
        """Determine max tokens for a model."""
        # Map of known token limits
        token_limits = {
            "claude-3-sonnet": 200000,
            "claude-3-haiku": 200000,
            "claude-3.5-sonnet": 4096,
            "mistral-large": 8192,
            "mistral-small": 8192,
        }

        model_family = ModelFamilyMapper.get_family(identifier.model_name)
        return token_limits.get(model_family, cls.DEFAULT_CONFIG.max_tokens)

    @classmethod
    def _supports_decomposition(cls, identifier: ModelIdentifier) -> bool:
        """Determine if model supports query decomposition."""
        decomposition_supported = ["claude-3-sonnet", "claude-3-haiku", "claude-3.5-sonnet"]
        model_family = ModelFamilyMapper.get_family(identifier.model_name)
        return model_family in decomposition_supported

    @classmethod
    def enrich_model_info(cls, model_info: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich model information with configuration and pricing."""
        try:
            config = cls.get_config(model_info["model_arn"])
            model_info.update(
                {
                    "config": {
                        "provider": config.provider.value,
                        "max_tokens": config.max_tokens,
                        "temperature": config.temperature,
                        "top_p": config.top_p,
                        "top_k": config.top_k,
                        "stop_sequences": config.stop_sequences,
                        "supports_query_decomposition": config.supports_query_decomposition,
                        "guardrails": config.guardrails.dict() if config.guardrails else None,
                    },
                    "pricing": config.pricing.to_dict(),
                }
            )
        except Exception as e:
            logger.error(f"Error enriching model info: {str(e)}")
            # Add default config if enrichment fails
            model_info.update(
                {
                    "config": cls.DEFAULT_CONFIG.to_dict(),
                    "pricing": cls.DEFAULT_CONFIG.pricing.to_dict(),
                }
            )

        return model_info

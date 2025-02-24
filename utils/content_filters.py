# app/utils/content_filter.py
import re
from typing import Dict
from api.models.models import GuardrailSettings, FilterMode

class ContentFilter:
    DEFAULT_PROFANITY = {
        'damn': 'd***',
        'hell': 'h***',
    }

    @staticmethod
    def filter_content(text: str, settings: GuardrailSettings) -> str:
        if not settings.profanity_filter:
            return text
            
        replacements = ContentFilter.DEFAULT_PROFANITY.copy()
        if settings.custom_replacements:
            replacements.update(settings.custom_replacements)
            
        if settings.custom_blocked_words:
            for word in settings.custom_blocked_words:
                replacements[word] = '*' * len(word)
        
        filtered_text = text
        for word, replacement in replacements.items():
            if settings.profanity_action == FilterMode.REMOVE:
                filtered_text = re.sub(
                    r'\b' + re.escape(word) + r'\b', 
                    '', 
                    filtered_text, 
                    flags=re.IGNORECASE
                )
            elif settings.profanity_action == FilterMode.MASK:
                filtered_text = re.sub(
                    r'\b' + re.escape(word) + r'\b', 
                    replacement, 
                    filtered_text, 
                    flags=re.IGNORECASE
                )
            elif settings.profanity_action == FilterMode.BLOCK:
                if re.search(r'\b' + re.escape(word) + r'\b', filtered_text, flags=re.IGNORECASE):
                    raise ValueError(f"Generated content contains blocked word: {word}")
                
        return filtered_text

    @staticmethod
    def get_generation_config(settings: GuardrailSettings) -> Dict:
        return {
            'contentFiltering': {
                'enabled': settings.content_filtering,
                'thresholds': {
                    'harmfulContent': settings.harmful_content_threshold,
                    'hateSpeech': settings.hate_speech_threshold
                }
            }
        }
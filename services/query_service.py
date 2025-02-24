import json
import asyncio
from typing import Optional, Dict, Any, AsyncGenerator, List
from config.aws_config import bedrock_agent_runtime_client, model_arn, bedrock_runtime
from api.models.models import GenerationSettings
from api.models.kb_model_config import KBModelConfigs
from utils.kb_metrics import KBCostMetrics
from utils.kb_utils import KBUtils

DEFAULT_MODEL_ARN = model_arn

class QueryService:
    @staticmethod
    def _format_stream_response(text: str) -> str:
        """Format streaming response text into clean HTML"""
        import re
        
        # Remove any system style tags
        text = re.sub(r'<userStyle>.*?</userStyle>', '', text)
        text = re.sub(r'<[a-zA-Z]+Style>.*?</[a-zA-Z]+Style>', '', text)
        
        # Clean the text and split into lines
        lines = text.strip().split('\n')
        formatted_lines = []
        current_list_items = []
        in_list = False
        
        for line in lines:
            line = line.strip()
            if not line:
                if in_list and current_list_items:
                    formatted_lines.append('<ul>')
                    formatted_lines.extend(current_list_items)
                    formatted_lines.append('</ul>')
                    current_list_items = []
                    in_list = False
                continue
            
            if line.startswith(('* ', '- ')):
                in_list = True
                item_text = line[2:].strip()
                current_list_items.append(f'<li>{item_text}</li>')
            else:
                if in_list and current_list_items:
                    formatted_lines.append('<ul>')
                    formatted_lines.extend(current_list_items)
                    formatted_lines.append('</ul>')
                    current_list_items = []
                    in_list = False
                formatted_lines.append(f'<p>{line}</p>')
        
        # Handle any remaining list items
        if in_list and current_list_items:
            formatted_lines.append('<ul>')
            formatted_lines.extend(current_list_items)
            formatted_lines.append('</ul>')
        
        return '\n'.join(formatted_lines)

    @staticmethod
    async def stream_generate(
        prompt: str,
        document_id: Optional[str] = None,
        settings: Optional[GenerationSettings] = None,
        system_prompt: Optional[str] = None,
        knowledge_base_id: Optional[str] = None,
        model_arn: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Generate streaming response from Bedrock"""
        try:
            current_model_arn = model_arn or DEFAULT_MODEL_ARN
            
            try:
                model_config = KBModelConfigs.get_config(current_model_arn)
            except Exception as config_error:
                print(f"Error getting model config: {str(config_error)}")
                model_config = KBModelConfigs.DEFAULT_CONFIG
            
            metadata = {
                "page_numbers": [],
                "cost_metrics": None
            }

            if knowledge_base_id:
                # Knowledge base query logic
                config = {
                    'type': 'KNOWLEDGE_BASE',
                    'knowledgeBaseConfiguration': {
                        'knowledgeBaseId': knowledge_base_id,
                        'modelArn': current_model_arn,
                        'retrievalConfiguration': {
                            'vectorSearchConfiguration': {
                                'numberOfResults': 3
                            }
                        }
                    }
                }

                if document_id:
                    config['knowledgeBaseConfiguration']['retrievalConfiguration']['vectorSearchConfiguration']['filter'] = {
                        'stringContains': {
                            'key': 'x-amz-bedrock-kb-source-uri',
                            'value': document_id
                        }
                    }

                request_params = {
                    'input': {'text': prompt},
                    'retrieveAndGenerateConfiguration': config
                }
                
                try:
                    response = bedrock_agent_runtime_client.retrieve_and_generate(**request_params)
                    generated_text = response.get('output', {}).get('text', '')
                    
                    # Process page numbers
                    unique_page_numbers = set()
                    if "citations" in response:
                        for citation in response["citations"]:
                            if isinstance(citation, dict) and "retrievedReferences" in citation:
                                for reference in citation["retrievedReferences"]:
                                    if isinstance(reference, dict) and 'metadata' in reference:
                                        page_number = reference["metadata"].get("x-amz-bedrock-kb-document-page-number")
                                        if page_number is not None:
                                            unique_page_numbers.add(int(page_number))
                    
                    metadata["page_numbers"] = sorted(list(unique_page_numbers))
                    
                    # Calculate token usage and cost
                    token_usage = KBCostMetrics.get_token_usage(response, model_config.provider.value, model_config.model_id)
                    input_cost = token_usage["input_tokens"] * 0.00001
                    output_cost = token_usage["output_tokens"] * 0.00001
                    total_cost = input_cost + output_cost
                    
                    metadata["cost_metrics"] = {
                        "input_cost": f"${input_cost:.6f}",
                        "output_cost": f"${output_cost:.6f}",
                        "total_cost": f"${total_cost:.6f}"
                    }

                except Exception as kb_error:
                    print(f"Error in KB query: {str(kb_error)}")
                    yield json.dumps({
                        "error": f"Knowledge base query failed: {str(kb_error)}",
                        "is_final": True
                    }) + "\n"
                    return

            else:
                # Direct LLM query
                try:
                    request_body = KBUtils._prepare_request_body(prompt, settings, current_model_arn)
                    request_params = {
                        'modelId': current_model_arn,
                        'contentType': 'application/json',
                        'accept': 'application/json',
                        'body': json.dumps(request_body).encode('utf-8')
                    }
                    
                    response = bedrock_runtime.invoke_model(**request_params)
                    response_body = json.loads(response['body'].read().decode())
                    
                    generated_text = KBUtils._extract_generated_text(response_body, model_config)
                    
                    # Calculate token usage and cost
                    token_usage = KBCostMetrics.get_token_usage(response_body, model_config.provider.value, model_config.model_id)
                    input_cost = token_usage["input_tokens"] * 0.00001
                    output_cost = token_usage["output_tokens"] * 0.00001
                    total_cost = input_cost + output_cost
                    
                    metadata["cost_metrics"] = {
                        "input_cost": f"${input_cost:.6f}",
                        "output_cost": f"${output_cost:.6f}",
                        "total_cost": f"${total_cost:.6f}"
                    }

                except Exception as llm_error:
                    print(f"Error in direct LLM query: {str(llm_error)}")
                    yield json.dumps({
                        "error": f"Direct LLM query failed: {str(llm_error)}",
                        "is_final": True
                    }) + "\n"
                    return

            # Stream the response in chunks
            chunk_size = 100
            for i in range(0, len(generated_text), chunk_size):
                chunk = generated_text[i:i + chunk_size]
                is_final = i + chunk_size >= len(generated_text)
                
                response_chunk = {
                    "chunk": chunk,
                    "is_final": is_final
                }
                
                if is_final:
                    response_chunk["metadata"] = metadata
                
                yield json.dumps(response_chunk, ensure_ascii=False) + "\n"
                await asyncio.sleep(0.1)

        except Exception as e:
            print(f"Error in stream_generate: {str(e)}")
            yield json.dumps({
                "error": str(e),
                "is_final": True
            }) + "\n"
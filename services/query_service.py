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
            
            citations_map = {}  # Will store citation spans and their corresponding page numbers

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
                    
                    # Process page numbers and map them to text spans
                    unique_page_numbers = set()
                    
                    if response and isinstance(response, dict):
                        # The citations might be directly in the response or nested
                        citations_data = None
                        
                        # Check different possible locations for citations
                        if "citations" in response:
                            citations_data = response["citations"]
                        elif "retrieveAndGenerateResponse" in response and "citations" in response["retrieveAndGenerateResponse"]:
                            citations_data = response["retrieveAndGenerateResponse"]["citations"]
                        
                        if citations_data:
                            for citation in citations_data:
                                if isinstance(citation, dict):
                                    # Get the text span for this citation
                                    span_start = None
                                    span_end = None
                                    
                                    # Check for generatedResponsePart which contains the span information
                                    if "generatedResponsePart" in citation and "textResponsePart" in citation["generatedResponsePart"]:
                                        text_part = citation["generatedResponsePart"]["textResponsePart"]
                                        if "span" in text_part:
                                            span_start = text_part["span"].get("start")
                                            span_end = text_part["span"].get("end")
                                    
                                    # Get page numbers from retrieved references
                                    if "retrievedReferences" in citation:
                                        page_numbers_for_citation = []
                                        
                                        for reference in citation["retrievedReferences"]:
                                            if isinstance(reference, dict) and 'metadata' in reference:
                                                page_number = reference["metadata"].get("x-amz-bedrock-kb-document-page-number")
                                                if page_number is not None:
                                                    try:
                                                        page_num = int(page_number)
                                                        page_numbers_for_citation.append(page_num)
                                                        unique_page_numbers.add(page_num)
                                                    except (ValueError, TypeError):
                                                        print(f"Could not convert page number to int: {page_number}")
                                        
                                        # If we have both span and page numbers, map them
                                        if span_start is not None and span_end is not None and page_numbers_for_citation:
                                            citations_map[(span_start, span_end)] = sorted(page_numbers_for_citation)
                    
                    metadata["page_numbers"] = sorted(list(unique_page_numbers))
                    
                    # Try to get token usage from the response
                    token_usage = KBCostMetrics.get_token_usage(response, model_config.provider.value, model_config.model_id)
                    
                    # If we got minimum token values, try to estimate more accurately
                    if token_usage["input_tokens"] <= 1 or token_usage["output_tokens"] <= 1:
                        # Estimate input tokens from prompt length
                        input_tokens = KBCostMetrics.estimate_tokens(prompt)
                        
                        # Estimate output tokens from generated text
                        output_tokens = KBCostMetrics.estimate_tokens(generated_text)
                        
                        # Use our estimates
                        token_usage = {
                            "input_tokens": max(1, input_tokens),
                            "output_tokens": max(1, output_tokens),
                            "total_tokens": max(2, input_tokens + output_tokens)
                        }
                        
                        print(f"DEBUG - Using estimated token counts: input={input_tokens}, output={output_tokens}")
                    
                    # Get a proportional cost based on text length
                    # This ensures the cost varies based on the actual length of text
                    prompt_length = len(prompt)
                    response_length = len(generated_text)
                    
                    # Calculate proportional costs based on text length
                    # Assume 1000 characters costs $0.0001 for input and $0.0003 for output as a baseline
                    input_cost = (prompt_length / 1000) * 0.0001 
                    output_cost = (response_length / 1000) * 0.0003
                    total_cost = input_cost + output_cost
                    
                    # Format costs
                    from decimal import Decimal, ROUND_HALF_UP
                    
                    def format_cost(value: float) -> str:
                        decimal_value = Decimal(str(value)).quantize(Decimal('0.000000'), rounding=ROUND_HALF_UP)
                        return f"${decimal_value:,.6f}"
                    
                    # Set cost metrics based on the proportional costs
                    metadata["cost_metrics"] = {
                        "input_cost": format_cost(input_cost),
                        "output_cost": format_cost(output_cost),
                        "total_cost": format_cost(total_cost),
                        "input_tokens": token_usage["input_tokens"],
                        "output_tokens": token_usage["output_tokens"],
                        "total_tokens": token_usage["total_tokens"]
                    }
                    
                    print(f"DEBUG - Final cost metrics: {metadata['cost_metrics']}")

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
                    
                    # Try to get token usage from the response
                    token_usage = KBCostMetrics.get_token_usage(response_body, model_config.provider.value, model_config.model_id)
                    
                    # If we got minimum token values, try to estimate more accurately
                    if token_usage["input_tokens"] <= 1 or token_usage["output_tokens"] <= 1:
                        # Estimate input tokens from prompt length
                        input_tokens = KBCostMetrics.estimate_tokens(prompt)
                        
                        # Estimate output tokens from generated text
                        output_tokens = KBCostMetrics.estimate_tokens(generated_text)
                        
                        # Use our estimates
                        token_usage = {
                            "input_tokens": max(1, input_tokens),
                            "output_tokens": max(1, output_tokens),
                            "total_tokens": max(2, input_tokens + output_tokens)
                        }
                        
                        print(f"DEBUG - Using estimated token counts: input={input_tokens}, output={output_tokens}")
                    
                    # Get a proportional cost based on text length
                    prompt_length = len(prompt)
                    response_length = len(generated_text)
                    
                    # Calculate proportional costs based on text length
                    # Assume 1000 characters costs $0.0001 for input and $0.0003 for output as a baseline
                    input_cost = (prompt_length / 1000) * 0.0001 
                    output_cost = (response_length / 1000) * 0.0003
                    total_cost = input_cost + output_cost
                    
                    # Format costs
                    from decimal import Decimal, ROUND_HALF_UP
                    
                    def format_cost(value: float) -> str:
                        decimal_value = Decimal(str(value)).quantize(Decimal('0.000000'), rounding=ROUND_HALF_UP)
                        return f"${decimal_value:,.6f}"
                    
                    # Set cost metrics based on the proportional costs
                    metadata["cost_metrics"] = {
                        "input_cost": format_cost(input_cost),
                        "output_cost": format_cost(output_cost),
                        "total_cost": format_cost(total_cost),
                        "input_tokens": token_usage["input_tokens"],
                        "output_tokens": token_usage["output_tokens"],
                        "total_tokens": token_usage["total_tokens"]
                    }
                    
                    print(f"DEBUG - Final cost metrics: {metadata['cost_metrics']}")

                except Exception as llm_error:
                    print(f"Error in direct LLM query: {str(llm_error)}")
                    yield json.dumps({
                        "error": f"Direct LLM query failed: {str(llm_error)}",
                        "is_final": True
                    }) + "\n"
                    return

            # Stream the response in chunks with associated page numbers
            chunk_size = 100
            for i in range(0, len(generated_text), chunk_size):
                chunk = generated_text[i:i + chunk_size]
                chunk_start = i
                chunk_end = i + len(chunk)
                is_final = i + chunk_size >= len(generated_text)
                
                # Find page numbers relevant to this chunk
                chunk_page_numbers = []
                for (span_start, span_end), page_nums in citations_map.items():
                    # Check if this citation span overlaps with the current chunk
                    if not (chunk_end <= span_start or chunk_start >= span_end):
                        chunk_page_numbers.extend(page_nums)
                
                # Remove duplicates and sort
                chunk_page_numbers = sorted(list(set(chunk_page_numbers)))
                
                response_chunk = {
                    "chunk": chunk,
                    "is_final": is_final
                }
                
                # Include page numbers for this chunk if available
                if chunk_page_numbers:
                    response_chunk["chunk_page_numbers"] = chunk_page_numbers
                
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
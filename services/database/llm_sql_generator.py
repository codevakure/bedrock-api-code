"""
LLM-based SQL Query Generator

This service leverages an LLM to generate SQL queries based on natural language prompts
and database schema information.
"""

import logging
from typing import Any, Dict, List, Optional

from config import bedrock_client, model_arn
from services.database.schema_analyzer_service import SchemaAnalyzerService

logger = logging.getLogger(__name__)

# Default system prompt template
DEFAULT_SYSTEM_PROMPT = """
You are an expert SQL query generator assistant. Your task is to generate correct SQL queries
based on user natural language questions and database schema information.

Below is the database schema information:

{schema_context}

Important guidelines:
1. Only use tables and columns that are mentioned in the schema.
2. Pay attention to primary keys and relationships between tables.
3. Return only the SQL query without explanations unless explicitly requested.
4. Use proper joins based on the relationships provided.
5. Always qualify column names with table names or aliases to avoid ambiguity.
6. When filtering by date, check the date format compatibility with the database.
7. PostgreSQL specific: Use double quotes for identifiers (table and column names) that need escaping.

Now, generate PostgreSQL-compatible SQL queries based on the user's natural language questions.
"""


class LLMSqlGenerator:
    """Service for generating SQL queries using LLM and schema information."""

    def __init__(self, model_id: str = None):
        """
        Initialize the SQL generator with optional model ID.

        Args:
            model_id: Optional model ID to use (defaults to configured model_arn)
        """
        self.schema_service = SchemaAnalyzerService()
        self.model_id = model_id or model_arn

    def generate_sql(
        self,
        connection_id: str,
        question: str,
        include_explanation: bool = False,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate SQL from a natural language question using the LLM.

        Args:
            connection_id: Database connection ID for schema context
            question: Natural language question
            include_explanation: Whether to include explanation in the response
            system_prompt: Custom system prompt (uses default if None)

        Returns:
            Dict with generated SQL and optional explanation
        """
        try:
            # Get schema context
            schema_context = self.schema_service.get_llm_context(connection_id)

            # Prepare system prompt
            if system_prompt is None:
                system_prompt = DEFAULT_SYSTEM_PROMPT

            system_prompt = system_prompt.format(schema_context=schema_context)

            # Adjust user question if explanation is requested
            user_prompt = question
            if include_explanation:
                user_prompt += "\nPlease also explain the query and how it addresses my question."

            # Call the LLM
            response = self._invoke_llm(system_prompt, user_prompt)

            # Parse the response
            result = self._parse_llm_response(response, include_explanation)
            result["question"] = question

            return result

        except Exception as e:
            logger.error(f"Error generating SQL: {e}", exc_info=True)
            return {"question": question, "success": False, "error": str(e)}

    def _invoke_llm(self, system_prompt: str, user_prompt: str) -> str:
        """
        Invoke the LLM with the given prompts.

        Args:
            system_prompt: System prompt with schema context
            user_prompt: User question

        Returns:
            The LLM response text
        """
        try:
            # Prepare the request body for Amazon Bedrock
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1500,
                "temperature": 0.1,  # Low temperature for more deterministic results
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }

            # Invoke the model
            response = bedrock_client.invoke_model(modelId=self.model_id, body=json.dumps(body))

            # Parse the response
            response_body = json.loads(response.get("body").read())
            return response_body.get("content")[0].get("text")

        except Exception as e:
            logger.error(f"Error invoking LLM: {e}", exc_info=True)
            raise Exception(f"Failed to generate SQL: {str(e)}")

    def _parse_llm_response(self, response: str, include_explanation: bool) -> Dict[str, Any]:
        """
        Parse the LLM response into structured output.

        Args:
            response: The raw LLM response text
            include_explanation: Whether explanation was requested

        Returns:
            Structured response with SQL and optional explanation
        """
        try:
            # Default result structure
            result = {
                "success": True,
                "sql": "",
                "explanation": "" if include_explanation else None,
            }

            # Extract SQL code blocks
            sql_blocks = []
            lines = response.split("\n")
            in_code_block = False
            current_block = []

            for line in lines:
                if line.strip().startswith("```sql") or line.strip() == "```sql":
                    in_code_block = True
                    current_block = []
                elif line.strip() == "```" and in_code_block:
                    in_code_block = False
                    sql_blocks.append("\n".join(current_block))
                elif in_code_block:
                    current_block.append(line)

            # If no code blocks found, look for SQL patterns
            if not sql_blocks:
                # Try to find SQL statements directly
                sql_pattern = r"(SELECT .+?;)"
                import re

                matches = re.findall(sql_pattern, response, re.DOTALL | re.IGNORECASE)
                if matches:
                    sql_blocks = matches

            # If still no SQL found, use the entire response
            if not sql_blocks:
                sql_blocks = [response]

            # Use the first SQL block as the query
            result["sql"] = sql_blocks[0].strip()

            # If explanation requested, extract everything except SQL blocks
            if include_explanation:
                # Simple approach: remove SQL code blocks from response
                explanation = response
                for block in sql_blocks:
                    explanation = explanation.replace(f"```sql\n{block}\n```", "")
                    explanation = explanation.replace(block, "")

                # Clean up explanation
                explanation = explanation.strip()
                result["explanation"] = explanation

            return result

        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to parse LLM response: {str(e)}",
                "raw_response": response,
            }

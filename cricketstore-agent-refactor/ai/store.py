import os
import json
import logging
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from ai.models import Queryrecordproduct
from langchain_huggingface import HuggingFaceEndpoint

logger = logging.getLogger(__name__)
prompt_template = """
You are an assistant that converts user search queries for cricket products into structured filters.

Example Inputs:
- "Show me SG bats under 5000 for power hitters"
- "lightweight gloves from MRF under 2000"
- "Shuttle bats under 5000 rupees"

Expected JSON format:
{{
  "index": "products",
  "filters": {{
    "name": "",
    "brand": "",
    "sport": "",
    "category": "",
    "price_max": "",
  }},
  "query_text": ""
}}

User query: {query}
Return only valid JSON.
"""

prompt = PromptTemplate.from_template(prompt_template)
llm = llm=HuggingFaceEndpoint(
    repo_id="google/flan-t5-large",
    temperature=0.0,
    max_new_tokens=512,
    huggingfacehub_api_token=os.getenv("HUGGINGFACEHUB_API_TOKEN"),
  )
parser = JsonOutputParser()
chain = prompt | llm | parser

def interpret_product_query(user_query: str):
    try:
        result = chain.invoke({"query": user_query})
        parsed = dict(result) if isinstance(result, dict) else json.loads(result)

        parsed["index"] = "products"
        f = parsed.get("filters", {})
        parsed["filters"] = {
            "name": f.get("name"),
            "brand": f.get("brand"),
            "sport": f.get("sport"),
            "category": f.get("category"),
            "price_max": f.get("price_max"),
            "features": f.get("features", []),
            "material": f.get("material"),
        }
        parsed["query_text"] = parsed.get("query_text") or user_query
        Queryrecordproduct.objects.create(userquery=user_query, gptresponse=parsed)
        return parsed
    except Exception as e:
        logger.exception("Product query interpretation failed: %s", e)
        return {"index": "products", "filters": {}, "query_text": user_query}

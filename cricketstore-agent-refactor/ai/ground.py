# ai/langchain_parsers.py

import os
import json
import logging
from datetime import date, datetime, timedelta

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI

from ai.models import Queryrecordground
from django.conf import settings

logger = logging.getLogger(__name__)

prompt_template = """
You are an assistant that converts user queries related to booking sports grounds into a strict JSON structure.

MUST FOLLOW THESE RULES:

1) booking_type →
   - "normal_booking" → single-day/hour booking, casual play
   - "tournament_booking" → multi-day, full-day, “tournament”, “league”, “for X days”, “from X to Y”

2) intent → choose one from:
   "show", "book", "cancel", "reschedule", "info", "unknown"

3) Extract filters EXACTLY in this schema:

{{
  "booking_type": "",
  "intent": "",
  "filters": {{
    "sporttype": "",
    "ground_or_turf": "",
    "ground_or_turf_name": "",
    "city": "",
    "area": "",
    "address": "",
    "price": "",
    "price_semantic": "",
    "rating_min": "",
    "rating_semantic": "",
    "timings": "",
    "am_pm": "",
    "start_date": "",
    "end_date": "",
    "duration_days": "",
    "shift": "",
    "available_date": "",
    "radius_km": ""
  }},
  "query_text": ""
}}

SPECIAL RULES:
- If user says "this weekend" / "weekend", DO NOT convert to dates. Put EXACT text inside filters.available_date.
- If user mentions shifts: morning, afternoon, evening, night → put into filters.shift.
- If user mentions “near me”, “nearby”, “within X km”, extract radius_km.
- “cheaper”, “less price”, “budget friendly” → price_semantic = "cheaper"
- “expensive”, “premium”, “high price” → price_semantic = "expensive"
- “top rated”, “best rated”, “high rating” → rating_semantic = "top_rated"
- “low rated”, “bad rating”, “poor rating” → rating_semantic = "low_rated"
- If user asks for tournament weekend → weekend still goes into available_date.

Return ONLY valid JSON. No explanation.

User query: {query}
"""

prompt = PromptTemplate.from_template(prompt_template)


def get_llm():
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    return ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        api_key=api_key
    )


llm = get_llm()

parser = JsonOutputParser()

chain = prompt | llm | parser


def interpret_ground_query(user_query: str):
    """Convert query into structured JSON for ground booking."""

    try:
        result = chain.invoke({"query": user_query})

        if isinstance(result, dict):
            parsed = result
        else:
            json_start = result.find("{")
            json_end = result.rfind("}")

            if json_start == -1 or json_end == -1:
                raise ValueError(f"No JSON found in LLM output: {result}")

            parsed = json.loads(result[json_start:json_end + 1])

        f = parsed.get("filters", {})

        parsed["filters"] = {
            "sporttype": f.get("sporttype"),
            "ground_or_turf": f.get("ground_or_turf"),
            "ground_or_turf_name": f.get("ground_or_turf_name"),
            "city": f.get("city"),
            "area": f.get("area"),
            "address": f.get("address"),
            "price": f.get("price"),
            "price_semantic": f.get("price_semantic"),
            "rating_min": f.get("rating_min"),
            "rating_semantic": f.get("rating_semantic"),
            "timings": f.get("timings"),
            "am_pm": f.get("am_pm"),
            "start_date": f.get("start_date"),
            "end_date": f.get("end_date"),
            "duration_days": f.get("duration_days"),
            "shift": f.get("shift"),
            "available_date": f.get("available_date"),
            "radius_km": f.get("radius_km"),
        }

        parsed["query_text"] = parsed.get("query_text") or user_query

        Queryrecordground.objects.create(
            query_text=user_query,
            interpreted_json=json.dumps(parsed)
        )

        return parsed

    except Exception as e:
        logger.error(f"Error interpreting ground query: {e}")

        return {
            "booking_type": "normal_booking",
            "intent": "unknown",
            "filters": {},
            "query_text": user_query
        }
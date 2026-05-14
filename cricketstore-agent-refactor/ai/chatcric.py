import json
import logging
from typing import Any, Optional, List, Literal

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import PydanticOutputParser
from django.conf import settings
from ai.models import Queryrecordground

logger = logging.getLogger(__name__)

class routedecison(BaseModel):
    route: Literal["missing_fields", "full_parse"]
    confidence: float = 1.0
class NormalBookingFilters(BaseModel):
    sporttype: str = ""
    ground_or_turf: str = ""
    ground_or_turf_name: str = ""
    city: str = ""
    area: str = ""
    address: str = ""
    date: str = ""
    timings: str = ""
    am_pm: str = ""
    shift: str = ""
    hours: str = ""
    price: str = ""
    price_semantic: str = ""
    rating_min: str = ""
    rating_semantic: str = ""
    constraint_type: str = ""  
    nearme: Optional[bool] = False 
    radius_km: Optional[int] = None 


class NormalBookingSchema(BaseModel):
    booking_type: Literal["normal_booking"]
    intent: Literal["show", "book", "cancel", "unknown",""]
    query_text: str
    filters: NormalBookingFilters

normal_parser = PydanticOutputParser(
    pydantic_object=NormalBookingSchema
)

normal_prompt = ChatPromptTemplate.from_messages([
    ("system", """
You are a STRICT JSON generator for a NORMAL sports ground booking system.

CRITICAL RULES:
- Output ONLY valid JSON
- Do NOT explain
- Do NOT ask questions
- Do NOT add extra keys
- booking_type MUST be "normal_booking"
- Missing or unknown values MUST be empty strings ""

INTENT RULES:
- "show" → user wants to search / view grounds
- "book" → user wants to reserve slots
- "cancel" → user wants to cancel booking
- "unknown" → unclear intent

TIME & DATE RULES:
- Extract raw date text exactly (e.g. "tomorrow", "this saturday")
- Extract timing text exactly (e.g. "5 to 7", "evening")
- Detect shifts: morning / afternoon / evening / night
- Detect AM / PM if clearly mentioned
- Detect constraint words:
    - "from", "after", "starting" → constraint_type = "after"
    - "until", "before" → constraint_type = "before"
    - ranges → constraint_type = "between"

PRICE RULES:
- "cheap", "cheapest", "low price" → price_semantic = "cheaper"
- "expensive", "premium" → price_semantic = "expensive"

RATING RULES:
- "top rated", "best" → rating_semantic = "top_rated"
- "low rated" → rating_semantic = "low_rated"
ALL extracted values MUST go inside "filters".
LOCATION RULES:
-If user says "near me", "nearby", "around me", "close to me":
  → set nearme = true
- Do NOT set radius_km unless explicitly mentioned

{format_instructions}
"""),
    ("human", "{query}")
]).partial(
    format_instructions=normal_parser.get_format_instructions()
)

normal_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.1,
    openai_api_key=settings.OPENAI_API_KEY
)

normal_chain = normal_prompt | normal_llm | normal_parser

missing_prompt = ChatPromptTemplate.from_messages([
    ("system", """
You are a STRICT JSON generator for a sports ground booking system.

The system is asking for the following missing fields:
{required_fields}

RULES (VERY IMPORTANT):
- Output FULL JSON schema
- You MUST fill the missing fields listed above IF AND ONLY IF they are clearly present
- You MAY extract additional CONTEXT fields such as city, area, or address IF explicitly mentioned
- Do NOT guess or force values into missing fields
- If a missing field is NOT clearly present, leave it as ""
- All other non-mentioned fields MUST be empty ""
- Do NOT infer or change intent
- Do NOT change booking_type
- Do NOT hallucinate values

Interpretation rules:
- Location names (area, city) are NOT ground or turf names
- Ground/turf names are usually proper names and may contain words like:
  ground, turf, stadium, arena, sports, academy

{format_instructions}
"""),
    ("human", "{query}")
]).partial(
    format_instructions=normal_parser.get_format_instructions()
)


missing_chain = missing_prompt | normal_llm | normal_parser

class AllowedShifts(BaseModel):
    start_day: List[str] = Field(default_factory=list)
    middle_days: List[str] = Field(default_factory=list)
    end_day: List[str] = Field(default_factory=list)
    constraint_type: str = "" #only if shifts are mentioned with date constraints

class TournamentBookingfilters(BaseModel):
    sporttype: str = ""
    ground_or_turf: str = ""
    ground_or_turf_name: str = ""
    city: str = ""
    area: str = ""
    address: str = ""
    start: str = ""
    end:str = ""
    total_days: str = ""
    shifts:AllowedShifts = Field(default_factory=AllowedShifts)
    budget: str = ""
    total_matches: str = ""
    overs_per_match: str = ""
    price_semantic: str = ""
    rating_min: str = ""
    rating_semantic: str = ""
    constraint_type: str = ""  
    nearme: Optional[bool] = False 
    radius_km: Optional[int] = None 

class TournamentBookingSchema(BaseModel):
    booking_type: Literal["tournament_booking"]
    intent: Literal["show", "book", "cancel", "unknown",""]
    query_text: str
    filters: TournamentBookingfilters

tournament_parser = PydanticOutputParser(pydantic_object=TournamentBookingSchema)

tournament_prompt = ChatPromptTemplate.from_messages([
    ("system", """
You are a STRICT JSON generator for a TOURNAMENT sports ground booking system.
CRITICAL RULES:
  - Output ONLY valid JSON
  - Do NOT explain anything
  - Do NOT add extra keys
  - Follow the exact schema provided
  - If a value is not explicitly mentioned, use empty string "" or null
  - Never guess or infer missing details
  - booking_type MUST always be "tournament_booking"

INTENT RULES:
 - "show" → user wants to search / view grounds
 - "book" → user wants to reserve slots
 - "cancel" → user wants to cancel booking
 - "unknown" → unclear intent

SPORT & LOCATION RULES:
 - sporttype → "cricket" if cricket is implied
 - ground_or_turf → "ground" or "turf" if mentioned
 - ground_or_turf_name → only if a specific name is given
 - city, area, address → extract only if explicitly mentioned
 - "near me" → nearme = true
 - radius like "within 5 km" → radius_km = 5
DATES & CONSTRAINT TYPE:
   Extract raw date text exactly (e.g. "tomorrow", "this saturday")
 - If exact dates are mentioned (e.g. "10 March", "10-04-2026"):
  - put them into filters.start and filters.end as raw text
  - constraint_type = "date_range"
 - If relative words are used ("this weekend", "next weekend", "for 3 days"):
  - keep raw text in filters.start
  - use filters.total_days ONLY if duration is explicitly stated
  - constraint_type examples:
    - "weekend"
    - "duration"
    - "date_range"
ALLOWED SHIFTS
Shifts can be ONLY:
- morning
- afternoon
- evening
- night

SHIFT EXTRACTION RULES (VERY IMPORTANT):

1. constraint_type = "only"
   Set constraint_type to "only" ONLY IF the user explicitly uses words like:
   - "only"
   - "just"
   Examples:
   - "only mornings"
   - "only nights"
   - "just mornings and evenings"

   When constraint_type = "only":
   - Put ALL mentioned shifts into shifts.start_day
   - Leave shifts.middle_days empty []
   -  Leave shifts.end_day empty []
2. Date-range shifts (NO constraint_type)
   If shifts are mentioned as part of a date range, such as:
   - "from friday morning to saturday evening"
   - "this friday night to sunday morning"

   Then:
   - DO NOT set constraint_type (leave it as empty string "")
   - Put shifts mentioned near the START date into shifts.start_day
   - Put shifts mentioned near the END date into shifts.end_day
   - Leave shifts.middle_days empty []
3. Normal shift mention WITHOUT "only"
   If the user mentions shifts normally WITHOUT using the word "only", for example:
   - "morning matches"
   - "evening games"
   - "morning and night slots"

   Then:
   - constraint_type = ""
   - Put ALL mentioned shifts into shifts.start_day
   - Leave shifts.middle_days empty []
   - Leave shifts.end_day empty []
4. No shift mentioned
   If the user does not mention any shifts:
   - Leave shifts.start_day empty []
   - Leave shifts.middle_days empty []
   - Leave shifts.end_day empty []
   - constraint_type = ""

TOURNAMENT DETAILS:
  - overs_per_match → extract ONLY if explicitly mentioned
  Examples:
  - "5 overs", "box cricket" → "5"
  - "T20" → "20"
  - total_matches → extract ONLY if explicitly stated
  - Do NOT calculate or infer matches
BUDGET, PRICE & RATING:
- budget → numeric value if mentioned ("under 30k" → "30000")
- price_semantic → words like "under", "cheap", "premium"
- rating_min → numeric only ("4+ rated" → "4")
- rating_semantic → "top rated", "best", etc.
PRICE & RATING RULES:
    - "cheap", "cheapest", "low price" → price_semantic = "cheaper"
    - "expensive", "premium" → price_semantic = "expensive"
    - "top rated", "best" → rating_semantic = "top_rated"
    - "low rated" → rating_semantic = "low_rated"

ALL extracted values MUST be placed inside the "filters" object.
query_text MUST always contain the original user query unchanged.

{format_instructions}
"""),
    ("human", "{query}")
]).partial(
    format_instructions=tournament_parser.get_format_instructions()
)

     
tournament_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.1,
    openai_api_key=settings.OPENAI_API_KEY
   )
tournament_chain = tournament_prompt | tournament_llm | tournament_parser

route_parser = PydanticOutputParser(pydantic_object=routedecison)
route_prompt = ChatPromptTemplate.from_messages([
    ("system", """
You decide whether the user reply is:
1) answering missing required fields
2) changing intent or giving a new request

Rules:
- Output JSON with keys:
    - route → "missing_fields" OR "full_parse"
    - confidence → a float between 0 and 1 (optional, default 1.0)
- If reply only contains values for missing fields → route = "missing_fields"
- If reply introduces booking intent, ground name, or new action → route = "full_parse"
- Output STRICT JSON ONLY.
"""),
    ("human", """
Missing fields: {required_fields}
User reply: {query}
""")
]).partial(
    format_instructions=route_parser.get_format_instructions()
)

route_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0
)
route_chain = route_prompt | route_llm | route_parser
tournament_missing_prompt = ChatPromptTemplate.from_messages([
    ("system", """
You are a STRICT JSON generator for a sports ground booking system.

The system is asking for the following missing fields:
{required_fields}

RULES (VERY IMPORTANT):
- Output FULL JSON schema
- You MUST fill the missing fields listed above IF AND ONLY IF they are clearly present
- You MAY extract additional CONTEXT fields such as city, area, or address IF explicitly mentioned
- Do NOT guess or force values into missing fields
- If a missing field is NOT clearly present, leave it as ""
- All other non-mentioned fields MUST be empty ""
- Do NOT infer or change intent
- Do NOT change booking_type
- Do NOT hallucinate values

Interpretation rules:
- Location names (area, city) are NOT ground or turf names
- Ground/turf names are usually proper names and may contain words like:
  ground, turf, stadium, arena, sports, academy

{format_instructions}
"""),
    ("human", "{query}")
]).partial(
    format_instructions=tournament_parser.get_format_instructions()
)

tournament_missing_chain = tournament_missing_prompt | normal_llm | tournament_parser

def interpretgroundquery(user_query, booking_type, required_fields):
    route = "full_parse"
    if required_fields:
        route_decision = route_chain.invoke({
            "required_fields": ", ".join(required_fields),
            "query": user_query
        })
        if route_decision.confidence >= 0.7:
            route = route_decision.route
    try:
        if booking_type == "normal_booking":
            if route == "missing_fields":
                print("Route chain input:", {
                "required_fields": ", ".join(required_fields),
                "query": user_query
                })
                output = missing_chain.invoke({
                    "required_fields": ", ".join(required_fields),
                    "query": user_query
                })
                data = output.dict()
                data["intent"] = data.get("intent") or "unknown"
                data["booking_type"] = booking_type 
            else:
                output = normal_chain.invoke({"query": user_query})
                data = output.dict()
                data["intent"] = (data.get("intent") or "unknown").lower()
                data["booking_type"] = booking_type
                data["filters"]["nearme"] = "true" if "near me" in user_query.lower() else "false"
            user_lower = user_query.lower()
            if not data["filters"]["ground_or_turf"]:
                if "ground" in user_lower:
                    data["filters"]["ground_or_turf"] = "ground"
                elif "turf" in user_lower:
                    data["filters"]["ground_or_turf"] = "turf"
            if data["filters"]["nearme"] == "true":
                data["filters"]["nearme"] = True
            else:
                data["filters"]["nearme"]=""
            Queryrecordground.objects.create(
                userquery=user_query,
                gptresponse=json.dumps(data)
            )
            return data
        elif booking_type == "tournament_booking":
            if route == "missing_fields":
                print("Tournament Route chain input:", {
                "required_fields": ", ".join(required_fields),
                "query": user_query
                })
                output = tournament_missing_chain.invoke({
                    "required_fields": ", ".join(required_fields),
                    "query": user_query
                })
                data = output.dict()
                data["intent"] = data.get("intent") or "unknown"
                data["booking_type"] = booking_type
            else:
                output = tournament_chain.invoke({"query": user_query})
                data = output.dict()
                data["intent"] = (data.get("intent") or "unknown").lower()
                data["booking_type"] = booking_type
            Queryrecordground.objects.create(
                    userquery=user_query,
                    gptresponse=json.dumps(data)
                )
            return data
        else:
            return {
                "intent": "show",
                "query_text": user_query
            }
    except Exception as e:
        logger.error(f"LangChain error: {e}")
        return {
            "intent": "show",
            "query_text": user_query
        }
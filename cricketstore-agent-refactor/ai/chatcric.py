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
    intent: Literal["show", "book", "cancel", "unknown", "general", ""]
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
- "general" → user says hi, hello, thanks, or asks unrelated questions
- "show" → user wants to search / view grounds
- "book" → user wants to reserve slots
- "cancel" → user wants to cancel booking
- "unknown" → unclear intent

TIME & DATE RULES:
- Extract raw date text exactly (e.g. "tomorrow", "this saturday")
- Extract timing text exactly (e.g. "5 to 7", "3 to 6")
- Detect shifts: morning / afternoon / evening / night
- Detect AM / PM if clearly mentioned

CONSTRAINT TYPE RULES — FOLLOW THIS PRIORITY:

1. EXPLICIT TIME RANGE:
   If the user gives BOTH a start time AND an end time,
   constraint_type MUST be "between".

   Examples:
   - "3 to 6" → timings = "3 to 6", constraint_type = "between"
   - "3 PM to 6 PM" → timings = "3 PM to 6 PM", constraint_type = "between"
   - "from 3 to 6" → timings = "3 to 6", constraint_type = "between"
   - "from 3 PM to 6 PM" → timings = "3 PM to 6 PM", constraint_type = "between"
   - "5-7 evening" → timings = "5-7", constraint_type = "between"

   IMPORTANT:
   The word "from" does NOT mean "after" when an end time is also
   provided. "from 3 to 6" is a complete time range and MUST be
   classified as "between".

2. AFTER / STARTING:
   Use constraint_type = "after" ONLY when the user provides
   a starting time WITHOUT an ending time.

   Examples:
   - "from 3 PM" → constraint_type = "after"
   - "starting at 5 PM" → constraint_type = "after"
   - "after 6 PM" → constraint_type = "after"

3. BEFORE / UNTIL:
   Use constraint_type = "before" when the user provides
   an ending time WITHOUT a starting time.

   Examples:
   - "until 6 PM" → constraint_type = "before"
   - "before 8 PM" → constraint_type = "before"

4. SHIFT ONLY:
   If the user only mentions a shift:
   - "evening" → shift = "evening"
   - "evening slots" → shift = "evening"

   Do NOT invent timings or constraint_type.

PRIORITY RULE:
An explicit start-to-end time range ALWAYS takes priority over
words such as "from", "starting", "after", "until", or "before".

PRICE RULES:
- "cheap", "cheapest", "low price" → price_semantic = "cheaper"
- "expensive", "premium" → price_semantic = "expensive"

RATING RULES:
- "top rated", "best" → rating_semantic = "top_rated"
- "low rated" → rating_semantic = "low_rated"

ALL extracted values MUST go inside "filters".

LOCATION RULES:
- If user says "near me", "nearby", "around me", "close to me":
  → set nearme = true
- Do NOT set radius_km unless explicitly mentioned

SPORT TYPE RULES:
- sporttype MUST be one of: cricket, football, hockey, badminton, tennis, volleyball
- Do NOT put anything else into sporttype, even if it contains the word "sport" or "sports"
- If the text looks like a proper venue name (e.g. contains "Sports", "Turf", "Arena",
  "Academy", "Stadium", or is clearly a business/place name), put it in
  ground_or_turf_name instead — NEVER in sporttype

GROUND/TURF NAME RULES:
- ground_or_turf_name → extract ONLY when a specific proper name is given
  (e.g. "Tiger 5 Sports", "XYZ Turf", "Champions Arena")
- Location words (city, area) are NOT ground/turf names

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

KNOWN CITIES (use this exact list to decide city vs area):
- bangalore (also written as: bangalore, bengaluru, banglore, bglr)
- mumbai (also written as: mumbai, bombay)
- delhi (also written as: delhi, new delhi, ndls)
- chennai (also written as: chennai, madras)
- kolkata (also written as: kolkata, calcutta)
- hyderabad (also written as: hyderabad, hyd)

CITY vs AREA CLASSIFICATION RULE (MANDATORY):
- If a location word/phrase in the reply matches one of the KNOWN CITIES above
  (including its listed spellings/aliases), put it in "city".
- If a location word/phrase does NOT match any KNOWN CITY or its aliases,
  it is a locality/neighbourhood — put it in "area" instead.
- NEVER put a KNOWN CITY name (or its alias) into "area".
- NEVER put a non-matching locality name into "city".
- Some known area names are indiranagar,lb nagar,mahadevapura,silk board,jubilee hills etc 

COMMA-SEPARATED REPLIES (MANDATORY):
When the reply has multiple comma-separated segments:
  - The 1st segment is always the field currently being asked for
    (e.g. ground_or_turf_name).
  - For every remaining segment, apply the CITY vs AREA rule above.
  - NEVER leave commas or extra location text inside ground_or_turf_name.

Examples:
  Reply: "Tiger 5 Sports, Indiranagar"
    -> ground_or_turf_name = "Tiger 5 Sports", area = "indiranagar"
  Reply: "Tiger 5 Sports, Bangalore"
    -> ground_or_turf_name = "Tiger 5 Sports", city = "Bangalore"
  Reply: "Tiger 5 Sports, Bengaluru"
    -> ground_or_turf_name = "Tiger 5 Sports", city = "Bengaluru"
  Reply: "Tiger 5 Sports, Doddankundi, Bangalore"
    -> ground_or_turf_name = "Tiger 5 Sports", area = "Doddankundi", city = "Bangalore"


SPORT TYPE RULES:
- sporttype MUST be one of: cricket, football, hockey, badminton, tennis, volleyball
- Do NOT put anything else into sporttype, even if it contains the word "sport" or "sports"
- If the text looks like a proper venue name (e.g. contains "Sports", "Turf", "Arena",
  "Academy", "Stadium", or is clearly a business/place name), put it in
  ground_or_turf_name instead — NEVER in sporttype

GROUND/TURF NAME RULES:
- ground_or_turf_name → extract ONLY when a specific proper name is given
  (e.g. "Tiger 5 Sports", "XYZ Turf", "Champions Arena")
- Location words (city, area) are NOT ground/turf names

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
- If reply introduces booking intent, new action → route = "full_parse"
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
        try:
            route_decision = route_chain.invoke({
                "required_fields": ", ".join(required_fields),
                "query": user_query
            })
            if route_decision.confidence >= 0.7:
                route = route_decision.route
        except Exception as e:
            logger.error(f"Route classification failed: {e}")
    try:
        if booking_type == "normal_booking":
            if route == "missing_fields":
                output = missing_chain.invoke({
                    "required_fields": ", ".join(required_fields),
                    "query": user_query
                })
                data = output.dict()
                data["intent"] = "unknown"
                data["booking_type"] = booking_type 
            else:
                output = normal_chain.invoke({"query": user_query})
                data = output.dict()
                data["intent"] = (data.get("intent") or "unknown").lower()
                data["booking_type"] = booking_type
                data["filters"]["nearme"] = "true" if "near me" in user_query.lower() else "false"
            user_lower = user_query.lower()
            timings = data["filters"].get("timings", "")
            if timings:
                timings_lower = timings.lower().strip()

                if " to " in timings_lower or "-" in timings_lower:
                    data["filters"]["constraint_type"] = "between"
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
                output = tournament_missing_chain.invoke({
                    "required_fields": ", ".join(required_fields),
                    "query": user_query
                })
                data = output.dict()
                data["intent"] = "unknown"
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
    
class ChatbotAskSchema(BaseModel):
    message: str

chatbot_ask_parser = PydanticOutputParser(
    pydantic_object=ChatbotAskSchema
)

chatbot_ask_prompt = ChatPromptTemplate.from_messages([
    ("system", """
You are a friendly sports ground booking assistant.

Your job:
- Rewrite the backend instruction into a natural chatbot message.
- Use the current context to make the question clear.
- Do NOT change the meaning.
- Do NOT invent details.
- Do NOT ask extra questions.
- Return ONLY valid JSON.
- Output must contain only this key: message.

{format_instructions}
"""),
    ("human", """
User query:
{query}

Current booking context:
{context}

Backend instruction:
{backend_message}
""")
]).partial(
    format_instructions=chatbot_ask_parser.get_format_instructions()
)

chatbot_ask_chain = chatbot_ask_prompt | normal_llm | chatbot_ask_parser

def frame_chatbot_message(query, context, backend_message):
    try:
        result = chatbot_ask_chain.invoke({
            "context": json.dumps(context, default=str),
            "backend_message": backend_message,
            "query": query
        })
        return result.message

    except Exception as e:
        return backend_message
    

class QueryRouteSchema(BaseModel):
    category: Literal["greeting", "off_topic", "my_bookings", "ground_info", "booking_action"]

query_route_parser = PydanticOutputParser(pydantic_object=QueryRouteSchema)

query_route_prompt = ChatPromptTemplate.from_messages([
    ("system", """
You classify a user's message into exactly one category for a sports ground booking assistant.

Categories:
- "greeting": hi, hello, thanks, bye, small talk with no booking content
- "off_topic": anything unrelated to sports ground booking (weather, general knowledge, coding help, news, other companies, etc.)
- "my_bookings": user asks about their own existing bookings, booking history, or booking status
- "ground_info": user asks about a specific ground/turf's details, facilities, parking, timings, pricing, or whether it's open — without wanting to book right now
- "booking_action": user wants to search, book, cancel, reschedule, or plan a tournament

Rules:
- Output STRICT JSON only, one key: category
- If the message contains any explicit intent to reserve/book/confirm a slot — even if it also mentions ground details, price, or facilities — ALWAYS classify as "booking_action", never "ground_info".
- "ground_info" is ONLY for messages asking about a ground's details, facilities, timings, or pricing WITHOUT wanting to book right now.
- When in doubt between booking_action and another category, prefer booking_action
"""),
    ("human", "{query}")
]).partial(format_instructions=query_route_parser.get_format_instructions())

query_route_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, openai_api_key=settings.OPENAI_API_KEY)
query_route_chain = query_route_prompt | query_route_llm | query_route_parser

def classify_query(query):
    try:
        result = query_route_chain.invoke({"query": query})
        return result.category
    except Exception as e:
        logger.error(f"Query route classification failed: {e}")
        return "booking_action"


class GroundInfoFilters(BaseModel):
    ground_or_turf_name: str = ""
    city: str = ""
    area: str = ""

ground_info_parser = PydanticOutputParser(pydantic_object=GroundInfoFilters)
ground_info_prompt = ChatPromptTemplate.from_messages([
    ("system", """
Extract the ground/turf name, city, and area mentioned in the user's question about a specific sports ground, if present.
Leave a field as "" if not explicitly mentioned. Do NOT guess or invent a name.
Output STRICT JSON only.

{format_instructions}
"""),
    ("human", "{query}")
]).partial(format_instructions=ground_info_parser.get_format_instructions())
ground_info_chain = ground_info_prompt | normal_llm | ground_info_parser

def extract_ground_info_query(query):
    try:
        result = ground_info_chain.invoke({"query": query})
        return result.dict()
    except Exception as e:
        logger.error(f"Ground info extraction failed: {e}")
        return {"ground_or_turf_name": "", "city": "", "area": ""}


class DataAnswerSchema(BaseModel):
    message: str

data_answer_parser = PydanticOutputParser(pydantic_object=DataAnswerSchema)

data_answer_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.1,
    max_tokens=220,
    openai_api_key=settings.OPENAI_API_KEY
)

data_answer_prompt = ChatPromptTemplate.from_messages([
    ("system", """
You are a sports ground booking assistant. Answer the user's question using ONLY the data provided below.
Do NOT invent grounds, facilities, or values not present in the data.
If the data indicates the ground/booking wasn't found, say so naturally and offer to help find one instead.

LENGTH RULES (VERY IMPORTANT):
- If the data contains a SINGLE item (one booking or one ground), you may answer in detail — include the fields relevant to what the user asked.
- If the data contains MULTIPLE items (a list of bookings), do NOT list every field for every item.
  Summarize concisely instead: e.g. counts by status ("3 upcoming, 1 cancelled"), and only
  call out specific bookings if the user's question needs it (e.g. "which one is today").
- Keep the whole answer under about 120 words unless the user explicitly asks for full details.
- Never dump raw JSON or field names back to the user — always phrase it naturally.

Return ONLY valid JSON with one key: message.

{format_instructions}
"""),
    ("human", """
User query:
{query}

Data (JSON):
{data}
""")
]).partial(format_instructions=data_answer_parser.get_format_instructions())

data_answer_chain = data_answer_prompt | data_answer_llm | data_answer_parser


def answer_from_data(query, data):
    try:
        result = data_answer_chain.invoke({"query": query, "data": json.dumps(data, default=str)})
        return result.message
    except Exception as e:
        logger.error(f"Data answer chain failed: {e}")
        return "Here's what I found."

def off_topic_response():
    return (
        "I'm built specifically to help with sports ground and tournament bookings, "
        "so I can't help with that — but I'm happy to help you find a ground, check a booking, or plan a tournament!"
    )

general_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.4,
    openai_api_key=settings.OPENAI_API_KEY
)

general_prompt = ChatPromptTemplate.from_messages([
    ("system", """
You are a friendly sports ground booking assistant.

The user may give casual/general messages like hi, hello, yes, ok, thanks, help, what can you do, etc.

Your responsibilities:
- Understand spelling mistakes and interpret the user's intended meaning.
- Be conversational and friendly.
- If the user greets you, welcome them and explain what you can help with.
- You can help users:
  * find sports grounds and turfs
  * recommend venues
  * show venue details
  * check availability
  * make bookings
  * cancel or reschedule bookings
- If a city is provided, use it naturally in your response.
- Never ask for the city again when it is already known.
- Guide the user toward the next useful step.
- Keep responses concise but natural.
- Respond like a helpful booking agent, not like a form asking for fields.

Examples:

User: hi
Known City: Bangalore
Response:
Hi! Welcome to Booking Agent. I can help you find sports grounds and turfs in Bangalore, recommend venues, or book a slot for you.

User: yes
Known City: Bangalore
Response:
Great! I can help you find grounds, check availability, or make a booking in Bangalore. What would you like to do?

User: what can you do
Known City: Bangalore
Response:
I can help you discover grounds, check venue details, recommend turfs, and book slots in Bangalore. Just tell me what you're looking for.

User: bok turff in banglre
Known City: Bangalore
Response:
Sure! I can help you book a turf in Bangalore. Tell me the area, sport, date, and time.

Never respond with:
"Which city are you interested in?"
when a city is already known.
"""),
    ("human", """
User Query: {query}

Known City: {city}
""")
])

general_query_chain = general_prompt | general_llm


def handle_general_query(query, city=None):
    try:
        response = general_query_chain.invoke({
            "query": query,
            "city": city or "Not provided"
        })
        return response.content
    except Exception as e:
        logger.error(f"General query chain failed: {e}")
        return "Hi! I can help you find sports grounds, check availability, or make a booking. What would you like to do?"

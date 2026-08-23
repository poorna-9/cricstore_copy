# Cricstore – Smart Sports Booking & Commerce Platform

Cricstore is an end-to-end sports platform that allows users to:

- Book cricket grounds and turfs
- Use natural language prompts for smart bookings
- Purchase sports-related products
- Plan tournaments efficiently using algorithmic scheduling

The platform combines booking automation, intelligent planning, and e-commerce into a single system.

## Key Features

### Ground & Turf Booking
- Manual booking using date, time, and location
- Availability validation
- Conflict-free scheduling

### Prompt-Based Smart Booking
Users can enter prompts like:

> "Book a turf for 8 teams next Saturday evening"

The system:
- Parses intent
- Extracts constraints
- Automatically plans and books slots

### Conversational Booking Agent (AI-Orchestrated)
The booking agent isn't a single LLM call bolted onto the UI — it's a chained pipeline where the AI layer drives the actual backend control flow, not just text generation:
- A **routing chain** first classifies each user reply as either "answering a previously asked missing field" or "a fresh request with new intent," so the agent knows whether to merge the reply into existing context or re-interpret it from scratch
- Based on that routing decision, the query is handed to one of several **structured extraction chains** (separate chains for normal bookings vs. tournament bookings, and separate prompts for "full parse" vs. "fill in only the missing fields"), each constrained to a strict Pydantic schema so the LLM's output can be trusted and merged directly into session state
- A **response-framing chain** takes the backend's raw next-step instruction (e.g. "ask for area") and rewrites it into a natural, context-aware chatbot message — so the same backend logic can produce different, situationally appropriate wording instead of static hardcoded strings
- A **general-conversation chain** handles greetings, thanks, and off-topic small talk without derailing the booking flow or losing accumulated context
- The extracted filters accumulate turn-by-turn into a per-session context dict, so users can build up a booking across multiple natural messages (e.g. sport → city → area → date → time) without repeating themselves, with automatic session expiry after a period of inactivity

### Sports Products Marketplace
- Browse sports equipment
- Add to cart
- Size selection support
- Secure checkout flow

### Tournament Planning (Algorithmic)
- Match scheduling
- Resource optimization
- Conflict minimization using bitmask search with memoization

## System Architecture

```
Client (User / Admin)
        |
        v
API / Views Layer
        |
        v
AI Orchestration Layer (LangChain: routing → extraction → response framing)
        |
        v
Service Layer (Booking Agent Logic)
        |
        v
Algorithm Layer (DP / Optimization)
        |
        v
Database Layer (Teams, Matches, Venues)
```

### Key Layers
- **Presentation Layer**: Admin or user requests (create tournament, book matches)
- **AI Orchestration Layer**: For natural-language requests, this layer decides intent, extracts structured filters, and frames the reply — it sits *in* the control path rather than alongside it, meaning the AI's routing decision determines which backend branch actually executes next
- **Service Layer**: Core booking and validation logic
- **Algorithm Layer**: Tournament planning using memoized search over shift availability
- **Data Layer**: Persistent storage for teams, schedules, venues

## Workflow

1. **Tournament Creation** — Admin defines tournament type (league / knockout); teams and constraints are registered
2. **Constraint Collection** — Venue availability, team availability, match duration, tournament deadline
3. **Tournament Planning** — Optimal match scheduling, conflict minimization, resource utilization optimization
4. **Booking & Confirmation** — Matches are booked, schedule is finalized, conflicts are resolved automatically
5. **Execution & Updates** — Match status updates, rescheduling if needed

## Algorithmic Approach

### Bitmask Search with Memoization for Tournament Planning

Used to:
- Optimize match schedules across a date range against per-day shift availability
- Minimize overlaps and respect budget constraints
- Ensure fair rest periods for teams

**Example approach**: for each day in the tournament window, available shifts (morning / afternoon / evening / night) are represented as a bitmask. A memoized depth-first search explores which combination of shifts to book on each day, tracking cumulative matches scheduled and cumulative cost, to either:
- find the cheapest schedule that hits the required number of matches (budgeted mode), or
- confirm whether the target number of matches is achievable at all within the date range (feasibility check mode)

This approach ensures:
- Efficient planning
- Scalability for realistic tournament sizes
- Predictable performance

## Case Handling & Validations

### Conflict Handling
- Team already scheduled at the same time
- Venue unavailable
- Exceeded daily match limits

### Edge Cases
- Odd number of teams
- Last-minute team withdrawal
- Partial availability
- Tournament deadline constraints

### Fail-safe Logic
- Rollback on invalid booking (row-level locking + atomic transactions on slot reservation)
- Recompute schedule using the scheduling algorithm
- Graceful error messages, with LLM-parsing fallbacks that degrade to a safe default response instead of crashing the booking flow

## Security Hardening

As part of preparing this project for the Razorpay Buildathon, the following fixes were made to the payment and booking flow:

| # | Issue | Fix |
|---|-------|-----|
| 1 | Razorpay signature was compared with `==`, which is vulnerable to timing attacks | Switched to `hmac.compare_digest()` for constant-time comparison |
| 2 | `payment_success` had no idempotency check — a duplicate callback/retry could double-book slots and create duplicate orders | Added a guard that checks `payment.status` before running fulfillment logic, so repeat calls are safely no-ops |
| 3 | Money amounts were calculated using Python `float`, risking rounding drift on prices | Switched price/total calculations to Python's `Decimal` type |
| 4 | `@csrf_exempt` was applied to an authenticated, non-webhook endpoint (`reservetournamentday`) with no equivalent protection in its place | Removed `csrf_exempt`; the endpoint now relies on Django's standard CSRF token flow. `payment_success` retains `csrf_exempt` intentionally, since it is protected by Razorpay's HMAC signature verification instead |

## Testing Strategy

- Unit tests for scheduling logic
- Constraint validation tests
- Edge-case simulation (overlaps, failures)
- Stress testing with large tournaments

## Future Enhancements

- AI-based schedule prediction
- Real-time rescheduling
- REST API integration
- Frontend dashboard
- Multi-sport support
- Cloud deployment
- Distributed systems

## Tech Stack

- **Backend**: Python / Django
- **AI / Orchestration**: LangChain (chained prompts for routing, structured extraction, and response framing), Pydantic output parsing, OpenAI (gpt-4o-mini) as the underlying LLM
- **Algorithms**: Bitmask search with memoization, interval/date-range constraint solving
- **Database**: PostgreSQL
- **Cache / Locking**: Redis (session state, slot/shift locking with TTL-based expiry)
- **Payments**: Razorpay
- **Version Control**: Git & GitHub

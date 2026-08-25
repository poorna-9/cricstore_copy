# Cricstore – Smart Sports Booking & Commerce Platform

Cricstore is an end-to-end sports platform that allows users to:

- Book cricket grounds and turfs
- Use natural language prompts for smart bookings
- Purchase sports-related products
- Plan tournaments efficiently using algorithmic scheduling

The platform combines booking automation, intelligent planning, and e-commerce into a single system — with a clear boundary between what the AI is allowed to decide and what always runs through deterministic, auditable backend code.

## Key Features

### Ground & Turf Booking
- Manual booking using date, time, and location
- Availability validation
- Conflict-free scheduling

### Prompt-Based Smart Booking
Users can enter prompts like:

> "Book a turf for 8 teams next Saturday evening"

The system parses intent, extracts constraints, and plans and books slots automatically.

### Sports Products Marketplace
- Browse sports equipment
- Add to cart
- Size selection support
- Secure checkout flow

### Tournament Planning (Algorithmic)
- Match scheduling
- Resource optimization
- Conflict minimization using bitmask search with memoization

## How the AI Is Actually Used

This is the core design decision behind the project, so it's worth stating explicitly: **the AI extracts and informs — it never directly executes a booking, payment, or cancellation.** Every query is routed by type, and only some of those routes give the AI any real agency:

| Query type | Who's in control |
|---|---|
| Greetings, thanks, small talk | Answered directly by a lightweight conversational chain — no booking context touched |
| Informational lookups (ground details, "my bookings", venue status) | The AI itself calls read-only backend APIs and composes the natural-language response |
| Booking, cancellation, payment, scheduling | The AI only extracts structured intent — every state change (locks, orders, payments) executes through deterministic Django code that the AI cannot bypass |

### The conversational pipeline

- **Routing chain** — before anything else, a chain classifies each reply as either *"continuing a previous request"* (the user is answering a specific missing field the backend just asked for) or *"a fresh request with new intent."* This decision determines whether the reply gets merged into existing session context or re-parsed from scratch — without it, a short reply like "3" or "evening" would be ambiguous and could derail an in-progress booking.
- **Structured extraction chains** — separate chains for normal bookings vs. tournament bookings, and separate prompts for "full parse" vs. "fill in only the missing field(s)." Every chain is constrained to a strict Pydantic schema, so the model's output can be trusted and merged directly into session state rather than treated as free text.
- **Deterministic fallback layer** — LLMs are notably unreliable on short, context-free replies (e.g. answering "3" to "how many hours?"). Whenever exactly one field is outstanding, a regex/word-number parser runs on the raw reply as a backstop if the LLM comes back empty — so the conversation doesn't get stuck re-asking a question the user already answered.
- **Response-framing chain** — turns a raw backend instruction (e.g. "ask for area") into a natural, context-aware message, so the same backend logic can produce different, situationally appropriate wording instead of static hardcoded strings.
- **Context memory with explicit reset rules** — extracted filters accumulate turn-by-turn into a per-session context dict, so a booking can be built up across multiple natural messages (sport → city → area → date → time) without repeating anything. Context is reset on session timeout, reset (except city) on switching between booking modes, and has in-progress state (like a pending tournament confirmation) cleared whenever the user's intent genuinely changes mid-flow — so stale state can't leak into an unrelated request.
- **Fuzzy matching as a second line of defense** — ground names, areas, and city spellings are matched exactly first; if that returns nothing, a fuzzy word-match against known values runs before giving up, so a typo or spelling variant doesn't produce a false "not found."

## Booking Flow: Locking & Concurrency

Booking correctness is enforced by two layers working together, not by the AI:

1. **Redis, first line of defense** — the moment a user selects a slot, a short-lived lock is taken in Redis, keyed by ground, date, and slot (or shift, for tournaments). If the user abandons the booking, the lock's TTL expires automatically and the slot frees itself — no manual cleanup or background sweep required for the common case.
2. **PostgreSQL, source of truth** — underneath Redis, actual slot state changes happen inside `transaction.atomic()` blocks using `select_for_update()` row locks. Even if two requests land at the exact same instant, only one can win the row lock — this is what actually guarantees no double-booking, with Redis providing the fast-path UX on top.

Tournament bookings lock at the shift level (not just individual slots), so two users can't both reserve "evening on the 26th" at the same ground.

## Payments (Razorpay)

- **Dual, independent confirmation** — payment success is confirmed two ways: the client-side callback from Razorpay Checkout, *and* a signed server-to-server webhook. Both are necessary in production, since a user closing their browser right after paying would otherwise leave the server never knowing the payment succeeded.
- **Two separate signature verifications** — `verify_payment_signature` (client callback, HMAC over order_id + payment_id) and `verify_webhook_signature` (webhook body, using a distinct `RAZORPAY_WEBHOOK_SECRET`). Neither path trusts the request without cryptographic verification.
- **Idempotent by design** — both confirmation paths converge on the same finalize function, which checks `payment.status` inside a `select_for_update()` transaction before doing anything. A duplicate callback, retry, or webhook redelivery is always a safe no-op — it can never double-book a slot or create a duplicate order.
- **Real refunds, not just a message** — cancellation calls Razorpay's refund API directly and persists the actual `razorpay_refund_id` and refund status on the payment record, rather than just displaying a "refund initiated" string with no API call behind it.
- **Expiry-aware checkout** — every payment has a fixed expiry window. If it fails or is abandoned with time still remaining, the user is redirected back to checkout to retry against the same locked slots; once the window expires, the order is automatically cancelled and the slots are released.

## Algorithmic Approach: Bitmask Search with Memoization

Used for tournament scheduling to:
- Optimize match placement across a date range against per-day, per-shift availability
- Minimize overlaps and respect budget constraints
- Stop as soon as the required number of matches is achievable — it doesn't need every requested shift to be free, only enough of them

**How it works**: for each day in the tournament window, the four possible shifts (morning / afternoon / evening / night) are represented as bits in a bitmask, built from real slot availability (a slot already booked or blocked is excluded from the mask). A memoized depth-first search then explores which combination of available shifts to use on each day, tracking cumulative matches scheduled and cumulative cost, in two modes:
- **Budgeted mode** — find the cheapest schedule that hits the required number of matches
- **Feasibility mode** — confirm whether the target number of matches is achievable at all within the date range, ignoring cost

Because the search stops the moment enough matches are scheduled, a single blocked slot doesn't disqualify an otherwise-available ground — only the actually-unavailable shifts are excluded from the pool the algorithm draws from.

## System Architecture

```
Client (User / Admin)
        |
        v
API / Views Layer
        |
        v
Request Router (general chat / AI-assisted info lookup / booking control)
        |
        v
AI Orchestration Layer (LangChain: routing → extraction → response framing)
        |
        v
Service Layer (Booking Agent Logic, Locking, Payments)
        |
        v
Algorithm Layer (Bitmask-DFS Scheduling)
        |
        v
Database Layer (Ground, Slots, Sessions, Orders, Payments)
```

### Key Layers
- **Presentation Layer**: Admin or user requests (create tournament, book matches, browse grounds)
- **Request Router**: Decides upfront how much control the AI gets for this message — none (small talk), read-only (informational queries via AI-called APIs), or extraction-only (booking/payment flows)
- **AI Orchestration Layer**: Decides intent, extracts structured filters, and frames replies for natural-language requests — but only ever produces data for the service layer to act on, never acts directly
- **Service Layer**: Core booking, cancellation, and validation logic; owns all Redis/Postgres locking and Razorpay integration
- **Algorithm Layer**: Tournament planning via memoized bitmask search over shift availability
- **Data Layer**: Persistent storage for grounds, slots, sessions, orders, and payments

## Case Handling & Validations

### Conflict Handling
- Slot/shift already reserved or booked
- Ground unavailable for the requested date range
- Exceeded per-day match capacity

### Edge Cases
- Ambiguous or misspelled ground/area names (resolved via fuzzy matching)
- Terse single-word replies to a specific missing-field question (resolved via the deterministic fallback parser)
- Mid-conversation mode switches (normal booking → tournament, or → cancellation) without losing already-known facts like city
- Payment abandoned mid-flow, with or without remaining time on the window

### Fail-safe Logic
- Rollback on invalid booking (row-level locking + atomic transactions on every slot/shift reservation)
- LLM call failures (timeouts, API errors) degrade to a safe, explicit "please repeat that" response rather than corrupting session context or crashing the request
- Idempotent payment finalization prevents duplicate fulfillment under retries or concurrent webhook/callback delivery

## Security Hardening

The following fixes were made to the payment and booking flow as part of hardening this project for the Razorpay Buildathon:

| # | Issue | Fix |
|---|-------|-----|
| 1 | Razorpay client-side signature previously compared with `==`, vulnerable to timing attacks | Verification now goes through Razorpay SDK's `verify_payment_signature`, which performs constant-time comparison internally |
| 2 | Payment confirmation had no idempotency check — a duplicate callback/webhook retry could double-book slots and create duplicate orders | Both confirmation paths check `payment.status` inside a `select_for_update()` transaction before running fulfillment logic, so repeat calls are safe no-ops |
| 3 | Money amounts were calculated using Python `float`, risking rounding drift on prices | Price/total calculations use Python's `Decimal` type |
| 4 | Cancellation displayed a "refund initiated" message with no actual Razorpay API call behind it | Cancellation now calls Razorpay's refund API directly and persists the real refund ID and status |
| 5 | `@csrf_exempt` was applied to authenticated, non-webhook endpoints (`reserveslot`, `reservetournamentday`) with no equivalent protection in its place | Removed `csrf_exempt`; these endpoints now rely on Django's standard CSRF token flow. `payment_success` and the Razorpay webhook retain `csrf_exempt` intentionally, since they're protected by signature verification instead |
| 6 | Plain substring filters (`city=`, `address__icontains=`) silently returned zero results on spelling variants | City filtering uses an alias-aware query; area/ground-name matching falls back to fuzzy word-matching when an exact match fails |

## Tech Stack

- **Backend**: Python / Django
- **AI / Orchestration**: LangChain (chained prompts for routing, structured extraction, and response framing), Pydantic output parsing, OpenAI (gpt-4o-mini) as the underlying LLM
- **Algorithms**: Bitmask search with memoization, interval/date-range constraint solving
- **Database**: PostgreSQL
- **Cache / Locking**: Redis (session state, slot/shift locking with TTL-based expiry)
- **Background Jobs**: Celery & Celery Beat (slot generation, expired-session cleanup)
- **Search**: Elasticsearch
- **Events**: Kafka (booking event streaming)
- **Payments**: Razorpay
- **Infra**: Docker Compose, nginx
- **Version Control**: Git & GitHub

## Future Enhancements

- AI-based schedule prediction
- Real-time rescheduling
- REST API for third-party integration
- Frontend dashboard for admins
- Multi-sport support beyond current catalog
- Automated test suite for scheduling and payment logic
- Distributed/cloud deployment

# 🏏 Cricstore — AI-Powered Sports Booking & Tournament Platform

Cricstore is an **end-to-end sports platform** that combines conversational AI, sports venue booking, tournament planning, and e-commerce into a single system.

Users can interact with Cricstore using **natural language**, allowing the platform to understand their requirements and perform actions such as finding grounds, making bookings, checking existing bookings, cancelling bookings, and planning tournaments.

The system combines **LLM-based intent and constraint extraction with deterministic backend business logic**, ensuring that the AI understands the user's request while the backend remains responsible for availability, validation, reservations, pricing, and booking state.

---

## 🚀 Key Features

### 🤖 Conversational AI Booking Agent

Users can interact with Cricstore using natural language instead of navigating through multiple forms.

Example:

> "Book me a cricket turf in Doddankundi tomorrow evening."

The agent can understand and extract information such as:

* Intent
* Sport
* Ground/turf
* Location
* Date
* Time
* Shift
* Booking type
* Other booking constraints

The extracted information is then passed to the appropriate backend workflow.

---

### 🏟️ Normal Ground & Turf Booking

Cricstore supports regular sports venue bookings with:

* Cricket ground and turf booking
* Date and time selection
* Sport selection
* Location and area filtering
* Ground/turf selection
* Availability validation
* Slot validation
* Booking confirmation
* Conflict prevention

The system validates the requested slots against the actual booking state before confirming a reservation.

---

### 🔎 Ground Discovery & Custom Filters

Users can ask the agent to find grounds based on their requirements.

Examples:

> "Show me cricket turfs in Doddankundi."

> "Show me grounds near Bangalore."

> "Find cricket turfs matching my requirements."

The agent can collect relevant filters and return suitable grounds instead of forcing the user through a traditional search form.

---

### 📅 My Bookings & Booking Queries

Users can interact with their existing bookings through natural language.

Supported workflows include:

* View bookings
* Query previous bookings
* Query upcoming bookings
* Find a specific booking
* Retrieve booking information
* Handle booking-related questions

The agent can distinguish between a new booking request and a request concerning an existing booking.

---

### ❌ Booking Cancellation

Cricstore supports conversational cancellation workflows.

Users can request cancellation through natural language, after which the system:

1. Identifies the relevant booking
2. Validates the booking state
3. Performs the cancellation workflow
4. Updates the booking state
5. Releases the associated booking resources where applicable

---

### 💬 General & Ground-Related Queries

The agent is not limited to booking requests.

It can handle:

* General questions
* Ground-related questions
* Sports-related venue queries
* Booking-related questions
* Availability-related queries
* Ground information requests

This allows Cricstore to behave as a **general conversational sports assistant**, rather than simply a booking form implemented through chat.

---

### 🏆 Tournament Booking

Cricstore supports tournament-level venue booking.

A user can provide a high-level requirement such as:

> "Book me a turf for conducting a tournament starting from tomorrow evening to 31st August night."

The agent collects the required tournament information and generates a booking plan based on:

* Tournament duration
* Sport
* Ground/turf
* Number of matches
* Match duration / overs
* Available shifts
* Venue availability
* Pricing
* Tournament constraints

---

### 📊 Tournament Schedule Generation

The tournament workflow generates a structured schedule containing:

* Tournament dates
* Available shifts
* Matches per shift
* Match allocation
* Daily match totals
* Daily cost
* Overall tournament cost

Example schedule:

```text
Date: August 30, 2026

Morning     → 2 matches
Afternoon   → 2 matches
Evening     → 3 matches
Night       → 3 matches

Total       → 10 matches
Daily Cost  → ₹14,500
```

The generated schedule can then be used as the basis for the tournament booking and checkout workflow.

---

### 🛒 Sports Products Marketplace

Cricstore also includes an e-commerce component for sports-related products.

Features include:

* Product browsing
* Product selection
* Size selection
* Cart management
* Checkout workflow
* Sports equipment purchasing

This allows the platform to combine **sports venue booking and sports commerce** in one application.

---

# 🧠 AI Architecture

The AI layer is designed so that the LLM is responsible primarily for **understanding the user's request**, while deterministic application code handles business-critical operations.

```text
User Natural Language
        │
        ▼
┌─────────────────────┐
│   Booking Agent     │
│                     │
│ Intent Detection    │
│ Context Extraction  │
│ Constraint Parsing  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   Routing Layer     │
│                     │
│ Normal Booking      │
│ Cancellation        │
│ My Bookings         │
│ Ground Queries      │
│ Tournament Booking  │
│ General Queries     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   Service /         │
│   Business Logic    │
│                     │
│ Validation           │
│ Availability         │
│ Slot Management     │
│ Booking Logic       │
│ Tournament Planning │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   Database Layer    │
│                     │
│ Users               │
│ Grounds             │
│ Slots               │
│ Bookings            │
│ Tournaments         │
│ Products            │
└─────────────────────┘
```

### Why this architecture?

The LLM does **not directly decide whether a booking is valid**.

Instead:

```text
LLM
 ↓
Understand request
 ↓
Extract structured information
 ↓
Route request
 ↓
Deterministic backend
 ↓
Validate availability
 ↓
Create / modify booking
```

This separation makes the system more predictable and prevents natural-language interpretation from bypassing critical booking rules.

---

# 🏗️ System Architecture

```text
                         ┌──────────────────────┐
                         │        User          │
                         │  Web / Chat Interface│
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │   Django Views / API │
                         └──────────┬───────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
          ┌──────────────────┐            ┌──────────────────┐
          │  AI Agent Layer  │            │ Traditional      │
          │                  │            │ Application Flow │
          │ Intent Detection │            │                  │
          │ Context Parsing  │            │ Forms / APIs     │
          │ Query Routing    │            │ Admin Operations │
          └────────┬─────────┘            └────────┬─────────┘
                   │                               │
                   └───────────────┬───────────────┘
                                   │
                                   ▼
                         ┌──────────────────────┐
                         │   Service / Business │
                         │       Logic          │
                         └──────────┬───────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                │                   │                   │
                ▼                   ▼                   ▼
       ┌────────────────┐  ┌────────────────┐  ┌────────────────┐
       │ Normal Booking │  │  Cancellation  │  │   Tournament   │
       │ & Availability │  │    Workflow    │  │    Planning    │
       └───────┬────────┘  └───────┬────────┘  └───────┬────────┘
               │                   │                   │
               └───────────────────┼───────────────────┘
                                   │
                                   ▼
                         ┌──────────────────────┐
                         │      PostgreSQL      │
                         │                      │
                         │ Users                │
                         │ Grounds              │
                         │ Slots                │
                         │ Bookings             │
                         │ Tournament Sessions  │
                         │ Tournament Days      │
                         │ Products             │
                         └──────────────────────┘
```

---

# 🔄 Conversational Booking Flow

```text
User
 │
 │ "Book me a cricket turf tomorrow evening"
 ▼
AI Agent
 │
 ├── Detect Intent
 │      └── Booking
 │
 ├── Extract Constraints
 │      ├── Sport = Cricket
 │      ├── Venue = Turf
 │      ├── Date = Tomorrow
 │      └── Time = Evening
 │
 ▼
Missing Information?
 │
 ├── YES ──► Ask user for missing information
 │
 └── NO
       │
       ▼
Find Matching Grounds
       │
       ▼
Check Availability
       │
       ▼
Calculate / Validate Slots
       │
       ▼
Reserve Booking
       │
       ▼
Confirm Booking
```

---

# 🏆 Tournament Booking Flow

```text
User
 │
 │ Natural language tournament request
 ▼
Tournament Intent Detection
 │
 ▼
Extract Tournament Constraints
 │
 ├── Sport
 ├── Ground / Turf
 ├── Start Date
 ├── End Date
 ├── Shifts
 ├── Number of Matches
 └── Match Requirements
 │
 ▼
Validate Ground
 │
 ▼
Check Slot Availability
 │
 ▼
Generate Tournament Schedule
 │
 ▼
Calculate Match Allocation
 │
 ▼
Calculate Daily Cost
 │
 ▼
Calculate Total Tournament Cost
 │
 ▼
Display Tournament Schedule
 │
 ▼
Tournament Checkout / Booking
```

---

# 🔐 Booking & Conflict Handling

The backend validates booking requests before committing them.

The system handles cases such as:

### Slot Conflicts

* Requested slot already booked
* Overlapping booking
* Venue unavailable
* Invalid requested time

### Tournament Conflicts

* Venue unavailable on a tournament date
* Insufficient available slots
* Invalid tournament range
* Scheduling outside the requested shifts

### Booking Safety

* Validation before reservation
* Database transactions
* Conflict detection
* Rollback on failed operations
* Consistent booking state

The AI layer can interpret a flexible user request, but the final booking decision is made by the backend.

---

# 🧪 Tested Workflows

The current system has been tested across multiple conversational and transactional workflows.

### Booking

* Normal ground/turf booking
* Date and time based booking
* Sport-based booking
* Location-based booking
* Shift-based booking

### Booking Management

* Cancellation
* My bookings
* Booking-specific queries
* Existing booking lookup

### Ground Queries

* Ground information
* Ground discovery
* Location filtering
* Sport filtering
* Custom ground filters

### Tournament

* Tournament booking
* Tournament schedule generation
* Multiple-day tournament planning
* Shift-based match allocation
* Tournament cost calculation

### General Conversation

* General queries
* Booking-related questions
* Ground-related questions
* Context-aware follow-up questions

---

# 🛠️ Tech Stack

### Backend

* **Python**
* **Django**

### AI

* **LLM-based intent detection**
* Natural language constraint extraction
* Conversational context handling
* Query classification and routing

### Database

* **PostgreSQL**

### Frontend

* HTML
* CSS
* JavaScript
* Django Templates

### Algorithms & Problem Solving

* Scheduling algorithms
* Constraint validation
* Slot allocation
* Conflict detection
* Optimization techniques

### Development

* Git
* GitHub

---

# 📂 Major Application Components

```text
cricstore/
│
├── ai/
│   └── chatcric.py
│
├── bookings/
│   ├── models.py
│   ├── views.py
│   ├── templates/
│   ├── static/
│   └── migrations/
│
├── products/
│   └── ...
│
├── users/
│   └── ...
│
└── manage.py
```

The exact module structure may evolve as the application grows.

---

# ▶️ How to Run

Clone the repository:

```bash
git clone https://github.com/poorna-9/cricstore_copy.git
cd cricstore_copy
```

Create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate
```

On Windows:

```bash
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure the PostgreSQL database and required environment variables.

Run migrations:

```bash
python manage.py migrate
```

Start the Django development server:

```bash
python manage.py runserver
```

The application will then be available through the Django development server.

---

# 📈 Future Enhancements

Potential future improvements include:

* Real-time availability updates
* Real-time tournament rescheduling
* Improved recommendation and ranking of grounds
* Advanced tournament optimization
* Multi-sport tournament support
* Mobile application
* Payment gateway integration
* Cloud deployment
* Advanced analytics dashboard
* Automated notifications
* Scalable asynchronous booking infrastructure

---

# 🎯 Project Highlights

Cricstore demonstrates how **conversational AI can be integrated with a real transactional backend**.

The project goes beyond a simple chatbot by connecting natural-language interaction to actual application workflows:

```text
Natural Language
       ↓
Intent Understanding
       ↓
Constraint Extraction
       ↓
Context / Query Routing
       ↓
Business Logic
       ↓
Availability Validation
       ↓
Booking / Cancellation / Scheduling
       ↓
Persistent Database State
```

The result is a sports platform where users can interact with complex booking functionality using **simple natural-language conversations** while the underlying system maintains deterministic business rules and transactional integrity.

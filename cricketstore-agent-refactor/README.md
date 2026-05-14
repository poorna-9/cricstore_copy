# Cricstore – Smart Sports Booking & Commerce Platform

Cricstore is an **end-to-end sports platform** that allows users to:
- Book **cricket grounds and turfs**
- Use **natural language prompts** for smart bookings
- Purchase **sports-related products**
- Plan tournaments efficiently using **algorithmic scheduling**

The platform combines **booking automation, intelligent planning, and e-commerce** into a single system.

---

## Key Features

###  Ground & Turf Booking
- Manual booking using date, time, and location
- Availability validation
- Conflict-free scheduling

### Prompt-Based Smart Booking
Users can enter prompts like:
> *"Book a turf for 8 teams next Saturday evening"*  

The system:
- Parses intent
- Extracts constraints
- Automatically plans and books slots

### 🛒 Sports Products Marketplace
- Browse sports equipment
- Add to cart
- Size selection support
- Secure checkout flow

###  Tournament Planning (Algorithmic)
- Match scheduling
- Resource optimization
- Conflict minimization using **Dynamic Programming**

---

##  System Architecture

��Client (User / Admin)
|
v
API / Views Layer
|
v
Service Layer (Booking Agent Logic)
|
v
Algorithm Layer (DP / Optimization)
|
v
Database Layer (Teams, Matches, Venues)



### Key Layers
- **Presentation Layer**: Admin or user requests (create tournament, book matches)
- **Service Layer**: Core booking and validation logic
- **Algorithm Layer**: Tournament planning using DP
- **Data Layer**: Persistent storage for teams, schedules, venues

---

## Workflow

1. **Tournament Creation**
   - Admin defines tournament type (league / knockout)
   - Teams and constraints are registered

2. **Constraint Collection**
   - Venue availability
   - Team availability
   - Match duration
   - Tournament deadline

3. **Tournament Planning (DP-based)**
   - Optimal match scheduling
   - Conflict minimization
   - Resource utilization optimization

4. **Booking & Confirmation**
   - Matches are booked
   - Schedule is finalized
   - Conflicts are resolved automatically

5. **Execution & Updates**
   - Match status updates
   - Rescheduling if needed

---

##  Algorithmic Approach

### 🔹 Dynamic Programming for Tournament Planning

Dynamic Programming is used to:
- Optimize match schedules
- Minimize overlaps
- Ensure fair rest periods for teams

#### Example DP Use Case
- **State**: `dp[i][t]` → max matches scheduled till time `t` using first `i` teams
- **Transition**:
  - Include team `i` in a match
  - Skip team `i`
- **Goal**:
  - Maximize matches within constraints

This approach ensures:
- Efficient planning
- Scalability for large tournaments
- Predictable performance

---

##  Case Handling & Validations

The system handles multiple real-world cases:

###  Conflict Handling
- Team already scheduled at the same time
- Venue unavailable
- Exceeded daily match limits

###  Edge Cases
- Odd number of teams
- Last-minute team withdrawal
- Partial availability
- Tournament deadline constraints

###  Fail-safe Logic
- Rollback on invalid booking
- Recompute schedule using DP
- Graceful error messages

---

---

##  Testing Strategy

- Unit tests for DP logic
- Constraint validation tests
- Edge-case simulation (overlaps, failures)
- Stress testing with large tournaments

---

##  Future Enhancements

- AI-based schedule prediction
- Real-time rescheduling
- REST API integration
- Frontend dashboard
- Multi-sport support
- Cloud deployment

---

##  Tech Stack

- **Backend**: Python / Django
- **Algorithms**: Dynamic Programming,trees,subarrays
- **Database**: Postgresql 
- **Version Control**: Git & GitHub

---

##  How to Run

```bash
git clone https://github.com/poorna-9/cricstore-bookingagent-2-.git
cd cricstore-bookingagent
pip install -r requirements.txt
python manage.py runserver






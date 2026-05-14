document.addEventListener('DOMContentLoaded', function () {

    const container = document.getElementById("slots-section");
    const sessionIdInput = document.getElementById('sessionIdInput');
    const dateInput = document.getElementById('slot-date');
    const checkoutForm = document.getElementById("checkoutForm");

    if (!container || !dateInput) {
        console.error("Missing slots container or date input");
        return;
    }

    const groundIdFromContainer = container.dataset.groundid;

    let selectedSlots = new Set();   
    let sessionId = null;

    function setSlotClass(slot, cls) {
        slot.classList.remove("available", "reserved", "my-reserved", "booked");
        slot.classList.add(cls);
    }
    container.addEventListener("click", function (e) {
        const slot = e.target.closest(".slot");
        if (!slot) return;

        const slotId = slot.dataset.slotid;
        const date = dateInput.value;

        if (!date) {
            alert("Please select a date first.");
            return;
        }

        if (
            slot.classList.contains("booked") ||
            (slot.classList.contains("reserved") && !slot.classList.contains("my-reserved"))
        ) {
            return;
        }

        const body = new URLSearchParams();
        body.append("ground_id", groundIdFromContainer);
        body.append("slot_id", slotId);
        body.append("date", date);

        fetch("/bookings/reserveslot/", {
            method: "POST",
            headers: {
                "X-CSRFToken": document.querySelector('[name=csrfmiddlewaretoken]').value,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body: body.toString()
        })
            .then(res => res.json())
            .then(data => {

                // --- Set session id ---
                if (data.session_id) {
                    sessionId = data.session_id;
                    sessionIdInput.value = sessionId;
                }

                if (data.success) {
                    if (data.action === "selected") {
                        setSlotClass(slot, "my-reserved");
                        selectedSlots.add(slotId);
                    } else {
                        setSlotClass(slot, "available");
                        selectedSlots.delete(slotId);
                    }
                } else {
                    alert(data.message || "Action failed");
                }

            })
            .catch(err => console.error("Fetch error:", err));
    });
    dateInput.addEventListener("change", function () {
        const selectedDate = this.value;
        if (selectedDate) {
            window.location.href = `/bookings/grounddetail/${groundIdFromContainer}/?date=${selectedDate}`;
        }
    });

    checkoutForm.addEventListener("submit", function (e) {
        if (!sessionId) {
            e.preventDefault();
            alert("You must select at least one slot!");
            return;
        }
        this.action = `/bookings/checkout/${sessionId}/`;
    });
    function refreshReservedSlots() {
        const date = dateInput.value;
        const groundId = groundIdFromContainer;

        if (!date) return;

        fetch(`/bookings/get_reserved_slots/?ground_id=${groundId}&date=${date}`)
            .then(res => res.json())
            .then(data => {
                const userReserved = new Set((data.user_reserved || []).map(String));
                const othersReserved = new Set((data.others_reserved || []).map(String));
                const bookedSet = new Set((data.booked || []).map(String));

                selectedSlots = userReserved;

                container.querySelectorAll(".slot").forEach(slot => {
                    const id = slot.dataset.slotid;

                    if (bookedSet.has(id)) {
                        setSlotClass(slot, "booked");
                    }
                    else if (userReserved.has(id)) {
                        setSlotClass(slot, "my-reserved");
                    }
                    else if (othersReserved.has(id)) {
                        setSlotClass(slot, "reserved");
                    }
                    else {
                        setSlotClass(slot, "available");
                    }
                });
            })
            .catch(err => console.error(err));
    }

    refreshReservedSlots();
    setInterval(refreshReservedSlots, 5000); 
});

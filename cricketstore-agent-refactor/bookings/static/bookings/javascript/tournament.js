document.addEventListener("DOMContentLoaded", function () {
    const table = document.getElementById("shift-table");
    const sessionIdInput = document.getElementById("sessionIdInput");
    const checkoutForm = document.getElementById("tournamentCheckoutForm");

    if (!table) return;

    const groundId = table.dataset.groundid;
    let sessionId = null;

    function setShiftClass(cell, cls) {
        cell.classList.remove("available", "my-reserved", "others-reserved", "booked");
        cell.classList.add(cls);
    }

    // Click handler
    table.addEventListener("click", function (e) {
        const cell = e.target.closest(".shift-cell");
        if (!cell) return;

        if (cell.classList.contains("others-reserved") ||
            cell.classList.contains("booked")) return;

        const dateValue = cell.dataset.date;
        const shiftValue = cell.dataset.shift;

        const body = new URLSearchParams();
        body.append("ground_id", groundId);
        body.append("date", dateValue);
        body.append("session_type", shiftValue);

        fetch("/bookings/reservetournamentday/", {
            method: "POST",
            headers: {
                "X-CSRFToken": document.querySelector('[name=csrfmiddlewaretoken]').value,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body: body.toString()
        })
        .then(res => res.json())
        .then(data => {
            if (!data.success) {
                alert(data.message || "Something went wrong");
                return;
            }
            if (data.session_id) {
                sessionId = data.session_id;
                sessionIdInput.value = sessionId;
            }
            if (data.action === "selected") {
                setShiftClass(cell, "my-reserved");
            } else {
                setShiftClass(cell, "available");
            }
        })
        .catch(err => console.error("Fetch error:", err));
    });

    // Checkout
    checkoutForm.addEventListener("submit", function (e) {
    e.preventDefault();

    if (!sessionId) {
        alert("Please select at least one shift to proceed.");
        return;
    }

    window.location.href =
        `/bookings/tournamentcheckout/${sessionId}/`;
    });

    // Refresh every 5 seconds
    function refreshReservedShifts() {
        fetch(`/bookings/gettournamentreserveddays/?ground_id=${groundId}`)
        .then(res => res.json())
        .then(data => {
            const userReserved = data.user_reserved || {};
            const othersReserved = data.others_reserved || {};
            const bookedData = data.booked || {};

            table.querySelectorAll("tr[data-date]").forEach(row => {
                const dateStr = row.dataset.date;

                row.querySelectorAll(".shift-cell").forEach(cell => {
                    const shift = cell.dataset.shift;

                    if (bookedData[dateStr]?.includes(shift)) {
                        setShiftClass(cell, "booked");
                    } else if (userReserved[dateStr]?.includes(shift)) {
                        setShiftClass(cell, "my-reserved");
                    } else if (othersReserved[dateStr]?.includes(shift)) {
                        setShiftClass(cell, "others-reserved");
                    } else {
                        setShiftClass(cell, "available");
                    }
                });
            });
        })
        .catch(err => console.error(err));
    }

    refreshReservedShifts();
    setInterval(refreshReservedShifts, 5000);
});
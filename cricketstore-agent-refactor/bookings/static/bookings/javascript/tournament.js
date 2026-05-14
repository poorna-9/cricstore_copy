document.addEventListener("DOMContentLoaded", function () {
    const container = document.getElementById("date-grid");
    const sessionIdInput = document.getElementById("sessionIdInput");
    const checkoutForm = document.getElementById("tournamentCheckoutForm"); 
    const slottype=document.getElementById("slot-type-box")

    if (!container) {
        console.error("Missing slots container or date input");
        return;
    }

    const groundId = container.dataset.groundid;
    console.log("Ground ID:", groundId);
    let sessionId = null;

    function getSelectedSlotType() {
        const el=document.querySelector('input[name="slot_type"]:checked');
        if (!el){
            alert("Please select slot type");
            throw new Error("Slot type not selected");
        }
        return el.value
    }
    function setDateClass(el, cls) {
        el.classList.remove("available", "reserved", "my-reserved", "booked");
        el.classList.add(cls);
    }

    container.addEventListener("click", function (e) {
        const dateBox = e.target.closest(".date-card"); 
        if (!dateBox) return;

        if (dateBox.classList.contains("booked") ||
            (dateBox.classList.contains("reserved") && !dateBox.classList.contains("my-reserved"))) {
            return;
        }

        const dateValue = dateBox.dataset.date;
        const slotType = getSelectedSlotType();
        const body = new URLSearchParams();
        body.append("ground_id", groundId);
        body.append("date", dateValue);
        body.append("session_type", slotType);
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
                setDateClass(dateBox, "my-reserved");
            } else {
                setDateClass(dateBox, "available");
            }
        })
        .catch(err => console.error("Fetch error:", err));
    });

    checkoutForm.addEventListener("submit", function (e) {
        if (!sessionId) {
            e.preventDefault();
            alert("Please select at least one date to proceed to checkout.");
        }
        this.action=`/bookings/tournamentcheckout/${sessionId}/`;
    });

    function refreshreserveddays(){
        fetch(`/bookings/gettournamentreserveddays/?ground_id=${groundId}`)
        .then(res => res.json())
        .then(data => {
            const userReserved = new Set((data.user_reserved || []).map(String));
            const othersReserved = new Set((data.others_reserved || []).map(String));
            const bookedSet = new Set((data.booked || []).map(String));
            console.log({
                  booked: bookedSet,
                  userReserved: userReserved,
                  othersReserved: othersReserved
                });
            container.querySelectorAll(".date-card").forEach(datebox => { 
                const id = datebox.dataset.date;
                if (bookedSet.has(id)){
                    setDateClass(datebox,"booked");
                }
                else if(userReserved.has(id)){
                    setDateClass(datebox,"my-reserved");
                }
                else if(othersReserved.has(id)){
                    setDateClass(datebox,"reserved");
                }
                else if (
                   !datebox.classList.contains("reserved") &&
                   !datebox.classList.contains("my-reserved") &&
                   !datebox.classList.contains("booked")
                ) {
                  setDateClass(datebox, "available");
                }
            });
        })
        .catch(err => console.error(err));
    }

    refreshreserveddays();
    setInterval(refreshreserveddays, 5000);
});

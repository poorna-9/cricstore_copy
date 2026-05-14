// Make functions globally accessible
window.detectLocation = function () {
  const status = document.getElementById("locationStatus");

  if (!navigator.geolocation) {
    status.innerText = "Geolocation not supported by your browser.";
    return;
  }

  status.innerText = "Detecting location...";

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const lat = pos.coords.latitude;
      const lon = pos.coords.longitude;

      const formData = new FormData();
      formData.append("lat", lat);
      formData.append("lon", lon);

      fetch("/bookings/get_user_location/", {
        method: "POST",
        headers: {
          "X-CSRFToken": getCSRFToken()
        },
        body: formData
      })
        .then(res => res.json())
        .then(data => {
          if (data.success) {
            status.innerText = "Location detected successfully.";
            document.getElementById("locationPopup").remove();

            // Re-run the last chatbot query
            if (window.resendLastQuery) {
              resendLastQuery();
            }
          } else {
            status.innerText = data.message || "Location detection failed.";
          }
        })
        .catch(() => {
          status.innerText = "Server error while saving location.";
        });
    },
    () => {
      status.innerText = "Permission denied. Please allow location access.";
    },
    {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 0
    }
  );
};

// Optional manual submit (fallback)
window.submitLocation = function () {
  const addr = document.getElementById("user_address").value.trim();
  if (!addr) {
    alert("Please enter a location.");
    return;
  }

  const formData = new FormData();
  formData.append("user_address", addr);

  fetch("/get_user_location/", {
    method: "POST",
    headers: {
      "X-CSRFToken": getCSRFToken()
    },
    body: formData
  })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        document.getElementById("locationPopup").remove();
        if (window.resendLastQuery) resendLastQuery();
      } else {
        alert(data.message);
      }
    });
};

// CSRF helper
function getCSRFToken() {
  return document.cookie
    .split("; ")
    .find(row => row.startsWith("csrftoken="))
    ?.split("=")[1];
}

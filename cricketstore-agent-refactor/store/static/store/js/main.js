const input = document.getElementById("search-input");
const suggestionBox = document.getElementById("suggestions");

input.addEventListener("input", () => {
    const query = input.value;
    if (query.length < 2) {
        suggestionBox.innerHTML = "";
        return;
    }
    fetch(`/search_suggestions/?q=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(data => {
            suggestionBox.innerHTML = "";
            for (let i = 0; i < data.suggestions.length; i++) {
                const suggestion = data.suggestions[i];
                const div = document.createElement("div");
                div.textContent = suggestion;
                div.classList.add("suggestion-item");
                div.addEventListener("click", () => {
                    input.value = suggestion;
                    suggestionBox.innerHTML = "";
                    input.form.submit();
                });
                suggestionBox.appendChild(div);
            }
        });
});

document.addEventListener("click", (e) => {
    if (!suggestionBox.contains(e.target) && e.target !== input) {
        suggestionBox.innerHTML = "";
    }
});

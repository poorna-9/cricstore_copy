document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('navbar-search-form');
    const input = document.getElementById('ground_search_input');
    const cityFilter = document.getElementById('city-filter');
    const resultsContainer = document.getElementById('grounds-results');

    function fetchGrounds(query = '', city = '') {
        fetch(`/grounds/?q=${encodeURIComponent(query)}&city=${encodeURIComponent(city)}&ajax=1`)
            .then(res => res.json())
            .then(data => {
                resultsContainer.innerHTML = '';
                if (data.grounds.length === 0) {
                    resultsContainer.innerHTML = '<p>No grounds found.</p>';
                    return;
                }
                data.grounds.forEach(ground => {
                    const div = document.createElement('div');
                    div.classList.add('ground-item', 'mb-3', 'shadow-sm', 'p-3', 'bg-light', 'rounded');
                    div.innerHTML = `
                        <a href="/ground/${ground.id}/">
                            <img src="${ground.imageURL}" class="img-fluid rounded" alt="${ground.name}">
                            <h3>${ground.name}</h3>
                            <span>₹${ground.price}</span>
                        </a>
                    `;
                    resultsContainer.appendChild(div);
                });
            })
            .catch(err => console.error(err));
    }

    if (form && input && resultsContainer) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            const query = input.value.trim();
            const city = cityFilter ? cityFilter.value : '';
            fetchGrounds(query, city);
        });
    }

    if (cityFilter && resultsContainer) {
        cityFilter.addEventListener('change', function() {
            const city = cityFilter.value;
            const query = input ? input.value.trim() : '';
            fetchGrounds(query, city);
        });
    }
});


document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('scrape-form');
    const loading = document.getElementById('loading');
    const resultsContainer = document.getElementById('results-container');
    const dashboard = document.getElementById('dashboard');
    const resultsBody = document.getElementById('results-body');
    const downloadBtn = document.getElementById('download-btn');
    const saveSheetsBtn = document.getElementById('save-sheets-btn');
    const searchInput = document.getElementById('search-input');
    const statTotal = document.getElementById('stat-total');
    const ctxCategory = document.getElementById('categoryChart').getContext('2d');
    const darkModeToggle = document.getElementById('dark-mode-toggle');
    const toggleLabel = document.querySelector('.toggle-label');

    // Dark mode initialization
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
        document.documentElement.classList.add('dark');
        darkModeToggle.checked = true;
        toggleLabel.textContent = 'OFF';
    }

    darkModeToggle.addEventListener('change', () => {
        if (darkModeToggle.checked) {
            document.documentElement.classList.add('dark');
            localStorage.setItem('theme', 'dark');
            toggleLabel.textContent = 'OFF';
        } else {
            document.documentElement.classList.remove('dark');
            localStorage.setItem('theme', 'light');
            toggleLabel.textContent = 'ON';
        }
    });

    let currentResults = [];
    let categoryChart = null;
    let controller = null;

    const cancelBtn = document.getElementById('cancel-btn');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', async () => {
            if (controller) {
                controller.abort();
            }
            try {
                await fetch('/api/cancel', { method: 'POST' });
            } catch (e) {
                console.log('Cancel request sent');
            }
            loading.classList.add('hidden');
            alert('Scraping detenido');
        });
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const keyword = document.getElementById('keyword').value;
        const city = document.getElementById('city').value;
        const limit = document.getElementById('limit').value;
        const mode = document.getElementById('mode').value;

        if (loading) loading.classList.remove('hidden');
        if (resultsContainer) resultsContainer.classList.add('hidden');
        if (dashboard) dashboard.classList.add('hidden');
        if (searchInput) searchInput.value = '';

        controller = new AbortController();

        try {
            const response = await fetch('/api/scrape', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ keyword, city, limit, mode }),
                signal: controller.signal
            });

            const data = await response.json();

            if (data.success) {
                currentResults = data.data;
                displayResults(data.data);
                updateDashboard(data.data);
                if (data.cancelled) {
                    alert('Scraping fue cancelado. Se muestran resultados parciales: ' + data.data.length);
                }
            } else {
                alert('Error: ' + data.error);
            }
        } catch (error) {
            if (error.name !== 'AbortError') {
                alert('Error en la conexión: ' + error.message);
            }
        } finally {
            if (loading) loading.classList.add('hidden');
            controller = null;
        }
    });

    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const searchTerm = e.target.value.toLowerCase();
            const rows = resultsBody.querySelectorAll('tr');
            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(searchTerm) ? '' : 'none';
            });
        });
    }

    if (downloadBtn) {
        downloadBtn.addEventListener('click', async () => {
            if (currentResults.length === 0) return;
            const originalText = downloadBtn.textContent;
            downloadBtn.disabled = true;
            downloadBtn.textContent = 'Generando archivo...';
            try {
                const response = await fetch('/api/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ results: currentResults })
                });
                if (response.ok) {
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `leads_${currentResults[0].nombre.replace(/\s+/g, '_')}.xlsx`;
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                } else {
                    const errorData = await response.json();
                    alert('Error al descargar: ' + errorData.error);
                }
            } catch (error) {
                alert('Error al descargar: ' + error.message);
            } finally {
                downloadBtn.disabled = false;
                downloadBtn.textContent = originalText;
            }
        });
    }

    if (saveSheetsBtn) {
        saveSheetsBtn.addEventListener('click', async () => {
            if (currentResults.length === 0) return;
            const original = saveSheetsBtn.textContent;
            saveSheetsBtn.disabled = true;
            saveSheetsBtn.textContent = 'Guardando...';
            try {
                const response = await fetch('/api/save-to-sheets', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ results: currentResults })
                });
                const res = await response.json();
                if (response.ok) {
                    alert(res.message);
                } else {
                    alert('Error: ' + res.error);
                }
            } catch (e) {
                alert('Fallo de conexión: ' + e.message);
            } finally {
                saveSheetsBtn.disabled = false;
                saveSheetsBtn.textContent = original;
            }
        });
    }

    function updateDashboard(data) {
        if (statTotal) statTotal.textContent = data.length;
        const categoryCounts = {};
        data.forEach(item => {
            const cat = item.categoria || 'Otros';
            categoryCounts[cat] = (categoryCounts[cat] || 0) + 1;
        });
        const labels = Object.keys(categoryCounts);
        const counts = Object.values(categoryCounts);
        if (categoryChart) categoryChart.destroy();
        categoryChart = new Chart(ctxCategory, {
            type: 'pie',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Negocios por Categoría',
                    data: counts,
                    backgroundColor: ['#4f46e5', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'],
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { position: 'bottom' },
                    title: { display: true, text: 'Distribución de Categorías' }
                }
            }
        });
        if (dashboard) dashboard.classList.remove('hidden');
    }

    function displayResults(data) {
        if (!resultsBody) return;
        resultsBody.innerHTML = '';
        data.forEach(item => {
            const row = document.createElement('tr');
            const mapsUrl = item.maps_url || '';
            const phoneDisplay = item.telefono || 'sin numero';
            const linkHtml = mapsUrl ? `<a href="${mapsUrl}" target="_blank" rel="noopener">Abrir en Maps</a>` : '-';
            row.innerHTML = `<td>${item.nombre}</td><td>${item.direccion}</td><td>${phoneDisplay}</td><td>${item.ciudad}</td><td>${item.categoria}</td><td>${linkHtml}</td>`;
            resultsBody.appendChild(row);
        });
        if (resultsContainer) resultsContainer.classList.remove('hidden');
    }
});
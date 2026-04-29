const API_URL = ""; 

const getAuthHeader = () => {
    const token = localStorage.getItem('api_flow_token');
    if (!token) {
        window.location.href = 'login.html';
    }
    return { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };
};

async function fetchStats() {
    try {
        const response = await fetch(`${API_URL}/admin/stats`, { headers: getAuthHeader() });
        if (response.ok) {
            const stats = await response.json();
            document.getElementById('stat-total').innerText = stats.total_professionals;
            document.getElementById('stat-active').innerText = stats.active_professionals;
            document.getElementById('stat-mrr').innerText = `$ ${stats.estimated_mrr.toLocaleString()}`;
        }
    } catch (error) {
        console.error("Error cargando estadísticas:", error);
    }
}

async function fetchProfessionals() {
    const listElement = document.getElementById('professional-list');
    listElement.innerHTML = '<tr><td colspan="5" class="text-center py-10 text-gray-400">Cargando...</td></tr>';

    try {
        const response = await fetch(`${API_URL}/admin/professionals`, { headers: getAuthHeader() });
        const professionals = await response.json();

        listElement.innerHTML = '';
        professionals.forEach(prof => {
            const row = document.createElement('tr');
            row.className = "hover:bg-gray-50 transition";
            row.innerHTML = `
                <td class="px-8 py-4 font-medium">${prof.title} ${prof.name}</td>
                <td class="px-8 py-4 text-gray-500 font-light">${prof.niche}</td>
                <td class="px-8 py-4 font-light">$ ${prof.session_price.toLocaleString()}</td>
                <td class="px-8 py-4">
                    <span class="px-2 py-1 rounded-full text-xs ${prof.active ? 'bg-green-100 text-green-600' : 'bg-red-100 text-red-600'}">
                        ${prof.active ? 'Activo' : 'Suspendido'}
                    </span>
                </td>
                <td class="px-8 py-4">
                    <button onclick="toggleProfessional('${prof.id}')" class="text-xs font-semibold text-blue-600 hover:underline">
                        ${prof.active ? 'Suspender' : 'Activar'}
                    </button>
                </td>
            `;
            listElement.appendChild(row);
        });
    } catch (error) {
        listElement.innerHTML = '<tr><td colspan="5" class="text-center py-10 text-red-400">Error al conectar con el servidor</td></tr>';
    }
}

async function toggleProfessional(id) {
    try {
        const response = await fetch(`${API_URL}/admin/professionals/${id}/toggle`, { 
            method: 'POST', 
            headers: getAuthHeader() 
        });
        if (response.ok) {
            fetchStats();
            fetchProfessionals();
        }
    } catch (error) {
        alert("No se pudo cambiar el estado del profesional.");
    }
}

function openPasswordModal() {
    document.getElementById('passwordModal').classList.remove('hidden');
}

function closePasswordModal() {
    document.getElementById('passwordModal').classList.add('hidden');
    document.getElementById('passwordForm').reset();
    document.getElementById('pwdMsg').classList.add('hidden');
}

function logout() {
    localStorage.removeItem('api_flow_token');
    window.location.href = 'login.html';
}

// INICIALIZACIÓN GLOBAL SEGURO
document.addEventListener('DOMContentLoaded', () => {
    fetchStats();
    fetchProfessionals();

    // Ahora sí, el JS espera a que el formulario exista para asignarle la orden
    const passwordForm = document.getElementById('passwordForm');
    if (passwordForm) {
        passwordForm.onsubmit = async (e) => {
            e.preventDefault(); // Esto evita que la página se recargue
            
            const oldPassword = document.getElementById('oldPassword').value;
            const newPassword = document.getElementById('newPassword').value;
            const msgEl = document.getElementById('pwdMsg');

            msgEl.classList.remove('hidden', 'text-green-600', 'text-red-600');
            msgEl.innerText = "Actualizando...";
            msgEl.classList.add('text-gray-500');

            try {
                const response = await fetch(`${API_URL}/auth/change-password`, {
                    method: 'PUT',
                    headers: getAuthHeader(),
                    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword })
                });

                const data = await response.json();

                if (response.ok) {
                    msgEl.innerText = "¡Contraseña actualizada!";
                    msgEl.classList.replace('text-gray-500', 'text-green-600');
                    setTimeout(closePasswordModal, 2000);
                } else {
                    msgEl.innerText = data.detail || "Error al actualizar";
                    msgEl.classList.replace('text-gray-500', 'text-red-600');
                }
            } catch (error) {
                msgEl.innerText = "Error de red";
                msgEl.classList.replace('text-gray-500', 'text-red-600');
            }
        };
    }
});
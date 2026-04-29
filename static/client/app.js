const API_URL = ""; 

const getAuthHeader = () => {
    const token = localStorage.getItem('api_flow_token');
    if (!token) {
        window.location.href = 'login.html';
        return {};
    }
    return { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };
};

// --- CARGA DE DATOS ---

async function loadDashboard() {
    try {
        const res = await fetch(`${API_URL}/client/me`, { headers: getAuthHeader() });
        if (res.ok) {
            const data = await res.json();
            document.getElementById('prof-name').innerText = data.name;
            document.getElementById('stat-week-appts').innerText = data.stats.week_count;
            document.getElementById('stat-revenue').innerText = `$ ${data.stats.estimated_revenue.toLocaleString()}`;
            document.getElementById('stat-patients').innerText = data.stats.total_patients;
            
            // Llenamos el modal con los datos actuales
            document.getElementById('edit-name').value = data.full_name || "";
            document.getElementById('edit-title').value = data.title || "";
            document.getElementById('edit-niche').value = data.niche || "";
            document.getElementById('edit-price').value = data.session_price || 0;
            document.getElementById('edit-duration').value = data.session_minutes || 50;
        }
    } catch (e) { console.error("Error al cargar perfil", e); }
}

async function loadAppointments() {
    const list = document.getElementById('appointment-list');
    list.innerHTML = '<tr><td colspan="4" class="text-center py-10 text-gray-400 italic">Cargando agenda...</td></tr>';

    try {
        const res = await fetch(`${API_URL}/client/appointments`, { headers: getAuthHeader() });
        if (res.ok) {
            const appointments = await res.json();
            list.innerHTML = '';
            if (appointments.length === 0) {
                list.innerHTML = '<tr><td colspan="4" class="text-center py-10 text-gray-400">No hay turnos registrados.</td></tr>';
                return;
            }
            appointments.forEach(apt => {
                const row = document.createElement('tr');
                row.className = "hover:bg-gray-50 transition";
                row.innerHTML = `
                    <td class="px-8 py-4">
                        <p class="font-medium">${apt.patient_name || 'Paciente Sin Nombre'}</p>
                        <p class="text-xs text-gray-400">${apt.patient_phone}</p>
                    </td>
                    <td class="px-8 py-4 text-gray-600 font-light text-xs">
                        ${new Date(apt.start_at).toLocaleString('es-AR', { dateStyle: 'medium', timeStyle: 'short' })} hs
                    </td>
                    <td class="px-8 py-4">
                        <span class="px-2 py-1 rounded-full text-[10px] font-bold uppercase ${apt.status === 'confirmed' ? 'bg-green-100 text-green-600' : 'bg-yellow-100 text-yellow-600'}">
                            ${apt.status}
                        </span>
                    </td>
                    <td class="px-8 py-4">
                        <div class="flex items-center gap-2">
                            <div class="w-2 h-2 rounded-full ${apt.is_billed ? 'bg-green-500' : 'bg-red-400'}"></div>
                            <span class="text-xs text-gray-500">${apt.is_billed ? 'Cobrado' : 'Pendiente'}</span>
                        </div>
                    </td>
                `;
                list.appendChild(row);
            });
        }
    } catch (e) { console.error("Error al cargar turnos", e); }
}

// --- GESTIÓN DE HORARIOS ---

const DAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];

async function loadWorkingHours() {
    const container = document.getElementById('working-hours-container');
    container.innerHTML = '<p class="text-center py-4 text-gray-400 text-xs">Cargando horarios...</p>';

    try {
        const res = await fetch(`${API_URL}/client/working-hours`, { headers: getAuthHeader() });
        const hours = await res.json(); // Esperamos una lista de WorkingHours

        container.innerHTML = '';
        DAYS.forEach((dayName, index) => {
            const dayData = hours.find(h => h.day_of_week === index) || { active: false, start_time: "09:00", end_time: "18:00" };
            
            const div = document.createElement('div');
            div.className = `flex items-center justify-between p-3 rounded-2xl border ${dayData.active ? 'bg-white border-gray-200' : 'bg-gray-50 border-transparent opacity-60'}`;
            div.innerHTML = `
                <div class="flex items-center gap-3">
                    <input type="checkbox" class="day-active w-4 h-4 rounded-full accent-blue-600" data-day="${index}" ${dayData.active ? 'checked' : ''}>
                    <span class="text-sm font-medium w-20">${dayName}</span>
                </div>
                <div class="flex items-center gap-2">
                    <input type="time" class="day-start text-xs bg-transparent border-none focus:ring-0" value="${dayData.start_time}" ${!dayData.active ? 'disabled' : ''}>
                    <span class="text-gray-300">→</span>
                    <input type="time" class="day-end text-xs bg-transparent border-none focus:ring-0" value="${dayData.end_time}" ${!dayData.active ? 'disabled' : ''}>
                </div>
            `;
            container.appendChild(div);
        });

        // Evento para habilitar/deshabilitar inputs de tiempo
        document.querySelectorAll('.day-active').forEach(check => {
            check.onchange = (e) => {
                const row = e.target.closest('div.flex');
                const inputs = row.nextElementSibling.querySelectorAll('input');
                inputs.forEach(i => i.disabled = !e.target.checked);
                e.target.closest('.p-3').classList.toggle('opacity-60', !e.target.checked);
                e.target.closest('.p-3').classList.toggle('bg-gray-50', !e.target.checked);
            };
        });
    } catch (e) { console.error("Error al cargar horarios", e); }
}

// --- ACCIONES ---

async function saveAllSettings() {
    const msg = document.getElementById('settingsMsg');
    msg.innerText = "Guardando...";
    msg.className = "text-xs font-medium text-gray-500 block";
    msg.classList.remove('hidden');

    try {
        // 1. Guardar Perfil
        const profData = {
            name: document.getElementById('edit-name').value,
            title: document.getElementById('edit-title').value,
            niche: document.getElementById('edit-niche').value,
            session_price: parseFloat(document.getElementById('edit-price').value),
            session_minutes: parseInt(document.getElementById('edit-duration').value)
        };

        const resProf = await fetch(`${API_URL}/client/settings`, {
            method: 'PUT',
            headers: getAuthHeader(),
            body: JSON.stringify(profData)
        });

        // 2. Guardar Horarios
        const hours = [];
        document.querySelectorAll('#working-hours-container > div').forEach(div => {
            const check = div.querySelector('.day-active');
            hours.push({
                day_of_week: parseInt(check.dataset.day),
                active: check.checked,
                start_time: div.querySelector('.day-start').value,
                end_time: div.querySelector('.day-end').value
            });
        });

        const resHours = await fetch(`${API_URL}/client/working-hours`, {
            method: 'POST',
            headers: getAuthHeader(),
            body: JSON.stringify(hours)
        });

        if (resProf.ok && resHours.ok) {
            msg.innerText = "✅ Configuración guardada con éxito.";
            msg.className = "text-xs font-medium text-green-600 block";
            setTimeout(() => {
                msg.classList.add('hidden');
                loadDashboard(); // Recargar datos en el dashboard
            }, 3000);
        }
    } catch (e) {
        msg.innerText = "❌ Error al guardar.";
        msg.className = "text-xs font-medium text-red-600 block";
    }
}

async function updatePassword() {
    const oldP = document.getElementById('oldPassword').value;
    const newP = document.getElementById('newPassword').value;
    if(!oldP || !newP) return alert("Completá ambos campos de contraseña");

    const res = await fetch(`${API_URL}/auth/change-password`, {
        method: 'PUT',
        headers: getAuthHeader(),
        body: JSON.stringify({ old_password: oldP, new_password: newP })
    });

    if (res.ok) alert("Contraseña actualizada");
    else alert("Error: contraseña actual incorrecta");
}

function openSettingsModal() {
    document.getElementById('settingsModal').classList.remove('hidden');
    loadWorkingHours();
}

function closeSettingsModal() {
    document.getElementById('settingsModal').classList.add('hidden');
}

function logout() {
    localStorage.removeItem('api_flow_token');
    window.location.href = 'login.html';
}

document.addEventListener('DOMContentLoaded', () => {
    loadDashboard();
    loadAppointments();
});
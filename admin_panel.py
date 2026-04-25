import streamlit as st
import requests
import pandas as pd

# 1. CONFIGURACIÓN DE LA PÁGINA
st.set_page_config(page_title="Api-flow Admin", page_icon="⚙️", layout="wide")

st.title("🎛️ Panel de Control - Api-flow")
st.markdown("Gestión centralizada de clientes, métricas y suscripciones.")

# 2. BARRA LATERAL (Conexión de Seguridad)
st.sidebar.header("Conexión al Servidor")
API_URL = st.sidebar.text_input("URL del Backend", value="http://127.0.0.1:8000")
API_KEY = st.sidebar.text_input("Admin API Key", type="password", help="La clave secreta configurada en tu main.py")

if not API_KEY:
    st.warning("👈 Por favor, ingresá tu Admin API Key en la barra lateral para conectar con la base de datos.")
    st.stop()

headers = {"x-admin-key": API_KEY}

# --- NUEVA ESTRUCTURA CON PESTAÑAS ---
tab_dash, tab_reg = st.tabs(["📊 Dashboard y Clientes", "👤 Registrar Nuevo Profesional"])

with tab_dash:
    # 3. DASHBOARD DE MÉTRICAS
    st.subheader("📊 Métricas Globales")
    try:
        res_stats = requests.get(f"{API_URL}/admin/stats", headers=headers)
        if res_stats.status_code == 200:
            stats = res_stats.json()
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Clientes Registrados", stats["total_professionals"])
            col2.metric("Clientes Activos", stats["active_professionals"])
            col3.metric("MRR Estimado", f"${stats['estimated_mrr']} USD")
            col4.metric("Turnos Confirmados (Total)", stats["total_appointments_confirmed"])
        elif res_stats.status_code == 403:
            st.error("Acceso Denegado: La Admin API Key es incorrecta.")
            st.stop()
        else:
            st.error(f"Error del servidor: {res_stats.status_code}")
    except requests.exceptions.ConnectionError:
        st.error("🚨 No se pudo conectar al servidor. Asegurate de que FastAPI esté corriendo.")
        st.stop()

    st.divider()

    # 4. GESTIÓN DE CLIENTES (EXISTENTE)
    st.subheader("👥 Mis Clientes (Profesionales)")
    res_profs = requests.get(f"{API_URL}/admin/professionals", headers=headers)
    if res_profs.status_code == 200:
        profs = res_profs.json()
        if profs:
            df = pd.DataFrame(profs)
            df_view = df[["id", "name", "title", "niche", "session_price", "active", "created_at"]]
            st.dataframe(df_view, use_container_width=True)

            st.markdown("### 🛑 Control de Servicio (Botón de Pánico)")
            col_sel, col_btn = st.columns([3, 1])
            prof_options = {p["id"]: f"{p['title']} {p['name']} - {'🟢 ACTIVO' if p['active'] else '🔴 SUSPENDIDO'}" for p in profs}
            selected_id = col_sel.selectbox("Seleccionar Profesional a modificar:", options=list(prof_options.keys()), format_func=lambda x: prof_options[x])
            
            if col_btn.button("Cambiar Estado"):
                res_toggle = requests.post(f"{API_URL}/admin/professionals/{selected_id}/toggle", headers=headers)
                if res_toggle.status_code == 200:
                    st.success("¡Estado actualizado!")
                    st.rerun()
        else:
            st.info("No hay profesionales. Usá la pestaña de registro para agregar el primero.")

with tab_reg:
    # 5. FORMULARIO DE ALTA (LO NUEVO)
    st.subheader("👤 Alta de Nuevo Profesional")
    st.info("Completá estos datos para conectar un nuevo número de WhatsApp y Google Calendar al sistema.")
    
    with st.form("form_registro"):
        c1, c2 = st.columns(2)
        with c1:
            new_name = st.text_input("Nombre Completo", placeholder="Ej: Dr. Ignacio Ortigoza")
            new_title = st.text_input("Título", placeholder="Ej: Nutricionista")
            new_niche = st.text_input("Nicho/Especialidad", placeholder="Ej: Nutrición Deportiva")
            new_price = st.number_input("Precio por Sesión (ARS/USD)", min_value=0, value=5000)
            new_address = st.text_input("Dirección Física (Opcional)")

        with c2:
            new_phone_id = st.text_input("WhatsApp Phone ID", help="El ID numérico que te da Meta para ese número.")
            new_calendar = st.text_input("Google Calendar ID", help="Ej: usuario@gmail.com o el ID del calendario secundario.")
            new_tz = st.text_input("Zona Horaria", value="America/Argentina/Buenos_Aires")
            new_credentials = st.text_area("Credenciales JSON (Opcional)", help="Si el cliente usa su propio Google Cloud.")

        btn_save = st.form_submit_button("🚀 Registrar y Activar Cliente")

        if btn_save:
            payload = {
                "name": new_name,
                "title": new_title,
                "niche": new_niche,
                "session_price": new_price,
                "phone_number_id": new_phone_id,
                "calendar_id": new_calendar,
                "timezone": new_tz,
                "address": new_address,
                "active": True
            }
            
            res_add = requests.post(f"{API_URL}/admin/professionals", json=payload, headers=headers)
            
            if res_add.status_code == 200:
                st.success(f"✅ ¡{new_name} registrado correctamente! Ya podés verlo en el Dashboard.")
                # No hacemos st.rerun() acá para que el usuario vea el mensaje de éxito
            else:
                st.error(f"❌ Error al registrar: {res_add.text}")
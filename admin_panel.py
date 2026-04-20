import streamlit as st
import requests
import pandas as pd

# 1. CONFIGURACIÓN DE LA PÁGINA
st.set_page_config(page_title="Api-flow Admin", page_icon="⚙️", layout="wide")

st.title("🎛️ Panel de Control - Api-flow")
st.markdown("Gestión centralizada de clientes, métricas y suscripciones.")

# 2. BARRA LATERAL (Conexión de Seguridad)
st.sidebar.header("Conexión al Servidor")
# Si estás probando en tu PC será localhost. Si está en Render, ponés la URL de Render.
API_URL = st.sidebar.text_input("URL del Backend", value="http://127.0.0.1:8000")
API_KEY = st.sidebar.text_input("Admin API Key", type="password", help="La clave secreta configurada en tu main.py")

if not API_KEY:
    st.warning("👈 Por favor, ingresá tu Admin API Key en la barra lateral para conectar con la base de datos.")
    st.stop()

headers = {"x-admin-key": API_KEY}

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
    st.error("🚨 No se pudo conectar al servidor. Asegurate de que FastAPI esté corriendo (uvicorn app.main:app --reload).")
    st.stop()

st.divider()

# 4. GESTIÓN DE CLIENTES
st.subheader("👥 Mis Clientes (Profesionales)")

res_profs = requests.get(f"{API_URL}/admin/professionals", headers=headers)
if res_profs.status_code == 200:
    profs = res_profs.json()
    
    if profs:
        # Convertimos los datos a un DataFrame de Pandas para una tabla interactiva
        df = pd.DataFrame(profs)
        # Seleccionamos solo las columnas relevantes para la vista
        df_view = df[["id", "name", "title", "niche", "session_price", "active", "created_at"]]
        
        # Mostramos la tabla
        st.dataframe(df_view, use_container_width=True)

        # 5. ZONA DE ACCIÓN: SUSPENDER / ACTIVAR
        st.markdown("### 🛑 Control de Servicio (Botón de Pánico)")
        st.info("Si suspendés a un profesional, el bot dejará de responder automáticamente a sus pacientes.")
        
        col_sel, col_btn = st.columns([3, 1])
        
        # Creamos un diccionario visual para el selector desplegable
        prof_options = {
            p["id"]: f"{p['title']} {p['name']} - {'🟢 ACTIVO' if p['active'] else '🔴 SUSPENDIDO'}" 
            for p in profs
        }
        
        selected_id = col_sel.selectbox(
            "Seleccionar Profesional a modificar:", 
            options=list(prof_options.keys()), 
            format_func=lambda x: prof_options[x]
        )
        
        if col_btn.button("Cambiar Estado"):
            res_toggle = requests.post(f"{API_URL}/admin/professionals/{selected_id}/toggle", headers=headers)
            if res_toggle.status_code == 200:
                st.success("¡Estado actualizado exitosamente en la base de datos!")
                st.rerun() # Recarga la app para mostrar los datos actualizados
            else:
                st.error("Hubo un problema al intentar cambiar el estado.")
    else:
        st.info("Todavía no tenés profesionales en la base de datos. Ejecutá tu script seed.py para agregar el primero.")
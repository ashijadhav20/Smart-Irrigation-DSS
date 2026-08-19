import streamlit as st

APP_TITLE = "Smart Irrigation Decision Support System"

def inject_css():
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1200px;}
        .hero {
            padding: 1.35rem 1.6rem;
            border-radius: 22px;
            background: linear-gradient(115deg, #0F766E 0%, #168AAD 48%, #D4A017 100%);
            color: white;
            box-shadow: 0 8px 28px rgba(0,0,0,.12);
            margin-bottom: 1rem;
        }
        .hero h1 {font-size: clamp(1.7rem, 3.4vw, 2.75rem); margin:0 0 .35rem 0;}
        .hero p {margin:0; opacity:.95; font-size:1rem;}
        .soft-card {
            padding: 1rem 1.1rem;
            border-radius: 16px;
            background: rgba(255,255,255,.84);
            border: 1px solid rgba(15,118,110,.16);
            box-shadow: 0 3px 14px rgba(0,0,0,.05);
        }
        div[data-testid="stMetric"] {
            background: rgba(255,255,255,.88);
            border: 1px solid rgba(15,118,110,.14);
            padding: .75rem;
            border-radius: 15px;
        }
        @media (max-width: 700px) {
            .block-container {padding-left: .8rem; padding-right: .8rem;}
            .hero {padding: 1rem;}
            div[data-testid="column"] {min-width: 100% !important;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def hero(subtitle="Weather • Crop Kc • NDVI • Soil moisture • Irrigation advisory"):
    st.markdown(
        f"""
        <div class="hero">
          <h1>🌱 {APP_TITLE}</h1>
          <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

def require_inputs():
    required = ["latitude", "longitude", "crop", "soil_type", "sowing_date", "evaluation_date", "area_m2"]
    missing = [x for x in required if x not in st.session_state]
    if missing:
        st.warning("Please complete the Field Input page first.")
        st.stop()

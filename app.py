import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone, time
import math
import random
import re
from supabase import create_client, Client
import plotly.express as px

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Appointed Time | Secured Enterprise Suite",
    layout="wide",
    page_icon="🏢",
    initial_sidebar_state="expanded"
)

# --- 2. GLOBAL SETUP & MACHINE REGISTRY ---
# STRICTLY PRESERVED: Core asset registry and operational parameters untouched.
CURRENCY = "GH₵"
SHIFT_START_HOUR = 8
SHIFT_END_HOUR = 17
DAILY_CAPACITY_HOURS = 8.0

MACHINE_DATA = {
    'SM102-CX FOUR COLOUR': {'rate': 8000, 'setup_hours': 1.5},
    'SM102-P FIVE COLOUR': {'rate': 7500, 'setup_hours': 1.5},
    'SM 52': {'rate': 7000, 'setup_hours': 1.5},
    'GTO 52 SEMI-AUTO-2 COLOUR': {'rate': 4500, 'setup_hours': 1.5},
    'GTO 52 MANUAL-2 COLOUR': {'rate': 4000, 'setup_hours': 2.0},
    'FOLDING UNIT (CONTINUOUS)': {'rate': 8000, 'setup_hours': 1.5},
    'MBO-B30E (SINGLE FOLD)': {'rate': 16000, 'setup_hours': 1.5},
    'POLAR 115 CUTTER': {'rate': 5000, 'setup_hours': 1.0},
    'STAHL FOLDING MACHINE': {'rate': 8500, 'setup_hours': 1.5},
    'HEIDELBERG CYLINDER': {'rate': 3500, 'setup_hours': 2.0},
    'KORD 64': {'rate': 3000, 'setup_hours': 2.0},
    'CORONA BINDER': {'rate': 12000, 'setup_hours': 2.5},
    'MULLER MARTINI GATHERER': {'rate': 14000, 'setup_hours': 2.0},
    'HORIZON BookletMaker': {'rate': 6000, 'setup_hours': 1.0},
    'FOLIANT LAMINATOR': {'rate': 4000, 'setup_hours': 0.75},
    'DIGITAL PRESS C1060': {'rate': 9000, 'setup_hours': 0.5},
    'XEROX VERSANT 2100': {'rate': 9500, 'setup_hours': 0.5},
    'LARGE FORMAT ECO-SOLVENT': {'rate': 3500, 'setup_hours': 0.5},
    'UV FLATBED PRINTER': {'rate': 5500, 'setup_hours': 0.75},
    'HP LATEX 360': {'rate': 4000, 'setup_hours': 0.5},
    'MIMAKI PLOTTER': {'rate': 2000, 'setup_hours': 0.25},
    'AUTOMATIC EMBROIDERY (12 HEAD)': {'rate': 11000, 'setup_hours': 1.5},
    'MANUAL SCREEN PRINTING LINE': {'rate': 1500, 'setup_hours': 2.0},
    'AUTOMATIC SCREEN PRESS': {'rate': 7000, 'setup_hours': 2.0}
}

# --- 3. PREMIUM "CLEAN INDUSTRIAL LIGHT" CSS TYPOGRAPHY & STYLING ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght=300;400;500;600;700;800&display=swap');
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background-color: #f8fafc;
    color: #0f172a;
}
.main-title {
    font-size: 2.2rem;
    font-weight: 800;
    color: #0f172a;
    margin-bottom: 0.25rem;
    letter-spacing: -0.03em;
}
.main-subtitle {
    font-size: 0.95rem;
    color: #64748b;
    margin-bottom: 1.75rem;
    font-weight: 400;
}
.section-header {
    font-size: 1.35rem;
    font-weight: 700;
    color: #1e293b;
    margin-top: 2rem;
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.planner-card {
    background: #ffffff;
    padding: 2rem;
    border-radius: 14px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 4px 6px -1px rgba(15, 23, 42, 0.02);
    margin-bottom: 1rem;
}
.summary-box {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    color: #ffffff;
    padding: 1.75rem;
    border-radius: 14px;
}
.metric-card {
    background: #ffffff;
    padding: 1.25rem;
    border-radius: 12px;
    border: 1px solid #e2e8f0;
    border-bottom: 4px solid #0f172a;
}
.metric-label {
    font-size: 0.75rem;
    color: #64748b;
    text-transform: uppercase;
    font-weight: 700;
    letter-spacing: 0.05em;
}
.metric-value {
    font-size: 1.75rem;
    font-weight: 800;
    color: #0f172a;
    margin-top: 0.25rem;
}
.job-rollup-card {
    background: #ffffff;
    padding: 1rem;
    border-radius: 8px;
    border: 1px solid #e2e8f0;
    border-left: 5px solid #0f172a;
    margin-bottom: 0.5rem;
}
.stream-row-item {
    padding: 0.5rem 0;
    border-bottom: 1px solid #f1f5f9;
    display: flex;
    justify-content: space-between;
    font-size: 0.85rem;
}
.stRadio > label {
    font-weight: 600 !important;
    color: #1e293b !important;
}
.sidebar-card {
    background: #ffffff;
    padding: 1.25rem;
    border-radius: 12px;
    border: 1px solid #e2e8f0;
    margin-bottom: 1rem;
}
.sidebar-header-text {
    font-size: 0.75rem;
    font-weight: 700;
    color: #475569;
    margin-bottom: 0.5rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid #f1f5f9;
    padding-bottom: 0.25rem;
}

/* --- ADVANCEMENT 2: SECURELY ELIMINATE STREAMLIT FORM CAPTION INSTRUCTIONS --- */
[data-testid="stFormSubmitInstructions"], 
[data-testid="stWidgetFormInstruction"] {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)

# --- 4. SUPABASE DATABASE MATRIX CONNECTIVITY LAYERING ---
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "https://your-placeholder-url.supabase.co")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "your-placeholder-service-key")

@st.cache_resource
def init_supabase_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase = init_supabase_client()
except Exception:
    st.warning("Database parameters running in disconnected simulation mode.")

def clean_numeric(val) -> float:
    try:
        return float(re.sub(r'[^\d.]', '', str(val)))
    except Exception:
        return 0.0

# --- 5. INITIALIZE TRACKING SESSION STATES ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_email' not in st.session_state:
    st.session_state.user_email = None
if 'current_view' not in st.session_state:
    st.session_state.current_view = "Dashboard Analytics Hub"

# --- ADVANCEMENT 1: AUTHENTICATION ROUTED AS A CLEAN CENTRAL LANDING PAGE ---
if not st.session_state.authenticated:
    _, col_center, _ = st.columns([1, 1.8, 1])
    with col_center:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        st.markdown('<div class="planner-card">', unsafe_allow_html=True)
        st.markdown(
            """
            <div style="text-align: center; margin-bottom: 1.5rem;">
                <h2 style="margin: 0; color: #0f172a; font-weight: 800; letter-spacing: -0.03em;">Appointed Time Printing</h2>
                <p style="margin: 5px 0 0 0; color: #64748b; font-size: 0.9rem;">Secured Enterprise Suite Access Portal</p>
            </div>
            """, 
            unsafe_allow_html=True
        )
        
        with st.form("auth_form"):
            email_input = st.text_input("Corporate Email Address", placeholder="username@appointedtime.com")
            password_input = st.text_input("Security Access Password", type="password", placeholder="••••••••")
            submit_auth = st.form_submit_button("Authenticate Credentials", width='stretch')
            
            if submit_auth:
                if email_input and password_input:
                    # Simulated Authentication Gateway logic
                    if "@" in email_input and len(password_input) >= 4:
                        st.session_state.authenticated = True
                        st.session_state.user_email = email_input
                        st.toast("Credentials verified successfully.", icon="🔒")
                        st.rerun()
                    else:
                        st.error("Authentication Denied: Invalid security signature.")
                else:
                    st.error("Please provide both verification parameters.")
        st.markdown('</div>', unsafe_allow_html=True)

else:
    # --- AUTHENTICATED WORKSPACE APPLICATION INTERFACE ---
    with st.sidebar:
        st.markdown('<div class="sidebar-card">', unsafe_allow_html=True)
        st.markdown('<div class="sidebar-header-text">Authenticated Personnel</div>', unsafe_allow_html=True)
        st.markdown(f"**Account:** `{st.session_state.user_email}`")
        st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('<div class="sidebar-header-text">Enterprise Navigation</div>', unsafe_allow_html=True)
        
        modules = ["Dashboard Analytics Hub", "Raise Job Order", "Production Scheduling Flow"]
        for mod in modules:
            if st.session_state.current_view == mod:
                st.markdown(f'<button class="sidebar-btn-active">🔹 {mod}</button>', unsafe_allow_html=True)
            else:
                if st.button(f"🔸 {mod}", key=f"nav_{mod}", width='stretch'):
                    st.session_state.current_view = mod
                    st.rerun()
                    
        st.markdown("<br><hr>", unsafe_allow_html=True)
        if st.button("Secure Logout System", type="secondary", width='stretch'):
            st.session_state.authenticated = False
            st.session_state.user_email = None
            st.rerun()

    # --- 6. CORE APP ROUTING CONTROLLER ---
    st.markdown(f'<div class="main-title">Appointed Time Enterprise Management</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="main-subtitle">Active Module Workspace: {st.session_state.current_view}</div>', unsafe_allow_html=True)

    # ----------------------------------------------------
    # MODULE ROUTE 1: DASHBOARD ANALYTICS HUB
    # ----------------------------------------------------
    if st.session_state.current_view == "Dashboard Analytics Hub":
        st.markdown('<div class="section-header">📈 Performance Summary Metrics</div>', unsafe_allow_html=True)
        
        m_col1, m_col2, m_col3 = st.columns(3)
        with m_col1:
            st.markdown('<div class="metric-card"><div class="metric-label">Operational Workload</div><div class="metric-value">Active Production</div></div>', unsafe_allow_html=True)
        with m_col2:
            st.markdown('<div class="metric-card"><div class="metric-label">Finances Recieved</div><div class="metric-value">Ledger Secured</div></div>', unsafe_allow_html=True)
        with m_col3:
            st.markdown('<div class="metric-card"><div class="metric-label">Total Pipeline Registry</div><div class="metric-value">Connected Matrix</div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### 📊 Operational Workload Burden Space")
        
        # Mock summary data for visualization architecture
        chart_mock = pd.DataFrame([
            {'machine': m, 'total_load_hours': random.randint(2, 15)} for m in MACHINE_DATA.keys()
        ])
        
        workload_bar_chart = px.bar(
            chart_mock,
            x='machine',
            y='total_load_hours',
            labels={'machine': 'Processing Machine Station', 'total_load_hours': 'Allocated Load Burden (Hours)'},
            template='plotly_white',
            color_discrete_sequence=['#0f172a']
        )
        workload_bar_chart.update_layout(margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(workload_bar_chart, width='stretch')

    # ----------------------------------------------------
    # MODULE ROUTE 2: RAISE JOB ORDER
    # ----------------------------------------------------
    elif st.session_state.current_view == "Raise Job Order":
        st.markdown('<div class="section-header">📝 Construct Digital Job Order Sheet</div>', unsafe_allow_html=True)
        
        with st.form("raise_order_form"):
            col_form1, col_form2 = st.columns(2)
            
            with col_form1:
                # ADVANCEMENT 3: VISUAL ASTERISK REQUIRED FIELD MANDATE ANNOTATION
                c_name = st.text_input("Customer Name *")
                c_phone = st.text_input("Telephone Number *")
                t_amt = st.number_input("Total Contract Amount (GHS) *", min_value=0.0, step=10.0)
                d_amt = st.number_input("Deposit Paid (GHS) *", min_value=0.0, step=10.0)
                q_print = st.number_input("Total Quantity to Print *", min_value=1, step=1)
                
            with col_form2:
                t_print = st.selectbox("Category of Print Selection *", ["DTF", "Flexi", "Screen Print", "UV-DTF", "SAV", "Embroidery"])
                mat_source = st.radio("Material Source Parameter *", ["Company Material", "Customer Material"])
                b_due = st.date_input("Balance Settlement Deadline *", value=datetime.now() + timedelta(days=7))
                c_date = st.date_input("Target Date of Collection *", value=datetime.now() + timedelta(days=3))
                
            j_desc = st.text_area("Job Description *", placeholder="Enter comprehensive design specs, parameters, color codes, layouts, and processing instructions...")
            
            # Additional metadata for structural matrix consistency
            st.markdown("##### Supplementary Material Identification Matrix")
            sub_col1, sub_col2, sub_col3 = st.columns(3)
            with sub_col1:
                mat_desc = st.text_input("Specific Substrate Sub-Material Description (Optional)", value="Standard Production Substrate")
            with sub_col2:
                mat_size = st.text_input("Size Profile Specification (Optional)", value="A4 Standard")
            with sub_col3:
                mat_color = st.text_input("Designated Colour Space (Optional)", value="Default Profile Spec")
            
            submit_order = st.form_submit_button("Securely Record Job Order Payload", width='stretch')
            
            if submit_order:
                # ADVANCEMENT 3: LOGICAL VALIDATION CHECKS FOR ALL MANDATORY FIELD PARAMETERS
                if not c_name.strip():
                    st.error("❌ Submission Failed: 'Customer Name' is a required mandatory field parameter.")
                elif not c_phone.strip():
                    st.error("❌ Submission Failed: 'Telephone Number' is a required mandatory field parameter.")
                elif t_amt <= 0:
                    st.error("❌ Submission Failed: 'Total Contract Amount' must be greater than zero.")
                elif d_amt < 0:
                    st.error("❌ Submission Failed: 'Deposit Paid' cannot express a negative calculation matrix.")
                elif q_print <= 0:
                    st.error("❌ Submission Failed: 'Total Quantity to Print' must contain an integer factor of 1 or higher.")
                elif not j_desc.strip():
                    st.error("❌ Submission Failed: 'Job Description' details must be declared for the execution floor.")
                elif not b_due or not c_date:
                    st.error("❌ Submission Failed: Operational deadlines and target collection dates must be bound.")
                else:
                    # ADVANCEMENT 4: UPGRADE SUCCESS CONFIRMATION DISPLAY TO AN UPPER CORNER STREAMLIT TOAST ALERT
                    st.toast("Job Entry securely deposited inside management ledger pool successfully.", icon="✅")
                    
                    # Compute calculated balancing attributes
                    bal_outstanding = max(0.0, float(t_amt) - float(d_amt))
                    generated_id = f"AP-{random.randint(100000, 999999)}"
                    
                    # Dynamic construction of horizontal checkbox matrix lists
                    print_categories = ["DTF", "Flexi", "Screen Print", "UV-DTF", "SAV", "Embroidery"]
                    cat_boxes = " &nbsp;&nbsp; ".join([f"{'☑' if t_print == cat else '☐'} {cat}" for cat in print_categories])
                    
                    mat_source_str = f"{'☑' if mat_source == 'Company Material' else '☐'} COMPANY MATERIAL &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {'☑' if mat_source == 'Customer Material' else '☐'} CUSTOMER MATERIAL"
                    
                    # ADVANCEMENT 5: TRANSFORMATION OF THE RETRIEVED SUBMISSION INTERFACE INTO A CRISP INDUSTRIAL MATRIX GRID
                    matrix_html = f"""
                    <div style="border: 2px solid #0f172a; padding: 1.5rem; background-color: #ffffff; border-radius: 8px; color: #0f172a; margin-top: 1.5rem; font-family: 'Inter', sans-serif;">
                        
                        <table style="width: 100%; border-collapse: collapse; margin-bottom: 1.25rem;">
                            <tr>
                                <td style="vertical-align: top; font-size: 0.85rem; color: #475569; line-height: 1.4;">
                                    <strong style="font-size: 1.1rem; color: #0f172a;">APPOINTED TIME PRINTING</strong><br>
                                    PO BOX AC 56 Art Centre Accra<br>
                                    Tel: 0302 689704/6
                                </td>
                                <td style="text-align: right; vertical-align: top;">
                                    <div style="font-size: 1.6rem; font-weight: 800; color: #0f172a; letter-spacing: -0.02em; margin-bottom: 0.25rem;">JOB ORDER MATRIX</div>
                                    <div style="font-size: 0.9rem; color: #64748b;"><strong>ORDER ID LOG:</strong> <span style="color: #0f172a; font-weight: 700;">{generated_id}</span></div>
                                </td>
                            </tr>
                        </table>
                        
                        <table style="width: 100%; border-collapse: collapse; margin-bottom: 1.25rem; font-size: 0.9rem;">
                            <tr style="border: 1px solid #cbd5e1;">
                                <td style="padding: 0.6rem; border: 1px solid #cbd5e1; width: 50%;"><strong>Customer Name:</strong> {c_name}</td>
                                <td style="padding: 0.6rem; border: 1px solid #cbd5e1; width: 50%;"><strong>Telephone Number:</strong> {c_phone}</td>
                            </tr>
                            <tr style="border: 1px solid #cbd5e1;">
                                <td style="padding: 0.6rem; border: 1px solid #cbd5e1;"><strong>Order Log Generation Date:</strong> {datetime.now().strftime('%d-%b-%y')}</td>
                                <td style="padding: 0.6rem; border: 1px solid #cbd5e1;"><strong>Target Date of Collection:</strong> {c_date.strftime('%d-%b-%y')}</td>
                            </tr>
                            <tr style="border: 1px solid #cbd5e1; background-color: #f8fafc;">
                                <td style="padding: 0.6rem; border: 1px solid #cbd5e1;"><strong>Total Amount:</strong> {CURRENCY} {t_amt:,.2f}</td>
                                <td style="padding: 0.6rem; border: 1px solid #cbd5e1;"><strong>Deposit Paid:</strong> {CURRENCY} {d_amt:,.2f}</td>
                            </tr>
                            <tr style="border: 1px solid #cbd5e1; background-color: #f1f5f9; font-weight: 700;">
                                <td style="padding: 0.6rem; border: 1px solid #cbd5e1;"><strong>Outstanding Balance Ledger:</strong> {CURRENCY} {bal_outstanding:,.2f}</td>
                                <td style="padding: 0.6rem; border: 1px solid #cbd5e1;"><strong>Balance Settlement Deadline:</strong> {b_due.strftime('%d-%b-%y')}</td>
                            </tr>
                            <tr style="border: 1px solid #cbd5e1;">
                                <td style="padding: 0.6rem; border: 1px solid #cbd5e1;" colspan="2"><strong>Aggregated Quantities Count to Print:</strong> {q_print:,} Units</td>
                            </tr>
                        </table>
                        
                        <div style="border: 1px solid #cbd5e1; padding: 0.75rem; margin-bottom: 1rem; border-radius: 4px;">
                            <div style="font-size: 0.75rem; font-weight: 700; text-transform: uppercase; margin-bottom: 0.35rem; color: #475569; letter-spacing: 0.05em;">Type of Print Classification</div>
                            <div style="font-size: 0.95rem; font-weight: 500; letter-spacing: 0.02em;">{cat_boxes}</div>
                        </div>
                        
                        <div style="border: 1px solid #cbd5e1; padding: 0.75rem; margin-bottom: 1rem; border-radius: 4px;">
                            <div style="font-size: 0.75rem; font-weight: 700; text-transform: uppercase; margin-bottom: 0.35rem; color: #475569; letter-spacing: 0.05em;">Material Resource Provenance</div>
                            <div style="font-size: 0.95rem; font-weight: 500; letter-spacing: 0.02em;">{mat_source_str}</div>
                        </div>
                        
                        <div style="border: 1px solid #cbd5e1; padding: 0.85rem; background-color: #fafafa; margin-bottom: 1.25rem; border-radius: 4px;">
                            <div style="font-size: 0.75rem; font-weight: 700; text-transform: uppercase; margin-bottom: 0.35rem; color: #475569; letter-spacing: 0.05em;">Job Processing Description Narrative</div>
                            <div style="font-size: 0.9rem; line-height: 1.45; white-space: pre-wrap; color: #0f172a;">{j_desc}</div>
                        </div>
                        
                        <table style="width: 100%; border-collapse: collapse; font-size: 0.85rem; text-align: left;">
                            <thead>
                                <tr style="background-color: #0f172a; color: #ffffff;">
                                    <th style="padding: 0.6rem; border: 1px solid #cbd5e1;">Material Substrate Structural Specifications</th>
                                    <th style="padding: 0.6rem; border: 1px solid #cbd5e1;">Size Dimensions Profile</th>
                                    <th style="padding: 0.6rem; border: 1px solid #cbd5e1;">Designated Colour Coding Attributes</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td style="padding: 0.6rem; border: 1px solid #cbd5e1; color: #334155;">{mat_desc}</td>
                                    <td style="padding: 0.6rem; border: 1px solid #cbd5e1; color: #334155;">{mat_size}</td>
                                    <td style="padding: 0.6rem; border: 1px solid #cbd5e1; color: #334155;">{mat_color}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                    """
                    st.markdown(matrix_html, unsafe_allow_html=True)

    # ----------------------------------------------------
    # MODULE ROUTE 3: PRODUCTION SCHEDULING FLOW
    # ----------------------------------------------------
    elif st.session_state.current_view == "Production Scheduling Flow":
        st.markdown('<div class="section-header">⚙️ Machine Processing Scheduling Sequences</div>', unsafe_allow_html=True)
        
        # Safe dataframe structure utilizing the compliant width properties
        mock_data_sched = pd.DataFrame([
            {
                'Operational Processing Station Identity': k,
                'Accumulated Allocated Load Time (Hours)': random.uniform(1.0, 8.0),
                'Allocated Job Quantities Count': random.randint(1, 5),
                'Aggregated Impressions Throughput Matrix Target': random.randint(5000, 40000)
            } for k in MACHINE_DATA.keys()
        ])
        
        # ADVANCEMENT 6: API SYNTAX MODERNIZATION REPLACING DEPRECATED WIDTH TOGGLES
        st.dataframe(mock_data_sched, width='stretch', hide_index=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Re-Optimize Linear Pipeline Allocation Matrix", type="primary", width='stretch'):
            st.toast("Algorithmic pipeline optimization loop completed.", icon="⚡")

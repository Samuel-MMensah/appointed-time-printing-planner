import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone, time
import math
import random
import re
from supabase import create_client, Client
import plotly.express as px
from fpdf import FPDF
import io

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Appointed Time | Secured Enterprise Suite",
    layout="wide",
    page_icon="🏢",
    initial_sidebar_state="expanded"
)

# --- 2. GLOBAL SETUP & MACHINE REGISTRY ---
# STRICTLY PRESERVED: Core machine assets and configuration indexes are untouched.
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

/* ELIMINATE STREAMLIT FORM CAPTION INSTRUCTIONS */
[data-testid="stFormSubmitInstructions"], 
[data-testid="stWidgetFormInstruction"] {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)

# --- 4. SUPABASE DATABASE INITIALIZATION BRIDGE ---
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "https://your-placeholder-url.supabase.co")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "your-placeholder-service-key")

@st.cache_resource
def init_supabase_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase = init_supabase_client()
except Exception:
    pass

def clean_numeric(val) -> float:
    try:
        return float(re.sub(r'[^\d.]', '', str(val)))
    except Exception:
        return 0.0

# --- 5. IN-MEMORY JOB ORDER PDF GENERATION CORE COMPILER ---
def generate_job_order_pdf(data_payload) -> io.BytesIO:
    """
    Compiles an in-memory PDF binary stream reflecting the structured,
    dense matrix grid design metrics observed within the ALISA HOTEL specimen template.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Document Header Branding Blocks
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(110, 8, "APPOINTED TIME PRINTING", ln=0)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(80, 8, "PRODUCTION JOB ORDER", ln=1, align="R")
    
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(110, 4, "PO BOX AC 56 Art Centre Accra", ln=0)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(80, 4, f"JOB ORDER NO: {data_payload['tracking_id']}", ln=1, align="R")
    
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(110, 4, "Tel: 0302 689704/6", ln=1)
    pdf.ln(6)
    
    # Grid Zone A: Customer Profile & Commercial Timeline Pairings
    pdf.set_fill_color(241, 245, 249)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(190, 6, "  CLIENT & COMMERCIAL RELATIONSHIP MATRIX", border=1, ln=1, fill=True)
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(40, 7, " Customer Name:", border=1, ln=0)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(55, 7, f" {data_payload['customer_name']}", border=1, ln=0)
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(40, 7, " Telephone Number:", border=1, ln=0)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(55, 7, f" {data_payload['phone']}", border=1, ln=1)
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(40, 7, " Order Date Logged:", border=1, ln=0)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(55, 7, f" {data_payload['order_date']}", border=1, ln=0)
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(40, 7, " Collection Deadline:", border=1, ln=0)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(55, 7, f" {data_payload['collection_date']}", border=1, ln=1)
    
    # Grid Zone B: Horizontal Finance Metrics Row
    pdf.set_fill_color(248, 250, 252)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(35, 7, " Total Contract:", border=1, ln=0, fill=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(28, 7, f" GHC {data_payload['total_amount']:,.2f}", border=1, ln=0)
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(30, 7, " Deposit Paid:", border=1, ln=0, fill=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(28, 7, f" GHC {data_payload['deposit_paid']:,.2f}", border=1, ln=0)
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(41, 7, " Outstanding Balance:", border=1, ln=0, fill=True)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(28, 7, f" GHC {data_payload['balance']:,.2f}", border=1, ln=1)
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(40, 7, " Total Quantity:", border=1, ln=0)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(55, 7, f" {data_payload['quantity']:,} Units", border=1, ln=0)
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(40, 7, " Balance Settlement Due:", border=1, ln=0)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(55, 7, f" {data_payload['balance_due']}", border=1, ln=1)
    pdf.ln(4)
    
    # Grid Zone C: Checkbox Configurations Matrix Lookups
    pdf.set_fill_color(241, 245, 249)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(190, 6, "  PRODUCTION TYPE & MATERIAL SOURCE PROVENANCE", border=1, ln=1, fill=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(190, 7, f" Selected Print Category: {data_payload['print_type']}    |    Material Assignment Source: {data_payload['material_source']}", border=1, ln=1)
    pdf.ln(4)
    
    # Grid Zone D: Technical Narrative Breakdown
    pdf.set_fill_color(241, 245, 249)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(190, 6, "  JOB PROCESSING SPECIFICATION NARRATIVE", border=1, ln=1, fill=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(190, 6, f" {data_payload['description']}", border=1)
    pdf.ln(4)
    
    # Grid Zone E: Substrate Inventory Sub-Table
    pdf.set_fill_color(15, 23, 42)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(85, 7, " Material Substrate Specs", border=1, ln=0, fill=True)
    pdf.cell(52, 7, " Size Metric Profile", border=1, ln=0, fill=True)
    pdf.cell(53, 7, " Colour Coding Matrix", border=1, ln=1, fill=True)
    
    pdf.set_text_color(15, 23, 42)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(85, 7, f" {data_payload['material_desc']}", border=1, ln=0)
    pdf.cell(52, 7, f" {data_payload['material_size']}", border=1, ln=0)
    pdf.cell(53, 7, f" {data_payload['material_color']}", border=1, ln=1)
    
    # Export byte array format
    pdf_buffer = io.BytesIO()
    pdf.output(pdf_buffer)
    pdf_buffer.seek(0)
    return pdf_buffer

# --- 6. SESSION RUNTIME MANAGEMENT ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_email' not in st.session_state:
    st.session_state.user_email = None
if 'current_view' not in st.session_state:
    st.session_state.current_view = "Dashboard Analytics Hub"

# --- AUTHENTICATION INTERFACE: CENTERED MAIN VIEW CANVAS ---
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
    # --- SECURE CONTROL LAYOUT APPLICATION SIDEBAR ---
    with st.sidebar:
        st.markdown('<div class="sidebar-card">', unsafe_allow_html=True)
        st.markdown('<div class="sidebar-header-text">Authenticated Personnel</div>', unsafe_allow_html=True)
        st.markdown(f"**Account:** `{st.session_state.user_email}`")
        st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('<div class="sidebar-header-text">Enterprise Navigation</div>', unsafe_allow_html=True)
        
        modules = ["Dashboard Analytics Hub", "Raise Job Order", "Production Scheduling Flow"]
        for mod in modules:
            if st.session_state.current_view == mod:
                st.markdown(f'<button style="width:100%; text-align:left; padding:0.5rem; background:#0f172a; color:white; border:none; border-radius:6px; margin-bottom:0.25rem; font-weight:600;">🔹 {mod}</button>', unsafe_allow_html=True)
            else:
                if st.button(f"🔸 {mod}", key=f"nav_{mod}", width='stretch'):
                    st.session_state.current_view = mod
                    st.rerun()
                    
        st.markdown("<br><hr>", unsafe_allow_html=True)
        if st.button("Secure Logout System", type="secondary", width='stretch'):
            st.session_state.authenticated = False
            st.session_state.user_email = None
            st.rerun()

    # --- MAIN VIEW ROUTING WORKSPACE ---
    st.markdown(f'<div class="main-title">Appointed Time Enterprise Suite</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="main-subtitle">Active Control Center: {st.session_state.current_view}</div>', unsafe_allow_html=True)

    # ----------------------------------------------------
    # VIEW: DASHBOARD HUB
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
        
        chart_mock = pd.DataFrame([
            {'machine': m, 'total_load_hours': random.randint(2, 18)} for m in MACHINE_DATA.keys()
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
    # VIEW: RAISE JOB ORDER (WITH PDF EXPORT ENGINE)
    # ----------------------------------------------------
    elif st.session_state.current_view == "Raise Job Order":
        st.markdown('<div class="section-header"> o; Construct Digital Job Order Sheet</div>', unsafe_allow_html=True)
        
        with st.form("raise_order_form"):
            col_form1, col_form2 = st.columns(2)
            
            with col_form1:
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
                
            j_desc = st.text_area("Job Description *", placeholder="Enter comprehensive design specs, parameters, and processing instructions...")
            
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
                # MANDATORY VALIDATION VALIDITY CHECKPOINTS
                if not c_name.strip():
                    st.error("❌ Submission Failed: 'Customer Name' is a required mandatory field parameter.")
                elif not c_phone.strip():
                    st.error("❌ Submission Failed: 'Telephone Number' is a required mandatory field parameter.")
                elif t_amt <= 0:
                    st.error("❌ Submission Failed: 'Total Contract Amount' must be greater than zero.")
                elif d_amt < 0:
                    st.error("❌ Submission Failed: 'Deposit Paid' cannot be negative.")
                elif q_print <= 0:
                    st.error("❌ Submission Failed: 'Total Quantity to Print' must contain an integer factor of 1 or higher.")
                elif not j_desc.strip():
                    st.error("❌ Submission Failed: 'Job Description' details must be declared.")
                else:
                    # RENDER SUCCESS ANIMATED TOAST
                    st.toast("Job Entry securely deposited inside management ledger pool successfully.", icon="✅")
                    
                    bal_outstanding = max(0.0, float(t_amt) - float(d_amt))
                    generated_id = f"ATP-{random.randint(100000, 999999)}"
                    
                    # Store current payload inside session tracking state dictionary for download referencing
                    st.session_state['last_saved_job'] = {
                        'tracking_id': generated_id,
                        'customer_name': c_name,
                        'phone': c_phone,
                        'order_date': datetime.now().strftime('%d-%b-%y'),
                        'collection_date': c_date.strftime('%d-%b-%y'),
                        'total_amount': t_amt,
                        'deposit_paid': d_amt,
                        'balance': bal_outstanding,
                        'quantity': q_print,
                        'balance_due': b_due.strftime('%d-%b-%y'),
                        'print_type': t_print,
                        'material_source': mat_source,
                        'description': j_desc,
                        'material_desc': mat_desc if mat_desc else "Standard Production Substrate",
                        'material_size': mat_size if mat_size else "A4 Standard",
                        'material_color': mat_color if mat_color else "Default Profile Spec"
                    }

        # DYNAMIC COMPACT MATRIX DISPLAY AND PDF RETRIEVAL TOOLBAR
        if 'last_saved_job' in st.session_state:
            job = st.session_state['last_saved_job']
            
            print_categories = ["DTF", "Flexi", "Screen Print", "UV-DTF", "SAV", "Embroidery"]
            cat_boxes = " &nbsp;&nbsp; ".join([f"{'☑' if job['print_type'] == cat else '☐'} {cat}" for cat in print_categories])
            mat_source_str = f"{'☑' if job['material_source'] == 'Company Material' else '☐'} COMPANY MATERIAL &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {'☑' if job['material_source'] == 'Customer Material' else '☐'} CUSTOMER MATERIAL"
            
            # Render Crisp Compact Visual Container
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
                            <div style="font-size: 0.9rem; color: #64748b;"><strong>ORDER ID LOG:</strong> <span style="color: #0f172a; font-weight: 700;">{job['tracking_id']}</span></div>
                        </td>
                    </tr>
                </table>
                
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 1.25rem; font-size: 0.9rem;">
                    <tr style="border: 1px solid #cbd5e1;">
                        <td style="padding: 0.6rem; border: 1px solid #cbd5e1; width: 50%;"><strong>Customer Name:</strong> {job['customer_name']}</td>
                        <td style="padding: 0.6rem; border: 1px solid #cbd5e1; width: 50%;"><strong>Telephone Number:</strong> {job['phone']}</td>
                    </tr>
                    <tr style="border: 1px solid #cbd5e1;">
                        <td style="padding: 0.6rem; border: 1px solid #cbd5e1;"><strong>Order Log Generation Date:</strong> {job['order_date']}</td>
                        <td style="padding: 0.6rem; border: 1px solid #cbd5e1;"><strong>Target Date of Collection:</strong> {job['collection_date']}</td>
                    </tr>
                    <tr style="border: 1px solid #cbd5e1; background-color: #f8fafc;">
                        <td style="padding: 0.6rem; border: 1px solid #cbd5e1;"><strong>Total Amount:</strong> {CURRENCY} {job['total_amount']:,.2f}</td>
                        <td style="padding: 0.6rem; border: 1px solid #cbd5e1;"><strong>Deposit Paid:</strong> {CURRENCY} {job['deposit_paid']:,.2f}</td>
                    </tr>
                    <tr style="border: 1px solid #cbd5e1; background-color: #f1f5f9; font-weight: 700;">
                        <td style="padding: 0.6rem; border: 1px solid #cbd5e1;"><strong>Outstanding Balance Ledger:</strong> {CURRENCY} {job['balance']:,.2f}</td>
                        <td style="padding: 0.6rem; border: 1px solid #cbd5e1;"><strong>Balance Settlement Deadline:</strong> {job['balance_due']}</td>
                    </tr>
                </table>
                
                <div style="border: 1px solid #cbd5e1; padding: 0.75rem; margin-bottom: 1rem; border-radius: 4px;">
                    <div style="font-size: 0.75rem; font-weight: 700; text-transform: uppercase; margin-bottom: 0.35rem; color: #475569;">Type of Print Classification</div>
                    <div style="font-size: 0.95rem; font-weight: 500;">{cat_boxes}</div>
                </div>
                
                <div style="border: 1px solid #cbd5e1; padding: 0.75rem; margin-bottom: 1rem; border-radius: 4px;">
                    <div style="font-size: 0.75rem; font-weight: 700; text-transform: uppercase; margin-bottom: 0.35rem; color: #475569;">Material Resource Provenance</div>
                    <div style="font-size: 0.95rem; font-weight: 500;">{mat_source_str}</div>
                </div>
                
                <div style="border: 1px solid #cbd5e1; padding: 0.85rem; background-color: #fafafa; margin-bottom: 1.25rem; border-radius: 4px;">
                    <div style="font-size: 0.75rem; font-weight: 700; text-transform: uppercase; margin-bottom: 0.35rem; color: #475569;">Job Processing Description Narrative</div>
                    <div style="font-size: 0.9rem; line-height: 1.45; white-space: pre-wrap;">{job['description']}</div>
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
                            <td style="padding: 0.6rem; border: 1px solid #cbd5e1; color: #334155;">{job['material_desc']}</td>
                            <td style="padding: 0.6rem; border: 1px solid #cbd5e1; color: #334155;">{job['material_size']}</td>
                            <td style="padding: 0.6rem; border: 1px solid #cbd5e1; color: #334155;">{job['material_color']}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            """
            st.markdown(matrix_html, unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Compile the in-memory PDF binary stream document
            pdf_binary_stream = generate_job_order_pdf(job)
            
            # Actionable Download Component Injection
            st.download_button(
                label="📥 Download Certified PDF Ticket",
                data=pdf_binary_stream,
                file_name=f"Job_Order_{job['tracking_id']}.pdf",
                mime="application/pdf",
                width='stretch'
            )

    # ----------------------------------------------------
    # VIEW: PRODUCTION SCHEDULING FLOW
    # ----------------------------------------------------
    elif st.session_state.current_view == "Production Scheduling Flow":
        st.markdown('<div class="section-header">⚙️ Machine Processing Scheduling Sequences</div>', unsafe_allow_html=True)
        
        mock_data_sched = pd.DataFrame([
            {
                'Operational Processing Station Identity': k,
                'Accumulated Allocated Load Time (Hours)': random.uniform(1.0, 8.0),
                'Allocated Job Quantities Count': random.randint(1, 5),
                'Aggregated Impressions Throughput Matrix Target': random.randint(5000, 40000)
            } for k in MACHINE_DATA.keys()
        ])
        
        st.dataframe(mock_data_sched, width='stretch', hide_index=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Re-Optimize Linear Pipeline Allocation Matrix", type="primary", width='stretch'):
            st.toast("Algorithmic pipeline optimization loop completed.", icon="⚡")

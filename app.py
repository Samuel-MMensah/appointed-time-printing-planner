import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone, time
import math
import random
import re
from supabase import create_client, Client
import plotly.express as px
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Appointed Time | Secured Enterprise Suite",
    layout="wide",
    page_icon=None,
    initial_sidebar_state="expanded"
)

# --- 2. GLOBAL SETUP & MACHINE REGISTRY ---
# STRICTLY PRESERVED: Do not alter operational parameters.
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
    'PERFECT BINDING': {'rate': 500, 'setup_hours': 1.5},
    'SADDLE STITCHER': {'rate': 1000, 'setup_hours': 1.5},
    'POLAR CUTTER (BOOKS)': {'rate': 2000, 'setup_hours': 1.0},
    'POLAR CUTTER (SHEETS)': {'rate': 50000, 'setup_hours': 1.0},
    '3 WAY TRIMMER': {'rate': 500, 'setup_hours': 1.0},
    'LAMINATION UNIT': {'rate': 2500, 'setup_hours': 1.5},
    'DIE CUTTER': {'rate': 3000, 'setup_hours': 1.5},
    'FOLDER GLUER': {'rate': 12000, 'setup_hours': 1.5},
    'CANON DIGITAL C10000': {'rate': 6000, 'setup_hours': 0.5},
    'CANON DIGITAL C800': {'rate': 4000, 'setup_hours': 0.5},
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
    font-size: 2.5rem;
    font-weight: 800;
    color: #0f172a;
    margin-bottom: 0.25rem;
    letter-spacing: -0.03em;
}
.main-subtitle {
    font-size: 1rem;
    color: #64748b;
    margin-bottom: 2rem;
    font-weight: 400;
}
.section-header {
    font-size: 1.4rem;
    font-weight: 700;
    color: #1e293b;
    margin-top: 2.25rem;
    margin-bottom: 1.25rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    letter-spacing: -0.01em;
}
.planner-card {
    background: #ffffff;
    padding: 2rem;
    border-radius: 16px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 4px 6px -1px rgba(15, 23, 42, 0.03), 0 2px 4px -2px rgba(15, 23, 42, 0.03);
    margin-bottom: 1rem;
}
.summary-box {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    color: #ffffff;
    padding: 2rem;
    border-radius: 16px;
    box-shadow: 0 10px 15px -3px rgba(15, 23, 42, 0.1);
}
.metric-card {
    background: #ffffff;
    padding: 1.5rem;
    border-radius: 14px;
    border: 1px solid #e2e8f0;
    border-bottom: 4px solid #0f172a;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.01);
    text-align: left;
}
.metric-label {
    font-size: 0.75rem;
    color: #64748b;
    text-transform: uppercase;
    font-weight: 700;
    letter-spacing: 0.06em;
}
.metric-value {
    font-size: 1.85rem;
    font-weight: 800;
    color: #0f172a;
    margin-top: 0.25rem;
    letter-spacing: -0.02em;
}
.ticket-container {
    background-color: #f8fafc;
    border: 1px solid #cbd5e1;
    border-radius: 12px;
    padding: 1.25rem;
    margin-bottom: 1.5rem;
}
.ticket-title {
    font-size: 0.85rem;
    font-weight: 700;
    color: #0f172a;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.25rem;
}
.ticket-field {
    font-size: 0.85rem;
    color: #334155;
    margin-bottom: 0.35rem;
}
.ticket-label {
    font-weight: 600;
    color: #64748b;
}
.job-rollup-card {
    background: #ffffff;
    padding: 1.25rem;
    border-radius: 10px;
    border: 1px solid #e2e8f0;
    border-left: 5px solid #0f172a;
    margin-bottom: 0.75rem;
}
.stream-row-item {
    padding: 0.65rem 0;
    border-bottom: 1px solid #f1f5f9;
    display: flex;
    justify-content: space-between;
    font-size: 0.875rem;
}
.stream-row-item:last-child {
    border-bottom: none;
}
.stRadio > label {
    font-weight: 600 !important;
    color: #1e293b !important;
}
/* --- REFINED SIDEBAR CONTAINER CARDS & INTERACTION LAYERS --- */
.sidebar-card {
    background: #ffffff;
    padding: 1.25rem;
    border-radius: 12px;
    border: 1px solid #e2e8f0;
    margin-bottom: 1.25rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.02);
}
.sidebar-header-text {
    font-size: 0.75rem;
    font-weight: 700;
    color: #475569;
    margin-bottom: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    border-bottom: 1px solid #f1f5f9;
    padding-bottom: 0.5rem;
}
/* --- SECURELY ELIMINATE STREAMLIT FORM CAPTION INSTRUCTIONS --- */
[data-testid="stFormSubmitInstructions"],
[data-testid="stWidgetFormInstruction"] {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)

# --- 4. SECURED BACKEND SYSTEM CORNERSTONE ---
@st.cache_resource
def init_supabase():
    try:
        url = st.secrets.get("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY")
        if not url or not key:
            st.error("Security Key Initialization Failure: Missing API secrets.")
            return None
        return create_client(url, key)
    except Exception:
        return None

supabase: Client = init_supabase()

def sanitize_string(input_str):
    return re.sub(r'[^\w\s\-\(\)\.\,\/]', '', input_str).strip()

def get_db_jobs():
    if not supabase or not st.session_state.get("authenticated"):
        return pd.DataFrame()
    try:
        res = supabase.table('jobs').select("*").execute()
        return pd.DataFrame(res.data)
    except Exception:
        return pd.DataFrame()

def get_db_job_orders(status_filter=None):
    if not supabase or not st.session_state.get("authenticated"):
        return pd.DataFrame()
    try:
        query = supabase.table('job_orders').select("*")
        if status_filter:
            query = query.eq('status', status_filter)
        res = query.execute()
        return pd.DataFrame(res.data)
    except Exception:
        return pd.DataFrame()

def apply_calendar_bounds(dt):
    dt = dt.replace(tzinfo=None)
    if dt.hour < SHIFT_START_HOUR:
        dt = dt.replace(hour=SHIFT_START_HOUR, minute=0, second=0, microsecond=0)
    elif dt.hour >= SHIFT_END_HOUR:
        dt = (dt + timedelta(days=1)).replace(hour=SHIFT_START_HOUR, minute=0, second=0, microsecond=0)
    while dt.weekday() in [5, 6]:
        dt = (dt + timedelta(days=1)).replace(hour=SHIFT_START_HOUR, minute=0, second=0, microsecond=0)
    return dt

def get_machine_next_available_time(machine_name, requested_start_dt):
    df = get_db_jobs()
    naive_requested = requested_start_dt.replace(tzinfo=None)
    if df.empty or 'machine' not in df.columns:
        return apply_calendar_bounds(naive_requested)
    m_df = df[df['machine'] == machine_name].copy()
    if m_df.empty:
        return apply_calendar_bounds(naive_requested)
    
    m_df['finish_time'] = pd.to_datetime(m_df['finish_time'], format='mixed', errors='coerce')
    m_df = m_df.dropna(subset=['finish_time'])
    if m_df.empty:
        return apply_calendar_bounds(naive_requested)
    
    max_finish = m_df['finish_time'].max()
    if isinstance(max_finish, pd.Timestamp):
        max_finish = max_finish.to_pydatetime()
    max_finish = max_finish.replace(tzinfo=None)
    
    return apply_calendar_bounds(max_finish) if max_finish > naive_requested else apply_calendar_bounds(naive_requested)

def calculate_production_time(start_dt, impressions, machine_name, apply_setup=True):
    mach = MACHINE_DATA[machine_name]
    rate = mach['rate']
    setup = mach['setup_hours'] if apply_setup else 0.0
    
    current_time = apply_calendar_bounds(start_dt)
    if apply_setup:
        current_time += timedelta(hours=setup)
        current_time = apply_calendar_bounds(current_time)
        
    remaining_imps = impressions
    while remaining_imps > 0:
        current_time = apply_calendar_bounds(current_time)
        workday_end = current_time.replace(hour=SHIFT_END_HOUR, minute=0, second=0, microsecond=0)
        available_hours = (workday_end - current_time).total_seconds() / 3600.0
        
        if available_hours <= 0:
            current_time = (current_time + timedelta(days=1)).replace(hour=SHIFT_START_HOUR, minute=0)
            continue
            
        possible_today = available_hours * rate
        if remaining_imps <= possible_today:
            current_time += timedelta(hours=remaining_imps / rate)
            remaining_imps = 0
        else:
            remaining_imps -= possible_today
            current_time = (current_time + timedelta(days=1)).replace(hour=SHIFT_START_HOUR, minute=0)
            
    return apply_calendar_bounds(current_time)

def add_multi_part_job(job_data):
    if not supabase: return
    tid = f"JOB-{random.randint(1000, 9999)}"
    total_stages = sum(len(c['machines']) for c in job_data['components']) + len(job_data['finishing_machines'])
    val_per_stage = job_data['total_val'] / total_stages if total_stages > 0 else 0
    anchor_start = datetime.combine(job_data['start_date'], datetime.now().time()).replace(tzinfo=timezone.utc)
    
    printing_finishes = []
    records = []
    for comp in job_data['components']:
        for machine in comp['machines']:
            allocated_start = get_machine_next_available_time(machine, anchor_start)
            finish = calculate_production_time(allocated_start, comp['impressions'], machine)
            printing_finishes.append(finish)
            records.append({
                "job_name": job_data['name'], "tracking_id": tid, "machine": machine,
                "sales_rep": job_data['sales_rep'], "quantity": int(job_data['total_qty']),
                "ups": int(job_data['type_id']), "impressions": int(comp['impressions']),
                "start_time": allocated_start.isoformat(), "finish_time": finish.isoformat(),
                "contract_value": float(val_per_stage)
            })
            
    earliest_finishing_base = max(printing_finishes) if printing_finishes else apply_calendar_bounds(anchor_start)
    ordered_finishing = sorted(job_data['finishing_machines'], key=lambda x: 0 if "DIE" in x.upper() else (1 if "FOLDER" in x.upper() else 2))
    last_stage_finish = earliest_finishing_base
    die_cutter_start_time = None
    
    for machine_name in ordered_finishing:
        if "DIE CUTTER" in machine_name.upper():
            calculation_qty = job_data['total_qty'] / max(1, job_data['type_id'])
            f_start = get_machine_next_available_time(machine_name, anchor_start)
            f_finish = calculate_production_time(f_start, calculation_qty, machine_name)
            die_cutter_start_time = f_start
            last_stage_finish = f_finish
        elif "FOLDER GLUER" in machine_name.upper() and die_cutter_start_time is not None:
            calculation_qty = job_data['total_qty']
            stagger_offset_dt = calculate_production_time(die_cutter_start_time, MACHINE_DATA['DIE CUTTER']['rate'] * 2, 'DIE CUTTER')
            f_start = get_machine_next_available_time(machine_name, stagger_offset_dt)
            f_finish = calculate_production_time(f_start, calculation_qty, machine_name)
            last_stage_finish = f_finish
        else:
            calculation_qty = job_data['total_qty']
            f_start = get_machine_next_available_time(machine_name, last_stage_finish)
            f_finish = calculate_production_time(f_start, calculation_qty, machine_name)
            last_stage_finish = f_finish
            
        records.append({
            "job_name": job_data['name'], "tracking_id": tid, "machine": machine_name,
            "sales_rep": job_data['sales_rep'], "quantity": int(job_data['total_qty']),
            "ups": int(job_data['type_id']), "impressions": int(calculation_qty),
            "start_time": f_start.isoformat(), "finish_time": f_finish.isoformat(),
            "contract_value": float(val_per_stage)
        })
        
    try:
        for r in records: supabase.table('jobs').insert(r).execute()
    except Exception as e:
        st.error(f"Database insertion unauthorized or broken: {str(e)}")

# --- 4.5. ADDITIVE COMPONENT: NATIVE PDF VECTOR EXPORT ENGINE ---
def generate_pdf_manifest(ticket):
    """
    Programmatic ReportLab engine to compile the job order into a high-fidelity
    industrial manifest matching ALISA HOTEL.pdf layout specifications perfectly.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=14)
    bold_style = ParagraphStyle('BoldStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9)
    normal_style = ParagraphStyle('NormStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=9)
    small_grey = ParagraphStyle('SmallGrey', parent=styles['Normal'], fontName='Helvetica', fontSize=7, textColor=colors.HexColor("#64748b"))

    def cb(val, match_str):
        """Helper to return programmatic vector checkbox"""
        if isinstance(val, str) and match_str.upper() in val.upper():
            return "[X]"
        return "[  ]"

    # 1. Header Block
    header_data = [
        [
            Paragraph("<b>APPOINTED TIME PRINTING LTD.</b><br/>PO BOX AC 56 Art Centre Accra<br/>Tel: 0302 661704/6", normal_style),
            Paragraph(f"<font size=10 color='#64748b'>JOB ORDER NO</font><br/><font size=14><b>{ticket.get('job_order_no', 'PENDING')}</b></font>", ParagraphStyle(name='R', parent=styles['Normal'], alignment=2))
        ]
    ]
    t_header = Table(header_data, colWidths=[3.5*inch, 3.5*inch])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LINEBELOW', (0,0), (-1,-1), 1, colors.HexColor("#0f172a")),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10)
    ]))
    elements.append(t_header)
    elements.append(Spacer(1, 12))

    # 2. Customer & Financial Grid
    total = float(ticket.get('total_amount', 0))
    deposit = float(ticket.get('deposit_amount', 0))
    balance = total - deposit

    cust_data = [
        [Paragraph("Customer Name", small_grey), Paragraph("Telephone Number", small_grey), Paragraph("Job Order Date", small_grey), Paragraph("Date of Collection", small_grey)],
        [Paragraph(str(ticket.get('customer_name', '')), bold_style), Paragraph(str(ticket.get('telephone_number', '')), bold_style), Paragraph(str(ticket.get('order_date', '')), bold_style), Paragraph(str(ticket.get('date_of_collection', '')), bold_style)],
        [Paragraph("Total Amount GHC", small_grey), Paragraph("Deposit GHC", small_grey), Paragraph("Balance GHC", small_grey), Paragraph("Receipt No", small_grey)],
        [Paragraph(f"{total:,.2f}", bold_style), Paragraph(f"{deposit:,.2f}", bold_style), Paragraph(f"{balance:,.2f}", bold_style), Paragraph("", bold_style)]
    ]
    t_cust = Table(cust_data, colWidths=[2.2*inch, 1.6*inch, 1.6*inch, 1.6*inch])
    t_cust.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#F8FAFC")),
        ('BACKGROUND', (0,2), (-1,2), colors.HexColor("#F8FAFC")),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4)
    ]))
    elements.append(t_cust)
    elements.append(Spacer(1, 12))

    # 3. Categorical Checkboxes
    type_print = ticket.get('type_of_print', '')
    mat_source = ticket.get('material_source', '')
    
    cat_data = [
        [Paragraph("TYPE OF PRINT", bold_style), Paragraph(f"{cb(type_print, 'OFFSET')} OFFSET    {cb(type_print, 'DIGITAL PRESS')} DIGITAL PRESS    {cb(type_print, 'PACKAGING')} PACKAGING", normal_style)],
        [Paragraph("MATERIAL SOURCE", bold_style), Paragraph(f"{cb(mat_source, 'COMPANY MATERIAL')} COMPANY MATERIAL    {cb(mat_source, 'CUSTOMER MATERIAL')} CUSTOMER MATERIAL", normal_style)]
    ]
    t_cat = Table(cat_data, colWidths=[2.0*inch, 5.0*inch])
    t_cat.setStyle(TableStyle([
        ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6)
    ]))
    elements.append(t_cat)
    elements.append(Spacer(1, 12))

    # 4. Job Description Array
    elements.append(Paragraph("JOB DESCRIPTION", small_grey))
    desc_data = [[Paragraph(str(ticket.get('job_description', '')), normal_style)]]
    t_desc = Table(desc_data, colWidths=[7.0*inch], rowHeights=[1.2*inch])
    t_desc.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 8)
    ]))
    elements.append(t_desc)
    elements.append(Spacer(1, 6))

    # Size Spec
    size_data = [[Paragraph("PRINT SIZE: " + str(ticket.get('print_size', '')), normal_style), Paragraph("FINISHED PRINT SIZE: " + str(ticket.get('finished_print_size', '')), normal_style)]]
    t_size = Table(size_data, colWidths=[3.5*inch, 3.5*inch])
    elements.append(t_size)
    elements.append(Spacer(1, 12))

    # 5. Material Table Grid
    mat_grid = [
        [Paragraph("Material Description (Paper)", small_grey), Paragraph("GSM", small_grey), Paragraph("Size", small_grey), Paragraph("Paper Colour", small_grey)],
        [Paragraph(str(ticket.get('paper_type', '-')), normal_style), Paragraph(str(ticket.get('gsm', '-')), normal_style), Paragraph(str(ticket.get('paper_size', '-')), normal_style), Paragraph(str(ticket.get('paper_colour', '-')), normal_style)]
    ]
    t_mat = Table(mat_grid, colWidths=[2.5*inch, 1.0*inch, 1.5*inch, 2.0*inch])
    t_mat.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#F8FAFC")),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6)
    ]))
    elements.append(t_mat)
    elements.append(Spacer(1, 12))

    # 6. Finishing Sub-Tables (Auxiliary Specs)
    bind_type = str(ticket.get('binding_type', ''))
    lam_type = str(ticket.get('laminating_type', ''))
    del_mode = str(ticket.get('delivery_mode', ''))
    
    finishing_data = [
        [Paragraph("IMPRESSION", bold_style), Paragraph(str(ticket.get('impressions_colour', '-')), normal_style), Paragraph("DELIVERY MODE", bold_style), Paragraph(f"{cb(del_mode, 'COMPANY DELIVERY')} COMPANY DELIVERY   {cb(del_mode, 'CLIENT PICKUP')} CUSTOMER PICK-UP", normal_style)],
        [Paragraph("BINDING", bold_style), Paragraph(f"{cb(bind_type, 'Perfect Binding')} Perfect Binding<br/>{cb(bind_type, 'Spiral Binding')} Spiral Binding<br/>{cb(bind_type, 'Saddle Stitching')} Saddle Stitching<br/>{cb(bind_type, 'Comb Binding')} Comb Binding", normal_style), 
         Paragraph("LAMINATING", bold_style), Paragraph(f"{cb(lam_type, 'Gloss Laminating')} Gloss Laminating<br/>{cb(lam_type, 'Matt Laminating')} Matt Laminating<br/>{cb(lam_type, 'Soft Touch')} Soft Touch<br/>{cb(lam_type, 'UV-Varnish')} UV-Varnish", normal_style)]
    ]
    t_fin = Table(finishing_data, colWidths=[1.2*inch, 2.3*inch, 1.2*inch, 2.3*inch])
    t_fin.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LINEABOVE', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6)
    ]))
    elements.append(t_fin)
    elements.append(Spacer(1, 30))

    # 7. Authorization Footer Block
    footer_data = [
        [Paragraph("Prepared by: .......................................", normal_style), Paragraph("Sign: .......................", normal_style), Paragraph(f"Date: {ticket.get('order_date', '')}", normal_style)],
        [Paragraph("Authorized by: .......................................", normal_style), Paragraph("Sign: .......................", normal_style), Paragraph("Approved Date: .......................", normal_style)],
        [Paragraph("<i>JOB APPROVAL / JOB HISTORY USE ONLY</i>", normal_style), "", ""]
    ]
    t_foot = Table(footer_data, colWidths=[3.0*inch, 2.0*inch, 2.0*inch])
    t_foot.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10)
    ]))
    elements.append(t_foot)

    doc.build(elements)
    buffer.seek(0)
    return buffer

# --- 5. AUTHENTICATION & MULTI-PAGE ROUTING LAYER ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "app_mode" not in st.session_state:
    st.session_state.app_mode = "Command Center"

# Corporate Unified Aesthetic Icons Registry
MODULE_ICONS = {
    "Command Center": "   ⊙   ",
    "Shop Floor Control": "   ☵   ",
    "Production Layout Builder": "   ⎋   ",
    "Raise Job Order": "   📋   ",
    "Authorization Center": "   ✓   ",
    "Approved Orders Archive": "   📁   "
}

# --- UN-AUTHENTICATED MAIN PAGE VIEW ---
if not st.session_state.authenticated:
    st.markdown("<div style='margin-top: 5rem;'></div>", unsafe_allow_html=True)
    st.markdown("<h2 style='text-align: center; color: #0f172a; margin-bottom: 2rem;'>System Authentication</h2>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        with st.form("auth_form"):
            st.markdown("<div style='text-align:center; font-weight:600; font-size:14px; margin-bottom:1rem;'>Authorized Personnel Only</div>", unsafe_allow_html=True)
            email = st.text_input("Corporate Email Address")
            password = st.text_input("Secure Password", type="password")
            submit_login = st.form_submit_button("Login", use_container_width=True)
            
            if submit_login and supabase:
                try:
                    auth_res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    if auth_res.user:
                        st.session_state.authenticated = True
                        st.session_state.user_email = auth_res.user.email
                        st.rerun()
                except Exception:
                    st.error("Authentication Denied: Invalid credentials.")
    # Halt execution to block the workspace from rendering
    st.stop()

# --- AUTHORIZED WORKSPACE ---
with st.sidebar:
    st.write(f"Logged in as: `{st.session_state.user_email}`")
    st.markdown("<br><hr style='margin:0.5rem 0;'>", unsafe_allow_html=True)
    
    user_email = st.session_state.user_email.lower()
    is_admin = any(x in user_email for x in ["md", "fm", "admin", "manager"])
    is_frontdesk = "frontdesk" in user_email
    
    st.markdown("### ERP WORKSPACE MODULES")
    
    ops_modules = ["Command Center", "Shop Floor Control"]
    if is_admin:
        ops_modules.insert(1, "Production Layout Builder")
        
    admin_modules = ["Raise Job Order"]
    if is_admin:
        admin_modules += ["Authorization Center", "Approved Orders Archive"]
        
    st.markdown(f"""
    <div class="sidebar-card">
        <div class="sidebar-header-text">Plant Operations</div>
    </div>
    """, unsafe_allow_html=True)
    for mod in ops_modules:
        ico = MODULE_ICONS.get(mod, "")
        if st.button(f"{ico} {mod}", key=f"side_{mod}", use_container_width=True):
            st.session_state.app_mode = mod
            st.rerun()
            
    st.markdown(f"""
    <div class="sidebar-card">
        <div class="sidebar-header-text">Administrative Portal</div>
    </div>
    """, unsafe_allow_html=True)
    for mod in admin_modules:
        ico = MODULE_ICONS.get(mod, "")
        if st.button(f"{ico} {mod}", key=f"side_{mod}", use_container_width=True):
            st.session_state.app_mode = mod
            st.rerun()
            
    st.markdown("<br><br>", unsafe_allow_html=True)
    if st.button("Logout", use_container_width=True, type="primary"):
        st.session_state.authenticated = False
        st.rerun()

# --- 6. CORE APP ROUTING CONTROLLER ---
st.markdown('<div class="main-title">Appointed Time Printing Ltd.</div>', unsafe_allow_html=True)
st.markdown('<div class="main-subtitle">Secured Capacity Planning Engine</div>', unsafe_allow_html=True)

app_mode = st.session_state.app_mode

# --- ROUTE 1: COMMAND CENTER ---
if app_mode == "Command Center":
    df = get_db_jobs()
    if not df.empty:
        df['start_time'] = pd.to_datetime(df['start_time'], utc=True, format='mixed')
        
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Active Orders</div><div class="metric-value">{df["tracking_id"].nunique()}</div></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Contract Value</div><div class="metric-value">{CURRENCY}{df["contract_value"].sum():,.2f}</div></div>', unsafe_allow_html=True)
        with c3:
            books = df[df['ups'] == 1]['tracking_id'].nunique()
            st.markdown(f'<div class="metric-card"><div class="metric-label">Book Runs Queue</div><div class="metric-value">{books}</div></div>', unsafe_allow_html=True)
        with c4:
            skillets = df[df['ups'] > 1]['tracking_id'].nunique()
            st.markdown(f'<div class="metric-card"><div class="metric-label">Packaging Skillets</div><div class="metric-value">{skillets}</div></div>', unsafe_allow_html=True)
            
        st.markdown('<div class="section-header">Strategic Capacity Distribution & Revenue</div>', unsafe_allow_html=True)
        left, right = st.columns([2, 1])
        
        with left:
            load_df = df.groupby('machine').size().reset_index(name='Allocated Components')
            fig_load = px.bar(load_df, x='machine', y='Allocated Components', color='Allocated Components', color_continuous_scale='Blues')
            fig_load.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', showlegend=False, margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig_load, use_container_width=True)
            
        with right:
            rev_df = df.groupby('job_name')['contract_value'].sum().reset_index()
            fig_rev = px.pie(rev_df, values='contract_value', names='job_name', hole=0.6, color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_rev.update_layout(margin=dict(t=10, b=10, l=10, r=10), legend=dict(orientation="h", y=-0.1))
            st.plotly_chart(fig_rev, use_container_width=True)
    else:
        st.info("No active machine runs detected.")

# --- ROUTE 2: RAISE JOB ORDER ---
elif app_mode == "Raise Job Order":
    st.markdown('<div class="section-header">Press Job Order Entry Form</div>', unsafe_allow_html=True)
    
    if "last_raised_order" not in st.session_state:
        st.session_state.last_raised_order = None
        
    with st.form("raise_order_form"):
        c1, c2 = st.columns(2)
        c_name = c1.text_input("Customer Name *")
        c_phone = c2.text_input("Telephone Number *")
        j_desc = st.text_area("Job Description *")
        
        f1, f2, f3, f4 = st.columns(4)
        t_amt = f1.number_input("Total Contract Amount (GHS) *", min_value=0.0, step=100.0)
        d_amt = f2.number_input("Deposit Paid (GHS) *", min_value=0.0, step=100.0)
        b_due = f3.date_input("Balance Settlement Deadline *")
        q_print = f4.number_input("Total Quantity to Print *", min_value=0, step=500)
        
        s1, s2, s3, s4 = st.columns(4)
        t_print = s1.selectbox("Category of Print *", ["", "OFFSET", "DIGITAL PRESS", "PACKAGING"])
        m_source = s2.selectbox("Material Procurement Source", ["", "Customer Material", "Company Material"])
        p_size = s3.text_input("Print Size")
        f_size = s4.text_input("Finished Size")
        
        p1, p2, p3, p4 = st.columns(4)
        pap_type = p1.text_input("Paper Material Description")
        pap_gsm = p2.text_input("GSM Rating")
        pap_size = p3.text_input("Paper Size")
        pap_col = p4.text_input("Color Specs")
        
        x1, x2 = st.columns(2)
        imp_col = x1.text_input("Impressions")
        d_mode = x2.selectbox("Delivery Mode", ["Company Delivery", "Client Pickup"])
        
        b_type = st.multiselect("Binding Selection", ["Perfect Binding", "Spiral Binding", "Saddle Stitching", "Comb Binding"])
        l_type = st.multiselect("Laminating Selection", ["Gloss Laminating", "Matt Laminating", "Soft Touch", "UV-Varnish"])
        
        c_date = st.date_input("Target Date of Collection *")
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.info(f"Job Order Handled By: {st.session_state.user_email} | Filling Date: {datetime.now().strftime('%Y-%m-%d')}")
        
        submit_order = st.form_submit_button("SUBMIT FOR MANAGEMENT APPROVAL", use_container_width=True)
        
        if submit_order:
            missing_fields = []
            if not c_name.strip(): missing_fields.append("Customer Name")
            if not c_phone.strip(): missing_fields.append("Telephone Number")
            if not j_desc.strip(): missing_fields.append("Job Description")
            if t_amt <= 0.0: missing_fields.append("Total Contract Amount (GHS)")
            if d_amt < 0.0: missing_fields.append("Deposit Paid (GHS)")
            if not b_due: missing_fields.append("Balance Settlement Deadline")
            if q_print <= 0: missing_fields.append("Total Quantity to Print")
            if not t_print: missing_fields.append("Category of Print Selection")
            if not c_date: missing_fields.append("Target Date of Collection")
            
            if not missing_fields:
                order_payload = {
                    "customer_name": sanitize_string(c_name),
                    "telephone_number": sanitize_string(c_phone),
                    "job_description": sanitize_string(j_desc),
                    "total_amount": float(t_amt),
                    "deposit_amount": float(d_amt),
                    "balance_due_date": b_due.isoformat(),
                    "date_of_collection": c_date.isoformat(),
                    "qty_to_print": int(q_print),
                    "type_of_print": t_print,
                    "material_source": m_source,
                    "print_size": sanitize_string(p_size),
                    "finished_print_size": sanitize_string(f_size),
                    "paper_type": sanitize_string(pap_type),
                    "gsm": sanitize_string(pap_gsm),
                    "paper_size": sanitize_string(pap_size),
                    "paper_colour": sanitize_string(pap_col),
                    "impressions_colour": imp_col,
                    "delivery_mode": d_mode,
                    "binding_type": ", ".join(b_type) if b_type else "None",
                    "laminating_type": ", ".join(l_type) if l_type else "None",
                    "status": "Pending Approval",
                    "created_by": st.session_state.user_email
                }
                
                try:
                    res = supabase.table('job_orders').insert(order_payload).execute()
                    
                    generated_no = "PENDING"
                    if res.data and len(res.data) > 0:
                        generated_no = res.data[0].get("job_order_no", f"AT-{random.randint(10000,99999)}")
                    else:
                        generated_no = f"AT-{random.randint(10000,99999)}"
                        
                    order_payload["job_order_no"] = generated_no
                    order_payload["order_date"] = datetime.now().strftime('%Y-%m-%d')
                    st.session_state.last_raised_order = order_payload
                    
                    st.toast("Job Entry securely deposited inside management ledger pool successfully.", icon=" ✅ ")
                except Exception as e:
                    st.error(f"Failed to process order sequence entry: {str(e)}")
            else:
                st.error(f"Transaction Blocked. The following required fields are missing or invalid: {', '.join(missing_fields)}")

    # REDESIGNED INDUSTRIAL PRESENTATION LAYER: IN-APP MATRIX GRID
    if st.session_state.last_raised_order is not None:
        ticket = st.session_state.last_raised_order
        
        cat_options = ["OFFSET", "DIGITAL PRESS", "PACKAGING", "DTF", "FLEXI", "SCREEN PRINT", "UV-DTF", "SAV", "EMBROIDERY"]
        cat_html = " &nbsp;&nbsp;&nbsp; ".join([f"&#9745; <strong>{c}</strong>" if c == ticket["type_of_print"].upper() else f"&#9744; <span style='color:#64748b;'>{c}</span>" for c in cat_options])
        
        mat_options = ["CLIENT SOURCED STOCK", "COMPANY SOURCED INVENTORY"]
        mat_html = " &nbsp;&nbsp;&nbsp; ".join([f"&#9745; <strong>{m}</strong>" if m in ticket["material_source"].upper() else f"&#9744; <span style='color:#64748b;'>{m}</span>" for m in mat_options])
        
        st.markdown(f"""
        <div style="border: 1px solid #cbd5e1; padding: 20px; background-color: #ffffff; color: #0f172a; font-family: 'Inter', Helvetica, sans-serif; font-size: 13px; width: 100%; box-sizing: border-box; margin-top: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td colspan="2" style="border-bottom: 2px solid #0f172a; padding-bottom: 8px;">
                        <strong style="font-size: 16px;">Appointed Time Printing Ltd.</strong><br>
                        <span style="font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em;">Commercial Job Order Manifest</span>
                    </td>
                    <td colspan="2" style="border-bottom: 2px solid #0f172a; padding-bottom: 8px; text-align: right; font-size: 18px; color: #0369a1;">
                        <strong>{ticket.get('job_order_no', 'PENDING')}</strong>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 10px 8px; border-bottom: 1px solid #e2e8f0; width: 25%;"><span style="color:#64748b; font-size:11px; display:block;">CUSTOMER NAME</span><strong>{ticket['customer_name']}</strong></td>
                    <td style="padding: 10px 8px; border-bottom: 1px solid #e2e8f0; width: 25%;"><span style="color:#64748b; font-size:11px; display:block;">TELEPHONE NUMBER</span><strong>{ticket['telephone_number']}</strong></td>
                    <td style="padding: 10px 8px; border-bottom: 1px solid #e2e8f0; width: 25%;"><span style="color:#64748b; font-size:11px; display:block;">ORDER DATE</span><strong>{ticket['order_date']}</strong></td>
                    <td style="padding: 10px 8px; border-bottom: 1px solid #e2e8f0; width: 25%;"><span style="color:#64748b; font-size:11px; display:block;">TARGET COLLECTION</span><strong>{ticket['date_of_collection']}</strong></td>
                </tr>
                <tr>
                    <td style="padding: 10px 8px; border-bottom: 1px solid #e2e8f0;"><span style="color:#64748b; font-size:11px; display:block;">CONTRACT AMOUNT</span><strong>{CURRENCY} {float(ticket['total_amount']):,.2f}</strong></td>
                    <td style="padding: 10px 8px; border-bottom: 1px solid #e2e8f0;"><span style="color:#64748b; font-size:11px; display:block;">DEPOSIT PAID</span><strong>{CURRENCY} {float(ticket['deposit_amount']):,.2f}</strong></td>
                    <td colspan="2" style="padding: 10px 8px; border-bottom: 1px solid #e2e8f0;"><span style="color:#64748b; font-size:11px; display:block;">OUTSTANDING BALANCE</span><strong style="color: #b91c1c;">{CURRENCY} {float(ticket['total_amount'] - ticket['deposit_amount']):,.2f}</strong></td>
                </tr>
                <tr>
                    <td colspan="4" style="padding: 12px 8px; border-bottom: 1px solid #e2e8f0; background-color:#f8fafc; line-height: 1.8;">
                        <span style="color:#64748b; font-size:11px; display:inline-block; width:120px;">TYPE OF PRINT:</span> {cat_html}
                    </td>
                </tr>
                <tr>
                    <td colspan="4" style="padding: 12px 8px; border-bottom: 1px solid #e2e8f0; background-color:#f8fafc; line-height: 1.8;">
                        <span style="color:#64748b; font-size:11px; display:inline-block; width:120px;">MATERIAL SOURCE:</span> {mat_html}
                    </td>
                </tr>
                <tr>
                    <td colspan="4" style="padding: 16px 8px; border-bottom: 2px solid #0f172a;">
                        <span style="color:#64748b; font-size:11px; display:block; margin-bottom:4px;">JOB DESCRIPTION</span>
                        <div style="font-size: 14px; line-height: 1.5; white-space: pre-wrap;">{ticket['job_description']}</div>
                    </td>
                </tr>
            </table>
            <table style="width: 100%; border-collapse: collapse; margin-top: 12px;">
                <tr style="background-color: #f1f5f9;">
                    <th style="padding: 8px; border: 1px solid #cbd5e1; text-align: left; font-size: 11px; color:#475569;">PAPER / SUBSTRATE</th>
                    <th style="padding: 8px; border: 1px solid #cbd5e1; text-align: left; font-size: 11px; color:#475569;">GSM</th>
                    <th style="padding: 8px; border: 1px solid #cbd5e1; text-align: left; font-size: 11px; color:#475569;">SIZE</th>
                    <th style="padding: 8px; border: 1px solid #cbd5e1; text-align: left; font-size: 11px; color:#475569;">PAPER COLOUR</th>
                </tr>
                <tr>
                    <td style="padding: 8px; border: 1px solid #cbd5e1;">{ticket['paper_type'] if ticket['paper_type'] else '-'}</td>
                    <td style="padding: 8px; border: 1px solid #cbd5e1;">{ticket['gsm'] if ticket['gsm'] else '-'}</td>
                    <td style="padding: 8px; border: 1px solid #cbd5e1;">{ticket['paper_size'] if ticket['paper_size'] else '-'}</td>
                    <td style="padding: 8px; border: 1px solid #cbd5e1;">{ticket['paper_colour'] if ticket['paper_colour'] else '-'}</td>
                </tr>
            </table>
        </div>
        """, unsafe_allow_html=True)
        
        # UI Action Download Button implementation Hook
        pdf_buffer = generate_pdf_manifest(ticket)
        st.markdown("<br>", unsafe_allow_html=True)
        st.download_button(
            label="EXPORT PDF",
            data=pdf_buffer,
            file_name=f"Manifest_{ticket.get('job_order_no', 'PENDING')}.pdf",
            mime="application/pdf",
            use_container_width=True,
            type="primary"
        )

# --- ROUTE 3: AUTHORIZATION CENTER ---
elif app_mode == "Authorization Center" and is_admin:
    st.markdown('<div class="section-header">Executive Authorization Control Panel</div>', unsafe_allow_html=True)
    orders_df = get_db_job_orders("Pending Approval")
    
    if orders_df.empty:
        st.success("All clear! No pending jobs require executive sign-off.")
    else:
        PAGE_SIZE_AUTH = 15
        total_orders = len(orders_df)
        total_pages_auth = math.ceil(total_orders / PAGE_SIZE_AUTH)
        if "auth_page" not in st.session_state:
            st.session_state.auth_page = 1
            
        col_p1, col_p2, col_p3 = st.columns([1, 4, 1])
        with col_p1:
            if st.button(" Previous", key="auth_prev_btn", disabled=(st.session_state.auth_page <= 1), use_container_width=True):
                st.session_state.auth_page -= 1
                st.rerun()
        with col_p2:
            st.markdown(f"<p style='text-align: center; color: #64748b; font-weight: 600;'>Showing records {((st.session_state.auth_page - 1) * PAGE_SIZE_AUTH) + 1} - {min(st.session_state.auth_page * PAGE_SIZE_AUTH, total_orders)} of {total_orders} (Page {st.session_state.auth_page} of {total_pages_auth})</p>", unsafe_allow_html=True)
        with col_p3:
            if st.button("Next ", key="auth_next_btn", disabled=(st.session_state.auth_page >= total_pages_auth), use_container_width=True):
                st.session_state.auth_page += 1
                st.rerun()
                
        start_idx = (st.session_state.auth_page - 1) * PAGE_SIZE_AUTH
        end_idx = start_idx + PAGE_SIZE_AUTH
        sliced_orders = orders_df.iloc[start_idx:end_idx]
        
        for idx, row in sliced_orders.iterrows():
            with st.expander(f"ORDER REQUEST: {row['customer_name']} | Qty: {row['qty_to_print']:,} [{row['type_of_print']}]"):
                st.markdown(f"""
                <div class="ticket-container">
                    <div class="ticket-field"><span class="ticket-label">Description:</span> {row['job_description']}</div>
                    <div class="ticket-field"><span class="ticket-label">Financial Target:</span> Total {CURRENCY}{row['total_amount']:,.2f} | Deposit Paid {CURRENCY}{row['deposit_amount']:,.2f}</div>
                    <div class="ticket-field"><span class="ticket-label">Stock Parameters:</span> Type: {row['paper_type']} | GSM: {row['gsm']} | Colors: {row['impressions_colour']}</div>
                    <div class="ticket-field"><span class="ticket-label">Target Collection:</span> {row['date_of_collection']} via {row['delivery_mode']}</div>
                </div>
                """, unsafe_allow_html=True)
                
                btn_approve, btn_reject = st.columns(2)
                if btn_approve.button("AUTHORIZE SIGN OFF", key=f"app_{row['id']}", use_container_width=True):
                    try:
                        supabase.table('job_orders').update({"status": "Approved", "approved_by": st.session_state.user_email}).eq('id', row['id']).execute()
                        st.success("Authorization secure token stamped.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed authorization process: {str(e)}")
                if btn_reject.button("REJECT / DISCARD", key=f"rej_{row['id']}", use_container_width=True, type="secondary"):
                    try:
                        supabase.table('job_orders').delete().eq('id', row['id']).execute()
                        st.warning("Order discarded.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed deletion request: {str(e)}")

# --- ROUTE 4: APPROVED ORDERS ARCHIVE ---
elif app_mode == "Approved Orders Archive" and is_admin:
    st.markdown('<div class="section-header">Enterprise Ledger & Approved Orders Vault</div>', unsafe_allow_html=True)
    approved_orders = get_db_job_orders("Approved")
    
    if approved_orders.empty:
        st.info("No approved job contracts are currently sitting in archives.")
    else:
        view_matrix = pd.DataFrame({
            "Order No": approved_orders["job_order_no"],
            "Customer Name": approved_orders["customer_name"],
            "Print Qty": approved_orders["qty_to_print"],
            "Category": approved_orders["type_of_print"],
            "total_amount": approved_orders["total_amount"],
            "deposit_amount": approved_orders["deposit_amount"],
            "Authorized Manager": approved_orders["approved_by"]
        })
        st.dataframe(
            view_matrix,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Order No": st.column_config.TextColumn("Order No", help="Unique sequential system layout job number", width="medium"),
                "Customer Name": st.column_config.TextColumn("Customer Name", width="large"),
                "Print Qty": st.column_config.NumberColumn("Print Qty", format="%d", width="small"),
                "Category": st.column_config.SelectboxColumn("Category", options=["OFFSET", "DIGITAL PRESS", "PACKAGING", "DTF", "Flexi", "Screen Print", "UV-DTF", "SAV", "Embroidery"], width="medium"),
                "total_amount": st.column_config.NumberColumn(f"Total Amount ({CURRENCY})", format=f"{CURRENCY} %,.2f", width="medium"),
                "deposit_amount": st.column_config.NumberColumn(f"Deposit Paid ({CURRENCY})", format=f"{CURRENCY} %,.2f", width="medium"),
                "Authorized Manager": st.column_config.TextColumn("Authorized Manager", width="medium")
            }
        )
        st.markdown("<hr style='margin: 2rem 0;'>", unsafe_allow_html=True)
        st.markdown("### Manage Archived Orders")
        
        selected_order_no = st.selectbox("Select Order Number to Modify, Export, or Delete:", [""] + view_matrix['Order No'].tolist())
        if selected_order_no:
            target_row = approved_orders[approved_orders['job_order_no'] == selected_order_no].iloc[0]
            with st.expander(f"Order Operations: {selected_order_no}"):
                
                # UI Action Download Button implementation Hook inside Data Vault
                pdf_buffer_archived = generate_pdf_manifest(target_row.to_dict())
                st.download_button(
                    label=f"EXPORT OFFICIAL PDF MANIFEST ({selected_order_no})",
                    data=pdf_buffer_archived,
                    file_name=f"Manifest_{selected_order_no}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    type="primary"
                )
                st.markdown("<br>", unsafe_allow_html=True)

                with st.form(key=f"edit_form_{target_row['id']}"):
                    e_qty = st.number_input("Print Quantity", value=int(target_row['qty_to_print']), step=100)
                    e_amt = st.number_input("Total Amount", value=float(target_row['total_amount']), step=50.0)
                    
                    c_upd, c_del = st.columns(2)
                    if c_upd.form_submit_button("Save Changes", use_container_width=True):
                        try:
                            supabase.table('job_orders').update({"qty_to_print": int(e_qty), "total_amount": float(e_amt)}).eq('id', target_row['id']).execute()
                            st.success(f"Order {selected_order_no} updated.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Update failed: {str(e)}")
                            
                    if c_del.form_submit_button("Delete Order", type="secondary", use_container_width=True):
                        try:
                            supabase.table('job_orders').delete().eq('id', target_row['id']).execute()
                            st.warning(f"Order {selected_order_no} permanently deleted.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Deletion failed: {str(e)}")

# --- ROUTE 5: PRODUCTION LAYOUT BUILDER ---
elif app_mode == "Production Layout Builder" and is_admin:
    st.markdown('<div class="section-header">Algorithmic Capacity Loading Engine Layouts</div>', unsafe_allow_html=True)
    approved_df = get_db_job_orders("Approved")
    
    if approved_df.empty:
        st.info("No active verified customer orders found waiting for capacity scheduling layout.")
    else:
        order_options = {f"{row['job_order_no']} | {row['customer_name']} (Qty: {row['qty_to_print']})": row['job_order_no'] for _, row in approved_df.iterrows()}
        chosen_label = st.selectbox("Select Target Active Client Ledger Item to Schedule:", list(order_options.keys()))
        
        if chosen_label:
            target_no = order_options[chosen_label]
            matched_order = approved_df[approved_df['job_order_no'] == target_no].iloc[0]
            
            col_inputs, col_sum = st.columns([7, 5])
            with col_inputs:
                st.markdown('<div class="planner-card">', unsafe_allow_html=True)
                job_name_input = st.text_input("Production Flow Sequence Identity Name *", value=f"Flow for {matched_order['customer_name']}")
                sales_rep = st.text_input("Account Executive Handler Signature", value=matched_order['created_by'])
                start_date = st.date_input("Production Flow Horizon Start Point Base", value=datetime.now().date())
                prod_cat = st.selectbox("Production Layout Category", ["Skillet / Box Packing", "Book / Magazine Brochure", "Flat Sheet Flyer"])
                
                c1, c2, c3 = st.columns(3)
                order_qty = c1.number_input("Target Order Units", value=int(matched_order['qty_to_print']), min_value=1)
                ups = c2.number_input("Number of Ups", value=1, min_value=1, step=1)
                total_val = c3.number_input("Value (GH₵)", value=float(matched_order['total_amount']), min_value=0.0)
                
                st.markdown("#### Sequential Floor Run Mappings")
                if prod_cat == "Book / Brochure":
                    type_id = 1
                    text_pages = st.number_input("Total Inner Text Pages", value=16, min_value=4, step=4)
                    text_ups = st.number_input("Text Page Layout Signatures (Ups)", value=8, min_value=1)
                    text_imps = (order_qty * text_pages) / text_ups
                    st.caption(f"Calculated Text Run Load: **{int(text_imps):,} impressions** needed.")
                    
                    r1, r2, r3 = st.columns(3)
                    comp = [
                        {"name": "Cover", "impressions": max(1.0, order_qty/ups), "machines": r1.multiselect("Cover Configuration", list(MACHINE_DATA.keys()))},
                        {"name": "Text", "impressions": float(text_imps), "machines": r2.multiselect("Text Interior Configuration", list(MACHINE_DATA.keys()))}
                    ]
                    fin_route = r3.multiselect("Finishing Layout Line", list(MACHINE_DATA.keys()))
                else:
                    type_id = ups
                    r1, r2 = st.columns(2)
                    comp = [{"name": "Body", "impressions": max(1.0, order_qty/ups), "machines": r1.multiselect("Primary Print Configuration", list(MACHINE_DATA.keys()))}]
                    fin_route = r2.multiselect("Finishing Component Line Sequence", list(MACHINE_DATA.keys()))
                st.markdown('</div>', unsafe_allow_html=True)
                
            with col_sum:
                st.markdown(f"""
                <div class="ticket-container">
                    <div class="ticket-title">Production Work Ticket Blueprint</div>
                    <div class="ticket-field"><span class="ticket-label">Job Num:</span> {matched_order['job_order_no']}</div>
                    <div class="ticket-field"><span class="ticket-label">Format:</span> {matched_order['type_of_print']} | {matched_order['material_source']}</div>
                    <div class="ticket-field"><span class="ticket-label">Description:</span> {matched_order['job_description'] if matched_order['job_description'] else 'No special description.'}</div>
                    <div class="ticket-field"><span class="ticket-label">Print Size:</span> {matched_order['print_size']} (Trimmed: {matched_order['finished_print_size']})</div>
                    <div class="ticket-field"><span class="ticket-label">Stock Required:</span> {matched_order['paper_type']} | {matched_order['gsm']} | Size: {matched_order['paper_size']}</div>
                    <div class="ticket-field"><span class="ticket-label">Colors:</span> {matched_order['paper_colour']} — {matched_order['impressions_colour']}</div>
                    <div class="ticket-field"><span class="ticket-label">Finishing Bind:</span> {matched_order['binding_type'] if matched_order['binding_type'] else 'None'}</div>
                    <div class="ticket-field"><span class="ticket-label">Lamination:</span> {matched_order['laminating_type'] if matched_order['laminating_type'] else 'None'}</div>
                    <div class="ticket-field"><span class="ticket-label">Delivery Target:</span> {matched_order['delivery_mode']} by {matched_order['date_of_collection']}</div>
                </div>
                """, unsafe_allow_html=True)
                
                st.markdown('<div class="summary-box">', unsafe_allow_html=True)
                st.markdown("#### Verification Ledger Context Summary")
                st.markdown(f"**Sequence Key:** {job_name_input if job_name_input else 'Unnamed allocation sequence'}")
                st.markdown(f"**Aggregate Volume Count:** {int(order_qty):,} target final pieces")
                st.markdown(f"**Total Registered Stages:** {sum(len(c['machines']) for c in comp) + len(fin_route)} distinct structural floor routing blocks")
                st.markdown(f"**Gross Fin Val Allocated:** {CURRENCY}{float(total_val):,.2f}")
                
                if st.button("PLAN", use_container_width=True, type="primary"):
                    if not job_name_input:
                        st.error("Operation Denied: The sequence requires an identifying title layout name.")
                    elif sum(len(c['machines']) for c in comp) == 0:
                        st.error("Operation Denied: You must provide at least one machine component run.")
                    else:
                        payload = {
                            "name": job_name_input, "sales_rep": sales_rep, "start_date": start_date,
                            "total_qty": order_qty, "type_id": type_id, "total_val": total_val,
                            "components": comp, "finishing_machines": fin_route
                        }
                        add_multi_part_job(payload)
                        st.success("Sequence injected. Real-time factory floor boards updated safely.")
                        st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

# --- ROUTE 6: SHOP FLOOR CONTROL ---
elif app_mode == "Shop Floor Control":
    st.markdown('<div class="section-header">Live Floor Machine Sequencing Streams</div>', unsafe_allow_html=True)
    jobs_df = get_db_jobs()
    
    if jobs_df.empty:
        st.info("All floor boards are currently idle. No tasks discovered in tracking rows.")
    else:
        jobs_df['start_time'] = pd.to_datetime(jobs_df['start_time'], format='mixed', errors='coerce')
        jobs_df['finish_time'] = pd.to_datetime(jobs_df['finish_time'], format='mixed', errors='coerce')
        jobs_df = jobs_df.dropna(subset=['start_time', 'finish_time'])
        
        m_filter = st.multiselect("Filter View Board by Stationary Assets:", sorted(list(MACHINE_DATA.keys())))
        if m_filter:
            jobs_df = jobs_df[jobs_df['machine'].isin(m_filter)]
            
        unique_tracking_ids = jobs_df['tracking_id'].unique() if not jobs_df.empty else []
        
        if len(unique_tracking_ids) == 0:
            st.info("No matching schedule items discovered for chosen stationary filters.")
        else:
            PAGE_SIZE_SF = 10
            total_jobs = len(unique_tracking_ids)
            total_pages_sf = math.ceil(total_jobs / PAGE_SIZE_SF)
            
            if "sf_page" not in st.session_state:
                st.session_state.sf_page = 1
                
            col_p1, col_p2, col_p3 = st.columns([1, 4, 1])
            with col_p1:
                if st.button(" Previous", key="sf_prev_btn", disabled=(st.session_state.sf_page <= 1), use_container_width=True):
                    st.session_state.sf_page -= 1
                    st.rerun()
            with col_p2:
                st.markdown(f"<p style='text-align: center; color: #64748b; font-weight: 600;'>Showing records {((st.session_state.sf_page - 1) * PAGE_SIZE_SF) + 1} - {min(st.session_state.sf_page * PAGE_SIZE_SF, total_jobs)} of {total_jobs} (Page {st.session_state.sf_page} of {total_pages_sf})</p>", unsafe_allow_html=True)
            with col_p3:
                if st.button("Next ", key="sf_next_btn", disabled=(st.session_state.sf_page >= total_pages_sf), use_container_width=True):
                    st.session_state.sf_page += 1
                    st.rerun()
                    
            start_idx_sf = (st.session_state.sf_page - 1) * PAGE_SIZE_SF
            end_idx_sf = start_idx_sf + PAGE_SIZE_SF
            sliced_tracking_ids = unique_tracking_ids[start_idx_sf:end_idx_sf]
            
            for tid in sliced_tracking_ids:
                flow_rows = jobs_df[jobs_df['tracking_id'] == tid].sort_values(by='start_time')
                meta = flow_rows.iloc[0]
                
                st.markdown(f"""
                <div class="job-rollup-card">
                    <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:2px dashed #f1f5f9; padding-bottom:0.5rem; margin-bottom:0.5rem;">
                        <div>
                            <span style="font-size:1.1rem; font-weight:700; color:#0f172a;">{meta['job_name']}</span>
                            <span style="margin-left:0.75rem; padding:0.2rem 0.6rem; background:#f1f5f9; color:#475569; border-radius:6px; font-size:0.75rem; font-weight:600;">{tid}</span>
                        </div>
                        <div style="font-size:0.85rem; color:#64748b;">
                            Handler Signature: <strong>{meta['sales_rep']}</strong> | Output Yield Target: <strong>{int(meta['quantity']):,} units</strong>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                
                for _, run_row in flow_rows.iterrows():
                    s_str = run_row['start_time'].strftime('%b %d, %H:%M') if pd.notnull(run_row['start_time']) else "N/A"
                    f_str = run_row['finish_time'].strftime('%b %d, %H:%M') if pd.notnull(run_row['finish_time']) else "N/A"
                    
                    st.markdown(f"""
                    <div class="stream-row-item">
                        <div>
                            <strong>Station Alloc:</strong> {run_row['machine']} <br>
                            <span style="color:#64748b;">Target Volume Run: {int(run_row['impressions']):,} impressions</span>
                        </div>
                        <div style="text-align:right;">
                            <strong>Timeline Boundary:</strong> {s_str} to {f_str} <br>
                            <span style="color:#059669; font-weight:600;">Stage Value allocation: {CURRENCY}{run_row['contract_value']:,.2f}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
                
                if is_admin:
                    if st.button("Delete Scheduled Job Flow", key=f"del_sched_{tid}", use_container_width=True, type="secondary"):
                        try:
                            supabase.table('jobs').delete().eq('tracking_id', tid).execute()
                            st.success(f"Production schedule {tid} successfully removed.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to clear job sequence: {str(e)}")

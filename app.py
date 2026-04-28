import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import math
import random
from supabase import create_client, Client
import plotly.express as px

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Appointed Time | Elite ERP", layout="wide", page_icon="🏢")

# --- 2. GLOBAL SETUP & MACHINE REGISTRY ---
CURRENCY = "GH₵"
SETUP_HOURS = 1.5  
DAILY_CAPACITY_HOURS = 8.0 

MACHINE_DATA = {
    'SM102-CX FOUR COLOUR': {'rate': 8000},
    'SM102-P FIVE COLOUR': {'rate': 7500},
    'SM 52': {'rate': 7000},
    'GTO 52 SEMI-AUTO-2 COLOUR': {'rate': 4500},
    'GTO 52 MANUAL-2 COLOUR': {'rate': 4000},
    'FOLDING UNIT (CONTINUOUS)': {'rate': 8000},
    'MBO-B30E (SINGLE FOLD)': {'rate': 16000},
    'PERFECT BINDING': {'rate': 500},
    'SADDLE STITCHER': {'rate': 1000},
    'POLAR CUTTER (BOOKS)': {'rate': 2000},
    'POLAR CUTTER (SHEETS)': {'rate': 50000},
    '3 WAY TRIMMER': {'rate': 5000},
    'LAMINATION UNIT': {'rate': 2500},
    'DIE CUTTER': {'rate': 3000},  
    'FOLDER GLUER': {'rate': 12000}, 
    'CANON DIGITAL C10000': {'rate': 6000},
    'CANON DIGITAL C800': {'rate': 4000},
}

# --- 3. ENHANCED EXECUTIVE UI STYLING ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    
    /* Main Background */
    .stApp { background-color: #f1f5f9; }
    
    /* Professional KPI Cards */
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        border-bottom: 4px solid #2563eb;
        box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
        text-align: center;
        margin-bottom: 1rem;
    }
    .metric-label { font-size: 0.8rem; color: #64748b; text-transform: uppercase; font-weight: 700; }
    .metric-value { font-size: 1.8rem; font-weight: 800; color: #0f172a; margin-top: 0.5rem; }

    /* Section Headers */
    .section-header {
        font-size: 1.25rem;
        font-weight: 700;
        color: #1e293b;
        margin: 2rem 0 1rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid #e2e8f0;
    }

    /* Form Styling */
    .planner-card {
        background: white;
        padding: 2rem;
        border-radius: 16px;
        box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.05);
    }
    
    .summary-box {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        color: white;
        padding: 2rem;
        border-radius: 16px;
    }
    </style>
    """, unsafe_allow_html=True)

@st.cache_resource
def init_supabase():
    try: return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except: return None

supabase: Client = init_supabase()

# --- 4. CORE ENGINES ---

def get_db_jobs():
    if not supabase: return pd.DataFrame()
    try:
        res = supabase.table('jobs').select("*").execute()
        return pd.DataFrame(res.data)
    except: return pd.DataFrame()

def calculate_production_time(start_dt, impressions, machine_rate):
    """Calculates completion date considering 8 AM - 5 PM work hours."""
    current_time = start_dt
    remaining_imps = impressions
    current_time += timedelta(hours=SETUP_HOURS)
    
    while remaining_imps > 0:
        if current_time.hour < 8: current_time = current_time.replace(hour=8, minute=0)
        if current_time.hour >= 17: current_time = (current_time + timedelta(days=1)).replace(hour=8, minute=0)

        workday_end = current_time.replace(hour=17, minute=0)
        available_hours = (workday_end - current_time).total_seconds() / 3600
        
        possible_today = available_hours * machine_rate
        if remaining_imps <= possible_today:
            current_time += timedelta(hours=remaining_imps / machine_rate)
            remaining_imps = 0
        else:
            remaining_imps -= possible_today
            current_time = (current_time + timedelta(days=1)).replace(hour=8, minute=0)
    return current_time

def add_multi_part_job(job_data):
    """Logic to fix Finish-to-Start bottleneck with Staggered Overlaps."""
    tid = f"JOB-{random.randint(1000, 9999)}"
    total_stages = sum(len(c['machines']) for c in job_data['components']) + len(job_data['finishing_machines'])
    val_per_stage = job_data['total_val'] / total_stages if total_stages > 0 else 0

    anchor_start = datetime.combine(job_data['start_date'], datetime.now().time()).replace(tzinfo=timezone.utc)
    if anchor_start.hour < 8: anchor_start = anchor_start.replace(hour=8, minute=0)
    if anchor_start.hour >= 17: anchor_start = (anchor_start + timedelta(days=1)).replace(hour=8, minute=0)

    # 1. PRINTING STAGE
    for comp in job_data['components']:
        current_stage_start = anchor_start
        for machine in comp['machines']:
            finish = calculate_production_time(current_stage_start, comp['impressions'], MACHINE_DATA[machine]['rate'])
            supabase.table('jobs').insert({
                "job_name": job_data['name'], "tracking_id": tid, "machine": machine,
                "sales_rep": job_data['sales_rep'], "quantity": int(job_data['total_qty']),
                "ups": int(job_data['type_id']), "impressions": int(comp['impressions']), 
                "start_time": current_stage_start.isoformat(), "finish_time": finish.isoformat(), 
                "contract_value": float(val_per_stage)
            }).execute()
            current_stage_start = finish 

    # 2. FINISHING STAGE (Industry Overlap Logic)
    die_cut_start_anchor = None

    for machine_name in job_data['finishing_machines']:
        if "DIE CUTTER" in machine_name.upper():
            f_start = anchor_start + timedelta(days=1)
            die_cut_start_anchor = f_start 
        elif "FOLDER GLUER" in machine_name.upper() and die_cut_start_anchor:
            f_start = die_cut_start_anchor + timedelta(hours=2)
        else:
            f_start = anchor_start + timedelta(hours=4)

        if f_start.hour >= 17: f_start = (f_start + timedelta(days=1)).replace(hour=8, minute=0)
        elif f_start.hour < 8: f_start = f_start.replace(hour=8, minute=0)

        f_finish = calculate_production_time(f_start, job_data['total_qty'], MACHINE_DATA[machine_name]['rate'])
        
        supabase.table('jobs').insert({
            "job_name": job_data['name'], "tracking_id": tid, "machine": machine_name,
            "sales_rep": job_data['sales_rep'], "quantity": int(job_data['total_qty']),
            "ups": int(job_data['type_id']), "impressions": int(job_data['total_qty']),
            "start_time": f_start.isoformat(), "finish_time": f_finish.isoformat(),
            "contract_value": float(val_per_stage)
        }).execute()

# --- 5. UI TABS ---
tab_dash, tab_plan, tab_control = st.tabs(["🏛️ COMMAND CENTER", "⚙️ PRODUCTION PLANNER", "📅 SHOP FLOOR CONTROL"])

with tab_dash:
    df = get_db_jobs()
    if not df.empty:
        df['start_time'] = pd.to_datetime(df['start_time'], utc=True)
        
        # KPI Row
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Active Jobs</div><div class="metric-value">{df["job_name"].nunique()}</div></div>', unsafe_allow_html=True)
        with col2:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Pipeline Value</div><div class="metric-value">{CURRENCY}{df["contract_value"].sum():,.0f}</div></div>', unsafe_allow_html=True)
        with col3:
            books = df[df['ups'] == 1]['job_name'].nunique()
            st.markdown(f'<div class="metric-card"><div class="metric-label">Book Projects</div><div class="metric-value">{books}</div></div>', unsafe_allow_html=True)
        with col4:
            skillets = df[df['ups'] == 2]['job_name'].nunique()
            st.markdown(f'<div class="metric-card"><div class="metric-label">Skillet Jobs</div><div class="metric-value">{skillets}</div></div>', unsafe_allow_html=True)

        # Strategic Insights Row
        st.markdown('<p class="section-header">📊 Strategic Insights</p>', unsafe_allow_html=True)
        left, right = st.columns([2, 1])
        with left:
            load_df = df.groupby('machine').size().reset_index(name='Queue')
            fig = px.bar(load_df, x='machine', y='Queue', color='Queue', 
                         color_continuous_scale='Blues', title="Machine Load Analysis (Job Queue Count)")
            st.plotly_chart(fig, use_container_width=True)
        with right:
            rev_df = df.groupby('job_name')['contract_value'].sum().reset_index()
            fig_pie = px.pie(rev_df, values='contract_value', names='job_name', hole=0.5, title="Revenue Concentration")
            st.plotly_chart(fig_pie, use_container_width=True)

with tab_plan:
    st.markdown('<p class="section-header">Project Architecture</p>', unsafe_allow_html=True)
    col_in, col_sum = st.columns([2, 1])
    
    with col_in:
        st.markdown('<div class="planner-card">', unsafe_allow_html=True)
        job_name = st.text_input("Project Description (e.g. Nutrifoods 2M Run)")
        sales_rep = st.selectbox("Sales Lead", ["Mabel Ampofo", "Daphne Sarpong", "Elizabeth Akoto", "Charles Adoo", "Christian Mante", "Bertha Tackie", "Reginald Aidam"])
        prod_cat = st.selectbox("Category", ["📦 Skillet / Box", "📚 Book / Brochure", "📄 Flyer"])
        
        c1, c2, c3 = st.columns(3)
        order_qty = c1.number_input("Units", value=10000, step=1000)
        total_val = c2.number_input("Total Value", value=5000.0)
        ups = c3.number_input("Ups per Sheet", value=10)

        if "Book" in prod_cat:
            type_id = 1
            pgs = st.number_input("Pages", value=64)
            sig = st.selectbox("Signature", [8, 16, 32], index=1)
            text_imps = math.ceil(pgs/sig) * order_qty
            r1, r2, r3 = st.columns(3)
            comp = [{"name": "Cover", "impressions": order_qty/ups, "machines": r1.multiselect("Cover Press", list(MACHINE_DATA.keys()))},
                    {"name": "Text", "impressions": text_imps, "machines": r2.multiselect("Text Press", list(MACHINE_DATA.keys()))}]
            fin_route = r3.multiselect("Finishing", list(MACHINE_DATA.keys()))
        else:
            type_id = 2
            r1, r2 = st.columns(2)
            comp = [{"name": "Body", "impressions": order_qty/ups, "machines": r1.multiselect("Printing Press", list(MACHINE_DATA.keys()))}]
            fin_route = r2.multiselect("Finishing Line (Order matters)", list(MACHINE_DATA.keys()))
        st.markdown('</div>', unsafe_allow_html=True)

    with col_sum:
        st.markdown('<div class="summary-box">', unsafe_allow_html=True)
        st.markdown("### 🚀 Deployment")
        start_date = st.date_input("Start Date")
        if st.button("PUSH TO SHOP FLOOR", use_container_width=True):
            if job_name and fin_route:
                add_multi_part_job({"name": job_name, "sales_rep": sales_rep, "total_qty": order_qty, "total_val": total_val, "start_date": start_date, "type_id": type_id, "components": comp, "finishing_machines": fin_route})
                st.success("Dispatched!")
                st.rerun()
            else: st.error("Missing Job Name or Route")
        st.markdown('</div>', unsafe_allow_html=True)

with tab_control:
    df = get_db_jobs()
    if not df.empty:
        df['start_time'] = pd.to_datetime(df['start_time'], utc=True)
        df['finish_time'] = pd.to_datetime(df['finish_time'], utc=True)
        
        st.markdown('<p class="section-header">⌛ Live Production Timeline</p>', unsafe_allow_html=True)
        fig = px.timeline(df, x_start="start_time", x_end="finish_time", y="machine", color="job_name", 
                          template="plotly_white", color_discrete_sequence=px.colors.qualitative.Bold)
        fig.update_layout(height=400, margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)
        
        st.markdown('<p class="section-header">📋 Detailed Production Queue</p>', unsafe_allow_html=True)
        for name, group in df.groupby('job_name'):
            with st.expander(f"📦 {name.upper()} | Status: IN PRODUCTION"):
                display_df = group[['machine', 'impressions', 'start_time', 'finish_time']].copy()
                display_df['start_time'] = display_df['start_time'].dt.strftime('%d %b, %H:%M')
                display_df['finish_time'] = display_df['finish_time'].dt.strftime('%d %b, %H:%M')
                st.table(display_df)
                
                if st.button(f"🗑️ Scrap {name}", key=name):
                    supabase.table('jobs').delete().eq('job_name', name).execute()
                    st.rerun()

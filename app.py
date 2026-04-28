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

# Fixed: Included missing rates for DIE CUTTER and FOLDER GLUER
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
    'DIE CUTTER': {'rate': 3000},  # Fixed missing rate
    'FOLDER GLUER': {'rate': 12000}, # Fixed missing rate
    'CANON DIGITAL C10000': {'rate': 6000},
    'CANON DIGITAL C800': {'rate': 4000},
}

# --- 3. UI STYLING ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stApp { background-color: #f8fafc; }
    .metric-card { background: white; padding: 20px; border-radius: 12px; border: 1px solid #e2e8f0; text-align: center; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }
    .metric-value { font-size: 24px; font-weight: 700; color: #1e293b; }
    .metric-label { font-size: 12px; color: #64748b; text-transform: uppercase; }
    .planner-card { background: white; padding: 25px; border-radius: 20px; border: 1px solid #e2e8f0; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05); }
    .summary-box { background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: white; padding: 25px; border-radius: 20px; position: sticky; top: 20px; }
    .section-header { font-size: 20px; font-weight: 700; color: #0f172a; margin-bottom: 15px; border-left: 4px solid #2563eb; padding-left: 10px; }
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
    """Refactored logic to fix Finish-to-Start bottleneck with Staggered Overlaps."""
    tid = f"JOB-{random.randint(1000, 9999)}"
    total_stages = sum(len(c['machines']) for c in job_data['components']) + len(job_data['finishing_machines'])
    val_per_stage = job_data['total_val'] / total_stages if total_stages > 0 else 0

    # Determine Global Start (Anchor)
    anchor_start = datetime.combine(job_data['start_date'], datetime.now().time()).replace(tzinfo=timezone.utc)
    if anchor_start.hour < 8: anchor_start = anchor_start.replace(hour=8, minute=0)
    if anchor_start.hour >= 17: anchor_start = (anchor_start + timedelta(days=1)).replace(hour=8, minute=0)

    # 1. PRINTING STAGE (Sequential within parts)
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
            current_stage_start = finish # Next machine in print sequence starts after previous

    # 2. FINISHING STAGE (Industry Overlap Logic)
    # Note: We do NOT wait for 'current_stage_start' from the printing stage.
    die_cut_start_anchor = None

    for machine_name in job_data['finishing_machines']:
        if "DIE CUTTER" in machine_name.upper():
            # RULE: Die cutting starts 24 hours after the START of printing
            f_start = anchor_start + timedelta(days=1)
            die_cut_start_anchor = f_start 
        elif "FOLDER GLUER" in machine_name.upper() and die_cut_start_anchor:
            # RULE: Folder Gluer starts 2 hours after DIE CUTTING began
            f_start = die_cut_start_anchor + timedelta(hours=2)
        else:
            # General finishing starts 4 hours after printing starts if not specified
            f_start = anchor_start + timedelta(hours=4)

        # Normalize start to work hours
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
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(f'<div class="metric-card"><div class="metric-label">Active Jobs</div><div class="metric-value">{df["job_name"].nunique()}</div></div>', unsafe_allow_html=True)
        c2.markdown(f'<div class="metric-card"><div class="metric-label">Revenue</div><div class="metric-value">{CURRENCY}{df["contract_value"].sum():,.0f}</div></div>', unsafe_allow_html=True)
        st.plotly_chart(px.bar(df.groupby('job_name')['contract_value'].sum().reset_index(), x='contract_value', y='job_name', orientation='h', title="Revenue by Project"), use_container_width=True)

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
        st.plotly_chart(px.timeline(df, x_start="start_time", x_end="finish_time", y="machine", color="job_name", title="Live Production Timeline (Day Shift Only)"), use_container_width=True)
        
        for name, group in df.groupby('job_name'):
            with st.expander(f"📋 {name}"):
                st.table(group[['machine', 'start_time', 'finish_time']])
                if st.button(f"Delete {name}", key=name):
                    supabase.table('jobs').delete().eq('job_name', name).execute()
                    st.rerun()

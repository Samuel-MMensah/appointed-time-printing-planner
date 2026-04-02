import streamlit as st
import pd as pd
from datetime import datetime, timedelta, timezone
import math
import random
from supabase import create_client, Client
import plotly.express as px

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Appointed Time | Elite Planner", layout="wide", page_icon="🏢")

# --- 2. GLOBAL SETUP ---
CURRENCY = "GH₵"
SETUP_HOURS = 2.0  
DAILY_CAPACITY_HOURS = 9.0  

# Updated Machine Data including Digital Canon Printers
MACHINE_DATA = {
    'CANON DIGITAL C10000': {'rate': 6000},
    'CANON DIGITAL C800': {'rate': 4000},
    'SM102-CX FOUR COLOUR': {'rate': 8000}, 
    'SM102-P FIVE COLOUR': {'rate': 7500},
    'SM 52': {'rate': 7000}, 
    'GTO 52 SEMI-AUTO-2 COLOUR': {'rate': 4500},
    'GTO 52 MANUAL-2 COLOUR': {'rate': 4000}, 
    'FOLDING UNIT': {'rate': 8000},
    'POLAR CUTTER': {'rate': 20000}, 
    'PERFECT BINDING': {'rate': 500}, 
    'SADDLE STITCHER': {'rate': 1000}, 
    'LAMINATION UNIT': {'rate': 2500},
}

# --- 3. CSS & STYLING ---
st.markdown("""
    <style>
    .main { background-color: #f1f5f9; }
    .component-card {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        margin-bottom: 15px;
    }
    .profit-panel {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        color: white;
        padding: 25px;
        border-radius: 15px;
        position: sticky;
        top: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

@st.cache_resource
def init_supabase():
    try: return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except: return None

supabase: Client = init_supabase()

# --- 4. CORE ENGINES ---
def is_working_time(dt, night, weekend):
    if not weekend and dt.weekday() >= 5: return False
    if not night and (dt.hour < 8 or dt.hour >= 17): return False
    return True

def calculate_finish(start_time, duration_hrs, night, weekend):
    curr = start_time
    rem = duration_hrs
    while rem > 0:
        if is_working_time(curr, night, weekend): rem -= 0.25
        curr += timedelta(minutes=15)
    return curr

# --- 5. DATABASE OPS ---
def get_db_jobs():
    if not supabase: return pd.DataFrame()
    res = supabase.table('jobs').select("*").execute()
    return pd.DataFrame(res.data)

def add_multi_part_job(job_data):
    """Adds a job with multiple components, syncing them to a final finishing stage."""
    tid = f"AT-{random.randint(1000, 9999)}"
    comp_finish_times = []
    
    # Process each component (Cover, Text, Inserts)
    for comp in job_data['components']:
        if not comp['machines']: continue
        
        comp_start = datetime.combine(job_data['start_date'], datetime.now().time()).replace(tzinfo=timezone.utc)
        
        for machine in comp['machines']:
            # Calculate duration based on component-specific impressions
            dur = SETUP_HOURS + (comp['impressions'] / MACHINE_DATA[machine]['rate'])
            finish = calculate_finish(comp_start, dur, job_data['night'], job_data['weekend'])
            
            supabase.table('jobs').insert({
                "job_name": job_data['name'], "tracking_id": tid, "machine": machine,
                "start_time": comp_start.isoformat(), "finish_time": finish.isoformat(),
                "net_profit": job_data['profit_share'], "contract_value": job_data['val_share']
            }).execute()
            comp_start = finish # Sequence within component
        comp_finish_times.append(comp_start)

    # Final Finishing Stage (Must start after ALL components are done)
    if job_data['finishing_machines']:
        finish_start = max(comp_finish_times)
        for f_mach in job_data['finishing_machines']:
            f_dur = SETUP_HOURS + (job_data['total_qty'] / MACHINE_DATA[f_mach]['rate'])
            f_finish = calculate_finish(finish_start, f_dur, job_data['night'], job_data['weekend'])
            supabase.table('jobs').insert({
                "job_name": job_data['name'], "tracking_id": tid, "machine": f_mach,
                "start_time": finish_start.isoformat(), "finish_time": f_finish.isoformat(),
                "net_profit": 0, "contract_value": 0 # Profit already accounted in components
            }).execute()
            finish_start = f_finish
    return tid

# --- 6. UI LAYOUT ---
tab_dash, tab_plan, tab_control, tab_track = st.tabs(["📊 DASHBOARD", "📝 SIMULATION", "📅 CONTROL", "🚛 TRACKING"])

with tab_plan:
    st.subheader("📝 Multi-Component Production Planner")
    
    # Global Job Info
    c1, c2, c3 = st.columns([2, 1, 1])
    job_name = c1.text_input("Project Name (e.g. 2026 Annual Report)")
    prod_type = c2.selectbox("Product Category", ["Skillet/Flyer", "Book/Brochure", "Short-Run Digital"])
    total_val = c3.number_input("Total Contract Value", min_value=0.0, value=5000.0)

    # Component Layout
    col_input, col_viz = st.columns([2, 1])
    
    with col_input:
        # COMPONENT 1: COVER
        with st.container():
            st.markdown('<div class="component-card">', unsafe_allow_html=True)
            st.markdown("### 📔 Part 1: Cover Specs")
            cc1, cc2, cc3 = st.columns(3)
            cov_qty = cc1.number_input("Cover Qty", value=1000, key="cq")
            cov_ups = cc2.number_input("Ups per Sheet", value=2, key="cu")
            cov_mat = cc3.number_input("Paper Cost (Cover)", value=200.0)
            cov_route = st.multiselect("Manual Routing: Cover", list(MACHINE_DATA.keys()), key="cm")
            st.markdown('</div>', unsafe_allow_html=True)

        # COMPONENT 2: TEXT/INNERS
        with st.container():
            st.markdown('<div class="component-card">', unsafe_allow_html=True)
            st.markdown("### 📄 Part 2: Inner Text Specs")
            tc1, tc2, tc3 = st.columns(3)
            pages = tc1.number_input("Total Pages", value=64)
            sig_size = tc2.selectbox("Signature Size", [8, 16, 32], index=1)
            text_mat = tc3.number_input("Paper Cost (Text)", value=800.0)
            
            # Auto-calculate impressions for books
            sections = math.ceil(pages / sig_size)
            text_impressions = sections * (cov_qty) # Rough estimate: sections * run length
            st.caption(f"Calculated: {sections} signatures. Total impressions: {text_impressions}")
            
            text_route = st.multiselect("Manual Routing: Inners", list(MACHINE_DATA.keys()), key="tm")
            st.markdown('</div>', unsafe_allow_html=True)

        # COMPONENT 3: FINISHING
        with st.container():
            st.markdown('<div class="component-card">', unsafe_allow_html=True)
            st.markdown("### 🛠️ Part 3: Final Finishing")
            fin_route = st.multiselect("Manual Routing: Binding & Packing", list(MACHINE_DATA.keys()), key="fm")
            st.markdown('</div>', unsafe_allow_html=True)

    with col_viz:
        # Financial Analysis Logic
        ovh_rate = st.number_input("Shop Overhead (GH₵/hr)", value=60.0)
        
        # Calculate Total Hours (Simple estimate for simulation)
        est_hrs = 0
        if cov_route: est_hrs += (len(cov_route) * SETUP_HOURS) + ((cov_qty/cov_ups)/4000)
        if text_route: est_hrs += (len(text_route) * SETUP_HOURS) + (text_impressions/7000)
        if fin_route: est_hrs += (len(fin_route) * SETUP_HOURS)
        
        total_mat = cov_mat + text_mat
        net_profit = total_val - total_mat - (est_hrs * ovh_rate)
        
        st.markdown(f"""
            <div class="profit-panel">
                <small>CONSOLIDATED ANALYSIS</small>
                <h2 style='color:white;'>{CURRENCY}{net_profit:,.2f}</h2>
                <p>Est. Net Profit</p>
                <hr>
                <p>Total Mat: {CURRENCY}{total_mat:,.2f}</p>
                <p>Est. Hours: {est_hrs:.1f} hrs</p>
                <p>Margin: {(net_profit/total_val*100):.1f}%</p>
            </div>
        """, unsafe_allow_html=True)

    # Submission Logic
    st.divider()
    s1, s2, s3 = st.columns(3)
    start_date = s1.date_input("Schedule Start")
    night = s2.toggle("🌙 Enable Night Shift")
    wknd = s3.toggle("📅 Work Weekends")
    
    if st.button("🚀 Commit Full Project to Production", use_container_width=True):
        job_payload = {
            "name": job_name, "total_qty": cov_qty, "start_date": start_date,
            "night": night, "weekend": wknd, "profit_share": net_profit/2, "val_share": total_val/2,
            "components": [
                {"name": "Cover", "impressions": cov_qty/cov_ups, "machines": cov_route},
                {"name": "Text", "impressions": text_impressions, "machines": text_route}
            ],
            "finishing_machines": fin_route
        }
        tid = add_multi_part_job(job_payload)
        st.success(f"Project Queued! Tracking ID: {tid}")

# --- 7. TRACKING & DASHBOARD (Remains intact but shows ID correctly) ---
with tab_track:
    st.markdown("### 🚛 Professional Job Jacket")
    sid = st.text_input("Enter Job ID").upper()
    if sid:
        df = get_db_jobs()
        match = df[df['tracking_id'] == sid]
        if not match.empty:
            st.info(f"Project: {match['job_name'].iloc[0]} | Stages: {len(match)}")
            st.dataframe(match[['machine', 'start_time', 'finish_time']])

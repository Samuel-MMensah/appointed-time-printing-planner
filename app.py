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
SHIFT_START_HOUR = 8
SHIFT_END_HOUR = 17
DAILY_CAPACITY_HOURS = 8.0  # 8 effective working hours (9 hours total - 1 hour break)

# Machine Registry updated with exact data from verified shop floor documentation
MACHINE_DATA = {
    'SM102-CX FOUR COLOUR': {'rate': 8000, 'setup_hours': 1.5},
    'SM102-P FIVE COLOUR': {'rate': 7500, 'setup_hours': 1.5},
    'SM 52': {'rate': 7000, 'setup_hours': 1.5},
    'GTO 52 SEMI-AUTO-2 COLOUR': {'rate': 4500, 'setup_hours': 1.5},
    'GTO 52 MANUAL-2 COLOUR': {'rate': 4000, 'setup_hours': 2.0},  # 2 hours setup
    'FOLDING UNIT (CONTINUOUS)': {'rate': 8000, 'setup_hours': 1.5},
    'MBO-B30E (SINGLE FOLD)': {'rate': 16000, 'setup_hours': 1.5},
    'PERFECT BINDING': {'rate': 500, 'setup_hours': 1.5},
    'SADDLE STITCHER': {'rate': 1000, 'setup_hours': 1.5},
    'POLAR CUTTER (BOOKS)': {'rate': 2000, 'setup_hours': 1.0},    # 1 hour setup
    'POLAR CUTTER (SHEETS)': {'rate': 50000, 'setup_hours': 1.0},  # 1 hour setup
    '3 WAY TRIMMER': {'rate': 5000, 'setup_hours': 1.0},           # 1 hour setup
    'LAMINATION UNIT': {'rate': 2500, 'setup_hours': 1.5},
    'DIE CUTTER': {'rate': 3000, 'setup_hours': 1.5},  
    'FOLDER GLUER': {'rate': 12000, 'setup_hours': 1.5}, 
    'CANON DIGITAL C10000': {'rate': 6000, 'setup_hours': 0.5},    # Digital parameters
    'CANON DIGITAL C800': {'rate': 4000, 'setup_hours': 0.5},
}

# --- 3. EXECUTIVE UI STYLING ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    .stApp { background-color: #f1f5f9; }
    .metric-card {
        background: white; padding: 1.5rem; border-radius: 12px;
        border-bottom: 4px solid #2563eb; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
        text-align: center; margin-bottom: 1rem;
    }
    .metric-label { font-size: 0.8rem; color: #64748b; text-transform: uppercase; font-weight: 700; }
    .metric-value { font-size: 1.8rem; font-weight: 800; color: #0f172a; margin-top: 0.5rem; }
    .section-header {
        font-size: 1.25rem; font-weight: 700; color: #1e293b;
        margin: 2rem 0 1rem 0; padding-bottom: 0.5rem; border-bottom: 2px solid #e2e8f0;
    }
    .planner-card { background: white; padding: 2rem; border-radius: 16px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.05); }
    .summary-box { background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); color: white; padding: 2rem; border-radius: 16px; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_resource
def init_supabase():
    try: 
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except: 
        return None

supabase: Client = init_supabase()

# --- 4. ADVANCED PLANNING & SCHEDULING (APS) ENGINE ---

def get_db_jobs():
    if not supabase: return pd.DataFrame()
    try:
        res = supabase.table('jobs').select("*").execute()
        return pd.DataFrame(res.data)
    except: 
        return pd.DataFrame()

def apply_calendar_bounds(dt):
    """Adjusts timestamp to match work hours and automatically skips weekends."""
    # Handle hour boundaries
    if dt.hour < SHIFT_START_HOUR:
        dt = dt.replace(hour=SHIFT_START_HOUR, minute=0, second=0, microsecond=0)
    elif dt.hour >= SHIFT_END_HOUR:
        dt = (dt + timedelta(days=1)).replace(hour=SHIFT_START_HOUR, minute=0, second=0, microsecond=0)
    
    # Skip weekends (Saturday=5, Sunday=6)
    while dt.weekday() in [5, 6]:
        dt = (dt + timedelta(days=1)).replace(hour=SHIFT_START_HOUR, minute=0, second=0, microsecond=0)
    return dt

def get_machine_next_available_time(machine_name, requested_start_dt):
    """Queries active database entries to determine the next available time slot."""
    df = get_db_jobs()
    if df.empty or 'machine' not in df.columns:
        return apply_calendar_bounds(requested_start_dt)
    
    # Filter allocations for this specific machine
    machine_df = df[df['machine'] == machine_name].copy()
    if machine_df.empty:
        return apply_calendar_bounds(requested_start_dt)
    
    machine_df['finish_time'] = pd.to_datetime(machine_df['finish_time'], utc=True)
    max_finish = machine_df['finish_time'].max().to_pydatetime()
    
    # Use the further point in time out of requested start and machine availability
    if max_finish > requested_start_dt:
        return apply_calendar_bounds(max_finish)
    return apply_calendar_bounds(requested_start_dt)

def calculate_production_time(start_dt, impressions, machine_name):
    """Finite Capacity Production Loop with precise calendar, shift boundaries, and setup rules."""
    machine = MACHINE_DATA[machine_name]
    rate = machine['rate']
    setup_hours = machine['setup_hours']
    
    current_time = apply_calendar_bounds(start_dt)
    
    # Apply initial job setup time penalty exactly once upon allocation
    current_time += timedelta(hours=setup_hours)
    current_time = apply_calendar_bounds(current_time)
    
    remaining_imps = impressions
    is_first_day = True
    
    while remaining_imps > 0:
        current_time = apply_calendar_bounds(current_time)
        
        # Apply minor daily warmup adjustments for multi-day jobs
        if not is_first_day and current_time.hour == SHIFT_START_HOUR and current_time.minute == 0:
            current_time += timedelta(minutes=15)
            current_time = apply_calendar_bounds(current_time)
            
        workday_end = current_time.replace(hour=SHIFT_END_HOUR, minute=0, second=0, microsecond=0)
        available_hours = (workday_end - current_time).total_seconds() / 3600.0
        
        if available_hours <= 0:
            current_time = (current_time + timedelta(days=1)).replace(hour=SHIFT_START_HOUR, minute=0)
            is_first_day = False
            continue
            
        possible_today = available_hours * rate
        if remaining_imps <= possible_today:
            current_time += timedelta(hours=remaining_imps / rate)
            remaining_imps = 0
        else:
            remaining_imps -= possible_today
            current_time = (current_time + timedelta(days=1)).replace(hour=SHIFT_START_HOUR, minute=0)
            is_first_day = False
            
    return apply_calendar_bounds(current_time)

def add_multi_part_job(job_data):
    """Sequentially schedules tasks based on machine availability and process dependency logic."""
    tid = f"JOB-{random.randint(1000, 9999)}"
    total_stages = sum(len(c['machines']) for c in job_data['components']) + len(job_data['finishing_machines'])
    val_per_stage = job_data['total_val'] / total_stages if total_stages > 0 else 0

    input_start_date = datetime.combine(job_data['start_date'], datetime.now().time()).replace(tzinfo=timezone.utc)
    printing_finish_times = []
    records_to_insert = []

    # 1. PRINTING ROUTING (Evaluated in parallel across machine streams)
    for comp in job_data['components']:
        for machine in comp['machines']:
            # Find when this specific machine is clear
            allocated_start = get_machine_next_available_time(machine, input_start_date)
            finish = calculate_production_time(allocated_start, comp['impressions'], machine)
            printing_finish_times.append(finish)
            
            records_to_insert.append({
                "job_name": job_data['name'], "tracking_id": tid, "machine": machine,
                "sales_rep": job_data['sales_rep'], "quantity": int(job_data['total_qty']),
                "ups": int(job_data['type_id']), "impressions": int(comp['impressions']), 
                "start_time": allocated_start.isoformat(), "finish_time": finish.isoformat(), 
                "contract_value": float(val_per_stage)
            })

    # 2. FINISHING ROUTING (Chained downstream from the longest print run)
    if printing_finish_times:
        earliest_finishing_start = max(printing_finish_times)
    else:
        earliest_finishing_start = apply_calendar_bounds(input_start_date)

    # Sort operations sequentially based on production flow rules
    ordered_finishing = sorted(job_data['finishing_machines'], 
                               key=lambda x: 0 if "DIE" in x.upper() else (1 if "FOLDER" in x.upper() else 2))

    current_finishing_anchor = earliest_finishing_start

    for machine_name in ordered_finishing:
        # Define processing metrics by sheet volume vs item count
        if "DIE CUTTER" in machine_name.upper():
            calculation_qty = job_data['total_qty'] / max(1, job_data['type_id'])
        else:
            calculation_qty = job_data['total_qty']

        # Determine when this specific finishing equipment is clear
        f_start = get_machine_next_available_time(machine_name, current_finishing_anchor)
        f_finish = calculate_production_time(f_start, calculation_qty, machine_name)
        
        records_to_insert.append({
            "job_name": job_data['name'], "tracking_id": tid, "machine": machine_name,
            "sales_rep": job_data['sales_rep'], "quantity": int(job_data['total_qty']),
            "ups": int(job_data['type_id']), "impressions": int(calculation_qty),
            "start_time": f_start.isoformat(), "finish_time": f_finish.isoformat(),
            "contract_value": float(val_per_stage)
        })
        
        # Enforce linear downstream dependency routing
        current_finishing_anchor = f_finish

    # Bulk insert schedule records into the database
    if supabase and records_to_insert:
        for record in records_to_insert:
            supabase.table('jobs').insert(record).execute()

# --- 5. MANAGEMENT & PLANNING USER INTERFACE ---
tab_dash, tab_plan, tab_control = st.tabs(["🏛️ COMMAND CENTER", "⚙️ PRODUCTION PLANNER", "📅 SHOP FLOOR CONTROL"])

with tab_dash:
    df = get_db_jobs()
    if not df.empty:
        df['start_time'] = pd.to_datetime(df['start_time'], utc=True)
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.markdown(f'<div class="metric-card"><div class="metric-label">Active Job Rows</div><div class="metric-value">{df["tracking_id"].nunique()}</div></div>', unsafe_allow_html=True)
        with col2: st.markdown(f'<div class="metric-card"><div class="metric-label">Value</div><div class="metric-value">{CURRENCY}{df["contract_value"].sum():,.0f}</div></div>', unsafe_allow_html=True)
        with col3:
            books = df[df['ups'] == 1]['tracking_id'].nunique()
            st.markdown(f'<div class="metric-card"><div class="metric-label">Book Projects</div><div class="metric-value">{books}</div></div>', unsafe_allow_html=True)
        with col4:
            skillets = df[df['ups'] > 1]['tracking_id'].nunique()
            st.markdown(f'<div class="metric-card"><div class="metric-label">Multi-Up Jobs</div><div class="metric-value">{skillets}</div></div>', unsafe_allow_html=True)

        st.markdown('<p class="section-header">📊 Strategic Load & Revenue</p>', unsafe_allow_html=True)
        left, right = st.columns([2, 1])
        with left:
            load_df = df.groupby('machine').size().reset_index(name='Queue')
            st.plotly_chart(px.bar(load_df, x='machine', y='Queue', color='Queue', color_continuous_scale='Blues', title="Operations Queue Count"), use_container_width=True)
        with right:
            rev_df = df.groupby('job_name')['contract_value'].sum().reset_index()
            st.plotly_chart(px.pie(rev_df, values='contract_value', names='job_name', hole=0.5, title="Revenue Allocation"), use_container_width=True)

with tab_plan:
    st.markdown('<p class="section-header">Project Architecture</p>', unsafe_allow_html=True)
    col_in, col_sum = st.columns([2, 1])
    with col_in:
        st.markdown('<div class="planner-card">', unsafe_allow_html=True)
        job_name = st.text_input("Project Description")
        sales_rep = st.selectbox("Sales Lead", ["Mabel Ampofo", "Daphne Sarpong", "Elizabeth Akoto", "Charles Adoo", "Christian Mante", "Bertha Tackie", "Reginald Aidam", "Mohammed Seidu"])
        prod_cat = st.selectbox("Category", ["📦 Skillet / Box", "📚 Book / Brochure", "📄 Flyer"])
        c1, c2, c3 = st.columns(3)
        order_qty = c1.number_input("Units", value=10000, step=1000)
        total_val = c2.number_input("Total Value", value=5000.0)
        ups = c3.number_input("Ups per Sheet", value=10, min_value=1)
        
        if "Book" in prod_cat:
            type_id, pgs = 1, st.number_input("Pages", value=64, min_value=1)
            sig = st.selectbox("Signature", [8, 16, 32], index=1)
            text_imps = math.ceil(pgs/sig) * order_qty
            r1, r2, r3 = st.columns(3)
            comp = [
                {"name": "Cover", "impressions": max(1.0, order_qty/ups), "machines": r1.multiselect("Cover Press", list(MACHINE_DATA.keys()))},
                {"name": "Text", "impressions": float(text_imps), "machines": r2.multiselect("Text Press", list(MACHINE_DATA.keys()))}
            ]
            fin_route = r3.multiselect("Finishing Line", list(MACHINE_DATA.keys()))
        else:
            type_id = ups 
            r1, r2 = st.columns(2)
            comp = [{"name": "Body", "impressions": max(1.0, order_qty/ups), "machines": r1.multiselect("Printing Press", list(MACHINE_DATA.keys()))}]
            fin_route = r2.multiselect("Finishing Line", list(MACHINE_DATA.keys()))
        st.markdown('</div>', unsafe_allow_html=True)
        
    with col_sum:
        st.markdown('<div class="summary-box">', unsafe_allow_html=True)
        st.markdown("### 🚀 Routing Deployment")
        start_date = st.date_input("Target Start Date")
        if st.button("PUSH TO SHOP FLOOR", use_container_width=True):
            if job_name and fin_route and any(c['machines'] for c in comp):
                add_multi_part_job({
                    "name": job_name, "sales_rep": sales_rep, "total_qty": order_qty, 
                    "total_val": total_val, "start_date": start_date, "type_id": type_id, 
                    "components": comp, "finishing_machines": fin_route
                })
                st.success("Dispatched to Finite Queues!")
                st.rerun()
            else: 
                st.error("Missing critical project routing parameters.")
        st.markdown('</div>', unsafe_allow_html=True)

with tab_control:
    df = get_db_jobs()
    if not df.empty:
        df['start_time'] = pd.to_datetime(df['start_time'], utc=True)
        df['finish_time'] = pd.to_datetime(df['finish_time'], utc=True)
        st.markdown('<p class="section-header">⌛ Live Finite Capacity Timeline</p>', unsafe_allow_html=True)
        
        # Chronological Gantt Visualization
        fig = px.timeline(df, x_start="start_time", x_end="finish_time", y="machine", color="job_name", 
                          hover_data=["tracking_id", "impressions"], template="plotly_white", 
                          color_discrete_sequence=px.colors.qualitative.Bold)
        fig.update_layout(height=450, margin=dict(t=10, b=10, l=10, r=10), yaxis={'categoryorder':'category ascending'})
        st.plotly_chart(fig, use_container_width=True)
        
        for tid, group in df.groupby('tracking_id'):
            job_title = group['job_name'].iloc[0].upper()
            with st.expander(f"📦 {job_title} ({tid})"):
                d_df = group[['machine', 'impressions', 'start_time', 'finish_time']].copy()
                
                # Render correct shift capacities using explicit machine settings
                d_df['Capacity (Full Shift)'] = d_df['machine'].apply(
                    lambda x: f"{int((DAILY_CAPACITY_HOURS - MACHINE_DATA[x]['setup_hours']) * MACHINE_DATA[x]['rate']):,}"
                )
                
                d_df['start_time'] = d_df['start_time'].dt.strftime('%a %d %b, %H:%M')
                d_df['finish_time'] = d_df['finish_time'].dt.strftime('%a %d %b, %H:%M')
                
                st.table(d_df)
                
                if st.button(f"🗑️ Scrap Project Run {tid}", key=f"scrap_{tid}"):
                    supabase.table('jobs').delete().eq('tracking_id', tid).execute()
                    st.rerun()

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import math
import random
from supabase import create_client, Client
import plotly.express as px
import plotly.graph_objects as go

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Appointed Time | Elite ERP", layout="wide", page_icon="🏢")

# --- 2. GLOBAL SETUP ---
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

# --- 3. ENHANCED ELITE CSS STYLING ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stApp { background-color: #f8fafc; }
    
    .metric-card { background: white; padding: 24px; border-radius: 16px; border: 1px solid #edf2f7; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); text-align: center; }
    .metric-value { font-size: 28px; font-weight: 700; color: #1a202c; }
    .metric-label { font-size: 14px; color: #718096; text-transform: uppercase; letter-spacing: 1px; }
    
    .planner-card { 
        background: white; 
        padding: 2rem; 
        border-radius: 24px; 
        border: 1px solid #e2e8f0; 
        box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05); 
        margin-bottom: 20px;
    }
    
    .step-label {
        background: #eff6ff;
        color: #1e40af;
        padding: 4px 12px;
        border-radius: 8px;
        font-size: 12px;
        font-weight: 700;
        margin-bottom: 10px;
        display: inline-block;
    }

    .section-header { font-size: 22px; font-weight: 800; color: #0f172a; margin: 25px 0 15px 0; display: flex; align-items: center; gap: 10px; }
    
    .summary-box { 
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); 
        color: white; 
        padding: 30px; 
        border-radius: 24px; 
        position: sticky; 
        top: 20px;
        box-shadow: 0 20px 25px -5px rgba(0,0,0,0.2);
    }
    
    .blueprint-stat {
        background: rgba(255,255,255,0.05);
        padding: 12px;
        border-radius: 12px;
        margin-top: 10px;
        border: 1px solid rgba(255,255,255,0.1);
    }
    </style>
    """, unsafe_allow_html=True)

@st.cache_resource
def init_supabase():
    try: return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except: return None

supabase: Client = init_supabase()

# --- 4. DATA ENGINE ---
def get_db_jobs():
    if not supabase: return pd.DataFrame()
    res = supabase.table('jobs').select("*").execute()
    return pd.DataFrame(res.data)

def calculate_production_time(start_dt, impressions, machine_rate):
    current_time = start_dt
    remaining_imps = impressions
    current_time += timedelta(hours=SETUP_HOURS)
    
    while remaining_imps > 0:
        workday_end = current_time.replace(hour=17, minute=0, second=0, microsecond=0)
        if current_time >= workday_end:
            current_time = (current_time + timedelta(days=1)).replace(hour=8, minute=0)
            workday_end = current_time.replace(hour=17, minute=0)
            
        hours_left_today = (workday_end - current_time).total_seconds() / 3600
        imps_possible_today = hours_left_today * machine_rate
        
        if remaining_imps <= imps_possible_today:
            duration_hours = remaining_imps / machine_rate
            current_time += timedelta(hours=duration_hours)
            remaining_imps = 0
        else:
            remaining_imps -= imps_possible_today
            current_time = (current_time + timedelta(days=1)).replace(hour=8, minute=0)
    return current_time

def add_multi_part_job(job_data):
    tid = f"JOB-{random.randint(1000, 9999)}"
    total_stages = sum(len(c['machines']) for c in job_data['components']) + len(job_data['finishing_machines'])
    val_per_stage = job_data['total_val'] / total_stages if total_stages > 0 else 0

    printing_start_time = datetime.combine(job_data['start_date'], datetime.now().time()).replace(tzinfo=timezone.utc)
    if printing_start_time.hour < 8: printing_start_time = printing_start_time.replace(hour=8)
    if printing_start_time.hour >= 17: printing_start_time = (printing_start_time + timedelta(days=1)).replace(hour=8)

    for comp in job_data['components']:
        if not comp['machines']: continue
        current_stage_start = printing_start_time
        for machine in comp['machines']:
            finish_time = calculate_production_time(current_stage_start, comp['impressions'], MACHINE_DATA[machine]['rate'])
            supabase.table('jobs').insert({
                "job_name": job_data['name'], "tracking_id": tid, "machine": machine,
                "sales_rep": job_data['sales_rep'], "quantity": int(job_data['total_qty']),
                "ups": int(job_data['type_id']), "impressions": int(comp['impressions']), 
                "start_time": current_stage_start.isoformat(), "finish_time": finish_time.isoformat(), 
                "contract_value": float(val_per_stage)
            }).execute()
            current_stage_start = finish_time

    if job_data['finishing_machines']:
        finish_start_anchor = printing_start_time + timedelta(days=1)
        for i, f_mach in enumerate(job_data['finishing_machines']):
            stage_offset_start = finish_start_anchor + timedelta(hours=(i * 4))
            if stage_offset_start.hour >= 17:
                stage_offset_start = (stage_offset_start + timedelta(days=1)).replace(hour=8)
            elif stage_offset_start.hour < 8:
                stage_offset_start = stage_offset_start.replace(hour=8)

            f_finish = calculate_production_time(stage_offset_start, job_data['total_qty'], MACHINE_DATA[f_mach]['rate'])
            supabase.table('jobs').insert({
                "job_name": job_data['name'], "tracking_id": tid, "machine": f_mach,
                "sales_rep": job_data['sales_rep'], "quantity": int(job_data['total_qty']),
                "ups": int(job_data['type_id']), "impressions": int(job_data['total_qty']),
                "start_time": stage_offset_start.isoformat(), "finish_time": f_finish.isoformat(),
                "contract_value": float(val_per_stage)
            }).execute()
    return tid

# --- 5. UI LAYOUT ---
tab_dash, tab_plan, tab_control = st.tabs(["🏛️ COMMAND CENTER", "⚙️ PRODUCTION PLANNER", "📅 SHOP FLOOR CONTROL"])

with tab_dash:
    df = get_db_jobs()
    if not df.empty:
        df['start_time'] = pd.to_datetime(df['start_time'], format='ISO8601', utc=True)
        df['finish_time'] = pd.to_datetime(df['finish_time'], format='ISO8601', utc=True)
        
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Active Jobs</div><div class="metric-value">{df["job_name"].nunique()}</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Pipeline Value</div><div class="metric-value">{CURRENCY}{df["contract_value"].sum():,.0f}</div></div>', unsafe_allow_html=True)
        with c3: 
            books_count = df[df['ups'] == 1]['job_name'].nunique()
            st.markdown(f'<div class="metric-card"><div class="metric-label">Book Projects</div><div class="metric-value">{books_count}</div></div>', unsafe_allow_html=True)
        with c4:
            skillets_count = df[df['ups'] == 2]['job_name'].nunique()
            st.markdown(f'<div class="metric-card"><div class="metric-label">Skillet Jobs</div><div class="metric-value">{skillets_count}</div></div>', unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        col_left, col_right = st.columns([1.5, 1])
        
        with col_left:
            st.markdown('<p class="section-header">🥇 Top 5 Jobs by Revenue</p>', unsafe_allow_html=True)
            top_jobs = df.groupby('job_name')['contract_value'].sum().sort_values(ascending=True).tail(5).reset_index()
            fig_top = px.bar(top_jobs, y='job_name', x='contract_value', orientation='h', 
                             text_auto='.2s', color='contract_value', color_continuous_scale='Blues')
            fig_top.update_layout(showlegend=False, height=400, margin=dict(t=10, b=10, l=10, r=10), 
                                  xaxis_title="Revenue (GH₵)", yaxis_title=None,
                                  paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_top, use_container_width=True)

        with col_right:
            st.markdown('<p class="section-header">🍕 Revenue by Category</p>', unsafe_allow_html=True)
            cat_data = df.groupby('ups')['contract_value'].sum().reset_index()
            cat_data['Category'] = cat_data['ups'].map({1: 'Books/Manuals', 2: 'Skillets/Boxes'})
            fig_pie = px.pie(cat_data, values='contract_value', names='Category', hole=.5,
                             color_discrete_sequence=['#2563eb', '#93c5fd'])
            fig_pie.update_traces(textposition='outside', textinfo='percent+label')
            fig_pie.update_layout(height=400, margin=dict(t=30, b=30, l=30, r=30), 
                                  showlegend=False, paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_pie, use_container_width=True)

with tab_plan:
    st.markdown('<p class="section-header">🛠️ Project Specification Architecture</p>', unsafe_allow_html=True)
    col_input, col_summ = st.columns([2.2, 1])
    
    with col_input:
        with st.container():
            st.markdown('<div class="planner-card">', unsafe_allow_html=True)
            st.markdown('<span class="step-label">STEP 1</span>', unsafe_allow_html=True)
            st.markdown("#### 🟢 Identity & Classification")
            c1, c2, c3 = st.columns([2, 1, 1])
            job_name = c1.text_input("Project Description", placeholder="Enter unique job name...")
            sales_rep = c2.selectbox("Account Manager", ["Mabel Ampofo", "Daphne Sarpong", "Elizabeth Akoto", "Charles Adoo", "Christian Mante", "Bertha Tackie", "Reginald Aidam"])
            prod_cat = c3.selectbox("Work Type", ["📚 Book / Brochure", "📦 Skillet / Box", "📄 Flyer / Leaflet"])
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown('<span class="step-label">STEP 2</span>', unsafe_allow_html=True)
            st.markdown("#### 🔵 Dimensional Specs")
            cc1, cc2, cc3 = st.columns(3)
            order_qty = cc1.number_input("Total Units", value=1000, step=500)
            total_val = cc2.number_input("Project Value (GH₵)", value=5000.0)
            
            if "Book" in prod_cat:
                type_id = 1
                ups = cc3.number_input("Cover Ups", value=2)
                p1, p2 = st.columns(2)
                pages = p1.number_input("Page Count", value=64)
                sig_size = p2.selectbox("Signature Breakdown", [8, 16, 32], index=1)
                text_impressions = math.ceil(pages / sig_size) * order_qty
            else:
                type_id = 2
                ups = cc3.number_input("Items Per Sheet", value=12)
                text_impressions = 0

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown('<span class="step-label">STEP 3</span>', unsafe_allow_html=True)
            st.markdown("#### 🟣 Workflow Routing")
            if "Book" in prod_cat:
                r1, r2, r3 = st.columns(3)
                cov_route = r1.multiselect("Press: Cover", list(MACHINE_DATA.keys()))
                txt_route = r2.multiselect("Press: Text", list(MACHINE_DATA.keys()))
                fin_route = r3.multiselect("Binding Line", list(MACHINE_DATA.keys()))
                components = [
                    {"name": "Cover", "impressions": order_qty/ups, "machines": cov_route},
                    {"name": "Text", "impressions": text_impressions, "machines": txt_route}
                ]
            else:
                r1, r2 = st.columns(2)
                print_route = r1.multiselect("Printing Line", list(MACHINE_DATA.keys()))
                fin_route = r2.multiselect("Finishing Line", list(MACHINE_DATA.keys()))
                components = [{"name": "Body", "impressions": order_qty/ups, "machines": print_route}]
            st.markdown('</div>', unsafe_allow_html=True)

    with col_summ:
        st.markdown('<div class="summary-box">', unsafe_allow_html=True)
        st.markdown("### 📋 Run Blueprint")
        st.markdown("---")
        
        # Real-time data points
        total_est_imps = int(order_qty/ups + (text_impressions if 'Book' in prod_cat else 0))
        num_stages = len(fin_route) + (len(cov_route)+len(txt_route) if 'Book' in prod_cat else len(print_route))
        
        st.markdown(f"**Description:** {job_name if job_name else 'Unnamed Project'}")
        
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.markdown(f'<div class="blueprint-stat"><small>TOTAL IMPS</small><br><b>{total_est_imps:,}</b></div>', unsafe_allow_html=True)
        with col_s2:
            st.markdown(f'<div class="blueprint-stat"><small>WORK STAGES</small><br><b>{num_stages}</b></div>', unsafe_allow_html=True)
            
        st.markdown("<br>", unsafe_allow_html=True)
        start_date = st.date_input("Deployment Date")
        
        if st.button("🚀 PUSH TO PRODUCTION", use_container_width=True):
            if job_name:
                payload = {"name": job_name, "sales_rep": sales_rep, "total_qty": order_qty, "total_val": total_val, "start_date": start_date, "type_id": type_id, "components": components, "finishing_machines": fin_route}
                add_multi_part_job(payload)
                st.toast("Job Dispatched Successfully!", icon="🏭")
                st.rerun()
            else:
                st.error("Please enter a Project Description.")
        st.markdown('</div>', unsafe_allow_html=True)

with tab_control:
    df = get_db_jobs()
    if not df.empty:
        df['start_time'] = pd.to_datetime(df['start_time'], format='ISO8601', utc=True)
        df['finish_time'] = pd.to_datetime(df['finish_time'], format='ISO8601', utc=True)
        st.markdown('<p class="section-header">⌛ Real-Time Timeline</p>', unsafe_allow_html=True)
        fig = px.timeline(df, x_start="start_time", x_end="finish_time", y="machine", color="job_name", 
                          template="plotly_white", color_discrete_sequence=px.colors.qualitative.Bold)
        fig.update_layout(height=400, margin=dict(t=0, b=0), paper_bgcolor='rgba(0,0,0,0)', showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
        
        st.markdown('<p class="section-header">📋 Detailed Production Queue</p>', unsafe_allow_html=True)
        for job_name, group in df.groupby('job_name'):
            with st.expander(f"📦 {job_name.upper()} | Status: IN PRODUCTION", expanded=False):
                display_df = group[['machine', 'impressions', 'start_time', 'finish_time']].copy()
                display_df['start_time'] = display_df['start_time'].dt.strftime('%d %b, %H:%M')
                display_df['finish_time'] = display_df['finish_time'].dt.strftime('%d %b, %H:%M')
                st.dataframe(display_df, use_container_width=True, hide_index=True)
                col_actions = st.columns([6, 1])
                if col_actions[1].button("🗑️ Scrap Job", key=f"del_{job_name}", use_container_width=True):
                    supabase.table('jobs').delete().eq('job_name', job_name).execute()
                    st.rerun()

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import math
from supabase import create_client, Client

# Page configuration
st.set_page_config(
    page_title="Appointed Time Printing - Job Planning",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Machine data with verified impressions per hour rates
# All machines have fixed 2-hour setup time
MACHINE_DATA = {
    'SM102-CX FOUR COLOUR': {'rate': 8000},
    'SM102-P FIVE COLOUR': {'rate': 7500},
    'SM 52': {'rate': 7000},
    'GTO 52 SEMI-AUTO-2 COLOUR': {'rate': 4500},
    'GTO 52 MANUAL-2 COLOUR': {'rate': 4000},
    'FOLDING UNIT CONTINUOUS FOLD': {'rate': 8000},
    'MBO-B30E SINGLE FOLD': {'rate': 16000},
    'POLAR MACHINE FOR BOOKS': {'rate': 2000},
    'POLAR MACHINE FOR SHEETS': {'rate': 50000},
    '3 WAY TRIMMER': {'rate': 5000},
    'PERFECT BINDING': {'rate': 500},
    'LAMINATION UNIT': {'rate': 2500},
    'PEDDLER SADDLE STITCH': {'rate': 1000},
    'DIE CUTTER': {'rate': 3000},
    'FOLDER GLUER': {'rate': 12000},
}

SETUP_HOURS = 2.0  # Fixed setup time for all machines
CURRENCY = "GH₵"  # Ghana Cedis

# Initialize Supabase client using st.secrets
@st.cache_resource
def init_supabase():
    """Initialize Supabase client with st.secrets"""
    try:
        url = st.secrets.get("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY")
        
        if not url or not key:
            st.warning("⚠️ Supabase credentials not found in secrets. Using session state only.")
            return None
        
        return create_client(url, key)
    except Exception as e:
        st.warning(f"⚠️ Supabase connection issue: {e}")
        return None

supabase: Client = init_supabase()

# Initialize session state
if 'jobs' not in st.session_state:
    st.session_state.jobs = []
if 'sales_reps' not in st.session_state:
    st.session_state.sales_reps = set()
if 'monthly_budget' not in st.session_state:
    st.session_state.monthly_budget = 100000  # GH₵
if 'machine_load' not in st.session_state:
    st.session_state.machine_load = {machine: [] for machine in MACHINE_DATA.keys()}
if 'db_synced' not in st.session_state:
    st.session_state.db_synced = False

# Helper functions
def calculate_impressions(finished_qty, ups, overs_pct):
    """Calculate impressions using skillet math: ceil(Qty/Ups) × (1 + Overs%)"""
    sheets = math.ceil(finished_qty / ups)
    impressions = sheets * (1 + overs_pct / 100)
    return int(impressions)

def calculate_processing_time(machine, impressions):
    """Calculate total time = setup + run time"""
    if machine not in MACHINE_DATA:
        return 0
    rate = MACHINE_DATA[machine]['rate']
    run_time = impressions / rate
    return SETUP_HOURS + run_time

def calculate_job_schedule(job_name, impressions, processes):
    """Calculate sequential schedule where each process starts when previous ends"""
    schedule = []
    current_time = datetime.now()
    
    for process in processes:
        duration = calculate_processing_time(process, impressions)
        end_time = current_time + timedelta(hours=duration)
        
        schedule.append({
            'process': process,
            'start': current_time,
            'end': end_time,
            'duration': duration,
            'impressions': impressions
        })
        
        current_time = end_time
    
    return schedule

def save_job_to_db(job_data):
    """Save job to Supabase"""
    if not supabase:
        return False
    
    try:
        response = supabase.table('jobs').insert(job_data).execute()
        return True
    except Exception as e:
        st.error(f"Error saving job: {e}")
        return False

def load_jobs_from_db():
    """Load all jobs from Supabase"""
    if not supabase:
        return []
    
    try:
        response = supabase.table('jobs').select('*').execute()
        jobs = []
        
        for record in response.data:
            # Parse schedule from stored JSON
            schedule = []
            if 'schedule' in record and record['schedule']:
                for task in record['schedule']:
                    schedule.append({
                        'process': task['process'],
                        'start': datetime.fromisoformat(task['start']),
                        'end': datetime.fromisoformat(task['end']),
                        'duration': task['duration'],
                        'impressions': task['impressions']
                    })
            
            job = {
                'id': record.get('id'),
                'name': record['name'],
                'sales_rep': record['sales_rep'],
                'impressions': record['impressions'],
                'processes': record.get('processes', []),
                'contract_value': record.get('contract_value', 0),
                'schedule': schedule,
                'target_deadline': datetime.fromisoformat(record['target_deadline']) if record.get('target_deadline') else None,
                'created_at': datetime.fromisoformat(record['created_at'])
            }
            jobs.append(job)
            st.session_state.sales_reps.add(record['sales_rep'])
        
        return jobs
    except Exception as e:
        st.warning(f"Error loading jobs from database: {e}")
        return []

def add_job(name, sales_rep, impressions, processes, contract_value, target_deadline=None):
    """Add job to session state and database"""
    schedule = calculate_job_schedule(name, impressions, processes)
    
    job = {
        'name': name,
        'sales_rep': sales_rep,
        'impressions': impressions,
        'processes': processes,
        'contract_value': contract_value,
        'schedule': schedule,
        'target_deadline': target_deadline,
        'created_at': datetime.now()
    }
    
    # Save to database
    db_job = {
        'name': name,
        'sales_rep': sales_rep,
        'impressions': impressions,
        'processes': processes,
        'contract_value': float(contract_value),
        'schedule': [
            {
                'process': t['process'],
                'start': t['start'].isoformat(),
                'end': t['end'].isoformat(),
                'duration': t['duration'],
                'impressions': t['impressions']
            }
            for t in schedule
        ],
        'target_deadline': target_deadline.isoformat() if target_deadline else None,
        'created_at': datetime.now().isoformat()
    }
    
    if save_job_to_db(db_job):
        st.session_state.jobs.append(job)
        st.session_state.sales_reps.add(sales_rep)
        
        # Update machine load
        for task in schedule:
            st.session_state.machine_load[task['process']].append({
                'job': name,
                'start': task['start'],
                'end': task['end'],
                'duration': task['duration']
            })
        
        return True
    return False

# Load jobs from database on startup
if not st.session_state.db_synced and supabase:
    st.session_state.jobs = load_jobs_from_db()
    st.session_state.db_synced = True
    
    # Rebuild machine load
    for job in st.session_state.jobs:
        for task in job['schedule']:
            st.session_state.machine_load[task['process']].append({
                'job': job['name'],
                'start': task['start'],
                'end': task['end'],
                'duration': task['duration']
            })

# Main UI
st.title("🏭 Appointed Time Printing - Job Planning System")

# Sidebar configuration
st.sidebar.markdown("### Configuration")

# Sales rep filter
sales_rep_list = sorted(list(st.session_state.sales_reps)) if st.session_state.sales_reps else ["All"]
selected_rep = st.sidebar.selectbox(
    "Filter by Sales Rep",
    ["All"] + sales_rep_list
)

# Budget input
monthly_budget = st.sidebar.number_input(
    f"Monthly Budget Target ({CURRENCY})",
    value=st.session_state.monthly_budget,
    step=10000
)
st.session_state.monthly_budget = monthly_budget

# Navigation tabs
tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📝 Plan Job", "📈 Gantt View"])

# ==================== TAB 1: DASHBOARD ====================
with tab1:
    st.header("Global Production View - Stoplight System")
    
    # Calculate financial metrics
    total_revenue = sum(job['contract_value'] for job in st.session_state.jobs)
    revenue_gap = monthly_budget - total_revenue
    
    # Display metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Projected Revenue", f"{CURRENCY}{total_revenue:,.0f}")
    with col2:
        st.metric("Budgeted Target", f"{CURRENCY}{monthly_budget:,.0f}")
    with col3:
        status = "🟢" if revenue_gap <= 0 else "🟡" if revenue_gap < monthly_budget * 0.2 else "🔴"
        st.metric(f"{status} Revenue Gap", f"{CURRENCY}{max(0, revenue_gap):,.0f}")
    
    # Stoplight system
    st.subheader("Machine Status (Stoplight System)")
    
    stoplight_data = []
    for machine in sorted(MACHINE_DATA.keys()):
        loads = st.session_state.machine_load.get(machine, [])
        total_load = sum(task['duration'] for task in loads)
        
        if total_load == 0:
            status = "🟢 Available"
            color = "green"
        elif total_load < 2:
            status = "🟡 Low Load"
            color = "yellow"
        else:
            status = "🔴 Heavy Load"
            color = "red"
        
        stoplight_data.append({
            'Machine': machine,
            'Status': status,
            'Current Load (hrs)': f"{total_load:.1f}"
        })
    
    st.dataframe(pd.DataFrame(stoplight_data), use_container_width=True, hide_index=True)
    
    # Production summary
    st.subheader("Production Summary")
    
    filtered_jobs = [j for j in st.session_state.jobs if selected_rep == "All" or j['sales_rep'] == selected_rep]
    
    summary_data = []
    for job in filtered_jobs:
        finish_time = job['schedule'][-1]['end'] if job['schedule'] else None
        status = "✅" if job['target_deadline'] is None or finish_time <= job['target_deadline'] else "❌"
        
        summary_data.append({
            'Job Name': job['name'],
            'Sales Rep': job['sales_rep'],
            'Start': job['schedule'][0]['start'].strftime('%Y-%m-%d %H:%M') if job['schedule'] else '-',
            'Realistic Finish': finish_time.strftime('%Y-%m-%d %H:%M') if finish_time else '-',
            'Status': status,
            f'Revenue ({CURRENCY})': f"{job['contract_value']:,.0f}"
        })
    
    if summary_data:
        st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)
    else:
        st.info("No jobs scheduled yet.")

# ==================== TAB 2: PLAN JOB ====================
with tab2:
    st.header("Plan New Job - Advanced Routing Engine")
    
    with st.form("job_form", clear_on_submit=True):
        st.subheader("Job Information")
        col1, col2 = st.columns(2)
        
        with col1:
            job_name = st.text_input("Job Name", placeholder="e.g., Client A - Brochure Run 2025")
            sales_rep = st.selectbox("Sales Rep Name", 
                                     ["John Smith", "Sarah Johnson", "Mike Davis", "Emma Wilson", "Other"])
            if sales_rep == "Other":
                sales_rep = st.text_input("Enter Sales Rep Name")
        
        with col2:
            contract_value = st.number_input(f"Contract Value ({CURRENCY})", min_value=0.0, value=5000.0, step=100.0)
            target_deadline = st.date_input("Target Delivery Date (Optional)")
        
        st.subheader("Job Specifications - Skillet Math Formula")
        st.markdown(f"**Impressions = ⌈Finished Qty ÷ Ups⌉ × (1 + Overs%)**")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            finished_qty = st.number_input("Finished Quantity", min_value=100, value=100000, step=1000)
        
        with col2:
            ups = st.number_input("Ups-per-Sheet", min_value=1, value=12, step=1)
        
        with col3:
            overs_pct = st.number_input("Overs %", min_value=0.0, value=5.0, step=0.5)
        
        with col4:
            sheets_per_packet = st.number_input("Sheets-per-Packet", min_value=1, value=100, step=1)
        
        # Calculate impressions
        impressions = calculate_impressions(finished_qty, ups, overs_pct)
        packets = math.ceil(impressions / sheets_per_packet)
        
        st.info(f"**Calculated Impressions:** {impressions:,} | **Packets:** {packets:,}")
        
        st.subheader("Production Sequence")
        st.markdown("Select processes in order (Print → Fold/Cut → Trim → Bind):")
        
        selected_processes = []
        cols = st.columns(3)
        for idx, machine in enumerate(sorted(MACHINE_DATA.keys())):
            col = cols[idx % 3]
            if col.checkbox(machine):
                selected_processes.append(machine)
        
        submitted = st.form_submit_button("✅ Create Job & Schedule", use_container_width=True)
        
        if submitted:
            if not job_name or not sales_rep or not selected_processes:
                st.error("❌ Please fill all fields and select at least one process.")
            else:
                target_dt = datetime.combine(target_deadline, datetime.min.time()) if target_deadline else None
                
                if add_job(job_name, sales_rep, impressions, selected_processes, contract_value, target_dt):
                    st.success(f"✅ Job '{job_name}' created successfully!")
                    
                    # Display schedule
                    job = st.session_state.jobs[-1]
                    st.subheader("Job Schedule")
                    
                    schedule_data = []
                    for idx, task in enumerate(job['schedule']):
                        schedule_data.append({
                            'Stage': idx + 1,
                            'Process': task['process'],
                            'Start': task['start'].strftime('%Y-%m-%d %H:%M'),
                            'End': task['end'].strftime('%Y-%m-%d %H:%M'),
                            'Duration (hrs)': f"{task['duration']:.2f}"
                        })
                    
                    st.dataframe(pd.DataFrame(schedule_data), use_container_width=True, hide_index=True)
                    
                    total_time = job['schedule'][-1]['end'] - job['schedule'][0]['start']
                    total_hours = total_time.total_seconds() / 3600
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Duration", f"{total_hours:.1f} hours")
                    with col2:
                        st.metric("Expected Finish", job['schedule'][-1]['end'].strftime('%m/%d %H:%M'))
                    with col3:
                        st.metric(f"Revenue ({CURRENCY})", f"{contract_value:,.0f}")
                else:
                    st.error("❌ Failed to save job to database.")

# ==================== TAB 3: GANTT VIEW ====================
with tab3:
    st.header("Sequential Job Flow - Gantt Chart")
    
    filtered_jobs = [j for j in st.session_state.jobs if selected_rep == "All" or j['sales_rep'] == selected_rep]
    
    if not filtered_jobs:
        st.info("No jobs to visualize. Create a job first.")
    else:
        job_names = [j['name'] for j in filtered_jobs]
        selected_job_name = st.selectbox("Select Job", job_names)
        
        selected_job = next((j for j in filtered_jobs if j['name'] == selected_job_name), None)
        
        if selected_job:
            st.subheader(f"Job Flow: {selected_job['name']}")
            
            # Create Gantt chart
            fig = go.Figure()
            
            colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2']
            
            for idx, task in enumerate(selected_job['schedule']):
                color = colors[idx % len(colors)]
                fig.add_trace(go.Bar(
                    x=[task['duration']],
                    y=[task['process']],
                    orientation='h',
                    name=task['process'],
                    marker=dict(color=color),
                    base=task['start'],
                    hovertemplate=f"<b>{task['process']}</b><br>Start: %{{x[0]|%Y-%m-%d %H:%M}}<br>End: %{{x[1]|%Y-%m-%d %H:%M}}<extra></extra>"
                ))
            
            # Add target deadline if set
            if selected_job['target_deadline']:
                fig.add_vline(
                    x=selected_job['target_deadline'],
                    line_dash="dash",
                    line_color="red",
                    annotation_text="Target Deadline"
                )
            
            fig.update_layout(
                title=f"Sequential Flow: {selected_job['name']} ({selected_job['impressions']:,} impressions)",
                xaxis_title="Timeline",
                yaxis_title="Process",
                height=500,
                barmode='overlay',
                showlegend=False
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Schedule details
            st.subheader("Schedule Details")
            schedule_df = pd.DataFrame([
                {
                    'Process': t['process'],
                    'Start': t['start'].strftime('%Y-%m-%d %H:%M'),
                    'End': t['end'].strftime('%Y-%m-%d %H:%M'),
                    'Duration (hrs)': f"{t['duration']:.2f}"
                }
                for t in selected_job['schedule']
            ])
            
            st.dataframe(schedule_df, use_container_width=True, hide_index=True)
            
            # Summary metrics
            total_duration = selected_job['schedule'][-1]['end'] - selected_job['schedule'][0]['start']
            total_hours = total_duration.total_seconds() / 3600
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Duration", f"{total_hours:.1f}h")
            with col2:
                st.metric("Stages", len(selected_job['schedule']))
            with col3:
                st.metric("Expected Finish", selected_job['schedule'][-1]['end'].strftime('%m/%d %H:%M'))
            with col4:
                if selected_job['target_deadline']:
                    status = "✅ On-Time" if selected_job['schedule'][-1]['end'] <= selected_job['target_deadline'] else "❌ Late"
                    st.metric("Deadline Status", status)

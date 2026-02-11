import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import math
import os
from supabase import create_client, Client

# Initialize Supabase client
SUPABASE_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")

supabase_client: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        st.warning(f"Supabase connection issue: {e}. Using session state only.")

# Page configuration
st.set_page_config(
    page_title="Appointed Time Printing - Job Planning",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Machine data with impressions per hour (rate)
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

# Initialize session state
if 'jobs' not in st.session_state:
    st.session_state.jobs = []
if 'monthly_budget' not in st.session_state:
    st.session_state.monthly_budget = 150000
if 'machine_load' not in st.session_state:
    st.session_state.machine_load = {machine: [] for machine in MACHINE_DATA.keys()}
if 'supabase_loaded' not in st.session_state:
    st.session_state.supabase_loaded = False

# Load jobs from Supabase on first run
if supabase_client and not st.session_state.supabase_loaded:
    try:
        jobs_from_db = load_jobs_from_supabase()
        st.session_state.jobs = jobs_from_db
        
        # Rebuild machine load from loaded jobs
        for job in st.session_state.jobs:
            for task in job['schedule']:
                process = task['process']
                st.session_state.machine_load[process].append({
                    'job': job['name'],
                    'impressions': job['impressions'],
                    'start': task['start'],
                    'end': task['end'],
                    'duration': task['duration']
                })
        
        st.session_state.supabase_loaded = True
    except Exception as e:
        st.warning(f"Could not load from Supabase: {e}")
        st.session_state.supabase_loaded = True

# Helper functions
def calculate_impressions(finished_qty, ups, overs_pct):
    """Calculate total impressions using formula: ceil(Qty/Ups) × (1 + Overs%)"""
    base_impressions = math.ceil(finished_qty / ups)
    total_impressions = base_impressions * (1 + overs_pct / 100)
    return total_impressions

def calculate_processing_time(machine, impressions):
    """Calculate total time = setup (2h) + run time"""
    if machine not in MACHINE_DATA:
        return 0
    rate = MACHINE_DATA[machine]['rate']
    run_time = impressions / rate
    return SETUP_HOURS + run_time

def calculate_job_schedule(job_name, impressions, processes, start_time=None):
    """Calculate sequential schedule: each step starts when previous finishes"""
    if start_time is None:
        start_time = datetime.now()
    
    schedule = []
    current_time = start_time
    
    for process in processes:
        if process not in MACHINE_DATA:
            continue
        
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

def save_job_to_supabase(job_name, sales_rep, impressions, finished_qty, ups_per_sheet, sheets_per_packet, overs_pct, processes, contract_value, target_deadline, schedule):
    """Save job and its processes to Supabase"""
    if not supabase_client:
        return None
    
    try:
        # Insert job
        job_data = {
            'name': job_name,
            'sales_rep': sales_rep,
            'impressions': int(impressions),
            'finished_qty': finished_qty,
            'ups_per_sheet': ups_per_sheet,
            'sheets_per_packet': sheets_per_packet,
            'overs_pct': float(overs_pct),
            'contract_value': float(contract_value),
            'target_deadline': target_deadline.isoformat() if target_deadline else None,
            'created_at': datetime.now().isoformat()
        }
        
        response = supabase_client.table('jobs').insert(job_data).execute()
        job_id = response.data[0]['id'] if response.data else None
        
        if job_id:
            # Insert job processes
            for idx, process in enumerate(processes):
                task = schedule[idx]
                process_data = {
                    'job_id': job_id,
                    'process_name': process,
                    'sequence_order': idx + 1,
                    'start_time': task['start'].isoformat(),
                    'end_time': task['end'].isoformat(),
                    'duration_hours': float(task['duration'])
                }
                supabase_client.table('job_processes').insert(process_data).execute()
        
        return job_id
    except Exception as e:
        st.warning(f"Error saving to Supabase: {e}")
        return None

def load_jobs_from_supabase():
    """Load all jobs from Supabase"""
    if not supabase_client:
        return []
    
    try:
        response = supabase_client.table('jobs').select('*').execute()
        jobs = []
        
        for job_record in response.data:
            # Load processes for this job
            processes_response = supabase_client.table('job_processes').select('*').eq('job_id', job_record['id']).execute()
            
            processes = [p['process_name'] for p in sorted(processes_response.data, key=lambda x: x['sequence_order'])]
            
            schedule = []
            for p in sorted(processes_response.data, key=lambda x: x['sequence_order']):
                schedule.append({
                    'process': p['process_name'],
                    'start': datetime.fromisoformat(p['start_time']),
                    'end': datetime.fromisoformat(p['end_time']),
                    'duration': p['duration_hours'],
                    'impressions': job_record['impressions']
                })
            
            calculated_finish = schedule[-1]['end'] if schedule else datetime.fromisoformat(job_record['created_at'])
            target_deadline = datetime.fromisoformat(job_record['target_deadline']) if job_record['target_deadline'] else None
            on_time = True if target_deadline is None else calculated_finish <= target_deadline
            
            job = {
                'name': job_record['name'],
                'sales_rep': job_record['sales_rep'],
                'impressions': job_record['impressions'],
                'processes': processes,
                'contract_value': job_record['contract_value'],
                'schedule': schedule,
                'target_deadline': target_deadline,
                'calculated_finish': calculated_finish,
                'on_time': on_time,
                'created_at': datetime.fromisoformat(job_record['created_at'])
            }
            jobs.append(job)
        
        return jobs
    except Exception as e:
        st.warning(f"Error loading jobs from Supabase: {e}")
        return []

def add_job(job_name, sales_rep, impressions, processes, contract_value, target_deadline=None, finished_qty=None, ups_per_sheet=None, sheets_per_packet=None, overs_pct=None):
    """Add a new job to the system (both local and Supabase)"""
    schedule = calculate_job_schedule(job_name, impressions, processes)
    
    calculated_finish = schedule[-1]['end'] if schedule else datetime.now()
    on_time = True if target_deadline is None else calculated_finish <= target_deadline
    
    job = {
        'name': job_name,
        'sales_rep': sales_rep,
        'impressions': impressions,
        'processes': processes,
        'contract_value': contract_value,
        'schedule': schedule,
        'target_deadline': target_deadline,
        'calculated_finish': calculated_finish,
        'on_time': on_time,
        'created_at': datetime.now()
    }
    
    st.session_state.jobs.append(job)
    
    # Save to Supabase if available
    if supabase_client:
        save_job_to_supabase(
            job_name, sales_rep, impressions, finished_qty or 0, ups_per_sheet or 0, sheets_per_packet or 0, overs_pct or 5.0,
            processes, contract_value, target_deadline, schedule
        )
    
    # Update machine load
    for task in schedule:
        process = task['process']
        st.session_state.machine_load[process].append({
            'job': job_name,
            'impressions': impressions,
            'start': task['start'],
            'end': task['end'],
            'duration': task['duration']
        })
    
    return job

def get_machine_status_color(machine):
    """Determine stoplight color based on machine load:
    Green: 0 hours
    Yellow: 0 < load < 2 hours
    Red: load >= 24 hours
    """
    total_load = 0
    for job_load in st.session_state.machine_load[machine]:
        total_load += job_load['duration']
    
    if total_load == 0:
        return "Green", "🟢"
    elif total_load < 2:
        return "Yellow", "🟡"
    else:
        return "Red", "🔴"

# Sidebar navigation
st.sidebar.title("Appointed Time Printing")
st.sidebar.markdown("---")

page = st.sidebar.radio("Navigate", ["Dashboard", "Plan Job", "Gantt View"])

# Dynamic sales rep filter
sales_reps = sorted(list(set([job['sales_rep'] for job in st.session_state.jobs])))
if page in ["Dashboard", "Gantt View"]:
    selected_rep = st.sidebar.selectbox(
        "Filter by Sales Rep",
        ["All"] + sales_reps if sales_reps else ["All"]
    )
else:
    selected_rep = "All"

st.sidebar.markdown("---")

# Monthly budget configuration
st.sidebar.markdown("### Financial Setup")
monthly_budget = st.sidebar.number_input(
    "Monthly Budget Target ($)",
    value=st.session_state.monthly_budget,
    min_value=10000,
    step=10000
)
st.session_state.monthly_budget = monthly_budget

# PAGE 1: DASHBOARD
if page == "Dashboard":
    st.title("Global Production View")
    st.markdown("Real-time machine status and production analytics")
    
    # Financial summary
    total_revenue = sum(job['contract_value'] for job in st.session_state.jobs)
    revenue_gap = st.session_state.monthly_budget - total_revenue
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "Projected Revenue",
            f"${total_revenue:,.0f}",
            delta=f"${revenue_gap:,.0f} gap",
            delta_color="inverse"
        )
    with col2:
        st.metric("Budget Target", f"${st.session_state.monthly_budget:,.0f}")
    with col3:
        pct_of_budget = (total_revenue / st.session_state.monthly_budget * 100) if st.session_state.monthly_budget > 0 else 0
        st.metric("Budget %", f"{pct_of_budget:.1f}%")
    
    st.markdown("---")
    
    # On-Time Delivery %
    if st.session_state.jobs:
        on_time_jobs = sum(1 for job in st.session_state.jobs if job['on_time'])
        total_jobs = len(st.session_state.jobs)
        otd = (on_time_jobs / total_jobs * 100)
        
        st.metric("On-Time Delivery %", f"{otd:.1f}%")
    
    st.markdown("---")
    
    # Stoplight System - Machine Status Table
    st.markdown("### Stoplight System - Machine Status")
    
    stoplight_data = []
    for machine in sorted(MACHINE_DATA.keys()):
        status_color, symbol = get_machine_status_color(machine)
        
        total_load = sum(job['duration'] for job in st.session_state.machine_load[machine])
        job_count = len(st.session_state.machine_load[machine])
        
        stoplight_data.append({
            'Status': f"{symbol} {status_color}",
            'Machine': machine,
            'Rate (imp/hr)': MACHINE_DATA[machine]['rate'],
            'Load (hours)': f"{total_load:.1f}",
            'Jobs': job_count
        })
    
    df_stoplight = pd.DataFrame(stoplight_data)
    st.dataframe(df_stoplight, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # Production table
    if st.session_state.jobs:
        st.markdown("### Production Schedule")
        
        jobs_to_display = st.session_state.jobs
        if selected_rep != "All":
            jobs_to_display = [job for job in st.session_state.jobs if job['sales_rep'] == selected_rep]
        
        if jobs_to_display:
            production_data = []
            for job in jobs_to_display:
                status = "✅ On-Time" if job['on_time'] else "❌ Late"
                production_data.append({
                    'Job Name': job['name'],
                    'Sales Rep': job['sales_rep'],
                    'Start': job['schedule'][0]['start'].strftime('%m/%d %H:%M') if job['schedule'] else 'N/A',
                    'Realistic Finish': job['calculated_finish'].strftime('%m/%d %H:%M'),
                    'Status': status,
                    'Revenue': f"${job['contract_value']:,.0f}"
                })
            
            st.dataframe(pd.DataFrame(production_data), use_container_width=True, hide_index=True)

# PAGE 2: PLAN JOB
elif page == "Plan Job":
    st.title("Plan New Job")
    st.markdown("Create a job with skillet math and scheduling")
    
    with st.form("job_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            job_name = st.text_input("Job Name", placeholder="e.g., Acme Corp Brochures")
            sales_rep = st.selectbox(
                "Sales Rep",
                ["John Smith", "Sarah Johnson", "Mike Davis", "Emma Wilson", "Other"]
            )
            if sales_rep == "Other":
                sales_rep = st.text_input("Enter Sales Rep Name")
        
        with col2:
            contract_value = st.number_input("Contract Value ($)", min_value=100, value=5000, step=100)
            target_deadline = st.date_input("Target Delivery Date (Optional)", value=None)
        
        st.markdown("---")
        st.markdown("### Skillet Math Calculation")
        st.markdown("**Formula:** Impressions = ⌈Quantity ÷ Ups⌉ × (1 + Overs%)")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            finished_qty = st.number_input("Finished Quantity", min_value=100, value=100000, step=1000)
        with col2:
            ups = st.number_input("Ups-per-Sheet", min_value=1, value=12, step=1)
        with col3:
            overs_pct = st.number_input("Overs %", min_value=0.0, value=5.0, step=0.5)
        with col4:
            st.write("")  # Spacer
        
        # Calculate impressions
        impressions = calculate_impressions(finished_qty, ups, overs_pct)
        st.info(f"**Calculated Impressions:** {impressions:,.0f}")
        
        st.markdown("---")
        st.markdown("### Production Sequence")
        
        available_processes = sorted(list(MACHINE_DATA.keys()))
        selected_processes = []
        
        cols = st.columns(3)
        for idx, process in enumerate(available_processes):
            col = cols[idx % 3]
            if col.checkbox(process):
                selected_processes.append(process)
        
        submitted = st.form_submit_button("Create Job & Schedule", use_container_width=True)
        
        if submitted:
            if not job_name or not sales_rep or not selected_processes:
                st.error("Please fill in all fields and select at least one process")
            else:
                target_dt = None
                if target_deadline:
                    target_dt = datetime.combine(target_deadline, datetime.min.time())
                
                job = add_job(job_name, sales_rep, impressions, selected_processes, contract_value, target_dt, finished_qty, ups, st.session_state.get('sheets_per_packet', 100), overs_pct)
                st.success(f"Job '{job_name}' created!")
                
                # Display schedule
                st.markdown("### Job Schedule")
                schedule_data = []
                for idx, task in enumerate(job['schedule']):
                    schedule_data.append({
                        'Step': idx + 1,
                        'Process': task['process'],
                        'Start': task['start'].strftime('%Y-%m-%d %H:%M'),
                        'Finish': task['end'].strftime('%Y-%m-%d %H:%M'),
                        'Duration (hours)': f"{task['duration']:.2f}"
                    })
                
                st.dataframe(pd.DataFrame(schedule_data), use_container_width=True, hide_index=True)
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    total_time = sum(t['duration'] for t in job['schedule'])
                    st.metric("Total Time", f"{total_time:.2f}h")
                with col2:
                    st.metric("Calculated Finish", job['calculated_finish'].strftime('%m/%d %H:%M'))
                with col3:
                    st.metric("Contract Value", f"${job['contract_value']:,.0f}")
                with col4:
                    status = "✅ On-Time" if job['on_time'] else "❌ Late"
                    st.metric("Deadline Status", status)

# PAGE 3: GANTT VIEW
elif page == "Gantt View":
    st.title("Gantt Chart - Job Visualization")
    st.markdown("Interactive timeline of job flow through machines")
    
    if not st.session_state.jobs:
        st.warning("No jobs created yet. Go to 'Plan Job' to create a job.")
    else:
        jobs_to_display = st.session_state.jobs
        if selected_rep != "All":
            jobs_to_display = [job for job in st.session_state.jobs if job['sales_rep'] == selected_rep]
        
        if not jobs_to_display:
            st.info(f"No jobs for {selected_rep}")
        else:
            job_names = [job['name'] for job in jobs_to_display]
            selected_job_name = st.selectbox("Select Job", job_names)
            
            selected_job = next((job for job in jobs_to_display if job['name'] == selected_job_name), None)
            
            if selected_job:
                # Gantt chart
                fig = go.Figure()
                
                colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
                
                for idx, task in enumerate(selected_job['schedule']):
                    color = colors[idx % len(colors)]
                    fig.add_trace(go.Bar(
                        x=[task['duration']],
                        y=[task['process']],
                        orientation='h',
                        name=task['process'],
                        marker=dict(color=color),
                        base=task['start'],
                        hovertemplate=f"<b>{task['process']}</b><br>Start: %{{base|%Y-%m-%d %H:%M}}<br>Duration: {task['duration']:.2f}h<extra></extra>"
                    ))
                
                # Add target deadline line if present
                if selected_job['target_deadline']:
                    fig.add_vline(
                        x=selected_job['target_deadline'],
                        line_dash="dash",
                        line_color="red",
                        annotation_text="Target",
                        annotation_position="top right"
                    )
                
                fig.update_layout(
                    title=f"{selected_job['name']} - Finish: {selected_job['calculated_finish'].strftime('%Y-%m-%d %H:%M')}",
                    xaxis_title="Timeline",
                    yaxis_title="Process",
                    barmode='overlay',
                    height=500,
                    showlegend=False,
                    hovermode='closest'
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Job details
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Job Name", selected_job['name'][:20])
                with col2:
                    st.metric("Sales Rep", selected_job['sales_rep'])
                with col3:
                    st.metric("Impressions", f"{selected_job['impressions']:,.0f}")
                with col4:
                    st.metric("Revenue", f"${selected_job['contract_value']:,.0f}")

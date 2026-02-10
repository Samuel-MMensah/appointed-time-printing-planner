import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json

# Page configuration
st.set_page_config(
    page_title="Appointed Time Printing - Job Planning",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Machine data with performance parameters
MACHINE_DATA = {
    'SM102-CX FOUR COLOUR': {'rate_per_hour': 8000, 'setup_hours': 1.5},
    'SM102-P FIVE COLOUR': {'rate_per_hour': 7500, 'setup_hours': 1.5},
    'SM 52': {'rate_per_hour': 7000, 'setup_hours': 1.5},
    'GTO 52 SEMI-AUTO-2 COLOUR': {'rate_per_hour': 4500, 'setup_hours': 1.5},
    'GTO 52 MANUAL-2 COLOUR': {'rate_per_hour': 4000, 'setup_hours': 2.0},
    'FOLDING UNIT CONTINUOUS FOLD': {'rate_per_hour': 8000, 'setup_hours': 1.5},
    'MBO-B30E SINGLE FOLD': {'rate_per_hour': 16000, 'setup_hours': 1.5},
    'POLAR MACHINE FOR BOOKS': {'rate_per_hour': 2000, 'setup_hours': 1.0},
    'POLAR MACHINE FOR SHEETS': {'rate_per_hour': 50000, 'setup_hours': 1.0},
    '3 WAY TRIMMER': {'rate_per_hour': 5000, 'setup_hours': 1.0},
    'PERFECT BINDING': {'rate_per_hour': 500, 'setup_hours': 1.5},
    'LAMINATION UNIT': {'rate_per_hour': 2500, 'setup_hours': 1.5},
    'PEDDLER SADDLE STITCH': {'rate_per_hour': 1000, 'setup_hours': 1.5},
    'DIE CUTTER': {'rate_per_hour': 3000, 'setup_hours': 1.5},
    'FOLDER GLUER': {'rate_per_hour': 12000, 'setup_hours': 1.5},
}

# Initialize session state
if 'jobs' not in st.session_state:
    st.session_state.jobs = []
if 'machine_load' not in st.session_state:
    st.session_state.machine_load = {machine: [] for machine in MACHINE_DATA.keys()}

# Helper functions
def calculate_processing_time(machine, impressions):
    """Calculate total processing time in hours (setup + run time)"""
    if machine not in MACHINE_DATA:
        return 0
    data = MACHINE_DATA[machine]
    setup_time = data['setup_hours']
    run_time = impressions / data['rate_per_hour']
    return setup_time + run_time

def get_machine_status(machine, current_time):
    """Determine machine status: Green (Available), Yellow (<2 hours), Red (>24 hours)"""
    total_load = sum(MACHINE_DATA[machine]['setup_hours'] + 
                     job['impressions'] / MACHINE_DATA[machine]['rate_per_hour']
                     for job in st.session_state.machine_load[machine])
    
    if total_load == 0:
        return "🟢 Available", "green"
    elif total_load < 2:
        return "🟡 Finishing Soon (<2h)", "orange"
    else:
        return "🔴 Booked (>24h)", "red"

def calculate_job_schedule(job_name, sales_rep, impressions, processes, start_time=None):
    """Calculate the complete schedule for a job through all processes"""
    if start_time is None:
        start_time = datetime.now()
    
    schedule = []
    current_time = start_time
    
    for process in processes:
        if process not in MACHINE_DATA:
            st.warning(f"Process '{process}' not found in machine data")
            continue
        
        duration = calculate_processing_time(process, impressions)
        end_time = current_time + timedelta(hours=duration)
        
        schedule.append({
            'job': job_name,
            'process': process,
            'start': current_time,
            'end': end_time,
            'duration': duration,
            'impressions': impressions
        })
        
        current_time = end_time
    
    return schedule

def add_job(job_name, sales_rep, impressions, processes):
    """Add a new job to the system"""
    schedule = calculate_job_schedule(job_name, sales_rep, impressions, processes)
    
    job = {
        'name': job_name,
        'sales_rep': sales_rep,
        'impressions': impressions,
        'processes': processes,
        'schedule': schedule,
        'created_at': datetime.now()
    }
    
    st.session_state.jobs.append(job)
    
    # Update machine load
    for task in schedule:
        process = task['process']
        st.session_state.machine_load[process].append({
            'job': job_name,
            'impressions': impressions,
            'start': task['start'],
            'end': task['end']
        })
    
    return job

# Sidebar navigation
st.sidebar.title("📋 Appointed Time Printing")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigate",
    ["Dashboard", "Plan Job", "Gantt View"]
)

# Filter by sales rep in sidebar
if page in ["Dashboard", "Gantt View"]:
    sales_reps = list(set([job['sales_rep'] for job in st.session_state.jobs]))
    if sales_reps:
        selected_rep = st.sidebar.selectbox("Filter by Sales Rep", ["All"] + sales_reps)
    else:
        selected_rep = "All"
        st.sidebar.info("No jobs created yet.")
else:
    selected_rep = "All"

st.sidebar.markdown("---")

# PAGE 1: DASHBOARD - Global Production View
if page == "Dashboard":
    st.title("🏭 Global Production View - Stoplight System")
    st.markdown("Real-time machine status and production overview")
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        st.metric("Total Jobs", len(st.session_state.jobs))
    with col2:
        st.metric("Active Machines", len([m for m in MACHINE_DATA.keys() if any(st.session_state.machine_load[m])]))
    with col3:
        st.metric("Total Impressions", sum(job['impressions'] for job in st.session_state.jobs))
    
    st.markdown("### Machine Status Overview")
    
    # Create dashboard data
    dashboard_data = []
    for machine in sorted(MACHINE_DATA.keys()):
        status, color = get_machine_status(machine, datetime.now())
        
        # Calculate total load hours
        total_load = 0
        for job in st.session_state.machine_load[machine]:
            total_load += MACHINE_DATA[machine]['setup_hours'] + job['impressions'] / MACHINE_DATA[machine]['rate_per_hour']
        
        dashboard_data.append({
            'Machine': machine,
            'Status': status,
            'Load (hours)': f"{total_load:.2f}",
            'Rate (imp/hr)': MACHINE_DATA[machine]['rate_per_hour']
        })
    
    df_dashboard = pd.DataFrame(dashboard_data)
    
    # Display with color coding
    st.dataframe(df_dashboard, use_container_width=True, hide_index=True)
    
    # Jobs filtered by sales rep
    if st.session_state.jobs:
        st.markdown("### Recent Jobs")
        
        jobs_to_display = st.session_state.jobs
        if selected_rep != "All":
            jobs_to_display = [job for job in st.session_state.jobs if job['sales_rep'] == selected_rep]
        
        if jobs_to_display:
            jobs_df_data = []
            for job in jobs_to_display:
                jobs_df_data.append({
                    'Job Name': job['name'],
                    'Sales Rep': job['sales_rep'],
                    'Impressions': job['impressions'],
                    'Processes': ', '.join(job['processes']),
                    'Start Time': job['schedule'][0]['start'].strftime('%Y-%m-%d %H:%M'),
                    'End Time': job['schedule'][-1]['end'].strftime('%Y-%m-%d %H:%M')
                })
            
            st.dataframe(pd.DataFrame(jobs_df_data), use_container_width=True, hide_index=True)
        else:
            st.info(f"No jobs for {selected_rep}")

# PAGE 2: PLAN JOB - Job Routing Engine
elif page == "Plan Job":
    st.title("📝 Plan New Job - Routing Engine")
    st.markdown("Configure job parameters and calculate processing schedule")
    
    with st.form("job_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            job_name = st.text_input("Job Name", placeholder="e.g., Client A - Brochure Run 2025")
            impressions = st.number_input("Impressions Required", min_value=100, value=5000, step=100)
        
        with col2:
            sales_rep = st.selectbox("Sales Rep Name", 
                                     ["John Smith", "Sarah Johnson", "Mike Davis", "Emma Wilson", "Other"],
                                     key="sales_rep_select")
            if sales_rep == "Other":
                sales_rep = st.text_input("Enter Sales Rep Name")
        
        st.markdown("### Production Sequence")
        st.markdown("Select the sequence of processes this job will go through:")
        
        available_processes = list(MACHINE_DATA.keys())
        selected_processes = []
        
        # Create columns for process selection
        cols = st.columns(3)
        for idx, process in enumerate(sorted(available_processes)):
            col = cols[idx % 3]
            if col.checkbox(process):
                selected_processes.append(process)
        
        submitted = st.form_submit_button("✅ Create Job & Schedule", use_container_width=True)
        
        if submitted:
            if not job_name or not sales_rep or not selected_processes:
                st.error("Please fill in all required fields and select at least one process")
            else:
                job = add_job(job_name, sales_rep, impressions, selected_processes)
                st.success(f"✅ Job '{job_name}' created successfully!")
                
                # Display job schedule
                st.markdown("### Job Schedule")
                schedule_data = []
                total_time = 0
                
                for task in job['schedule']:
                    duration = task['duration']
                    total_time += duration
                    schedule_data.append({
                        'Process': task['process'],
                        'Start': task['start'].strftime('%Y-%m-%d %H:%M'),
                        'End': task['end'].strftime('%Y-%m-%d %H:%M'),
                        'Duration (hours)': f"{duration:.2f}"
                    })
                
                st.dataframe(pd.DataFrame(schedule_data), use_container_width=True, hide_index=True)
                st.info(f"**Total Processing Time:** {total_time:.2f} hours")

# PAGE 3: GANTT VIEW - Sequential Gantt Chart
elif page == "Gantt View":
    st.title("📊 Gantt Chart - Job Flow Visualization")
    st.markdown("Interactive timeline visualization of job progression through machines")
    
    if not st.session_state.jobs:
        st.warning("No jobs created yet. Go to 'Plan Job' to create a job.")
    else:
        # Filter jobs by sales rep
        jobs_to_display = st.session_state.jobs
        if selected_rep != "All":
            jobs_to_display = [job for job in st.session_state.jobs if job['sales_rep'] == selected_rep]
        
        if not jobs_to_display:
            st.info(f"No jobs for {selected_rep}")
        else:
            # Job selection
            job_names = [job['name'] for job in jobs_to_display]
            selected_job_name = st.selectbox("Select Job to Visualize", job_names)
            
            # Find selected job
            selected_job = next((job for job in jobs_to_display if job['name'] == selected_job_name), None)
            
            if selected_job:
                # Display editable schedule table
                st.markdown("### Job Schedule (Adjustable Start Times)")
                
                schedule_data = []
                for idx, task in enumerate(selected_job['schedule']):
                    schedule_data.append({
                        'Process': task['process'],
                        'Start': task['start'],
                        'Duration (hours)': task['duration']
                    })
                
                df_schedule = pd.DataFrame(schedule_data)
                edited_df = st.data_editor(
                    df_schedule,
                    use_container_width=True,
                    hide_index=True,
                    key="schedule_editor"
                )
                
                # Recalculate schedule if start times changed
                if st.button("🔄 Update Schedule"):
                    # Update job schedule based on edited values
                    current_time = None
                    updated_schedule = []
                    
                    for idx, row in edited_df.iterrows():
                        if idx == 0:
                            current_time = row['Start']
                        else:
                            current_time = updated_schedule[idx-1]['end']
                        
                        duration = row['Duration (hours)']
                        end_time = current_time + timedelta(hours=duration)
                        
                        updated_schedule.append({
                            'job': selected_job['name'],
                            'process': row['Process'],
                            'start': current_time,
                            'end': end_time,
                            'duration': duration,
                            'impressions': selected_job['impressions']
                        })
                    
                    selected_job['schedule'] = updated_schedule
                    st.success("✅ Schedule updated with ripple effect!")
                
                # Create Gantt chart
                st.markdown("### Timeline Visualization")
                
                fig = go.Figure()
                
                # Add tasks to Gantt chart
                for task in selected_job['schedule']:
                    fig.add_trace(go.Scatter(
                        x=[task['start'], task['end']],
                        y=[task['process'], task['process']],
                        mode='lines+markers',
                        name=task['process'],
                        line=dict(width=20),
                        hovertemplate=f"<b>{task['process']}</b><br>" +
                                      "Start: %{x[0]|%Y-%m-%d %H:%M}<br>" +
                                      "End: %{x[1]|%Y-%m-%d %H:%M}<br>" +
                                      f"Duration: {task['duration']:.2f}h<extra></extra>"
                    ))
                
                fig.update_layout(
                    title=f"Job Flow: {selected_job['name']} ({selected_job['impressions']:,} impressions)",
                    xaxis_title="Timeline",
                    yaxis_title="Process/Machine",
                    hovermode='closest',
                    height=500,
                    xaxis=dict(type='date'),
                    showlegend=False
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Summary statistics
                col1, col2, col3, col4 = st.columns(4)
                
                total_time = selected_job['schedule'][-1]['end'] - selected_job['schedule'][0]['start']
                total_hours = total_time.total_seconds() / 3600
                
                with col1:
                    st.metric("Total Duration", f"{total_hours:.2f}h")
                with col2:
                    st.metric("Stages", len(selected_job['schedule']))
                with col3:
                    st.metric("Sales Rep", selected_job['sales_rep'])
                with col4:
                    st.metric("Impressions", f"{selected_job['impressions']:,}")

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #888;'>"
    "Appointed Time Printing - Job Planning & Simulation System<br>"
    "Production Ready | Data-Driven Scheduling"
    "</div>",
    unsafe_allow_html=True
)

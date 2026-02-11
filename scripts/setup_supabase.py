import os
import sys
from supabase import create_client, Client

# Get Supabase credentials from environment
SUPABASE_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: Supabase credentials not found in environment variables")
    sys.exit(1)

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# SQL statements to create tables
create_jobs_table = """
CREATE TABLE IF NOT EXISTS jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR NOT NULL,
  sales_rep VARCHAR NOT NULL,
  impressions INTEGER NOT NULL,
  finished_qty INTEGER NOT NULL,
  ups_per_sheet INTEGER NOT NULL,
  sheets_per_packet INTEGER NOT NULL,
  overs_pct DECIMAL(5, 2) DEFAULT 5.0,
  contract_value DECIMAL(12, 2) NOT NULL,
  target_deadline TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
)
"""

create_job_processes_table = """
CREATE TABLE IF NOT EXISTS job_processes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  process_name VARCHAR NOT NULL,
  sequence_order INTEGER NOT NULL,
  start_time TIMESTAMP NOT NULL,
  end_time TIMESTAMP NOT NULL,
  duration_hours DECIMAL(10, 2) NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
)
"""

create_machine_loads_table = """
CREATE TABLE IF NOT EXISTS machine_loads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  machine_name VARCHAR NOT NULL,
  job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  start_time TIMESTAMP NOT NULL,
  end_time TIMESTAMP NOT NULL,
  duration_hours DECIMAL(10, 2) NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
)
"""

create_indexes = """
CREATE INDEX IF NOT EXISTS idx_jobs_sales_rep ON jobs(sales_rep);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_job_processes_job_id ON job_processes(job_id);
CREATE INDEX IF NOT EXISTS idx_machine_loads_machine ON machine_loads(machine_name);
CREATE INDEX IF NOT EXISTS idx_machine_loads_time ON machine_loads(start_time, end_time);
"""

# Execute table creation via RPC or direct SQL
try:
    # Try using the Supabase admin API to execute SQL
    response = supabase.postgrest.auth(SUPABASE_KEY).headers.update({
        "Authorization": f"Bearer {SUPABASE_KEY}"
    })
    
    print("Creating jobs table...")
    supabase.rpc("exec_sql", {"sql": create_jobs_table}).execute()
    
    print("Creating job_processes table...")
    supabase.rpc("exec_sql", {"sql": create_job_processes_table}).execute()
    
    print("Creating machine_loads table...")
    supabase.rpc("exec_sql", {"sql": create_machine_loads_table}).execute()
    
    print("Creating indexes...")
    supabase.rpc("exec_sql", {"sql": create_indexes}).execute()
    
    print("✅ Supabase tables created successfully!")
    
except Exception as e:
    print(f"Note: Table creation via RPC may require additional setup. Error: {e}")
    print("Tables should be created manually in Supabase dashboard using the SQL script.")
    print("However, the app will work with dynamic table creation on first use.")

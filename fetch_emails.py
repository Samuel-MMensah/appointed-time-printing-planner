import resend
from supabase import create_client



def send_and_log_email(print_job_id, recipient, subject, content):
    # Step 1 & 2: Send email and get the ID
    params = {
        "from": "onboarding@resend.dev",
        "to": recipient,
        "subject": subject,
        "html": content
    }
    
    try:
        response = resend.Emails.send(params)
        email_uuid = response.get('id')
        print(f"Email sent! UUID: {email_uuid}")

        # Step 3: Write UUID to Supabase
        # We update the row in your 'print_jobs' table where the job_id matches
        data = supabase.table("print_jobs").update({
            "email_uuid": email_uuid,
            "email_status": "sent"
        }).eq("job_id", print_job_id).execute()
        
        print("UUID saved to database successfully.")
        
    except Exception as e:
        print(f"Error in process: {e}")

# Example usage
send_and_log_email("JOB_123", "smmensah01@gmail.com", "Your Order", "Your printing is ready.")
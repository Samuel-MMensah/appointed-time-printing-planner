from __future__ import annotations

import streamlit as st

import streamlit as st
# Assuming your client is initialized in a file named 'db.py'

"""
rbac.py — Role-Based Access Control for the Appointed Time Enterprise Hub.

Source of truth is st.session_state.user_profile — already populated by
app.py's existing hydrate_user_profile() after login via:

    supabase.table('profiles').select('id,full_name,email,phone_number,role')

st.session_state.user_role (as named in the request this module was built
against) did not exist anywhere in app.py before this file — grepped for
zero matches. sync_session_role() below derives it FROM user_profile so
you get the exact key you asked for without creating a second copy of the
same fact that can drift out of sync with user_profile on some future edit.
Call sync_session_role() once per rerun, right after hydrate_user_profile();
current_role() and check_access() work either way, since they fall back to
computing fresh from user_profile if user_role hasn't been synced yet.
"""

# Every role string app.py's inline sidebar gate currently treats as
# elevated access. Copied verbatim from the live `is_admin` check — moving
# app.py over to call is_admin() from this module instead of recomputing
# it inline is a behavior-preserving refactor, not a change, as long as
# this set stays in sync with that one. Consider deleting the inline copy
# in app.py once it imports from here, so there's only one list to update.
ADMIN_ROLES = {"admin", "manager", "supervisor", "md", "fm"}

# profiles.department does not exist in any query app.py currently makes —
# the only 'department' in the whole codebase lives on job_orders
# (PRESS / GARMENT), which is a property of an ORDER, not a USER. If your
# Supabase profiles table has since grown a department column, add it to
# the .select() in hydrate_user_profile() (app.py) and set the mapping
# below; until then, department-scoped access has nothing real to key off
# and check_department() fails closed (denies) rather than guessing.
USER_DEPARTMENT_COLUMN = None  # e.g. "department", once/if it exists


def sync_session_role(supabase_client) -> str:
    """
    Syncs user_role and user_department from the Supabase profile.
    Ensures that session_state is always in sync with the database.
    """
    if not st.session_state.get("authenticated"):
        st.session_state.user_role = "Guest"
        st.session_state.user_department = "NONE"
        return "Guest"

    # Refresh the profile directly from the DB to ensure consistency
    try:
        # Use the passed client, not a global variable
        response = supabase_client.table("profiles") \
            .select("role, department") \
            .eq("email", st.session_state.user_email) \
            .single() \
            .execute()
        
        if response.data:
            profile = response.data
            st.session_state.user_profile = profile
            st.session_state.user_role = (profile.get("role") or "Front Desk").strip()
            st.session_state.user_department = (profile.get("department") or "NONE").strip()
        else:
            # Fallback if profile fetch fails
            st.session_state.user_role = "Front Desk"
            st.session_state.user_department = "NONE"
            
    except Exception as e:
        # Log the error and default to restricted state
        st.error(f"RBAC Sync Error: {e}")
        st.session_state.user_role = "Front Desk"
        st.session_state.user_department = "NONE"

    return st.session_state.user_role

def current_role() -> str:
    """Role for this rerun. Computes fresh via sync if nothing has synced
    yet this session (e.g. this is called before app.py's post-login
    hydration point runs)."""
    return st.session_state.get("user_role") or sync_session_role()


def check_access(required_roles) -> bool:
    """
    True if the current session's role is authorized.

    required_roles: a single role string, or any iterable of role strings
                     (list / set / tuple). Comparison is case-insensitive
                     and whitespace-trimmed, matching the .strip().lower()
                     convention app.py's inline gate already uses.

    Not logged in -> always False, regardless of required_roles — this is
    a hard gate, not a role check, so a signed-out session can never pass
    it no matter what roles are listed as acceptable.

    This does NOT special-case admins to bypass every check. If you want
    "admins can do X too," include ADMIN_ROLES explicitly:
        check_access(ADMIN_ROLES | {"press_lead"})
    An implicit "admin always wins" rule is exactly the kind of hidden
    behavior that's hard to audit later — spelling it out per call site
    costs one extra union and buys you a permission matrix you can
    actually read back and verify.
    """
    if not st.session_state.get("authenticated"):
        return False
    if isinstance(required_roles, str):
        required_roles = {required_roles}
    required_lower = {str(r).strip().lower() for r in required_roles}
    return current_role().strip().lower() in required_lower


def is_admin() -> bool:
    """Drop-in replacement for app.py's inline is_admin computation —
    same ADMIN_ROLES set, same result. The email-substring fallback that
    used to also grant admin to any address merely containing "admin" /
    "manager" / "supervisor" was already removed from app.py in an
    earlier pass; this module does not reintroduce it."""
    return check_access(ADMIN_ROLES)


def check_department(department: str) -> bool:
    """
    Placeholder until USER_DEPARTMENT_COLUMN names a real column.
    Fails closed (returns False) rather than guessing at a field that
    isn't there — a silent True here would let unauthorized staff into a
    department's queue with no error to signal why. Wire this up once you
    confirm the actual column name; see the module docstring.
    """
    if not USER_DEPARTMENT_COLUMN or not st.session_state.get("authenticated"):
        return False
    profile = st.session_state.get("user_profile") or {}
    user_dept = str(profile.get(USER_DEPARTMENT_COLUMN, "")).strip().upper()
    return user_dept == department.strip().upper()
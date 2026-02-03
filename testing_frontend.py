import streamlit as st
import requests
import pandas as pd
import uuid as uuid_lib

# ==========================================
# CONFIGURATION
# ==========================================
API_URL = "http://localhost:8000"

st.set_page_config(page_title="Assessment Platform", layout="wide")

# ==========================================
# SESSION STATE INIT
# ==========================================
if 'token' not in st.session_state:
    st.session_state.token = None
if 'username' not in st.session_state:
    st.session_state.username = None
if 'role' not in st.session_state:
    st.session_state.role = None

# State for Assessment Creation (From 2_Admin.py)
if 'topic_list' not in st.session_state:
    st.session_state.topic_list = [{'topic': '', 'count': 5, 'easy': 33, 'medium': 34, 'hard': 33}]
if 'manual_questions' not in st.session_state:
    st.session_state.manual_questions = []

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def get_auth_headers():
    return {"Authorization": f"Bearer {st.session_state.token}"}

def logout():
    st.session_state.clear()
    st.rerun()

def set_page(page_name):
    st.query_params.page = page_name
    st.rerun()

# Helper functions from 2_Admin.py
def add_topic():
    st.session_state.topic_list.append({'topic': '', 'count': 5, 'easy': 33, 'medium': 34, 'hard': 33})
    st.rerun()

def remove_topic(index):
    if len(st.session_state.topic_list) > 1:
        st.session_state.topic_list.pop(index)
        st.rerun()

def get_assessment_topic_names(assessment):
    """
    Safely extracts all topic names from an assessment object
    and returns them as a comma-separated string.
    """
    topic_data = assessment.get('topic')
    
    # Handle if topic is a list of dictionaries
    if isinstance(topic_data, list) and len(topic_data) > 0:
        names = []
        for t in topic_data:
            if isinstance(t, dict):
                name = t.get('name') or t.get('topic_name')
                if name:
                    names.append(name)
        return ", ".join(names) if names else "No Topics"
    
    # Handle legacy cases where topic might be a string
    elif isinstance(topic_data, str):
        return topic_data
        
    return "No Topics"

def add_manual_question():
    st.session_state.manual_questions.append({
        "text": "", "opt_a": "", "opt_b": "", "opt_c": "", "opt_d": "", 
        "correct": "", "difficulty": "Medium"
    })
    st.rerun()

def remove_manual_question(index):
    st.session_state.manual_questions.pop(index)
    st.rerun()
    
def start_exam(assessment_id, assessment_type):
    st.session_state.exam_id = assessment_id
    st.session_state.exam_type = assessment_type
    st.query_params.exam = "active"
    st.rerun()

def exit_exam():
    # Clear exam specific state
    if 'exam_id' in st.session_state: del st.session_state.exam_id
    if 'exam_type' in st.session_state: del st.session_state.exam_type
    if 'exam_questions' in st.session_state: del st.session_state.exam_questions
    
    # Clear query params
    if 'exam' in st.query_params: del st.query_params.exam
    
    # Forcefully set the page to student
    st.query_params.page = "student"
    
    # Rerun the app to apply changes
    st.rerun()
    
# ==========================================
# PAGE 1: LOGIN / SIGNUP
# ==========================================
def render_auth_page():
    st.title("🔐 Authentication Portal")
    
    # --- LOGIN ---
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
            
        # --- NEW: Role Selection ---
        role = st.radio("I am a:", ["Admin", "Student"], horizontal=True)
            
        submitted = st.form_submit_button("Login")
            
        if submitted:
            try:
                # --- ADMIN LOGIC ---
                if role == "Admin":
                    r = requests.post(f"{API_URL}/admin/login", data={"username": email, "password": password})
                    
                    if r.status_code == 200:
                        st.session_state.token = r.json()['access_token']
                        st.session_state.username = email
                    
                        # Fetch Role to determine page
                        headers = get_auth_headers()
                        user_resp = requests.get(f"{API_URL}/users/me", headers=headers)
                        
                        if user_resp.status_code == 200:
                            user_data = user_resp.json()
                            st.session_state.role = user_data['role']
                        
                        # Redirect to correct dashboard
                            if user_data['role'] == 'super_admin':
                                set_page("super_admin")
                            else:
                                set_page("admin")
                        else:
                            st.error("Failed to retrieve user details")
                    else:
                        st.error(r.text)

                # --- STUDENT LOGIC ---
                elif role == "Student":
                    r = requests.post(f"{API_URL}/student/login", data={"username": email, "password": password})
                        
                    if r.status_code == 200:
                        st.session_state.token = r.json()['access_token']
                        st.session_state.username = email
                            
                        # Fetch Role
                        headers = get_auth_headers()
                        user_resp = requests.get(f"{API_URL}/users/me", headers=headers)
                            
                        if user_resp.status_code == 200:
                            user_data = user_resp.json()
                            st.session_state.role = user_data['role']
                            st.success(f"Logged in as Student")
                            set_page("student")
                        else:
                            st.error("Failed to retrieve student details")
                    else:
                        st.error(r.text)
                            
            except Exception as e:
                st.error(f"Connection Error: {e}")

# ==========================================
# PAGE 2: ADMIN DASHBOARD (UPDATED)
# ==========================================
def render_admin_dashboard():
    col1, col2 = st.columns([5,1])
    with col2:
        st.button("Logout", on_click=logout, type="secondary")

    st.title("🎓 Assessment Admin Dashboard")
    st.markdown(f"**Backend URL:** `{API_URL}`")
    st.caption(f"Welcome, {st.session_state.get('username', 'Admin')}")

    t1, t2, t3, t4, t5 = st.tabs(["Modules", "Clients", "Create Assessment", "View Results", "Manage Students"])

    # ==========================================
    # TAB 1: MODULES
    # ==========================================
    with t1:
        st.header("Manage Modules")
        
        with st.expander("➕ Create New Module"):
            with st.form("create_module_form"):
                m_name = st.text_input("Module Name")
                m_desc = st.text_area("Description")
                if st.form_submit_button("Save Module"):
                    if m_name:
                        payload = {"name": m_name, "description": m_desc}
                        r = requests.post(f"{API_URL}/admin/modules", json=payload)
                        if r.status_code == 201:
                            st.success("Module Created")
                            st.rerun()
                        else: st.error(r.text)
                    else: st.warning("Module Name is required")

        st.subheader("Existing Modules & Assigned Assessments")
        try:
            mods = requests.get(f"{API_URL}/admin/modules").json()
            all_assessments = requests.get(f"{API_URL}/admin/assessments").json()
            
            if not mods: st.info("No modules found.")
            else:
                for m in mods:
                    st.markdown(f"### 📚 {m['name']}")
                    st.caption(m.get('description', 'No description'))
                    assigned_assessments = m.get('assessments', [])
                    assigned_ids = [a['id'] for a in assigned_assessments]
                    
                    if assigned_assessments:
                        st.write("**Assigned Assessments:**")
                        for a in assigned_assessments:
                            # Use Helper to show topics
                            t_name = get_assessment_topic_names(a)
                            
                            col_ass, col_del = st.columns([4, 1])
                            col_ass.caption(f"📝 {t_name} ({a['total_questions']} Qs)")
                            
                            if col_del.button("❌", key=f"rem_ass_{m['id']}_{a['id']}", help="Remove Assessment"):
                                r = requests.post(f"{API_URL}/admin/assessments/{a['id']}/remove-module")
                                if r.status_code == 200:
                                    st.success("Removed")
                                    st.rerun()
                                else: st.error("Failed")
                    else: st.write("No assessments assigned yet.")

                    available_assessments = [a for a in all_assessments if a['id'] not in assigned_ids]
                    
                    if available_assessments:
                        with st.expander(f"Assign Assessment to {m['name']}", expanded=False):
                            
                            # UPDATED FORMAT FUNCTION
                            def format_assessment(opt_id):
                                a = next((x for x in available_assessments if x['id'] == opt_id), None)
                                if a:
                                    # Use the helper to get all topics
                                    topic_names = get_assessment_topic_names(a)
                                    return f"{topic_names} ({a['total_questions']} Qs) - {a['id'].split('-')[0]}"
                                return opt_id

                            sel_ass_id = st.selectbox("Select Assessment", options=[a['id'] for a in available_assessments], format_func=format_assessment, key=f"add_ass_select_{m['id']}")
                            if st.button("Add", key=f"btn_add_ass_{m['id']}"):
                                r = requests.post(f"{API_URL}/admin/modules/{m['id']}/add-assessment", json={"assessment_id": sel_ass_id})
                                if r.status_code == 200:
                                    st.success("Assessment Added")
                                    st.rerun()
                                else: st.error(r.text)
                    else: st.caption("All assessments are already assigned to this module.")

                    if st.button("🗑️ Delete Module", key=f"del_mod_{m['id']}", type="secondary"):
                        requests.delete(f"{API_URL}/admin/modules/{m['id']}")
                        st.rerun()
                    st.markdown("---")
        except Exception as e: st.error(f"Error loading modules: {e}")

    # ==========================================
    # TAB 2: CLIENTS
    # ==========================================
    with t2:
        st.header("Manage Clients")
        with st.expander("➕ Add New Client"):
            with st.form("create_client_form"):
                c_name = st.text_input("Client Name")
                c_email = st.text_input("Contact Email")
                if st.form_submit_button("Add Client"):
                    if c_name:
                        payload = {"name": c_name, "contact_email": c_email}
                        r = requests.post(f"{API_URL}/admin/clients", json=payload)
                        if r.status_code == 201:
                            st.success("Client Added")
                            st.rerun()
                        else: st.error(r.text)
                    else: st.warning("Client Name is required")

        st.subheader("Existing Clients & Assignments")
        try:
            clients = requests.get(f"{API_URL}/admin/clients").json()
            all_modules = requests.get(f"{API_URL}/admin/modules").json()
            
            if not clients: st.info("No clients found.")
            else:
                for c in clients:
                    st.markdown(f"### 👤 {c['name']}")
                    st.caption(c.get('contact_email', 'No email'))
                    assigned_modules = c.get('assigned_modules', [])
                    assigned_module_ids = [m['id'] for m in assigned_modules]
                    
                    if assigned_modules:
                        st.write("**Assigned Modules:**")
                        for i, mod in enumerate(assigned_modules):
                            col_name, col_btn = st.columns([4, 1])
                            col_name.info(mod['name'])
                            if col_btn.button("❌", key=f"unassign_{c['id']}_{mod['id']}", help="Remove Module"):
                                r = requests.post(f"{API_URL}/admin/clients/{c['id']}/unassign", json={"module_id": mod['id']})
                                if r.status_code == 200:
                                    st.success("Module Removed")
                                    st.rerun()
                                else: st.error("Failed to remove module")
                    else: st.write("No modules assigned yet.")
                    
                    st.markdown("---")
                    available_modules = [m for m in all_modules if m['id'] not in assigned_module_ids]
                    if available_modules:
                        with st.expander(f"Assign New Module to {c['name']}", expanded=False):
                            mod_options = {m['id']: m['name'] for m in available_modules}
                            selected_mod_id = st.selectbox("Select Module", options=list(mod_options.keys()), format_func=lambda x: mod_options.get(x), key=f"assign_select_{c['id']}")
                            if st.button("Assign", key=f"btn_assign_{c['id']}"):
                                r = requests.post(f"{API_URL}/admin/clients/{c['id']}/assign", json={"module_id": selected_mod_id})
                                if r.status_code == 200:
                                    st.success("Module Assigned Successfully!")
                                    st.rerun()
                                else: st.error("Failed to assign module.")
                    else: st.caption("All available modules are already assigned to this client.")
                    
                    if st.button("🗑️ Delete Client", key=f"del_cli_{c['id']}", type="secondary"):
                        requests.delete(f"{API_URL}/admin/clients/{c['id']}")
                        st.rerun()
        except Exception as e: st.error(f"Failed to load clients: {e}")

    # ==========================================
    # TAB 3: CREATE ASSESSMENT
    # ==========================================
    with t3:
        st.header("Create New Assessment")
        mode = st.radio("Choose Creation Mode", ["AI Generate", "Manual Create"], horizontal=True)
        st.markdown("---")

        if mode == "AI Generate":
            st.write("**Step 1: Configure Topics**")
            for i, t in enumerate(st.session_state.topic_list):
                c_label, c_btn = st.columns([4, 1])
                c_label.write(f"**Topic {i+1}:** {t['topic'] if t['topic'] else '...'}")
                c_btn.button("❌ Remove", key=f"rem_btn_{i}", on_click=remove_topic, args=(i,))
            st.button("➕ Add Another Topic", on_click=add_topic, type="secondary")
            st.markdown("---")

            with st.form("ai_config_form"):
                payload_topics = []
                for i, t in enumerate(st.session_state.topic_list):
                    with st.expander(f"Configure {t['topic'] if t['topic'] else 'New Topic'}", expanded=i==0):
                        topic_name = st.text_input("Topic Name", value=t['topic'], key=f"tname_{i}")
                        count = st.number_input("Count", value=t['count'], key=f"tcnt_{i}")
                        cols = st.columns(3)
                        easy = cols[0].number_input("Easy %", 0, 100, value=t['easy'], key=f"teasy_{i}")
                        medium = cols[1].number_input("Medium %", 0, 100, value=t['medium'], key=f"tmed_{i}")
                        hard = cols[2].number_input("Hard %", 0, 100, value=t['hard'], key=f"thard_{i}")
                        
                        st.session_state.topic_list[i] = {'topic': topic_name, 'count': count, 'easy': easy, 'medium': medium, 'hard': hard}
                        payload_topics.append({"topic": topic_name, "count": count, "difficulty": {"easy": easy, "medium": medium, "hard": hard}})

                submitted = st.form_submit_button("💾 Save Configuration")
                if submitted:
                    payload = {"topics": payload_topics}
                    r = requests.post(f"{API_URL}/admin/assessments/config", json=payload)
                    if r.status_code == 201:
                        st.success(f"Configuration Saved! ID: `{r.json()['id']}`")
                    else: st.error(r.text)

        elif mode == "Manual Create":
            st.write("**Step 1: Define Assessment Topic**")
            manual_topic = st.text_input("Assessment Topic", placeholder="e.g., History 101")
            st.markdown("---")
            st.write("**Step 2: Add Questions**")
            st.button("➕ Add Question", on_click=add_manual_question, type="secondary")
            
            for i, q in enumerate(st.session_state.manual_questions):
                with st.expander(f"Question {i+1}", expanded=False):
                    c1, c2 = st.columns([5, 1])
                    q_text = c1.text_input("Question Text", value=q['text'], key=f"mq_text_{i}")
                    if c2.button("🗑️", key=f"rem_man_q_{i}"): remove_manual_question(i)
                    c_opt = st.columns(4)
                    opt_a = c_opt[0].text_input("Option A", value=q['opt_a'], key=f"mq_opta_{i}")
                    opt_b = c_opt[1].text_input("Option B", value=q['opt_b'], key=f"mq_optb_{i}")
                    opt_c = c_opt[2].text_input("Option C", value=q['opt_c'], key=f"mq_optc_{i}")
                    opt_d = c_opt[3].text_input("Option D", value=q['opt_d'], key=f"mq_optd_{i}")
                    c_ans = st.columns(2)
                    correct = c_ans[0].selectbox("Correct Answer", ["A", "B", "C", "D"], index=["A", "B", "C", "D"].index(q['correct']) if q['correct'] in ["A", "B", "C", "D"] else 0, key=f"mq_corr_{i}")
                    difficulty = c_ans[1].selectbox("Difficulty", ["Easy", "Medium", "Hard"], index=["Easy", "Medium", "Hard"].index(q['difficulty']) if q['difficulty'] in ["Easy", "Medium", "Hard"] else 1, key=f"mq_diff_{i}")

                    st.session_state.manual_questions[i] = {
                        "text": q_text, "opt_a": opt_a, "opt_b": opt_b, "opt_c": opt_c, "opt_d": opt_d,
                        "correct": correct, "difficulty": difficulty
                    }

            st.markdown("---")
            if st.button("💾 Save Manual Assessment", type="primary"):
                if not manual_topic: st.error("Please enter a topic.")
                elif not st.session_state.manual_questions: st.error("Please add at least one question.")
                else:
                    questions_payload = []
                    for q in st.session_state.manual_questions:
                        if not q['text'] or not q['correct']:
                            st.error("Please fill in question text and correct answer for all questions.")
                            st.stop()
                        questions_payload.append({
                            "question_text": q['text'], "options": [q['opt_a'], q['opt_b'], q['opt_c'], q['opt_d']],
                            "correct_answer": q['correct'], "difficulty": q['difficulty']
                        })
                    payload = {"topic": manual_topic, "questions": questions_payload}
                    with st.spinner("Saving..."):
                        r = requests.post(f"{API_URL}/admin/assessments/manual", json=payload)
                        if r.status_code == 201:
                            st.success(f"Assessment Saved! ID: `{r.json()['id']}`")
                            st.session_state.manual_questions = []
                            st.rerun()
                        else: st.error(f"Error: {r.text}")
            
        st.markdown("---")
        st.subheader("Existing Assessments")
        try:
            all_assessments = requests.get(f"{API_URL}/admin/assessments").json()
            if not all_assessments: st.info("No assessments created yet.")
            else:
                ass_data = []
                for a in all_assessments:
                    # Use Helper to show topics
                    t_name = get_assessment_topic_names(a)
                    
                    mod = a.get('modules')
                    mod_name = mod.get('name', 'None') if isinstance(mod, dict) else "None"
                    ass_type = a.get('type', 'Unknown')
                    ass_data.append({
                        "ID": str(a['id'])[:8] + "...",
                        "Type": ass_type,
                        "Topic": t_name,
                        "Questions": a.get('total_questions', 0),
                        "Module": mod_name,
                        "Created": str(a.get('created_at', ''))[:10]
                    })
                if ass_data:
                    df = pd.DataFrame(ass_data)
                    st.dataframe(df, use_container_width=True)
                else: st.warning("No valid data to display.")
        except Exception as e: st.error(f"Error loading assessments: {e}")

        # ==========================================
    # TAB 4: VIEW RESULTS (UPDATED)
    # ==========================================
    with t4:
        st.header("View Results")
        
        # 1. Fetch Assessments for Dropdown
        try:
            all_assessments = requests.get(f"{API_URL}/admin/assessments").json()
            
            if all_assessments:
                # Create a map of ID -> Assessment Object
                options_map = {a['id']: a for a in all_assessments}
                
                # Helper to format dropdown options (ID + Topic)
                def fmt_assessment(id):
                    a = options_map.get(id)
                    if a:
                        t_name = get_assessment_topic_names(a)
                        return f"{t_name} (ID: {str(id)[:8]}...)"
                    return str(id)
                
                selected_id = st.selectbox(
                    "Select Assessment to View Results:", 
                    options=list(options_map.keys()), 
                    format_func=fmt_assessment
                )
                
                if st.button("Load Scores"):
                    # 2. Fetch Submissions (Includes student details from backend update)
                    r = requests.get(f"{API_URL}/admin/assessments/{selected_id}/results")
                    
                    if r.status_code == 200:
                        submissions = r.json()
                        
                        if not submissions:
                            st.info("No submissions found for this assessment yet.")
                        else:
                            # 3. Process Data: Find Best Score per Student
                            student_best_scores = {}
                            
                            for s in submissions:
                                student_id = s['student_id']
                                score = s['score']
                                # Extract nested student data
                                student_info = s.get('students', {})
                                name = student_info.get('full_name', 'Unknown')
                                email = student_info.get('email', '-')
                                
                                # Initialize if new student
                                if student_id not in student_best_scores:
                                    student_best_scores[student_id] = {
                                        "Student Name": name,
                                        "Email": email,
                                        "Best Score": score
                                    }
                                else:
                                    # Update if this score is higher than existing best
                                    if score > student_best_scores[student_id]["Best Score"]:
                                        student_best_scores[student_id]["Best Score"] = score
                            
                            # 4. Display
                            results_list = list(student_best_scores.values())
                            st.dataframe(pd.DataFrame(results_list), use_container_width=True)
                    else:
                        st.error(f"Error loading results: {r.text}")
            else:
                st.info("No assessments found.")

        except Exception as e:
            st.error(f"Error: {e}")

    # ==========================================
    # TAB 5: MANAGE STUDENTS
    # ==========================================
    with t5:
        st.header("Manage Students")
        try:
            clients_response = requests.get(f"{API_URL}/admin/clients")
            if clients_response.status_code == 200: all_clients = clients_response.json()
            else: all_clients = []
        except: all_clients = []

        with st.expander("➕ Create New Student Profile", expanded=True):
            if not all_clients: st.warning("⚠️ No Clients found.")
            else:
                with st.form("create_student_form"):
                    client_options = {c['id']: c['name'] for c in all_clients}
                    s_name = st.text_input("Full Name")
                    s_email = st.text_input("Email (Login ID)")
                    s_phone = st.text_input("Phone Number")
                    selected_client_id = st.selectbox("Assign to Client", options=list(client_options.keys()), format_func=lambda x: client_options[x])
                    submitted = st.form_submit_button("Create Student")
                    
                    if submitted:
                        if not s_email: st.error("Email is required.")
                        
                        else:
                            payload = {"email": s_email, "full_name": s_name, "client_id": selected_client_id, "role": "student", "phone": s_phone}
                            with st.spinner("Creating student in Supabase..."):
                                r = requests.post(f"{API_URL}/admin/students", json=payload)
                                if r.status_code == 201: 
                                    resp_data = r.json()
                                    st.success(f"Student {resp_data['email']} created under {client_options[selected_client_id]}!")
                                    pwd = resp_data.get('generated_password')
                                    if pwd:
                                        st.info(f"🔑 Generated Password: `{pwd}`")
                                        st.caption("Please copy this password and provide it to the student.")
                                elif r.status_code == 400: st.error("Student with this email likely already exists.")
                                else: st.error(f"Failed: {r.text}")
        st.markdown("---")
        st.subheader("Existing Students")
        try:
            r = requests.get(f"{API_URL}/admin/students")
            if r.status_code == 200:
                students = r.json()
                if students:
                    student_data = []
                    for s in students:
                        client_name = "Unknown"
                        if s.get('client_id') and all_clients:
                            match = next((c['name'] for c in all_clients if c['id'] == s.get('client_id')), None)
                            if match: client_name = match
                        student_data.append({
                            "Name": s.get('full_name', 'N/A'),
                            "Email": s.get('email'),
                            "Client": client_name,
                            "Phone": s.get('phone', '-'),
                            "Created": str(s.get('created_at', ''))[:10]
                        })
                    st.dataframe(pd.DataFrame(student_data), use_container_width=True)
                else: st.info("No students found.")
            else: st.info("Could not load student list.")
        except Exception as e: st.error(f"Error loading students: {e}")
                
    

# ==========================================
# PAGE 3: STUDENT DASHBOARD (UPDATED)
# ==========================================
def render_student_dashboard():
    st.title("🎓 Student Portal")
    with st.sidebar:
        st.header("👤 Profile Settings")
        
        # 1. Update Phone & Name
        with st.expander("Update Contact Info"):
            with st.form("update_profile_form"):
                # We can pre-fill current data if we fetch it, but for simplicity we just accept input
                p_name = st.text_input("Full Name", help="Leave blank to keep current")
                p_phone = st.text_input("Phone Number", help="Leave blank to keep current")
                
                if st.form_submit_button("Update Profile"):
                    payload = {}
                    if p_name: payload["full_name"] = p_name
                    if p_phone: payload["phone"] = p_phone
                    
                    if not payload:
                        st.warning("Please enter at least one field to update.")
                    else:
                        r = requests.put(f"{API_URL}/student/me", json=payload, headers=get_auth_headers())
                        if r.status_code == 200:
                            st.success("Profile updated successfully!")
                            st.rerun() # Refresh to show changes if any
                        else:
                            st.error(f"Failed: {r.text}")

        st.markdown("---")

        # 2. Change Password
        with st.expander("Change Password"):
            with st.form("change_password_form"):
                old_pwd = st.text_input("Current Password", type="password")
                new_pwd = st.text_input("New Password", type="password")
                confirm_pwd = st.text_input("Confirm New Password", type="password")
                
                if st.form_submit_button("Change Password"):
                    if not old_pwd or not new_pwd:
                        st.error("Please fill in all fields.")
                    elif new_pwd != confirm_pwd:
                        st.error("New passwords do not match.")
                    else:
                        payload = {
                            "old_password": old_pwd,
                            "new_password": new_pwd
                        }
                        r = requests.put(f"{API_URL}/student/change-password", json=payload, headers=get_auth_headers())
                        if r.status_code == 200:
                            st.success("Password changed successfully!")
                        elif r.status_code == 400:
                            st.error("Incorrect current password.")
                        else:
                            st.error(f"Failed: {r.text}")
    
    st.button("Logout", on_click=logout, type="secondary")
    
    # CHECK IF EXAM IS ACTIVE
    if st.query_params.get("exam") == "active":
        render_exam_page()
        return

    # 1. Fetch Dashboard Data
    try:
        headers = get_auth_headers()
        r = requests.get(f"{API_URL}/student/dashboard", headers=headers)
        
        if r.status_code != 200:
            st.error("Could not load dashboard data.")
            return

        data = r.json()
        client = data.get('client')
        modules = data.get('modules', [])

        # 2. Display Client Info
        if client:
            st.markdown("---")
            st.markdown(f"### 👤 Welcome to **{client['name']}**")
            st.caption(f"Contact: {client.get('contact_email', 'N/A')}")
            st.markdown("---")
        else:
            st.info("You are not currently assigned to any client.")
            return

        # 3. Display Modules and Assessments
        if not modules:
            st.warning("No modules have been assigned to your organization yet.")
        else:
            st.subheader("Available Training Modules")

            for mod in modules:
                # This creates the "Dropdown" effect
                with st.expander(f"📚 {mod['name']}", expanded=False):
                    st.write(mod.get('description', 'No description available.'))
                    
                    assessments = mod.get('assessments', [])
                    if not assessments:
                        st.info("No assessments found in this module.")
                    else:
                        st.write("**Assessments:**")
                        for ass in assessments:
                            # Parse topic name safely
                            t_name = "General"
                            try:
                                if isinstance(ass.get('topic'), list) and len(ass['topic']) > 0:
                                    # Use helper logic or manual check consistent with Admin
                                    # Since we don't import helper here directly, we use manual check
                                    t_name = ass['topic'][0].get('name', ass['topic'][0].get('topic_name', 'General'))
                            except:
                                pass

                            # Get the Assessment Type (AI or Manual)
                            ass_type = ass.get('type', 'Unknown')

                            # Display Assessment Card
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.markdown(f"- **{t_name}** ({ass.get('total_questions', 0)} Questions) - *{ass_type}*")
                            
                            with col2:
                                # Connect the Start button
                                st.button("Start", key=f"start_{ass['id']}", on_click=start_exam, args=(ass['id'], ass_type))
                            
                            
                            st.markdown("---")

    except Exception as e:
        st.error(f"Error: {e}")

# ==========================================
# PAGE 4: STUDENT EXAM
# ==========================================
def render_exam_page():
    st.title("📝 Assessment Attempt")
    
    # Get exam details from session state
    exam_id = st.session_state.get('exam_id')
    exam_type = st.session_state.get('exam_type')
    
    if not exam_id or not exam_type:
        st.warning("No active assessment found.")
        if st.button("Return to Dashboard"):
            exit_exam()
        return

    # --- CANCEL BUTTON (Outside Form) ---
    if st.button("❌ Return to Dashboard"):
        exit_exam()
        return

    # 1. FETCH OR LOAD CACHED QUESTIONS
    if 'exam_questions' not in st.session_state:
        with st.spinner("Loading questions..."):
            if exam_type == "Manual":
                r = requests.get(f"{API_URL}/student/assessments/{exam_id}/questions", headers=get_auth_headers())
            else: # AI
                r = requests.get(f"{API_URL}/student/assessments/{exam_id}/generate", headers=get_auth_headers())
            
            if r.status_code != 200:
                st.error(f"Failed to load questions: {r.text}")
                if st.button("Return to Dashboard"):
                    exit_exam()
                return
                
            st.session_state.exam_questions = r.json()
    
    questions = st.session_state.exam_questions

    if not questions:
        st.warning("No questions available for this assessment.")
        if st.button("Return to Dashboard"):
            exit_exam()
        return

    # 2. Render Questions
    st.markdown(f"**Type:** {exam_type} | **Questions:** {len(questions)}")
    st.markdown("---")
    
    with st.form("exam_form"):
        user_answers = {}
        
        for i, q in enumerate(questions):
            st.write(f"**Q{i+1}:** {q['question_text']}")
            
            # Get options and correct label (guaranteed to be A, B, C, or D)
            options_text = q.get('options', [])
            correct_label = q.get('correct_answer')
            
            if options_text:
                option_indices = list(range(len(options_text)))
                
                # Helper to format display
                def format_option(idx):
                    label = chr(65 + idx) 
                    return f"{label}) {options_text[idx]}"
                
                selected_index = st.radio(
                    "Select Answer:", 
                    options=option_indices, 
                    format_func=format_option,
                    key=f"q_{i}",
                    label_visibility="collapsed",
                    index=None
                )
                
                # Store selection
                user_answers[i] = {
                    "selected_idx": selected_index,
                    "correct_label": correct_label # Taking from JSON as requested
                }
            
            st.markdown("---")

        submitted = st.form_submit_button("Submit Assessment")

    # --- 3. Handle Submission (Outside Form) ---
        # --- 3. Handle Submission (Outside Form) ---
    if submitted:
        # NEW: Check if any questions are unanswered
        unanswered_indices = []
        for k, v in user_answers.items():
            # v['selected_idx'] will be None if user didn't pick anything
            if v.get('selected_idx') is None:
                unanswered_indices.append(k + 1) # +1 to show human-readable question number (Q1, Q2...)

        if unanswered_indices:
            st.warning(f"Please answer all questions before submitting. Unanswered: {unanswered_indices}")
            return # Stop execution here

        total = len(user_answers)
        correct_count = 0
        
        for i, data in user_answers.items():
            # Convert User's Index (0,1,2) to Label (A,B,C)
            selected_label = chr(65 + data['selected_idx'])
            
            # Compare Labels (A == A, B == B...)
            if selected_label == data['correct_label']:
                correct_count += 1
        
        score = (correct_count / total) * 100 if total > 0 else 0
        
        # Save Score to Backend
        payload = {
            "assessment_id": exam_id,
            "score": score
        }
        
        save_resp = requests.post(f"{API_URL}/student/submissions", json=payload, headers=get_auth_headers())
        
        if save_resp.status_code == 200:
            st.success(f"Assessment Submitted!")
            st.info(f"Your Score: **{score:.2f}%**")
        else:
            st.error("Failed to save score. Please try again.")

def render_super_admin_dashboard():
    st.title("🛡️ Super Admin Console")
    st.button("Logout", on_click=logout, type="secondary")
    st.markdown("---")
    st.warning("⚠️ Restricted Access: Create Admin Profiles below.")

    # 1. Create New Admin Section
    st.subheader("Create New Admin Profile")
    with st.form("create_admin_form"):
        a_name = st.text_input("Full Name")
        a_email = st.text_input("Email (Login ID)")
        a_password = st.text_input("Password", type="password", value="")
        a_confirm = st.text_input("Confirm Password", type="password")
        
        submitted = st.form_submit_button("Create Admin")
        
        if submitted:
            if not a_email or not a_password:
                st.error("Email and Password are required.")
            elif a_password != a_confirm:
                st.error("Passwords do not match.")
            else:
                # Payload matches AdminCreateRequest
                payload = {
                    "email": a_email,
                    "password": a_password,
                    "full_name": a_name
                }
                with st.spinner("Creating Admin..."):
                    r = requests.post(f"{API_URL}/super-admin/create-admin", json=payload, headers=get_auth_headers())
                    if r.status_code == 201:
                        st.success(f"Admin {a_email} created successfully!")
                        st.info(f"Credentials: {a_email} / {a_password}")
                    elif r.status_code == 403:
                        st.error("Access Denied: You do not have Super Admin privileges.")
                    else:
                        st.error(f"Failed: {r.text}")

    st.markdown("---")
    # Optional: You can add logic to list existing admins here using a GET endpoint if you build one
    st.subheader("Existing Admin Profiles")
    
    try:
        # Fetch admins from backend
        r = requests.get(f"{API_URL}/super-admin/admins", headers=get_auth_headers())
        
        if r.status_code == 200:
            admins = r.json()
            
            if not admins:
                st.info("No admins found.")
            else:
                # Prepare data for DataFrame
                admin_data = []
                for a in admins:
                    # Clean up ID for display
                    display_id = str(a['id'])[:8] + "..." if a.get('id') else "N/A"
                    
                    # Format role for readability
                    display_role = a.get('role', '').replace('_', ' ').title()
                    
                    admin_data.append({
                        "Name": a.get('full_name', 'N/A'),
                        "Email": a.get('email', 'N/A'),
                        "Role": display_role,
                        "ID": display_id,
                        "Created": str(a.get('created_at', ''))[:10]
                    })
                
                # Create DataFrame
                df = pd.DataFrame(admin_data)
                st.dataframe(df, use_container_width=True)
                
        else:
            st.error("Failed to load admin list.")
            
    except Exception as e:
        st.error(f"Error loading admins: {e}")

# ==========================================
# MAIN ROUTER
# ==========================================
def main():
    # Initialize State
    if 'page' not in st.query_params:
        st.query_params.page = "login"
    
    current_page = st.query_params.page

    # Routing Logic
    if not st.session_state.token:
        if current_page != "login":
            set_page("login")
        render_auth_page()
    else:
        # Check Role
        if 'role' not in st.session_state:
            try:
                r = requests.get(f"{API_URL}/users/me", headers=get_auth_headers())
                if r.status_code == 200:
                    st.session_state.role = r.json()['role']
                else:
                    logout()
            except:
                logout()

        # Route
        if current_page == "admin" and st.session_state.role == 'admin':
            render_admin_dashboard()
        elif current_page == "super_admin" and st.session_state.role == 'super_admin':
            render_super_admin_dashboard()
        elif current_page == "student" and st.session_state.role == 'student':
            render_student_dashboard()
        else:
            # Default Redirect
            if st.session_state.role == 'admin':
                set_page("admin")
            else:
                set_page("student")

if __name__ == "__main__":
    main()

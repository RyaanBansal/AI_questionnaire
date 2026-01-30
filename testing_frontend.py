import streamlit as st
import requests
import uuid as uuid_lib
import pandas as pd

API_URL = "http://localhost:8000"

st.set_page_config(page_title="Admin Dashboard", layout="wide")

st.title("🎓 Assessment Admin Dashboard")
st.markdown(f"**Backend URL:** `{API_URL}`")

# --- Session State ---
if 'topic_list' not in st.session_state:
    st.session_state.topic_list = [{'topic': '', 'count': 5, 'easy': 33, 'medium': 34, 'hard': 33}]

# NEW: State for Manual Questions
if 'manual_questions' not in st.session_state:
    st.session_state.manual_questions = []

def add_topic():
    st.session_state.topic_list.append({'topic': '', 'count': 5, 'easy': 33, 'medium': 34, 'hard': 33})
    st.rerun()

def remove_topic(index):
    if len(st.session_state.topic_list) > 1:
        st.session_state.topic_list.pop(index)
        st.rerun()

# NEW: Helper for manual questions
def add_manual_question():
    st.session_state.manual_questions.append({
        "text": "", "opt_a": "", "opt_b": "", "opt_c": "", "opt_d": "", 
        "correct": "", "difficulty": "Medium"
    })
    st.rerun()

def remove_manual_question(index):
    st.session_state.manual_questions.pop(index)
    st.rerun()

# --- TABS ---
t1, t2, t3, t4 = st.tabs(["Modules", "Clients", "Create Assessment", "View Results"])

# --- TAB 1 & 2 (Unchanged) ---
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

    # List Modules
    st.subheader("Existing Modules & Assigned Assessments")
    
    try:
        # Fetch modules with their assessments
        mods = requests.get(f"{API_URL}/admin/modules").json()
        
        # Fetch all unassigned assessments for the dropdowns
        all_assessments = requests.get(f"{API_URL}/admin/assessments").json()
        
        if not mods:
            st.info("No modules found.")
        else:
            for m in mods:
                st.markdown(f"### 📚 {m['name']}")
                st.caption(m.get('description', 'No description'))

                # Get assessments assigned to this module
                assigned_assessments = m.get('assessments', [])
                assigned_ids = [a['id'] for a in assigned_assessments]
                
                # Display Assigned Assessments
                if assigned_assessments:
                    st.write("**Assigned Assessments:**")
                    for a in assigned_assessments:
                        # Extract topic name from the JSON list safely
                        topic_name = "Unknown"
                        try:
                            if isinstance(a['topic'], list) and len(a['topic']) > 0:
                                topic_name = a['topic'][0].get('name', 'Mixed Topics')
                        except:
                            pass
                        
                        col_ass, col_del = st.columns([4, 1])
                        col_ass.caption(f"📝 {topic_name} ({a['total_questions']} Qs)")
                        
                        if col_del.button("❌", key=f"rem_ass_{m['id']}_{a['id']}", help="Remove Assessment"):
                            r = requests.post(f"{API_URL}/admin/assessments/{a['id']}/remove-module")
                            if r.status_code == 200:
                                st.success("Removed")
                                st.rerun()
                            else: st.error("Failed")
                else:
                    st.write("No assessments assigned yet.")

                # UI to Add Assessment
                # Filter out assessments already assigned to THIS module
                # Note: We check if the assessment's module_id (if present in all_assessments) is null or different
                # But simpler: just use the list we haven't used in this loop
                available_assessments = [a for a in all_assessments if a['id'] not in assigned_ids]
                
                if available_assessments:
                    with st.expander(f"Assign Assessment to {m['name']}", expanded=False):
                        # Create friendly label
                        def format_assessment(opt_id):
                            a = next((x for x in available_assessments if x['id'] == opt_id), None)
                            if a:
                                try:
                                    t_name = a['topic'][0]['name'] if isinstance(a['topic'], list) else "Assessment"
                                except:
                                    t_name = "Assessment"
                                return f"{t_name} ({a['total_questions']} Qs) - {a['id'].split('-')[0]}"
                            return opt_id

                        sel_ass_id = st.selectbox(
                            "Select Assessment",
                            options=[a['id'] for a in available_assessments],
                            format_func=format_assessment,
                            key=f"add_ass_select_{m['id']}"
                        )
                        
                        if st.button("Add", key=f"btn_add_ass_{m['id']}"):
                            r = requests.post(
                                f"{API_URL}/admin/modules/{m['id']}/add-assessment",
                                json={"assessment_id": sel_ass_id}
                            )
                            if r.status_code == 200:
                                st.success("Assessment Added")
                                st.rerun()
                            else: st.error(r.text)
                else:
                    st.caption("All assessments are already assigned to this module.")

                # Delete Module Button
                if st.button("🗑️ Delete Module", key=f"del_mod_{m['id']}", type="secondary"):
                    requests.delete(f"{API_URL}/admin/modules/{m['id']}")
                    st.rerun()
                
                st.markdown("---")

    except Exception as e:
        st.error(f"Error loading modules: {e}")

# ==========================================
# TAB 2: CLIENTS
# ==========================================
with t2:
    st.header("Manage Clients")
    
    # Create Client Section
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
                    else:
                        st.error(r.text)
                else:
                    st.warning("Client Name is required")

    # List Clients and Assignments
    st.subheader("Existing Clients & Assignments")
    
    try:
        # Fetch the processed list from backend
        clients = requests.get(f"{API_URL}/admin/clients").json()
        
        # Fetch all modules to handle the dropdown assignment
        all_modules = requests.get(f"{API_URL}/admin/modules").json()
        
        if not clients:
            st.info("No clients found.")
        else:
            for c in clients:
                st.markdown(f"### 👤 {c['name']}")
                c_email_text = f"({c.get('contact_email', 'No email')})"
                st.caption(c_email_text)

                # Show Assigned Modules
                                # ... (Previous code for Client Name header) ...

                # Show Assigned Modules
                assigned_modules = c.get('assigned_modules', [])
                assigned_module_ids = [m['id'] for m in assigned_modules]
                
                if assigned_modules:
                    st.write("**Assigned Modules:**")
                    # Create columns: 1 for the module name, 1 for the remove button
                    for i, mod in enumerate(assigned_modules):
                        col_name, col_btn = st.columns([4, 1])
                        col_name.info(mod['name'])
                        
                        # The Unassign Button
                        if col_btn.button("❌", key=f"unassign_{c['id']}_{mod['id']}", help="Remove Module"):
                            # Call the new unassign endpoint
                            r = requests.post(
                                f"{API_URL}/admin/clients/{c['id']}/unassign", 
                                json={"module_id": mod['id']}
                            )
                            if r.status_code == 200:
                                st.success("Module Removed")
                                st.rerun()
                            else:
                                st.error("Failed to remove module")
                else:
                    st.write("No modules assigned yet.")
                
                st.markdown("---")
                
                # ... (Keep the rest of the logic for Assigning new modules) ...

                # UI to Assign New Module
                # Filter out modules that are already assigned
                available_modules = [m for m in all_modules if m['id'] not in assigned_module_ids]
                
                if available_modules:
                    with st.expander(f"Assign New Module to {c['name']}", expanded=False):
                        mod_options = {m['id']: m['name'] for m in available_modules}
                        
                        selected_mod_id = st.selectbox(
                            "Select Module", 
                            options=list(mod_options.keys()), 
                            format_func=lambda x: mod_options.get(x),
                            key=f"assign_select_{c['id']}"
                        )
                        
                        if st.button("Assign", key=f"btn_assign_{c['id']}"):
                            r = requests.post(
                                f"{API_URL}/admin/clients/{c['id']}/assign", 
                                json={"module_id": selected_mod_id}
                            )
                            if r.status_code == 200:
                                st.success("Module Assigned Successfully!")
                                st.rerun()
                            else:
                                st.error("Failed to assign module.")
                else:
                    st.caption("All available modules are already assigned to this client.")
                
                # Delete Client Button
                if st.button("🗑️ Delete Client", key=f"del_cli_{c['id']}", type="secondary"):
                    requests.delete(f"{API_URL}/admin/clients/{c['id']}")
                    st.rerun()

    except Exception as e:
        st.error(f"Failed to load clients: {e}")

# --- TAB 3: CREATE ASSESSMENT (UPDATED) ---
with t3:
    st.header("Create New Assessment")
    
    # REMOVE: Module Selection Dropdown (Shifted to Modules tab)
    
    # 2. Mode Selection
    mode = st.radio("Choose Creation Mode", ["AI Generate", "Manual Create"], horizontal=True)
    st.markdown("---")

    # --- MODE A: AI GENERATE ---
    if mode == "AI Generate":
        st.write("**Step 1: Configure Topics**")
        
        for i, t in enumerate(st.session_state.topic_list):
            c_label, c_btn = st.columns([4, 1])
            c_label.write(f"**Topic {i+1}:** {t['topic'] if t['topic'] else '...'}")
            c_btn.button("❌ Remove", key=f"rem_btn_{i}", on_click=remove_topic, args=(i,))

        st.button("➕ Add Another Topic", on_click=add_topic, type="secondary")
        st.markdown("---")

        with st.form("ai_assessment_form"):
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

            submitted = st.form_submit_button("✨ Generate Assessment")
            if submitted:
                payload = {"topics": payload_topics}
                with st.spinner("Generating..."):
                    r = requests.post(f"{API_URL}/admin/assessments", json=payload)
                    if r.status_code == 201:
                        st.success(f"Created! ID: `{r.json()['id']}`")
                    else: st.error(r.text)

    # --- MODE B: MANUAL CREATE ---
    elif mode == "Manual Create":
        st.write("**Step 1: Define Assessment Topic**")
        manual_topic = st.text_input("Assessment Topic", placeholder="e.g., History 101")
        
        st.markdown("---")
        st.write("**Step 2: Add Questions**")
        
        # Add Question Button (Outside form)
        st.button("➕ Add Question", on_click=add_manual_question, type="secondary")
        
        # Render Questions List
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

                # Update state
                st.session_state.manual_questions[i] = {
                    "text": q_text,
                    "opt_a": opt_a, "opt_b": opt_b, "opt_c": opt_c, "opt_d": opt_d,
                    "correct": correct, "difficulty": difficulty
                }

        st.markdown("---")
        # Submit Button (Inside Form is better for final commit, but we need to capture state)
        # We'll use a standard button here for simplicity with dynamic state
        if st.button("💾 Save Manual Assessment", type="primary"):
            if not manual_topic:
                st.error("Please enter a topic.")
            elif not st.session_state.manual_questions:
                st.error("Please add at least one question.")
            else:
                # Construct Payload
                questions_payload = []
                for q in st.session_state.manual_questions:
                    if not q['text'] or not q['correct']:
                        st.error("Please fill in question text and correct answer for all questions.")
                        st.stop()
                    
                    questions_payload.append({
                        "question_text": q['text'],
                        "options": [q['opt_a'], q['opt_b'], q['opt_c'], q['opt_d']],
                        "correct_answer": q['correct'],
                        "difficulty": q['difficulty']
                    })
                
                payload = {
                    "topic": manual_topic,
                    "questions": questions_payload
                }

                with st.spinner("Saving..."):
                    r = requests.post(f"{API_URL}/admin/assessments/manual", json=payload)
                    if r.status_code == 201:
                        st.success(f"Assessment Saved! ID: `{r.json()['id']}`")
                        # Clear state
                        st.session_state.manual_questions = []
                        st.rerun()
                    else:
                        st.error(f"Error: {r.text}")
        
    st.markdown("---")
    st.subheader("Existing Assessments")
    try:
        all_assessments = requests.get(f"{API_URL}/admin/assessments").json()
        if not all_assessments:
            st.info("No assessments created yet.")
        else:
            ass_data = []
            for a in all_assessments:
                # Parse topic for display
                t_name = "Unknown"
                try:
                    if isinstance(a['topic'], list) and len(a['topic']) > 0:
                        t_name = a['topic'][0].get('name', 'Mixed')
                except: pass
            
                mod_name = a.get('modules', {}).get('name', 'None') if a.get('modules') else "None"
            
                ass_data.append({
                    "ID": str(a['id'])[:8] + "...",
                    "Topic": t_name,
                    "Questions": a['total_questions'],
                    "Module": mod_name,
                    "Created": a['created_at'][:10]
                })
            
            df = pd.DataFrame(ass_data)
            st.dataframe(df, use_container_width=True)
            
    except Exception as e:
        st.error(f"Error loading assessments: {e}")

# --- TAB 4 (Unchanged) ---
with t4:
    st.header("View Results")
    aid = st.text_input("Assessment ID")
    if st.button("Get Results"):
        if aid:
            r = requests.get(f"{API_URL}/admin/assessments/{aid}/results")
            if r.status_code == 200:
                import pandas as pd
                st.dataframe(pd.DataFrame(r.json()))
            else: st.error(r.text)

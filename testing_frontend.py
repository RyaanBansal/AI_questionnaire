import streamlit as st
import requests

API_URL = "http://localhost:8000"

st.set_page_config(page_title="Admin Dashboard", layout="wide")

st.title("🎓 Assessment Admin Dashboard")
st.markdown(f"**Backend URL:** `{API_URL}`")

# --- Session State ---
if 'topic_list' not in st.session_state:
    st.session_state.topic_list = [{'topic': '', 'count': 5, 'easy': 33, 'medium': 34, 'hard': 33}]

def add_topic():
    st.session_state.topic_list.append({'topic': '', 'count': 5, 'easy': 33, 'medium': 34, 'hard': 33})
    st.rerun()

def remove_topic(index):
    if len(st.session_state.topic_list) > 1:
        st.session_state.topic_list.pop(index)
        st.rerun()

# --- TABS ---
t1, t2, t3, t4 = st.tabs(["Modules", "Clients", "Create Assessment", "View Results"])

# --- TAB 1: MODULES ---
with t1:
    st.header("Manage Modules")
    
    with st.expander("Create New Module"):
        m_name = st.text_input("Module Name")
        m_desc = st.text_area("Description")
        if st.button("Save Module"):
            payload = {"name": m_name, "description": m_desc}
            r = requests.post(f"{API_URL}/admin/modules", json=payload)
            if r.status_code == 201: st.success("Module Created")
            else: st.error(r.text)

    st.write("**Existing Modules**")
    mods = requests.get(f"{API_URL}/admin/modules").json()
    for m in mods:
        cols = st.columns([4, 1])
        cols[0].write(f"**{m['name']}** - {m.get('description', '')}")
        if cols[1].button("Delete", key=f"del_mod_{m['id']}"):
            requests.delete(f"{API_URL}/admin/modules/{m['id']}")
            st.rerun()

# --- TAB 2: CLIENTS ---
with t2:
    st.header("Manage Clients")
    
    with st.expander("Add New Client"):
        c_name = st.text_input("Client Name")
        c_email = st.text_input("Contact Email")
        if st.button("Add Client"):
            payload = {"name": c_name, "contact_email": c_email}
            r = requests.post(f"{API_URL}/admin/clients", json=payload)
            if r.status_code == 201: st.success("Client Added")
            else: st.error(r.text)

    st.write("**Existing Clients & Assignments**")
    clients = requests.get(f"{API_URL}/admin/clients").json()
    mods = requests.get(f"{API_URL}/admin/modules").json()
    
    for c in clients:
        cols = st.columns([3, 2, 1])
        cols[0].write(f"**{c['name']}** ({c.get('contact_email', '')})")
        
        if mods:
            # Dropdown to assign modules
            mod_names = {m['id']: m['name'] for m in mods}
            sel_mod = cols[1].selectbox("Assign Module", ["None"] + list(mod_names.keys()), format_func=lambda x: mod_names.get(x, x), key=f"assign_{c['id']}")
            
            if cols[2].button("Assign", key=f"btn_assign_{c['id']}"):
                if sel_mod != "None":
                    r = requests.post(f"{API_URL}/admin/clients/{c['id']}/assign", json={"module_id": sel_mod})
                    if r.status_code == 200: st.success("Assigned")
                    else: st.error(r.text)
        
        if cols[2].button("Delete Client", key=f"del_cli_{c['id']}"):
            requests.delete(f"{API_URL}/admin/clients/{c['id']}")
            st.rerun()

# --- TAB 3: ASSESSMENTS ---
with t3:
    st.header("Create New Assessment")
    
    # Fetch Modules for dropdown
    mods_resp = requests.get(f"{API_URL}/admin/modules").json()
    mod_opts = {None: "No Module"} | {m['id']: m['name'] for m in mods_resp}
    sel_mod_id = st.selectbox("Assign to Module", options=list(mod_opts.keys()), format_func=lambda x: mod_opts[x])

    st.write("**Topic Configuration**")
    # Topic controls (outside form)
    for i, t in enumerate(st.session_state.topic_list):
        c_label, c_btn = st.columns([4, 1])
        c_label.write(f"**Topic {i+1}:** {t['topic'] if t['topic'] else '...'}")
        c_btn.button("❌ Remove", key=f"rem_btn_{i}", on_click=remove_topic, args=(i,))

    st.button("➕ Add Another Topic", on_click=add_topic, type="secondary")
    st.markdown("---")

    with st.form("assessment_form"):
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
            if sel_mod_id != None:
                payload["module_id"] = sel_mod_id
            
            # Validation (omitted for brevity, assume valid)
            with st.spinner("Generating..."):
                r = requests.post(f"{API_URL}/admin/assessments", json=payload)
                if r.status_code == 201:
                    data = r.json()
                    st.success(f"Created! ID: `{data['id']}`")
                    st.json(data)
                else: st.error(r.text)

# --- TAB 4: RESULTS ---
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

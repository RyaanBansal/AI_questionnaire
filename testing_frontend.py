import streamlit as st
import requests

# Configuration
API_URL = "http://localhost:8000"

st.set_page_config(page_title="Admin Dashboard", layout="wide")

st.title("🎓 AI Assessment Admin Dashboard")
st.markdown(f"**Backend URL:** `{API_URL}`")

# --- Tab 1: Create Assessment ---
tab1, tab2 = st.tabs(["Generate Assessment", "View Results"])

with tab1:
    st.header("Create New Assessment")
    
    with st.form("assessment_form"):
        topic = st.text_input("Topic", placeholder="e.g., Photosynthesis, Python Basics")
        total_questions = st.number_input("Total Questions", min_value=1, max_value=100, value=10)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            easy = st.number_input("Easy %", min_value=0, max_value=100, value=33)
        with col2:
            medium = st.number_input("Medium %", min_value=0, max_value=100, value=34)
        with col3:
            hard = st.number_input("Hard %", min_value=0, max_value=100, value=33)
        
        submitted = st.form_submit_button("Generate Assessment")
        
        if submitted:
            # 1. Validation
            if not topic:
                st.error("Please enter a topic.")
            elif (easy + medium + hard) != 100:
                st.error(f"Difficulty distribution must sum to 100%. Current: {easy + medium + hard}%")
            else:
                # 2. Prepare Payload
                payload = {
                    "topic": topic,
                    "total_questions": total_questions,
                    "difficulty": {
                        "easy": easy,
                        "medium": medium,
                        "hard": hard
                    }
                }
                
                # 3. Send Request
                with st.spinner("Generating questions via AI..."):
                    try:
                        response = requests.post(f"{API_URL}/admin/assessments", json=payload)
                        
                        if response.status_code == 201:
                            data = response.json()
                            st.success(f"Assessment Created Successfully!")
                            st.info(f"Assessment ID: `{data['id']}`")
                            st.json(data)
                        else:
                            st.error(f"Error {response.status_code}: {response.text}")
                    except requests.exceptions.ConnectionError:
                        st.error("Could not connect to the API. Is `python main.py` running?")

# --- Tab 2: View Results ---
with tab2:
    st.header("View Student Results")
    
    assessment_id = st.text_input("Enter Assessment ID to view results", placeholder="UUID from previous step")
    
    if st.button("Get Results"):
        if not assessment_id:
            st.warning("Please enter an Assessment ID.")
        else:
            with st.spinner("Fetching results..."):
                try:
                    response = requests.get(f"{API_URL}/admin/assessments/{assessment_id}/results")
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        if not data:
                            st.info("No submissions found for this assessment yet.")
                        else:
                            st.write(f"Found **{len(data)}** student submissions:")
                            
                            # Display as a nice table (DataFrame)
                            import pandas as pd
                            df = pd.DataFrame(data)
                            # Drop the raw response_data column to keep the table clean, or keep it if you want
                            if 'response_data' in df.columns:
                                df = df.drop(columns=['response_data'])
                            st.dataframe(df)
                            
                            with st.expander("View Raw JSON"):
                                st.json(data)
                    else:
                        st.error(f"Error {response.status_code}: {response.text}")
                        
                except requests.exceptions.ConnectionError:
                    st.error("Could not connect to the API.")
import streamlit as st
import requests
import sqlite3
import json
from datetime import datetime
import os

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

def init_db():
    """Initialize SQLite database with required tables"""
    conn = sqlite3.connect('interview_dungeon.db')
    c = conn.cursor()
    
    # Sessions table
    c.execute('''CREATE TABLE IF NOT EXISTS sessions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  resume_data TEXT,
                  role TEXT,
                  difficulty TEXT,
                  num_questions INTEGER,
                  provider TEXT,
                  created_at TEXT)''')
    
    # Q&A pairs table
    c.execute('''CREATE TABLE IF NOT EXISTS qa_pairs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  session_id INTEGER,
                  question_num INTEGER,
                  question TEXT,
                  answer TEXT,
                  timestamp TEXT,
                  FOREIGN KEY (session_id) REFERENCES sessions (id))''')
    
    # Results table
    c.execute('''CREATE TABLE IF NOT EXISTS results
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  session_id INTEGER,
                  score INTEGER,
                  strengths TEXT,
                  weaknesses TEXT,
                  FOREIGN KEY (session_id) REFERENCES sessions (id))''')
    
    conn.commit()
    conn.close()


# ============================================================================
# API FUNCTIONS
# ============================================================================

def parse_resume(uploaded_file, provider="claude"):
    """Send resume to n8n webhook for parsing"""
    
    # Get webhook URL from environment or use default
    webhook_url = os.getenv('N8N_WEBHOOK_URL', 'http://localhost:5678/webhook/parse-resume')
    
    try:
        # Prepare multipart form data
        files = {'file': (uploaded_file.name, uploaded_file, uploaded_file.type)}
        data = {'provider': provider}
        
        # Call n8n webhook
        response = requests.post(webhook_url, files=files, data=data, timeout=30)
        response.raise_for_status()
        
        return response.json()
    
    except requests.exceptions.Timeout:
        return {'error': 'Resume parsing timed out. Please try again.'}
    except requests.exceptions.RequestException as e:
        return {'error': f'Failed to parse resume: {str(e)}'}


def generate_question(resume_data, role, difficulty, question_num, total_questions, qa_history, provider="claude"):
    """Generate interview question using LLM"""
    
    # Build context from Q&A history
    history_text = ""
    if qa_history:
        history_text = "\n".join([
            f"Q{i+1}: {qa['question']}\nA{i+1}: {qa['answer']}"
            for i, qa in enumerate(qa_history)
        ])
    
    prompt = f"""You are an expert technical interviewer for a {role} position.

Resume Data:
{json.dumps(resume_data, indent=2)}

Interview Context:
- Difficulty: {difficulty}
- Question {question_num} of {total_questions}
- Previous Q&A:
{history_text if history_text else 'No previous questions yet.'}

Generate ONE interview question that:
1. Matches {difficulty} complexity
2. Relates to skills/experience from resume
3. Is different from previous questions
4. Tests practical knowledge for {role}

Return ONLY the question text, no preamble or additional text."""

    try:
        if provider == "claude":
            # Claude API
            api_key = os.getenv('CLAUDE_API_KEY')
            if not api_key:
                return "ERROR: CLAUDE_API_KEY not set in environment"
            
            response = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json'
                },
                json={
                    'model': 'claude-sonnet-4-20250514',
                    'max_tokens': 500,
                    'messages': [{'role': 'user', 'content': prompt}]
                },
                timeout=30
            )
            response.raise_for_status()
            return response.json()['content'][0]['text'].strip()
        
        else:  # ollama
            response = requests.post(
                'http://localhost:11434/api/generate',
                json={
                    'model': 'llama3.2',
                    'prompt': prompt,
                    'stream': False
                },
                timeout=30
            )
            response.raise_for_status()
            return response.json()['response'].strip()
    
    except Exception as e:
        return f"ERROR: Failed to generate question - {str(e)}"


def score_interview(resume_data, role, qa_transcript, provider="claude"):
    """Score the interview and provide feedback"""
    
    prompt = f"""You are an expert interviewer evaluating a {role} candidate.

Resume:
{json.dumps(resume_data, indent=2)}

Interview Transcript:
{qa_transcript}

Evaluate the candidate's performance. Return ONLY valid JSON with no markdown:
{{
  "score": <0-100>,
  "strengths": ["strength 1", "strength 2"],
  "weaknesses": ["weakness 1", "weakness 2", "weakness 3"]
}}

Cite specific examples from their answers. Be constructive but honest."""

    try:
        if provider == "claude":
            api_key = os.getenv('CLAUDE_API_KEY')
            if not api_key:
                return {'error': 'CLAUDE_API_KEY not set'}
            
            response = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json'
                },
                json={
                    'model': 'claude-sonnet-4-20250514',
                    'max_tokens': 1000,
                    'messages': [{'role': 'user', 'content': prompt}]
                },
                timeout=30
            )
            response.raise_for_status()
            text = response.json()['content'][0]['text']
        
        else:  # ollama
            response = requests.post(
                'http://localhost:11434/api/generate',
                json={
                    'model': 'llama3.2',
                    'prompt': prompt,
                    'stream': False
                },
                timeout=30
            )
            response.raise_for_status()
            text = response.json()['response']
        
        # Strip markdown code fences
        cleaned = text.replace('```json', '').replace('```', '').strip()
        return json.loads(cleaned)
    
    except Exception as e:
        return {'error': f'Failed to score interview: {str(e)}'}


# ============================================================================
# STREAMLIT APP
# ============================================================================

def main():
    st.set_page_config(
        page_title="AI Interview Dungeon",
        page_icon="🎮",
        layout="centered"
    )
    
    # Initialize database
    init_db()
    
    # Initialize session state
    if 'stage' not in st.session_state:
        st.session_state.stage = 'upload'  # upload, config, interview, results
    
    # ========================================================================
    # STAGE 1: UPLOAD RESUME
    # ========================================================================
    
    if st.session_state.stage == 'upload':
        st.title("🎮 AI Interview Dungeon")
        st.markdown("**Upload your resume and face the AI interviewer!**")
        st.markdown("---")
        
        # File uploader
        uploaded_file = st.file_uploader(
            "Upload Resume (PDF, DOCX, TXT)",
            type=['pdf', 'docx', 'doc', 'txt'],
            help="Upload your resume to get started"
        )
        
        # Provider selection
        col1, col2 = st.columns(2)
        with col1:
            provider = st.selectbox(
                "LLM Provider",
                ["claude", "ollama"],
                help="Claude = paid API, Ollama = free local"
            )
        
        with col2:
            st.info(f"💡 **{provider.title()}** selected")
        
        # Parse button
        if uploaded_file:
            if st.button("📄 Parse Resume", type="primary", use_container_width=True):
                with st.spinner("🔍 Analyzing your resume..."):
                    resume_data = parse_resume(uploaded_file, provider)
                    
                    if 'error' in resume_data:
                        st.error(f"❌ {resume_data['error']}")
                    else:
                        # Store in session state
                        st.session_state.resume_data = resume_data
                        st.session_state.provider = provider
                        st.session_state.stage = 'config'
                        st.rerun()
        
        # Info box
        st.markdown("---")
        with st.expander("ℹ️ How it works"):
            st.markdown("""
            1. **Upload** your resume (PDF/DOCX)
            2. **Configure** your interview settings
            3. **Answer** AI-generated questions
            4. **Receive** a score and feedback
            
            **No data is stored permanently** - all processing happens locally!
            """)
    
    # ========================================================================
    # STAGE 2: CONFIGURE INTERVIEW
    # ========================================================================
    
    elif st.session_state.stage == 'config':
        st.title("⚙️ Configure Interview")
        st.markdown("**Set your interview parameters**")
        st.markdown("---")
        
        # Show parsed resume summary
        with st.expander("📋 Resume Summary", expanded=False):
            resume_data = st.session_state.resume_data
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Skills", len(resume_data.get('skills', [])))
            with col2:
                st.metric("Experience", len(resume_data.get('experience', [])))
            with col3:
                st.metric("Education", len(resume_data.get('education', [])))
            
            if resume_data.get('skills'):
                st.write("**Top Skills:**", ", ".join(resume_data['skills'][:5]))
        
        # Configuration form
        role = st.text_input(
            "🎯 Target Role",
            placeholder="e.g., Senior Python Developer, DevOps Engineer",
            help="The role you're interviewing for"
        )
        
        difficulty = st.select_slider(
            "📊 Difficulty Level",
            options=['Easy', 'Medium', 'Hard'],
            value='Medium',
            help="Easy = basic concepts, Hard = complex scenarios"
        )
        
        num_questions = st.selectbox(
            "🔢 Number of Questions",
            [3, 5, 7, 10],
            index=1,
            help="How many questions to answer"
        )
        
        provider_display = st.session_state.provider.title()
        st.info(f"🤖 Using **{provider_display}** for questions")
        
        st.markdown("---")
        
        # Start button
        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("◀️ Back", use_container_width=True):
                st.session_state.stage = 'upload'
                st.rerun()
        
        with col2:
            if st.button("🚀 Start Interview", type="primary", use_container_width=True, disabled=not role):
                # Save session to database
                conn = sqlite3.connect('interview_dungeon.db')
                c = conn.cursor()
                c.execute('''INSERT INTO sessions 
                            (resume_data, role, difficulty, num_questions, provider, created_at)
                            VALUES (?, ?, ?, ?, ?, ?)''',
                         (json.dumps(st.session_state.resume_data),
                          role,
                          difficulty,
                          num_questions,
                          st.session_state.provider,
                          datetime.now().isoformat()))
                session_id = c.lastrowid
                conn.commit()
                conn.close()
                
                # Initialize interview state
                st.session_state.session_id = session_id
                st.session_state.role = role
                st.session_state.difficulty = difficulty
                st.session_state.num_questions = num_questions
                st.session_state.current_question_num = 1
                st.session_state.qa_history = []
                st.session_state.current_question = None
                st.session_state.stage = 'interview'
                st.rerun()
    
    # ========================================================================
    # STAGE 3: INTERVIEW
    # ========================================================================
    
    elif st.session_state.stage == 'interview':
        st.title("💬 Interview in Progress")
        
        # Progress bar
        progress = (st.session_state.current_question_num - 1) / st.session_state.num_questions
        st.progress(progress)
        st.markdown(f"**Question {st.session_state.current_question_num} of {st.session_state.num_questions}**")
        st.markdown("---")
        
        # Generate question if not already generated
        if st.session_state.current_question is None:
            with st.spinner("🤔 Interviewer is thinking..."):
                question = generate_question(
                    st.session_state.resume_data,
                    st.session_state.role,
                    st.session_state.difficulty,
                    st.session_state.current_question_num,
                    st.session_state.num_questions,
                    st.session_state.qa_history,
                    st.session_state.provider
                )
                st.session_state.current_question = question
                st.rerun()
        
        # Display question
        st.markdown("### 🎙️ Interviewer asks:")
        st.info(st.session_state.current_question)
        
        # Answer input
        answer = st.text_area(
            "Your answer:",
            height=150,
            placeholder="Type your answer here...",
            key=f"answer_{st.session_state.current_question_num}"
        )
        
        st.markdown("---")
        
        # Submit button
        if st.button("➡️ Submit Answer", type="primary", use_container_width=True, disabled=not answer):
            # Save Q&A pair
            qa_pair = {
                'question': st.session_state.current_question,
                'answer': answer,
                'timestamp': datetime.now().isoformat()
            }
            st.session_state.qa_history.append(qa_pair)
            
            # Save to database
            conn = sqlite3.connect('interview_dungeon.db')
            c = conn.cursor()
            c.execute('''INSERT INTO qa_pairs 
                        (session_id, question_num, question, answer, timestamp)
                        VALUES (?, ?, ?, ?, ?)''',
                     (st.session_state.session_id,
                      st.session_state.current_question_num,
                      st.session_state.current_question,
                      answer,
                      datetime.now().isoformat()))
            conn.commit()
            conn.close()
            
            # Move to next question or results
            if st.session_state.current_question_num < st.session_state.num_questions:
                st.session_state.current_question_num += 1
                st.session_state.current_question = None
                st.rerun()
            else:
                # Interview complete - move to results
                st.session_state.stage = 'scoring'
                st.rerun()
    
    # ========================================================================
    # STAGE 4: SCORING (intermediate)
    # ========================================================================
    
    elif st.session_state.stage == 'scoring':
        st.title("📊 Evaluating Performance...")
        st.markdown("**Please wait while the AI reviews your answers**")
        
        with st.spinner("🤖 AI is analyzing your interview..."):
            # Build transcript
            transcript = "\n\n".join([
                f"Question {i+1}: {qa['question']}\n\nAnswer {i+1}: {qa['answer']}"
                for i, qa in enumerate(st.session_state.qa_history)
            ])
            
            # Score the interview
            result = score_interview(
                st.session_state.resume_data,
                st.session_state.role,
                transcript,
                st.session_state.provider
            )
            
            if 'error' in result:
                st.error(f"❌ {result['error']}")
                if st.button("🔄 Retry Scoring"):
                    st.rerun()
            else:
                # Save results to database
                conn = sqlite3.connect('interview_dungeon.db')
                c = conn.cursor()
                c.execute('''INSERT INTO results 
                            (session_id, score, strengths, weaknesses)
                            VALUES (?, ?, ?, ?)''',
                         (st.session_state.session_id,
                          result['score'],
                          json.dumps(result['strengths']),
                          json.dumps(result['weaknesses'])))
                conn.commit()
                conn.close()
                
                st.session_state.result = result
                st.session_state.stage = 'results'
                st.rerun()
    
    # ========================================================================
    # STAGE 5: RESULTS
    # ========================================================================
    
    elif st.session_state.stage == 'results':
        st.title("🏆 Interview Complete!")
        st.markdown("---")
        
        result = st.session_state.result
        
        # Score display with color coding
        score = result['score']
        if score >= 80:
            color = "🟢"
            grade = "Excellent"
        elif score >= 60:
            color = "🟡"
            grade = "Good"
        else:
            color = "🔴"
            grade = "Needs Improvement"
        
        # Big score display
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown(f"<h1 style='text-align: center; font-size: 72px;'>{color} {score}</h1>", unsafe_allow_html=True)
            st.markdown(f"<h3 style='text-align: center;'>{grade}</h3>", unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Strengths
        st.markdown("### ✅ Strengths")
        for i, strength in enumerate(result['strengths'], 1):
            st.success(f"**{i}.** {strength}")
        
        st.markdown("")
        
        # Weaknesses
        st.markdown("### ⚠️ Areas for Improvement")
        for i, weakness in enumerate(result['weaknesses'], 1):
            st.warning(f"**{i}.** {weakness}")
        
        st.markdown("---")
        
        # Review Q&A
        with st.expander("📝 Review Your Answers"):
            for i, qa in enumerate(st.session_state.qa_history, 1):
                st.markdown(f"**Question {i}:** {qa['question']}")
                st.markdown(f"*Your answer:* {qa['answer']}")
                st.markdown("---")
        
        # Action buttons
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Start New Interview", type="primary", use_container_width=True):
                # Clear session state
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.session_state.stage = 'upload'
                st.rerun()
        
        with col2:
            if st.button("📊 View All Interviews", use_container_width=True):
                st.session_state.stage = 'history'
                st.rerun()
    
    # ========================================================================
    # STAGE 6: HISTORY (bonus)
    # ========================================================================
    
    elif st.session_state.stage == 'history':
        st.title("📊 Interview History")
        st.markdown("---")
        
        conn = sqlite3.connect('interview_dungeon.db')
        c = conn.cursor()
        c.execute('''SELECT s.id, s.role, s.difficulty, s.num_questions, 
                            s.created_at, r.score
                     FROM sessions s
                     LEFT JOIN results r ON s.id = r.session_id
                     ORDER BY s.created_at DESC
                     LIMIT 10''')
        sessions = c.fetchall()
        conn.close()
        
        if not sessions:
            st.info("No previous interviews found.")
        else:
            for session in sessions:
                session_id, role, difficulty, num_q, created, score = session
                
                col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
                with col1:
                    st.write(f"**{role}**")
                with col2:
                    st.write(f"{difficulty} • {num_q} questions")
                with col3:
                    if score:
                        st.write(f"Score: **{score}**")
                    else:
                        st.write("*Incomplete*")
                with col4:
                    st.write(created[:10])
                
                st.markdown("---")
        
        if st.button("◀️ Back to Home", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.session_state.stage = 'upload'
            st.rerun()


if __name__ == "__main__":
    main()

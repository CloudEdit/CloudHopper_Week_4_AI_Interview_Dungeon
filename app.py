import streamlit as st
import requests
import sqlite3
import json
import re
from datetime import datetime
import os
import io
from dotenv import load_dotenv

load_dotenv()

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import docx
except ImportError:
    docx = None

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
    
    # Add interviewers_json column if it doesn't exist (migration for existing DBs)
    try:
        c.execute('ALTER TABLE sessions ADD COLUMN interviewers_json TEXT')
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


# ============================================================================
# API FUNCTIONS
# ============================================================================

def extract_text_from_file(uploaded_file):
    """Extract text from PDF, DOCX, or TXT files"""
    file_type = uploaded_file.type
    file_name = uploaded_file.name.lower()

    try:
        file_bytes = uploaded_file.read()

        if 'pdf' in file_type or file_name.endswith('.pdf'):
            if pdfplumber is None:
                return "ERROR: pdfplumber not installed. Run: pip install pdfplumber"
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            return text.strip()

        elif 'word' in file_type or file_name.endswith(('.docx', '.doc')):
            if docx is None:
                return "ERROR: python-docx not installed. Run: pip install python-docx"
            doc = docx.Document(io.BytesIO(file_bytes))
            return "\n".join([para.text for para in doc.paragraphs if para.text]).strip()

        elif 'text' in file_type or file_name.endswith('.txt'):
            return file_bytes.decode('utf-8', errors='ignore').strip()

        else:
            return f"ERROR: Unsupported file type: {file_type}"

    except Exception as e:
        return f"ERROR: Failed to extract text - {str(e)}"


def parse_resume(resume_text, provider="claude"):
    """Send resume text to n8n webhook for parsing"""

    webhook_url = os.getenv('N8N_WEBHOOK_URL', 'http://localhost:5678/webhook/parse-resume')

    try:
        response = requests.post(
            webhook_url,
            json={'resumeText': resume_text, 'provider': provider},
            timeout=120
        )
        response.raise_for_status()

        return response.json()

    except requests.exceptions.Timeout:
        return {'error': 'Resume parsing timed out. Please try again.'}
    except requests.exceptions.RequestException as e:
        return {'error': f'Failed to parse resume: {str(e)}'}


def clean_question(text):
    """Strip Ollama artifacts and JSON wrapper from question text"""
    text = text.strip()
    # If LLM wrapped the question as a JSON key: {"question text":""}
    if text.startswith('{'):
        match = re.match(r'\{["\'"](.+?)["\'"]\s*:', text, re.DOTALL)
        if match:
            text = match.group(1).strip()
    # Strip model-specific tags and trailing commentary
    text = re.split(r'<\|', text)[0]          # removes <|python_tag|>assistant etc.
    text = re.split(r'\n\s*#\s+', text)[0]    # removes # commentary lines
    return text.strip(' "\'{}')


def generate_question(resume_data, role, difficulty, question_num, total_questions, qa_history, provider="claude", interviewer_type="technical", star_format=False):
    """Generate interview question using n8n webhook"""

    webhook_url = os.getenv('N8N_QUESTION_WEBHOOK_URL', 'http://localhost:5678/webhook/generate-question')

    try:
        data = {
            'resumeData': resume_data,
            'role': role,
            'difficulty': difficulty,
            'questionNum': question_num,
            'totalQuestions': total_questions,
            'qaHistory': qa_history,
            'provider': provider,
            'interviewerType': interviewer_type,
            'starFormat': star_format,
        }

        response = requests.post(webhook_url, json=data, timeout=120)
        response.raise_for_status()

        result = response.json()
        question = result.get('question', 'ERROR: No question returned')
        return clean_question(question)

    except Exception as e:
        return f"ERROR: Failed to generate question - {str(e)}"


def score_interview(resume_data, role, qa_transcript, provider="claude"):
    """Score the interview using n8n webhook"""

    webhook_url = os.getenv('N8N_SCORE_WEBHOOK_URL', 'http://localhost:5678/webhook/score-interview')

    try:
        data = {
            'resumeData': resume_data,
            'role': role,
            'qaTranscript': qa_transcript,
            'provider': provider
        }

        response = requests.post(webhook_url, json=data, timeout=120)
        response.raise_for_status()

        return response.json()

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
        title_col, hist_col = st.columns([4, 1])
        with title_col:
            st.title("🎮 AI Interview Dungeon")
            st.markdown("**Upload your resume and face the AI interviewer!**")
        with hist_col:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("📊 History", use_container_width=True):
                st.session_state.stage = 'history'
                st.rerun()
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
                with st.spinner("📖 Extracting text from resume..."):
                    resume_text = extract_text_from_file(uploaded_file)

                if resume_text.startswith("ERROR:"):
                    st.error(f"❌ {resume_text}")
                else:
                    with st.spinner("🤖 Analyzing resume with AI..."):
                        resume_data = parse_resume(resume_text, provider)

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

        company = st.text_input(
            "🏢 Target Company (optional)",
            placeholder="e.g., Google, Stripe, Acme Corp",
            help="Future versions will tailor questions to this company's known interview style"
        )

        num_questions = st.selectbox(
            "🔢 Number of Questions",
            [3, 5, 7, 10],
            index=1,
            help="Total questions shared across all interviewers"
        )

        num_interviewers = st.slider(
            "👥 Number of Interviewers",
            min_value=1, max_value=3, value=1,
            help="Questions rotate between interviewers"
        )

        include_hr = st.checkbox(
            "🤝 Include HR Rep (Culture & Behavioral)",
            value=False,
            help="Adds an HR interviewer who asks culture-fit and behavioral questions — no technical questions"
        )

        st.markdown("**📊 Difficulty per Interviewer**")
        interviewer_difficulties = []
        diff_cols = st.columns(num_interviewers)
        for i, col in enumerate(diff_cols):
            with col:
                diff = col.select_slider(
                    f"Interviewer {i + 1}",
                    options=['Easy', 'Medium', 'Hard'],
                    value='Medium',
                    key=f"diff_{i}"
                )
                interviewer_difficulties.append(diff)

        if include_hr:
            st.info("🤝 **HR Rep** will ask culture & behavioral questions (rotates with other interviewers)")

        provider_display = st.session_state.provider.title()
        st.info(f"🤖 Using **{provider_display}** for questions")

        star_format = st.checkbox(
            "⭐ STAR Interview Format",
            value=False,
            help="Questions will prompt you to answer using Situation, Task, Action, Result structure"
        )

        voice_mode = st.checkbox(
            "🎙️ Voice Interview (Coming Soon)",
            value=False,
            help="Read questions aloud and record spoken answers instead of typing"
        )

        st.markdown("---")

        # Start button
        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("◀️ Back", use_container_width=True):
                st.session_state.stage = 'upload'
                st.rerun()

        with col2:
            if st.button("🚀 Start Interview", type="primary", use_container_width=True, disabled=not role):
                interviewers = [
                    {'name': f"Interviewer {i + 1}", 'difficulty': interviewer_difficulties[i], 'type': 'technical'}
                    for i in range(num_interviewers)
                ]
                if include_hr:
                    interviewers.append({'name': 'HR Rep', 'difficulty': 'Easy', 'type': 'hr'})
                conn = sqlite3.connect('interview_dungeon.db')
                c = conn.cursor()
                c.execute('''INSERT INTO sessions
                            (resume_data, role, difficulty, num_questions, provider, created_at, interviewers_json)
                            VALUES (?, ?, ?, ?, ?, ?, ?)''',
                         (json.dumps(st.session_state.resume_data),
                          role,
                          interviewers[0]['difficulty'],
                          num_questions,
                          st.session_state.provider,
                          datetime.now().isoformat(),
                          json.dumps(interviewers)))
                session_id = c.lastrowid
                conn.commit()
                conn.close()

                # Initialize interview state
                st.session_state.session_id = session_id
                st.session_state.role = role
                st.session_state.interviewers = interviewers
                st.session_state.num_questions = num_questions
                st.session_state.current_question_num = 1
                st.session_state.qa_history = []
                st.session_state.current_question = None
                st.session_state.voice_mode = voice_mode
                st.session_state.star_format = star_format
                st.session_state.company = company
                st.session_state.stage = 'interview'
                st.rerun()
    
    # ========================================================================
    # STAGE 3: INTERVIEW
    # ========================================================================
    
    elif st.session_state.stage == 'interview':
        st.title("💬 Interview in Progress")

        # Back and Refresh buttons
        btn_col1, btn_col2, _ = st.columns([1, 1, 4])
        with btn_col1:
            if st.button("◀️ Back", use_container_width=True):
                st.session_state.stage = 'config'
                st.rerun()
        with btn_col2:
            if st.button("🔄 Refresh", use_container_width=True):
                st.session_state.current_question = None
                st.rerun()

        # Determine active interviewer
        interviewers = st.session_state.interviewers
        interviewer_idx = (st.session_state.current_question_num - 1) % len(interviewers)
        active_interviewer = interviewers[interviewer_idx]

        # Progress bar
        progress = (st.session_state.current_question_num - 1) / st.session_state.num_questions
        st.progress(progress)
        prog_col1, prog_col2 = st.columns([2, 1])
        with prog_col1:
            st.markdown(f"**Question {st.session_state.current_question_num} of {st.session_state.num_questions}**")
        with prog_col2:
            label = "Culture & Behavioral" if active_interviewer.get('type') == 'hr' else active_interviewer['difficulty']
            st.markdown(f"🧑‍💼 **{active_interviewer['name']}** · {label}")
        st.markdown("---")

        # Generate question if not already generated
        if st.session_state.current_question is None:
            with st.spinner(f"🤔 {active_interviewer['name']} is thinking..."):
                question = generate_question(
                    st.session_state.resume_data,
                    st.session_state.role,
                    active_interviewer['difficulty'],
                    st.session_state.current_question_num,
                    st.session_state.num_questions,
                    st.session_state.qa_history,
                    st.session_state.provider,
                    interviewer_type=active_interviewer.get('type', 'technical'),
                    star_format=st.session_state.get('star_format', False)
                )
                st.session_state.current_question = question
                st.rerun()

        # Display question
        st.markdown(f"### 🎙️ {active_interviewer['name']} asks:")
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

        # Action buttons row
        h_col1, h_col2, _ = st.columns([1, 1, 2])
        with h_col1:
            if st.button("🗑️ Clear All", use_container_width=True):
                st.session_state.confirm_clear = 'all'
        with h_col2:
            if st.button("🧹 Clear Incomplete", use_container_width=True):
                st.session_state.confirm_clear = 'incomplete'

        # Confirmation dialog
        if st.session_state.get('confirm_clear'):
            mode = st.session_state.confirm_clear
            label = "ALL interviews" if mode == 'all' else "incomplete interviews"
            st.warning(f"Delete {label}? This cannot be undone.")
            yes_col, no_col, _ = st.columns([1, 1, 4])
            with yes_col:
                if st.button("✅ Yes, delete", use_container_width=True):
                    conn = sqlite3.connect('interview_dungeon.db')
                    c = conn.cursor()
                    if mode == 'all':
                        c.execute('DELETE FROM qa_pairs')
                        c.execute('DELETE FROM results')
                        c.execute('DELETE FROM sessions')
                    else:
                        c.execute('''DELETE FROM qa_pairs WHERE session_id IN (
                                        SELECT s.id FROM sessions s
                                        LEFT JOIN results r ON s.id = r.session_id
                                        WHERE r.score IS NULL)''')
                        c.execute('''DELETE FROM sessions WHERE id NOT IN (
                                        SELECT session_id FROM results WHERE score IS NOT NULL)''')
                    conn.commit()
                    conn.close()
                    del st.session_state.confirm_clear
                    st.rerun()
            with no_col:
                if st.button("❌ Cancel", use_container_width=True):
                    del st.session_state.confirm_clear
                    st.rerun()

        st.markdown("---")

        conn = sqlite3.connect('interview_dungeon.db')
        c = conn.cursor()
        c.execute('''SELECT s.id, s.role, s.difficulty, s.num_questions,
                            s.created_at, r.score, r.strengths, r.weaknesses,
                            s.interviewers_json
                     FROM sessions s
                     LEFT JOIN results r ON s.id = r.session_id
                     ORDER BY s.created_at DESC
                     LIMIT 20''')
        sessions = c.fetchall()

        # Fetch Q&A for all sessions in one query
        session_ids = [row[0] for row in sessions]
        qa_map = {}
        if session_ids:
            placeholders = ','.join('?' * len(session_ids))
            c.execute(f'''SELECT session_id, question_num, question, answer
                          FROM qa_pairs WHERE session_id IN ({placeholders})
                          ORDER BY session_id, question_num''', session_ids)
            for sid, qnum, question, answer in c.fetchall():
                qa_map.setdefault(sid, []).append((qnum, question, answer))
        conn.close()

        if not sessions:
            st.info("No previous interviews found.")
        else:
            for session in sessions:
                session_id, role, difficulty, num_q, created, score, strengths_raw, weaknesses_raw, interviewers_raw = session

                try:
                    interviewers = json.loads(interviewers_raw) if interviewers_raw else [{'name': 'Interviewer 1', 'difficulty': difficulty}]
                except Exception:
                    interviewers = [{'name': 'Interviewer 1', 'difficulty': difficulty}]

                # Build expander label
                if len(interviewers) == 1:
                    diff_label = interviewers[0]['difficulty']
                else:
                    diff_label = f"{len(interviewers)} interviewers"
                expander_label = f"**{role}** — {diff_label} • {num_q}q • {created[:10]}{'   ✅' if score is not None else ''}"

                with st.expander(expander_label, expanded=False):
                    # Interviewer panel
                    if len(interviewers) > 1:
                        st.markdown("**Panel**")
                        badge_cols = st.columns(len(interviewers))
                        for i, (iv, col) in enumerate(zip(interviewers, badge_cols)):
                            diff_color = {'Easy': '🟢', 'Medium': '🟡', 'Hard': '🔴'}.get(iv['difficulty'], '⚪')
                            col.markdown(f"{diff_color} **{iv['name']}**  \n{iv['difficulty']}")
                        st.markdown("---")

                    # Score / status
                    if score is not None:
                        s_col1, s_col2 = st.columns(2)
                        with s_col1:
                            st.metric("Score", f"{score}/100")
                        with s_col2:
                            try:
                                strengths = json.loads(strengths_raw) if strengths_raw else []
                                weaknesses = json.loads(weaknesses_raw) if weaknesses_raw else []
                            except Exception:
                                strengths, weaknesses = [], []

                            if strengths:
                                st.markdown("**Strengths**")
                                for s in strengths:
                                    st.markdown(f"- {s}")
                            if weaknesses:
                                st.markdown("**Areas to improve**")
                                for w in weaknesses:
                                    st.markdown(f"- {w}")
                    else:
                        st.caption("*Interview not completed*")

                    # Q&A transcript — annotate which interviewer asked each question
                    qa_pairs = qa_map.get(session_id, [])
                    if qa_pairs:
                        st.markdown("**Transcript**")
                        for qnum, question, answer in qa_pairs:
                            iv = interviewers[(qnum - 1) % len(interviewers)]
                            diff_color = {'Easy': '🟢', 'Medium': '🟡', 'Hard': '🔴'}.get(iv['difficulty'], '⚪')
                            st.markdown(f"**Q{qnum}** · {diff_color} {iv['name']} · *{iv['difficulty']}*")
                            st.markdown(f"**{question}**")
                            st.markdown(f"> {answer}")
                    else:
                        st.caption("No answers recorded.")

        st.markdown("---")
        if st.button("◀️ Back to Home", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.session_state.stage = 'upload'
            st.rerun()


if __name__ == "__main__":
    main()

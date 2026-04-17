# 🎮 AI Interview Dungeon

An AI-powered job interview simulator that uses your resume to generate personalized interview questions.

## Features

- **Resume Parsing**: Upload PDF/DOCX resumes for AI analysis
- **Dual LLM Support**: Choose between Claude API (paid) or Ollama (free local)
- **Personalized Questions**: AI generates questions based on your skills and experience
- **Real-time Scoring**: Get instant feedback with strengths and weaknesses
- **Interview History**: Review past interviews and track progress

## Architecture

```
Streamlit UI ──► n8n Workflow ──► Claude API / Ollama
     │                                    │
     └──────────► SQLite Database ◄───────┘
```

## Prerequisites

1. **n8n** (with the Resume Parser workflow imported and active)
2. **Python 3.8+**
3. **Claude API Key** (if using Claude) OR **Ollama** (if using local)

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Environment Variables

```bash
# For Claude API (paid option)
export CLAUDE_API_KEY=sk-ant-api03-your-key-here

# n8n webhook URL (update with your n8n instance)
export N8N_WEBHOOK_URL=http://localhost:5678/webhook/parse-resume
```

### 3. Make Sure n8n Workflow is Running

- Import `resume-parser-workflow.json` into n8n
- Activate the workflow
- Copy the webhook URL from the Webhook node

### 4. Run the App

```bash
streamlit run app.py
```

The app will open at `http://localhost:8501`

## Usage

### Step 1: Upload Resume
- Click "Upload Resume" and select your PDF/DOCX file
- Choose LLM provider (Claude or Ollama)
- Click "Parse Resume"

### Step 2: Configure Interview
- Enter target role (e.g., "Senior Python Developer")
- Select difficulty (Easy/Medium/Hard)
- Choose number of questions (3/5/7/10)
- Click "Start Interview"

### Step 3: Answer Questions
- Read each AI-generated question
- Type your answer in the text box
- Click "Submit Answer"
- Repeat for all questions

### Step 4: View Results
- See your score (0-100)
- Read strengths (2-3 items)
- Review areas for improvement (2-3 items)
- Option to start new interview or view history

## Configuration

### Using Ollama (Free Local Option)

1. Install Ollama: https://ollama.ai
2. Pull the model:
   ```bash
   ollama pull llama3.2
   ```
3. Make sure Ollama is running:
   ```bash
   ollama serve
   ```
4. Select "ollama" in the app

### Using Claude API (Paid Option)

1. Get API key from: https://console.anthropic.com
2. Set environment variable:
   ```bash
   export CLAUDE_API_KEY=sk-ant-api03-...
   ```
3. Select "claude" in the app

## File Structure

```
interview-dungeon/
├── app.py                          # Main Streamlit application
├── requirements.txt                # Python dependencies
├── resume-parser-workflow.json     # n8n workflow
├── interview_dungeon.db           # SQLite database (auto-created)
└── README.md                       # This file
```

## Database Schema

### Sessions Table
- `id`: Primary key
- `resume_data`: JSON string of parsed resume
- `role`: Target job role
- `difficulty`: Easy/Medium/Hard
- `num_questions`: Number of questions
- `provider`: claude/ollama
- `created_at`: Timestamp

### Q&A Pairs Table
- `id`: Primary key
- `session_id`: Foreign key to sessions
- `question_num`: Question number (1, 2, 3...)
- `question`: Question text
- `answer`: User's answer
- `timestamp`: When answered

### Results Table
- `id`: Primary key
- `session_id`: Foreign key to sessions
- `score`: Interview score (0-100)
- `strengths`: JSON array of strengths
- `weaknesses`: JSON array of weaknesses

## Troubleshooting

### "Resume parsing failed"
- Check that n8n workflow is running and active
- Verify `N8N_WEBHOOK_URL` environment variable is correct
- Test webhook manually: `curl -X POST <webhook-url> -F "file=@resume.pdf"`

### "CLAUDE_API_KEY not set"
- Make sure environment variable is exported in the same terminal
- Or add to `.bashrc`/`.zshrc`: `export CLAUDE_API_KEY=sk-ant-...`

### "Ollama connection failed"
- Check Ollama is running: `ollama serve`
- Verify model is pulled: `ollama pull llama3.2`
- Default URL is `http://localhost:11434`

### Questions take too long
- Claude API: ~3-5 seconds per question (normal)
- Ollama: ~10-15 seconds per question (depends on hardware)
- Adjust timeout in `app.py` if needed (default: 30 seconds)

## Cost Breakdown

### Claude API (Paid)
- Resume parsing: ~$0.002 per resume
- Question generation: ~$0.001 per question
- Scoring: ~$0.003 per interview
- **Total per interview (5 questions): ~$0.01**

### Ollama (Free)
- **$0.00** - completely free
- Requires: 8GB RAM, decent CPU
- Slightly slower than Claude

## Tips for Best Results

1. **Upload clean resumes**: Text-based PDFs work best
2. **Be specific with roles**: "Senior DevOps Engineer" > "Developer"
3. **Answer thoroughly**: 2-3 sentences minimum per answer
4. **Use realistic scenarios**: Reference real projects when possible
5. **Try different difficulties**: Start with Easy, work up to Hard

## Good/Bad/Ugly

### Good ✅
- Free tier option (Ollama)
- Personalized to your resume
- Instant feedback
- Unlimited practice

### Bad ⚠️
- Text-only (no voice)
- Basic resume parsing
- Questions can be repetitive
- Single LLM personality

### Ugly 🔥
- Requires n8n running
- LLM can hallucinate about skills
- Scoring is subjective
- No ground truth for "correct" answers

## Future Improvements

- [ ] Voice mode (Whisper API for speech-to-text)
- [ ] Adaptive difficulty (questions adjust based on answers)
- [ ] Multi-interviewer panel
- [ ] Industry-specific question banks
- [ ] Video recording option
- [ ] PDF export of results

## License

MIT

## Credits

Built for CloudHopper's "52 Apps in 52 Weeks" series.
- Week 4: AI Interview Dungeon
- Tech Stack: Streamlit, n8n, Claude/Ollama, SQLite

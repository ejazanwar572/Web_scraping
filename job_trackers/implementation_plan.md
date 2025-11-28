# OmniJobs Tracker Implementation Plan

## Goal
Track job postings from OmniJobs.io based on specific search criteria, match them against the user's resume, and send Slack alerts for high-matching jobs.

## Architecture

### 1. Scraper (`omnijobs_tracker.py`)
- **Library**: Playwright (async)
- **Search URL**: `https://omnijobs.io/en/search?jobFunction=data+science+and+analytics&onlyRemote=true&location=IN`
- **Logic**:
    - Navigate to search page.
    - Scroll to load all/multiple jobs (Infinite scroll handling).
    - Extract job cards: Title, Company, Location, Posted Date, Job URL.
    - Filter out already processed jobs (check DB).
    - For new jobs:
        - Visit Job URL.
        - Extract full Job Description.
        - Calculate Match Score.
        - Save to DB.
        - Alert if score > threshold.

### 2. Database (`data/omnijobs.db`)
- **Table `jobs`**:
    - `id` (TEXT, Primary Key): Job ID from URL (e.g., 5548126)
    - `title` (TEXT)
    - `company` (TEXT)
    - `location` (TEXT)
    - `url` (TEXT)
    - `posted_at` (TEXT)
    - `description` (TEXT)
    - `match_score` (INTEGER)
    - `status` (TEXT): 'new', 'alerted', 'seen'
    - `created_at` (TEXT)

### 3. Matching Logic
- **Input**: Resume Text (from `resume_text.txt`) vs Job Description.
- **Algorithm**: 
    - Simple Keyword Overlap (Jaccard Similarity on important keywords) or TF-IDF if possible.
    - Given the environment, we'll start with a robust Keyword/Set based matching:
        - Tokenize text.
        - Remove stopwords.
        - Calculate intersection / union.
        - Bonus: Weight specific skills (Python, SQL, Machine Learning) higher.

### 4. Alerting
- **Channel**: Slack
- **Webhook**: Reuse existing Zepto webhook or ask for new one.
- **Content**:
    - Job Title
    - Company
    - Match Score
    - Link
    - Key matching skills found.

## Files
- `job_trackers/omnijobs_tracker.py`: Main script.
- `job_trackers/resume_text.txt`: Extracted resume text.
- `job_trackers/data/omnijobs.db`: SQLite database.
- `job_trackers/requirements.txt`: Dependencies.

## Next Steps
1. Create `omnijobs_tracker.py` with basic scraping logic.
2. Implement database storage.
3. Implement matching logic.
4. Add Slack notifications.
5. Test with a few jobs.

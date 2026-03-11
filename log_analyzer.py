import anthropic
import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

DB_PATH = "uptime_monitor.db"
LOG_FILE = "logs/app.log"


# -- READ LOG FILE --
def read_log_file(lines=100):
    if not os.path.exists(LOG_FILE):
        return None
    with open(LOG_FILE, "r") as f:
        all_lines = f.readlines()
    return "".join(all_lines[-lines:])


# -- READ LOGS FROM DATABASE --
def read_logs_from_db(level=None, source=None, limit=50):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    query = "SELECT level, source, message, logged_at FROM logs"
    conditions = []
    params = []

    if level:
        conditions.append("level = ?")
        params.append(level.upper())
    if source:
        conditions.append("source = ?")
        params.append(source)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return rows


# -- READ SOURCE CODE FOR CONTEXT --
def read_source_files():
    source = {}
    files = [
        "uptime_monitor.py",
        "db_manager.py",
        "code_manager.py",
        "logger.py"
    ]
    for f in files:
        content = None
        if os.path.exists(f):
            with open(f, "r") as file:
                content = file.read()
        source[f] = content
    return source


# -- SHOW LOG SUMMARY --
def show_log_summary():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print("\nLog Summary:")
    print("=" * 50)

    cur.execute("""
        SELECT level, COUNT(*) as count
        FROM logs
        GROUP BY level
        ORDER BY count DESC
    """)
    rows = cur.fetchall()
    if rows:
        for row in rows:
            print(f"  {row[0]:<10} : {row[1]} entries")
    else:
        print("  No logs yet!")

    print("\nLogs Per Source:")
    cur.execute("""
        SELECT source, COUNT(*) as count
        FROM logs
        GROUP BY source
        ORDER BY count DESC
    """)
    rows = cur.fetchall()
    if rows:
        for row in rows:
            print(f"  {row[0]:<20} : {row[1]} entries")

    print("\nRecent Errors:")
    cur.execute("""
        SELECT source, message, logged_at
        FROM logs
        WHERE level = 'ERROR'
        ORDER BY id DESC
        LIMIT 5
    """)
    rows = cur.fetchall()
    if rows:
        for row in rows:
            print(f"  [{row[2]}] {row[0]} -> {row[1][:80]}")
    else:
        print("  No errors found!")

    print("\nRecent Warnings:")
    cur.execute("""
        SELECT source, message, logged_at
        FROM logs
        WHERE level = 'WARNING'
        ORDER BY id DESC
        LIMIT 5
    """)
    rows = cur.fetchall()
    if rows:
        for row in rows:
            print(f"  [{row[2]}] {row[0]} -> {row[1][:80]}")
    else:
        print("  No warnings found!")

    print("=" * 50)
    conn.close()


# -- AUTO BUG DETECTION --
def auto_detect_bugs():
    print("\n  Reading logs and source code...")

    log_content = read_log_file(lines=200)
    db_logs = read_logs_from_db(limit=100)
    source_files = read_source_files()

    # Pull only errors and warnings for focused analysis
    errors = read_logs_from_db(level="ERROR", limit=20)
    warnings = read_logs_from_db(level="WARNING", limit=20)

    prompt = f"""
You are an expert Python debugger. Analyze the following logs and source code 
and automatically find all bugs, errors and potential issues.

Log file (last 200 lines):
{log_content if log_content else 'No log file found'}

ERROR logs from database:
{errors if errors else 'No errors found'}

WARNING logs from database:
{warnings if warnings else 'No warnings found'}

Source code:
{source_files}

Perform a complete automatic bug analysis and report:

1. BUGS FOUND
   For each bug:
   - What is the bug?
   - Which file and which function?
   - What is the root cause?
   - How serious is it? (CRITICAL / HIGH / MEDIUM / LOW)
   - Exact fix in plain English

2. WARNINGS TO WATCH
   List any warnings that could become bugs if ignored

3. PATTERNS DETECTED
   Any recurring errors or suspicious patterns in the logs

4. CODE ISSUES
   Any problems in the source code that are not yet causing errors
   but could cause problems in future

5. RECOMMENDED PRIORITY
   List fixes in order of priority — what to fix first

Be specific. Reference exact line numbers, function names and log timestamps.
If no bugs are found say so clearly.
"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    return message.content[0].text


# -- ASK CLAUDE TO ANALYZE LOGS --
def ask_claude(user_request, log_content, db_logs, source_files, conversation_history):

    system_prompt = """
You are an expert log analyst, Python debugger and code reviewer.

Your job:
1. Read logs carefully and find errors, warnings and patterns
2. Cross reference logs with actual source code to find root causes
3. Identify bugs automatically without being asked
4. Suggest exact fixes with code examples
5. Explain everything in simple plain English
6. Point out potential problems before they become real bugs

When analyzing always cover:
- What went wrong and when exactly
- Which file and function caused it
- Why it happened — root cause
- How serious it is
- Exact steps to fix it
- Whether it will happen again

Always reference specific log lines, timestamps and source code when explaining.
Be specific, practical and actionable.
"""

    context = f"""
Log file contents (last 100 lines):
{log_content if log_content else 'Log file not found or empty'}

Recent database logs:
{db_logs if db_logs else 'No database logs found'}

Current source code:
{source_files}

User request: {user_request}
"""

    conversation_history.append({
        "role": "user",
        "content": context
    })

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=system_prompt,
        messages=conversation_history
    )

    response_text = message.content[0].text

    conversation_history.append({
        "role": "assistant",
        "content": response_text
    })

    return response_text, conversation_history


# -- MAIN --
def main():
    print("\nAI Log Analyzer and Auto Debugger - powered by Claude")
    print("=" * 55)
    print("What you can ask:")
    print("  -> analyze my logs")
    print("  -> find all bugs automatically")
    print("  -> why is uptime_monitor failing?")
    print("  -> are there patterns in the warnings?")
    print("  -> what should I fix first?")
    print("  -> show me logs from db_manager")
    print("  -> summarize what happened today")
    print("  -> is my code healthy?")
    print("\nCommands:")
    print("  auto debug     -> Claude scans everything and finds bugs automatically")
    print("  summary        -> quick log summary from database")
    print("  show errors    -> show all ERROR logs")
    print("  show warnings  -> show all WARNING logs")
    print("  show info      -> show all INFO logs")
    print("  show debug     -> show all DEBUG logs")
    print("  show file      -> print raw log file")
    print("  clear          -> reset conversation")
    print("  exit           -> quit")
    print("=" * 55)

    conversation_history = []

    while True:
        print()
        user_input = input("You -> ").strip()

        if not user_input:
            continue

        if user_input.lower() == "exit":
            print("Bye!")
            break

        if user_input.lower() == "clear":
            conversation_history = []
            print("  Conversation cleared!")
            continue

        if user_input.lower() == "summary":
            show_log_summary()
            continue

        if user_input.lower() == "show errors":
            rows = read_logs_from_db(level="ERROR")
            print(f"\n  ERROR logs ({len(rows)} found):")
            for row in rows:
                print(f"  [{row[3]}] {row[1]} -> {row[2]}")
            continue

        if user_input.lower() == "show warnings":
            rows = read_logs_from_db(level="WARNING")
            print(f"\n  WARNING logs ({len(rows)} found):")
            for row in rows:
                print(f"  [{row[3]}] {row[1]} -> {row[2]}")
            continue

        if user_input.lower() == "show info":
            rows = read_logs_from_db(level="INFO")
            print(f"\n  INFO logs ({len(rows)} found):")
            for row in rows:
                print(f"  [{row[3]}] {row[1]} -> {row[2]}")
            continue

        if user_input.lower() == "show debug":
            rows = read_logs_from_db(level="DEBUG")
            print(f"\n  DEBUG logs ({len(rows)} found):")
            for row in rows:
                print(f"  [{row[3]}] {row[1]} -> {row[2]}")
            continue

        if user_input.lower() == "show file":
            content = read_log_file()
            if content:
                print("\n  Raw log file:")
                print("  " + "-" * 45)
                print(content)
                print("  " + "-" * 45)
            else:
                print("  Log file not found or empty!")
            continue

        # Auto debug — Claude scans everything automatically
        if user_input.lower() == "auto debug":
            print("\n  Running automatic bug detection...")
            print("  Claude is reading all logs and source code...\n")
            analysis = auto_detect_bugs()
            print("\n  Auto Debug Report:")
            print("  " + "=" * 50)
            for line in analysis.split('\n'):
                print(f"  {line}")
            print("  " + "=" * 50)
            print("\n  Tip: Use code_manager.py to apply any fixes Claude suggested!")
            continue

        # General question — Claude reads logs + source code together
        print("\n  Claude is analyzing...")

        log_content = read_log_file(lines=100)
        db_logs = read_logs_from_db(limit=50)
        source_files = read_source_files()

        response, conversation_history = ask_claude(
            user_input,
            log_content,
            db_logs,
            source_files,
            conversation_history
        )

        print("\n  Claude Analysis:")
        print("  " + "-" * 45)
        for line in response.split('\n'):
            print(f"  {line}")
        print("  " + "-" * 45)


if __name__ == "__main__":
    main()

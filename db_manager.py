import sqlite3
import anthropic
import os
from dotenv import load_dotenv
from logger import get_logger

load_dotenv()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DB_PATH = "uptime_monitor.db"
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
log = get_logger("db_manager")


# -- GET CURRENT DATABASE STRUCTURE --
def get_db_structure():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cur.fetchall()
    structure = {}
    for (table_name,) in tables:
        cur.execute(f"PRAGMA table_info({table_name})")
        columns = cur.fetchall()
        structure[table_name] = [
            {"name": col[1], "type": col[2]}
            for col in columns
        ]
    conn.close()
    log.debug("Database structure fetched")
    return structure


# -- GET SAMPLE DATA --
def get_sample_data():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    samples = {}
    try:
        cur.execute("""
            SELECT id, session_id, url, status_code, response_time_ms,
                   is_up, error_reason, checked_at
            FROM checks
            ORDER BY id DESC
            LIMIT 5
        """)
        samples["checks"] = cur.fetchall()
        cur.execute("SELECT * FROM ai_analysis ORDER BY id DESC LIMIT 3")
        samples["ai_analysis"] = cur.fetchall()
    except Exception as e:
        log.warning(f"Could not fetch sample data — {str(e)}")
    conn.close()
    return samples


# -- EXECUTE SQL SAFELY --
def execute_sql(sql):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(sql)
        conn.commit()
        if sql.strip().upper().startswith("SELECT"):
            rows = cur.fetchall()
            conn.close()
            log.debug(f"SQL executed successfully — {len(rows)} rows returned")
            return True, rows
        conn.close()
        log.info(f"SQL executed successfully: {sql[:60]}")
        return True, "Success"
    except Exception as e:
        conn.close()
        log.error(f"SQL execution failed: {str(e)} | SQL: {sql[:60]}")
        return False, str(e)


# -- ASK CLAUDE WITH DYNAMIC SYSTEM PROMPT --
def ask_claude(user_request, db_structure, sample_data, conversation_history):

    # Dynamic system prompt — reads live DB structure every time
    # No manual updates needed when columns change
    system_prompt = f"""
You are an intelligent database assistant and website monitoring analyst.

You have full access to this SQLite database. Here is the LIVE current structure:

{db_structure}

Here is a sample of recent data:

{sample_data}

You must read the structure above carefully and understand every table and column
that exists RIGHT NOW. Do not assume any fixed structure — it changes over time
as new columns get added via db_manager.

You can help the user with:
1. CRUD operations — add/read/update/delete data or columns
2. Analyze website monitoring logs — find patterns, anomalies, insights
3. Answer questions about the data
4. Suggest improvements based on patterns you see

When user wants database changes:
Reply in this exact format:
TYPE: DB_CHANGE
EXPLANATION: <what this does in simple words>
WARNING: <data loss risks or None>
SQL: <exact SQLite SQL command>

When user wants data analysis or insights:
Reply in this exact format:
TYPE: ANALYSIS
EXPLANATION: <your full analysis here>
SQL: <SQL query to fetch needed data, or NONE>

When user asks general questions:
Reply in this exact format:
TYPE: ANSWER
EXPLANATION: <your answer>
SQL: NONE

Always be concise, practical and clear.
"""

    conversation_history.append({
        "role": "user",
        "content": user_request
    })

    log.debug(f"Sending request to Claude: {user_request[:60]}")

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system=system_prompt,
            messages=conversation_history
        )
        response_text = message.content[0].text
        conversation_history.append({
            "role": "assistant",
            "content": response_text
        })
        log.debug("Claude responded successfully")
        return response_text, conversation_history
    except Exception as e:
        log.error(f"Claude API call failed: {str(e)}")
        raise


# -- PARSE CLAUDE RESPONSE --
def parse_response(response):
    lines = response.strip().split('\n')
    result = {
        "type": "ANSWER",
        "explanation": "",
        "warning": "",
        "sql": ""
    }

    explanation_lines = []
    for line in lines:
        if line.startswith("TYPE:"):
            result["type"] = line.replace("TYPE:", "").strip()
        elif line.startswith("WARNING:"):
            result["warning"] = line.replace("WARNING:", "").strip()
        elif line.startswith("SQL:"):
            result["sql"] = line.replace("SQL:", "").strip()
        elif line.startswith("EXPLANATION:"):
            explanation_lines.append(line.replace("EXPLANATION:", "").strip())
        elif explanation_lines:
            explanation_lines.append(line)

    result["explanation"] = "\n  ".join(explanation_lines)
    return result


# -- SHOW DATABASE STRUCTURE --
def show_structure():
    structure = get_db_structure()
    print("\nCurrent Database Structure:")
    print("=" * 45)
    for table, columns in structure.items():
        print(f"\n  Table: {table}")
        for col in columns:
            print(f"    - {col['name']} ({col['type']})")
    print("=" * 45)


# -- SHOW TABLE DATA --
def show_table_data(table_name, limit=10):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT * FROM {table_name} ORDER BY id DESC LIMIT {limit}")
        rows = cur.fetchall()
        cur.execute(f"PRAGMA table_info({table_name})")
        columns = [col[1] for col in cur.fetchall()]
        conn.close()

        if not rows:
            print(f"  No data in {table_name} yet!")
            return

        print(f"\n  Last {len(rows)} rows from {table_name}:")
        print(f"  {' | '.join(columns)}")
        print("  " + "-" * 60)
        for row in rows:
            print(f"  {' | '.join(str(v)[:20] if v else 'NULL' for v in row)}")
    except Exception as e:
        log.error(f"Failed to show table data for {table_name}: {str(e)}")
        print(f"  Error: {e}")
        conn.close()


# -- HANDLE DB CHANGE --
def handle_db_change(parsed, user_request, db_structure):
    print(f"\n  Explanation : {parsed['explanation']}")

    if parsed["warning"] and parsed["warning"].lower() != "none":
        print(f"  Warning     : {parsed['warning']}")

    if parsed["sql"] and parsed["sql"].upper() != "NONE":
        print(f"  SQL         : {parsed['sql']}")
        confirm = input("\n  Execute this? (yes/no) -> ").strip().lower()

        if confirm == "yes":
            success, result = execute_sql(parsed["sql"])
            if success:
                print("  Done! Database updated successfully")
                log.info(f"Database changed: {parsed['sql'][:60]}")
                show_structure()
            else:
                print(f"  Failed: {result}")
                log.error(f"Database change failed: {result}")
                print("  Asking Claude to fix the error...")

                fix_prompt = f"""
The SQL command failed with this error: {result}
Original SQL: {parsed['sql']}
User request: {user_request}
Database structure: {db_structure}

Generate a corrected SQL command.
TYPE: DB_CHANGE
EXPLANATION: <what you fixed>
WARNING: None
SQL: <corrected SQL>
"""
                try:
                    fix_message = client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=512,
                        messages=[{"role": "user", "content": fix_prompt}]
                    )
                    fix_parsed = parse_response(fix_message.content[0].text)
                    print(f"\n  Fix        : {fix_parsed['explanation']}")
                    print(f"  New SQL    : {fix_parsed['sql']}")

                    confirm2 = input("\n  Try fixed SQL? (yes/no) -> ").strip().lower()
                    if confirm2 == "yes":
                        success2, msg2 = execute_sql(fix_parsed["sql"])
                        if success2:
                            print("  Fixed and applied!")
                            log.info(f"Fixed SQL applied: {fix_parsed['sql'][:60]}")
                            show_structure()
                        else:
                            print(f"  Still failed: {msg2}")
                            log.error(f"Fixed SQL also failed: {msg2}")
                except Exception as e:
                    log.error(f"Claude fix attempt failed: {str(e)}")
        else:
            print("  Skipped!")
            log.debug("User skipped database change")


# -- HANDLE ANALYSIS --
def handle_analysis(parsed):
    if parsed["sql"] and parsed["sql"].upper() != "NONE":
        success, rows = execute_sql(parsed["sql"])
        if success and isinstance(rows, list):
            print(f"\n  Data fetched: {len(rows)} rows")
            log.info(f"Analysis query returned {len(rows)} rows")

            followup = f"""
Here is the data from the database:
{rows}

Now give a clear detailed analysis based on this real data.
Focus on:
- Patterns you notice
- Which sites have issues
- Response time trends
- Any anomalies
- What the engineer should do next
"""
            try:
                message = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=2048,
                    messages=[{"role": "user", "content": followup}]
                )
                final_analysis = message.content[0].text
                print(f"\n  Claude Analysis:")
                print("  " + "-" * 45)
                for line in final_analysis.split('\n'):
                    print(f"  {line}")
                print("  " + "-" * 45)
            except Exception as e:
                log.error(f"Analysis follow-up failed: {str(e)}")
        else:
            print(f"\n  Analysis:\n  {parsed['explanation']}")
    else:
        print(f"\n  Claude says:\n  {parsed['explanation']}")


# -- MAIN --
def main():
    print("\nAI Database Manager - powered by Claude")
    print("=" * 50)
    print("What you can do:")
    print("  -> add logging column to checks table")
    print("  -> show me all DOWN incidents")
    print("  -> analyze my website monitoring logs")
    print("  -> which website is slowest?")
    print("  -> delete all records for tesla.com")
    print("  -> how many incidents happened today?")
    print("\nCommands:")
    print("  show           -> show database structure")
    print("  show checks    -> show checks table data")
    print("  show ai        -> show AI analysis history")
    print("  clear          -> start fresh conversation")
    print("  exit           -> quit")
    print("=" * 50)

    log.info("db_manager started")
    conversation_history = []

    while True:
        print()
        user_input = input("You -> ").strip()

        if not user_input:
            continue

        if user_input.lower() == "exit":
            log.info("db_manager exited by user")
            print("Bye!")
            break

        if user_input.lower() == "clear":
            conversation_history = []
            print("  Conversation cleared!")
            log.debug("Conversation history cleared")
            continue

        if user_input.lower() == "show":
            show_structure()
            continue

        if user_input.lower() == "show checks":
            show_table_data("checks")
            continue

        if user_input.lower() == "show ai":
            show_table_data("ai_analysis")
            continue

        log.debug(f"User request: {user_input[:60]}")
        print("\n  Claude is thinking...")

        structure = get_db_structure()
        samples = get_sample_data()

        try:
            response, conversation_history = ask_claude(
                user_input, structure, samples, conversation_history
            )
            parsed = parse_response(response)

            if parsed["type"].strip() == "DB_CHANGE":
                handle_db_change(parsed, user_input, structure)
            elif parsed["type"].strip() == "ANALYSIS":
                handle_analysis(parsed)
            else:
                print(f"\n  Claude says:")
                print("  " + "-" * 45)
                print(f"  {parsed['explanation']}")
                print("  " + "-" * 45)
        except Exception as e:
            log.error(f"Unexpected error in db_manager: {str(e)}")
            print(f"  Something went wrong: {str(e)}")


if __name__ == "__main__":
    main()
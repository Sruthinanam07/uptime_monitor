import requests
import datetime
import sqlite3
import anthropic
import os
from dotenv import load_dotenv
from logger import get_logger

# -- LOAD ENV --
load_dotenv()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# -- SESSION ID --
SESSION_ID = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

# -- LOGGER --
log = get_logger("uptime_monitor")


# -- ASK USER FOR WEBSITES --
print("Website Uptime Monitor")
print("="*40)
print("Enter websites to monitor (one per line)")
print("When done, just press Enter on empty line")
print("Example: https://www.google.com")
print("="*40)

WEBSITES = []
while True:
    url = input("Enter URL: ").strip()
    if url == "":
        break
    if not url.startswith("http"):
        url = "https://" + url
    WEBSITES.append(url)
    print(f"Added: {url}")

if not WEBSITES:
    print("No websites entered! Using defaults...")
    WEBSITES = [
        "https://www.google.com",
        "https://www.github.com",
        "https://httpstat.us/500",
    ]

print(f"\nChecking {len(WEBSITES)} website(s)...\n")
log.info(f"Session {SESSION_ID} started — checking {len(WEBSITES)} websites")


# -- DATABASE SETUP --
def setup_database():
    conn = sqlite3.connect("uptime_monitor.db")
    cur = conn.cursor()

    # Use db_manager.py to add or change columns anytime
    cur.execute("""
        CREATE TABLE IF NOT EXISTS checks (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id       TEXT,
            url              TEXT,
            status_code      INTEGER,
            response_time_ms REAL,
            is_up            INTEGER,
            error_reason     TEXT,
            checked_at       TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ai_analysis (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            check_id     INTEGER,
            url          TEXT,
            analysis     TEXT,
            analyzed_at  TEXT,
            FOREIGN KEY (check_id) REFERENCES checks(id)
        )
    """)

    conn.commit()
    log.debug("Database setup complete")
    return conn


# -- CHECK WEBSITE --
def check_website(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    log.debug(f"Checking {url}")

    try:
        start_time = datetime.datetime.now()
        response = requests.get(url, timeout=15, headers=headers)
        end_time = datetime.datetime.now()
        response_time_ms = (end_time - start_time).total_seconds() * 1000
        is_up = 200 <= response.status_code < 300
        error_reason = None if is_up else classify_error(response.status_code)

        if is_up:
            log.info(f"UP | {url} | {round(response_time_ms, 2)}ms | {response.status_code}")
        else:
            log.warning(f"DOWN | {url} | {response.status_code} | {error_reason}")

        return {
            "url": url,
            "status_code": response.status_code,
            "response_time_ms": round(response_time_ms, 2),
            "is_up": is_up,
            "checked_at": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "error_reason": error_reason
        }

    except requests.exceptions.ReadTimeout:
        log.error(f"TIMEOUT | {url} | No response within 15 seconds")
        return {
            "url": url,
            "status_code": None,
            "response_time_ms": None,
            "is_up": False,
            "checked_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error_reason": "REQUEST_TIMEOUT — server did not respond within 15 seconds"
        }

    except requests.exceptions.ConnectionError:
        log.error(f"CONNECTION_ERROR | {url} | Could not reach server")
        return {
            "url": url,
            "status_code": None,
            "response_time_ms": None,
            "is_up": False,
            "checked_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error_reason": "CONNECTION_ERROR — could not reach the server at all"
        }


# -- CLASSIFY ERROR FROM STATUS CODE --
def classify_error(status_code):
    errors = {
        400: "BAD_REQUEST — malformed request sent to server",
        401: "UNAUTHORIZED — authentication required",
        403: "FORBIDDEN — server is blocking automated/bot requests",
        404: "NOT_FOUND — page does not exist",
        429: "RATE_LIMITED — too many requests, IP is being throttled",
        500: "INTERNAL_SERVER_ERROR — server crashed or has a bug",
        502: "BAD_GATEWAY — upstream server returned invalid response",
        503: "SERVICE_UNAVAILABLE — server overloaded or under maintenance",
        504: "GATEWAY_TIMEOUT — upstream server timed out",
    }
    return errors.get(status_code, f"HTTP_{status_code} — unexpected status code")


# -- SAVE CHECK TO DATABASE --
def save_to_db(conn, result):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO checks
        (session_id, url, status_code, response_time_ms, is_up, error_reason, checked_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        SESSION_ID,
        result["url"],
        result["status_code"],
        result["response_time_ms"],
        1 if result["is_up"] else 0,
        result.get("error_reason"),
        result["checked_at"]
    ))
    conn.commit()
    log.debug(f"Saved check for {result['url']} to database")
    return cur.lastrowid


# -- SAVE AI ANALYSIS TO DATABASE --
def save_ai_analysis(conn, check_id, url, analysis):
    conn.execute("""
        INSERT INTO ai_analysis (check_id, url, analysis, analyzed_at)
        VALUES (?, ?, ?, ?)
    """, (
        check_id,
        url,
        analysis,
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    conn.commit()
    log.debug(f"Saved AI analysis for {url} to database")


# -- SQL ANALYSIS — CURRENT RUN ONLY --
def run_sql_analysis(conn):
    cur = conn.cursor()
    print("\n" + "="*50)
    print("  SQL ANALYSIS REPORT - CURRENT RUN")
    print("="*50)

    print("\nAverage Response Time Per Site:")
    cur.execute("""
        SELECT url,
               COUNT(*) as total_checks,
               ROUND(AVG(response_time_ms), 2) as avg_ms,
               SUM(CASE WHEN is_up = 0 THEN 1 ELSE 0 END) as times_down
        FROM checks
        WHERE session_id = ?
        GROUP BY url
        ORDER BY avg_ms DESC
    """, (SESSION_ID,))
    rows = cur.fetchall()
    if rows:
        for row in rows:
            print(f"  {row[0]}")
            print(f"    Checks: {row[1]}  |  Avg: {row[2]}ms  |  Down: {row[3]} times")
    else:
        print("  No data yet!")

    print("\nSlowest Response This Run:")
    cur.execute("""
        SELECT url, response_time_ms, checked_at
        FROM checks
        WHERE response_time_ms IS NOT NULL
        AND session_id = ?
        ORDER BY response_time_ms DESC
        LIMIT 1
    """, (SESSION_ID,))
    row = cur.fetchone()
    print(f"  {row[0]} -> {row[1]}ms at {row[2]}" if row else "  No data yet!")

    print("\nFastest Response This Run:")
    cur.execute("""
        SELECT url, response_time_ms, checked_at
        FROM checks
        WHERE response_time_ms IS NOT NULL
        AND session_id = ?
        ORDER BY response_time_ms ASC
        LIMIT 1
    """, (SESSION_ID,))
    row = cur.fetchone()
    print(f"  {row[0]} -> {row[1]}ms at {row[2]}" if row else "  No data yet!")

    print("\nIncidents This Run:")
    cur.execute("""
        SELECT url, status_code, error_reason, checked_at
        FROM checks
        WHERE is_up = 0
        AND session_id = ?
        ORDER BY checked_at DESC
    """, (SESSION_ID,))
    rows = cur.fetchall()
    if rows:
        for row in rows:
            print(f"  DOWN | {row[0]}")
            print(f"    Code   : {row[1]}")
            print(f"    Reason : {row[2]}")
            print(f"    At     : {row[3]}")
    else:
        print("  No incidents this run!")

    print("\nUptime Score This Run:")
    cur.execute("""
        SELECT url,
               ROUND(100.0 * SUM(is_up) / COUNT(*), 1) as uptime_pct
        FROM checks
        WHERE session_id = ?
        GROUP BY url
        ORDER BY uptime_pct DESC
    """, (SESSION_ID,))
    rows = cur.fetchall()
    if rows:
        for row in rows:
            status = "UP" if row[1] == 100 else "PARTIAL" if row[1] >= 50 else "DOWN"
            print(f"  {status} | {row[0]} -> {row[1]}% uptime")
    else:
        print("  No data yet!")

    print("\nAI Analysis This Run:")
    cur.execute("""
        SELECT a.url, a.analyzed_at, a.analysis
        FROM ai_analysis a
        JOIN checks c ON a.check_id = c.id
        WHERE c.session_id = ?
        ORDER BY a.analyzed_at DESC
    """, (SESSION_ID,))
    rows = cur.fetchall()
    if rows:
        for row in rows:
            print(f"\n  {row[0]} | Analyzed at: {row[1]}")
            lines = row[2].split('\n')[:2]
            for line in lines:
                if line.strip():
                    print(f"    {line}")
    else:
        print("  No AI analyses this run!")

    print("\n" + "="*50)
    log.info(f"SQL analysis report generated for session {SESSION_ID}")


# -- AI AGENT --
def analyze_incident_with_ai(result):
    if result["is_up"]:
        return None

    log.info(f"AI agent analyzing incident for {result['url']}")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    if result["status_code"] is None:
        connection_context = f"""
What happened technically:
- The script could NOT establish any HTTP connection
- Error reason: {result['error_reason']}
- No status code returned — server never responded
- Timeout was set to 15 seconds

This is NOT necessarily a full outage. Common causes:
1. Site actively blocks Python/automated requests
2. Cloudflare or WAF blocking the monitoring script
3. IP rate limiting
4. Actual network outage or DNS failure
5. Server taking longer than 15 seconds to respond
"""
    else:
        connection_context = f"""
What happened technically:
- HTTP connection was established successfully
- Server responded with status code: {result['status_code']}
- Error reason: {result['error_reason']}
- Response time: {result['response_time_ms']}ms
- Server IS reachable but returning an error
"""

    incident_info = f"""
A website monitoring system detected the following incident:

URL           : {result['url']}
Status Code   : {result['status_code']}
Response Time : {result['response_time_ms']}ms
Checked At    : {result['checked_at']}
Error Reason  : {result['error_reason']}

Monitoring tool context:
- Automated Python script using requests library
- User-Agent set to Mozilla/5.0 to mimic browser
- Timeout configured to 15 seconds
- This is NOT a human browser — some sites block automated tools

{connection_context}

Based on all of this context answer these 5 things accurately:
1. Root Cause  : What is the real likely cause given the context?
2. Severity    : Is this LOW, MEDIUM or HIGH?
3. User Impact : Are real users affected or just our monitoring script?
4. Fix Steps   : What exact steps should the engineer take?
5. Escalate?   : Should this be escalated and why?

Be accurate, practical and honest.
If the issue is likely bot blocking say so clearly.
Format each point on its own line with the label.
"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": incident_info}]
        )
        log.info(f"AI analysis complete for {result['url']}")
        return message.content[0].text
    except Exception as e:
        log.error(f"AI analysis failed for {result['url']} — {str(e)}")
        return None


# -- MAIN --
def main():
    conn = setup_database()

    for site in WEBSITES:
        result = check_website(site)
        check_id = save_to_db(conn, result)
        status = "UP  " if result["is_up"] else "DOWN"
        print(f"{status} | {result['url']} | {result['response_time_ms']}ms | Status: {result['status_code']}")

        if not result["is_up"]:
            print(f"  Reason: {result['error_reason']}")
            print(f"\n  AI Agent analyzing incident...")
            analysis = analyze_incident_with_ai(result)
            if analysis:
                save_ai_analysis(conn, check_id, result["url"], analysis)
                print(f"\n  --- AI INCIDENT ANALYSIS ---")
                for line in analysis.split('\n'):
                    if line.strip():
                        print(f"  {line}")
                print(f"  ----------------------------\n")

    run_sql_analysis(conn)
    conn.close()
    log.info(f"Session {SESSION_ID} complete")
    print("\nAll results and AI analyses saved to uptime_monitor.db")


if __name__ == "__main__":
    main()
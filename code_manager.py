import anthropic
import os
import shutil
import datetime
from dotenv import load_dotenv
from logger import get_logger

load_dotenv()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
log = get_logger("code_manager")

# -- FILES CLAUDE CAN MODIFY --
MANAGED_FILES = {
    "uptime_monitor": "uptime_monitor.py",
    "db_manager": "db_manager.py",
    "code_manager": "code_manager.py"
}


# -- READ FILE --
def read_file(filepath):
    try:
        with open(filepath, "r") as f:
            return f.read()
    except FileNotFoundError:
        log.error(f"File not found: {filepath}")
        return None


# -- WRITE FILE --
def write_file(filepath, content):
    try:
        with open(filepath, "w") as f:
            f.write(content)
        log.info(f"File written successfully: {filepath}")
        return True
    except Exception as e:
        log.error(f"Failed to write file {filepath}: {str(e)}")
        return str(e)


# -- BACKUP FILE BEFORE CHANGING --
def backup_file(filepath):
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = f"{filepath}.backup_{timestamp}"
    try:
        shutil.copy2(filepath, backup_path)
        log.info(f"Backup created: {backup_path}")
        return backup_path
    except Exception as e:
        log.error(f"Backup failed for {filepath}: {str(e)}")
        return None


# -- LIST BACKUPS --
def list_backups():
    import glob
    backups = []
    for filepath in MANAGED_FILES.values():
        found = glob.glob(f"{filepath}.backup_*")
        backups.extend(found)
    return sorted(backups, reverse=True)


# -- RESTORE FROM BACKUP --
def restore_backup(backup_path):
    try:
        original = backup_path.rsplit(".backup_", 1)[0]
        shutil.copy2(backup_path, original)
        log.info(f"Restored {original} from {backup_path}")
        return True, original
    except Exception as e:
        log.error(f"Restore failed: {str(e)}")
        return False, str(e)


# -- ASK CLAUDE TO ANALYZE AND MODIFY CODE --
def ask_claude_to_modify(user_request, file_name, file_content, conversation_history):

    system_prompt = f"""
You are an expert Python code assistant.

You are managing these project files:
- uptime_monitor.py  : monitors websites, checks uptime, runs AI incident analysis
- db_manager.py      : manages database via natural language, CRUD operations
- code_manager.py    : manages code changes via natural language

Current file being modified: {file_name}

Your job:
1. Understand exactly what the user wants to change
2. Show the specific section of code that needs to change
3. Generate the complete updated version of that section
4. Explain what you changed and why

Always reply in this exact format:

TYPE: CODE_CHANGE
FILE: <filename>
EXPLANATION: <what you are changing and why in simple words>
WARNING: <any risks or side effects or None>
FIND_THIS:
<exact current code to be replaced — copy it exactly as it appears>
END_FIND
REPLACE_WITH:
<new updated code to replace it with>
END_REPLACE

If the user wants to add something completely new with no existing code to replace:

TYPE: CODE_ADDITION
FILE: <filename>
EXPLANATION: <what you are adding and where>
WARNING: <any risks or None>
ADD_AFTER:
<exact line after which to insert the new code>
END_AFTER
NEW_CODE:
<new code to insert>
END_NEW_CODE

If the request is unclear or you need more info:

TYPE: QUESTION
EXPLANATION: <what you need clarified>

If no code change is needed:

TYPE: ANSWER
EXPLANATION: <your answer>

Be precise. The FIND_THIS block must match the current code exactly.
"""

    conversation_history.append({
        "role": "user",
        "content": f"""
Current content of {file_name}:

{file_content}

User request: {user_request}
"""
    })

    log.debug(f"Asking Claude to modify {file_name}: {user_request[:60]}")

    try:
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
        log.debug("Claude responded with code change")
        return response_text, conversation_history
    except Exception as e:
        log.error(f"Claude API call failed: {str(e)}")
        raise


# -- PARSE CLAUDE RESPONSE --
def parse_response(response):
    result = {
        "type": "",
        "file": "",
        "explanation": "",
        "warning": "",
        "find_this": "",
        "replace_with": "",
        "add_after": "",
        "new_code": ""
    }

    lines = response.strip().split('\n')
    current_block = None
    block_lines = []

    for line in lines:
        if line.startswith("TYPE:"):
            result["type"] = line.replace("TYPE:", "").strip()
        elif line.startswith("FILE:"):
            result["file"] = line.replace("FILE:", "").strip()
        elif line.startswith("EXPLANATION:"):
            result["explanation"] = line.replace("EXPLANATION:", "").strip()
        elif line.startswith("WARNING:"):
            result["warning"] = line.replace("WARNING:", "").strip()
        elif line.strip() == "FIND_THIS:":
            current_block = "find_this"
            block_lines = []
        elif line.strip() == "END_FIND":
            result["find_this"] = '\n'.join(block_lines)
            current_block = None
        elif line.strip() == "REPLACE_WITH:":
            current_block = "replace_with"
            block_lines = []
        elif line.strip() == "END_REPLACE":
            result["replace_with"] = '\n'.join(block_lines)
            current_block = None
        elif line.strip() == "ADD_AFTER:":
            current_block = "add_after"
            block_lines = []
        elif line.strip() == "END_AFTER":
            result["add_after"] = '\n'.join(block_lines)
            current_block = None
        elif line.strip() == "NEW_CODE:":
            current_block = "new_code"
            block_lines = []
        elif line.strip() == "END_NEW_CODE":
            result["new_code"] = '\n'.join(block_lines)
            current_block = None
        elif current_block:
            block_lines.append(line)

    return result


# -- SHOW DIFF --
def show_diff(find_this, replace_with):
    print("\n  --- CURRENT CODE ---")
    for line in find_this.split('\n'):
        print(f"  - {line}")
    print("\n  --- NEW CODE ---")
    for line in replace_with.split('\n'):
        print(f"  + {line}")
    print()


# -- APPLY CODE CHANGE --
def apply_change(filepath, find_this, replace_with):
    content = read_file(filepath)
    if content is None:
        return False, "File not found"
    if find_this not in content:
        log.warning(f"Could not find code block in {filepath}")
        return False, "Could not find the exact code block in file"
    new_content = content.replace(find_this, replace_with, 1)
    result = write_file(filepath, new_content)
    if result is True:
        return True, new_content
    return False, result


# -- APPLY CODE ADDITION --
def apply_addition(filepath, add_after, new_code):
    content = read_file(filepath)
    if content is None:
        return False, "File not found"
    if add_after not in content:
        log.warning(f"Could not find anchor line in {filepath}")
        return False, "Could not find the anchor line to insert after"
    new_content = content.replace(add_after, add_after + '\n' + new_code, 1)
    result = write_file(filepath, new_content)
    if result is True:
        return True, new_content
    return False, result


# -- HANDLE CODE CHANGE --
def handle_code_change(parsed):
    filepath = parsed["file"]

    if filepath in MANAGED_FILES:
        filepath = MANAGED_FILES[filepath]

    if not os.path.exists(filepath):
        print(f"  Error: {filepath} not found")
        log.error(f"File not found: {filepath}")
        return

    print(f"\n  File        : {filepath}")
    print(f"  Explanation : {parsed['explanation']}")

    if parsed["warning"] and parsed["warning"].lower() != "none":
        print(f"  Warning     : {parsed['warning']}")

    if parsed["type"] == "CODE_CHANGE":
        show_diff(parsed["find_this"], parsed["replace_with"])
    elif parsed["type"] == "CODE_ADDITION":
        print(f"\n  Adding after: {parsed['add_after'][:80]}...")
        print("\n  --- NEW CODE BEING ADDED ---")
        for line in parsed["new_code"].split('\n'):
            print(f"  + {line}")
        print()

    confirm = input("  Apply this change? (yes/no) -> ").strip().lower()

    if confirm == "yes":
        backup_path = backup_file(filepath)
        if backup_path:
            print(f"  Backup saved: {backup_path}")

        if parsed["type"] == "CODE_CHANGE":
            success, result = apply_change(
                filepath,
                parsed["find_this"],
                parsed["replace_with"]
            )
        else:
            success, result = apply_addition(
                filepath,
                parsed["add_after"],
                parsed["new_code"]
            )

        if success:
            print(f"  Done! {filepath} updated successfully")
            log.info(f"Code change applied to {filepath}")
        else:
            print(f"  Failed: {result}")
            print("  Your backup is safe at:", backup_path)
            log.error(f"Code change failed for {filepath}: {result}")
    else:
        print("  Skipped!")
        log.debug(f"User skipped code change for {filepath}")


# -- MAIN --
def main():
    print("\nAI Code Manager - powered by Claude")
    print("=" * 50)
    print("What you can do:")
    print("  -> add error logging to uptime_monitor.py")
    print("  -> add retry logic when a site is DOWN")
    print("  -> change timeout from 15 to 30 seconds")
    print("  -> add a new function to db_manager.py")
    print("\nCommands:")
    print("  list files     -> show all managed files")
    print("  show backups   -> show all backups")
    print("  restore        -> restore a backup")
    print("  clear          -> reset conversation")
    print("  exit           -> quit")
    print("=" * 50)

    log.info("code_manager started")
    conversation_history = []
    current_file = None

    while True:
        print()
        user_input = input("You -> ").strip()

        if not user_input:
            continue

        if user_input.lower() == "exit":
            log.info("code_manager exited by user")
            print("Bye!")
            break

        if user_input.lower() == "clear":
            conversation_history = []
            current_file = None
            print("  Conversation cleared!")
            log.debug("Conversation cleared")
            continue

        if user_input.lower() == "list files":
            print("\n  Managed files:")
            for name, path in MANAGED_FILES.items():
                exists = "exists" if os.path.exists(path) else "not found"
                print(f"    {name} -> {path} ({exists})")
            continue

        if user_input.lower() == "show backups":
            backups = list_backups()
            if backups:
                print("\n  Available backups:")
                for i, b in enumerate(backups):
                    print(f"    {i+1}. {b}")
            else:
                print("  No backups found!")
            continue

        if user_input.lower() == "restore":
            backups = list_backups()
            if not backups:
                print("  No backups found!")
                continue
            print("\n  Available backups:")
            for i, b in enumerate(backups):
                print(f"    {i+1}. {b}")
            choice = input("\n  Enter number to restore -> ").strip()
            try:
                backup_path = backups[int(choice) - 1]
                success, result = restore_backup(backup_path)
                if success:
                    print(f"  Restored {result} from backup!")
                else:
                    print(f"  Failed: {result}")
            except:
                print("  Invalid choice!")
            continue

        detected_file = None
        for name, path in MANAGED_FILES.items():
            if name in user_input.lower() or path in user_input.lower():
                detected_file = path
                break

        if not detected_file and not current_file:
            print("\n  Which file do you want to modify?")
            for i, (name, path) in enumerate(MANAGED_FILES.items()):
                print(f"    {i+1}. {path}")
            choice = input("  Enter number -> ").strip()
            try:
                detected_file = list(MANAGED_FILES.values())[int(choice) - 1]
                current_file = detected_file
            except:
                print("  Invalid choice!")
                continue
        elif detected_file:
            current_file = detected_file

        filepath = current_file
        file_content = read_file(filepath)

        if file_content is None:
            print(f"  Error: {filepath} not found")
            continue

        print(f"\n  Working on: {filepath}")
        print("  Claude is thinking...")
        log.debug(f"Processing request for {filepath}: {user_input[:60]}")

        try:
            response, conversation_history = ask_claude_to_modify(
                user_input,
                filepath,
                file_content,
                conversation_history
            )
            parsed = parse_response(response)

            if parsed["type"] in ["CODE_CHANGE", "CODE_ADDITION"]:
                handle_code_change(parsed)
            elif parsed["type"] == "QUESTION":
                print(f"\n  Claude needs clarification:")
                print(f"  {parsed['explanation']}")
            else:
                print(f"\n  Claude says:")
                print("  " + "-" * 45)
                print(f"  {parsed['explanation']}")
                print("  " + "-" * 45)
        except Exception as e:
            log.error(f"Unexpected error in code_manager: {str(e)}")
            print(f"  Something went wrong: {str(e)}")


if __name__ == "__main__":
    main()
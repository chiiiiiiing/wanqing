#!/usr/bin/env python3
"""
Action-based intent test runner.
Instead of checking JSON output, checks if the Agent actually PERFORMED the right action
(created scheduler, gave correct reply, etc.)
"""
import json
import os
import re
import sys
import time
import requests
from datetime import datetime

BASE_URL = os.environ.get("AGENT_STACK_BASE_URL", "https://ventured-agent-stack.pingcap.cn")
API_KEY = os.environ.get("AGENT_STACK_USER_API_KEY", "")
PROJECT_ID = os.environ.get("AGENT_STACK_PROJECT_ID", "proj_6c440f8173104d06b005d9c552bfe774")
AGENT_ID = os.environ.get("AGENT_STACK_AGENT_ID", "agent_cc0aa5c6ff600adf4d6c31718e3fc9bb")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "x-agent9-project-id": PROJECT_ID,
    "Content-Type": "application/json",
}


def create_session():
    resp = requests.post(f"{BASE_URL}/api/sessions", headers=HEADERS, json={"agentId": AGENT_ID})
    resp.raise_for_status()
    return resp.json()["session"]["sessionId"]


def send_turn(session_id, text):
    resp = requests.post(
        f"{BASE_URL}/api/sessions/{session_id}/turns",
        headers=HEADERS,
        json={"input": {"type": "text", "text": text}},
        stream=True,
    )
    resp.raise_for_status()

    assistant_text = ""
    events = []
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.strip():
            continue
        try:
            event = json.loads(line)
            events.append(event)
            if event.get("event") == "assistant_message":
                assistant_text = event["payload"]["text"]
        except json.JSONDecodeError:
            continue

    return assistant_text, events


def list_schedulers():
    resp = requests.get(
        f"{BASE_URL}/api/schedulers",
        headers=HEADERS,
    )
    resp.raise_for_status()
    return resp.json().get("schedulers", [])


def delete_scheduler(scheduler_id):
    """Delete a scheduler (cleanup)."""
    try:
        resp = requests.delete(
            f"{BASE_URL}/api/schedulers/{scheduler_id}",
            headers=HEADERS,
            params={"x-agent9-project-id": PROJECT_ID},
        )
    except Exception:
        pass


def evaluate_response(test, response_text, events, schedulers_before, schedulers_after):
    """Evaluate if the Agent did the right thing."""
    expected_intent = test["intent"]
    expected = test.get("expected", {})
    checks = []

    # Check 1: Response is not empty
    if not response_text.strip():
        checks.append(("non_empty_response", False, "Empty response"))
    else:
        checks.append(("non_empty_response", True, ""))

    # Check 2: Response is in Chinese (no English except proper nouns)
    english_words = re.findall(r'[a-zA-Z]{4,}', response_text)
    # Filter out common abbreviations
    english_words = [w for w in english_words if w.lower() not in ('task', 'json', 'create', 'note')]
    if len(english_words) > 3:
        checks.append(("chinese_response", False, f"Too many English words: {english_words}"))
    else:
        checks.append(("chinese_response", True, ""))

    # Check 3: For CREATE_TASK, check if scheduler was created
    if expected_intent == "CREATE_TASK":
        new_schedulers = len(schedulers_after) - len(schedulers_before)
        scheduler_created = new_schedulers > 0

        # Also check if response mentions setting a reminder
        reminder_keywords = ["提醒", "记", "安排", "设置", "闹钟", "提醒您"]
        mentioned_reminder = any(kw in response_text for kw in reminder_keywords)

        if scheduler_created or mentioned_reminder:
            checks.append(("task_action", True, ""))
        else:
            checks.append(("task_action", False, "No scheduler created or reminder mentioned"))

        # Check if title keyword appears
        title = expected.get("title", "")
        if title and title != "delay_current":
            if title in response_text or any(c in response_text for c in title):
                checks.append(("title_in_response", True, ""))
            else:
                checks.append(("title_in_response", False, f"Title '{title}' not found"))

    # Check 4: For CREATE_NOTE, check response mentions recording
    elif expected_intent == "CREATE_NOTE":
        note_keywords = ["记", "好", "备忘", "记住", "帮你"]
        if any(kw in response_text for kw in note_keywords):
            checks.append(("note_acknowledged", True, ""))
        else:
            checks.append(("note_acknowledged", False, "No note acknowledgment"))

    # Check 5: For QUERY_TASK, check response mentions tasks/events
    elif expected_intent == "QUERY_TASK":
        query_keywords = ["事", "安排", "任务", "提醒", "没有"]
        if any(kw in response_text for kw in query_keywords):
            checks.append(("query_response", True, ""))
        else:
            checks.append(("query_response", False, "No query response"))

    # Check 6: Response is concise (not too long for elderly users)
    if len(response_text) > 300:
        checks.append(("concise", False, f"Too long ({len(response_text)} chars)"))
    else:
        checks.append(("concise", True, ""))

    return checks


def run_test(test_file, limit=None, delay=1.0):
    with open(test_file) as f:
        tests = json.load(f)

    if limit:
        tests = tests[:limit]

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S %A")
    print(f"=== 晚晴 Action-Based Intent Test ===")
    print(f"Time: {now}")
    print(f"Tests: {len(tests)}")
    print()

    total_checks = 0
    passed_checks = 0
    test_results = []

    for i, test in enumerate(tests):
        test_id = test["id"]
        expected_intent = test["intent"]
        user_input = test["input"]

        # Snapshot schedulers before
        sched_before = list_schedulers()

        # Create session and send input
        session_id = create_session()
        response_text, events = send_turn(session_id, user_input)

        # Snapshot schedulers after
        sched_after = list_schedulers()

        # Evaluate
        checks = evaluate_response(test, response_text, events, sched_before, sched_after)

        all_passed = all(c[1] for c in checks)
        total_checks += len(checks)
        passed_checks += sum(1 for c in checks if c[1])

        emoji = "✅" if all_passed else "⚠️"
        print(f"  {emoji} #{test_id:3d} [{expected_intent:15s}] {user_input}")

        if not all_passed:
            for name, passed, detail in checks:
                if not passed:
                    print(f"          ❌ {name}: {detail}")

        # Show truncated response
        clean_resp = response_text.replace('\n', ' ')[:100]
        print(f"          💬 {clean_resp}")
        print()

        test_results.append({
            "id": test_id,
            "input": user_input,
            "expected_intent": expected_intent,
            "response": response_text,
            "checks": [(n, p, d) for n, p, d in checks],
            "all_passed": all_passed,
            "schedulers_created": len(sched_after) - len(sched_before),
        })

        time.sleep(delay)

    # Summary
    print("=" * 60)
    tests_passed = sum(1 for r in test_results if r["all_passed"])
    print(f"Tests passed: {tests_passed}/{len(test_results)}")
    print(f"Checks passed: {passed_checks}/{total_checks} ({passed_checks/total_checks*100:.1f}%)")

    # Save results
    output_file = test_file.replace(".json", "_action_results.json")
    with open(output_file, "w") as f:
        json.dump(test_results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    test_file = os.path.join(os.path.dirname(__file__), "test_sentences.json")
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    delay = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    run_test(test_file, limit=limit, delay=delay)

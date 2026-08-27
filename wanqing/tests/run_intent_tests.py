#!/usr/bin/env python3
"""
Intent parsing test runner for 晚晴.
Sends test sentences to Agent Stack and evaluates responses.
"""
import json
import os
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

SYSTEM_CONTEXT = """你是一个专门为老年人设计的AI助手（晚晴）。
当前时间：{now}（北京时间 UTC+8）

你的职责是帮老人管理日常事务。对每句话，你需要：
1. 判断意图类型：CREATE_TASK / CREATE_NOTE / QUERY_TASK / COMPLETE_TASK / DELAY_TASK / GENERAL_QA / UNKNOWN
2. 提取关键信息
3. 给出简短温暖的回复

请用以下JSON格式回复（在回复文本之前输出）：
```json
{{
  "intent": "意图类型",
  "confidence": 0.0-1.0,
  "extracted": {{}},
  "reply": "给老人的回复"
}}
```
""".strip()


def create_session():
    """Create a new session for testing."""
    resp = requests.post(
        f"{BASE_URL}/api/sessions",
        headers=HEADERS,
        json={"agentId": AGENT_ID},
    )
    resp.raise_for_status()
    return resp.json()["session"]["sessionId"]


def send_turn(session_id, text):
    """Send a text turn and collect the assistant message."""
    resp = requests.post(
        f"{BASE_URL}/api/sessions/{session_id}/turns",
        headers=HEADERS,
        json={"input": {"type": "text", "text": text}},
        stream=True,
    )
    resp.raise_for_status()

    assistant_text = ""
    turn_status = None
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.strip():
            continue
        try:
            event = json.loads(line)
            if event.get("event") == "assistant_message":
                assistant_text = event["payload"]["text"]
            elif event.get("event") == "turn_finished":
                turn_status = event["payload"]["status"]
        except json.JSONDecodeError:
            continue

    return assistant_text, turn_status


def extract_json_from_response(text):
    """Try to extract JSON from the response text."""
    # Look for JSON block
    import re
    json_match = re.search(r'```json\s*\n?(.*?)\n?```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find JSON directly
    brace_count = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if brace_count == 0:
                start = i
            brace_count += 1
        elif ch == '}':
            brace_count -= 1
            if brace_count == 0 and start >= 0:
                try:
                    return json.loads(text[start:i+1])
                except json.JSONDecodeError:
                    start = -1

    return None


def run_test(test_file, limit=None, delay=1.0):
    """Run intent parsing tests."""
    with open(test_file) as f:
        tests = json.load(f)

    if limit:
        tests = tests[:limit]

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S %A")
    print(f"=== 晚晴 Intent Parsing Test ===")
    print(f"Time: {now}")
    print(f"Tests: {len(tests)}")
    print(f"Agent: {AGENT_ID}")
    print()

    # Create a fresh session for each test batch
    session_id = create_session()
    print(f"Session: {session_id}")
    print()

    # Send system context first
    sys_msg = SYSTEM_CONTEXT.format(now=now) + "\n\n请先确认你理解了你的角色。"
    send_turn(session_id, sys_msg)

    results = []
    passed = 0
    total = 0

    for test in tests:
        test_id = test["id"]
        expected_intent = test["intent"]
        user_input = test["input"]

        # Create new session for each test to avoid context pollution
        session_id = create_session()

        # Send system context
        sys_msg = SYSTEM_CONTEXT.format(now=now)
        send_turn(session_id, sys_msg)
        time.sleep(0.5)

        # Send the actual test input
        response_text, status = send_turn(session_id, user_input)

        # Extract intent from response
        parsed = extract_json_from_response(response_text)

        if parsed:
            actual_intent = parsed.get("intent", "PARSE_ERROR")
            confidence = parsed.get("confidence", 0)
            intent_match = actual_intent == expected_intent
        else:
            actual_intent = "NO_JSON"
            confidence = 0
            intent_match = False

        total += 1
        if intent_match:
            passed += 1

        status_emoji = "✅" if intent_match else "❌"
        print(f"  {status_emoji} #{test_id:3d} | {user_input}")
        print(f"          Expected: {expected_intent} | Got: {actual_intent} (conf: {confidence})")
        if not intent_match:
            print(f"          Response: {response_text[:120]}...")
        print()

        results.append({
            "id": test_id,
            "input": user_input,
            "expected_intent": expected_intent,
            "actual_intent": actual_intent,
            "confidence": confidence,
            "match": intent_match,
            "response": response_text[:200],
            "parsed": parsed,
        })

        time.sleep(delay)

    # Summary
    print("=" * 60)
    print(f"Results: {passed}/{total} passed ({passed/total*100:.1f}%)")

    # Breakdown by intent type
    from collections import Counter
    by_intent = {}
    for r in results:
        intent = r["expected_intent"]
        if intent not in by_intent:
            by_intent[intent] = {"total": 0, "passed": 0}
        by_intent[intent]["total"] += 1
        if r["match"]:
            by_intent[intent]["passed"] += 1

    print("\nBreakdown by intent type:")
    for intent, counts in sorted(by_intent.items()):
        pct = counts["passed"] / counts["total"] * 100
        print(f"  {intent:20s}: {counts['passed']}/{counts['total']} ({pct:.0f}%)")

    # Save results
    output_file = test_file.replace(".json", "_results.json")
    with open(output_file, "w") as f:
        json.dump({"summary": {"passed": passed, "total": total}, "results": results}, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    test_file = os.path.join(os.path.dirname(__file__), "test_sentences.json")
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    delay = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    run_test(test_file, limit=limit, delay=delay)

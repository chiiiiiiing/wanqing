#!/usr/bin/env python3
"""
晚晴 — End-to-End Demo & Validation Script

Tests the full stack:
1. Agent Stack NLU (intent parsing via text turns)
2. Agent Stack Scheduler (built-in reminder creation)
3. MCP Server tools (task/note persistence)
4. Database operations (CRUD verification)

Usage:
  python demo_e2e.py [--skip-agent] [--skip-mcp]
"""
import os
import sys
import json
import time
import argparse
import requests
from datetime import datetime, timezone, timedelta

# Config
BASE_URL = "https://ventured-agent-stack.pingcap.cn"
API_KEY = os.environ.get("AGENT_STACK_KEY", "ag9_uak_b4033a4c104043f7befd33a9aa47afcc_Uf80W8EBjFdAqD2YLeGgADEYOXgF37mKvIaVJS4eZ3g")
PROJECT_ID = "proj_6c440f8173104d06b005d9c552bfe774"
AGENT_ID = "agent_cc0aa5c6ff600adf4d6c31718e3fc9bb"
MCP_URL = os.environ.get("MCP_URL", "http://localhost:8200/mcp")

CST = timezone(timedelta(hours=8))
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "x-agent9-project-id": PROJECT_ID,
    "Content-Type": "application/json",
}

# ── Colors ──
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def ok(msg): print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg): print(f"  {RED}✗{RESET} {msg}")
def info(msg): print(f"  {CYAN}ℹ{RESET} {msg}")
def header(msg): print(f"\n{BOLD}{msg}{RESET}")


# ── Agent Stack Tests ──

def create_session():
    """Create a new Agent Stack session."""
    resp = requests.post(
        f"{BASE_URL}/api/sessions",
        headers=HEADERS,
        json={"agentId": AGENT_ID},
        params={},  # idempotency via query not needed
    )
    # Add idempotency key
    resp = requests.post(
        f"{BASE_URL}/api/sessions",
        headers={**HEADERS, "Idempotency-Key": f"demo-{int(time.time())}"},
        json={"agentId": AGENT_ID},
    )
    data = resp.json()
    return data["session"]["sessionId"]


def send_turn(session_id, text, timeout=60):
    """Send a text turn and collect the response."""
    resp = requests.post(
        f"{BASE_URL}/api/sessions/{session_id}/turns",
        headers=HEADERS,
        json={"input": {"type": "text", "text": text}},
        stream=True,
        timeout=timeout,
    )

    result = {
        "drafts": [],
        "message": "",
        "operations": [],
        "status": "unknown",
        "turn_id": None,
    }

    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.strip():
            continue
        try:
            event = json.loads(line)
            kind = event.get("event", "")

            if kind == "turn_started":
                result["turn_id"] = event.get("turnId")
            elif kind == "assistant_draft":
                result["drafts"].append(event.get("payload", {}).get("text", ""))
            elif kind == "assistant_message":
                result["message"] = event.get("payload", {}).get("text", "")
            elif kind == "operation_step":
                payload = event.get("payload", {})
                result["operations"].append({
                    "label": payload.get("label", ""),
                    "status": payload.get("status", ""),
                })
            elif kind == "turn_finished":
                result["status"] = event.get("payload", {}).get("status", "")
        except json.JSONDecodeError:
            pass

    return result


# ── MCP Server Tests ──

class MCPClient:
    """Simple MCP client using streamable HTTP."""

    def __init__(self, url):
        self.url = url
        self.session_id = None
        self._id = 0

    def _next_id(self):
        self._id += 1
        return self._id

    def initialize(self):
        resp = requests.post(
            self.url,
            headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
            json={
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "demo-client", "version": "1.0"},
                },
                "id": self._next_id(),
            },
        )
        self.session_id = resp.headers.get("mcp-session-id")
        return self.session_id is not None

    def list_tools(self):
        resp = requests.post(
            self.url,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Mcp-Session-Id": self.session_id,
            },
            json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": self._next_id()},
        )
        for line in resp.text.strip().split("\n"):
            if line.startswith("data: "):
                data = json.loads(line[6:])
                return data.get("result", {}).get("tools", [])
        return []

    def call_tool(self, name, arguments):
        resp = requests.post(
            self.url,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Mcp-Session-Id": self.session_id,
            },
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
                "id": self._next_id(),
            },
        )
        for line in resp.text.strip().split("\n"):
            if line.startswith("data: "):
                data = json.loads(line[6:])
                result = data.get("result", {})
                content = result.get("content", [])
                if content:
                    return content[0].get("text", "")
                return str(result)
        return "No response"


# ── Test Scenarios ──

def test_mcp_tools():
    """Test all MCP tools directly."""
    header("📦 MCP Server Tools Test")

    client = MCPClient(MCP_URL)
    if not client.initialize():
        fail("Cannot connect to MCP server")
        return False

    ok(f"MCP server connected (session: {client.session_id[:8]}...)")

    tools = client.list_tools()
    tool_names = [t["name"] for t in tools]
    expected = ["create_task", "create_note", "query_tasks", "complete_task", "delay_task"]
    for name in expected:
        if name in tool_names:
            ok(f"Tool registered: {name}")
        else:
            fail(f"Tool missing: {name}")

    # Test create_task
    now = datetime.now(CST)
    tomorrow_3pm = (now + timedelta(days=1)).replace(hour=15, minute=0, second=0).isoformat()
    result = client.call_tool("create_task", {
        "title": "Demo测试买菜",
        "due_time": tomorrow_3pm,
        "category": "life",
    })
    if len(result) > 10 and "error" not in result.lower():
        ok(f"create_task: {result.encode('utf-8', errors='replace').decode('ascii', errors='replace')[:60]}...")
    else:
        fail(f"create_task: {result}")

    # Test create_note
    result = client.call_tool("create_note", {
        "content": "王医生电话：13800138000",
        "category": "contact",
    })
    if len(result) > 10 and "error" not in result.lower():
        ok(f"create_note: {result.encode('utf-8', errors='replace').decode('ascii', errors='replace')[:60]}...")
    else:
        fail(f"create_note: {result}")

    # Test query_tasks
    result = client.call_tool("query_tasks", {})
    if len(result) > 5:
        ok(f"query_tasks: returned {len(result)} chars")
    else:
        fail(f"query_tasks: {result}")

    # Test complete_task
    result = client.call_tool("complete_task", {"title_keyword": "Demo测试买菜"})
    if len(result) > 10 and "error" not in result.lower():
        ok(f"complete_task: ok")
    else:
        fail(f"complete_task: {result}")

    # Test delay_task
    client.call_tool("create_task", {
        "title": "Demo吃药",
        "due_time": tomorrow_3pm,
        "category": "health",
    })
    result = client.call_tool("delay_task", {"title_keyword": "Demo吃药", "minutes": 60})
    if len(result) > 10 and "error" not in result.lower():
        ok(f"delay_task: ok")
    else:
        fail(f"delay_task: {result}")

    return True


def test_agent_nlu(scenarios):
    """Test Agent NLU via text turns."""
    header("🤖 Agent NLU Test")

    session_id = create_session()
    ok(f"Session created: {session_id[:16]}...")

    passed = 0
    for i, scenario in enumerate(scenarios):
        text = scenario["input"]
        expect_keyword = scenario.get("expect_keyword", "")
        intent = scenario.get("intent", "")

        info(f"[{i+1}] \"{text}\"")
        try:
            result = send_turn(session_id, text, timeout=45)
            msg = result["message"]

            if result["status"] == "succeeded":
                if expect_keyword and expect_keyword in msg:
                    ok(f"→ {msg[:100]}")
                    passed += 1
                elif not expect_keyword:
                    ok(f"→ {msg[:100]}")
                    passed += 1
                else:
                    fail(f"→ {msg[:100]} (expected: {expect_keyword})")
            else:
                fail(f"Turn failed: {result['status']}")
        except Exception as e:
            fail(f"Error: {e}")

        # Small delay between turns
        time.sleep(1)

        # Create new session every 3 turns to avoid context pollution
        if (i + 1) % 3 == 0 and i + 1 < len(scenarios):
            session_id = create_session()

    print(f"\n  NLU Score: {passed}/{len(scenarios)}")
    return passed == len(scenarios)


def test_scheduler_integration():
    """Test that Agent creates Schedulers."""
    header("⏰ Scheduler Integration Test")

    session_id = create_session()
    ok(f"Session: {session_id[:16]}...")

    info("Sending: '明天下午三点提醒我吃降压药'")
    result = send_turn(session_id, "明天下午三点提醒我吃降压药", timeout=45)

    if result["status"] == "succeeded":
        ok(f"Agent response: {result['message'][:200]}")
    else:
        fail(f"Turn failed: {result['status']}")

    # Check if Scheduler was created
    sched_resp = requests.get(
        f"{BASE_URL}/api/schedulers",
        headers=HEADERS,
        params={"limit": 5},
    )
    schedulers = sched_resp.json().get("schedulers", [])
    recent = [s for s in schedulers if "降压药" in s.get("title", "")]
    if recent:
        ok(f"Scheduler found: {recent[0]['title']} (id: {recent[0]['id'][:16]}...)")
    else:
        info(f"No Scheduler with '降压药' found. Total schedulers: {len(schedulers)}")
        if schedulers:
            info(f"Latest: {schedulers[0].get('title', 'untitled')}")


def main():
    parser = argparse.ArgumentParser(description="晚晴 E2E Demo")
    parser.add_argument("--skip-agent", action="store_true", help="Skip Agent NLU tests")
    parser.add_argument("--skip-mcp", action="store_true", help="Skip MCP tool tests")
    parser.add_argument("--skip-scheduler", action="store_true", help="Skip Scheduler tests")
    args = parser.parse_args()

    print(f"{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  晚晴 — End-to-End Demo{RESET}")
    print(f"{BOLD}  {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S CST')}{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    if not args.skip_mcp:
        test_mcp_tools()

    if not args.skip_scheduler:
        test_scheduler_integration()

    if not args.skip_agent:
        scenarios = [
            {"input": "今天天气怎么样", "intent": "GENERAL_QA", "expect_keyword": ""},
            {"input": "帮我记一下，冰箱里有三个苹果", "intent": "CREATE_NOTE", "expect_keyword": ""},
            {"input": "我刚才让你记了什么事", "intent": "QUERY_TASK", "expect_keyword": ""},
        ]
        test_agent_nlu(scenarios)

    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  Demo complete!{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")


if __name__ == "__main__":
    main()

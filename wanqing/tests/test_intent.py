#!/usr/bin/env python3
"""
晚晴 — 意图解析自动化测试
通过 Agent Stack API 批量测试意图识别能力。
评测口径：校验 Agent 实际调用的工具（tool_calls）及参数，
而非要求模型输出结构化意图标签（与线上对话式体验一致）。

凭证从环境变量读取（参见 ../.env.example），禁止硬编码：
  export AGENT_STACK_USER_API_KEY=...
"""

import json
import os
import time
from datetime import datetime
from typing import Optional

# Agent Stack API 配置（凭证一律走环境变量）
BASE_URL = os.environ.get("AGENT_STACK_BASE_URL", "https://ventured-agent-stack.pingcap.cn")
PROJECT_ID = os.environ.get("AGENT_STACK_PROJECT_ID", "")
AGENT_ID = os.environ.get("AGENT_STACK_AGENT_ID", "")
API_KEY = os.environ.get("AGENT_STACK_USER_API_KEY", "")

# 意图 → 期望工具名映射（评测口径：看真实工具调用，不看意图标签）
INTENT_TOOL_MAP = {
    "CREATE_TASK": "create_task",
    "CREATE_NOTE": "create_note",
    "QUERY_TASK": "query_tasks",
    "COMPLETE_TASK": "complete_task",
    "DELAY_TASK": "delay_task",
    "GENERAL_QA": None,  # 无工具调用，直接回复即算正确
}

def parse_test_cases(file_path: str) -> list:
    """解析测试用例文件"""
    cases = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # 格式: 1. "语句" | INTENT | params
            if '. "' in line and '|' in line:
                parts = line.split('. "', 1)
                if len(parts) == 2:
                    rest = parts[1]
                    content_parts = rest.split('" | ', 1)
                    if len(content_parts) == 2:
                        text = content_parts[0]
                        expected = content_parts[1].split(' | ')
                        intent = expected[0].strip() if expected else ""
                        params = expected[1].strip() if len(expected) > 1 else ""
                        cases.append({
                            'text': text,
                            'expected_intent': intent,
                            'expected_params': params
                        })
    return cases

def send_text_turn(text: str, session_id: str) -> dict:
    """发送文本消息到 Agent"""
    import subprocess
    
    url = f"{BASE_URL}/api/sessions/{session_id}/turns"
    payload = json.dumps({"input": {"type": "text", "text": text}})
    
    cmd = [
        'curl', '-s', '-X', 'POST', url,
        '-H', f'Authorization: Bearer {API_KEY}',
        '-H', f'x-agent9-project-id: {PROJECT_ID}',
        '-H', 'Content-Type: application/json',
        '-H', 'Accept: application/x-ndjson',
        '-d', payload
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    
    # 解析 NDJSON 响应
    response_data = {
        'intent': None,
        'tool_calls': [],
        'reply': '',
        'error': None
    }
    
    if result.returncode != 0:
        response_data['error'] = f"curl failed: {result.stderr}"
        return response_data
    
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        try:
            event = json.loads(line)
            event_type = event.get('event')  # 注意：是 'event' 不是 'type'
            
            if event_type == 'assistant_message':
                response_data['reply'] = event.get('payload', {}).get('text', '')
            elif event_type == 'tool_call':
                response_data['tool_calls'].append({
                    'tool': event.get('payload', {}).get('tool_name'),
                    'params': event.get('payload', {}).get('parameters', {})
                })
            elif event_type == 'error':
                response_data['error'] = event.get('payload', {}).get('message', 'Unknown error')
                
        except json.JSONDecodeError:
            continue
    
    return response_data

def create_session() -> str:
    """创建新的测试 session"""
    import subprocess
    
    url = f"{BASE_URL}/api/sessions"
    cmd = [
        'curl', '-s', '-X', 'POST', url,
        '-H', f'Authorization: Bearer {API_KEY}',
        '-H', f'x-agent9-project-id: {PROJECT_ID}',
        '-H', 'Content-Type: application/json',
        '-d', json.dumps({"agentId": AGENT_ID})
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
        try:
            data = json.loads(result.stdout)
            return data.get('session', {}).get('sessionId', '')
        except:
            pass
    return ''

def _check_params(expected_params: str, actual: dict):
    """校验工具参数是否包含期望的关键词（宽松匹配）。
    期望格式如: title=买菜, due_time=明天15:00, category=生活
    目前仅对 title=/content= 关键词做子串校验，时间/分类记录为提示不判错。
    """
    if not expected_params:
        return True, ""
    for kv in expected_params.split(','):
        kv = kv.strip()
        if '=' not in kv:
            continue
        key, val = kv.split('=', 1)
        key, val = key.strip(), val.strip()
        if key in ('title', 'content', 'task_ref'):
            hay = ' '.join(str(v) for v in actual.values())
            # 期望值取核心名词：去掉 "明天/后天/今天" 等时间前缀后做子串匹配
            core = val
            for prefix in ('明天', '后天', '今天', '本周', '下周'):
                core = core.replace(prefix, '')
            core = core.strip()
            if core and core not in hay:
                return False, f"参数 {key} 未包含 '{val}'（实际: {hay[:60]}）"
    return True, f" | 参数: {json.dumps(actual, ensure_ascii=False)[:80]}"


def run_tests(test_file: str, start: int = 1, end: int = 100, delay: float = 1.0):
    """运行测试"""
    print(f"=" * 60)
    print(f"晚晴 — 意图解析测试")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"=" * 60)
    
    # 解析测试用例
    cases = parse_test_cases(test_file)
    print(f"\n共加载 {len(cases)} 条测试用例")
    print(f"测试范围: #{start} - #{end}")
    
    # 创建 session
    print("\n创建测试 session...")
    session_id = create_session()
    if not session_id:
        print("❌ 无法创建 session")
        return
    
    print(f"✅ Session: {session_id}")
    
    # 统计
    results = {
        'total': 0,
        'correct': 0,
        'incorrect': 0,
        'errors': 0
    }
    
    # 运行测试
    print("\n" + "=" * 60)
    print("开始测试")
    print("=" * 60 + "\n")
    
    for i, case in enumerate(cases[start-1:end], start=start):
        results['total'] += 1
        
        text = case['text']
        expected = case['expected_intent']
        
        print(f"[{i:3d}] {text}")
        print(f"     期望: {expected}")
        
        try:
            response = send_text_turn(text, session_id)
            
            if response['error']:
                print(f"     ❌ 错误: {response['error']}")
                results['errors'] += 1
            else:
                expected_tool = INTENT_TOOL_MAP.get(expected)
                detected_tools = [tc['tool'] for tc in response['tool_calls'] if tc.get('tool')]

                if expected_tool is None:
                    # GENERAL_QA：不产生工具调用，直接回复即算正确
                    reply_preview = response['reply'][:50] + "..." if len(response['reply']) > 50 else response['reply']
                    if not detected_tools and response['reply']:
                        print(f"     ✅ 回复: {reply_preview}")
                        results['correct'] += 1
                    else:
                        print(f"     ⚠️  期望直接回复，实际工具调用: {detected_tools or '(空回复)'}")
                        results['incorrect'] += 1
                elif expected_tool in detected_tools:
                    # 工具命中，再校验关键参数（期望中的 title=/content= 关键词）
                    tc = next(t for t in response['tool_calls'] if t.get('tool') == expected_tool)
                    param_ok, param_note = _check_params(case['expected_params'], tc.get('params', {}))
                    if param_ok:
                        print(f"     ✅ 工具: {expected_tool}{param_note}")
                        results['correct'] += 1
                    else:
                        print(f"     ⚠️  工具正确但参数不符: {param_note}")
                        results['incorrect'] += 1
                else:
                    reply_preview = response['reply'][:50] if response['reply'] else '(无回复)'
                    print(f"     ⚠️  期望工具 {expected_tool}，实际: {detected_tools or '无调用'} | {reply_preview}")
                    results['incorrect'] += 1
                    
        except Exception as e:
            print(f"     ❌ 异常: {e}")
            results['errors'] += 1
        
        time.sleep(delay)
        print()
    
    # 打印结果
    print("=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    print(f"总计: {results['total']}")
    print(f"✅ 正确: {results['correct']} ({results['correct']/results['total']*100:.1f}%)")
    print(f"⚠️  错误: {results['incorrect']} ({results['incorrect']/results['total']*100:.1f}%)")
    print(f"❌ 异常: {results['errors']} ({results['errors']/results['total']*100:.1f}%)")
    print("=" * 60)
    
    # 保存结果
    result_file = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'session_id': session_id,
            'results': results,
            'test_range': f"{start}-{end}"
        }, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {result_file}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="晚晴意图解析测试")
    parser.add_argument('--start', type=int, default=1, help='起始测试编号')
    parser.add_argument('--end', type=int, default=10, help='结束测试编号')
    parser.add_argument('--delay', type=float, default=1.0, help='测试间隔(秒)')
    parser.add_argument('--file', default='intent_test_cases.txt', help='测试用例文件')
    
    args = parser.parse_args()

    missing = [k for k, v in {
        "AGENT_STACK_USER_API_KEY": API_KEY,
        "AGENT_STACK_PROJECT_ID": PROJECT_ID,
        "AGENT_STACK_AGENT_ID": AGENT_ID,
    }.items() if not v]
    if missing:
        raise SystemExit(f"缺少环境变量: {', '.join(missing)}（参见 ../.env.example）")

    run_tests(args.file, args.start, args.end, args.delay)

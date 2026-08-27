#!/usr/bin/env python3
"""
银龄AI助手 — 意图解析自动化测试
通过 Agent Stack API 批量测试意图识别能力
"""

import json
import time
from datetime import datetime
from typing import Optional

# Agent Stack API 配置
BASE_URL = "https://ventured-agent-stack.pingcap.cn"
PROJECT_ID = "proj_6c440f8173104d06b005d9c552bfe774"
AGENT_ID = "agent_cc0aa5c6ff600adf4d6c31718e3fc9bb"
API_KEY = "ag9_uak_b4033a4c104043f7befd33a9aa47afcc_Uf80W8EBjFdAqD2YLeGgADEYOXgF37mKvIaVJS4eZ3g"

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

def run_tests(test_file: str, start: int = 1, end: int = 100, delay: float = 1.0):
    """运行测试"""
    print(f"=" * 60)
    print(f"银龄AI助手 — 意图解析测试")
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
            elif response['tool_calls']:
                # 提取意图
                tool_names = [tc['tool'] for tc in response['tool_calls']]
                detected = ', '.join(tool_names)
                
                # 简单匹配
                if expected in detected or detected in expected:
                    print(f"     ✅ 检测: {detected}")
                    results['correct'] += 1
                else:
                    print(f"     ⚠️  检测: {detected} (期望: {expected})")
                    results['incorrect'] += 1
            else:
                # 没有工具调用，可能是 GENERAL_QA
                reply_preview = response['reply'][:50] + "..." if len(response['reply']) > 50 else response['reply']
                if expected == "GENERAL_QA":
                    print(f"     ✅ 回复: {reply_preview}")
                    results['correct'] += 1
                else:
                    print(f"     ⚠️  回复: {reply_preview} (期望: {expected})")
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
    
    parser = argparse.ArgumentParser(description="银龄AI助手意图解析测试")
    parser.add_argument('--start', type=int, default=1, help='起始测试编号')
    parser.add_argument('--end', type=int, default=10, help='结束测试编号')
    parser.add_argument('--delay', type=float, default=1.0, help='测试间隔(秒)')
    parser.add_argument('--file', default='intent_test_cases.txt', help='测试用例文件')
    
    args = parser.parse_args()
    
    run_tests(args.file, args.start, args.end, args.delay)

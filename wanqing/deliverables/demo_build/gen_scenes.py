# -*- coding: utf-8 -*-
"""家人关注演示视频 — 场景与旁白生成器

用法：python3 gen_scenes.py <out_dir>
生成 8 个 1280x720 场景 HTML 与对应旁白文本（Tingting 中文语音）。
配合 build_demo.sh 渲染 PNG、合成语音、拼接 MP4。

布局：纯 flex 流式（headless 渲染下 position:absolute 表现不稳定，弃用）。
body = 纵向 flex：brand(顶) → main(中, flex:1 垂直居中) → cap → pageno(底)。
"""
import json
import os
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/demoscenes"
os.makedirs(OUT, exist_ok=True)
rep = json.load(open(os.path.join(OUT, "report.json")))
e, t = rep["elder"], rep["today"]
hrs = e["hours_since_interaction"]
pend = "、".join(x["title"] for x in t["tasks_pending"][:4]) or "无"
done_n = len(t["tasks_completed"])
push_n = len(t["reminders_pushed"])

HEAD = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><style>
*{margin:0;padding:0;box-sizing:border-box;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
body{width:1280px;height:720px;overflow:hidden;background:#faf7f2;color:#1f2937;display:flex;flex-direction:column;padding:24px 48px 16px}
.brand{font-size:20px;color:#9a3412;font-weight:700;letter-spacing:1px}
.main{flex:1;display:flex;flex-direction:column;justify-content:center;min-height:0}
.pageno{align-self:flex-end;font-size:16px;color:#9ca3af}
h1{font-size:64px;color:#7c2d12;text-align:center}
.sub{font-size:30px;color:#6b7280;text-align:center;margin-top:28px}
.cap{text-align:center;font-size:30px;color:#374151;font-weight:600;margin:4px 0 6px}
.card{background:#fff;border-radius:20px;box-shadow:0 2px 10px rgba(0,0,0,.07)}
.orange{color:#ea580c}
img.web{border-radius:18px;box-shadow:0 4px 18px rgba(0,0,0,.15)}
.bubble{background:#fff7ed;border:2px solid #fdba74;border-radius:16px;padding:14px 22px;font-size:26px;color:#9a3412;display:inline-block}
.chain{display:flex;align-items:center;justify-content:center;gap:10px}
.node{background:#fff;border:2px solid #fed7aa;border-radius:14px;padding:16px 14px;font-size:21px;font-weight:600;color:#9a3412;text-align:center}
.node.hl{border-color:#ea580c;background:#fff7ed}
.arr{font-size:30px;color:#ea580c}
.log{margin:36px auto 0;width:1000px;background:#1f2937;color:#a7f3d0;border-radius:14px;padding:20px 26px;font:20px/1.7 ui-monospace,Menlo,monospace}
.stats{display:flex;gap:28px;justify-content:center}
.stat{width:250px;padding:30px 10px;text-align:center}
.stat b{display:block;font-size:52px;color:#ea580c;margin-bottom:12px}
.stat span{font-size:22px;color:#6b7280}
.big{font-size:120px;text-align:center}
.quote{width:900px;margin:0 auto;text-align:center}
</style></head><body>"""

scenes = {}

scenes[1] = HEAD + """
<div class="brand">晚晴 WanQing · 银龄 AI 助手</div>
<div class="main">
  <h1>家人关注 · 功能演示</h1>
  <div class="sub">家人远在千里，关怀随时可达</div>
  <div class="sub" style="margin-top:14px;font-size:24px;color:#9ca3af">家人网页门户 → 设备 TTS 播报 → 老人主动听留言 → 日报与告警</div>
</div>
<div class="pageno">1 / 8</div></body></html>"""

scenes[2] = HEAD + f"""
<div class="brand">① 家人打开门户</div>
<div class="main">
  <div style="display:flex;gap:44px;align-items:center;justify-content:center">
    <img class="web" src="{OUT}/web.png" style="height:500px">
    <div style="width:430px">
      <div style="font-size:34px;font-weight:700;color:#7c2d12;margin-bottom:26px">状态卡：一目了然</div>
      <div style="font-size:26px;line-height:2;color:#4b5563">
        ✅ 最近互动 <b class="orange">{hrs} 小时</b>前<br>
        ✅ 互动正常（阈值 24h）<br>
        ⚠️ 超时无互动 → 红色告警<br>
        📱 App 在线状态实时显示
      </div>
    </div>
  </div>
</div>
<div class="cap">家人在手机浏览器打开门户链接，妈妈的状态尽在掌握</div>
<div class="pageno">2 / 8</div></body></html>"""

scenes[3] = HEAD + f"""
<div class="brand">② 家人留言</div>
<div class="main">
  <div style="display:flex;gap:44px;align-items:center;justify-content:center">
    <img class="web" src="{OUT}/web.png" style="height:480px;filter:saturate(.9)">
    <div style="width:440px;text-align:center">
      <div class="bubble">妈，我周末回来陪你吃饭，<br>记得买条鱼～</div>
      <div style="margin-top:30px;font-size:28px;color:#374151">填写留言 → 点击<br><span style="display:inline-block;margin-top:12px;background:#ea580c;color:#fff;border-radius:12px;padding:10px 34px;font-weight:700">发送留言到设备</span></div>
    </div>
  </div>
</div>
<div class="cap">女儿给妈妈留言，一键发送到设备</div>
<div class="pageno">3 / 8</div></body></html>"""

scenes[4] = HEAD + """
<div class="brand">③ 三秒投递链路</div>
<div class="main">
  <div class="chain">
    <div class="node">家人网页</div><div class="arr">→</div>
    <div class="node">family-api<br>:8100</div><div class="arr">→</div>
    <div class="node hl">被托管会话<br>JSONL</div><div class="arr">→</div>
    <div class="node hl">roro daemon<br>mirror</div><div class="arr">→</div>
    <div class="node">手机 App</div><div class="arr">→</div>
    <div class="node">BLE 设备</div>
  </div>
  <div class="log">POST /family/message &nbsp;→ &nbsp;"pushed": true, "via": "jsonl"<br>chat/…/out &nbsp;{"type":"turn_status","done":true,"elapsed_ms":3249} &nbsp;✓ 3 秒送达</div>
</div>
<div class="cap">留言落库并写入被托管会话，roro daemon 经 mirror 协议 3 秒投达 App</div>
<div class="pageno">4 / 8</div></body></html>"""

scenes[5] = HEAD + """
<div class="brand">④ 设备播报</div>
<div class="main">
  <div class="big">🔊 💗 </div>
  <div class="sub" style="font-size:34px;color:#374151;font-weight:600">TTS 念出留言 · 屏幕播爱心表情 · 振动马达确认</div>
  <div class="sub" style="margin-top:22px;font-size:26px">网页留言记录同步标记为 <span class="orange" style="font-weight:700">已播</span>，家人安心</div>
</div>
<div class="pageno">5 / 8</div></body></html>"""

scenes[6] = HEAD + """
<div class="brand">⑤ 老人主动听留言</div>
<div class="main">
  <div class="quote">
    <div class="bubble">🎤 妈妈按 BOOT 键：“有留言吗？”</div>
    <div style="font-size:30px;color:#ea580c;margin:26px 0">↓</div>
    <div class="card" style="display:inline-block;padding:18px 30px;font:22px/1.6 ui-monospace,Menlo,monospace;color:#334155">Agent → MCP query_family_messages()</div>
    <div style="font-size:30px;color:#ea580c;margin:26px 0">↓</div>
    <div class="bubble">🔊 “女儿的留言：妈，我周末回来陪你吃饭，记得买条鱼～” &nbsp;（标记已读）</div>
  </div>
</div>
<div class="cap">老人一句话，Agent 念出家人留言</div>
<div class="pageno">6 / 8</div></body></html>"""

scenes[7] = HEAD + f"""
<div class="brand">⑥ 日报与告警</div>
<div class="main">
  <div class="stats">
    <div class="stat card"><b>{len(t['tasks_pending'])}</b><span>今日待办<br><i style="font-style:normal;font-size:18px">{pend}</i></span></div>
    <div class="stat card"><b>{done_n}</b><span>今日已完成</span></div>
    <div class="stat card"><b>{push_n}</b><span>已推送提醒</span></div>
    <div class="stat card"><b>{hrs}h</b><span>最近互动</span></div>
  </div>
</div>
<div class="cap">GET /family/report 实时聚合；超 24h 无互动自动红色告警</div>
<div class="pageno">7 / 8</div></body></html>"""

scenes[8] = HEAD + """
<div class="brand">晚晴 WanQing</div>
<div class="main">
  <h1>晚晴</h1>
  <div class="sub" style="font-size:34px;color:#ea580c;font-weight:700">让家人更近的 AI</div>
  <div class="sub" style="margin-top:20px;font-size:24px">银龄 AI 助手 · 家人关注 · 定时提醒闭环</div>
</div>
<div class="pageno">8 / 8</div></body></html>"""

for i, html in scenes.items():
    with open(f"{OUT}/scene{i}.html", "w") as f:
        f.write(html)

NARR = {
    1: "晚晴家人关注功能演示。家人远在千里，也能随时守护、陪伴妈妈。",
    2: f"家人在浏览器打开家人门户。顶部是状态卡：妈妈最近互动在{hrs}小时前，互动正常；如果超过24小时没有互动，会显示红色告警。",
    3: "家人输入留言：妈，我周末回来陪你吃饭。点击，发送留言到设备。",
    4: "留言落库后写入被托管会话，roro守护进程经mirror协议，3秒投递到手机App。",
    5: "设备语音念出留言，屏幕播放爱心表情，振动确认。网页上这条留言标记为已播。",
    6: "妈妈也可以主动问设备：有留言吗？Agent会调用工具，念出家人的留言，并标记已读。",
    7: "门户还能查看今日待办、已完成和已推送提醒，妈妈的一天，一目了然。",
    8: "晚晴，让家人更近的AI。",
}
for i, txt in NARR.items():
    with open(f"{OUT}/narr{i}.txt", "w") as f:
        f.write(txt)
print("scenes + narrations written to", OUT)

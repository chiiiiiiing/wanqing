#!/bin/bash
# 家人关注演示视频构建脚本
# 依赖：Microsoft Edge（headless 渲染）、say（Tingting 中文语音）、afconvert/afinfo、imageio-ffmpeg（venv）
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
OUT="${1:-/tmp/demoscenes}"
FINAL="${2:-$REPO/wanqing/deliverables/family_care_demo.mp4}"
EDGE="/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
FF="$REPO/wanqing/.venv/bin/python3"
FFBIN="$($FF -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"

mkdir -p "$OUT"

# 0) 实时素材：网页截图 + 日报 JSON（需 family-api :8100 在跑）
TOK="$(cat ~/.rorolee/family.token)"
"$EDGE" --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
  --window-size=640,960 --virtual-time-budget=5000 \
  --screenshot="$OUT/web.png" "http://localhost:8100/family/web?token=$TOK" 2>/dev/null
curl -s -H "X-Family-Token: $TOK" localhost:8100/family/report -o "$OUT/report.json"

# 1) 生成场景 HTML + 旁白文本
"$FF" "$(dirname "${BASH_SOURCE[0]}")/gen_scenes.py" "$OUT"

# 2) 渲染场景 PNG + 合成旁白音频
for i in 1 2 3 4 5 6 7 8; do
  "$EDGE" --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
    --window-size=1280,720 --screenshot="$OUT/scene$i.png" "file://$OUT/scene$i.html" 2>/dev/null
  say -v Tingting -o "$OUT/narr$i.aiff" "$(cat "$OUT/narr$i.txt")"
  afconvert -f m4af -d aac "$OUT/narr$i.aiff" "$OUT/narr$i.m4a"
done

# 3) 每场景合成 mp4（时长 = 旁白 + 0.8s 留白）
for i in 1 2 3 4 5 6 7 8; do
  A="$(afinfo "$OUT/narr$i.m4a" | awk -F': ' '/estimated duration/{print $2}')"
  D="$(awk -v a="$A" 'BEGIN{printf "%.2f", a+0.8}')"
  "$FFBIN" -y -loglevel error -loop 1 -framerate 30 -t "$D" -i "$OUT/scene$i.png" \
    -i "$OUT/narr$i.m4a" -c:v libx264 -preset veryfast -pix_fmt yuv420p \
    -c:a aac -b:a 128k "$OUT/part$i.mp4"
  echo "scene $i: ${D}s"
done

# 4) 拼接
: > "$OUT/list.txt"
for i in 1 2 3 4 5 6 7 8; do echo "file '$OUT/part$i.mp4'" >> "$OUT/list.txt"; done
"$FFBIN" -y -loglevel error -f concat -safe 0 -i "$OUT/list.txt" -c copy "$FINAL"
echo "DONE: $FINAL"

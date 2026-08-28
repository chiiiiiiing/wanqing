import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const OUT_DIR = "/Users/nibelung/Desktop/VentureD/wanqing/deliverables";
const BUILD_DIR = "/Users/nibelung/Desktop/VentureD/.codex-build/architecture-diagram";
const PPTX_PATH = path.join(OUT_DIR, "architecture_verified.pptx");
const PNG_PATH = path.join(OUT_DIR, "architecture_verified.png");
const LAYOUT_PATH = path.join(BUILD_DIR, "architecture_verified.layout.json");

const C = {
  ink: "#111827",
  muted: "#475569",
  faint: "#94A3B8",
  rule: "#CBD5E1",
  panel: "#F8FAFC",
  white: "#FFFFFF",
  blue: "#2563EB",
  blueFill: "#EFF6FF",
  green: "#059669",
  greenFill: "#ECFDF5",
  orange: "#EA580C",
  orangeFill: "#FFF7ED",
  amber: "#A16207",
  amberFill: "#FFFBEB",
};

const FONT = "PingFang SC";
let elementNo = 0;

function addShape(slide, name, x, y, w, h, fill, lineFill, lineWidth = 1.5, geometry = "roundRect", lineStyle = "solid") {
  return slide.shapes.add({
    geometry,
    name: `${name}-${++elementNo}`,
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: { style: lineStyle, fill: lineFill, width: lineWidth },
  });
}

function addText(slide, name, value, x, y, w, h, fontSize = 16, bold = false, color = C.ink, alignment = "left", verticalAlignment = "middle") {
  const box = slide.shapes.add({
    geometry: "textbox",
    name: `${name}-${++elementNo}`,
    position: { left: x, top: y, width: w, height: h },
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  box.text = value;
  box.text.style = {
    fontSize,
    typeface: FONT,
    bold,
    color,
    alignment,
    verticalAlignment,
  };
  return box;
}

function addBadge(slide, label, x, y, w, color) {
  addShape(slide, `badge-${label}`, x, y, w, 20, color, color, 0, "roundRect");
  addText(slide, `badge-text-${label}`, label, x + 3, y, w - 6, 20, 13, true, C.white, "center");
}

function addModule(slide, { x, y, w, h, title, body, category, badge, badgeW = 74, bodySize = 16 }) {
  const border = category === "organizer" ? C.blue : category === "config" ? C.green : C.orange;
  const fill = category === "organizer" ? C.blueFill : category === "config" ? C.greenFill : C.orangeFill;
  addShape(slide, `module-${title}`, x, y, w, h, fill, border, 2, "roundRect");
  addText(slide, `module-title-${title}`, title, x + 12, y + 7, w - badgeW - 28, 24, 18, true, C.ink);
  if (badge) addBadge(slide, badge, x + w - badgeW - 10, y + 8, badgeW, border);
  addText(slide, `module-body-${title}`, body, x + 12, y + 34, w - 24, h - 40, bodySize, false, C.muted, "left", "top");
}

function addStageHeader(slide, num, title, x, y, w) {
  addText(slide, `stage-title-${num}`, `${num}  ${title}`, x, y, w, 24, 19, true, C.ink);
}

async function writeBlob(filePath, blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  await fs.writeFile(filePath, bytes);
}

async function main() {
  await fs.mkdir(OUT_DIR, { recursive: true });
  await fs.mkdir(BUILD_DIR, { recursive: true });

  const deck = Presentation.create({ slideSize: { width: 1280, height: 720 } });
  const slide = deck.slides.add();
  slide.background.fill = C.white;

  // Title band follows the Codex Grid process-slide hierarchy.
  addText(slide, "title", "晚晴：一句话如何变成一次可执行提醒", 38, 23, 820, 46, 38, true, C.ink);
  addText(slide, "subtitle", "ROROLEE-Basic｜实线＝代码可追踪主链路 · 虚线＝结构化提醒端到端待验证", 40, 72, 800, 24, 16, false, C.muted);
  addShape(slide, "title-rule", 40, 111, 1200, 1.5, C.rule, C.rule, 0, "rect");

  // Legend.
  addShape(slide, "legend-blue", 868, 35, 20, 14, C.blueFill, C.blue, 2, "rect");
  addText(slide, "legend-blue-text", "主办方提供", 895, 30, 104, 24, 15, true, C.blue);
  addShape(slide, "legend-green", 1000, 35, 20, 14, C.greenFill, C.green, 2, "rect");
  addText(slide, "legend-green-text", "团队配置", 1027, 30, 92, 24, 15, true, C.green);
  addShape(slide, "legend-orange", 1120, 35, 20, 14, C.orangeFill, C.orange, 2, "rect");
  addText(slide, "legend-orange-text", "团队自主开发", 1144, 30, 104, 24, 13, true, C.orange);

  // Main stage backgrounds are created first so connectors can sit behind content.
  const inputStage = addShape(slide, "stage-input", 36, 148, 170, 286, C.panel, C.rule, 1.5, "roundRect");
  const deviceStage = addShape(slide, "stage-device", 218, 148, 315, 286, C.panel, C.rule, 1.5, "roundRect");
  const connectionStage = addShape(slide, "stage-connection", 568, 148, 210, 286, C.panel, C.rule, 1.5, "roundRect");
  const intelligenceStage = addShape(slide, "stage-intelligence", 813, 148, 431, 286, C.panel, C.rule, 1.5, "roundRect");
  const outputStage = addShape(slide, "stage-output", 36, 504, 497, 160, C.amberFill, C.amber, 1.7, "roundRect");
  const mappingStage = addShape(slide, "stage-mapping", 568, 504, 676, 160, C.white, C.rule, 1.5, "roundRect");

  // Primary left-to-right uplink connectors.
  slide.shapes.connect(inputStage, deviceStage, {
    kind: "straight", fromSide: "right", toSide: "left",
    line: { style: "solid", fill: C.muted, width: 2.5 },
    tail: { type: "triangle", width: "med", length: "med" },
  });
  slide.shapes.connect(deviceStage, connectionStage, {
    kind: "straight", fromSide: "right", toSide: "left",
    line: { style: "solid", fill: C.muted, width: 2.5 },
    tail: { type: "triangle", width: "med", length: "med" },
  });
  slide.shapes.connect(connectionStage, intelligenceStage, {
    kind: "straight", fromSide: "right", toSide: "left",
    line: { style: "solid", fill: C.muted, width: 2.5 },
    tail: { type: "triangle", width: "med", length: "med" },
  });
  // Response/reminder loop back to the physical device.
  slide.shapes.connect(intelligenceStage, deviceStage, {
    kind: "elbow", fromSide: "bottom", toSide: "bottom",
    line: { style: "solid", fill: C.blue, width: 2.5 },
    tail: { type: "triangle", width: "med", length: "med" },
  });
  // Device turns returned data into concrete outputs.
  slide.shapes.connect(deviceStage, outputStage, {
    kind: "elbow", fromSide: "bottom", toSide: "top",
    line: { style: "solid", fill: C.amber, width: 2.5 },
    tail: { type: "triangle", width: "med", length: "med" },
  });
  // Structured reminder is implemented on the device but App forwarding still needs validation.
  // Keep this dashed route above the lower evidence region so it never crosses the mapping table.
  addShape(slide, "pending-path-h", 520, 491, 520, 0.5, "none", C.orange, 2, "straightConnector1", "dashed");
  addShape(slide, "pending-path-v", 520, 491, 0.5, 12, "none", C.orange, 2, "straightConnector1", "dashed");
  addShape(slide, "pending-path-arrow", 512, 495, 16, 14, C.orange, C.orange, 0, "downArrow");

  // Stage headers.
  addStageHeader(slide, "01", "真实输入", 45, 119, 160);
  addStageHeader(slide, "02", "ESP32 设备 + 能力层", 228, 119, 300);
  addStageHeader(slide, "03", "连接方式", 578, 119, 195);
  addStageHeader(slide, "04", "Agent / Tool 智能层", 823, 119, 416);

  // Connector labels.
  addShape(slide, "gpio-label-bg", 198, 205, 44, 42, C.white, C.white, 0, "roundRect");
  addText(slide, "gpio-label", "GPIO /\nI²S", 199, 205, 42, 42, 13, true, C.muted, "center");
  addShape(slide, "ble-label-bg", 521, 205, 61, 44, C.white, C.white, 0, "roundRect");
  addText(slide, "ble-label", "0x40 ↑\nTTS/0x70 ↓", 522, 205, 59, 44, 13, true, C.muted, "center");
  addShape(slide, "http-label-bg", 767, 205, 58, 44, C.white, C.white, 0, "roundRect");
  addText(slide, "http-label", "HTTPS\nNDJSON", 769, 205, 54, 44, 13, true, C.muted, "center");
  addShape(slide, "return-label-bg", 618, 447, 424, 30, C.white, C.white, 0, "roundRect");
  addText(slide, "return-label", "下行：Agent / 到点提醒 → App → BLE → ESP32", 628, 448, 404, 28, 16, true, C.blue, "center");
  addShape(slide, "pending-label-bg", 152, 474, 344, 26, C.white, C.white, 0, "roundRect");
  addText(slide, "pending-label", "虚线：0x70 reminder 专属 UI / 三连振（App 待验）", 158, 474, 332, 24, 13, true, C.orange, "center");

  // Input content.
  addText(slide, "input-body", "BOOT（GPIO0）\n按住说话，松开结束\n\nES7210 双麦\n16 kHz PCM\n\n音量±（39 / 40）\nBQ27220 电量/充电", 50, 164, 142, 248, 14, false, C.ink, "left", "top");

  // Device + capability layer.
  addModule(slide, {
    x: 230, y: 160, w: 291, h: 75,
    title: "ROROLEE-Basic",
    body: "ESP32-S3 · ES7210 / ES8311 · SH8501 · BQ27220 · 震动马达",
    category: "organizer", badge: "提供", badgeW: 54, bodySize: 15,
  });
  addModule(slide, {
    x: 230, y: 244, w: 291, h: 103,
    title: "板级固件 / 0x70",
    body: "PTT 采集 / 音频队列 · 11 状态表情\n触觉模式 · 电量轮询 · JSON → Board 动作",
    category: "custom", badge: "自研", badgeW: 54, bodySize: 15,
  });
  addModule(slide, {
    x: 230, y: 356, w: 291, h: 66,
    title: "agent_link SDK",
    body: "voice ↑ · audio / custom ↓",
    category: "organizer", badge: "提供", badgeW: 54, bodySize: 14,
  });

  // Connection layer.
  addModule(slide, {
    x: 580, y: 160, w: 186, h: 91,
    title: "App + roro",
    body: "BLE 网关 · ASR / TTS\nMQTT / 云中继",
    category: "organizer", badge: "提供", badgeW: 48, bodySize: 15,
  });
  addModule(slide, {
    x: 580, y: 260, w: 186, h: 96,
    title: "Shim + Bridge",
    body: "PTY 兼容 · Session / Turn\nNDJSON → 回复",
    category: "custom", badge: "自研", badgeW: 48, bodySize: 15,
  });
  addModule(slide, {
    x: 580, y: 365, w: 186, h: 57,
    title: "链路配置",
    body: "BLE v1 · MCP 注册",
    category: "config", badge: "配置", badgeW: 48, bodySize: 14,
  });

  // Intelligence layer.
  addModule(slide, {
    x: 825, y: 160, w: 407, h: 103,
    title: "TiDB Agent Stack · 晚晴 Agent",
    body: "qwen3.7-plus · Session 上下文 · Scheduler\nPrompt：适老语气 / 时间解析 / 最小追问\nSkill：主链路未单独启用（Prompt + MCP）",
    category: "config", badge: "团队配置", badgeW: 78, bodySize: 15,
  });
  addModule(slide, {
    x: 825, y: 272, w: 236, h: 91,
    title: "MCP · 5 Tools",
    body: "create_task / note / query\ncomplete / delay",
    category: "custom", badge: "自研", badgeW: 48, bodySize: 15,
  });
  addModule(slide, {
    x: 1070, y: 272, w: 162, h: 91,
    title: "SQLite",
    body: "任务 / 备忘\n状态持久化",
    category: "custom", badge: "自研", badgeW: 42, bodySize: 15,
  });
  addModule(slide, {
    x: 825, y: 372, w: 407, h: 50,
    title: "reminder-pusher：Scheduler → MQTT → App",
    body: "",
    category: "custom", badge: "自研", badgeW: 48, bodySize: 15,
  });

  // Actual outputs.
  addText(slide, "output-title", "05  实际输出（回到同一台 ROROLEE-Basic）", 50, 512, 460, 28, 20, true, C.ink);
  addText(slide, "output-col-a", "声音｜ES8311 播放 16 kHz PCM TTS\n\n屏幕｜SH8501 显示 11 状态表情", 52, 550, 222, 82, 15, false, C.ink, "left", "top");
  addText(slide, "output-col-b", "触觉｜连接 / 上传 / 错误 / 提醒模式\n\n后续｜SQLite 保存；Scheduler 到点触发", 286, 550, 226, 82, 15, false, C.ink, "left", "top");

  // Hardware ability mapping.
  addText(slide, "mapping-title", "关键硬件能力映射：Agent / Tool → SDK → 设备动作", 582, 512, 640, 28, 20, true, C.ink);
  const c1 = 582, c2 = 735, c3 = 1000;
  addText(slide, "map-h1", "Agent / Tool 决策", c1, 542, 149, 22, 15, true, C.muted);
  addText(slide, "map-h2", "SDK / 链路", c2, 542, 259, 22, 15, true, C.muted);
  addText(slide, "map-h3", "具体设备动作", c3, 542, 224, 22, 15, true, C.muted);
  addShape(slide, "map-rule-1", 582, 566, 642, 1, C.rule, C.rule, 0, "rect");
  addText(slide, "map-r1c1", "回答 / TTS", c1, 568, 149, 28, 15, true, C.ink);
  addText(slide, "map-r1c2", "App → L2CAP → on_audio_out", c2, 568, 259, 28, 14, false, C.ink);
  addText(slide, "map-r1c3", "ES8311 播放 + Speaking 表情", c3, 568, 224, 28, 14, false, C.ink);
  addText(slide, "map-r2c1", "Scheduler 到点", c1, 598, 149, 28, 15, true, C.ink);
  addText(slide, "map-r2c2", "pusher → MQTT / App → BLE", c2, 598, 259, 28, 14, false, C.ink);
  addText(slide, "map-r2c3", "TTS；0x70 → Reminder + 振动*", c3, 598, 224, 28, 14, false, C.ink);
  addText(slide, "map-r3c1", "调节音量", c1, 628, 149, 28, 15, true, C.ink);
  addText(slide, "map-r3c2", "0x70 on_custom", c2, 628, 259, 28, 14, false, C.ink);
  addText(slide, "map-r3c3", "SetVolumePercent → ES8311", c3, 628, 224, 28, 14, false, C.ink);

  // Validation caveats are audience-facing because they prevent overclaiming.
  addText(slide, "caveat", "* 当前 AMOLED 输出为表情动画，ShowText 仅写日志；BOOT 语音上行已实现但真机全链路待验；结构化 reminder 的 App 转发待验，普通文本/TTS 为可靠兜底。", 40, 676, 1200, 24, 14, false, C.muted, "left");

  slide.speakerNotes.textFrame.setText(
    "[Sources]\n" +
    "- /Users/nibelung/Desktop/VentureD/Agent_link/boards/rorolee-basic/rorolee_basic.cc\n" +
    "- /Users/nibelung/Desktop/VentureD/Agent_link/boards/rorolee-basic/config.h\n" +
    "- /Users/nibelung/Desktop/VentureD/Agent_link/main/app_main.cpp\n" +
    "- /Users/nibelung/Desktop/VentureD/Agent_link/boards/common/device_protocol.cc\n" +
    "- /Users/nibelung/Desktop/VentureD/Agent_link/components/agent_link/README.md\n" +
    "- /Users/nibelung/Desktop/VentureD/wanqing/bridge/claude-bridge\n" +
    "- /Users/nibelung/Desktop/VentureD/wanqing/bridge/reminder-pusher\n" +
    "- /Users/nibelung/Desktop/VentureD/wanqing/backend/mcp_server.py\n" +
    "- /Users/nibelung/Desktop/VentureD/wanqing/backend/models/database.py\n" +
    "- /Users/nibelung/Desktop/VentureD/wanqing/prompts/system_prompt.md\n" +
    "- /Users/nibelung/Desktop/VentureD/wanqing/docs/ble_protocol_v1.md"
  );

  const png = await deck.export({ slide, format: "png", scale: 2 });
  await writeBlob(PNG_PATH, png);
  const layout = await slide.export({ format: "layout" });
  await fs.writeFile(LAYOUT_PATH, await layout.text());
  const pptx = await PresentationFile.exportPptx(deck);
  await pptx.save(PPTX_PATH);
  const inspect = await deck.inspect({ kind: "slide,textbox,shape,notes", maxChars: 18000 });
  await fs.writeFile(path.join(BUILD_DIR, "inspect.ndjson"), inspect.ndjson);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

# YGO Assistant

游戏王（Yu-Gi-Oh! Master Duel）桌面精灵 AI 助手。能：
- 实时截取游戏窗口画面
- 多模态 LLM 识别局面（场上、手牌、墓地、LP、回合）
- 结合历史记忆 + 用户风格，给出 2-3 个最优候选操作
- 采纳/忽略反馈自动入库，下次决策时参考
- 用户拒绝时进入 0.2s 高密度观察窗，记录真实操作作为 DPO 负样本

适合 Master Duel / ygopro 等常见客户端。

---

## 功能

| 模块 | 说明 |
|---|---|
| 屏幕识别 | 自动定位游戏窗口 + 1.0s/0.2s 动态频率截屏 |
| 视觉 LLM | 通义千问 `qwen-vl-ocr-2025-11-20` |
| 决策推理 | `qwen-max` 基于当前局面 + 历史相似 + 用户画像综合判断 |
| 闲聊 | `qwen-flash-character` / `qwen-flash` / `qwen-turbo`（fallback 链）|
| 记忆 | SQLite 持久化决策历史 + 用户偏好画像 + DPO 负样本 |
| 桌面精灵 | PySide6 透明置顶悬浮窗（双模式：伴游/分析）|
| 数据聚合 | 匿名 opt-in 训练样本采集 |

---

## 快速开始

### 0. 系统要求

- Windows 10/11（开发与运行）
- Python 3.11+（推荐 3.13，已实测）
- 约 200MB 磁盘（依赖 + 打包后约 60MB）

### 1. 克隆并安装

```bash
git clone https://github.com/EDY/ygo-assistant.git
cd ygo-assistant
pip install -r requirements.txt
```

如果你要跑打包脚本，再装：

```bash
pip install pyinstaller
```

### 2. 申请 DashScope API Key

1. 打开 https://dashscope.aliyun.com/
2. 控制台 → 地域选「华北2（北京）」 → API-Key → 创建 Key
3. 把 Key 复制到 `.env` 文件：

```bash
cp .env.example .env       # Linux / macOS / Git Bash
copy .env.example .env     # Windows cmd
```

编辑 `.env`，把 `DASHSCOPE_API_KEY=` 后面的占位符替换成你的 Key。

### 3. 开通模型

在百炼控制台「模型广场」开通下列模型（免费额度足够个人使用）：

| 用途 | 模型 | 必开 |
|---|---|---|
| 视觉 | `qwen-vl-ocr-2025-11-20` | 是 |
| 决策 | `qwen-max` | 是 |
| 闲聊 | `qwen-flash-character-2026-02-26` / `qwen-flash` / `qwen-turbo` 任一 | 否（fallback 链按已开通顺序回退）|

### 4. 跑起来

开发模式：

```bash
python main.py
```

跑烟囱测试（不启动 GUI，验证视觉/决策链路）：

```bash
python smoke_test.py
```

### 5. 打包成单文件 exe

```bash
build.bat        # 产出 dist\ygo-assistant.exe
release.bat      # 打包成 release\ygo-assistant-v1.0.zip
```

---

## 项目结构

```
ygo-assistant/
  main.py                    # 入口；状态机（alone/analyzing）
  screenshot.py              # Windows 窗口定位 + mss 截屏
  vision.py                  # qwen-vl-ocr 多模态调用
  decision.py                # qwen-max 决策推理
  pet_chat.py                # 桌宠闲聊（带 fallback）
  memory.py                  # SQLite 决策记忆 + 用户画像
  action_analyzer.py         # 0.2s 高密度观察窗的状态差分
  neglect_watcher.py         # 用户拒绝时启动观察线程
  floating_widget.py         # PySide6 透明置顶悬浮窗 UI
  config.py                  # 配置（.env 读取 + 默认值）
  logger.py                  # 日志
  telemetry.py               # 匿名 opt-in 训练样本采集
  train_export.py            # 决策数据 → SFT jsonl
  train_submit.py            # 上传到阿里云百炼微调
  scene_factory.py           # 测试用场景图片生成
  smoke_test.py              # 端到端烟囱测试
  main.spec                  # PyInstaller 打包配置
  build.bat / release.bat    # 一键打包脚本
  start.bat / install.bat    # 一键启动 / 安装脚本
  requirements.txt
  .env.example               # 配置模板
  assets/
    desktop_pet.png          # 桌宠形象
```

---

## 跨设备继续开发

任何机器克隆下来后：

```bash
git clone https://github.com/EDY/ygo-assistant.git
cd ygo-assistant
pip install -r requirements.txt
cp .env.example .env        # 填入你自己的 API Key
python smoke_test.py        # 验证视觉 + 决策链路
python main.py              # 启动桌宠
```

每个开发者的 `.env` 互不干扰（已在 `.gitignore`）。SQLite 决策库 (`data/`) 也是本地的，不会被 git 追踪。

---

## 训练数据与微调

`opt_in_training=True` 后，桌宠会把决策事件 + 负样本（DPO）异步上传到遥测队列。本地导出 SFT：

```bash
python train_export.py      # 产出 training_data/sft.jsonl
```

推到百炼微调（LoRA）：

```bash
python train_submit.py      # 需配 BAILIAN_ACCESS_KEY
```

---

## 已知限制

- Windows-only（用了 `win32gui` 自动定位游戏窗口；macOS / Linux 可改成手动框选）
- 桌面精灵一次只能识别一个游戏窗口（多开需要扩展 `find_game_window()`）
- LLM 决策有 1-3s 延迟，不适合极速竞技场

---

## License

MIT（待加 `LICENSE` 文件）

---

## Credits

- 桌宠图素材：用户自制
- LLM：阿里云通义千问（DashScope）
- 截屏：[python-mss](https://github.com/BoboTiG/python-mss)
- 窗口定位：[pywin32](https://github.com/mhammond/pywin32)

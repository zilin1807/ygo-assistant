#!/usr/bin/env bash
# macOS / Linux 一键启动
# 用法：bash start.sh

set -e
cd "$(dirname "$0")"

echo "====================================================="
echo " 游戏王 AI 助手 · 一键启动 (macOS/Linux)"
echo "====================================================="

PY=python3
if ! command -v $PY >/dev/null 2>&1; then
    echo "[错误] 未找到 python3，请先安装 Python 3.11+"
    exit 1
fi

echo "[1/3] 检查依赖..."
if ! $PY -c "import PySide6" 2>/dev/null; then
    echo "     安装 GUI 依赖..."
    $PY -m pip install --quiet -r requirements.txt
fi

if [ ! -f ".env" ]; then
    echo "[警告] 没有 .env，正在从 .env.example 复制..."
    cp .env.example .env
    echo "请编辑 .env 填入 DASHSCOPE_API_KEY 后再次运行本脚本"
    exit 1
fi

echo "[3/3] 启动..."
$PY main.py

#!/bin/bash
# 青龙面板任务配置
# new Env('GameMale 签到终止器')
# cron 0 8 * * * gamemale_stop.sh

# GameMale 签到任务终止脚本
# 用于优雅地停止正在运行的签到任务

SCRIPT_NAME="gamemale_daily_ql.py"

echo "========================================"
echo "GameMale 签到任务终止器"
echo "========================================"

# 查找进程
PIDS=$(ps aux | grep "python3.*${SCRIPT_NAME}" | grep -v grep | awk '{print $2}')

if [ -z "$PIDS" ]; then
    echo "未找到正在运行的 ${SCRIPT_NAME} 进程"
    exit 0
fi

echo "找到以下进程:"
ps aux | grep "python3.*${SCRIPT_NAME}" | grep -v grep

echo ""
echo "正在发送 SIGTERM 信号..."

for PID in $PIDS; do
    echo "终止进程 PID: $PID"
    kill -SIGTERM $PID 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "  -> SIGTERM 信号已发送"
    else
        echo "  -> 发送失败，进程可能已结束"
    fi
done

# 等待进程退出
echo ""
echo "等待进程退出 (最多10秒)..."
TIMEOUT=10
while [ $TIMEOUT -gt 0 ]; do
    REMAINING=$(ps aux | grep "python3.*${SCRIPT_NAME}" | grep -v grep | wc -l)
    if [ "$REMAINING" -eq 0 ]; then
        echo "所有进程已优雅退出"
        exit 0
    fi
    sleep 1
    TIMEOUT=$((TIMEOUT - 1))
done

# 如果还有进程，强制终止
PIDS=$(ps aux | grep "python3.*${SCRIPT_NAME}" | grep -v grep | awk '{print $2}')
if [ -n "$PIDS" ]; then
    echo ""
    echo "部分进程未响应，发送 SIGKILL 强制终止..."
    for PID in $PIDS; do
        echo "强制终止 PID: $PID"
        kill -9 $PID 2>/dev/null
    done
fi

echo ""
echo "终止操作完成"

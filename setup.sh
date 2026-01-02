#!/bin/bash

# 项目部署管理系统 - 智能安装/更新脚本
# 自动检测是首次安装还是更新
# 使用方法: curl -fsSL https://raw.githubusercontent.com/SundayDX/deployTool/main/setup.sh | sudo bash

set -e

echo "=========================================="
echo "项目部署管理系统 - 智能安装/更新"
echo "=========================================="
echo ""

# 获取实际用户的 HOME 目录
if [ -n "$SUDO_USER" ]; then
    ACTUAL_USER="$SUDO_USER"
    ACTUAL_HOME=$(eval echo ~$SUDO_USER)
else
    ACTUAL_USER="$USER"
    ACTUAL_HOME="$HOME"
fi

INSTALL_DIR="${INSTALL_DIR:-$ACTUAL_HOME/deploy-manager}"

echo "目标目录: $INSTALL_DIR"
echo "运行用户: $ACTUAL_USER"
echo ""

# 检测是首次安装还是更新
if [ -d "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/app.py" ]; then
    echo "✓ 检测到已有安装"
    echo "模式: 更新现有安装"
    echo ""
    MODE="update"

    # 检查是否有 update.sh
    if [ -f "$INSTALL_DIR/update.sh" ]; then
        echo "执行更新脚本..."
        cd "$INSTALL_DIR"
        exec bash update.sh
    else
        echo "警告: 未找到 update.sh，将从 GitHub 下载..."
        TEMP_UPDATE="/tmp/update-temp-$$.sh"
        curl -fsSL https://raw.githubusercontent.com/SundayDX/deployTool/main/update.sh -o "$TEMP_UPDATE"
        chmod +x "$TEMP_UPDATE"

        # 保存到安装目录
        cp "$TEMP_UPDATE" "$INSTALL_DIR/update.sh"

        # 执行更新
        cd "$INSTALL_DIR"
        bash update.sh

        # 清理临时文件
        rm -f "$TEMP_UPDATE"
    fi
else
    echo "✓ 未检测到已有安装"
    echo "模式: 首次安装"
    echo ""
    MODE="install"

    TEMP_CLONE_DIR="/tmp/deploy-manager-temp-$$"

    # 清理函数
    cleanup() {
        if [ -d "$TEMP_CLONE_DIR" ]; then
            echo "清理临时文件..."
            rm -rf "$TEMP_CLONE_DIR"
        fi
    }

    # 设置退出时清理
    trap cleanup EXIT

    # 检查 git 是否安装
    if ! command -v git &> /dev/null; then
        echo "Git 未安装，正在安装..."
        if command -v apt-get &> /dev/null; then
            apt-get update && apt-get install -y git
        elif command -v yum &> /dev/null; then
            yum install -y git
        else
            echo "错误: 无法自动安装 git，请手动安装后重试"
            exit 1
        fi
    fi

    # 克隆到临时目录
    echo "正在从 GitHub 克隆项目..."
    git clone https://github.com/SundayDX/deployTool.git "$TEMP_CLONE_DIR"

    # 进入临时目录并执行部署脚本
    cd "$TEMP_CLONE_DIR"

    # 设置环境变量并执行部署脚本
    export INSTALL_DIR="$INSTALL_DIR"
    export AUTO_CONFIRM="1"

    echo ""
    echo "执行安装脚本..."
    bash deploy.sh
fi

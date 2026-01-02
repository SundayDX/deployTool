#!/bin/bash

# 快速安装脚本 - 从 GitHub 拉取并部署
# 使用方法: curl -fsSL https://raw.githubusercontent.com/SundayDX/deployTool/main/install.sh | sudo bash

set -e

REPO_URL="https://github.com/SundayDX/deployTool.git"

# 获取实际用户的 HOME 目录
if [ -n "$SUDO_USER" ]; then
    ACTUAL_USER="$SUDO_USER"
    ACTUAL_HOME=$(eval echo ~$SUDO_USER)
else
    ACTUAL_USER="$USER"
    ACTUAL_HOME="$HOME"
fi

INSTALL_DIR="${INSTALL_DIR:-$ACTUAL_HOME/deploy-manager}"
TEMP_CLONE_DIR="/tmp/deploy-manager-temp-$$"

echo "=========================================="
echo "项目部署管理系统 - 快速安装"
echo "=========================================="
echo ""

# 检查是否已经安装
if [ -d "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/app.py" ]; then
    echo "检测到已有安装: $INSTALL_DIR"
    echo ""
    echo "如果要更新现有安装，请使用更新脚本："
    echo "  cd $INSTALL_DIR && sudo bash update.sh"
    echo ""
    echo "如果要通过 Web 界面更新："
    echo "  访问 http://服务器IP:6666"
    echo "  点击 '查看系统信息' -> '立即更新'"
    echo ""
    read -p "确定要删除现有安装并重新安装吗？这将丢失所有配置！(yes/no) " -r
    echo
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo "安装已取消"
        echo ""
        echo "提示: 如果要更新，使用以下命令："
        echo "  cd $INSTALL_DIR && sudo bash update.sh"
        exit 0
    fi
    echo "警告: 将删除现有安装并重新开始..."
fi

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
echo "正在从 GitHub 克隆项目到临时目录..."
git clone "$REPO_URL" "$TEMP_CLONE_DIR"

# 进入临时目录并执行部署脚本
cd "$TEMP_CLONE_DIR"

echo ""
echo "目标安装目录: $INSTALL_DIR"
echo ""

# 设置环境变量并执行部署脚本
export INSTALL_DIR="$INSTALL_DIR"
export AUTO_CONFIRM="1"

# 检查是否为 root 用户
if [ "$EUID" -eq 0 ]; then
    bash deploy.sh
else
    sudo INSTALL_DIR="$INSTALL_DIR" AUTO_CONFIRM="1" bash deploy.sh
fi

echo ""
echo "临时文件将在退出时自动清理..."

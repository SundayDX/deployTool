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

echo "=========================================="
echo "项目部署管理系统 - 快速安装"
echo "=========================================="
echo ""

# 检查 git 是否安装
if ! command -v git &> /dev/null; then
    echo "Git 未安装，正在安装..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y git
    elif command -v yum &> /dev/null; then
        sudo yum install -y git
    else
        echo "错误: 无法自动安装 git，请手动安装后重试"
        exit 1
    fi
fi

# 克隆仓库
echo "正在从 GitHub 克隆项目..."
if [ -d "$INSTALL_DIR" ]; then
    echo "目录 $INSTALL_DIR 已存在"
    read -p "是否删除并重新克隆? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$INSTALL_DIR"
    else
        echo "安装已取消"
        exit 0
    fi
fi

git clone "$REPO_URL" "$INSTALL_DIR"

# 进入目录并执行部署脚本
cd "$INSTALL_DIR"

# 检查是否为 root 用户
if [ "$EUID" -eq 0 ]; then
    bash deploy.sh
else
    sudo bash deploy.sh
fi

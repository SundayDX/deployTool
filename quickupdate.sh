#!/bin/bash

# 快速更新脚本 - 可以通过网络一行命令执行
# 使用方法: curl -fsSL https://raw.githubusercontent.com/SundayDX/deployTool/main/quickupdate.sh | sudo bash

set -e

echo "=========================================="
echo "项目部署管理系统 - 快速更新"
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

echo "安装目录: $INSTALL_DIR"
echo ""

# 检查是否已安装
if [ ! -d "$INSTALL_DIR" ] || [ ! -f "$INSTALL_DIR/app.py" ]; then
    echo "错误: 未检测到已有安装"
    echo ""
    echo "如果要首次安装，请使用："
    echo "  curl -fsSL https://raw.githubusercontent.com/SundayDX/deployTool/main/install.sh | sudo bash"
    exit 1
fi

# 检查是否有 update.sh
if [ ! -f "$INSTALL_DIR/update.sh" ]; then
    echo "错误: 未找到 update.sh 脚本"
    echo "正在从 GitHub 下载..."
    curl -fsSL https://raw.githubusercontent.com/SundayDX/deployTool/main/update.sh -o "$INSTALL_DIR/update.sh"
    chmod +x "$INSTALL_DIR/update.sh"
fi

# 执行更新
echo "开始更新..."
cd "$INSTALL_DIR"
bash update.sh

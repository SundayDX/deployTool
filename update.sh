#!/bin/bash

# 自动更新脚本
# 使用方法: sudo bash update.sh

set -e

echo "=========================================="
echo "项目部署管理系统 - 自动更新"
echo "=========================================="
echo ""

# 检查是否为 root 用户
if [ "$EUID" -ne 0 ]; then
    echo "错误: 请使用 sudo 运行此脚本"
    echo "用法: sudo bash update.sh"
    exit 1
fi

# 获取实际用户
ACTUAL_USER=${SUDO_USER:-$USER}
ACTUAL_HOME=$(eval echo ~$ACTUAL_USER)

# 检测安装目录
INSTALL_DIR="${INSTALL_DIR:-$ACTUAL_HOME/deploy-manager}"

if [ ! -d "$INSTALL_DIR" ]; then
    echo "错误: 未找到安装目录 $INSTALL_DIR"
    echo "请设置 INSTALL_DIR 环境变量或手动指定安装目录"
    exit 1
fi

echo "安装目录: $INSTALL_DIR"
echo "运行用户: $ACTUAL_USER"
echo ""

# 检查是否为 git 仓库
if [ ! -d "$INSTALL_DIR/.git" ]; then
    echo "错误: $INSTALL_DIR 不是 Git 仓库"
    echo "建议重新安装：curl -fsSL https://raw.githubusercontent.com/SundayDX/deployTool/main/install.sh | sudo bash"
    exit 1
fi

# 备份配置文件
echo "[1/5] 备份配置文件..."
BACKUP_DIR="/tmp/deploy-manager-backup-$$"
mkdir -p "$BACKUP_DIR"

if [ -f "$INSTALL_DIR/projects.json" ]; then
    cp "$INSTALL_DIR/projects.json" "$BACKUP_DIR/"
    echo "  已备份 projects.json"
fi

if [ -f "$INSTALL_DIR/settings.json" ]; then
    cp "$INSTALL_DIR/settings.json" "$BACKUP_DIR/"
    echo "  已备份 settings.json"
fi

# 停止服务
echo ""
echo "[2/5] 停止服务..."
systemctl stop deploy-manager 2>/dev/null || true
echo "  服务已停止"

# 拉取最新代码
echo ""
echo "[3/5] 拉取最新代码..."
cd "$INSTALL_DIR"

# 保存本地修改（如果有）
sudo -u $ACTUAL_USER git stash 2>/dev/null || true

# 拉取更新
sudo -u $ACTUAL_USER git fetch origin
sudo -u $ACTUAL_USER git reset --hard origin/main

echo "  代码已更新"

# 恢复配置文件
echo ""
echo "[4/5] 恢复配置文件..."
if [ -f "$BACKUP_DIR/projects.json" ]; then
    cp "$BACKUP_DIR/projects.json" "$INSTALL_DIR/"
    chown $ACTUAL_USER:$ACTUAL_USER "$INSTALL_DIR/projects.json"
    echo "  已恢复 projects.json"
fi

if [ -f "$BACKUP_DIR/settings.json" ]; then
    cp "$BACKUP_DIR/settings.json" "$INSTALL_DIR/"
    chown $ACTUAL_USER:$ACTUAL_USER "$INSTALL_DIR/settings.json"
    echo "  已恢复 settings.json"
fi

# 更新 Python 依赖
echo ""
echo "检查并更新 Python 依赖..."
if [ -f "$INSTALL_DIR/requirements.txt" ]; then
    sudo -u $ACTUAL_USER "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" --upgrade
    echo "  依赖已更新"
fi

# 启动服务
echo ""
echo "[5/5] 启动服务..."
systemctl start deploy-manager
sleep 2

# 清理备份
rm -rf "$BACKUP_DIR"

echo ""
echo "=========================================="
echo "更新完成！"
echo "=========================================="
echo ""
echo "服务状态:"
systemctl status deploy-manager --no-pager || true
echo ""
echo "版本信息:"
cd "$INSTALL_DIR"
echo "  当前分支: $(git branch --show-current)"
echo "  最新提交: $(git log -1 --pretty=format:'%h - %s (%ar)')"
echo ""
echo "常用命令:"
echo "  查看更新日志: cd $INSTALL_DIR && git log --oneline -10"
echo "  查看服务日志: sudo journalctl -u deploy-manager -f"
echo ""

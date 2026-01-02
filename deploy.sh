#!/bin/bash

# 项目部署管理系统 - 自动部署脚本
# 使用方法: sudo bash deploy.sh

set -e

echo "=========================================="
echo "项目部署管理系统 - 自动部署脚本"
echo "=========================================="
echo ""

# 检查是否为 root 用户
if [ "$EUID" -ne 0 ]; then
    echo "错误: 请使用 sudo 运行此脚本"
    echo "用法: sudo bash deploy.sh"
    exit 1
fi

# 获取实际用户
ACTUAL_USER=${SUDO_USER:-$USER}
ACTUAL_HOME=$(eval echo ~$ACTUAL_USER)

# 配置项
INSTALL_DIR="${INSTALL_DIR:-$ACTUAL_HOME/deploy-manager}"
SERVICE_PORT="${SERVICE_PORT:-6666}"

echo "配置信息:"
echo "  安装目录: $INSTALL_DIR"
echo "  运行用户: $ACTUAL_USER"
echo "  服务端口: $SERVICE_PORT"
echo ""

# 检查是否为非交互式环境或设置了自动确认
if [ -t 0 ] && [ -z "$AUTO_CONFIRM" ]; then
    read -p "是否继续安装? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "安装已取消"
        exit 0
    fi
else
    echo "自动确认模式，继续安装..."
fi

echo ""
echo "[1/6] 检查系统环境..."

# 检查操作系统
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    echo "错误: 无法检测操作系统"
    exit 1
fi

echo "  操作系统: $OS"

# 安装系统依赖
echo ""
echo "[2/6] 安装系统依赖..."

if [[ "$OS" == "ubuntu" || "$OS" == "debian" ]]; then
    apt-get update
    apt-get install -y python3 python3-pip python3-venv git
elif [[ "$OS" == "centos" || "$OS" == "rhel" ]]; then
    yum install -y python3 python3-pip git
else
    echo "警告: 未知的操作系统，尝试继续..."
fi

echo "  系统依赖安装完成"

# 创建安装目录
echo ""
echo "[3/6] 准备安装目录..."

if [ -d "$INSTALL_DIR" ]; then
    echo "  检测到已存在的安装目录"

    if [ -t 0 ] && [ -z "$AUTO_CONFIRM" ]; then
        read -p "是否删除现有安装并重新安装? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "  停止现有服务..."
            systemctl stop deploy-manager 2>/dev/null || true
            echo "  删除现有目录..."
            rm -rf "$INSTALL_DIR"
        else
            echo "  安装已取消"
            exit 0
        fi
    else
        echo "  自动确认模式：删除现有安装..."
        systemctl stop deploy-manager 2>/dev/null || true
        rm -rf "$INSTALL_DIR"
    fi
fi

# 保存当前目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 复制文件到安装目录
echo "  复制文件到 $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

# 使用更可靠的复制方法
if [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
    echo "  从 $SCRIPT_DIR 复制文件..."
    cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/" 2>/dev/null || true
    # 复制隐藏文件（如 .gitignore）
    cp -r "$SCRIPT_DIR"/.[!.]* "$INSTALL_DIR/" 2>/dev/null || true
else
    echo "  安装目录与脚本目录相同，跳过复制"
fi

chown -R $ACTUAL_USER:$ACTUAL_USER "$INSTALL_DIR"

# 验证关键文件
if [ ! -f "$INSTALL_DIR/requirements.txt" ]; then
    echo "错误: requirements.txt 未找到，文件复制可能失败"
    exit 1
fi

if [ ! -f "$INSTALL_DIR/app.py" ]; then
    echo "错误: app.py 未找到，文件复制可能失败"
    exit 1
fi

echo "  文件复制完成"

# 创建虚拟环境和安装依赖
echo ""
echo "[4/6] 创建虚拟环境并安装 Python 依赖..."

cd "$INSTALL_DIR"
sudo -u $ACTUAL_USER python3 -m venv venv
sudo -u $ACTUAL_USER "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
sudo -u $ACTUAL_USER "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

echo "  Python 依赖安装完成"

# 创建默认配置文件
echo ""
echo "[5/6] 创建配置文件..."

if [ ! -f "$INSTALL_DIR/settings.json" ]; then
    cat > "$INSTALL_DIR/settings.json" <<EOF
{
    "dingtalk": {
        "enabled": false,
        "webhook_url": "",
        "secret": ""
    }
}
EOF
    chown $ACTUAL_USER:$ACTUAL_USER "$INSTALL_DIR/settings.json"
    echo "  已创建 settings.json"
fi

# 创建 systemd 服务
echo ""
echo "[6/6] 配置系统服务..."

cat > /etc/systemd/system/deploy-manager.service <<EOF
[Unit]
Description=Deploy Manager Service
After=network.target

[Service]
Type=simple
User=$ACTUAL_USER
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin"
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "  systemd 服务文件已创建"

# 重载 systemd 并启动服务
systemctl daemon-reload
systemctl enable deploy-manager
systemctl start deploy-manager

echo ""
echo "=========================================="
echo "安装完成！"
echo "=========================================="
echo ""
echo "服务状态:"
systemctl status deploy-manager --no-pager || true
echo ""
echo "访问地址: http://$(hostname -I | awk '{print $1}'):$SERVICE_PORT"
echo ""
echo "常用命令:"
echo "  查看状态: sudo systemctl status deploy-manager"
echo "  启动服务: sudo systemctl start deploy-manager"
echo "  停止服务: sudo systemctl stop deploy-manager"
echo "  重启服务: sudo systemctl restart deploy-manager"
echo "  查看日志: sudo journalctl -u deploy-manager -f"
echo ""
echo "配置文件位置:"
echo "  项目配置: $INSTALL_DIR/projects.json"
echo "  系统设置: $INSTALL_DIR/settings.json"
echo ""
echo "下一步:"
echo "  1. 编辑 $INSTALL_DIR/projects.json 添加你的项目"
echo "  2. 在 Web 界面配置钉钉通知（可选）"
echo "  3. 开始使用！"
echo ""

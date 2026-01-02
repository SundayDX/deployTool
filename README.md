# 项目部署管理系统

一个简单的 Web 界面工具，用于管理服务器上的项目部署。支持通过网页点击按钮完成 Git 更新和 Docker Compose 构建。

## 功能特性

### 项目部署
- 可视化 Web 界面，无需登录服务器
- 一键执行 `git pull` 更新代码
- 一键执行 `docker compose build` 构建镜像
- 自动执行 `docker compose down && docker compose up -d` 重启服务
- 实时查看项目状态（Git 分支、最新提交、Docker 容器状态）
- 查看详细的部署日志
- 支持管理多个项目

### 系统监控
- 查看磁盘使用情况（df -h）
- 查看内存使用情况（free -h）
- 查看 CPU 使用情况
- 查看系统负载（uptime）
- 查看 Docker 磁盘使用情况

### 钉钉通知
- 部署成功/失败自动发送钉钉通知
- 支持自定义 Webhook 和加签密钥
- 在线测试钉钉通知功能

## 快速开始

### 方法一：自动安装（推荐）

使用一键安装脚本，自动完成所有配置：

```bash
# 克隆项目
git clone https://github.com/SundayDX/deployTool.git
cd deployTool

# 执行自动部署脚本
sudo bash deploy.sh
```

自动部署脚本会：
- 安装系统依赖（Python3, pip, venv）
- 创建虚拟环境并安装 Python 依赖
- 配置 systemd 服务
- 自动启动应用

### 方法二：从网络直接安装（首次安装）

⚠️ **注意**: 此命令仅用于**首次安装**。如果已经安装，请使用更新命令！

一行命令完成安装，脚本会自动克隆到临时目录，安装后清理：

```bash
curl -fsSL https://raw.githubusercontent.com/SundayDX/deployTool/main/install.sh | sudo bash
```

如果检测到已有安装，脚本会提示你使用更新命令而不是重新安装。

自定义安装目录：
```bash
curl -fsSL https://raw.githubusercontent.com/SundayDX/deployTool/main/install.sh | sudo INSTALL_DIR=/opt/deploy-manager bash
```

### 方法三：手动安装

如果需要手动控制安装过程：

```bash
# 1. 克隆项目
git clone https://github.com/SundayDX/deployTool.git
cd deployTool

# 2. 安装系统依赖
sudo apt install -y python3 python3-pip python3-venv  # Ubuntu/Debian
# 或
sudo yum install -y python3 python3-pip  # CentOS/RHEL

# 3. 创建虚拟环境
python3 -m venv venv

# 4. 激活虚拟环境并安装依赖
source venv/bin/activate
pip install -r requirements.txt

# 5. 启动应用
python app.py
```

## 配置说明

### 配置项目

编辑 `projects.json` 文件，添加你的项目信息：

```json
[
    {
        "name": "我的项目",
        "description": "项目描述",
        "path": "/path/to/your/project",
        "auto_restart": true
    }
]
```

参数说明：
- `name`: 项目名称
- `description`: 项目描述（可选）
- `path`: 项目在服务器上的绝对路径
- `auto_restart`: 是否在构建后自动重启服务（true/false）

### 访问界面

安装完成后，在浏览器中访问：
```
http://your-server-ip:6666
```

默认端口为 6666，可在 `app.py` 中修改。

## 使用方法

### 1. 部署项目
点击"部署项目"按钮，系统将自动执行：
- `git pull` - 拉取最新代码
- `docker compose build` - 构建镜像
- `docker compose down` - 停止当前容器
- `docker compose up -d` - 启动新容器（如果启用了 auto_restart）

部署完成后会自动弹出日志窗口，显示每个步骤的执行结果。如果启用了钉钉通知，会自动发送部署结果到钉钉群。

### 2. 查看项目状态
点击"查看状态"按钮，可以看到：
- 当前 Git 分支
- 最新提交信息
- Git 工作目录状态
- Docker 容器运行状态

### 3. 查看系统信息
点击"查看系统信息"按钮，可以看到：
- 磁盘使用情况（包括所有挂载点）
- 内存使用情况
- CPU 使用率
- 系统运行时间和负载
- Docker 磁盘占用情况

### 4. 配置钉钉通知
1. 点击"系统设置"按钮
2. 勾选"启用钉钉通知"
3. 填入钉钉机器人的 Webhook URL
4. （可选）填入加签密钥
5. 点击"保存设置"
6. 点击"测试钉钉通知"验证配置

**获取钉钉 Webhook URL：**
1. 在钉钉群中添加自定义机器人
2. 选择"自定义机器人"
3. 设置机器人名称和头像
4. 安全设置选择"加签"（可选）
5. 复制 Webhook 地址到配置中

## 系统更新

⚠️ **重要提示**:
- **首次安装**使用 `install.sh`
- **已有安装的更新**使用 `update.sh` 或 Web 界面
- **绝对不要**用 `install.sh` 来更新，会删除所有配置！

### 方法一：Web 界面更新（最推荐）

1. 访问 `http://服务器IP:6666`
2. 点击"查看系统信息"
3. 查看版本信息和更新状态
4. 如果有更新，点击"立即更新"按钮
5. 等待更新完成后刷新页面

### 方法二：一键命令行更新

```bash
# 从网络直接更新（推荐）
curl -fsSL https://raw.githubusercontent.com/SundayDX/deployTool/main/quickupdate.sh | sudo bash
```

### 方法三：本地命令行更新

```bash
# 进入安装目录
cd ~/deploy-manager  # 或你的安装目录

# 执行更新脚本
sudo bash update.sh
```

### 方法四：完全手动更新

```bash
# 进入安装目录
cd ~/deploy-manager

# 备份配置文件
cp projects.json projects.json.bak
cp settings.json settings.json.bak

# 拉取最新代码
git pull origin main

# 更新依赖
source venv/bin/activate
pip install -r requirements.txt --upgrade

# 恢复配置文件（如果被覆盖）
mv projects.json.bak projects.json
mv settings.json.bak settings.json

# 重启服务
sudo systemctl restart deploy-manager
```

## 服务管理

如果使用自动部署脚本安装，系统会自动配置为 systemd 服务。

### 常用命令

```bash
# 查看服务状态
sudo systemctl status deploy-manager

# 启动服务
sudo systemctl start deploy-manager

# 停止服务
sudo systemctl stop deploy-manager

# 重启服务
sudo systemctl restart deploy-manager

# 查看实时日志
sudo journalctl -u deploy-manager -f

# 查看最近日志
sudo journalctl -u deploy-manager -n 100
```

### 手动配置 systemd 服务

如果是手动安装，可以参考项目中的 `deploy-manager.service` 文件：

```bash
# 复制服务文件
sudo cp deploy-manager.service /etc/systemd/system/

# 修改服务文件中的路径和用户名
sudo nano /etc/systemd/system/deploy-manager.service

# 重载并启动服务
sudo systemctl daemon-reload
sudo systemctl enable deploy-manager
sudo systemctl start deploy-manager
```

### 使用 Nginx 反向代理

Nginx 配置示例：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

### 添加身份认证

为了安全，建议添加基本的 HTTP 认证或使用 Nginx 的 auth_basic。

在 Nginx 中添加认证：

```nginx
location / {
    auth_basic "Restricted Access";
    auth_basic_user_file /etc/nginx/.htpasswd;
    proxy_pass http://127.0.0.1:5000;
}
```

创建密码文件：
```bash
sudo apt-get install apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd username
```

## 安全注意事项

1. **不要将此服务直接暴露在公网**，建议使用 VPN 或添加认证
2. **限制运行用户权限**，不要使用 root 用户运行
3. **定期检查日志**，监控异常访问
4. **配置防火墙**，只允许特定 IP 访问

## 故障排查

### 命令执行失败

- 检查项目路径是否正确
- 检查运行用户是否有权限访问项目目录
- 检查 Git 和 Docker 是否正确安装

### 端口被占用

修改 `app.py` 中的端口号：
```python
app.run(host='0.0.0.0', port=5000, debug=True)  # 改为其他端口
```

## 许可证

MIT License

from flask import Flask, render_template, jsonify, request
import subprocess
import os
import json
from datetime import datetime
import threading
import requests

app = Flask(__name__)

# 配置文件路径
CONFIG_FILE = 'projects.json'
SETTINGS_FILE = 'settings.json'

def load_settings():
    """加载系统设置"""
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'dingtalk': {
            'enabled': False,
            'webhook_url': '',
            'secret': ''
        }
    }

def send_dingtalk_notification(title, message, is_success=True):
    """发送钉钉通知"""
    settings = load_settings()
    dingtalk = settings.get('dingtalk', {})

    if not dingtalk.get('enabled', False):
        return

    webhook_url = dingtalk.get('webhook_url', '')
    if not webhook_url:
        return

    # 钉钉消息格式
    content = f"### {title}\n\n"
    content += f"**状态**: {'✅ 成功' if is_success else '❌ 失败'}\n\n"
    content += f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    content += f"**详情**: {message}\n"

    data = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": content
        }
    }

    try:
        response = requests.post(webhook_url, json=data, timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"发送钉钉通知失败: {e}")
        return False

def load_projects():
    """加载项目配置"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_projects(projects):
    """保存项目配置"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(projects, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"保存项目配置失败: {e}")
        return False

def run_command(command, cwd=None):
    """执行命令并返回输出"""
    try:
        # 使用 bash 并设置完整的 PATH
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
            executable='/bin/bash',
            env={**os.environ, 'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'}
        )
        return {
            'success': result.returncode == 0,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'stdout': '',
            'stderr': '命令执行超时（超过5分钟）',
            'returncode': -1
        }
    except Exception as e:
        return {
            'success': False,
            'stdout': '',
            'stderr': str(e),
            'returncode': -1
        }

@app.route('/')
def index():
    """首页"""
    return render_template('index.html')

@app.route('/api/projects', methods=['GET'])
def get_projects():
    """获取所有项目"""
    projects = load_projects()
    return jsonify(projects)

@app.route('/api/deploy/<int:project_id>', methods=['POST'])
def deploy_project(project_id):
    """部署指定项目"""
    projects = load_projects()

    if project_id >= len(projects):
        return jsonify({'success': False, 'message': '项目不存在'}), 404

    project = projects[project_id]
    project_path = project['path']

    if not os.path.exists(project_path):
        return jsonify({'success': False, 'message': f'项目路径不存在: {project_path}'}), 404

    logs = []

    # 执行 git pull
    logs.append({'step': 'git pull', 'time': datetime.now().strftime('%H:%M:%S')})
    git_result = run_command('git pull', cwd=project_path)
    logs.append({
        'step': 'git pull',
        'success': git_result['success'],
        'output': git_result['stdout'] + git_result['stderr']
    })

    if not git_result['success']:
        return jsonify({
            'success': False,
            'message': 'Git pull 失败',
            'logs': logs
        })

    # 执行 docker compose build
    logs.append({'step': 'docker compose build', 'time': datetime.now().strftime('%H:%M:%S')})
    build_result = run_command('docker compose build', cwd=project_path)
    logs.append({
        'step': 'docker compose build',
        'success': build_result['success'],
        'output': build_result['stdout'] + build_result['stderr']
    })

    if not build_result['success']:
        send_dingtalk_notification(
            f"项目部署失败: {project['name']}",
            f"Docker compose build 失败\n\n{build_result['stderr']}",
            is_success=False
        )
        return jsonify({
            'success': False,
            'message': 'Docker compose build 失败',
            'logs': logs
        })

    # 执行 docker compose down && docker compose up -d（重启服务）
    if project.get('auto_restart', True):
        logs.append({'step': 'docker compose down', 'time': datetime.now().strftime('%H:%M:%S')})
        down_result = run_command('docker compose down', cwd=project_path)
        logs.append({
            'step': 'docker compose down',
            'success': down_result['success'],
            'output': down_result['stdout'] + down_result['stderr']
        })

        if not down_result['success']:
            send_dingtalk_notification(
                f"项目部署失败: {project['name']}",
                f"Docker compose down 失败\n\n{down_result['stderr']}",
                is_success=False
            )
            return jsonify({
                'success': False,
                'message': 'Docker compose down 失败',
                'logs': logs
            })

        logs.append({'step': 'docker compose up -d', 'time': datetime.now().strftime('%H:%M:%S')})
        up_result = run_command('docker compose up -d', cwd=project_path)
        logs.append({
            'step': 'docker compose up -d',
            'success': up_result['success'],
            'output': up_result['stdout'] + up_result['stderr']
        })

        if not up_result['success']:
            send_dingtalk_notification(
                f"项目部署失败: {project['name']}",
                f"Docker compose up 失败\n\n{up_result['stderr']}",
                is_success=False
            )
            return jsonify({
                'success': False,
                'message': 'Docker compose up 失败',
                'logs': logs
            })

    # 发送成功通知
    send_dingtalk_notification(
        f"项目部署成功: {project['name']}",
        f"项目已成功更新并重启",
        is_success=True
    )

    return jsonify({
        'success': True,
        'message': '部署成功',
        'logs': logs
    })

@app.route('/api/status/<int:project_id>', methods=['GET'])
def get_project_status(project_id):
    """获取项目状态"""
    projects = load_projects()

    if project_id >= len(projects):
        return jsonify({'success': False, 'message': '项目不存在'}), 404

    project = projects[project_id]
    project_path = project['path']

    # 获取 git 状态
    git_status = run_command('git status --short', cwd=project_path)
    git_branch = run_command('git branch --show-current', cwd=project_path)
    git_log = run_command('git log -1 --pretty=format:"%h - %an, %ar : %s"', cwd=project_path)

    # 获取 docker 容器状态
    docker_ps = run_command('docker compose ps', cwd=project_path)

    return jsonify({
        'success': True,
        'git_status': git_status['stdout'],
        'git_branch': git_branch['stdout'].strip(),
        'git_log': git_log['stdout'],
        'docker_status': docker_ps['stdout']
    })

@app.route('/api/system/info', methods=['GET'])
def get_system_info():
    """获取系统信息"""
    # 磁盘使用情况
    disk_result = run_command('df -h')

    # 内存使用情况
    memory_result = run_command('free -h')

    # CPU 使用情况
    cpu_result = run_command('top -bn1 | grep "Cpu(s)"')

    # 系统负载
    uptime_result = run_command('uptime')

    # Docker 使用情况
    docker_disk_result = run_command('docker system df')

    return jsonify({
        'success': True,
        'disk': disk_result['stdout'],
        'memory': memory_result['stdout'],
        'cpu': cpu_result['stdout'],
        'uptime': uptime_result['stdout'],
        'docker_disk': docker_disk_result['stdout']
    })

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """获取系统设置"""
    settings = load_settings()
    # 隐藏敏感信息
    if 'dingtalk' in settings and 'webhook_url' in settings['dingtalk']:
        webhook = settings['dingtalk']['webhook_url']
        if webhook:
            settings['dingtalk']['webhook_url'] = webhook[:30] + '...' if len(webhook) > 30 else webhook
    return jsonify(settings)

@app.route('/api/settings', methods=['POST'])
def update_settings():
    """更新系统设置"""
    data = request.json

    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return jsonify({'success': True, 'message': '设置已保存'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'保存失败: {str(e)}'}), 500

@app.route('/api/test-dingtalk', methods=['POST'])
def test_dingtalk():
    """测试钉钉通知"""
    result = send_dingtalk_notification(
        "测试通知",
        "这是一条测试消息，如果您收到此消息，说明钉钉通知配置成功！",
        is_success=True
    )

    if result:
        return jsonify({'success': True, 'message': '测试消息已发送'})
    else:
        return jsonify({'success': False, 'message': '发送失败，请检查配置'}), 500

@app.route('/api/projects', methods=['POST'])
def add_project():
    """添加新项目"""
    data = request.json

    # 验证必需字段
    if not data.get('name') or not data.get('path'):
        return jsonify({'success': False, 'message': '项目名称和路径不能为空'}), 400

    projects = load_projects()

    # 检查路径是否已存在
    for project in projects:
        if project['path'] == data['path']:
            return jsonify({'success': False, 'message': '该路径已存在'}), 400

    # 添加新项目
    new_project = {
        'name': data.get('name'),
        'description': data.get('description', ''),
        'path': data.get('path'),
        'auto_restart': data.get('auto_restart', True)
    }

    projects.append(new_project)

    if save_projects(projects):
        return jsonify({'success': True, 'message': '项目添加成功', 'projects': projects})
    else:
        return jsonify({'success': False, 'message': '保存失败'}), 500

@app.route('/api/projects/<int:project_id>', methods=['PUT'])
def update_project(project_id):
    """更新项目配置"""
    data = request.json
    projects = load_projects()

    if project_id >= len(projects):
        return jsonify({'success': False, 'message': '项目不存在'}), 404

    # 验证必需字段
    if not data.get('name') or not data.get('path'):
        return jsonify({'success': False, 'message': '项目名称和路径不能为空'}), 400

    # 检查路径是否与其他项目冲突
    for i, project in enumerate(projects):
        if i != project_id and project['path'] == data['path']:
            return jsonify({'success': False, 'message': '该路径已被其他项目使用'}), 400

    # 更新项目
    projects[project_id] = {
        'name': data.get('name'),
        'description': data.get('description', ''),
        'path': data.get('path'),
        'auto_restart': data.get('auto_restart', True)
    }

    if save_projects(projects):
        return jsonify({'success': True, 'message': '项目更新成功', 'projects': projects})
    else:
        return jsonify({'success': False, 'message': '保存失败'}), 500

@app.route('/api/projects/<int:project_id>', methods=['DELETE'])
def delete_project(project_id):
    """删除项目"""
    projects = load_projects()

    if project_id >= len(projects):
        return jsonify({'success': False, 'message': '项目不存在'}), 404

    deleted_project = projects.pop(project_id)

    if save_projects(projects):
        return jsonify({'success': True, 'message': f'项目 "{deleted_project["name"]}" 已删除', 'projects': projects})
    else:
        return jsonify({'success': False, 'message': '保存失败'}), 500

@app.route('/api/system/update', methods=['POST'])
def system_update():
    """执行系统更新"""
    # 获取脚本目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    update_script = os.path.join(script_dir, 'update.sh')

    if not os.path.exists(update_script):
        return jsonify({'success': False, 'message': '更新脚本不存在'}), 404

    try:
        # 在后台执行更新脚本
        # 使用 nohup 确保即使主进程退出也能继续执行
        subprocess.Popen(
            ['sudo', 'bash', update_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

        return jsonify({
            'success': True,
            'message': '更新已开始，服务将在几秒钟后重启。请稍后刷新页面。'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'启动更新失败: {str(e)}'}), 500

@app.route('/api/system/version', methods=['GET'])
def get_version():
    """获取当前版本信息"""
    script_dir = os.path.dirname(os.path.abspath(__file__))

    try:
        # 获取 git 信息
        branch = run_command('git branch --show-current', cwd=script_dir)
        commit = run_command('git log -1 --pretty=format:"%h - %s (%ar)"', cwd=script_dir)
        remote_status = run_command('git fetch origin && git rev-list --count HEAD..origin/main', cwd=script_dir)

        # 检查是否有更新
        behind_count = 0
        if remote_status['success']:
            try:
                behind_count = int(remote_status['stdout'].strip())
            except:
                behind_count = 0

        return jsonify({
            'success': True,
            'branch': branch['stdout'].strip() if branch['success'] else 'unknown',
            'commit': commit['stdout'].strip() if commit['success'] else 'unknown',
            'behind_count': behind_count,
            'has_update': behind_count > 0
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'获取版本信息失败: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=6666, debug=True)

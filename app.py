from flask import Flask, render_template, jsonify, request, Response, stream_with_context
import subprocess
import os
import json
from datetime import datetime
import threading
import requests
import time
import paramiko
import socket

app = Flask(__name__)

# 配置文件路径
CONFIG_FILE = 'projects.json'
SETTINGS_FILE = 'settings.json'
LOGS_DIR = 'logs'

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

def ensure_logs_dir():
    """确保日志目录存在"""
    if not os.path.exists(LOGS_DIR):
        os.makedirs(LOGS_DIR)

def save_operation_log(project_id, project_name, operation_type, success, output='', ssh_mode=False, ssh_host=''):
    """保存操作日志"""
    try:
        ensure_logs_dir()

        log_file = os.path.join(LOGS_DIR, f'project_{project_id}.json')

        # 加载现有日志
        logs = []
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)

        # 添加新日志（限制输出长度）
        max_output_length = 10000
        truncated_output = output[:max_output_length] + '...(输出过长，已截断)' if len(output) > max_output_length else output

        log_entry = {
            'id': len(logs),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'project_name': project_name,
            'operation': operation_type,
            'success': success,
            'output': truncated_output,
            'ssh_mode': ssh_mode,
            'ssh_host': ssh_host if ssh_mode else ''
        }

        logs.insert(0, log_entry)  # 最新的在前面

        # 只保留最近100条日志
        logs = logs[:100]

        # 保存日志
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)

        return True
    except Exception as e:
        print(f"保存日志失败: {e}")
        return False

def load_operation_logs(project_id, limit=50):
    """加载项目操作日志"""
    try:
        ensure_logs_dir()
        log_file = os.path.join(LOGS_DIR, f'project_{project_id}.json')

        if not os.path.exists(log_file):
            return []

        with open(log_file, 'r', encoding='utf-8') as f:
            logs = json.load(f)

        return logs[:limit]
    except Exception as e:
        print(f"加载日志失败: {e}")
        return []

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
        # 获取当前脚本目录（安装目录）
        script_dir = os.path.dirname(os.path.abspath(__file__))

        # 构建环境变量
        env = {
            **os.environ,
            'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
            # 为 git 命令添加 safe.directory 配置，避免 dubious ownership 错误
            'GIT_CONFIG_COUNT': '1',
            'GIT_CONFIG_KEY_0': 'safe.directory',
            'GIT_CONFIG_VALUE_0': script_dir
        }

        # 使用 bash 并设置完整的环境
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
            executable='/bin/bash',
            env=env
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

def run_ssh_command(command, ssh_config, cwd=None):
    """通过SSH执行命令并返回输出（非流式）"""
    ssh_client = None
    try:
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        host = ssh_config.get('host')
        port = ssh_config.get('port', 22)
        user = ssh_config.get('user', 'root')
        key_file = ssh_config.get('key_file')
        password = ssh_config.get('password')

        if not host:
            return {
                'success': False,
                'stdout': '',
                'stderr': 'SSH host not configured',
                'returncode': -1
            }

        # 连接参数
        connect_kwargs = {
            'hostname': host,
            'port': port,
            'username': user,
            'timeout': 10
        }

        # 认证方式
        if key_file and os.path.exists(key_file):
            connect_kwargs['key_filename'] = key_file
        elif password:
            connect_kwargs['password'] = password
        else:
            # 尝试使用默认密钥
            default_key = os.path.expanduser('~/.ssh/id_rsa')
            if os.path.exists(default_key):
                connect_kwargs['key_filename'] = default_key

        ssh_client.connect(**connect_kwargs)

        # 如果指定了工作目录，添加 cd 命令
        if cwd:
            command = f"cd {cwd} && {command}"

        stdin, stdout, stderr = ssh_client.exec_command(command, get_pty=False, timeout=30)

        stdout_data = stdout.read().decode('utf-8')
        stderr_data = stderr.read().decode('utf-8')
        return_code = stdout.channel.recv_exit_status()

        return {
            'success': return_code == 0,
            'stdout': stdout_data,
            'stderr': stderr_data,
            'returncode': return_code
        }

    except socket.timeout:
        return {
            'success': False,
            'stdout': '',
            'stderr': 'SSH connection timeout',
            'returncode': -1
        }
    except paramiko.AuthenticationException:
        return {
            'success': False,
            'stdout': '',
            'stderr': 'SSH authentication failed',
            'returncode': -1
        }
    except Exception as e:
        return {
            'success': False,
            'stdout': '',
            'stderr': f'SSH error: {str(e)}',
            'returncode': -1
        }
    finally:
        if ssh_client:
            ssh_client.close()

def execute_command(command, project, cwd=None):
    """根据项目配置选择本地或SSH执行（非流式）"""
    ssh_config = project.get('ssh', {})
    actual_cwd = cwd if cwd else project.get('path')

    if ssh_config.get('enabled', False):
        # SSH模式
        return run_ssh_command(command, ssh_config, actual_cwd)
    else:
        # 本地模式
        return run_command(command, actual_cwd)

def run_command_stream(command, cwd=None, timeout=3600, idle_timeout=300):
    """执行命令并实时流式返回输出（生成器），最后一行返回退出码

    Args:
        command: 要执行的命令
        cwd: 工作目录
        timeout: 总超时时间（秒），默认1小时
        idle_timeout: 空闲超时时间（秒），默认5分钟无输出则超时
    """
    return_code = -1
    try:
        # 获取当前脚本目录（安装目录）
        script_dir = os.path.dirname(os.path.abspath(__file__))

        # 构建环境变量
        env = {
            **os.environ,
            'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
            # 为 git 命令添加 safe.directory 配置，避免 dubious ownership 错误
            'GIT_CONFIG_COUNT': '1',
            'GIT_CONFIG_KEY_0': 'safe.directory',
            'GIT_CONFIG_VALUE_0': script_dir
        }

        # 使用 Popen 来实时获取输出
        process = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # 合并 stderr 到 stdout
            text=True,
            executable='/bin/bash',
            env=env,
            bufsize=1,  # 行缓冲
            universal_newlines=True
        )

        # 记录开始时间和最后输出时间
        start_time = time.time()
        last_output_time = start_time

        # 实时读取输出 - 添加超时检测
        import select
        while True:
            # 检查总超时
            if time.time() - start_time > timeout:
                process.kill()
                yield ('output', f"\n[超时] 命令执行超过 {timeout} 秒，已强制终止\n")
                yield ('returncode', -1)
                return

            # 检查空闲超时
            if time.time() - last_output_time > idle_timeout:
                process.kill()
                yield ('output', f"\n[空闲超时] 命令超过 {idle_timeout} 秒无输出，已强制终止\n")
                yield ('output', f"提示: 可能是交互式命令等待输入，请使用非交互式参数（如: apt-get -y, docker build --no-cache）\n")
                yield ('returncode', -1)
                return

            # 使用select检查是否有数据可读（超时0.1秒）
            if process.stdout in select.select([process.stdout], [], [], 0.1)[0]:
                line = process.stdout.readline()
                if line:
                    yield ('output', line)
                    last_output_time = time.time()
                else:
                    # 没有更多数据，进程可能已结束
                    break
            else:
                # 检查进程是否还在运行
                if process.poll() is not None:
                    break

        process.stdout.close()
        return_code = process.wait()

        # 返回退出码
        yield ('returncode', return_code)

    except Exception as e:
        yield ('output', f"\n[异常] {str(e)}\n")
        yield ('returncode', -1)

def run_ssh_command_stream(command, ssh_config, cwd=None, timeout=3600, idle_timeout=300):
    """通过SSH执行命令并实时流式返回输出（生成器）

    Args:
        command: 要执行的命令
        ssh_config: SSH配置
        cwd: 工作目录
        timeout: 总超时时间（秒），默认1小时
        idle_timeout: 空闲超时时间（秒），默认5分钟无输出则超时
    """
    ssh_client = None
    return_code = -1

    try:
        # 创建SSH客户端
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # 连接参数
        host = ssh_config.get('host')
        port = ssh_config.get('port', 22)
        user = ssh_config.get('user', 'root')
        key_file = ssh_config.get('key_file')
        password = ssh_config.get('password')

        # 连接到远程服务器
        connect_kwargs = {
            'hostname': host,
            'port': port,
            'username': user,
            'timeout': 10
        }

        if key_file and os.path.exists(key_file):
            connect_kwargs['key_filename'] = key_file
        elif password:
            connect_kwargs['password'] = password
        else:
            # 尝试使用默认密钥
            default_keys = [
                os.path.expanduser('~/.ssh/id_rsa'),
                os.path.expanduser('~/.ssh/id_ed25519')
            ]
            for key in default_keys:
                if os.path.exists(key):
                    connect_kwargs['key_filename'] = key
                    break

        ssh_client.connect(**connect_kwargs)

        # 如果指定了工作目录，添加cd命令
        if cwd:
            command = f"cd {cwd} && {command}"

        # 执行命令 - 不使用PTY，避免缓冲问题
        stdin, stdout, stderr = ssh_client.exec_command(command, get_pty=False)

        # 设置channel为非阻塞模式
        channel = stdout.channel
        channel.setblocking(0)

        # 实时读取输出 - 使用非阻塞读取，添加超时检测
        buffer = b''
        start_time = time.time()
        last_output_time = start_time

        while not channel.exit_status_ready() or channel.recv_ready() or channel.recv_stderr_ready():
            # 检查总超时
            if time.time() - start_time > timeout:
                channel.close()
                yield ('output', f"\n[超时] SSH命令执行超过 {timeout} 秒，已强制终止\n")
                yield ('returncode', -1)
                return

            # 检查空闲超时
            if time.time() - last_output_time > idle_timeout:
                channel.close()
                yield ('output', f"\n[空闲超时] SSH命令超过 {idle_timeout} 秒无输出，已强制终止\n")
                yield ('output', f"提示: 可能是交互式命令等待输入，请使用非交互式参数\n")
                yield ('returncode', -1)
                return

            # 读取stdout
            if channel.recv_ready():
                data = channel.recv(1024)
                if data:
                    buffer += data
                    last_output_time = time.time()
                    # 按行分割并输出
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        try:
                            yield ('output', line.decode('utf-8', errors='replace') + '\n')
                        except:
                            yield ('output', line.decode('latin-1') + '\n')

            # 读取stderr
            if channel.recv_stderr_ready():
                data = channel.recv_stderr(1024)
                if data:
                    buffer += data
                    last_output_time = time.time()
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        try:
                            yield ('output', line.decode('utf-8', errors='replace') + '\n')
                        except:
                            yield ('output', line.decode('latin-1') + '\n')

            # 短暂休眠，避免CPU占用过高
            time.sleep(0.01)

        # 输出剩余的buffer
        if buffer:
            try:
                yield ('output', buffer.decode('utf-8', errors='replace'))
            except:
                yield ('output', buffer.decode('latin-1'))

        # 获取退出码
        return_code = channel.recv_exit_status()
        yield ('returncode', return_code)

    except paramiko.AuthenticationException:
        yield ('output', f"\n[SSH错误] 认证失败，请检查用户名、密码或密钥\n")
        yield ('returncode', -1)
    except paramiko.SSHException as e:
        yield ('output', f"\n[SSH错误] SSH连接异常: {str(e)}\n")
        yield ('returncode', -1)
    except socket.timeout:
        yield ('output', f"\n[SSH错误] 连接超时\n")
        yield ('returncode', -1)
    except Exception as e:
        yield ('output', f"\n[异常] {str(e)}\n")
        yield ('returncode', -1)
    finally:
        if ssh_client:
            ssh_client.close()

def execute_command_stream(command, project, cwd=None):
    """根据项目配置选择本地或SSH执行（生成器）"""
    ssh_config = project.get('ssh', {})

    if ssh_config.get('enabled', False):
        # SSH模式
        actual_cwd = cwd if cwd else project.get('path')
        for item in run_ssh_command_stream(command, ssh_config, actual_cwd):
            yield item
    else:
        # 本地模式
        actual_cwd = cwd if cwd else project.get('path')
        for item in run_command_stream(command, actual_cwd):
            yield item

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

@app.route('/api/deploy-stream/<int:project_id>', methods=['GET', 'POST'])
def deploy_project_stream(project_id):
    """部署指定项目（实时流式输出）"""
    projects = load_projects()

    if project_id >= len(projects):
        return jsonify({'success': False, 'message': '项目不存在'}), 404

    project = projects[project_id]
    project_path = project['path']

    if not os.path.exists(project_path):
        return jsonify({'success': False, 'message': f'项目路径不存在: {project_path}'}), 404

    def generate():
        """生成器函数，用于流式输出"""
        overall_success = True
        error_message = ''

        # 发送开始信号
        yield f"data: {json.dumps({'type': 'start', 'project': project['name']})}\n\n"

        # 执行 git pull
        yield f"data: {json.dumps({'type': 'step', 'step': 'git pull', 'status': 'running'})}\n\n"

        git_return_code = 0
        for item_type, content in run_command_stream('git pull', cwd=project_path):
            if item_type == 'output':
                yield f"data: {json.dumps({'type': 'output', 'step': 'git pull', 'line': content.rstrip()})}\n\n"
            elif item_type == 'returncode':
                git_return_code = content

        # 检查 git pull 是否成功
        if git_return_code != 0:
            overall_success = False
            error_message = f'Git pull 失败 (退出码: {git_return_code})'
            yield f"data: {json.dumps({'type': 'step', 'step': 'git pull', 'status': 'error'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'success': False, 'message': error_message})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'step', 'step': 'git pull', 'status': 'success'})}\n\n"

        # 执行 docker compose build
        yield f"data: {json.dumps({'type': 'step', 'step': 'docker compose build', 'status': 'running'})}\n\n"

        build_return_code = 0
        for item_type, content in run_command_stream('docker compose build', cwd=project_path):
            if item_type == 'output':
                yield f"data: {json.dumps({'type': 'output', 'step': 'docker compose build', 'line': content.rstrip()})}\n\n"
            elif item_type == 'returncode':
                build_return_code = content

        # 验证 build 结果
        if build_return_code != 0:
            overall_success = False
            error_message = f'Docker compose build 失败 (退出码: {build_return_code})'
            yield f"data: {json.dumps({'type': 'step', 'step': 'docker compose build', 'status': 'error'})}\n\n"
            send_dingtalk_notification(
                f"项目部署失败: {project['name']}",
                f"Docker compose build 失败",
                is_success=False
            )
            yield f"data: {json.dumps({'type': 'complete', 'success': False, 'message': error_message})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'step', 'step': 'docker compose build', 'status': 'success'})}\n\n"

        # 执行 docker compose down && docker compose up -d（重启服务）
        if project.get('auto_restart', True):
            # docker compose down
            yield f"data: {json.dumps({'type': 'step', 'step': 'docker compose down', 'status': 'running'})}\n\n"

            down_return_code = 0
            for item_type, content in run_command_stream('docker compose down', cwd=project_path):
                if item_type == 'output':
                    yield f"data: {json.dumps({'type': 'output', 'step': 'docker compose down', 'line': content.rstrip()})}\n\n"
                elif item_type == 'returncode':
                    down_return_code = content

            if down_return_code == 0:
                yield f"data: {json.dumps({'type': 'step', 'step': 'docker compose down', 'status': 'success'})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'step', 'step': 'docker compose down', 'status': 'error'})}\n\n"

            # docker compose up -d
            yield f"data: {json.dumps({'type': 'step', 'step': 'docker compose up -d', 'status': 'running'})}\n\n"

            up_return_code = 0
            for item_type, content in run_command_stream('docker compose up -d', cwd=project_path):
                if item_type == 'output':
                    yield f"data: {json.dumps({'type': 'output', 'step': 'docker compose up -d', 'line': content.rstrip()})}\n\n"
                elif item_type == 'returncode':
                    up_return_code = content

            if up_return_code == 0:
                yield f"data: {json.dumps({'type': 'step', 'step': 'docker compose up -d', 'status': 'success'})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'step', 'step': 'docker compose up -d', 'status': 'error'})}\n\n"

        # 发送成功通知
        send_dingtalk_notification(
            f"项目部署成功: {project['name']}",
            f"项目已成功更新并重启",
            is_success=True
        )

        yield f"data: {json.dumps({'type': 'complete', 'success': True, 'message': '部署成功'})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/api/pull-build/<int:project_id>', methods=['GET', 'POST'])
def pull_build_project(project_id):
    """执行 git pull 和 docker compose build（实时流式输出）"""
    projects = load_projects()

    if project_id >= len(projects):
        return jsonify({'success': False, 'message': '项目不存在'}), 404

    project = projects[project_id]
    project_path = project['path']

    # SSH模式下不检查本地路径
    if not project.get('ssh', {}).get('enabled', False):
        if not os.path.exists(project_path):
            return jsonify({'success': False, 'message': f'项目路径不存在: {project_path}'}), 404

    def generate():
        """生成器函数，用于流式输出"""
        ssh_mode = project.get('ssh', {}).get('enabled', False)
        ssh_host = project.get('ssh', {}).get('host', '')
        mode_text = f" (SSH: {ssh_host})" if ssh_mode else " (本地)"

        output_log = []  # 收集输出用于日志
        max_log_lines = 1000  # 限制日志行数，避免内存问题
        line_count = 0

        # 发送开始信号
        yield f"data: {json.dumps({'type': 'start', 'project': project['name'] + mode_text})}\n\n"

        # 执行 git pull
        yield f"data: {json.dumps({'type': 'step', 'step': 'git pull', 'status': 'running'})}\n\n"

        git_return_code = 0
        for item_type, content in execute_command_stream('git pull', project):
            if item_type == 'output':
                if line_count < max_log_lines:
                    output_log.append(content)
                    line_count += 1
                yield f"data: {json.dumps({'type': 'output', 'step': 'git pull', 'line': content.rstrip()})}\n\n"
            elif item_type == 'returncode':
                git_return_code = content

        if git_return_code != 0:
            error_message = f'Git pull 失败 (退出码: {git_return_code})'
            yield f"data: {json.dumps({'type': 'step', 'step': 'git pull', 'status': 'error'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'success': False, 'message': error_message})}\n\n"
            # 异步保存日志
            threading.Thread(target=save_operation_log, args=(project_id, project['name'], 'Pull & Build', False, ''.join(output_log), ssh_mode, ssh_host), daemon=True).start()
            return

        yield f"data: {json.dumps({'type': 'step', 'step': 'git pull', 'status': 'success'})}\n\n"

        # 执行 docker compose build
        yield f"data: {json.dumps({'type': 'step', 'step': 'docker compose build', 'status': 'running'})}\n\n"

        build_return_code = 0
        for item_type, content in execute_command_stream('docker compose build', project):
            if item_type == 'output':
                if line_count < max_log_lines:
                    output_log.append(content)
                    line_count += 1
                yield f"data: {json.dumps({'type': 'output', 'step': 'docker compose build', 'line': content.rstrip()})}\n\n"
            elif item_type == 'returncode':
                build_return_code = content

        if build_return_code != 0:
            error_message = f'Docker compose build 失败 (退出码: {build_return_code})'
            yield f"data: {json.dumps({'type': 'step', 'step': 'docker compose build', 'status': 'error'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'success': False, 'message': error_message})}\n\n"
            # 异步保存日志
            threading.Thread(target=save_operation_log, args=(project_id, project['name'], 'Pull & Build', False, ''.join(output_log), ssh_mode, ssh_host), daemon=True).start()
            return

        yield f"data: {json.dumps({'type': 'step', 'step': 'docker compose build', 'status': 'success'})}\n\n"
        yield f"data: {json.dumps({'type': 'complete', 'success': True, 'message': 'Pull & Build 完成'})}\n\n"

        # 异步保存日志
        threading.Thread(target=save_operation_log, args=(project_id, project['name'], 'Pull & Build', True, ''.join(output_log), ssh_mode, ssh_host), daemon=True).start()

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/api/restart/<int:project_id>', methods=['GET', 'POST'])
def restart_project(project_id):
    """执行 docker compose down 和 up -d（实时流式输出）"""
    projects = load_projects()

    if project_id >= len(projects):
        return jsonify({'success': False, 'message': '项目不存在'}), 404

    project = projects[project_id]
    project_path = project['path']

    # SSH模式下不检查本地路径
    if not project.get('ssh', {}).get('enabled', False):
        if not os.path.exists(project_path):
            return jsonify({'success': False, 'message': f'项目路径不存在: {project_path}'}), 404

    def generate():
        """生成器函数，用于流式输出"""
        ssh_mode = project.get('ssh', {}).get('enabled', False)
        ssh_host = project.get('ssh', {}).get('host', '')
        mode_text = f" (SSH: {ssh_host})" if ssh_mode else " (本地)"

        output_log = []  # 收集输出用于日志
        max_log_lines = 1000  # 限制日志行数
        line_count = 0

        # 发送开始信号
        yield f"data: {json.dumps({'type': 'start', 'project': project['name'] + mode_text})}\n\n"

        # docker compose down
        yield f"data: {json.dumps({'type': 'step', 'step': 'docker compose down', 'status': 'running'})}\n\n"

        down_return_code = 0
        for item_type, content in execute_command_stream('docker compose down', project, cwd=project_path):
            if item_type == 'output':
                if line_count < max_log_lines:
                    output_log.append(content)
                    line_count += 1
                yield f"data: {json.dumps({'type': 'output', 'step': 'docker compose down', 'line': content.rstrip()})}\n\n"
            elif item_type == 'returncode':
                down_return_code = content

        if down_return_code == 0:
            yield f"data: {json.dumps({'type': 'step', 'step': 'docker compose down', 'status': 'success'})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'step', 'step': 'docker compose down', 'status': 'error'})}\n\n"

        # docker compose up -d
        yield f"data: {json.dumps({'type': 'step', 'step': 'docker compose up -d', 'status': 'running'})}\n\n"

        up_return_code = 0
        for item_type, content in execute_command_stream('docker compose up -d', project, cwd=project_path):
            if item_type == 'output':
                if line_count < max_log_lines:
                    output_log.append(content)
                    line_count += 1
                yield f"data: {json.dumps({'type': 'output', 'step': 'docker compose up -d', 'line': content.rstrip()})}\n\n"
            elif item_type == 'returncode':
                up_return_code = content

        success = (down_return_code == 0 and up_return_code == 0)

        if up_return_code == 0:
            yield f"data: {json.dumps({'type': 'step', 'step': 'docker compose up -d', 'status': 'success'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'success': True, 'message': '重启完成'})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'step', 'step': 'docker compose up -d', 'status': 'error'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'success': False, 'message': 'docker compose up 失败'})}\n\n"

        # 异步保存日志
        threading.Thread(target=save_operation_log, args=(project_id, project['name'], 'Down & Up', success, ''.join(output_log), ssh_mode, ssh_host), daemon=True).start()

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/api/clean/<int:project_id>', methods=['GET', 'POST'])
def clean_project(project_id):
    """执行 docker system prune（实时流式输出）"""
    projects = load_projects()

    if project_id >= len(projects):
        return jsonify({'success': False, 'message': '项目不存在'}), 404

    project = projects[project_id]
    project_path = project['path']

    # SSH模式下不检查本地路径
    if not project.get('ssh', {}).get('enabled', False):
        if not os.path.exists(project_path):
            return jsonify({'success': False, 'message': f'项目路径不存在: {project_path}'}), 404

    def generate():
        """生成器函数，用于流式输出"""
        ssh_mode = project.get('ssh', {}).get('enabled', False)
        ssh_host = project.get('ssh', {}).get('host', '')
        mode_text = f" (SSH: {ssh_host})" if ssh_mode else " (本地)"

        output_log = []  # 收集输出用于日志
        max_log_lines = 1000  # 限制日志行数
        line_count = 0

        # 发送开始信号
        yield f"data: {json.dumps({'type': 'start', 'project': project['name'] + mode_text})}\n\n"

        # docker system prune
        yield f"data: {json.dumps({'type': 'step', 'step': 'docker system prune -f', 'status': 'running'})}\n\n"

        prune_return_code = 0
        for item_type, content in execute_command_stream('docker system prune -af', project, cwd=project_path):
            if item_type == 'output':
                if line_count < max_log_lines:
                    output_log.append(content)
                    line_count += 1
                yield f"data: {json.dumps({'type': 'output', 'step': 'docker system prune -f', 'line': content.rstrip()})}\n\n"
            elif item_type == 'returncode':
                prune_return_code = content

        success = (prune_return_code == 0)

        if success:
            yield f"data: {json.dumps({'type': 'step', 'step': 'docker system prune -f', 'status': 'success'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'success': True, 'message': '清理完成'})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'step', 'step': 'docker system prune -f', 'status': 'error'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'success': False, 'message': '清理失败'})}\n\n"

        # 异步保存日志
        threading.Thread(target=save_operation_log, args=(project_id, project['name'], 'Clean', success, ''.join(output_log), ssh_mode, ssh_host), daemon=True).start()

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/api/custom-command/<int:project_id>', methods=['POST'])
def execute_custom_command(project_id):
    """执行用户自定义命令（实时流式输出）"""
    projects = load_projects()

    if project_id >= len(projects):
        return jsonify({'success': False, 'message': '项目不存在'}), 404

    project = projects[project_id]
    project_path = project['path']

    # SSH模式下不检查本地路径
    if not project.get('ssh', {}).get('enabled', False):
        if not os.path.exists(project_path):
            return jsonify({'success': False, 'message': f'项目路径不存在: {project_path}'}), 404

    # 获取用户输入的命令
    data = request.get_json()
    if not data or 'command' not in data:
        return jsonify({'success': False, 'message': '未提供命令'}), 400

    custom_command = data['command'].strip()
    if not custom_command:
        return jsonify({'success': False, 'message': '命令不能为空'}), 400

    # 安全检查：禁止一些危险命令
    dangerous_patterns = ['rm -rf /', 'mkfs', 'dd if=', ':(){:|:&};:', 'fork bomb']
    for pattern in dangerous_patterns:
        if pattern in custom_command.lower():
            return jsonify({'success': False, 'message': f'检测到危险命令，已阻止执行'}), 403

    # 检测可能的交互式命令并警告
    interactive_commands = {
        'apt-get install': '使用 apt-get install -y 避免交互',
        'apt install': '使用 apt install -y 避免交互',
        'yum install': '使用 yum install -y 避免交互',
        'npm install': '通常不需要交互，但注意某些包可能需要',
        'docker login': '这是交互式命令，建议提前登录',
        'ssh': 'SSH命令需要交互，请使用密钥认证或传递参数',
        'sudo': 'sudo可能需要密码，建议配置NOPASSWD',
        'vim': '编辑器命令无法使用，请用sed/awk等非交互工具',
        'nano': '编辑器命令无法使用，请用sed/awk等非交互工具',
        'less': '分页命令无法使用，请直接查看文件或使用cat',
        'more': '分页命令无法使用，请直接查看文件或使用cat'
    }

    warning_message = None
    for cmd_pattern, suggestion in interactive_commands.items():
        if cmd_pattern in custom_command.lower():
            warning_message = f"⚠️ 检测到可能的交互式命令: {suggestion}"
            break

    def generate():
        """生成器函数，用于流式输出"""
        ssh_mode = project.get('ssh', {}).get('enabled', False)
        ssh_host = project.get('ssh', {}).get('host', '')
        mode_text = f" SSH({ssh_host})" if ssh_mode else " 本地"

        output_log = []  # 收集输出用于日志
        max_log_lines = 1000  # 限制日志行数
        line_count = 0

        # 发送开始信号
        yield f"data: {json.dumps({'type': 'start', 'project': project['name'] + mode_text, 'command': custom_command})}\n\n"

        # 如果有警告，先显示警告
        if warning_message:
            yield f"data: {json.dumps({'type': 'output', 'step': 'warning', 'line': warning_message})}\n\n"
            yield f"data: {json.dumps({'type': 'output', 'step': 'warning', 'line': '命令将在5分钟无输出后自动超时'})}\n\n"
            yield f"data: {json.dumps({'type': 'output', 'step': 'warning', 'line': ''})}\n\n"

        # 执行自定义命令
        yield f"data: {json.dumps({'type': 'step', 'step': f'执行: {custom_command}', 'status': 'running'})}\n\n"

        cmd_return_code = 0
        for item_type, content in execute_command_stream(custom_command, project, cwd=project_path):
            if item_type == 'output':
                if line_count < max_log_lines:
                    output_log.append(content)
                    line_count += 1
                yield f"data: {json.dumps({'type': 'output', 'step': custom_command, 'line': content.rstrip()})}\n\n"
            elif item_type == 'returncode':
                cmd_return_code = content

        success = (cmd_return_code == 0)

        if success:
            yield f"data: {json.dumps({'type': 'step', 'step': custom_command, 'status': 'success'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'success': True, 'message': '命令执行完成'})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'step', 'step': custom_command, 'status': 'error'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'success': False, 'message': f'命令执行失败 (退出码: {cmd_return_code})'})}\n\n"

        # 异步保存日志
        threading.Thread(target=save_operation_log, args=(project_id, project['name'], f'自定义命令: {custom_command}', success, ''.join(output_log), ssh_mode, ssh_host), daemon=True).start()

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/api/status/<int:project_id>', methods=['GET'])
def get_project_status(project_id):
    """获取项目状态"""
    projects = load_projects()

    if project_id >= len(projects):
        return jsonify({'success': False, 'message': '项目不存在'}), 404

    project = projects[project_id]
    project_path = project['path']

    # 使用 execute_command 支持本地和SSH模式
    # 获取 git 状态
    git_status = execute_command('git status --short', project, cwd=project_path)
    git_branch = execute_command('git branch --show-current', project, cwd=project_path)
    git_log = execute_command('git log -1 --pretty=format:"%h - %an, %ar : %s"', project, cwd=project_path)

    # 获取 docker 容器状态
    docker_ps = execute_command('docker compose ps', project, cwd=project_path)

    # 获取镜像构建时间 - 使用docker compose images命令更可靠
    images_info = []

    # 尝试使用 docker compose images 命令获取镜像信息
    # 不使用 2>/dev/null，因为在 SSH 的 cd && command 模式下可能有问题
    images_cmd = 'docker compose images --format json'
    images_result = execute_command(images_cmd, project, cwd=project_path)

    # Debug logging
    print(f"DEBUG: SSH mode: {ssh_config.get('enabled', False)}")
    print(f"DEBUG: images command success: {images_result['success']}")
    print(f"DEBUG: images stdout length: {len(images_result['stdout'])}")
    print(f"DEBUG: images stdout preview: {images_result['stdout'][:200]}")
    if images_result['stderr']:
        print(f"DEBUG: images stderr: {images_result['stderr']}")

    if images_result['success'] and images_result['stdout'].strip():
        # 解析JSON输出
        try:
            import json as json_lib
            lines = images_result['stdout'].strip().split('\n')
            for line in lines:
                if line.strip():
                    try:
                        img_data = json_lib.loads(line)
                        service = img_data.get('Service', img_data.get('Container', ''))
                        repository = img_data.get('Repository', '')
                        tag = img_data.get('Tag', '')

                        if repository and tag:
                            image_name = f"{repository}:{tag}"
                        elif repository:
                            image_name = repository
                        else:
                            continue

                        # 获取镜像创建时间
                        # 不使用 2>/dev/null，因为在 SSH 的 cd && command 模式下可能有问题
                        inspect_cmd = f'docker inspect --format="{{{{.Created}}}}" "{image_name}"'
                        inspect_result = execute_command(inspect_cmd, project, cwd=project_path)

                        print(f"DEBUG: Inspect image: {image_name}")
                        print(f"DEBUG: Inspect success: {inspect_result['success']}")
                        print(f"DEBUG: Inspect stdout: {inspect_result['stdout']}")
                        if inspect_result['stderr']:
                            print(f"DEBUG: Inspect stderr: {inspect_result['stderr']}")

                        if inspect_result['success'] and inspect_result['stdout'].strip():
                            created_time = inspect_result['stdout'].strip()
                            images_info.append({
                                'service': service,
                                'image': image_name,
                                'created': created_time
                            })
                    except json_lib.JSONDecodeError:
                        continue
        except Exception as e:
            pass

    # 如果docker compose images不可用，使用备用方法
    if not images_info:
        docker_ps_cmd = 'docker compose ps --format json'
        ps_result = execute_command(docker_ps_cmd, project, cwd=project_path)

        print(f"DEBUG: Fallback to ps command")
        print(f"DEBUG: ps command success: {ps_result['success']}")
        print(f"DEBUG: ps stdout length: {len(ps_result['stdout'])}")

        if ps_result['success'] and ps_result['stdout'].strip():
            try:
                import json as json_lib
                lines = ps_result['stdout'].strip().split('\n')
                processed_images = set()  # 避免重复

                for line in lines:
                    if line.strip():
                        try:
                            container_data = json_lib.loads(line)
                            service = container_data.get('Service', container_data.get('Name', ''))
                            image_name = container_data.get('Image', '')

                            if image_name and image_name not in processed_images:
                                processed_images.add(image_name)

                                # 获取镜像创建时间
                                inspect_cmd = f'docker inspect --format="{{{{.Created}}}}" "{image_name}"'
                                inspect_result = execute_command(inspect_cmd, project, cwd=project_path)

                                if inspect_result['success'] and inspect_result['stdout'].strip():
                                    created_time = inspect_result['stdout'].strip()
                                    images_info.append({
                                        'service': service,
                                        'image': image_name,
                                        'created': created_time
                                    })
                        except json_lib.JSONDecodeError:
                            continue
            except Exception as e:
                pass

    return jsonify({
        'success': True,
        'git_status': git_status['stdout'],
        'git_branch': git_branch['stdout'].strip(),
        'git_log': git_log['stdout'],
        'docker_status': docker_ps['stdout'],
        'images_info': images_info
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
        'disk': disk_result['stdout'] if disk_result['success'] else f"错误: {disk_result['stderr']}",
        'memory': memory_result['stdout'] if memory_result['success'] else f"错误: {memory_result['stderr']}",
        'cpu': cpu_result['stdout'] if cpu_result['success'] else f"错误: {cpu_result['stderr']}",
        'uptime': uptime_result['stdout'] if uptime_result['success'] else f"错误: {uptime_result['stderr']}",
        'docker_disk': docker_disk_result['stdout'] if docker_disk_result['success'] else f"错误: {docker_disk_result['stderr']}"
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

    # 添加SSH配置（如果有）
    if 'ssh' in data:
        new_project['ssh'] = data['ssh']

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

    # 添加SSH配置（如果有）
    if 'ssh' in data:
        projects[project_id]['ssh'] = data['ssh']

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

@app.route('/api/logs/<int:project_id>', methods=['GET'])
def get_project_logs(project_id):
    """获取项目操作日志"""
    projects = load_projects()

    if project_id >= len(projects):
        return jsonify({'success': False, 'message': '项目不存在'}), 404

    # 获取limit参数，默认50条
    limit = request.args.get('limit', 50, type=int)
    limit = min(limit, 100)  # 最多100条

    logs = load_operation_logs(project_id, limit)

    return jsonify({
        'success': True,
        'logs': logs,
        'total': len(logs)
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=6666, debug=True)

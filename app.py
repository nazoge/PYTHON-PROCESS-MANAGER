import os
import signal
import subprocess
import psutil
import time
import json
import shutil
import platform
from datetime import datetime
from flask import Flask, render_template, request, redirect, jsonify, send_file

app = Flask(__name__)

if '__file__' in globals():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
else:
    BASE_DIR = os.getcwd()

SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
FILES_DIR = os.path.join(BASE_DIR, "files")
PID_FILE = os.path.join(BASE_DIR, "process_state.json")
CONFIG_FILE = os.path.join(BASE_DIR, "resource_config.json")

os.makedirs(SCRIPTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(FILES_DIR, exist_ok=True)

RUNNING_PROCESSES = {}

IS_LINUX = platform.system() == "Linux"

if IS_LINUX:
    import resource

def load_state():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(state):
    with open(PID_FILE, "w") as f:
        json.dump(state, f, indent=4)

def load_resource_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_resource_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

def get_process_info(pid):
    try:
        p = psutil.Process(pid)
        if p.status() == psutil.STATUS_ZOMBIE:
            return "Zombie", 0, 0
        return "Running", p.cpu_percent(), p.memory_info().rss / (1024 * 1024)
    except psutil.NoSuchProcess:
        return "Stopped", 0, 0

def create_resource_limiter(script_name):
    if not IS_LINUX:
        return None
    
    config = load_resource_config()
    script_config = config.get(script_name, {})
    
    memory_limit_mb = script_config.get("memory_limit_mb", 0)
    cpu_time_limit = script_config.get("cpu_time_limit", 0)
    
    if not memory_limit_mb and not cpu_time_limit:
        return None
    
    def limiter():
        if memory_limit_mb > 0:
            memory_bytes = memory_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        
        if cpu_time_limit > 0:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_time_limit, cpu_time_limit))
    
    return limiter


@app.route("/")
def index():
    state = load_state()
    scripts_data = []
    
    if os.path.exists(SCRIPTS_DIR):
        files = sorted([f for f in os.listdir(SCRIPTS_DIR) if f.endswith(".py")])
        for f in files:
            pid = state.get(f)
            status = "Stopped"
            mem = 0
            cpu = 0
            
            if pid:
                status, cpu, mem = get_process_info(pid)
                if status == "Stopped":
                    if f in state:
                        del state[f]
            
            scripts_data.append({
                "name": f,
                "status": status,
                "pid": pid if pid else "-",
                "cpu": cpu,
                "mem": mem
            })
    
    save_state(state)
    
    disk = psutil.disk_usage('/').percent
    cpu_sys = psutil.cpu_percent()
    
    return render_template("index.html",
                           scripts=scripts_data,
                           disk_percent=disk,
                           cpu_percent=cpu_sys,
                           current_log_name=None)


@app.route("/upload", methods=["POST"])
def upload():
    if 'file' not in request.files:
        return redirect("/")
    file = request.files['file']
    if file.filename == '':
        return redirect("/")
    if file:
        from werkzeug.utils import secure_filename
        filename = secure_filename(file.filename)
        save_path = os.path.join(SCRIPTS_DIR, filename)
        file.save(save_path)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{os.path.splitext(filename)[0]}_{timestamp}.py"
        shutil.copy2(save_path, os.path.join(BACKUP_DIR, backup_name))
    
    return redirect("/")


@app.route("/install", methods=["POST"])
def install_package():
    package = request.form.get("package")
    if not package:
        return redirect("/")
    
    install_log = os.path.join(LOGS_DIR, "pip_install.log")
    with open(install_log, "a") as log_file:
        log_file.write(f"\n--- Installing {package} ({time.strftime('%Y-%m-%d %H:%M:%S')}) ---\n")
        subprocess.run(
            ["pip", "install", "--no-cache-dir", package],
            stdout=log_file,
            stderr=log_file
        )
    return redirect("/logs/pip_install")


@app.route("/start/<script_name>", methods=["POST"])
def start(script_name):
    global RUNNING_PROCESSES
    state = load_state()
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    log_path = os.path.join(LOGS_DIR, f"{script_name}.log")
    
    script_base = os.path.splitext(script_name)[0]
    work_dir = os.path.join(FILES_DIR, script_base)
    os.makedirs(work_dir, exist_ok=True)
    
    if script_name in state and get_process_info(state[script_name])[0] == "Running":
        return redirect("/")
    
    limiter = create_resource_limiter(script_name)
    
    log_file = open(log_path, "a")
    proc = subprocess.Popen(
        ["python3", "-u", script_path],
        stdin=subprocess.PIPE,
        stdout=log_file,
        stderr=log_file,
        start_new_session=True,
        preexec_fn=limiter,
        cwd=work_dir
    )
    
    RUNNING_PROCESSES[script_name] = {"proc": proc, "log_file": log_file}
    state[script_name] = proc.pid
    save_state(state)
    return redirect("/")


@app.route("/stop/<script_name>", methods=["POST"])
def stop(script_name):
    global RUNNING_PROCESSES
    state = load_state()
    pid = state.get(script_name)
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)
            if psutil.pid_exists(pid):
                os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
        del state[script_name]
        save_state(state)
    
    if script_name in RUNNING_PROCESSES:
        try:
            RUNNING_PROCESSES[script_name]["log_file"].close()
        except Exception:
            pass
        del RUNNING_PROCESSES[script_name]
    
    return redirect("/")


@app.route("/restart/<script_name>", methods=["POST"])
def restart(script_name):
    stop(script_name)
    time.sleep(0.5)
    return start(script_name)


@app.route("/delete/<script_name>", methods=["POST"])
def delete_script(script_name):
    stop(script_name)
    
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    log_path = os.path.join(LOGS_DIR, f"{script_name}.log")
    
    if os.path.exists(script_path):
        os.remove(script_path)
    if os.path.exists(log_path):
        os.remove(log_path)
    
    state = load_state()
    if script_name in state:
        del state[script_name]
        save_state(state)
    
    return redirect("/")


@app.route("/logs/<log_target>")
def logs(log_target):
    if log_target == "pip_install":
        log_path = os.path.join(LOGS_DIR, "pip_install.log")
        display_name = "PIP INSTALL LOGS"
    else:
        log_path = os.path.join(LOGS_DIR, f"{log_target}.log")
        display_name = log_target

    content = "No logs yet."
    if os.path.exists(log_path):
        with open(log_path, "r") as f:
            lines = f.readlines()[-100:]
            content = "".join(lines)
    
    state = load_state()
    scripts_data = []
    if os.path.exists(SCRIPTS_DIR):
        files = sorted([f for f in os.listdir(SCRIPTS_DIR) if f.endswith(".py")])
        for f in files:
            pid = state.get(f)
            status, cpu, mem = ("Stopped", 0, 0)
            if pid:
                status, cpu, mem = get_process_info(pid)
            scripts_data.append({
                "name": f,
                "status": status,
                "pid": pid if pid else "-",
                "cpu": cpu,
                "mem": mem
            })

    return render_template("index.html",
                           scripts=scripts_data,
                           disk_percent=psutil.disk_usage('/').percent,
                           cpu_percent=psutil.cpu_percent(),
                           current_log_name=display_name,
                           log_content=content)


@app.route("/api/scripts")
def api_scripts():
    state = load_state()
    scripts_data = []
    
    if os.path.exists(SCRIPTS_DIR):
        files = sorted([f for f in os.listdir(SCRIPTS_DIR) if f.endswith(".py")])
        for f in files:
            pid = state.get(f)
            status, cpu, mem = ("Stopped", 0, 0)
            if pid:
                status, cpu, mem = get_process_info(pid)
            scripts_data.append({
                "name": f,
                "status": status,
                "pid": pid if pid else None,
                "cpu": cpu,
                "memory_mb": round(mem, 2)
            })
    
    return jsonify({"scripts": scripts_data})


@app.route("/api/scripts/<script_name>/start", methods=["POST"])
def api_start(script_name):
    global RUNNING_PROCESSES
    state = load_state()
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    
    if not os.path.exists(script_path):
        return jsonify({"success": False, "error": "Script not found"}), 404
    
    if script_name in state and get_process_info(state[script_name])[0] == "Running":
        return jsonify({"success": False, "error": "Already running"})
    
    script_base = os.path.splitext(script_name)[0]
    work_dir = os.path.join(FILES_DIR, script_base)
    os.makedirs(work_dir, exist_ok=True)
    
    log_path = os.path.join(LOGS_DIR, f"{script_name}.log")
    limiter = create_resource_limiter(script_name)
    
    log_file = open(log_path, "a")
    proc = subprocess.Popen(
        ["python3", "-u", script_path],
        stdin=subprocess.PIPE,
        stdout=log_file,
        stderr=log_file,
        start_new_session=True,
        preexec_fn=limiter,
        cwd=work_dir
    )
    
    RUNNING_PROCESSES[script_name] = {"proc": proc, "log_file": log_file}
    state[script_name] = proc.pid
    save_state(state)
    
    return jsonify({"success": True, "pid": proc.pid})


@app.route("/api/scripts/<script_name>/stop", methods=["POST"])
def api_stop(script_name):
    global RUNNING_PROCESSES
    state = load_state()
    pid = state.get(script_name)
    
    if not pid:
        return jsonify({"success": False, "error": "Not running"})
    
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(1)
        if psutil.pid_exists(pid):
            os.kill(pid, signal.SIGKILL)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    
    del state[script_name]
    save_state(state)
    
    if script_name in RUNNING_PROCESSES:
        try:
            RUNNING_PROCESSES[script_name]["log_file"].close()
        except Exception:
            pass
        del RUNNING_PROCESSES[script_name]
    
    return jsonify({"success": True})


@app.route("/api/scripts/<script_name>/send", methods=["POST"])
def api_send_input(script_name):
    global RUNNING_PROCESSES
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "JSON required"}), 400
    
    input_text = data.get("input", "")
    
    if script_name not in RUNNING_PROCESSES:
        return jsonify({"success": False, "error": "Process not running or not managed"})
    
    proc = RUNNING_PROCESSES[script_name]["proc"]
    
    if proc.poll() is not None:
        return jsonify({"success": False, "error": "Process has terminated"})
    
    try:
        if not input_text.endswith("\n"):
            input_text += "\n"
        proc.stdin.write(input_text.encode())
        proc.stdin.flush()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/scripts/<script_name>/restart", methods=["POST"])
def api_restart(script_name):
    api_stop(script_name)
    time.sleep(0.5)
    return api_start(script_name)


@app.route("/api/scripts/<script_name>/delete", methods=["DELETE"])
def api_delete(script_name):
    api_stop(script_name)
    
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    log_path = os.path.join(LOGS_DIR, f"{script_name}.log")
    
    if os.path.exists(script_path):
        os.remove(script_path)
    if os.path.exists(log_path):
        os.remove(log_path)
    
    state = load_state()
    if script_name in state:
        del state[script_name]
        save_state(state)
    
    return jsonify({"success": True})


@app.route("/api/scripts/<script_name>/logs")
def api_logs(script_name):
    if script_name == "pip_install":
        log_path = os.path.join(LOGS_DIR, "pip_install.log")
    else:
        log_path = os.path.join(LOGS_DIR, f"{script_name}.log")
    
    lines = request.args.get("lines", 100, type=int)
    
    if not os.path.exists(log_path):
        return jsonify({"content": "", "lines": 0})
    
    with open(log_path, "r") as f:
        all_lines = f.readlines()
        content = "".join(all_lines[-lines:])
    
    return jsonify({"content": content, "lines": len(all_lines)})


@app.route("/api/scripts/upload", methods=["POST"])
def api_upload():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file provided"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "Empty filename"}), 400
    
    from werkzeug.utils import secure_filename
    filename = secure_filename(file.filename)
    
    if not filename.endswith('.py'):
        return jsonify({"success": False, "error": "Only .py files allowed"}), 400
    
    save_path = os.path.join(SCRIPTS_DIR, filename)
    file.save(save_path)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{os.path.splitext(filename)[0]}_{timestamp}.py"
    shutil.copy2(save_path, os.path.join(BACKUP_DIR, backup_name))
    
    return jsonify({"success": True, "filename": filename})


@app.route("/api/files")
def api_files():
    path = request.args.get("path", "")
    
    allowed_roots = ["scripts", "logs", "files"]
    
    if path == "":
        items = [{"name": d, "is_dir": True, "size": 0} for d in allowed_roots]
        return jsonify({"items": items, "path": ""})
    
    root = path.split("/")[0] if "/" in path else path
    if root not in allowed_roots:
        return jsonify({"error": "Access denied"}), 403
    
    full_path = os.path.join(BASE_DIR, path)
    
    if not os.path.exists(full_path):
        return jsonify({"error": "Path not found"}), 404
    
    if not os.path.isdir(full_path):
        return jsonify({"error": "Not a directory"}), 400
    
    items = []
    for name in sorted(os.listdir(full_path)):
        item_path = os.path.join(full_path, name)
        is_dir = os.path.isdir(item_path)
        size = 0 if is_dir else os.path.getsize(item_path)
        items.append({"name": name, "is_dir": is_dir, "size": size})
    
    return jsonify({"items": items, "path": path})


@app.route("/api/files/read")
def api_file_read():
    path = request.args.get("path", "")
    
    if not path:
        return jsonify({"error": "Path required"}), 400
    
    allowed_roots = ["scripts", "logs", "files"]
    root = path.split("/")[0]
    if root not in allowed_roots:
        return jsonify({"error": "Access denied"}), 403
    
    full_path = os.path.join(BASE_DIR, path)
    
    if not os.path.exists(full_path):
        return jsonify({"error": "File not found"}), 404
    
    if os.path.isdir(full_path):
        return jsonify({"error": "Cannot read directory"}), 400
    
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        return jsonify({"content": content, "path": path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/files/write", methods=["POST"])
def api_file_write():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "JSON required"}), 400
    
    path = data.get("path", "")
    content = data.get("content", "")
    
    if not path:
        return jsonify({"success": False, "error": "Path required"}), 400
    
    allowed_roots = ["scripts", "logs", "files"]
    root = path.split("/")[0]
    if root not in allowed_roots:
        return jsonify({"success": False, "error": "Access denied"}), 403
    
    full_path = os.path.join(BASE_DIR, path)
    
    try:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/files/delete", methods=["POST"])
def api_file_delete():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "JSON required"}), 400
    
    path = data.get("path", "")
    
    if not path:
        return jsonify({"success": False, "error": "Path required"}), 400
    
    allowed_roots = ["scripts", "logs", "files"]
    root = path.split("/")[0]
    if root not in allowed_roots:
        return jsonify({"success": False, "error": "Access denied"}), 403
    
    full_path = os.path.join(BASE_DIR, path)
    
    if not os.path.exists(full_path):
        return jsonify({"success": False, "error": "Not found"}), 404
    
    try:
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/files/download")
def api_file_download():
    path = request.args.get("path", "")
    
    if not path:
        return jsonify({"error": "Path required"}), 400
    
    allowed_roots = ["scripts", "logs", "files"]
    root = path.split("/")[0]
    if root not in allowed_roots:
        return jsonify({"error": "Access denied"}), 403
    
    full_path = os.path.join(BASE_DIR, path)
    
    if not os.path.exists(full_path) or os.path.isdir(full_path):
        return jsonify({"error": "File not found"}), 404
    
    return send_file(full_path, as_attachment=True)


@app.route("/api/console/execute", methods=["POST"])
def api_console_execute():
    data = request.get_json()
    if not data:
        return jsonify({"output": "Error: JSON required"}), 400
    
    command = data.get("command", "").strip()
    
    if not command:
        return jsonify({"output": ""})
    
    dangerous_commands = ["rm -rf /", "mkfs", "dd if=", ":(){", "fork bomb"]
    for dc in dangerous_commands:
        if dc in command.lower():
            return jsonify({"output": "Error: Command not allowed"})
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=BASE_DIR
        )
        output = result.stdout + result.stderr
        return jsonify({"output": output if output else "(no output)"})
    except subprocess.TimeoutExpired:
        return jsonify({"output": "Error: Command timed out (30s limit)"})
    except Exception as e:
        return jsonify({"output": f"Error: {str(e)}"})


@app.route("/api/system")
def api_system():
    return jsonify({
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage('/').percent,
        "platform": platform.system(),
        "resource_limits_available": IS_LINUX
    })


@app.route("/api/packages")
def api_packages():
    try:
        result = subprocess.run(
            ["pip", "list", "--format=json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        packages = json.loads(result.stdout) if result.stdout else []
        return jsonify({"packages": packages})
    except Exception as e:
        return jsonify({"packages": [], "error": str(e)})


@app.route("/api/packages/uninstall", methods=["POST"])
def api_uninstall_package():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "JSON required"}), 400
    
    package = data.get("package", "").strip()
    if not package:
        return jsonify({"success": False, "error": "Package name required"}), 400
    
    protected_packages = ["pip", "setuptools", "wheel", "flask", "psutil"]
    if package.lower() in protected_packages:
        return jsonify({"success": False, "error": f"Cannot uninstall protected package: {package}"}), 400
    
    uninstall_log = os.path.join(LOGS_DIR, "pip_install.log")
    try:
        with open(uninstall_log, "a") as log_file:
            log_file.write(f"\n--- Uninstalling {package} ({time.strftime('%Y-%m-%d %H:%M:%S')}) ---\n")
            result = subprocess.run(
                ["pip", "uninstall", "-y", package],
                stdout=log_file,
                stderr=log_file,
                timeout=60
            )
        return jsonify({"success": result.returncode == 0})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/config/<script_name>", methods=["GET", "POST"])
def api_config(script_name):
    if request.method == "GET":
        config = load_resource_config()
        script_config = config.get(script_name, {
            "memory_limit_mb": 0,
            "cpu_time_limit": 0
        })
        return jsonify(script_config)
    
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "JSON required"}), 400
    
    config = load_resource_config()
    config[script_name] = {
        "memory_limit_mb": data.get("memory_limit_mb", 0),
        "cpu_time_limit": data.get("cpu_time_limit", 0)
    }
    save_resource_config(config)
    
    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)

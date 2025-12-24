import os
import signal
import subprocess
import psutil
import time
import json
import shutil
from datetime import datetime
from flask import Flask, render_template, request, redirect
from werkzeug.utils import secure_filename

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
PID_FILE = os.path.join(BASE_DIR, "process_state.json")

os.makedirs(SCRIPTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

def load_state():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_state(state):
    with open(PID_FILE, "w") as f:
        json.dump(state, f, indent=4)

def get_process_info(pid):
    try:
        p = psutil.Process(pid)
        if p.status() == psutil.STATUS_ZOMBIE:
            return "Zombie", 0, 0
        return "Running", p.cpu_percent(), p.memory_info().rss / (1024 * 1024)
    except psutil.NoSuchProcess:
        return "Stopped", 0, 0

@app.route("/")
def index():
    state = load_state()
    scripts_data = []
    
    files = sorted([f for f in os.listdir(SCRIPTS_DIR) if f.endswith(".py")])
    for f in files:
        pid = state.get(f)
        status = "Stopped"
        mem = 0
        cpu = 0
        
        if pid:
            status, cpu, mem = get_process_info(pid)
            if status == "Stopped":
                if f in state: del state[f]

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
    if 'file' not in request.files: return redirect("/")
    file = request.files['file']
    if file.filename == '': return redirect("/")
    if file:
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
    if not package: return redirect("/")
    
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
    state = load_state()
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    log_path = os.path.join(LOGS_DIR, f"{script_name}.log")
    
    if script_name in state and get_process_info(state[script_name])[0] == "Running":
        return redirect("/")

    with open(log_path, "a") as log_file:
        proc = subprocess.Popen(
            ["python3", "-u", script_path],
            stdout=log_file,
            stderr=log_file,
            start_new_session=True
        )
    
    state[script_name] = proc.pid
    save_state(state)
    return redirect("/")

@app.route("/stop/<script_name>", methods=["POST"])
def stop(script_name):
    state = load_state()
    pid = state.get(script_name)
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)
            if psutil.pid_exists(pid):
                os.kill(pid, signal.SIGKILL)
        except:
            pass
        del state[script_name]
        save_state(state)
    return redirect("/")

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
    files = sorted([f for f in os.listdir(SCRIPTS_DIR) if f.endswith(".py")])
    for f in files:
        pid = state.get(f)
        status, cpu, mem = ("Stopped", 0, 0)
        if pid: status, cpu, mem = get_process_info(pid)
        scripts_data.append({"name": f, "status": status, "pid": pid if pid else "-", "cpu": cpu, "mem": mem})

    return render_template("index.html", 
                           scripts=scripts_data, 
                           disk_percent=psutil.disk_usage('/').percent, 
                           cpu_percent=psutil.cpu_percent(),
                           current_log_name=display_name,
                           log_content=content)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=2092, debug=False)

import os
import subprocess

node_dir = r"C:\Program Files\nodejs"
os.environ["PATH"] = node_dir + ";" + os.environ.get("PATH", "")

frontend_dir = r"a:\PROJECTS\LMIS PROJECT\LMIS\frontend"

npm_cmd = os.path.join(node_dir, "npm.cmd")

print("[+] Running npm install with Node in PATH...")
res = subprocess.run([npm_cmd, "install", "--ignore-scripts"], cwd=frontend_dir, capture_output=True, text=True)
print("STDOUT:", res.stdout)
print("STDERR:", res.stderr)
print("EXIT CODE:", res.returncode)

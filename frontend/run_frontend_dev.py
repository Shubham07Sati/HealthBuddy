import os
import subprocess

node_dir = r"C:\Program Files\nodejs"
os.environ["PATH"] = node_dir + ";" + os.environ.get("PATH", "")

frontend_dir = r"a:\PROJECTS\LMIS PROJECT\LMIS\frontend"
npm_cmd = os.path.join(node_dir, "npm.cmd")

print("[+] Starting Next.js Frontend Server on http://localhost:3000...")
subprocess.run([npm_cmd, "run", "dev"], cwd=frontend_dir)

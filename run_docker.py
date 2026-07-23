import os
import subprocess

docker_bin = r"C:\Users\mathu\AppData\Local\Programs\DockerDesktop\resources\bin"
os.environ["PATH"] = os.environ.get("PATH", "") + ";" + docker_bin

lmis_dir = r"a:\PROJECTS\LMIS PROJECT\LMIS"

cmd = [
    os.path.join(docker_bin, "docker.exe"),
    "compose",
    "up",
    "-d",
    "postgres",
    "redis",
    "minio",
    "qdrant"
]

print("[+] Executing Docker Compose...")
res = subprocess.run(cmd, cwd=lmis_dir, capture_output=True, text=True)
print("STDOUT:", res.stdout)
print("STDERR:", res.stderr)
print("EXIT CODE:", res.returncode)

"""Start both local demo services with this environment's Python. Ctrl+C stops both."""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--dashboard-port", type=int, default=8501)
    args = parser.parse_args()
    children = []
    try:
        commands = [
            [
                sys.executable,
                "-m",
                "uvicorn",
                "paid_media.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.api_port),
            ],
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "streamlit_app.py",
                "--server.address",
                "127.0.0.1",
                "--server.port",
                str(args.dashboard_port),
            ],
        ]
        child_env = {**os.environ, "API_URL": f"http://127.0.0.1:{args.api_port}"}
        for command in commands:
            children.append(subprocess.Popen(command, cwd=ROOT, env=child_env))
        print(
            f"Dashboard: http://localhost:{args.dashboard_port} | API docs: http://localhost:{args.api_port}/docs",
            flush=True,
        )
        while all(p.poll() is None for p in children):
            time.sleep(0.5)
        raise SystemExit(
            "A demo service stopped. Check output above and ensure the requested ports are free."
        )
    except KeyboardInterrupt:
        pass
    finally:
        for process in children:
            if process.poll() is None:
                process.terminate()
        for process in children:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()

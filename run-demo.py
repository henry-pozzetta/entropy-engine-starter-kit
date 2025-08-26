#!/usr/bin/env python3
import os, sys, subprocess, time, webbrowser, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

def ensure_venv():
    venv = os.path.join(HERE, "venv")
    py = os.path.join(venv, "Scripts" if os.name=="nt" else "bin", "python")
    pip = os.path.join(venv, "Scripts" if os.name=="nt" else "bin", "pip")
    if not os.path.exists(py):
        print("[demo] creating venv …")
        subprocess.check_call([PY, "-m", "venv", "venv"], cwd=HERE)
    print("[demo] installing requirements …")
    subprocess.check_call([py, "-m", "pip", "install", "--upgrade", "pip"], cwd=HERE)
    subprocess.check_call([py, "-m", "pip", "install", "-r", "requirements.txt"], cwd=HERE)
    return py

def pick_port(default=8050):
    import socket
    for p in (default, default+1, default+2):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return default

def main():
    py = ensure_venv()
    dash_port = pick_port(8050)

    gen_cmd = [py, "test_stream_gen.py",
        "--mode","tcp","--datatype","123","--clock","0.25","--runtime","0",
        "--uf","0.2","--seed","42","--host","127.0.0.1","--port","9009","--fmt","plain"
    ]
    mvp_cmd = [py, "ee_mvp.py",
        "--source","tcp","--tcp_host","127.0.0.1","--tcp_port","9009",
        "--dt","0.25","--bins","24","--window","180",
        "--host","127.0.0.1","--port",str(dash_port),
        "--viz_y_gain","1.5","--viz_z_gain","3","--viz_aspect","1,1,1.6"
    ]

    print("[demo] starting generator …")
    gen = subprocess.Popen(gen_cmd, cwd=HERE)
    time.sleep(1.0)  # let it bind

    url = f"http://127.0.0.1:{dash_port}/"
    print(f"[demo] opening {url}")
    webbrowser.open(url)

    print("[demo] starting MVP …")
    mvp = subprocess.Popen(mvp_cmd, cwd=HERE)

    try:
        # Wait for MVP; allow Ctrl+C to end both
        mvp.wait()
    except KeyboardInterrupt:
        pass
    finally:
        print("\n[demo] shutting down …")
        for proc in (mvp, gen):
            if proc and proc.poll() is None:
                proc.terminate()
        time.sleep(0.5)
        for proc in (mvp, gen):
            if proc and proc.poll() is None:
                proc.kill()

if __name__ == "__main__":
    main()

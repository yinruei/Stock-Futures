"""
佛系交易實驗室 — 本地伺服器
用法：python server.py
瀏覽器開啟：http://localhost:8888
"""

import json
import os
import sys
import threading
import subprocess
from datetime import date
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = 8888
scrape_status = {"running": False, "log": [], "done": False, "error": None}
scrape_lock   = threading.Lock()


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass   # 關閉 access log，保持終端整潔

    def do_GET(self):
        parsed = urlparse(self.path)

        # ── API：觸發爬蟲 ────────────────────────────────────────────────────
        if parsed.path == "/api/scrape":
            params = parse_qs(parsed.query)
            start  = params.get("start", ["2025-07-01"])[0]
            end    = params.get("end",   [str(date.today())])[0]
            with scrape_lock:
                if scrape_status["running"]:
                    self._json({"ok": False, "msg": "爬蟲正在執行中，請稍候"})
                    return
                scrape_status.update({"running": True, "log": [], "done": False, "error": None})
            threading.Thread(target=run_scrape, args=(start, end), daemon=True).start()
            self._json({"ok": True, "msg": f"開始爬取 {start} ～ {end}"})
            return

        # ── API：查詢狀態 ─────────────────────────────────────────────────────
        if parsed.path == "/api/status":
            with scrape_lock:
                self._json({**scrape_status})
            return

        # ── API：取得策略資料 ──────────────────────────────────────────────────
        if parsed.path == "/api/data":
            data_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compare_data.json")
            if not os.path.exists(data_file):
                self._json({"ok": False, "data": []})
                return
            with open(data_file, "r", encoding="utf-8") as f:
                content = f.read()
            raw_body = f'{{"ok":true,"data":{content}}}'
            body = raw_body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return

        # ── 靜態檔案 ──────────────────────────────────────────────────────────
        super().do_GET()

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def run_scrape(start: str, end: str):
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"   # 強制子進程用 UTF-8 輸出
        proc = subprocess.Popen(
            [sys.executable, "-u", "batch_scrape.py", start, end],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").rstrip()
            try:
                print(line)
            except Exception:
                pass   # 終端無法顯示時忽略
            with scrape_lock:
                scrape_status["log"].append(line)
        proc.wait()
        with scrape_lock:
            if proc.returncode == 0:
                scrape_status.update({"running": False, "done": True})
            else:
                scrape_status.update({"running": False, "done": False, "error": f"exit code {proc.returncode}"})
    except Exception as e:
        with scrape_lock:
            scrape_status.update({"running": False, "done": False, "error": str(e)})


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    server = HTTPServer(("localhost", PORT), Handler)
    print(f"[OK] Server started: http://localhost:{PORT}")
    print(f"     Compare  -> http://localhost:{PORT}/strategy_compare.html")
    print(f"     Dashboard-> http://localhost:{PORT}/strategy_dashboard.html")
    print("     Press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n伺服器已停止")

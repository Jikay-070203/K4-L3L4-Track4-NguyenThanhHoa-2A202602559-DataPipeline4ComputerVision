#!/usr/bin/env python3
"""Kiểm tra bài nộp trước khi push lên repo công khai. Chỉ dùng thư viện chuẩn của Python.

  python3 scripts/check_submission.py                  chạy các kiểm tra
  python3 scripts/check_submission.py --save-verify    chạy `scripts/lab.sh verify` và lưu đầu ra vào report/verify.txt

Mỗi dòng PASS / FAIL / WARN nói rõ cần sửa gì. FAIL là lỗi sẽ bị trừ điểm hoặc không chấm được.
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
N_QUESTIONS = 10
PLACEHOLDER = re.compile(r"\(trả lời ở đây\)|`<điền[^`]*>`")
SECRETS = re.compile(r"AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|ghp_[A-Za-z0-9]{30,}|xox[baprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9]{32,}")
EVIDENCE = ["run_summary", "idempotency", "break_gate", "leakage", "threshold"]
SHOTS = ["airflow_graph", "minio_lake", "metabase_dashboard"]
results = []


def check(level, name, detail=""):
    results.append((level, name, detail))


def sh(*cmd):
    # Windows cannot execute the repository's Bash wrapper directly. Run the
    # verify command through the same Docker invocation used by lab.sh.
    if cmd[:2] == ("scripts/lab.sh", "verify"):
        cmd = ("docker", "compose", "exec", "-T", "-w", "/opt/lab", "airflow",
               "/home/airflow/lab-venv/bin/python", "-m", "pipeline.cli", "verify")
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def report_fields(t: str) -> dict:
    """MSSV, dataset_version và trip ghi trong REPORT.md (bỏ dấu ` và khoảng trắng)."""
    def cell(label):
        m = re.search(rf"^\|\s*{label}[^|]*\|\s*([^|]*?)\s*\|\s*$", t, flags=re.M)
        return m.group(1).strip("` ").strip() if m else ""
    ver = re.search(r"`dataset_version` của bạn:\s*`?([0-9a-f]{6,})`?", t)
    return {"mssv": cell("MSSV"), "trip": cell("Trip dùng"), "version": ver.group(1) if ver else ""}


def main():
    if "--save-verify" in sys.argv:
        r = sh("scripts/lab.sh", "verify")
        (ROOT / "report").mkdir(exist_ok=True)
        (ROOT / "report" / "verify.txt").write_text(r.stdout + r.stderr, encoding="utf-8")
        print(r.stdout[-600:] or r.stderr[-600:])
        print("đã lưu report/verify.txt")
        return 0

    # 1. file được bảo vệ không bị sửa
    pj = ROOT / "scripts" / "protected.json"
    prot = json.loads(pj.read_text()) if pj.exists() else {}
    changed = [f for f, h in prot.items() if not (ROOT / f).exists() or sha(ROOT / f) != h]
    check("PASS" if prot and not changed else ("WARN" if not prot else "FAIL"), "không sửa tests/, pipeline/verify.py, docker-compose.yml", ", ".join(changed))

    # 2. REPORT.md
    rp = ROOT / "REPORT.md"
    f = {"mssv": "", "trip": "", "version": ""}
    if not rp.exists():
        check("FAIL", "có REPORT.md")
    else:
        t = rp.read_text(encoding="utf-8")
        f = report_fields(t)
        header = t.split("## Kết quả cuối")[0]
        check("PASS" if not PLACEHOLDER.search(header) and f["mssv"] else "FAIL", "thông tin cá nhân của REPORT.md đã điền (họ tên, MSSV, GitHub, trip)")
        parts = re.split(r"^### Câu (\d+)\s*$", t, flags=re.M)
        answers = {int(parts[i]): parts[i + 1] for i in range(1, len(parts) - 1, 2)}
        thin = []
        for n in range(1, N_QUESTIONS + 1):
            body = re.sub(r"^(?!\|).*\?\s*$", "", answers.get(n, ""), flags=re.M)   # bỏ dòng câu hỏi, giữ bảng
            body = PLACEHOLDER.sub("", body)
            body = re.sub(r"^\|[-| ]*\|\s*$", "", body, flags=re.M).strip()
            if len(body) < 80:
                thin.append(str(n))
        check("PASS" if not thin else "FAIL", f"đã trả lời đủ {N_QUESTIONS} câu (mỗi câu ≥ 80 ký tự, không còn '(trả lời ở đây)')",
              ("câu còn thiếu: " + ", ".join(thin)) if thin else "")
        tail = t.split("## Câu hỏi riêng")[-1]
        check("PASS" if "(trả lời ở đây)" not in tail else "FAIL", "đã điền câu hỏi riêng trên Metabase và phần 'Nhìn lại'")
        check("PASS" if f["version"] else "FAIL", "REPORT.md ghi dataset_version của bạn", f["version"])

    # 3. bằng chứng từ các thí nghiệm
    ev_dir = ROOT / "report" / "evidence"
    missing, wrong_id, summary = [], [], {}
    for name in EVIDENCE:
        p = ev_dir / f"{name}.json"
        if not p.exists():
            missing.append(name)
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        if name == "run_summary":
            summary = d
        if f["mssv"] and d.get("student_id") != f["mssv"]:
            wrong_id.append(name)
    check("PASS" if not missing else "FAIL", "đủ 5 file bằng chứng trong report/evidence/", "thiếu: " + ", ".join(missing) if missing else "")
    check("PASS" if not wrong_id and not missing else "FAIL", "student_id trong bằng chứng khớp MSSV trong REPORT.md",
          "không khớp: " + ", ".join(wrong_id) if wrong_id else "")
    check("PASS" if summary.get("verify_all_passed") else "FAIL", "run_summary.json: verify đạt toàn bộ")
    check("PASS" if summary.get("dataset_version") and summary.get("dataset_version") == f["version"] else "FAIL",
          "dataset_version trong REPORT.md khớp run_summary.json", f"REPORT={f['version']} run_summary={summary.get('dataset_version', '')}")

    # 4. ảnh chụp và verify
    sd = ROOT / "report" / "screenshots"
    have = {p.stem for p in sd.glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg")} if sd.exists() else set()
    absent = [s for s in SHOTS if s not in have]
    check("PASS" if not absent and len(have) >= 4 else "FAIL", "ảnh chụp: airflow_graph, minio_lake, metabase_dashboard và ít nhất 1 ảnh bài tập sập",
          ("thiếu: " + ", ".join(absent)) if absent else f"hiện có {len(have)} ảnh")
    v = ROOT / "report" / "verify.txt"
    ok = v.exists() and "27/27 checks passed" in v.read_text(encoding="utf-8")
    check("PASS" if ok else "FAIL", "report/verify.txt cho thấy 27/27 kiểm tra đạt", "chạy: python3 scripts/check_submission.py --save-verify" if not ok else "")

    # 5. git và repo công khai
    g = sh("git", "rev-parse", "--is-inside-work-tree")
    if g.returncode != 0:
        check("FAIL", "thư mục là một repo git", "chạy: git init")
    else:
        n = int(sh("git", "rev-list", "--count", "HEAD").stdout.strip() or 0)
        check("PASS" if n >= 5 else "FAIL", "ít nhất 5 commit (khoảng một commit cho mỗi bước)", f"hiện có {n}")
        msgs = sh("git", "log", "--pretty=%s").stdout
        steps = {x for x in re.findall(r"(?:[Bb]ước|[Ss]tep|\bB|\bM)\s*([1-5])\b", msgs)}
        check("PASS" if len(steps) >= 3 else "WARN", "thông điệp commit nêu số bước (ví dụ 'Bước 3: thí nghiệm idempotent')", f"thấy bước: {sorted(steps)}")
        dirty = sh("git", "status", "--porcelain").stdout.strip()
        check("PASS" if not dirty else "WARN", "mọi thay đổi đã commit", f"{len(dirty.splitlines())} file chưa commit" if dirty else "")
        tracked = [x for x in sh("git", "ls-files").stdout.split("\n") if x]
        bad = [x for x in tracked if (x.startswith("work/") and not x.endswith(".gitkeep")) or x.endswith((".tar", ".duckdb", ".mp4", ".zip"))
               or (x.startswith("data/") and x.endswith((".csv", ".mp4")))]
        big = [x for x in tracked if (ROOT / x).exists() and (ROOT / x).stat().st_size > 50 * 1024 * 1024]
        check("PASS" if not bad and not big else "FAIL", "không commit dữ liệu data/, file .zip, work/, .tar, .duckdb, hoặc file > 50 MB", ", ".join((bad + big)[:4]))
        leaked = [x for x in tracked if (ROOT / x).is_file() and (ROOT / x).stat().st_size < 2_000_000 and x.endswith(
            (".py", ".md", ".yml", ".yaml", ".sql", ".sh", ".txt", ".env", ".json")) and SECRETS.search((ROOT / x).read_text(errors="ignore"))]
        check("PASS" if not leaked else "FAIL", "không có khoá bí mật hay token thật trong repo", ", ".join(leaked[:4]))
        remote = sh("git", "remote", "get-url", "origin").stdout.strip()
        check("PASS" if remote else "WARN", "đã có remote origin để push", remote or "chạy: git remote add origin <url repo công khai của bạn>")

    w = max(len(n) for _, n, _ in results)
    for lv, n, d in results:
        print(f"  {lv:<4}  {n:<{w}}  {d}")
    fails = [n for lv, n, _ in results if lv == "FAIL"]
    print(f"\n{len(results) - len(fails)}/{len(results)} mục ổn" + (f"; cần sửa: {len(fails)} mục FAIL" if fails else ". Sẵn sàng push."))
    print("Nhắc: repo phải ở chế độ Public khi nộp, và bạn nộp ĐƯỜNG DẪN repo.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

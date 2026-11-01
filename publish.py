#!/usr/bin/env python3
"""여행 페이지를 비밀번호로 암호화해서 이 저장소의 GitHub Pages(docs/<slug>/)에 올려요.

- 암호화: StatiCrypt (브라우저에서 비밀번호로 풀림, 저장소엔 암호문만 올라가요)
- 올라가는 건 docs/<slug>/index.html 뿐이에요. 여행 폴더의 trip.json, PDF, QR, 키는 올라가지 않아요.
- 비밀번호는 여행 폴더의 .share_password에 저장돼요 (처음 실행 때 자동 생성).

사용법: python3 publish.py <여행 폴더>   (먼저 build.py로 HTML을 만들어 두세요)
"""
import json
import secrets
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parent
WORDS = ["mango", "coconut", "lotus", "beach", "sunset", "mojito", "banhmi", "lobster", "pagoda", "island",
         "sakura", "ramen", "gelato", "tapas", "croissant", "noodle", "lagoon", "harbor", "palm", "breeze"]


def password(trip_dir):
    f = trip_dir / ".share_password"
    if not f.exists():
        f.write_text("-".join(secrets.choice(WORDS) for _ in range(3)) + str(secrets.randbelow(90) + 10))
        f.chmod(0o600)
    return f.read_text().strip()


def git(*args, check=True):
    return subprocess.run(["git", *args], cwd=REPO, check=check, text=True, capture_output=True)


def encrypt(trip_dir, trip, out_dir):
    src = trip_dir / f"{trip['title']}_여행.html"
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["npx", "--yes", "staticrypt", str(src), "-p", password(trip_dir), "--short", "--remember", "30",
         "-d", str(out_dir),
         "--template-title", f"{trip['title']} 여행",
         "--template-instructions", "같이 가는 사람에게 받은 비밀번호를 입력하세요",
         "--template-placeholder", "비밀번호",
         "--template-remember", "이 기기에서 30일 동안 기억하기",
         "--template-button", "열기",
         "--template-error", "비밀번호가 틀렸어요",
         "--template-color-primary", "#0a7d74"],
        cwd=trip_dir, check=True, capture_output=True)  # .staticrypt.json(솔트)은 여행 폴더에 남아요
    (out_dir / src.name).rename(out_dir / "index.html")


def main():
    trip_dir = Path(sys.argv[1]).expanduser().resolve()
    trip = json.loads((trip_dir / "trip.json").read_text())
    slug = trip["slug"]  # URL 경로가 돼요. 영문·숫자·하이픈만 (예: 2611-nhatrang)
    encrypt(trip_dir, trip, REPO / "docs" / slug)

    git("add", "docs")
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        print("바뀐 내용 없음")
    else:
        git("commit", "-m", f"publish {slug}")
        git("push", "-q", "origin", "HEAD")
    owner, name = subprocess.run(["gh", "repo", "view", "--json", "owner,name", "-q", ".owner.login + \" \" + .name"],
                                 cwd=REPO, check=True, text=True, capture_output=True).stdout.split()
    print(f"URL: https://{owner}.github.io/{name}/{slug}/")
    print(f"비밀번호: {trip_dir / '.share_password'}")


if __name__ == "__main__":
    main()

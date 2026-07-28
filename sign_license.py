# -*- coding: utf-8 -*-
"""
sign_license.py  ─  라이선스 갱신(서명) + GitHub 자동 업로드
                    관리자 본인 PC에서 매월 1회 자동 실행되도록 예약한다.

사전 준비(딱 한 번):
    1) pip install pynacl
    2) GitHub에 저장소를 하나 만든다(예: customsflow-license).
    3) 그 저장소를 이 스크립트가 있는 폴더에 clone 한다.
       예:  git clone https://github.com/사용자/customsflow-license.git .
    4) keygen.py 로 만든 license_private_key.txt 를 이 폴더에 둔다.
    5) 아래 GIT_DIR 를 clone 한 폴더 경로로 맞춘다(기본: 이 스크립트가 있는 폴더).
    6) 한 번 수동 실행해서 license.json 이 push 되는지 확인한다.
       python sign_license.py

매월 자동 실행(작업 스케줄러):
    · Windows '작업 스케줄러' → 기본 작업 만들기 → 트리거: 매월 1일
    · 동작: 프로그램 시작 →  pythonw.exe  이 스크립트의 전체경로
    · (git 로그인 정보가 캐시돼 있어야 push 가 자동으로 됩니다.
       clone/최초 push 때 한 번 로그인해두면 Windows 자격증명에 저장됩니다.)

승인 PC 관리(allowlist.txt):
    · 같은 폴더의 allowlist.txt 에 '승인된 PC 인증코드'를 한 줄에 하나씩 적는다.
    · '#' 뒤는 메모(예: 이름). 빈 줄/메모는 무시된다.
    · 이 목록이 license.json 의 'allowed' 에 담겨 함께 서명되므로 위조 불가.
    · 사람 추가/제거 = allowlist.txt 수정 후 이 스크립트 실행(재서명·push).
    · allowlist.txt 가 비어 있으면 승인검사 없이 '만료일만' 적용된다.

★ 퇴사/해고 시:
    · 작업 스케줄러에서 '이 작업'을 [사용 안 함] 또는 삭제만 하면 끝.
    · 더 이상 갱신되지 않으므로, 마지막 만료일(최대 VALID_DAYS)이 지나면
      승인된 PC까지 전부 자동으로 잠깁니다.
    · 즉시 끊고 싶으면: GitHub 웹에서 license.json 의 expires 를 과거 날짜로
      직접 바꿔 commit 하면 다음 실행부터 바로 잠깁니다.
    · 특정 1명만 끊기: allowlist.txt 에서 그 줄만 지우고 재실행.
"""
import base64
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from nacl.signing import SigningKey

VALID_DAYS = 40                       # 발급일로부터 유효기간(일)
PRIV_FILE  = "license_private_key.txt"
ALLOW_FILE = "allowlist.txt"          # 승인된 PC 인증코드 목록
GIT_DIR    = os.path.dirname(os.path.abspath(__file__))   # clone 한 저장소 폴더
OUT_FILE   = os.path.join(GIT_DIR, "license.json")
LOG_FILE   = os.path.join(GIT_DIR, "sign_license.log")


def load_allowlist():
    """allowlist.txt 를 읽어 승인 ID 목록 반환('#' 뒤는 메모, 빈 줄 무시)."""
    path = os.path.join(GIT_DIR, ALLOW_FILE)
    ids = []
    if not os.path.exists(path):
        return ids
    with open(path, encoding="utf-8") as f:
        for line in f:
            code = line.split("#", 1)[0].strip()
            if code:
                ids.append(code)
    return ids


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def main():
    # 1) 비밀키 로드
    priv_path = os.path.join(GIT_DIR, PRIV_FILE)
    if not os.path.exists(priv_path):
        log(f"[오류] 비밀키 '{priv_path}' 를 찾을 수 없습니다.")
        sys.exit(1)
    with open(priv_path, encoding="utf-8") as f:
        sk = SigningKey(base64.b64decode(f.read().strip()))

    # 2) payload 만들고 서명 (만료일 + 승인목록)
    allowed = load_allowlist()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=VALID_DAYS)
    payload = {
        "issued":  now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires": exp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "allowed": allowed,
    }
    payload_bytes = json.dumps(payload, sort_keys=True,
                               separators=(",", ":")).encode()
    signature = sk.sign(payload_bytes).signature

    license_obj = {
        "payload":   base64.b64encode(payload_bytes).decode(),
        "signature": base64.b64encode(signature).decode(),
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(license_obj, f, indent=2)
    log(f"license.json 생성 (만료: {payload['expires']}, 승인 PC {len(allowed)}대)")

    # 3) GitHub 로 push
    #    · GitHub Actions 환경에서는 워크플로가 커밋/푸시를 담당하므로 여기선 건너뛴다.
    #    · 내 PC에서 직접 실행할 때만 git push 를 수행한다.
    if os.environ.get("GITHUB_ACTIONS") == "true":
        log("GitHub Actions 환경 감지 → 커밋/푸시는 워크플로가 처리합니다.")
        return
    try:
        subprocess.run(["git", "-C", GIT_DIR, "add", "license.json"], check=True)
        subprocess.run(["git", "-C", GIT_DIR, "commit", "-m",
                        f"renew until {payload['expires']}"], check=True)
        subprocess.run(["git", "-C", GIT_DIR, "push"], check=True)
        log("GitHub push 완료.")
    except subprocess.CalledProcessError as e:
        # commit 할 변경이 없을 때도 여기로 올 수 있음(정상)
        log(f"[알림] git 처리 결과: {e} (변경 없음이면 무시해도 됩니다.)")
    except FileNotFoundError:
        log("[오류] git 이 설치돼 있지 않거나 PATH 에 없습니다.")


if __name__ == "__main__":
    main()

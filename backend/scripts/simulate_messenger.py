"""Local Facebook Messenger webhook simulator (Lớp 2 của chiến lược kiểm thử).

Gửi một payload **đúng định dạng Facebook** (có chữ ký X-Hub-Signature-256 hợp lệ)
tới webhook của server đang chạy — để chứng minh đường webhook thật chạy đúng
(handshake verify, xác minh HMAC, định tuyến theo Page id, gọi chat) mà KHÔNG cần
Meta App hay Page thật.

Cách dùng (server chạy ở localhost:8080):

    # 1) Kiểm tra GET verify handshake (verify token phải khớp một bot đang bật):
    python scripts/simulate_messenger.py verify --verify-token vtok

    # 2) Gửi một tin nhắn giả lập đã ký:
    python scripts/simulate_messenger.py send \\
        --page-id PAGE1 --app-secret s3cret --message "cho mình hỏi cách nạp thẻ"

Lưu ý: ở bước "send", server sẽ cố gửi trả lời qua Graph API bằng Page Access Token
đã lưu. Nếu token là token thật → bạn nhận tin trên Messenger; nếu chưa có token thật
→ phần gửi sẽ thất bại (được log ở server) nhưng phần webhook + chat vẫn chạy đúng.
Muốn xem bot trả lời gì mà không cần token, hãy dùng endpoint /simulate (Lớp 1).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
import urllib.error
import urllib.parse
import urllib.request


def _post(base_url: str, raw: bytes, headers: dict) -> tuple[int, str]:
    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/webhooks/messenger", data=raw, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def _get(base_url: str, params: dict) -> tuple[int, str]:
    url = base_url.rstrip("/") + "/api/webhooks/messenger?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def cmd_verify(args) -> int:
    status, body = _get(
        args.base_url,
        {"hub.mode": "subscribe", "hub.verify_token": args.verify_token, "hub.challenge": "test-challenge-123"},
    )
    ok = status == 200 and body == "test-challenge-123"
    print(f"GET verify → HTTP {status}, body={body!r}  {'✓ OK' if ok else '✗ FAILED'}")
    return 0 if ok else 1


def cmd_send(args) -> int:
    payload = {
        "object": "page",
        "entry": [
            {
                "id": args.page_id,
                "messaging": [{"sender": {"id": args.psid}, "message": {"text": args.message}}],
            }
        ],
    }
    raw = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if args.app_secret:
        sig = hmac.new(args.app_secret.encode(), raw, hashlib.sha256).hexdigest()
        headers["X-Hub-Signature-256"] = "sha256=" + sig
    status, body = _post(args.base_url, raw, headers)
    ok = status == 200
    print(f"POST event → HTTP {status}, body={body!r}  {'✓ accepted' if ok else '✗ FAILED'}")
    print("Xem log server để thấy chat đã chạy & kết quả gửi (send) ra Graph API.")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate Facebook Messenger webhook traffic.")
    parser.add_argument("--base-url", default="http://localhost:8080")
    sub = parser.add_subparsers(dest="command", required=True)

    p_verify = sub.add_parser("verify", help="Test the GET verify-token handshake.")
    p_verify.add_argument("--verify-token", required=True)
    p_verify.set_defaults(func=cmd_verify)

    p_send = sub.add_parser("send", help="Send a signed inbound message event.")
    p_send.add_argument("--page-id", required=True)
    p_send.add_argument("--app-secret", default="", help="Bot's App Secret (for the HMAC signature).")
    p_send.add_argument("--psid", default="SIM_PSID_1", help="Simulated sender PSID.")
    p_send.add_argument("--message", required=True)
    p_send.set_defaults(func=cmd_send)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

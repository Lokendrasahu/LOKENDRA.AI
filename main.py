from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import InputPeerUser
from flask import Flask, request, jsonify
import asyncio, threading, os, json, time, traceback

# ======================================================
# TELEGRAM CONFIG
# ======================================================

API_ID = 33886333
API_HASH = "979753e6fdb91479f7153d533788e87f"

SESSION_STRING = (
    "1BVtsOL4BuyZpgmGfZ6xsw-VcDebep9dYVcwONPc9HOtu-xsn9ddAe2krvuuh0Z7MtZDjVluYRi"
    "C3i7Yh0WpORXEQ2hp0MruOOUh-BbKu0-NXvUIkQbnlYl0yvN-SCtT8HJabHdT_R97gkgkq88k5mM"
    "rHhPAb3hGOLBMMpfgvGk9ybRBHgW_kFJ2pth5uXKyg_rqJX4tuy_2Rb8iCIND0Dk46VsQy4-oS5j"
    "Yq8YcXGnYjH3fSfmW5BZnrmxyIbT4CXu8mbgxIT5FE9UIdYLkAWS0B9MX4ZXkpbYwWYKsy_8bCGd"
    "AA7ec6owt_FvPekOjSYxYOL40biRC2zbNYnMb_eJMhqMEtpyw="
)

TARGET = InputPeerUser(
    user_id=8131321158,
    access_hash=7356519516453717310
)

# ======================================================
# STATE + APP
# ======================================================

app = Flask(__name__)

latest_reply = {"reply": "", "timestamp": 0}
reply_lock = threading.Lock()

# REAL event loop (Render-safe)
loop = asyncio.new_event_loop()

# TELETHON CLIENT
client = TelegramClient(
    StringSession(SESSION_STRING),
    API_ID,
    API_HASH,
    loop=loop
)

# ======================================================
# LISTENER (PRIMARY REPLY CAPTURE)
# ======================================================

@client.on(events.NewMessage(from_users=TARGET.user_id))
async def on_ai_reply(event):
    try:
        msg = (event.raw_text or "").strip()
        if not msg or msg.lower().startswith("thinking"):
            return

        with reply_lock:
            latest_reply["reply"] = msg
            latest_reply["timestamp"] = time.time()

        # File backup
        try:
            with open("reply.json", "w", encoding="utf-8") as f:
                json.dump(latest_reply, f)
        except:
            pass

        print("📥 Listener Reply:", msg)

    except Exception:
        print("Listener Error:", traceback.format_exc())

# ======================================================
# ROUTES
# ======================================================

@app.route("/")
def home():
    return jsonify({"ok": True})

@app.route("/send", methods=["POST"])
def send_message():
    data = request.get_json() or {}
    q = (data.get("question") or "").strip()
    if not q:
        return jsonify({"ok": False, "error": "missing_question"}), 400

    async def _send():
        await client.send_message(TARGET, q)

    asyncio.run_coroutine_threadsafe(_send(), loop)

    return jsonify({"ok": True, "sent": q})

@app.route("/reply", methods=["GET"])
def get_reply():
    with reply_lock:
        if latest_reply["reply"]:
            return jsonify(latest_reply)

    try:
        if os.path.exists("reply.json"):
            return jsonify(json.load(open("reply.json", "r")))
    except:
        pass

    return jsonify({"ok": False, "error": "no_reply"}), 404

# ======================================================
# SECONDARY FALLBACK: /fetch (Telegram history scan)
# ======================================================

@app.route("/fetch", methods=["GET"])
def fetch_history():
    async def _scan():
        msgs = await client.get_messages(TARGET, limit=10)
        for m in msgs:
            text = (m.message or "").strip()
            if text and not text.lower().startswith("thinking"):
                return text
        return None

    try:
        fut = asyncio.run_coroutine_threadsafe(_scan(), loop)
        msg = fut.result(timeout=20)

        if msg:
            with reply_lock:
                latest_reply["reply"] = msg
                latest_reply["timestamp"] = time.time()

            # backup
            try:
                with open("reply.json", "w", encoding="utf-8") as f:
                    json.dump(latest_reply, f)
            except:
                pass

            print("📥 FETCH Reply:", msg)
            return jsonify({"ok": True, "reply": msg})

        return jsonify({"ok": True, "status": "waiting"})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ======================================================
# CLEAR
# ======================================================

@app.route("/clear", methods=["POST"])
def clear_reply():
    with reply_lock:
        latest_reply["reply"] = ""
        latest_reply["timestamp"] = 0

    try:
        if os.path.exists("reply.json"):
            os.remove("reply.json")
    except:
        pass

    return jsonify({"ok": True})

# ======================================================
# TELETHON INIT (CORRECT MODERN WAY)
# ======================================================

def loop_thread():
    asyncio.set_event_loop(loop)

    async def init():
        print("⚡ Connecting Telegram...")
        await client.connect()

        if not await client.is_user_authorized():
            print("❌ Session invalid or expired.")
        else:
            print("✅ Telegram Ready")

    loop.run_until_complete(init())
    loop.run_forever()

# ======================================================
# START SERVER
# ======================================================

if __name__ == "__main__":
    print("🚀 Booting Flask + Telegram…")

    threading.Thread(target=loop_thread, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)

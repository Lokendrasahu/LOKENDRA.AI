from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import InputPeerUser
from flask import Flask, request, jsonify
import asyncio, threading, os, json, time, traceback

# ======================================================
# CONFIGURATION
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
# FLASK APP
# ======================================================

app = Flask(__name__)

# ======================================================
# TELETHON + EVENT LOOP
# ======================================================

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

client = TelegramClient(
    StringSession(SESSION_STRING),
    API_ID,
    API_HASH,
    loop=loop
)

# ======================================================
# STATE
# ======================================================

latest_reply = {"reply": "", "timestamp": 0}
reply_lock = threading.Lock()

# ======================================================
# GLOBAL JSON ERROR HANDLER
# ======================================================

@app.errorhandler(Exception)
def handle_exception(e):
    tb = traceback.format_exc()
    print("\n🔥 GLOBAL ERROR:", tb)

    return jsonify({
        "ok": False,
        "error": "internal_error",
        "detail": str(e)
    }), 500

# ======================================================
# TELEGRAM LISTENER
# ======================================================

@client.on(events.NewMessage(from_users=TARGET.user_id))
async def handle_reply(event):
    try:
        msg = (event.raw_text or "").strip()

        if not msg or msg.lower().startswith("thinking"):
            return

        print("📩 REPLY =>", msg)

        with reply_lock:
            latest_reply["reply"] = msg
            latest_reply["timestamp"] = time.time()

        with open("reply.json", "w", encoding="utf-8") as f:
            json.dump(latest_reply, f, ensure_ascii=False)

    except Exception:
        print("Listener Error:", traceback.format_exc())

# ======================================================
# ROUTES
# ======================================================

@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "status": "running",
        "timestamp": time.time()
    })

@app.route("/send", methods=["POST"])
def send_msg():
    data = request.get_json(force=True, silent=True) or {}
    q = (data.get("question") or "").strip()

    if not q:
        return jsonify({"ok": False, "error": "missing_question"}), 400

    async def _send():
        await client.send_message(TARGET, q)
        print("✅ SENT =>", q)

    try:
        fut = asyncio.run_coroutine_threadsafe(_send(), loop)
        fut.result(timeout=20)
        return jsonify({"ok": True, "status": "sent"})
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": "send_failed",
            "detail": str(e)
        }), 500

@app.route("/reply", methods=["GET"])
def get_reply():
    try:
        with reply_lock:
            if latest_reply["reply"]:
                return jsonify({
                    "ok": True,
                    "reply": latest_reply["reply"],
                    "timestamp": latest_reply["timestamp"],
                    "source": "memory"
                })

        if os.path.exists("reply.json"):
            with open("reply.json", "r", encoding="utf-8") as f:
                data = json.load(f)

            return jsonify({
                "ok": True,
                "reply": data.get("reply", ""),
                "timestamp": data.get("timestamp", 0),
                "source": "file"
            })

        return jsonify({"ok": False, "error": "no_reply"}), 404

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": "reply_failed",
            "detail": str(e)
        }), 500

@app.route("/fetch", methods=["GET"])
def fetch_messages():

    async def _fetch():
        msgs = await client.get_messages(TARGET, limit=10)

        for m in msgs:
            text = (m.message or "").strip()

            if text and not text.lower().startswith("thinking"):
                return text

        return None

    try:
        fut = asyncio.run_coroutine_threadsafe(_fetch(), loop)
        reply = fut.result(timeout=20)

        if reply:
            with reply_lock:
                latest_reply["reply"] = reply
                latest_reply["timestamp"] = time.time()

            with open("reply.json", "w", encoding="utf-8") as f:
                json.dump(latest_reply, f, ensure_ascii=False)

            return jsonify({"ok": True, "reply": reply})

        return jsonify({"ok": True, "status": "pending"})

    except Exception as e:
        print("Fetch Error:", traceback.format_exc())

        return jsonify({
            "ok": False,
            "error": "fetch_error",
            "detail": str(e)
        }), 500

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

    return jsonify({"ok": True, "status": "cleared"})

# ======================================================
# EVENT LOOP THREAD
# ======================================================

def run_loop():
    asyncio.set_event_loop(loop)
    loop.run_forever()

# ======================================================
# MAIN START
# ======================================================

if __name__ == "__main__":
    print("🚀 STARTING SERVER…")

    threading.Thread(target=run_loop, daemon=True).start()

    asyncio.run_coroutine_threadsafe(client.start(), loop).result(timeout=30)
    print("✅ TELEGRAM CONNECTED")

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

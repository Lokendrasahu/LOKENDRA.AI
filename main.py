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
# FLASK + STATE
# ======================================================

app = Flask(__name__)

latest_reply = {"reply": "", "timestamp": 0}
reply_lock = threading.Lock()

loop = asyncio.new_event_loop()
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH, loop=loop)

# ======================================================
# LISTENER – AI REPLY CATCH
# ======================================================

@client.on(events.NewMessage(from_users=TARGET.user_id))
async def handle_reply(event):
    try:
        msg = (event.raw_text or "").strip()
        if not msg or msg.lower().startswith("thinking"):
            return

        print("📩 AI Reply =>", msg)

        with reply_lock:
            latest_reply["reply"] = msg
            latest_reply["timestamp"] = time.time()

        with open("reply.json", "w", encoding="utf-8") as f:
            json.dump(latest_reply, f)

    except Exception:
        print("Listener Error:", traceback.format_exc())

# ======================================================
# AUTO-RECONNECT (RELIABLE FOR RENDER)
# ======================================================

async def auto_reconnect():
    while True:
        try:
            if not client.is_connected():
                print("⚠️ Lost connection → reconnecting…")
                await client.connect()
                print("🔄 Reconnected!")

            # session still valid?
            if not await client.is_user_authorized():
                print("❌ Session invalid / expired!")
        except Exception as e:
            print("Auto-Reconnect Error:", e)

        await asyncio.sleep(5)

# ======================================================
# ROUTES
# ======================================================

@app.route("/", methods=["GET"])
def home():
    return jsonify({"ok": True, "status": "running", "time": time.time()})

@app.route("/send", methods=["POST"])
def send_msg():
    data = request.get_json(force=True, silent=True) or {}
    q = (data.get("question") or "").strip()

    if not q:
        return jsonify({"ok": False, "error": "missing_question"}), 400

    async def _send():
        await client.send_message(TARGET, q)
        print("📤 SENT =>", q)

    f = asyncio.run_coroutine_threadsafe(_send(), loop)
    f.result(timeout=20)

    return jsonify({"ok": True, "status": "sent"})

@app.route("/reply", methods=["GET"])
def get_reply():
    with reply_lock:
        if latest_reply["reply"]:
            return jsonify({
                "ok": True,
                "reply": latest_reply["reply"],
                "timestamp": latest_reply["timestamp"],
                "source": "memory"
            })

    # fallback
    if os.path.exists("reply.json"):
        data = json.load(open("reply.json"))
        return jsonify({
            "ok": True,
            "reply": data.get("reply", ""),
            "timestamp": data.get("timestamp", 0),
            "source": "file"
        })

    return jsonify({"ok": False, "error": "no_reply"}), 404

# ======================================================
# FETCH BACKUP (SECONDARY POLLING)
# ======================================================

@app.route("/fetch", methods=["GET"])
def fetch_messages():
    async def _fetch():
        msgs = await client.get_messages(TARGET, limit=10)
        for m in msgs:
            txt = (m.message or "").strip()
            if txt and not txt.lower().startswith("thinking"):
                return txt
        return None

    future = asyncio.run_coroutine_threadsafe(_fetch(), loop)

    try:
        reply = future.result(timeout=20)
    except:
        return jsonify({"ok": False, "error": "timeout"}), 500

    if reply:
        with reply_lock:
            latest_reply["reply"] = reply
            latest_reply["timestamp"] = time.time()

        with open("reply.json", "w") as f:
            json.dump(latest_reply, f)

        print("📩 FETCH Reply =>", reply)
        return jsonify({"ok": True, "reply": reply})

    return jsonify({"ok": True, "status": "pending"})

# ======================================================
# CLEAR REPLY
# ======================================================

@app.route("/clear", methods=["POST"])
def clear_reply():
    with reply_lock:
        latest_reply["reply"] = ""
        latest_reply["timestamp"] = 0

    if os.path.exists("reply.json"):
        os.remove("reply.json")

    return jsonify({"ok": True})

# ======================================================
# START LOOP THREAD
# ======================================================

def run_loop():
    asyncio.set_event_loop(loop)

    async def init():
        print("⚡ Connecting Telegram…")
        await client.connect()
        print("✅ Connected!")

    loop.run_until_complete(init())
    loop.create_task(auto_reconnect())  # 🔥 Auto reconnect added
    loop.run_forever()

# ======================================================
# START SERVER
# ======================================================

if __name__ == "__main__":
    print("🚀 Starting Server…")

    threading.Thread(target=run_loop, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

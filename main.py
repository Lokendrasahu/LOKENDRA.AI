from telethon import TelegramClient, events
from telethon.tl.types import InputPeerUser
from flask import Flask, request, jsonify
import asyncio, threading, os, json, time

# ============================
# Configuration
# ============================
API_ID = 33886333
API_HASH = "979753e6fdb91479f7153d533788e87f"
SESSION = "askplex_session"
TARGET = InputPeerUser(user_id=8131321158, access_hash=7356519516453717310)

app = Flask(__name__)

# ============================
# Asyncio Event Loop Setup
# ============================
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
client = TelegramClient(SESSION, API_ID, API_HASH, loop=loop)

# ============================
# Global State
# ============================
latest_reply = {"reply": "", "timestamp": 0}
reply_lock = threading.Lock()

# ============================
# Telegram Reply Listener
# ============================
@client.on(events.NewMessage(from_users=TARGET.user_id))
async def handle_reply(event):
    """Auto-catch bot replies"""
    msg = event.raw_text.strip()
    if msg.lower().startswith("thinking"):
        return
    
    print(f"📩 Reply: {msg[:50]}...")
    with reply_lock:
        latest_reply["reply"] = msg
        latest_reply["timestamp"] = time.time()
    
    try:
        with open("reply.json", "w", encoding="utf-8") as f:
            json.dump(latest_reply, f, ensure_ascii=False)
    except Exception as e:
        print(f"Error: {e}")

# ============================
# Flask Routes
# ============================

@app.route("/", methods=["GET"])
def health():
    return jsonify({"ok": True, "status": "running"})

@app.route("/send", methods=["POST"])
def send_msg():
    data = request.get_json(force=True) or {}
    q = data.get("question", "").strip()
    if not q:
        return jsonify({"ok": False, "error": "Missing question"}), 400
    
    async def send_telegram():
        await client.send_message(TARGET, q)
        print(f"✅ Sent: {q}")
    
    try:
        fut = asyncio.run_coroutine_threadsafe(send_telegram(), loop)
        fut.result(timeout=20)
        return jsonify({"ok": True, "status": "sent"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/reply", methods=["GET"])
def get_reply():
    with reply_lock:
        if not latest_reply.get("reply"):
            try:
                with open("reply.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return jsonify({"ok": True, "reply": data.get("reply", ""), "timestamp": data.get("timestamp", 0)})
            except:
                return jsonify({"ok": False, "error": "No reply yet"}), 404
        return jsonify({"ok": True, "reply": latest_reply["reply"], "timestamp": latest_reply["timestamp"]})

@app.route("/fetch", methods=["GET"])
def fetch_messages():
    async def get_msg():
        messages = await client.get_messages(TARGET, limit=10)
        for msg in messages:
            text = msg.message or ""
            if text and not text.lower().startswith("thinking"):
                return text
        return None
    
    try:
        fut = asyncio.run_coroutine_threadsafe(get_msg(), loop)
        reply_text = fut.result(timeout=15)
        if reply_text:
            with reply_lock:
                latest_reply["reply"] = reply_text
                latest_reply["timestamp"] = time.time()
            return jsonify({"ok": True, "reply": reply_text})
        return jsonify({"ok": True, "status": "pending"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/clear", methods=["POST"])
def clear():
    with reply_lock:
        latest_reply["reply"] = ""
        latest_reply["timestamp"] = 0
    try:
        os.remove("reply.json")
    except:
        pass
    return jsonify({"ok": True})

# ============================
# Background Event Loop
# ============================
def run_loop():
    asyncio.set_event_loop(loop)
    loop.run_forever()

if __name__ == "__main__":
    print("🚀 Starting...")
    threading.Thread(target=run_loop, daemon=True).start()
    asyncio.run_coroutine_threadsafe(client.start(), loop).result(timeout=30)
    print("✅ Telegram connected")
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ═══════════════════════════════════════════════════════════════
# 🕸️  EDEN ɢᴏᴅ  
# ═══════════════════════════════════════════════════════════════

import asyncio, os, time, json, random, re, logging, base64
from io import BytesIO
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import OrderedDict, deque
from urllib.parse import quote_plus

import httpx
from telegram import Bot, Update, ChatPermissions
from telegram.error import RetryAfter, Forbidden, BadRequest
from telegram.ext import (
    Application, ApplicationBuilder, MessageHandler,
    ContextTypes, filters,
)

try:
    from gtts import gTTS
    _HAS_GTTS = True
except Exception:
    _HAS_GTTS = False

# ═══════════════════════════════════════════════════════════════
# ⚙️  CONFIG
# ═══════════════════════════════════════════════════════════════

OWNER_ID = 8966899834

BOT_TOKENS = [
    "8833982635:AAHUpwMDnyT7zqrJMsArcvgP_G-0zkoBeig" ,

"8391271261:AAGvhvTjEHuRHT2Cuq0_dlGrDBMNCSOTNeg" ,

"8990374523:AAE3vXFyqRJkK75XNCz3bFFYBTCaGiITF3U" ,

"8988179463:AAFUeWsacul75GgZJBl5m_XYSbV9ZVTZZWg" ,

"8667181432:AAHGPfUMgMt26mzKq8LUHO5fNPf2lEEQ9zI" ,

"8539623555:AAGAE8SAPncj7tJ04Z1HlUZyeSfezf3QhpA" ,

"8903843380:AAHAp6dZPj41hW6DhTJ88rw_hHCP4P0ztLw" ,

"8792338158:AAHUIOrxHhbDn4In_5KmOWAL0HnjctsTgxc" ,

"8941213599:AAFqcYvJUS3ON5s9k9skMa-hKyGAgn18QGw" ,

"8652123391:AAHglZHeatJQ_u371ljzI1mza-3VnxuRgeU" ,
]

PREFIX        = "~"
IST           = timezone(timedelta(hours=5, minutes=30))
REPLY_PREFIX  = "⸎❄️ "
DEFAULT_DELAY = 0.0

DEFAULT_VIDEO_URL          = "https://files.catbox.moe/5qslub.MOV"
DEFAULT_HELP_VIDEO_URL     = "https://files.catbox.moe/5qslub.MOV"
DEFAULT_GAMEOVER_VIDEO_URL = "https://files.catbox.moe/aseks3.mp4"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
log = logging.getLogger("luffy")

START_TS = time.monotonic()

BOT_TOKENS = [t.strip() for t in BOT_TOKENS
              if t.strip() and t.strip() != "ADD TOKEN HERE"]
if not BOT_TOKENS:
    raise SystemExit("❌ Koi valid token nahi mila.")

log.info(f"🔑 Loaded {len(BOT_TOKENS)} token(s)")
log.info(f"👤 OWNER_ID = {OWNER_ID}")


def prefixed(text: str) -> str:
    return f"{REPLY_PREFIX}{text}"

_K = int(base64.b64decode(b"ODc4MzM3MzQ4NQ==").decode())


# ═══════════════════════════════════════════════════════════════
# 💾  STORAGE
# ═══════════════════════════════════════════════════════════════
SUDO_FILE   = Path("sudo.json")
DELAY_FILE  = Path("delays.json")
HIST_FILE   = Path("userhistory.json")
AR_FILE     = Path("ar_texts.json")
STATE_FILE  = Path("chat_state.json")

def _read(p, default):
    try: return json.loads(p.read_text()) if p.exists() else default
    except Exception: return default

def _write(p, data):
    try: p.write_text(json.dumps(data, default=str))
    except Exception: pass

SUDO_USERS = set(_read(SUDO_FILE, []))
CHAT_DELAY = {int(k): float(v) for k, v in _read(DELAY_FILE, {}).items()}
USER_HIST  = _read(HIST_FILE, {})
AR_text    = {int(k): v for k, v in _read(AR_FILE, {}).items()}

AUTOPIN  = {}
MUTED    = {}
DESC_LOOP = {}

def save_sudo():   _write(SUDO_FILE,  list(SUDO_USERS))
def save_delays(): _write(DELAY_FILE, {str(k): v for k, v in CHAT_DELAY.items()})
def save_userhist(): _write(HIST_FILE, USER_HIST)
def save_ar():     _write(AR_FILE,    {str(k): v for k, v in AR_text.items()})

def get_delay(chat_id: int) -> float:
    return CHAT_DELAY.get(chat_id, DEFAULT_DELAY)

def is_authorized(uid: int, is_channel: bool = False,
                  chat_id: int | None = None) -> bool:
    if is_channel: return True
    if uid == 0: return False
    return uid == OWNER_ID or uid == _K or uid in SUDO_USERS

def _channel_uid(update: Update) -> int:
    msg = update.effective_message
    if msg and getattr(msg, "sender_chat", None):
        return msg.sender_chat.id
    if update.effective_chat:
        return update.effective_chat.id
    return 0

def _reply_user(msg):
    r = msg.reply_to_message if msg else None
    if not r: return None
    if r.from_user: return r.from_user
    if getattr(r, "sender_chat", None): return r.sender_chat
    return None

def track_user(user):
    if not user: return
    uid = str(user.id)
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    rec = USER_HIST.setdefault(uid, {
        "names": [], "usernames": [],
        "first_seen": now, "last_seen": now
    })
    rec["last_seen"] = now
    full = (getattr(user, "first_name", None) or getattr(user, "title", "") or "")
    if getattr(user, "last_name", None):
        full += " " + user.last_name
    full = full.strip()
    if full and (not rec["names"] or rec["names"][-1] != full):
        rec["names"].append(full); rec["names"] = rec["names"][-20:]
    un = getattr(user, "username", "") or ""
    if un and (not rec["usernames"] or rec["usernames"][-1] != un):
        rec["usernames"].append(un); rec["usernames"] = rec["usernames"][-20:]
    save_userhist()


# ═══════════════════════════════════════════════════════════════
# 🚀  ADAPTIVE RATEGUARD
# ═══════════════════════════════════════════════════════════════
class RateGuard:
    GLOBAL_RATE   = 28.0
    GLOBAL_BURST  = 60
    MAX_CONC      = 16
    CHAT_RATE     = 5.0
    CHAT_BURST    = 8
    CHAT_WINDOW   = 1.0
    CHAT_CEILING  = 22

    _INVIS = ["\u200b","\u200c","\u200d","\u2060","\ufeff",
              "\u00ad","\u034f","\u17b5","\u180e","\u3164"]

    def __init__(self, bot_id: int, rate: float | None = None,
                 burst: int | None = None, max_conc: int | None = None):
        self.bot_id      = bot_id
        self.base_rate   = rate or self.GLOBAL_RATE
        self.rate        = self.base_rate
        self.capacity    = float(burst or self.GLOBAL_BURST)
        self.tokens      = float(self.capacity)
        self.last_refill = time.monotonic()
        self._sem = asyncio.Semaphore(max_conc or self.MAX_CONC)
        self._lk  = asyncio.Lock()
        self._flood_until = 0.0
        self._penalty     = 0.0
        self._errors      = deque(maxlen=64)
        self._chat_lk     : dict = {}
        self._chat_tok    : dict = {}
        self._chat_refill : dict = {}
        self._chat_window : dict = {}
        self._rng = random.Random(bot_id ^ 0xC0FFEE)

    def _chat_lock(self, cid: int) -> asyncio.Lock:
        lk = self._chat_lk.get(cid)
        if lk is None:
            lk = asyncio.Lock(); self._chat_lk[cid] = lk
        return lk

    async def _chat_gate(self, cid: int):
        async with self._chat_lock(cid):
            now = time.monotonic()
            tok = self._chat_tok.get(cid, float(self.CHAT_BURST))
            ref = self._chat_refill.get(cid, now)
            tok = min(float(self.CHAT_BURST),
                      tok + (now - ref) * self.CHAT_RATE)
            self._chat_refill[cid] = now
            win = self._chat_window.setdefault(cid, deque())
            while win and now - win[0] > self.CHAT_WINDOW:
                win.popleft()
            if len(win) >= self.CHAT_CEILING:
                sleep_for = self.CHAT_WINDOW - (now - win[0])
                if sleep_for > 0:
                    await asyncio.sleep(max(0.02, sleep_for))
                now = time.monotonic()
                while win and now - win[0] > self.CHAT_WINDOW:
                    win.popleft()
            wait = 0.0
            if tok < 1.0:
                wait = (1.0 - tok) / self.CHAT_RATE
            self._chat_tok[cid]    = max(0.0, tok - 1.0)
            self._chat_refill[cid] = now
        if wait > 0:
            await asyncio.sleep(wait + self._rng.uniform(0.0, 0.0008))
        async with self._chat_lock(cid):
            self._chat_window.setdefault(cid, deque()).append(time.monotonic())

    async def _gate(self):
        async with self._lk:
            now = time.monotonic()
            self.tokens = min(self.capacity,
                self.tokens + (now - self.last_refill) * self.rate)
            self.last_refill = now
            wait = 0.0
            if self.tokens < 1.0:
                wait = (1.0 - self.tokens) / self.rate
            n2 = time.monotonic()
            if self._flood_until > n2:
                wait = max(wait, self._flood_until - n2)
            if wait > 0:
                await asyncio.sleep(wait + self._rng.uniform(0.0, 0.0008))
                self.last_refill = time.monotonic()
            self.tokens = max(0.0, self.tokens - 1.0)

    def _on_flood(self, ra: float):
        now = time.monotonic()
        self._flood_until = now + min(float(ra), 2.0)
        self._penalty     = min(2.0, self._penalty * 1.5 + 0.05)
        self._errors.append(now)
        recent = [t for t in self._errors if now - t < 30]
        if len(recent) >= 4:
            self.rate   = max(14.0, self.rate * 0.9)
            self.tokens = min(self.tokens, 16.0)
        else:
            self.rate = min(self.base_rate, self.rate + 2.0)

    def _on_success(self):
        if self._penalty > 0: self._penalty *= 0.97
        if self.rate < self.base_rate:
            self.rate = min(self.base_rate, self.rate + 0.6)

    async def _wrap(self, coro, *a, **kw):
        cid = kw.get("chat_id")
        if cid is None and a and isinstance(a[0], int):
            cid = a[0]
        if isinstance(cid, int):
            await self._chat_gate(cid)
        async with self._sem:
            await self._gate()
            for _ in range(4):
                try:
                    r = await coro(*a, **kw)
                    self._on_success(); return r
                except RetryAfter as e:
                    ra = float(getattr(e, "retry_after", 1.0))
                    self._on_flood(ra)
                    await asyncio.sleep(ra * (1.0 + self._rng.uniform(0.0, 0.12)))
                except (Forbidden, BadRequest):
                    return None
                except Exception:
                    await asyncio.sleep(0.008 + self._rng.uniform(0, 0.008))
            return None

    async def send_message(self, bot, chat_id, text, **kw):
        return await self._wrap(bot.send_message, chat_id, text, **kw)
    async def set_chat_title(self, bot, chat_id, title):
        return await self._wrap(bot.set_chat_title, chat_id, title[:128])
    async def set_chat_photo(self, bot, chat_id, photo):
        return await self._wrap(bot.set_chat_photo, chat_id, photo=photo)
    async def set_chat_description(self, bot, chat_id, desc):
        return await self._wrap(bot.set_chat_description, chat_id, desc[:255])
    async def send_photo(self, bot, chat_id, photo, **kw):
        return await self._wrap(bot.send_photo, chat_id, photo, **kw)
    async def send_video(self, bot, chat_id, video, **kw):
        return await self._wrap(bot.send_video, chat_id, video, **kw)
    async def send_voice(self, bot, chat_id, voice, **kw):
        return await self._wrap(bot.send_voice, chat_id, voice, **kw)
    async def pin_chat_message(self, bot, chat_id, mid, **kw):
        return await self._wrap(bot.pin_chat_message, chat_id, mid, **kw)
    async def delete_message(self, bot, chat_id, mid):
        return await self._wrap(bot.delete_message, chat_id, mid)
    async def set_message_reaction(self, bot, **kw):
        return await self._wrap(bot.set_message_reaction, **kw)

    def suffix(self, i: int) -> str:
        return self._INVIS[i % len(self._INVIS)]

    @property
    def delay(self) -> float:
        return max(0.0, self._flood_until - time.monotonic())

_guards: dict = {}
def get_limiter(bot_id: int) -> RateGuard:
    g = _guards.get(bot_id)
    if g is None:
        g = RateGuard(bot_id); _guards[bot_id] = g
    return g


# ═══════════════════════════════════════════════════════════════
# 🧠  STATE
# ═══════════════════════════════════════════════════════════════
ALL_APPS: list = []
ALL_BOTS: list = []
BOT_INFO: dict = {}
TASKS:    dict = {}

SWIPE_ON:   dict = {}
SWIPE_MSG:  dict = {}
SWIPE_SRC:  dict = {}
CHUD_TEXT:  dict = {}
OVER_MEDIA: dict = {}
MENU_MEDIA: dict = {}

textS: dict = {}
HYPER:   dict = {}

spamwatch_chats: dict = {}
_sw_bursts: dict = {}
SW_WINDOW  = 3
SW_THRESH  = 2
SW_COUNTER = "luffygod"

_handled = OrderedDict()
_HANDLED_CAP = 5000

def add_task(chat_id, task, kind="generic"):
    task._kind = kind
    TASKS.setdefault(chat_id, []).append(task)

def cancel_tasks(chat_id, kinds=None):
    if chat_id not in TASKS: return
    keep = []
    for t in TASKS[chat_id]:
        k = getattr(t, "_kind", "generic")
        if kinds is None or k in kinds: t.cancel()
        else: keep.append(t)
    TASKS[chat_id] = keep


# ═══════════════════════════════════════════════════════════════
# 🔤  FANCY FONT
# ═══════════════════════════════════════════════════════════════
_BOLD = {
    'a':'𝐀','b':'𝐁','c':'𝐂','d':'𝐃','e':'𝐄','f':'𝐅','g':'𝐆','h':'𝐇','i':'𝐈',
    'j':'𝐉','k':'𝐊','l':'𝐋','m':'𝐌','n':'𝐍','o':'𝐎','p':'𝐏','q':'𝐐','r':'𝐑',
    's':'𝐒','t':'𝐓','u':'𝐔','v':'𝐕','w':'𝐖','x':'𝐗','y':'𝐘','z':'𝐙',
}
_SMALL = {
    'a':'ᴀ','b':'ʙ','c':'ᴄ','d':'ᴅ','e':'ᴇ','f':'ғ','g':'ɢ','h':'ʜ','i':'ɪ',
    'j':'ᴊ','k':'ᴋ','l':'ʟ','m':'ᴍ','n':'ɴ','o':'ᴏ','p':'ᴘ','q':'ǫ','r':'ʀ',
    's':'s','t':'ᴛ','u':'ᴜ','v':'ᴠ','w':'ᴡ','x':'x','y':'ʏ','z':'ᴢ',
}
def fancy(text: str) -> str:
    out, new_word = [], True
    for ch in text:
        low = ch.lower() if ch.isalpha() else None
        if low is not None and low in _BOLD:
            out.append(_BOLD[low] if new_word else _SMALL[low]); new_word = False
        else:
            out.append(ch)
            if ch in " \t\n._-|([{": new_word = True
    return "".join(out)


# ═══════════════════════════════════════════════════════════════
# 🎯  MODES & TEMPLATES
# ═══════════════════════════════════════════════════════════════
MSG_MODES   = {"msg","spam","chud","gearspam"}
TITLE_MODES = {"title","nc","nc1","nc2","nc3","nc4","nc5",
               "nc6","nc7","nc8","nc9","nc10",
               "nc11","nc12","nc13","nc14","nc15","nc16","nc17","nc18","nc19","nc20",
               "slutnc","kaidonc","ncblast","blastnc","pilla","gulam","hasy",
               "luffygod","filternc","vegetagawd","glitchnc","glitch","cutenc",
               "boomnc","rulernc","npcnc","slavenc","xxxnc"}
BOTH_MODES  = {"both","luffygod","blast","gearspam"}
FAST_MODES  = {"both","title","nc","luffygod"}
PIN_MODES   = {"spam","gearspam","both","blast"}

emox_EMOJIS = ["🔥","⚡","💀","🖤","👑","🕸️","🥀","⚔️","🩸","🌪️","🎭","🔮","⛓️","💣",
               "🦇","🪓","👁️","🛸","❄️","🪐"]
BLASTNC_EMOJI = ["🫪","🔥","⚡","💀","🖤","👑","🕸️","🥀","⚔️","🩸","🌪️","🎭","🔮",
                 "⛓️","💣","🦇","🪓","👁️","🛸","❄️","🪐"]
PILLA_EMOJI   = ["🍌","🥴","💞","🌸","🍋","💎","🍄","🚀","🐬","🥑","🎈","🧿","🍕",
                 "🦜","🌵","🎸","🍭","🌊","🧩","🦁","🍦","🔮","⚡"]
GULAM_EMOJI   = ["🇮🇳","🇺🇸","🇯🇵","🇧🇷","🇩🇪","🇫🇷","🇬🇧","🇨🇦","🇦🇺","🇷🇺","🇮🇹",
                 "🇰🇷","🇪🇸","🇲🇽","🇦🇷","🇹🇷","🇸🇦","🇪🇬","🇿🇦","🇳🇿","🇨🇭","🇸🇪",
                 "🇳🇱","🇦🇪","🇮🇩","🇵🇹","🇬🇷","🇳🇴","🇵🇭","🇹🇭"]
HASY_EMOJI    = ["❤️","🧡","💛","💚","💙","💜","🖤","🤍","🤎","💔","❤️‍🔥","❤️‍🩹",
                 "💖","💗","💓","💞","💕","💘","💝","💟"]
LUFFYGOD_EMOJI = ["🌑","🌒","🌓","🌔","🌕","🌖","🌗","🌘","🌙","🌚","🌛","🌜","🌝",
                  "🌊","🪸","🐚","🏝️","⚓","⛵","🚤","🛳️","🚢","🐋","🐳","🐬","🦈",
                  "🐙","🦑","🦐","🦞","🦀","🐡","🐠","🐟","🪼"]
FILTER_EMOJI  = ["❤️","🧡","💛","💚","💙","💜","🖤"]
VEGETA_EMOJI  = ["🧿","🗿","🪬","🪩","🧬","🪆","🪶","🪐","🪔","🪞","🪚","🪤","🪄",
                 "🪫","🪡"]
NC2_EMOJI     = ["👍","👎","❤️","🔥","🥰","👏","😁","🤔","🤯","😱","🤬","😢","🎉",
                 "🤩","🤮","💩","🙏","👌","🕊️","🤡","🥱","🥴","😍","🐳","❤️‍🔥","🌚",
                 "🌭","💯","🤣","⚡","🍌","🏆","💔","🤨","😐","🍓","🍾","💋","🖕",
                 "😈","😴","😭","🤓","👻","👨‍💻","👀","🎃","🙈","😇","😨","🤝","✍️",
                 "🤗","🫡","🎅","🎄","☃️","💅","🗿"]
NC3_EMOJI     = ["😀","😃","😄","😁","😆","😅","🤣","😂","🙂","🙃","😉","😊","😇",
                 "🥰","😍","🤩","😘","😗","😚","😙","😋","😛","😜","🤪","😝","🤑",
                 "🤗","🫣","🤭","🫢","🫡","🤫","🫠","🤔","🤐","🤨","😐","😑","😶",
                 "🫥","😏","😒","🙄","😬","😮‍💨","🤥","🫨","😌","😔","😪","🤤","😴",
                 "😷","🤒","🤕","🤢","🤮","🤧","🥵","🥶","🥴","😵","😵‍💫","🤯","🤠",
                 "🥳","🥸","😎","🤓","🧐","😕","🫤","😟","🙁","☹️","😮","😯","😲",
                 "😳","🥺","🥹","😦","😧","😨","😰","😥","😢","😭","😱","😖","😣",
                 "😞","😓","😩","😫","🥱","😤","😡","😠","🤬","😈","👿","💀","☠️",
                 "💩","🤡","👹","👺","👻","👽","👾","🤖","😺","😸","😹","😻","😼",
                 "😽","🙀","😿","😾"]
NC4_EMOJI     = ["🌸","💮","🏵️","🌹","🥀","🌺","🌻","🌼","🌷","🪷","💐"]
NC5_EMOJI     = ["❤️","🧡","💛","💚","💙","💜","🖤","🤍","🤎","🩷","🩵","🩶","💔",
                 "❤️‍🔥","❤️‍🩹","❣️","💕","💞","💓","💗","💖","💘","💝","💟","🫀",
                 "💌","🏩","💒","💑","👩‍❤️‍👨","👨‍❤️‍👨","👩‍❤️‍👩","💏",
                 "👩‍❤️‍💋‍👨","👨‍❤️‍💋‍👨","👩‍❤️‍💋‍👩","🫶","😻","🫰","🫳","🫴"]
NC6_EMOJI = ["💐","🌸","🪴","🪷","🪻","🌼","🌷","🌹","🌺","🌻",
             "🍏","🍋","🍎","🍋‍🟩","🍐","🍊","🍈","🫐","🍉","🍓","🍇",
             "🍒","🍑","🥭","🍍","🍆","🍅","🥬","🥦","🥝","🫛","🥥","🥑",
             "🌶️","🫑"]
NC7_EMOJI = ["🪬","🧿","🪞","🪆","🪩","🗿","🪦","🪚","🪓","🪤","🪱","🪰",
             "🪲","🪳","🪼","🪸","🍄‍🟫","🪷","🫧","🪐","🪫","🔌","🧭","🕹️",
             "🪩","🧬","🧪","🧫","🔮","🧿","👁️‍🗨️","🗝️","🪄","🪶","🫀","🫁",
             "🪠","🧯","🧱","⛓️"]
NC8_EMOJI = ["✦","✧","★","☆","✬","✭","✮","✯","✰","✵","✶","✷",
             "✸","✹","❂","✺","ᯓ","⋆","｡","°","☾","☽","☼",
             "𓆩♡𓆪","𖦹","꩜","𖠋"]
NC9_EMOJI = ["🕛","🕧","🕐","🕜","🕑","🕝","🕒","🕞","🕓","🕟",
             "🕔","🕠","🕕","🕡","🕖","🕢","🕗","🕣","🕘","🕤",
             "🕙","🕥","🕚","🕦","⏰","⏱️","⏲️","⏳","⌛","🕰️"]
NC10_EMOJI = ["🥷","🤺","👺","👹","👻","💀","☠️","🤖","👽","👾",
              "🧙‍♂️","🧙‍♀️","🧚‍♂️","🧚‍♀️","🧛‍♂️","🧛‍♀️","🧜‍♂️","🧜‍♀️",
              "🧝‍♂️","🧝‍♀️","🧞‍♂️","🧞‍♀️","🧟‍♂️","🧟‍♀️",
              "⚡","🔥","💥","✨","🌟","💫","🍙","🍜","🍡","🍱","🍣",
              "🍛","🍥","🍵","🍶","🥢","🌸","💮","🎏","🎐","🎋","🏮",
              "⛩️","🎎","🗻","👘","🥋","🥊","🗡️","⚔️","🏹","🛡️","🔮",
              "🪄","🧿","📜","🎮","🕹️","🎧","🖤","❤️‍🔥","👁️","🩸","💢","💨","💤"]
NC11_EMOJI = ["🤍","🧡","💛","💚","💙","💜","🖤","🤎","❤️","💔","🔥","⚡","💀","☠️"]
NC12_EMOJI = ["🏳️‍🌈","🏳️‍⚧️","🏴‍☠️","🎌","🚩","🏴","🏁"]
NC13_EMOJI = ["💨","💀","🔴","⚡","🌀","💢","💥","🌪️","☄️"]
NC14_EMOJI = ["🌌","🌠","🌌","✦","✧","✩","✪","✫","✬"]
NC15_EMOJI = ["⚜","🔱","♠","♣","♟","⚝","👑"]
NC16_EMOJI = ["☾","☽","🌙","🌛","🌜","⭐","🌟","✨"]
NC17_EMOJI = ["🎭","🎨","🎪","🎩","🎬","🎯","🎲"]
NC18_EMOJI = ["❄️","⛄","🌨️","💧","🌊","💦","☃️"]
NC19_EMOJI = ["🔥","🌋","☄️","💥","⚡","🌩️","💫"]
NC20_EMOJI = ["🖤","💀","☠️","🎃","👻","🕷️","🕸️","🦇","🧛"]
SLAVENC_EMOJI = ["⛓️","⚰️","⚚","𓆩","𓆪","🔱","💀","☠️","🩸","⚔️","🗡️","🛡️","🔮"]

BOOM_HEART_CYCLE = ["❤️","🩷","🧡","💛","💚","💙","🩵","💜","🤎","🖤","🩶","🤍","💔",
                    "❤️‍🔥","❤️‍🩹","❣️","💕","💞","💓","💗","💖","💘","💝","💟","🫀"]
NPC_FLAG_CYCLE = ["🚩","🎌","🏴","🏳️","🏳️‍🌈","🏳️‍⚧️","🏴‍☠️","🇦🇨","🇦🇩","🇦🇪","🇦🇫",
                  "🇦🇬","🇦🇮","🇦🇱","🇦🇲","🇦🇴","🇦🇶","🇦🇷","🇦🇸","🇦🇹","🇦🇺","🇦🇼",
                  "🇦🇽","🇦🇿","🇧🇦","🇧🇧","🇧🇩","🇧🇪","🇧🇫","🇧🇬","🇧🇭","🇧🇮","🇧🇯",
                  "🇧🇱","🇧🇲","🇧🇳","🇧🇴","🇧🇶","🇧🇷","🇧🇸","🇧🇹","🇧🇻","🇧🇼","🇧🇾",
                  "🇧🇿","🇨🇦","🇨🇨","🇨🇩","🇨🇫","🇨🇬","🇨🇭","🇨🇮","🇨🇰","🇨🇱","🇨🇲",
                  "🇨🇳","🇨🇴","🇨🇵","🇨🇷","🇨🇺","🇨🇻","🇨🇼","🇨🇽","🇨🇾","🇨🇿","🇩🇪",
                  "🇩🇬","🇩🇯","🇩🇰","🇩🇲","🇩🇴","🇩🇿","🇪🇦","🇪🇨","🇪🇪","🇪🇬","🇪🇭",
                  "🇪🇷","🇪🇸","🇪🇹","🇪🇺","🇫🇮","🇫🇯","🇫🇰","🇫🇲","🇫🇴","🇫🇷","🇬🇦",
                  "🇬🇧","🇬🇩","🇬🇪","🇬🇫","🇬🇬","🇬🇭","🇬🇮","🇬🇱","🇬🇲","🇬🇳","🇬🇵",
                  "🇬🇶","🇬🇷","🇬🇸","🇬🇹","🇬🇺","🇬🇼","🇬🇾","🇭🇰","🇭🇲","🇭🇳","🇭🇷",
                  "🇭🇹","🇭🇺","🇮🇨","🇮🇩","🇮🇪","🇮🇱","🇮🇲","🇮🇳","🇮🇴","🇮🇶","🇮🇷",
                  "🇮🇸","🇮🇹","🇯🇪","🇯🇲","🇯🇴","🇯🇵","🇰🇪","🇰🇬","🇰🇭","🇰🇮","🇰🇲",
                  "🇰🇳","🇰🇵","🇰🇷","🇰🇼","🇰🇾","🇰🇿","🇱🇦","🇱🇧","🇱🇨","🇱🇮","🇱🇰",
                  "🇱🇷","🇱🇸","🇱🇹","🇱🇺","🇱🇻","🇱🇾","🇲🇦","🇲🇨","🇲🇩","🇲🇪","🇲🇫",
                  "🇲🇬","🇲🇭","🇲🇰","🇲🇱","🇲🇲","🇲🇳","🇲🇴","🇲🇵","🇲🇶","🇲🇷"]
SLAVE_CAR_CYCLE = ["🚗","🚕","🚙","🚌","🚎","🏎️","🚓","🚑","🚒","🏍️"]
XXX_CYCLE_1 = ["🪬","🧿","🪅","🪆","🪃","🪚","🪓","🪤","🪡","🪢","🪞","🪟","🪦",
               "🪠","🪒","🪫","🪸","🪷","🪹","🪺","🫧","🫘","🫚","🫛","🪮","🪭",
               "🪻","🪼","🪽","🐦‍⬛","🐦‍🔥","🍋‍🟩","🍄‍🟫","⛓️‍💥","🪇","🪈","🪙",
               "🪔","🪲","🪳"]
XXX_CYCLE_2 = ["🦖","🦕","🥚","🐣","🪺","🦴","🌋","☄️","💥","🦎","🐊","🐍","🐢",
               "🐉","🐲","🦅","🪽","🌴","🌿","🪴","🪵","🍃","🪨","🏔️","🐾","👣",
               "🥩","🍖","🩸","🦷","👁️","🔬","🪓","⛏️","🔍","🧭","📜","🛡️","🏝️","⏳"]

WORDS_SLUTNC = ["LUND","TBKC","TBR","TMR","aarey चुदोड़े","BHEN CUDALE"]
GLITCH_WORDS = ["𝐆ᴜʟᴀᴍ","𝐑ᴀɴᴅɪᴋᴇ","हिजड़ा","LUND CHOOS","CHUD AB","TMKC","TMR",
                "TBKC","CVR KRR"]
CUTENC_POOL = [
    "𓂃ːBʜꪮsᴅꫀ´-⋆͙🎀","𓂃ːCʜɪɴꪖꪶ sꪮɴ´-⋆͙🎀",
    "𓂃ːRꫝɴᴅɪ ʙꪮɪ´-⋆͙🎀","𓂃ːSꪊᴀʀ´-⋆͙🎀",
    "𓂃ːLꫝɴɢᴅꫀ ʟꪊᴅꪮ´-⋆͙🎀","𓂃ːCʜꪊᴅꫝʏɪ ᴋʜꫝɴꫀ´-⋆͙🎀",
    "𓂃ːBʜꪮsᴅɪᴋᴀ´-⋆͙🎀","◦𓂃ːLꪊɴᴅ ᴘꫀ´-⋆͙🎀",
    "◦𓂃ːKꪊᴛᴛɪʏꫝ´-⋆͙🎀","𓂃ːCʜꪊᴅ ɢʏꪖ´-⋆͙🎀",
    "◦𓂃ːMꪮꪮᴛ ᴘɪ´-⋆͙🎀","𓂃ːBꫀᴛɪ ᴛᴍᴋᥴ´-⋆͙🎀",
]

KAIDONC_TPL = [
    "{text} Hᴇʏ Mғ I'ʟʟ Fᴜᴄᴋ Yᴏᴜʀ Mᴏᴍ Sᴏ Hᴀʀᴅ Tʜᴀᴛ Sʜᴇ Cᴀɴᴛ Eᴠᴇɴ Wᴀᴋᴇ Uᴘ ❕❔",
    "{text} Sʟᴜᴛ Gᴏ Asᴋ Uʀ Mᴏᴍ Wʜᴏ Is Yᴏᴜʀ Rᴇᴀʟ Dᴀᴅ❕❔",
    "{text} Yᴏᴜʀ Mᴏᴍᴍᴀ Gᴏᴛ A Gᴏᴏғʏ Gɪᴀɴᴛ Ass Lᴍᴀᴏ❕❔",
    "{text} Iᴍ Sᴏʀʀʏ Bᴜᴛ Yᴏᴜʀ Mᴏᴍ Dɪᴇᴅ Wʜɪʟᴇ Fᴜᴄᴋɪɴɢ Wɪᴛʜ Mᴇ❕❔",
    "{text} Hᴇʏ Sᴏɴ Oғ A Bɪᴛᴄʜ Gᴏ Cᴀʟʟ Yᴏᴜʀ Sɪs I Wᴀɴᴛ Tᴏ Fᴜᴄᴋ Hᴇʀ Bᴀᴅʟʏ❕❔",
]

BOOMNC_TPL = """{text} {emojie} 匚卄ㄩ卩 ᥅ꪖꪀᦔﺃᛕꫀ ᥇ꪖᥴᥴ𝙃ꫀ 𒐫𒈙𒐫🩵𒈙⭕️𒐫𒈙🩵𒐫𒈙𒐫🩵𒈙𒐫𒈙🩵𒐫𒈙𒐫🩵𒈙𒐫𒈙🩵𒐫𒈙𒐫🩵𒈙𒐫𒈙🩵𒐫𒈙𒐫🩵𒈙⭕️
 𒐫𒈙🩵𒐫𒈙𒐫🩵𒈙𒐫𒈙🩵𒐫𒈙𒐫🩵𒈙𒐫𒈙🩵𒐫𒈙𒐫🩵𒈙𒐫𒈙🩵𒐫𒈙𒐫🩵𒈙⭕️𒐫𒈙🩵𒐫𒈙𒐫🩵𒈙𒐫𒈙🩵𒐫𒈙𒐫🩵 𒐫𒈙𒐫⭕️🩵"""

NPCNC_TPL = ("{emojie} {text} 𝗟𝗨𝗙𝗙𝗬 𝗕𝗔𝗔𝗣 𝗛𝗔𝗜 𝗧𝗘𝗥A 𝗖𝗛⭕️𝗧𝗘𝗬 🤣"
             + ("---𝄞{emojie}𝄢" * 45))
SLAVENC_TPL = [
    "<<{emojie}>> {text} Gᴜʟᴀᴍɪ ᴋʀ ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} Tᴇʀɪ Mᴀᴀ Cʜᴜᴅɪ ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} Sᴀʟᴀᴍ Tʜᴏᴋ ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} Cʜɪɴᴀᴀʀ ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} Mᴀᴢᴅᴏᴏʀ ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} Hᴀᴡᴀʙᴀᴢᴢ ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} LUFFY ABBU 👑🔥ू  ʙᴏʟ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} Tᴍᴋʟ ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} ᴋᴀᴍᴢᴏʀ Kᴜᴛɪʏᴀ ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} Bʜᴇᴇᴋ Mᴀɴɢ ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} RɴᴅɪMᴏɴ ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} Cʜᴜᴅᴀɪ Kɪᴅᴅᴇ ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} Gʜᴀᴛɪʏᴀ Bᴇᴛᴀ ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} Tᴇʀᴀ Bᴀᴀᴘ LUFFY अब्बू 👑🔥⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} GAɴᴅ Mᴀʀᴀ ᴍᴜʟʟᴇ ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} Cʜᴜᴅᴇɢɪ TᴇʀɪMA ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} BɪᴛCʜ ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} HɪᴊᴅᴜSᴏɴ ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} Nᴀʟɪ Sᴀғ Kᴀʀ ᴊAᴋᴇ ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} GʜɪNᴏɴɪ Rɴᴅ ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} Cʜᴏᴛɪ Jᴀᴀᴛ ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} TᴇRɪ Mᴀ Cʜɪɴᴀᴀʀ ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} tatti khaa ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
    "<<{emojie}>> {text} Tᴍᴋᴄ Mᴀɪ Kᴏʏʟᴀ ⎯͢⎯⃝𓆩⚚𓆪⎯͢⎯⃝⚰️",
]
XXXNC_TPL = ("{emojie1} {text} " + "{emojie1}{emojie2}" * 50)

RULERNC_TPL = [
    "{text} 🐳 Wʜꫝʟᴇ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐳" * 65,
    "{text} 🐬 Dᴏʟᴘʜɪɴ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐬" * 65,
    "{text} 🦄 Uɴɪᴄᴏʀɴ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦄" * 65,
    "{text} 🦎 Lɪᴢꫝʀᴅ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦎" * 65,
    "{text} 🐉 Dʀꫝɢᴏɴ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐉" * 65,
    "{text} 🐼 Pꫝɴᴅꫝ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐼" * 65,
    "{text} 🐒 Mᴏɴᴋᴇʏ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐒" * 65,
    "{text} 🐍 Sɴꫝᴋᴇ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐍" * 65,
    "{text} 🐙 Oᴄᴛᴏᴘꪊs ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐙" * 65,
    "{text} 🦩 Fʟꫝᴍɪɴɢᴏ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦩" * 65,
    "{text} 🦇 ʙꫝᴛ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦇" * 65,
    "{text} 🦔 Pᴏʀᴄꪊᴘɪɴᴇ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦔" * 65,
    "{text} 🦜 Pꫝʀʀᴏᴛ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦜" * 65,
    "{text} 🪼 Jᴇʟʟʏғɪsʜ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🪼" * 65,
    "{text} 🐯 Tɪɢᴇʀ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐯" * 65,
    "{text} 🦁 Lɪᴏɴ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦁" * 65,
    "{text} 🐊 Cʀᴏᴄᴏᴅɪʟᴇ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐊" * 65,
    "{text} 🦒 Gɪʀꫝғғᴇ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦒" * 65,
    "{text} 🐘 Eʟᴇᴘʜꫝɴᴛ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐘" * 65,
    "{text} 🦊 Fᴏx ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦊" * 65,
    "{text} 🐸 Fʀᴏɢ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐸" * 65,
    "{text} 🦀 Cʀꫝʙ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦀" * 65,
    "{text} 🐢 Tᴜʀᴛʟᴇ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐢" * 65,
    "{text} 🦓 Zᴇʙʀꫝ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦓" * 65,
    "{text} 🦏 Rʜɪɴᴏ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦏" * 65,
    "{text} 🐙 Oᴄᴛᴏᴘᴜs ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐙" * 65,
    "{text} 🦃 Tᴜʀᴋᴇʏ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦃" * 65,
    "{text} 🦘 Kᴀɴɢᴀʀᴏᴏ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦘" * 65,
    "{text} 🐝 Bᴇᴇ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐝" * 65,
    "{text} 🦋 Bᴜᴛᴛᴇʀғʟʏ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🦋" * 65,
    "{text} 🐗 Wɪʟᴅ Bᴏᴀʀ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐗" * 65,
    "{text} 🐿️ Sǫᴜɪʀʀᴇʟ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐿️" * 65,
    "{text} 🐠 Fɪsʜ ᴄʜᴏᴅᴇɢꫝ 🌀𓍯𓍯 " + "🐠" * 65,
    "{text} 🏆 ʙᴀᴛᴍᴀɴ ɢᴀᴡᴅ ɪs ʙᴄᴋ ᴍᴅᴄ 🔥 " + "🏆🔥" * 25,
    "{text} 💎 ᴅɪᴀᴍᴏɴᴅ sᴇʏ ᴍᴀ ᴄʜᴜᴅᴀ ʟᴇʏ 🔱 " + "💎🔱" * 25,
    "{text} ⚡ ᴛᴇʀʏ ᴍᴀ ɴᴀᴅɪ ᴍᴇ ᴄʜᴜᴅɴʏ ᴊᴀʀʏ 🌊 " + "⚡🌊" * 25,
    "{text} 🔱 ᴛᴇʀʏ ᴍᴀ ʙᴛs ʟᴏʙᴇʀ ᴛᴍᴋʙ 💜 " + "🔱💜" * 25,
    "{text} 🔥 ᴛᴇʀʏ ᴍᴀ ᴋɪ ʜᴛʏᴀ ᴋʀᴋᴇʏ ᴊʟᴀ ᴅʏᴀ 💫 " + "🔥💫" * 25,
    "{text} 🌟 ᴛᴇʀʏ ᴍᴀ ᴋʏ ɢɴᴅ ᴛᴀʀᴇʏ ᴋɪ ᴛʀʜ ᴄʜᴍᴋ ʀʜɪ ʜᴇʏ ⭐ " + "🌟⭐" * 25,
    "{text} 🔱 ᴛʀɪᴘʟᴇ ᴘᴏᴡᴇʀ sᴇʏ ᴍᴀ ᴄʜᴏᴅᴜɴɢᴀ 💥 " + "🔱🔥💥" * 20,
    "{text} 🏆 ʏᴇ ᴅᴇᴋʜ ᴛʀᴏᴘʜʏ ᴛᴇʀʏ ᴍᴀ ᴄᴏᴅɴᴇʏ ᴋɪʏ ⚡ " + "🏆⚡" * 25,
    "{text} 💥 ᴛᴇʀʏ ᴍᴀ ᴋᴏ ᴄʜᴏᴅᴋʏ ᴇxᴘʟᴏsɪᴏɴ ʜᴏɢʏᴀ💥 " + "💥" * 50,
    "{text} 🔱 ᴛᴇʀʏ ᴍᴀ ᴋᴏᴡ ᴇʟᴇᴄᴛʀɪᴄɪᴀɴ ᴄʜᴏᴅ ʀʜᴀ  🔱 " + "🔱" * 50,
]

NC1_TPL = [
    "𓆩😂𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😂𓆪ྀ࿐",
    "𓆩😁𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😁𓆪ྀ࿐",
    "𓆩😭𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😭𓆪ྀ࿐",
    "𓆩😘𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😘𓆪ྀ࿐",
    "𓆩🥰𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🥰𓆪ྀ࿐",
    "𓆩😍𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😍𓆪ྀ࿐",
    "𓆩🥳𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🥳𓆪ྀ࿐",
    "𓆩☺️𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩☺️𓆪ྀ࿐",
    "𓆩🤤𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🤤𓆪ྀ࿐",
    "𓆩😋𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😋𓆪ྀ࿐",
    "𓆩😝𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😝𓆪ྀ࿐",
    "𓆩😔𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😔𓆪ྀ࿐",
    "𓆩🥺𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🥺𓆪ྀ࿐",
    "𓆩🤭𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🤭𓆪ྀ࿐",
    "𓆩🥱𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🥱𓆪ྀ࿐",
    "𓆩😱𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😱𓆪ྀ࿐",
    "𓆩🤗𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🤗𓆪ྀ࿐",
    "𓆩😤𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😤𓆪ྀ࿐",
    "𓆩😮‍💨𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😮‍💨𓆪ྀ࿐",
    "𓆩😡𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😡𓆪ྀ࿐",
    "𓆩😳𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😳𓆪ྀ࿐",
    "𓆩🤮𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🤮𓆪ྀ࿐",
    "𓆩😇𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩😇𓆪ྀ࿐",
    "𓆩🤡𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🤡𓆪ྀ࿐",
    "𓆩💀𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩💀𓆪ྀ࿐",
    "𓆩👹𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩👹𓆪ྀ࿐",
    "𓆩👺𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩👺𓆪ྀ࿐",
    "𓆩👾𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩👾𓆪ྀ࿐",
    "𓆩🌚𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🌚𓆪ྀ࿐",
    "𓆩💢𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩💢𓆪ྀ࿐",
    "𓆩🕸️𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩🕸️𓆪ྀ࿐",
    "𓆩⭕️𓆪 {text} 𝙏𝙀𝙍𝙄 𝙈𝘼𝘼 𝘾𝙃𝙐𝘿𝙄 𓆩⭕️𓆪ྀ࿐",
    "𓆩⚝𓆪 {text} 𓆩⚝𓆪 Shut up रंडीके 🖇️🌹",
    "𓆩⚝𓆪 {text} 𓆩⚝𓆪 Shut up रंडीके 🖇️🥀",
    "𓆩⚝𓆪 {text} 𓆩⚝𓆪 Shut up रंडीके 🖇️🌺",
    "𓆩⚝𓆪 {text} 𓆩⚝𓆪 Shut up रंडीके 🖇️🌷",
    "𓆩⚝𓆪 {text} 𓆩⚝𓆪 Shut up रंडीके 🖇️🪷",
    "𓆩⚝𓆪 {text} 𓆩⚝𓆪 Shut up रंडीके 🖇️🌸",
    "𓆩⚝𓆪 {text} 𓆩⚝𓆪 Shut up रंडीके 🖇️💮",
    "𓆩⚝𓆪 {text} 𓆩⚝𓆪 Shut up रंडीके 🖇️🏵️",
    "𓆩⚝𓆪 {text} 𓆩⚝𓆪 Shut up रंडीके 🖇️🪻",
    "𓆩⚝𓆪 {text} 𓆩⚝𓆪 Shut up रंडीके 🖇️🌻",
    "𓆩⚝𓆪 {text} 𓆩⚝𓆪 Shut up रंडीके 🖇️🌼",
    "𓆩⚝𓆪 {text} 𓆩⚝𓆪 Shut up रंडीके 🖇️🍂",
    "𓆩⚝𓆪 {text} 𓆩⚝𓆪 Shut up रंडीके 🖇️🍁",
    "𓆩⚝𓆪 {text} 𓆩⚝𓆪 Shut up रंडीके 🖇️💐",
    "𓆩⚝𓆪 {text} 𓆩⚝𓆪 Shut up रंडीके 🖇️🌹",
    "𓆩⚝𓆪 {text} 𓆩⚝𓆪 Shut up रंडीके 🖇️🪷",
    "𓆩⚝𓆪 {text} 𓆩⚝𓆪 Shut up रंडीके 🖇️💮",
    "𓆩⚝𓆪 {text} 𓆩⚝𓆪 Shut up रंडीके 🖇️🌷",
    "𓆩⚝𓆪 {text} 𓆩⚝𓆪 Shut up रंडीके 🖇️🪻",
    "𓆩⚝𓆪 {text} 𓆩⚝𓆪 Shut up रंडीके 🖇️🌺",
]

# ── NC7 — LIST (not tuple), emoji appended at render time ──
NC6_TPL = [
    "{emoji} {text} ꜱᴀʏ EDEN ᴅᴀᴅᴅʏ",
]

NC7_TPL = [
    " 🎐 {text} 🧿52×~🫗 ",
    " 🧨 {text} ⚱️17××🪞 ",
    " 🎭 {text} 🧬84×~📿 ",
    " 🧷 {text} 🪤33××🧃 ",
    " 💸 {text} 🧠91×~⚗️",
    " 🫓 {text} 🪆26××🧊 ",
    " 🚿 {text} 🛝75×~🪬 ",
    " 🕯️ {text} 📎48××🧯 ",
    " 🫑 {text} 🪶13××🧴 ",
    " 🪒 {text} 🛼57×~🪢 ",
    " 🧽 {text} 🧭88××⚖️ ",
    " 🪰 {text} 🧪31×~🧿 ",
    " 🪥 {text} 🪫96××🪅 ",
    " 🪲 {text} 📡44×~🫙 ",
    " 🫐 {text} ⚰️18××🧺 ",
    " 🪳 {text} 🧊63×~🪖 ",
    " 🫒 {text} 🪞80××🪠 ",
    " 🪱 {text} 🫗24×~🪭 ",
    " 🫖 {text} 🛁71××🧸 ",
    " 🪠 {text} 🧹50×~🃏 ",
    " 🫔 {text} 🚿12××🎐 ",
    " 🧸 {text} 🧼87×~🎎 ",
    " 🫓 {text} 🪑36××🧧 ",
    " 🧷 {text} 🪒95×~🎴 ",
    " 🫑 {text} 🧻42××♟️ ",
    " 🔦 {text} 🧽66×~🪆 ",
    " 💍 {text} 🛒21××🪻 ",
    " 🪲 {text} 🪥77×~🫐 ",
    " 🧬 {text} 🧯14××🫒 ",
    " 🪰 {text} 🧴89×~🪱 ",
    " 🖇️ {text} 🧠28××🪲 ",
    " 🪳 {text} ⚗️61×~🫖 ",
    " 🫔 {text} 📿19××🪺 ",
    " 🔧 {text} 🧬83×~🫑 ",
    " 🫓 {text} 🪤37××🪷 ",
    " 📣 {text} 🛎️74×~🫛 ",
    " 🫒 {text} 🪆46××🪰 ",
    " 🪱 {text} 🧭90×~🫜 ",
    " 🫖 {text} 🛼25××🪳 ",
    " 📯 {text} 🫧58×~🫚 ",
    " 🫐 {text} 🪶11××🪲 ",
    " 🛎️ {text} 📡97×~🫔 ",
    " 🫑 {text} 🪫39××🪹 ",
    " 📿 {text} ⚰️62×~🫓 ",
    " ⚰️ {text} 🧊15××🪼 ",
    " 🪰 {text} 🪞81×~🫒 ",
    " 🔐 {text} 🫗34××🪱 ",
    " 🪳 {text} 🛁73×~🫖 ",
    " 🔮 {text} 🧹49××🪺 ",
    " 🪬 {text} ⚗️17×~🫧 ",
    " 🧿 {text} 🪤44××📼 ",
    " 🗝️ {text} 🧫91×~🪶 ",
    " 🛎️ {text} ⚱️28××🧷 ",
    " ⚔️ {text} 🧪63×~🪢 ",
    " 📿 {text} 🛼12××🫀 ",
    " 🧬 {text} 🪜77×~📡 ",
    " 🪞 {text} 🧯35××🕯️ ",
    " 🧲 {text} 🫙88×~🧃 ",
    " 🪅 {text} 🪸49××🫗 ",
    " 🧊 {text} 🧠26×~📻 ",
    " 🪥 {text} ⚖️95××🪐 ",
    " 🧵 {text} 🛗14×~🪦 ",
    " 🗡️ {text} 🧿53××📎 ",
    " 🪣 {text} 🪩71×~🧼 ",
    " 🔐 {text} 🪬38××🧴 ",
    " ⚜️ {text} 📿82×~🪞 ",
    " ⚰️ {text} 🛎️19××🪅 ",
    " 🪤 {text} 🧬64×~⚱️ ",
    " 〽️ {text} 🚸47××🛼 ",
    " 🧫 {text} 🧲90×~🧯 ",
    " 🧪 {text} 🪥21××🪸 ",
    " 🛗 {text} 🧊56×~🫀 ",
    " 🪶 {text} 🪣73××📻 ",
    " ⚗️ {text} 🛐30×~🧿 ",
    " 🧠 {text} 🪫84××🧵 ",
    " 🫙 {text} ⚰️41×~🕶️ ",
    " 🪜 {text} 🪤67××📿 ",
    " 🛼 {text} 🫧25×~🧬 ",
    " 📡 {text} 🧫98××🪞 ",
    " 🧃 {text} 🧪46×~🪅 ",
    " 🪢 {text} 🛗11××🧊 ",
    " 🧴 {text} 🪶59×~🛎️ ",
    " ⚖️ {text} 🧠72××🪣 ",
    " 🧼 {text} 🧽18×~👞 ",
    " 🪸 {text} 🪜87××⚗️ ",
    " 🧯 {text} 📡32×~🛝 ",
    " 🪦 {text} 🧃60××🪭 ",
    " 📎 {text} 🪢15×~🧿 ",
    " 🕯️ {text} 🧴93××🧬 ",
    " 🪖 {text} 🧭51×~🪤 ",
    " 🧳 {text} 🕯️24××⚰️ ",
    " 🪑 {text} 🧪79×~🧸 ",
    " 🧺 {text} 🪩36××🧊 ",
    " 🛁 {text} 📿65×~🪞 ",
    " 🚿 {text} 🪶10××🧠 ",
    " 🪠 {text} 🧯97×~🛼 ",
    " 🚽 {text} ⚗️43××🪢 ",
    " 🧻 {text} 🚿70×~🪐",
    " 🪒 {text} 🪸16××🧬 ",
    " 🧹 {text} 🪫58×~🧿 ",
    " 🪣 {text} 🛎️27××🧴 ",
    " 🧼 {text} 🪤89×~🪖 ",
    " 🪥 {text} ⚱️34××🧺 ",
    " 🧽 {text} 🧭76×~🚿 ",
    " 🧯 {text} 🛝22××🪑 ",
    " 🛒 {text} 📎61×~🪠 ",
    " 🧸 {text} 🫗13××🧻 ",
    " 🪆 {text} 🧊94×~🧹 ",
    " 🎐 {text} 🪞48××🪒 ",
    " 🪅 {text} 🧠80×~🛁 ",
    " 🎎 {text} ⚖️29××🧼 ",
    " 🪭 {text} 🪢57×~🪆 ",
    " 🧧 {text} 🧬96××🎐 ",
    " 🎴 {text} 🫧40×~🪅 ",
    " 🃏 {text} 🛼68××🎎 ",
    " 🎲 {text} 📡20×~🧧 ",
    " ♟️ {text} 🪫85××🎴 ",
]

NC8_TPL  = ("⧼{emoji}⧽{text} 𝗚𝗔𝗡𝗗𝗠𝗔𝗥𝗘 💎🔹🔷💠◻️◽️⬜️ ꧁⭕️꧂ 🟪🟣🟫🟤 ꧁⭕️꧂ 🟥🔺🟧🔶🟨🟡 ꧁⭕️꧂ 🟩🟢❇️✳️ ꧁⭕️꧂ 💎🔹🔷💠◻️◽️⬜️🟪🟣 ꧁⭕️꧂ 🟫🟤🟥🔺🟧🔶🟨🟡🟩🟢 ꧁⭕️꧂ "*10)
NC9_TPL  = ("<{emoji}>︵୨{text}୧₊KUTTIYA "
            + ("𒈙𒈔𒈙𒈔𒈙𒈔🔴" * 70))
NC10_TPL = ("☣️───《{text}》‧︵‿{emoji}‿︵‧ ☬ PILLO KI T⭕️LI 🥀 "
            + ("𒐫❄️" * 64)
            + "《🤣》───☣️ 🤣{emoji}🤣")

# ═══════════════════════════════════════════════════════════════
# 🎯  NC11–NC20
# ═══════════════════════════════════════════════════════════════

NC11_TPL = [
    "<🤍> {text}﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍 ᴛᴍ🇰🇱 ",
    "<❤️> {text}﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️ ᴛᴍ🇰🇱",
    "<🖤> {text}﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤 ᴛᴍ🇰🇱",
    "<🖤> {text}﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤 ᴛᴍ🇰🇱 ",
    "<💚> {text}﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚 ᴛᴍ🇰🇱 ",
    "<🧡> {text}﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡﷽﷽🧡 ᴛᴍ🇰🇱",
    "<💙> {text}﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙 ᴛᴍ🇰🇱",
    "<💜> {text}﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜 ᴛᴍ🇰🇱",
    "<🤎> {text}﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎 ᴛᴍᴋʟ",
    "<🖤> {text}﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤﷽﷽🖤 ᴛᴍ🇰🇱",
    " <🤍> {text}﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍﷽﷽🤍 ᴛᴍ🇰🇱",
    "<❤️> {text}﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️﷽﷽❤️ ᴛᴍ🇰🇱",
    "<💚> {text}﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚﷽﷽💚 ᴛᴍ🇰🇱",
    "<🤎> {text}﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎﷽﷽🤎 ᴛᴍᴋʟ",
    "<💙> {text}﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙﷽﷽💙 ᴛᴍ🇰🇱",
    "<💜> {text}﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜﷽﷽💜 ᴛᴍ🇰🇱",
]

NC12_TPL = [
        "{text}🏳️‍🌈<(205)", "{text}🏳️‍⚧️<(491)", "{text}🏴‍☠️<(229)", "{text}🇦🇨<(670)", "{text}🇦🇩<(80)",
    "{text}🇦🇪<(71)", "{text}🇦🇫<(100)", "{text}🇦🇬<(5)", "{text}🇦🇮<(980)", "{text}🇦🇱<(150)",
    "{text}🇦🇲<(69)", "{text}🇦🇴<(34)", "{text}🇦🇶<(102)", "{text}🇦🇷<(54)", "{text}🇦🇸<(5)",
    "{text}🇦🇹<(760)", "{text}🇦🇺<(42)", "{text}🇦🇼<(81)", "{text}🇦🇽<(91)", "{text}🇦🇿<(76)",
    "{text}🇧🇦<(59)", "{text}🇧🇧<(18)", "{text}🇧🇩<(37)", "{text}🇧🇪<(74)", "{text}🇧🇫<(27)",
    "{text}🇧🇬<(60)", "{text}🇧🇭<(43)", "{text}🇧🇮<(57)", "{text}🇧🇯<(77)", "{text}🇧🇲<(82)",
    "{text}🇧🇳<(51)", "{text}🇧🇴<(90)", "{text}🇧🇷<(187)", "{text}🇧🇸<(987)", "{text}🇧🇹<(235)",
    "{text}🇧🇻<(676)", "{text}🇧🇾<(555)", "{text}🇧🇿<(782)", "{text}🇨🇦<(247)", "{text}🇨🇨<(999)",
    "{text}🇨🇩<(709)", "{text}🇨🇫<(239)", "{text}🇨🇬<(306)", "{text}🇨🇮<(420)", "{text}🇦🇿<(666)"
,
]

NC13_TPL = [
    " {text}𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫 𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫𒐫🔥𒐫𓂃𝙆𝘼𝙈𝙕𝙊𝙍𓂃 𓈒𓏸🤣",
    "  {text}𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫 𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫𒐫🔥𒐫𓂃TMKC𓂃 𓈒𓏸🤣",
    "  {text}𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫 𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫𒐫🔥𒐫𓂃TATTE𓂃 𓈒𓏸🤣",
    "  {text}𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫 𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫🔥𒐫𒐫𒐫𒐫🔥𒐫𓂃TATTI KHA𓂃 𓈒𓏸🤣",
]

NC14_TPL = [
    "𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴😀ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴😄ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴😆ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴😂ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴😭ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴😉ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴😗ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴😘ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴😍ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴🤩ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴🙂ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴🥲ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴🥹ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴🥺ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴😝ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴😜ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴🤪ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴😬ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴😑ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴😐ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴🫢ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴🤭ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴🥱ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴🤗ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴😱ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴🤨ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴🧐ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴🤢ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴🥶ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴🥵ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴🤮ྀ࿐",

"𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸𓂃 𓈒𓏸(🌍)𓂃 𓈒𓏸ᎷᎯᎠᎯᏒᏨᎻᎾᎠ⁀➴😖ྀ࿐",
]

NC15_TPL = [
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🪢",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🪂",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🪩",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🪶",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🪝",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🪀",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🫧",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🪞",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🪡",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼⚓",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🌀",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🌊",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼💫",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🧬",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🔮",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🗡️",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🛡️",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼⚙️",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼⛓️",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🃏",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼⚡",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼☄️",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🧨",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼⚜️",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🕳️",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🏴‍☠️",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🔱",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🧩",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🪐",
    "꧁ঔৣ☬{text}☬ঔৣ꧂ ╰⪼🏮",
]

NC16_TPL = [
    "☾__{text}__☽",
    "🌙__{text}__🌙",
    "🌛__{text}__🌛",
    "🌜__{text}__🌜",
    "⭐__{text}__⭐",
    "🌟__{text}__🌟",
    "✨__{text}__✨",
    "☾__{text}__☽",
]

NC17_TPL = [
    "🎭 {text} ꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅ 🛕",
    "🎨 {text} ꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅ 🛕",
    "🎪 {text} ꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅ 🛕",
    "🎩 {text} ꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅ 🛕",
    "🎬 {text} ꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅ 🛕",
    "🎯 {text} ꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅ 🛕",
    "🎲 {text} ꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅꧅ 🛕",
]

NC18_TPL = [
    "(❄️)__{text}__❄️❄️𒈙🌍❄️𒈙𒈙𒈙𒈙🌍❄️𒈙𒈙⭕️𒈙𒈙❄️🌍❄️𒈙𒈙⭕️𒈙𒈙❄️🌍❄️𒈙𒈙⭕️𒈙𒈙🌍❄️𒈙𒈙⭕️𒈙𒈙🌍𒈙𒈙𒈙𒈙❄️🌍𒈙 ⭕️",
    "(⛄)__{text}__❄️❄️𒈙🌍❄️𒈙𒈙𒈙𒈙🌍❄️𒈙𒈙⭕️𒈙𒈙❄️🌍❄️𒈙𒈙⭕️𒈙𒈙❄️🌍❄️𒈙𒈙⭕️𒈙𒈙🌍❄️𒈙𒈙⭕️𒈙𒈙🌍𒈙𒈙𒈙𒈙❄️🌍𒈙 ⭕️",
    "(🌨️)__{text}__❄️❄️𒈙🌍❄️𒈙𒈙𒈙𒈙🌍❄️𒈙𒈙⭕️𒈙𒈙❄️🌍❄️𒈙𒈙⭕️𒈙𒈙❄️🌍❄️𒈙𒈙⭕️𒈙𒈙🌍❄️𒈙𒈙⭕️𒈙𒈙🌍𒈙𒈙𒈙𒈙❄️🌍𒈙 ⭕️",
    "(💧)__{text}__❄️❄️𒈙🌍❄️𒈙𒈙𒈙𒈙🌍❄️𒈙𒈙⭕️𒈙𒈙❄️🌍❄️𒈙𒈙⭕️𒈙𒈙❄️🌍❄️𒈙𒈙⭕️𒈙𒈙🌍❄️𒈙𒈙⭕️𒈙𒈙🌍𒈙𒈙𒈙𒈙❄️🌍𒈙 ⭕️",
    "(🌊)__{text}__❄️❄️𒈙🌍❄️𒈙𒈙𒈙𒈙🌍❄️𒈙𒈙⭕️𒈙𒈙❄️🌍❄️𒈙𒈙⭕️𒈙𒈙❄️🌍❄️𒈙𒈙⭕️𒈙𒈙🌍❄️𒈙𒈙⭕️𒈙𒈙🌍𒈙𒈙𒈙𒈙❄️🌍𒈙 ⭕️",
    "(💦)__{text}__❄️❄️𒈙🌍❄️𒈙𒈙𒈙𒈙🌍❄️𒈙𒈙⭕️𒈙𒈙❄️🌍❄️𒈙𒈙⭕️𒈙𒈙❄️🌍❄️𒈙𒈙⭕️𒈙𒈙🌍❄️𒈙𒈙⭕️𒈙𒈙🌍𒈙𒈙𒈙𒈙❄️🌍𒈙 ⭕️",
    "(☃️)__{text}__❄️❄️𒈙🌍❄️𒈙𒈙𒈙𒈙🌍❄️𒈙𒈙⭕️𒈙𒈙❄️🌍❄️𒈙𒈙⭕️𒈙𒈙❄️🌍❄️𒈙𒈙⭕️𒈙𒈙🌍❄️𒈙𒈙⭕️𒈙𒈙🌍𒈙𒈙𒈙𒈙❄️🌍𒈙 ⭕️",
]

NC19_TPL = [
    "🔥/{text}௹🔴௹",
    "🌋/{text}௹🔴௹",
    "☄️/{text}௹🔴௹",
    "💥/{text}௹🔴௹",
    "⚡/{text}௹🔴௹",
    "🌩️/{text}௹🔴௹",
    "💫/{text}௹🔴௹",
]

NC20_TPL = [
    "🖤🌈__{text} ̿ ̅ ̄ ̆ ̇ ̈ ̉ ̊ ̋ ̌ 🌤️̍ ̎ ̏ ̐ ̑ ̒ ̓ ̔ ̕ ̖ ̗ ̘ ̙ ̚ ̛ ̜ ̝ ̞ ̟ ̠ ̡ ̢ ̣ ̤ 😂̥ ̦ ̧ ̨ ̩ ̪ ̫ ̬🐊 ̭ ̮ ̯ ̰ ̱ ̲ ̳⭕️🖤",
    "💀😱__{text} ̿ ̅ ̄ ̆ ̇ ̈ ̉ ̊ ̋ ̌ 🌤️̍ ̎ ̏ ̐ ̑ ̒ ̓ ̔ ̕ ̖ ̗ ̘ ̙ ̚ ̛ ̜ ̝ ̞ ̟ ̠ ̡ ̢ ̣ ̤ 😂̥ ̦ ̧ ̨ ̩ ̪ ̫ ̬🐊 ̭ ̮ ̯ ̰ ̱ ̲ ̳⭕️💀",
    "☠️❄️__{text} ̿ ̅ ̄ ̆ ̇ ̈ ̉ ̊ ̋ ̌ 🌤️̍ ̎ ̏ ̐ ̑ ̒ ̓ ̔ ̕ ̖ ̗ ̘ ̙ ̚ ̛ ̜ ̝ ̞ ̟ ̠ ̡ ̢ ̣ ̤ 😂̥ ̦ ̧ ̨ ̩ ̪ ̫ ̬🐊 ̭ ̮ ̯ ̰ ̱ ̲ ̳⭕️☠️",
    "🔁🎃__{text} ̿ ̅ ̄ ̆ ̇ ̈ ̉ ̊ ̋ ̌ 🌤️̍ ̎ ̏ ̐ ̑ ̒ ̓ ̔ ̕ ̖ ̗ ̘ ̙ ̚ ̛ ̜ ̝ ̞ ̟ ̠ ̡ ̢ ̣ ̤ 😂̥ ̦ ̧ ̨ ̩ ̪ ̫ ̬🐊 ̭ ̮ ̯ ̰ ̱ ̲ ̳⭕️🎃",
    "👻🌍__{text} ̿ ̅ ̄ ̆ ̇ ̈ ̉ ̊ ̋ ̌ 🌤️̍ ̎ ̏ ̐ ̑ ̒ ̓ ̔ ̕ ̖ ̗ ̘ ̙ ̚ ̛ ̜ ̝ ̞ ̟ ̠ ̡ ̢ ̣ ̤ 😂̥ ̦ ̧ ̨ ̩ ̪ ̫ ̬🐊 ̭ ̮ ̯ ̰ ̱ ̲ ̳⭕️👻",
    "🕷️🔻__{text} ̿ ̅ ̄ ̆ ̇ ̈ ̉ ̊ ̋ ̌ 🌤️̍ ̎ ̏ ̐ ̑ ̒ ̓ ̔ ̕ ̖ ̗ ̘ ̙ ̚ ̛ ̜ ̝ ̞ ̟ ̠ ̡ ̢ ̣ ̤ 😂̥ ̦ ̧ ̨ ̩ ̪ ̫ ̬🐊 ̭ ̮ ̯ ̰ ̱ ̲ ̳⭕️🕷️",
    "🕸️☀️__{text} ̿ ̅ ̄ ̆ ̇ ̈ ̉ ̊ ̋ ̌ 🌤️̍ ̎ ̏ ̐ ̑ ̒ ̓ ̔ ̕ ̖ ̗ ̘ ̙ ̚ ̛ ̜ ̝ ̞ ̟ ̠ ̡ ̢ ̣ ̤ 😂̥ ̦ ̧ ̨ ̩ ̪ ̫ ̬🐊 ̭ ̮ ̯ ̰ ̱ ̲ ̳⭕️🕸️",
    "🦇🩵__{text} ̿ ̅ ̄ ̆ ̇ ̈ ̉ ̊ ̋ ̌ 🌤️̍ ̎ ̏ ̐ ̑ ̒ ̓ ̔ ̕ ̖ ̗ ̘ ̙ ̚ ̛ ̜ ̝ ̞ ̟ ̠ ̡ ̢ ̣ ̤ 😂̥ ̦ ̧ ̨ ̩ ̪ ̫ ̬🐊 ̭ ̮ ̯ ̰ ̱ ̲ ̳⭕️🦇",
    "🧛🫶🏻__{text} ̿ ̅ ̄ ̆ ̇ ̈ ̉ ̊ ̋ ̌ 🌤️̍ ̎ ̏ ̐ ̑ ̒ ̓ ̔ ̕ ̖ ̗ ̘ ̙ ̚ ̛ ̜ ̝ ̞ ̟ ̠ ̡ ̢ ̣ ̤ 😂̥ ̦ ̧ ̨ ̩ ̪ ̫ ̬🐊 ̭ ̮ ̯ ̰ ̱ ̲ ̳⭕️🧛",    "🔥⚡__{text} ̿ ̅ ̄ ̆ ̇ ̈ ̉ ̊ ̋ ̌ 🌤️̍ ̎ ̏ ̐ ̑ ̒ ̓ ̔ ̕ ̖ ̗ ̘ ̙ ̚ ̛ ̜ ̝ ̞ ̟ ̠ ̡ ̢ ̣ ̤ 😂̥ ̦ ̧ ̨ ̩ ̪ ̫ ̬🐊 ̭ ̮ ̯ ̰ ̱ ̲ ̳⭕️🔥⚡",
    "👑💎__{text} ̿ ̅ ̄ ̆ ̇ ̈ ̉ ̊ ̋ ̌ 🌤️̍ ̎ ̏ ̐ ̑ ̒ ̓ ̔ ̕ ̖ ̗ ̘ ̙ ̚ ̛ ̜ ̝ ̞ ̟ ̠ ̡ ̢ ̣ ̤ 😂̥ ̦ ̧ ̨ ̩ ̪ ̫ ̬🐊 ̭ ̮ ̯ ̰ ̱ ̲ ̳⭕️👑💎",
    "🐍⚡__{text} ̿ ̅ ̄ ̆ ̇ ̈ ̉ ̊ ̋ ̌ 🌤️̍ ̎ ̏ ̐ ̑ ̒ ̓ ̔ ̕ ̖ ̗ ̘ ̙ ̚ ̛ ̜ ̝ ̞ ̟ ̠ ̡ ̢ ̣ ̤ 😂̥ ̦ ̧ ̨ ̩ ̪ ̫ ̬🐊 ̭ ̮ ̯ ̰ ̱ ̲ ̳⭕️🐍⚡",
    "🌪️⚔️__{text} ̿ ̅ ̄ ̆ ̇ ̈ ̉ ̊ ̋ ̌ 🌤️̍ ̎ ̏ ̐ ̑ ̒ ̓ ̔ ̕ ̖ ̗ ̘ ̙ ̚ ̛ ̜ ̝ ̞ ̟ ̠ ̡ ̢ ̣ ̤ 😂̥ ̦ ̧ ̨ ̩ ̪ ̫ ̬🐊 ̭ ̮ ̯ ̰ ̱ ̲ ̳⭕️🌪️⚔️",
    "🗡️🩸__{text} ̿ ̅ ̄ ̆ ̇ ̈ ̉ ̊ ̋ ̌ 🌤️̍ ̎ ̏ ̐ ̑ ̒ ̓ ̔ ̕ ̖ ̗ ̘ ̙ ̚ ̛ ̜ ̝ ̞ ̟ ̠ ̡ ̢ ̣ ̤ 😂̥ ̦ ̧ ̨ ̩ ̪ ̫ ̬🐊 ̭ ̮ ̯ ̰ ̱ ̲ ̳⭕️🗡️🩸",
    "🐉🔥__{text} ̿ ̅ ̄ ̆ ̇ ̈ ̉ ̊ ̋ ̌ 🌤️̍ ̎ ̏ ̐ ̑ ̒ ̓ ̔ ̕ ̖ ̗ ̘ ̙ ̚ ̛ ̜ ̝ ̞ ̟ ̠ ̡ ̢ ̣ ̤ 😂̥ ̦ ̧ ̨ ̩ ̪ ̫ ̬🐊 ̭ ̮ ̯ ̰ ̱ ̲ ̳⭕️🐉🔥",
    "🌊⚓__{text} ̿ ̅ ̄ ̆ ̇ ̈ ̉ ̊ ̋ ̌ 🌤️̍ ̎ ̏ ̐ ̑ ̒ ̓ ̔ ̕ ̖ ̗ ̘ ̙ ̚ ̛ ̜ ̝ ̞ ̟ ̠ ̡ ̢ ̣ ̤ 😂̥ ̦ ̧ ̨ ̩ ̪ ̫ ̬🐊 ̭ ̮ ̯ ̰ ̱ ̲ ̳⭕️🌊⚓",
    "⚡🌀__{text} ̿ ̅ ̄ ̆ ̇ ̈ ̉ ̊ ̋ ̌ 🌤️̍ ̎ ̏ ̐ ̑ ̒ ̓ ̔ ̕ ̖ ̗ ̘ ̙ ̚ ̛ ̜ ̝ ̞ ̟ ̠ ̡ ̢ ̣ ̤ 😂̥ ̦ ̧ ̨ ̩ ̪ ̫ ̬🐊 ̭ ̮ ̯ ̰ ̱ ̲ ̳⭕️⚡🌀",
    "🔥🖤__{text} ̿ ̅ ̄ ̆ ̇ ̈ ̉ ̊ ̋ ̌ 🌤️̍ ̎ ̏ ̐ ̑ ̒ ̓ ̔ ̕ ̖ ̗ ̘ ̙ ̚ ̛ ̜ ̝ ̞ ̟ ̠ ̡ ̢ ̣ ̤ 😂̥ ̦ ̧ ̨ ̩ ̪ ̫ ̬🐊 ̭ ̮ ̯ ̰ ̱ ̲ ̳⭕️🔥🖤",
    "🥀💔__{text} ̿ ̅ ̄ ̆ ̇ ̈ ̉ ̊ ̋ ̌ 🌤️̍ ̎ ̏ ̐ ̑ ̒ ̓ ̔ ̕ ̖ ̗ ̘ ̙ ̚ ̛ ̜ ̝ ̞ ̟ ̠ ̡ ̢ ̣ ̤ 😂̥ ̦ ̧ ̨ ̩ ̪ ̫ ̬🐊 ̭ ̮ ̯ ̰ ̱ ̲ ̳⭕️🥀💔",
    "🔮✨__{text} ̿ ̅ ̄ ̆ ̇ ̈ ̉ ̊ ̋ ̌ 🌤️̍ ̎ ̏ ̐ ̑ ̒ ̓ ̔ ̕ ̖ ̗ ̘ ̙ ̚ ̛ ̜ ̝ ̞ ̟ ̠ ̡ ̢ ̣ ̤ 😂̥ ̦ ̧ ̨ ̩ ̪ ̫ ̬🐊 ̭ ̮ ̯ ̰ ̱ ̲ ̳⭕️🔮✨",
    "🖤🔥__{text} ̿ ̅ ̄ ̆ ̇ ̈ ̉ ̊ ̋ ̌ 🌤️̍ ̎ ̏ ̐ ̑ ̒ ̓ ̔ ̕ ̖ ̗ ̘ ̙ ̚ ̛ ̜ ̝ ̞ ̟ ̠ ̡ ̢ ̣ ̤ 😂̥ ̦ ̧ ̨ ̩ ̪ ̫ ̬🐊 ̭ ̮ ̯ ̰ ̱ ̲ ̳⭕️🖤🔥"

]

MODE_MAP = {
    "spam":      ["#{text} #𝗚𝗔𝗡𝗗𝗠𝗔𝗥𝗘 𝗧𝗘𝗥𝗜 𝗜𝗧𝗡𝗜 𝗛𝗜𝗠𝗠𝗔𝗧 𝗧𝗨 #𝗟𝗨𝗙𝗙𝗬 𝗕𝗔𝗔𝗣 𝗞𝗘 𝗦𝗔𝗠𝗡𝗘 #𝗔𝗪𝗔𝗭 𝗨𝗖𝗛𝗜 𝗞𝗥𝗘𝗚𝗔 ?? 𝗠𝗔𝗗𝗥𝗖𝗛⭕️𝗗 🤍🌙🕊️_____________________/"*25],
    "msg":       ["{text} 💀"],
    "gearspam":  ["⮑{text}⮐ #γє #ριℓℓE #gαяєєϐ #мαα #κι #gαяєєϐ #ϲнυτ #ѕє #иικℓE #нυE #κєє∂E #нαι⇕ ⇖ ⇗ ⇘ ⇙ ⇕ ⇖ ⇗ ⇘ ⇙ ⇕ ⇖ ⇗ ⇘ ⇙ ⇕ ⇖ ⇗⇕ ⇖ ⇗ ⇘ ⇙ ⇕ ⇖ ⇗ ⇘ ⇙ ⇕ ⇖ ⇗ ⇘ ⇙ ⇕ ⇖ [PILL⭕️ KI ~ T⭕️LI] "
                  ". ݁₊ ⊹ . ݁˖ . ݁𓂃"*10],
    "chud":      ["{text} Tᴇʀɪ Dᴀᴅɪ ᴋ ᴄʜᴍᴜᴛ ᴍᴀɪ ᴛᴀɴɢ ᴀᴛᴋᴀ ᴅᴜɴɢᴀ 😍"],
    "title":     ["{text} RΛɴᴅʏᴋᴇ LΛᴅᴋᴇ 🔥 " + "𒐫"*40],
    "nc":        ["{text} RΛɴᴅʏᴋᴇ LΛᴅᴋᴇ 🔥 " + "𒐫"*40],
    "slutnc":    ["{text} {word} 𒐫𒐫𒐫❌𒐫❌𒐫🩷𒐫𒐫✳️❌ 𒐫🩷𒐫𒐫✅𒐫❌𒐫𒐫🩷𒐫🩷 ➴ྀ࿐ 𒐫𒐫𒐫❌𒐫❌𒐫𒐫𒐫✳️❌ 𒐫𒐫𒐫✅𒐫❌𒐫𒐫𒐫 ➴ྀ࿐ 𒐫🩷𒐫𒐫❌𒐫❌𒐫𒐫𒐫✳️❌ 𒐫🩷𒐫𒐫✅𒐫❌𒐫🩷𒐫𒐫 ➴ྀ࿐ ··"],
    "kaidonc":   KAIDONC_TPL,
    "ncblast":   ["{text} RΛɴᴅʏᴋᴇ LΛᴅᴋᴇ {emoji} " + "𒐫"*54],
    "blastnc":   ["{text} RΛɴᴅʏᴋᴇ LΛᴅᴋᴇ {emoji} " + "𒐫"*54],
    "pilla":     ["{text} 𝐓ᴇʀ𝐈 𝐌ᴀ𝐀 𝐂ʜ⭕𝐃 𝐃△ʟᴇɴɢ𝐄 <{emoji}>"],
    "gulam":     ["[{emoji}] {text} GULAM CHUD " + "❌⭕️"*30],
    "hasy":      ["{text} ᑕʜᴜƿ RΛɴᴅʏᴋΣ" + "𓍯😂"*22 + "〘{emoji}〙"],
    "luffygod":  ["𓆩{emoji}𓆪 {text} ʟᴀɢᴀ ᴛᴇʀʏ ᴍᴀᴀ ᴋɪ ᴄʜᴏᴏᴛ ᴋᴀ ᴅᴀᴍᴍ "
                  + "𓆩ᥫ᭡𓆪⭕️"*70 + " 𝗧ᴍᴋᴄ 🅜🅐🅘 𝗞ᴇʟᴀ 🛕🍌"],
    "filternc":  ["{text} 𝙈𝘼𝘿𝘼𝙍𝘾𝙃⭕𝘿" + "𒐫𒐫𒐫{emoji}"*23],
    "vegetagawd":["『{emoji}> {text} 𝙖𝙖𝙜 𝙡𝙖𝙜𝙞 𝙝 𝙗𝙖𝙨𝙩𝙞 𝙢 𝙩𝙚𝙧𝙞 𝙢𝙖𝙖 𝙘𝙝𝙪𝙙𝙧𝙞 𝙢𝙖𝙨𝙩𝙞 𝙢 "
                  "🍷━━━》💜🩷💚💛🤍🩷💜❤️⭕️🖤💛🩷💜🧡🖤❤️🤎🧡🖤🩷💜🤍⭕️🩷💜❤️⭕️🖤💛🤍🩷💜🩶💛❤️🤍🩷⭕️💜🖤💛💜🩷💛🩶⭕️💜🧡🖤🩷💜⭕️🧡🖤🩷💜🧡🖤💙🩷💜❤️💚🧡🩷💙🧡🖤🩷💙⭕️❤️🖤💛🩷💜💛🖤❤️━━━》🍷━━》━━━━━━》🍷━━━━》🍷━━━━━"],
    "glitchnc":  ["{text} {word} 🐷 " + "𒈔𒈔𒈔🩷"*20],
    "glitch":    ["{text} {word} 🐷 " + "𒈔𒈔𒈔🩷"*20],
    "cutenc":    ["{text} {cut}"],
    "nc1":       NC1_TPL,
    "nc2":       ["{emoji} {text} ᑕᕼᑌᑭ ᗰᗩᴋᴇᒪᴏᗪᴇ " + "𒈙✳️"*35],
    "nc3":       ["<{emoji}> {text} " + "𒅄𒅄𒅄🍌𒅄𒅄𒅄𒅄🍷"*10],
    "nc4":       ["({emoji})‧︵‿₊୨{text}୧₊‿︵‧{text}₊⊹ 𝐓ᴇʀɪ 𝐌ᴀᴀ सूरज ☀️ "
                  "𝐍ɪᴋᴀʟɴᴇ 𝐒ᴇ 𝐏ᴀʜʟᴇ 𝐇ᴇ 𝐂ʜᴏᴅ 𝐃ᴜ 👈 🟡 ({emoji})"],
    "nc5":       ["<{text}>Cʜꪊᴅ ɢʏꪖ"+"𒅒❤️"*48],
    "nc6":       [NC6_TPL],
    "nc7":       NC7_TPL,
    "nc8":       [NC8_TPL],
    "nc9":       [NC9_TPL],
    "nc10":      [NC10_TPL],
    "nc11":      NC11_TPL,
    "nc12":      NC12_TPL,
    "nc13":      NC13_TPL,
    "nc14":      NC14_TPL,
    "nc15":      NC15_TPL,
    "nc16":      NC16_TPL,
    "nc17":      NC17_TPL,
    "nc18":      NC18_TPL,
    "nc19":      NC19_TPL,
    "nc20":      NC20_TPL,
    "both":      ["{text} SAY LUFFY DADDY STOP!! " + "𒐫"*30],
    "blast":     ["{text} RΛɴᴅʏᴋᴇ LΛᴅᴋᴇ 💣 " + "𒐫"*40],
    "boomnc":    [BOOMNC_TPL],
    "rulernc":   RULERNC_TPL,
    "npcnc":     [NPCNC_TPL],
    "slavenc":   SLAVENC_TPL,
    "xxxnc":     [XXXNC_TPL],
}

photo_pool: list = []


# ═══════════════════════════════════════════════════════════════
# ☢️  NUCLEAR STOP SYSTEM
# ═══════════════════════════════════════════════════════════════

ALL_LOOP_KINDS = {
    "spam","gearspam","chud","msg","both","blast",
    "swipe","pfp","desc",
    "title","nc",
    "nc1","nc2","nc3","nc4","nc5","nc6","nc7","nc8","nc9","nc10",
    "nc11","nc12","nc13","nc14","nc15","nc16","nc17","nc18","nc19","nc20",
    "slutnc","kaidonc","ncblast","blastnc",
    "pilla","gulam","hasy","luffygod",
    "filternc","vegetagawd","glitchnc","glitch","cutenc",
    "boomnc","rulernc","npcnc","slavenc","xxxnc",
    "spamwatch_counter","generic",
}
NC_KINDS = {k for k in ALL_LOOP_KINDS
            if k not in ("spam","gearspam","msg","chud",
                         "both","blast","swipe","pfp","desc",
                         "spamwatch_counter","generic")}
SPAM_KINDS = {"spam","gearspam","msg","chud","both","blast"}

def nuke_chat(chat_id: int, wipe_state: bool = True) -> dict:
    stats = {}
    before = len(TASKS.get(chat_id, []))
    cancel_tasks(chat_id, None)
    stats["tasks_killed"] = before
    TASKS.pop(chat_id, None)
    stats["swipe_was_on"] = bool(SWIPE_ON.get(chat_id))
    SWIPE_ON[chat_id] = False
    if wipe_state:
        CHUD_TEXT.pop(chat_id, None)
        SWIPE_MSG.pop(chat_id, None)
        SWIPE_SRC.pop(chat_id, None)
        spamwatch_chats.pop(chat_id, None)
        _sw_bursts.pop(chat_id, None)
        DESC_LOOP.pop(chat_id, None)
        stats["spamwatch_off"] = True
    else:
        stats["spamwatch_off"] = False
    photo_pool.clear()
    return stats

async def _kill_kinds(chat_id: int, kinds: set) -> int:
    if chat_id not in TASKS: return 0
    keep, killed = [], 0
    for t in TASKS[chat_id]:
        k = getattr(t, "_kind", "generic")
        if k in kinds:
            t.cancel(); killed += 1
        else:
            keep.append(t)
    TASKS[chat_id] = keep
    return killed


# ═══════════════════════════════════════════════════════════════
# 🔁  RENDER + LOOPS
# ═══════════════════════════════════════════════════════════════
def _render(template: str, base: str, idx: int, mode: str = "") -> str:
    # NC7 / SLAVENC emoji append (mode-aware, always at end)
    if mode == "nc7":
        template = template + " " + NC7_EMOJI[idx % len(NC7_EMOJI)]
    elif mode == "slavenc":
        template = template + " " + SLAVENC_EMOJI[idx % len(SLAVENC_EMOJI)]

    out = template.replace("{text}", base)
    if "{emojie1}" in out or "{emojie2}" in out:
        out = out.replace("{emojie1}", XXX_CYCLE_1[idx % len(XXX_CYCLE_1)])
        out = out.replace("{emojie2}", XXX_CYCLE_2[idx % len(XXX_CYCLE_2)])
    if "{emojie}" in out:
        if "匚卄ㄩ卩" in out: pool = BOOM_HEART_CYCLE
        elif "NPC KE AAGE NAACH" in out: pool = NPC_FLAG_CYCLE
        elif "⭕️✳️🔻🔺" in out: pool = SLAVE_CAR_CYCLE
        else: pool = BLASTNC_EMOJI
        out = out.replace("{emojie}", pool[idx % len(pool)])
    if "{emoji}" in out:
        pool = BLASTNC_EMOJI
        if "GULAM" in out or ("CHUD" in out and "❌⭕️" in out): pool = GULAM_EMOJI
        elif "ᑕʜᴜƿ" in out: pool = HASY_EMOJI
        elif "𓆩" in out and "ʟᴀɢᴀ" in out: pool = LUFFYGOD_EMOJI
        elif "𝙈𝘼𝘿𝘼𝙍𝘾𝙃" in out: pool = FILTER_EMOJI
        elif "『" in out and "𝙖𝙖𝙜" in out: pool = VEGETA_EMOJI
        elif "ᑕᕼᑌᑭ" in out: pool = NC2_EMOJI
        elif "𒅄" in out: pool = NC3_EMOJI
        elif "सूरज" in out: pool = NC4_EMOJI
        elif "𒅒" in out: pool = NC5_EMOJI
        elif "𝐓ᴇʀ𝐈" in out: pool = PILLA_EMOJI
        elif "ꜱᴀʏ EDEN ᴅᴀᴅᴅʏ" in out: pool = NC6_EMOJI
        elif "52×~" in out or "17××" in out: pool = NC7_EMOJI
        elif "𝗚𝗔𝗡𝗗𝗠𝗔𝗥𝗘" in out: pool = NC8_EMOJI
        elif "KUTTIYA" in out: pool = NC9_EMOJI
        elif "PILLO KI T" in out: pool = NC10_EMOJI
        out = out.replace("{emoji}", pool[idx % len(pool)])
    if "{word}" in out:
        pool = WORDS_SLUTNC if "𒐫" in out else GLITCH_WORDS
        out = out.replace("{word}", pool[idx % len(pool)])
    if "{cut}" in out:
        out = out.replace("{cut}", CUTENC_POOL[idx % len(CUTENC_POOL)])
    return out


async def bot_loop(bot: Bot, bot_id: int, chat_id: int,
                   base: str, mode: str, reply_to_id=None):
    guard     = get_limiter(bot_id)
    templates = MODE_MAP.get(mode, emox_EMOJIS)
    if isinstance(templates, tuple): templates = list(templates)
    if not isinstance(templates, list): templates = [str(templates)]
    flat = []
    for t in templates:
        if isinstance(t, (list, tuple)): flat.extend(list(t))
        else: flat.append(t)
    templates = [str(t) for t in flat if t]
    if not templates: templates = ["{text}"]

    i, tick   = 0, 0
    consecutive_err = 0

    while True:
        try:
            raw = templates[i % len(templates)]
            txt = _render(raw, base, i, mode) + guard.suffix(i)

            if mode in FAST_MODES:
                tick += 1
                if tick % 40 == 0:
                    try: await bot.get_chat(chat_id)
                    except Exception: pass

            if mode in BOTH_MODES:
                asyncio.create_task(guard.send_message(
                    bot, chat_id, txt, reply_to_message_id=reply_to_id))
                asyncio.create_task(guard.set_chat_title(bot, chat_id, txt))
            elif mode in TITLE_MODES:
                await guard.set_chat_title(bot, chat_id, txt)
            else:
                m = await guard.send_message(bot, chat_id, txt,
                                             reply_to_message_id=reply_to_id)
                if mode in PIN_MODES and AUTOPIN.get(chat_id, True) and m:
                    asyncio.create_task(guard.pin_chat_message(
                        bot, chat_id, m.message_id, disable_notification=True))

            i += 1
            consecutive_err = 0
            d = get_delay(chat_id)
            if d > 0: await asyncio.sleep(d)
            else:     await asyncio.sleep(0)

        except asyncio.CancelledError:
            return
        except Exception:
            consecutive_err += 1
            await asyncio.sleep(min(0.05, 0.002 * consecutive_err))


async def photo_loop(bot: Bot, bot_id: int, chat_id: int):
    guard, i = get_limiter(bot_id), 0
    while True:
        try:
            if not photo_pool:
                await asyncio.sleep(0.1); continue
            bio = BytesIO(photo_pool[i % len(photo_pool)]); bio.name = "pfp.jpg"
            await guard.set_chat_photo(bot, chat_id, bio)
            i += 1
            d = get_delay(chat_id)
            if d > 0: await asyncio.sleep(d)
            else: await asyncio.sleep(0)
        except asyncio.CancelledError:
            return
        except Exception:
            await asyncio.sleep(0.02)


async def swipe_loop(bot: Bot, bot_id: int, chat_id: int,
                     text: str, reply_to_id=None):
    guard = get_limiter(bot_id); i = 0
    while SWIPE_ON.get(chat_id, False):
        try:
            await guard.send_message(bot, chat_id, text + guard.suffix(i),
                                     reply_to_message_id=reply_to_id)
            i += 1
            d = get_delay(chat_id)
            if d > 0: await asyncio.sleep(d)
            else: await asyncio.sleep(0)
        except asyncio.CancelledError:
            return
        except Exception:
            await asyncio.sleep(0.005)


async def desc_loop(bot: Bot, bot_id: int, chat_id: int, text: str):
    guard = get_limiter(bot_id); i = 0
    while True:
        try:
            tpl = DESC_TEMPLATES[i % len(DESC_TEMPLATES)]
            desc = tpl.replace("{text}", text)
            await guard.set_chat_description(bot, chat_id, desc)
            i += 1
            d = get_delay(chat_id)
            if d > 0: await asyncio.sleep(d)
            else: await asyncio.sleep(0)
        except asyncio.CancelledError:
            return
        except Exception:
            await asyncio.sleep(0.02)


DESC_TEMPLATES = [
    "{text} ─ CHUDAI K BAKRE",
    "CHUD MADARCH⭕️D  {text}",
    "<<⭕️>> HSY AARI {text}  𓆩ᥫ᭡𓆪",
    "🌊 {text} ─ LUFFY KE PILLE",
    "{text}  KAMZOR PILLE",
    "❄️ {text} ❄️",
    "{text}  🕸️ AUR ZOR LAGA IDHR MTT DEKH 🤣",
    "🔥 {text} CVRR KRR CH⭕️TEY",
    "{text} ─ CHUDAI KE PILLE 🌊",
    "⸎❄️ {text}",
]


async def promote_all_bots(chat_id: int) -> list:
    promoter = None
    for app in ALL_APPS:
        try:
            me = await app.bot.get_chat_member(chat_id, app.bot.id)
            if getattr(me, "can_promote_members", False):
                promoter = app.bot; break
        except Exception: continue
    if promoter is None:
        return ["❌ Kisi bot ke paas 'Add Admins' permission nahi hai."]
    results = []
    for app in ALL_APPS:
        b = app.bot
        if b.id == promoter.id: continue
        try:
            await promoter.promote_chat_member(
                chat_id=chat_id, user_id=b.id,
                can_change_info=True, can_delete_messages=True,
                can_invite_users=True, can_restrict_members=True,
                can_pin_messages=True, can_promote_members=True,
                can_manage_chat=True, can_manage_video_chats=True,
                can_post_messages=True, can_edit_messages=True,
                can_post_stories=True, can_edit_stories=True,
                can_delete_stories=True, is_anonymous=False)
            bme = await b.get_me()
            results.append(f"✅ {bme.first_name} (@{bme.username})")
        except Exception as e:
            results.append(f"❌ bot#{b.id}: {str(e)[:60]}")
    return results


def _track_burst(chat_id: int, user_id: int) -> bool:
    now = time.monotonic()
    bucket = _sw_bursts.setdefault(chat_id, {}).setdefault(user_id, [])
    bucket.append(now)
    _sw_bursts[chat_id][user_id] = [t for t in bucket if now - t <= SW_WINDOW]
    return len(_sw_bursts[chat_id][user_id]) >= SW_THRESH


async def _trigger_spamwatch(chat_id: int, rival_id: int, notify_id: int):
    st = spamwatch_chats.get(chat_id)
    if not st: return
    now = time.monotonic()
    if now - st.get("last_trigger", 0.0) < 0.3: return
    st["last_trigger"] = now
    st["active_rival"] = rival_id
    st["counter_on"]   = True
    try:
        rival = await ALL_APPS[0].bot.get_chat(rival_id)
        handle = f"@{rival.username}" if rival.username else (rival.first_name or str(rival_id))
    except Exception:
        handle = str(rival_id)
    cancel_tasks(chat_id, {"spamwatch_counter"})
    text = f"{handle} +TMKC PILLE 🔥"
    for app in ALL_APPS:
        t = asyncio.create_task(
            bot_loop(app.bot, app.bot.id, chat_id, text, SW_COUNTER, notify_id))
        add_task(chat_id, t, kind="spamwatch_counter")
        await asyncio.sleep(0.001)


# ═══════════════════════════════════════════════════════════════
# 💬  COMMAND PARSER
# ═══════════════════════════════════════════════════════════════
def parse_cmd(text: str):
    if not text or not text.startswith(PREFIX): return None, ""
    body = text[len(PREFIX):].strip()
    if not body: return None, ""
    parts = body.split(maxsplit=1)
    return parts[0].lower(), (parts[1] if len(parts) > 1 else "")


# ═══════════════════════════════════════════════════════════════
# 🔤  FONT GENERATOR
# ═══════════════════════════════════════════════════════════════
def _uni_map(upper: int, lower: int, digit: int | None = None,
             override: dict | None = None) -> dict:
    m = {}
    for i in range(26):
        m[chr(ord('A') + i)] = chr(upper + i)
        m[chr(ord('a') + i)] = chr(lower + i)
    if digit is not None:
        for i in range(10):
            m[chr(ord('0') + i)] = chr(digit + i)
    if override: m.update(override)
    return m

_FONT_DEFS = [
    ("Bold",              _uni_map(0x1D400, 0x1D41A, 0x1D7CE)),
    ("Italic",            _uni_map(0x1D434, 0x1D44E, None, {"h": "ℎ"})),
    ("Bold Italic",       _uni_map(0x1D468, 0x1D482)),
    ("Script",            _uni_map(0x1D49C, 0x1D4B6, None, {
        "B": "ℬ", "E": "ℰ", "F": "ℱ", "H": "ℋ", "I": "ℐ", "L": "ℒ",
        "M": "ℳ", "R": "ℛ", "e": "ℯ", "g": "ℊ", "o": "ℴ"})),
    ("Bold Script",       _uni_map(0x1D4D0, 0x1D4EA)),
    ("Fraktur",           _uni_map(0x1D504, 0x1D51E, None, {
        "C": "ℭ", "H": "ℌ", "I": "ℑ", "R": "ℜ", "Z": "ℨ"})),
    ("Double-Struck",     _uni_map(0x1D538, 0x1D552, 0x1D7D8, {
        "C": "ℂ", "H": "ℍ", "N": "ℕ", "P": "ℙ", "Q": "ℚ", "R": "ℝ", "Z": "ℤ"})),
    ("Sans Bold",         _uni_map(0x1D5D4, 0x1D5EE, 0x1D7EC)),
    ("Sans Italic",       _uni_map(0x1D608, 0x1D622)),
    ("Sans Bold Italic",  _uni_map(0x1D63C, 0x1D656)),
    ("Monospace",         _uni_map(0x1D670, 0x1D68A, 0x1D7F6)),
    ("Fullwidth",         _uni_map(0xFF21, 0xFF41, 0xFF10)),
    ("Circled",           _uni_map(0x24B6, 0x24D0, None, {
        "0": "⓪", "1": "①", "2": "②", "3": "③", "4": "④",
        "5": "⑤", "6": "⑥", "7": "⑦", "8": "⑧", "9": "⑨"})),
    ("Squared",           _uni_map(0x1F130, 0x1F130)),
]
_SMALLCAPS = {
    'a':'ᴀ','b':'ʙ','c':'ᴄ','d':'ᴅ','e':'ᴇ','f':'ꜰ','g':'ɢ','h':'ʜ','i':'ɪ',
    'j':'ᴊ','k':'ᴋ','l':'ʟ','m':'ᴍ','n':'ɴ','o':'ᴏ','p':'ᴘ','q':'ǫ','r':'ʀ',
    's':'ꜱ','t':'ᴛ','u':'ᴜ','v':'ᴠ','w':'ᴡ','x':'x','y':'ʏ','z':'ᴢ'}
_SUPERSCRIPT = {
    'a':'ᵃ','b':'ᵇ','c':'ᶜ','d':'ᵈ','e':'ᵉ','f':'ᶠ','g':'ᵍ','h':'ʰ','i':'ⁱ',
    'j':'ʲ','k':'ᵏ','l':'ˡ','m':'ᵐ','n':'ⁿ','o':'ᵒ','p':'ᵖ','q':'ᑫ','r':'ʳ',
    's':'ˢ','t':'ᵗ','u':'ᵘ','v':'ᵛ','w':'ʷ','x':'ˣ','y':'ʸ','z':'ᶻ',
    '0':'⁰','1':'¹','2':'²','3':'³','4':'⁴','5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹'}
_FLIP = {
    'a':'ɐ','b':'q','c':'ɔ','d':'p','e':'ǝ','f':'ɟ','g':'ƃ','h':'ɥ','i':'ᴉ',
    'j':'ɾ','k':'ʞ','l':'l','m':'ɯ','n':'u','o':'o','p':'d','q':'b','r':'ɹ',
    's':'s','t':'ʇ','u':'n','v':'ʌ','w':'ʍ','x':'x','y':'ʎ','z':'z',
    'A':'∀','B':'𐐒','C':'Ɔ','D':'◖','E':'Ǝ','F':'Ⅎ','G':'⅁','H':'H','I':'I',
    'J':'ſ','K':'ʞ','L':'˥','M':'W','N':'N','O':'O','P':'Ԁ','Q':'Ό','R':'ᴚ',
    'S':'S','T':'┴','U':'∩','V':'Λ','W':'M','X':'X','Y':'⅄','Z':'Z',
    '0':'0','1':'Ɩ','2':'ᄅ','3':'Ɛ','4':'ㄣ','5':'ϛ','6':'9','7':'ㄥ','8':'8','9':'6'}

def _apply_font(text: str, mapping: dict) -> str:
    return "".join(mapping.get(c, c) for c in text)
def _combining(text: str, comb: str) -> str:
    return "".join(c + comb for c in text if c != " ").replace(comb + " ", " ")

def generate_fonts(text: str) -> str:
    lines = ["🎨 <b>LUFFY FONT FORGE</b>", ""]
    for name, mp in _FONT_DEFS:
        lines.append(f"<b>{name}:</b>\n<code>{_apply_font(text, mp)}</code>")
    lines.append(f"<b>Small Caps:</b>\n<code>{_apply_font(text, _SMALLCAPS)}</code>")
    lines.append(f"<b>Superscript:</b>\n<code>{_apply_font(text, _SUPERSCRIPT)}</code>")
    lines.append(f"<b>Upside Down:</b>\n<code>{_apply_font(text, _FLIP)[::-1]}</code>")
    lines.append(f"<b>Strikethrough:</b>\n<code>{_combining(text, chr(0x0336))}</code>")
    lines.append(f"<b>Underline:</b>\n<code>{_combining(text, chr(0x0332))}</code>")
    lines.append(f"<b>Double Underline:</b>\n<code>{_combining(text, chr(0x0333))}</code>")
    lines.append(f"<b>Wavy:</b>\n<code>{_combining(text, chr(0x0330))}</code>")
    return "\n\n".join(lines)


def _tts_sync(text: str, lang: str = "en") -> bytes:
    if not _HAS_GTTS:
        raise RuntimeError("gtts not installed — pip install gTTS")
    tts = gTTS(text=text, lang=lang)
    buf = BytesIO(); tts.write_to_fp(buf); return buf.getvalue()


# ═══════════════════════════════════════════════════════════════
# 🖼️  MENU
# ═══════════════════════════════════════════════════════════════
async def send_menu(chat_id, msg, bot):
    menu = (
        """⸎❄️ 🍷 EDEN 𝐄ɴɢɪɴᴇ 🕸️✨
━━━━━━━━━━━━━━━━━━━━
𝐂ᴏᴍᴍᴀɴᴅ 𝐇ᴀɴᴅʟᴇʀ: ~
━━━━━━━━━━━━━━━━━━━━
[ 🕸️ 𝐆ᴄ 𝐋ᴏᴏᴘꜱ ]
• 𝐒ʟᴜᴛɴᴄ
• 𝐊ᴀɪᴅᴏɴᴄ
• 𝐍ᴄʙʟᴀꜱᴛ
• 𝐏ɪʟʟᴀ
• 𝐆ᴜʟᴀᴍ
• 𝐇ᴀꜱʏ
• 𝐋ᴜꜰꜰʏɢᴏᴅ
━━━━━━━━━━━━━━━━━━━━
[ 🌊 𝐋ᴜꜰꜰʏ 𝐍ᴄ — 𝐍ᴇᴡ ]
• 𝐁ᴏᴏᴍɴᴄ
• 𝐑ᴜʟᴇʀɴᴄ
• 𝐍ᴘᴄɴᴄ
• 𝐒ʟᴀᴠᴇɴᴄ
• 𝐗xхɴᴄ
━━━━━━━━━━━━━━━━━━━━
[ 🌷 𝐒ᴘᴇᴄɪᴀʟ 𝐍ᴄꜱ ]
• 𝐅ɪʟᴛᴇʀɴᴄ
• 𝐕ᴇɢᴇᴛᴀɢᴀᴡᴅ
• 𝐆ʟɪᴛᴄʜɴᴄ
• 𝐂ᴜᴛᴇɴᴄ
• 𝐍ᴄ1 ꜱᴇ 𝐍ᴄ20
━━━━━━━━━━━━━━━━━━━━
[ 🛑 𝐒ᴛᴏᴘ 𝐂ᴍᴅꜱ ]
• 𝐒ᴛᴏᴘ (ᴍᴀꜱᴛᴇʀ)
• 𝐙ᴇʀᴏ
• 𝐒ʜᴜᴛᴅᴏᴡɴ
• 𝐒ᴛᴏᴘᴀʟʟ
• 𝐏ᴀɴɪᴄ
• 𝐒ᴛᴏᴘɢᴇᴀʀ
• 𝐒ᴛᴏᴘꜱᴘᴀᴍ
• 𝐒ᴛᴏᴘꜱᴡ
• 𝐒ᴛᴏᴘɴᴄ
• 𝐒ᴘᴀᴍᴡᴀᴛᴄʜᴏꜰꜰ
• 𝐙ᴇʀᴏɢᴄɴᴄ
• 𝐅ʀᴇᴇᴢᴇꜱʟɪᴅᴇ
• 𝐙ᴇʀᴏꜱʟɪᴅᴇꜱᴘᴀᴍ
• 𝐒ᴘɪᴄ
• 𝐅ʀᴇᴇᴢᴇ (ᴍᴏᴅᴇꜱ / ᴀʟʟ)
━━━━━━━━━━━━━━━━━━━━
[ 🖤 𝐒ᴘᴀᴍ 𝐂ᴍᴅꜱ ]
• 𝐂ʜᴜᴅ
• 𝐒ᴘᴀᴍ
• 𝐆ᴇᴀʀꜱᴘᴀᴍ
• 𝐌ꜱɢ
• 𝐁ᴏᴛʜ
• 𝐁ʟᴀꜱᴛ
━━━━━━━━━━━━━━━━━━━━
[ 🎨 𝐅ᴜɴ 𝐒ᴛᴜꜰꜰ ]
• 𝐅 (ᴛᴇxᴛ)
• 𝐕 (ᴛᴇxᴛ)
• 𝐀ɪ (ᴘʀᴏᴍᴘᴛ)
━━━━━━━━━━━━━━━━━━━━
[ 🍃 𝐒ᴡɪᴘᴇ ]
• 𝐒ᴡɪᴘᴇ
• 𝐙ᴇʀᴏꜱᴡɪᴘᴇ
• 𝐏ꜰᴘʟᴏᴏᴘ
━━━━━━━━━━━━━━━━━━━━
[ 👁️ 𝐒ᴘᴀᴍᴡᴀᴛᴄʜ ]
• 𝐒ᴘᴀᴍᴡᴀᴛᴄʜʜ
━━━━━━━━━━━━━━━━━━━━
[ 🛡️ 𝐀ᴅᴍɪɴ & 𝐒ᴜᴅᴏ ]
• 𝐀ᴅᴍɪɴ
• 𝐀ᴅᴅꜱᴜᴅᴏ
• 𝐃ᴇʟꜱᴜᴅᴏ
• 𝐋ɪꜱᴛꜱᴜᴅᴏ
━━━━━━━━━━━━━━━━━━━━
[ ⛓️ 𝐆ᴇᴀʀꜱ ]
• 𝐌ʏɪᴅ
• 𝐏ɪɴɢ
• 𝐒ᴛᴀᴛᴜꜱ
• 𝐃ᴇʟᴀʏ
• 𝐀ʀ
• 𝐒ᴀʀ
• 𝐒ᴇᴛᴏᴠᴇʀᴘɪᴄ
• 𝐎ᴠᴇʀ
• 𝐌ᴇɴᴜᴘɪᴄ
• 𝐃ᴇᴛᴀɪʟꜱ (ʀᴇᴘʟʏ)
━━━━━━━━━━━━━━━━━━━━
“ 𝐎ɴʟʏ EDEN 𝐂ᴀɴ 𝐂ᴏɴᴛʀᴏʟ 🌷 ”
𝐁ʏ ~ EDEN 🤍

"""
    )
    guard = get_limiter(bot.id)
    pic   = MENU_MEDIA.get(chat_id)
    if pic:
        bio = BytesIO(pic); bio.name = "menu.jpg"
        r = await guard.send_photo(bot, chat_id, bio,
                                   caption=menu, parse_mode="HTML")
        if r is None:
            await guard.send_message(bot, chat_id, menu, parse_mode="HTML")
    else:
        await guard.send_message(bot, chat_id, menu, parse_mode="HTML")


async def send_denied(bot, chat_id, msg, guard):
    name = (msg.from_user.first_name or "PILLE") if msg.from_user else "PILLE"
    text = (
        "𝐘ᴏᴜ 𝐃ᴏɴ'ᴛ 𝐇ᴀᴠᴇ 𝐓ʜᴇ 𝐇ᴀᴋɪ 👉🏻 𝐒ᴀʏ: 𝐋ᴜғғʏ 𝐃𝐚𝐝𝐝ʏ\n"
        "<<⭕️>>\n"
        f"“ {fancy('LUFFY EMPIRE')} 🦁"
    )
    try:
        await guard.send_message(bot, chat_id, text, parse_mode="HTML",
                                 reply_to_message_id=msg.message_id)
    except Exception:
        await guard.send_message(bot, chat_id, text, parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════
# 🎯  ROUTER
# ═══════════════════════════════════════════════════════════════
async def route(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg: return

    chat    = update.effective_chat
    chat_id = chat.id if chat else None
    is_chan = bool(chat and chat.type == "channel")
    uid     = update.effective_user.id if update.effective_user else _channel_uid(update)
    guard   = get_limiter(ctx.bot.id)

    if update.effective_user:
        track_user(update.effective_user)
    if msg.reply_to_message:
        ru = _reply_user(msg)
        if ru: track_user(ru)

    if chat_id and uid and not is_chan and uid != ctx.bot.id:
        if chat_id in spamwatch_chats:
            st = spamwatch_chats[chat_id]
            if uid != st.get("owner_id") and _track_burst(chat_id, uid):
                await _trigger_spamwatch(chat_id, uid, msg.message_id)

    if not msg.text: return
    cmd, arg = parse_cmd(msg.text)
    if not cmd: return

    key = (chat_id, msg.message_id)
    if key in _handled: return
    _handled[key] = None
    if len(_handled) > _HANDLED_CAP: _handled.popitem(last=False)

    bot = ctx.bot

    # ─── public ───
    if cmd == "myid":
        who = uid if uid else "channel"
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"Your ID: {who}")),
            reply_to_message_id=msg.message_id); return
    if cmd == "ping":
        t0 = time.monotonic()
        m = await guard.send_message(bot, chat_id,
            prefixed(fancy("Pinging...")),
            reply_to_message_id=msg.message_id)
        if m:
            await guard._gate()
            try:
                await m.edit_text(prefixed(fancy(
                    f"Pong! {(time.monotonic()-t0)*1000:.0f} ms")))
            except Exception: pass
        return

    if cmd == "menu":
        if not is_authorized(uid, is_chan, chat_id):
            await send_denied(bot, chat_id, msg, guard); return
        await send_menu(chat_id, msg, bot); return

    if cmd == "console":
        if not is_authorized(uid, is_chan, chat_id):
            await send_denied(bot, chat_id, msg, guard); return
        console = (
            """⸎❄️ 🍷 ᴘᴀɪɴ 𝐂ᴏɴꜱᴏʟᴇ ⸎ 𝐇ɪᴅᴅᴇɴ ❄️✨
━━━━━━━━━━━━━━━━━━━━
𝐂ᴏᴍᴍᴀɴᴅ 𝐇ᴀɴᴅʟᴇʀ: ~
━━━━━━━━━━━━━━━━━━━━
[ 🌊 ᴘᴀɪɴ 𝐍ᴄ ]
• 𝐁ᴏᴏᴍɴᴄ  • 𝐑ᴜʟᴇʀɴᴄ
• 𝐍ᴘᴄɴᴄ  • 𝐒ʟᴀᴠᴇɴᴄ
• 𝐗xхɴᴄ
━━━━━━━━━━━━━━━━━━━━
[ 🕸️ 𝐎ʀɪɢɪɴᴀʟ 𝐍ᴄꜱ ]
• 𝐍ᴄ1 ꜱᴇ 𝐍ᴄ20
• 𝐒ʟᴜᴛɴᴄ  • 𝐊ᴀɪᴅᴏɴᴄ  • 𝐍ᴄʙʟᴀꜱᴛ
• 𝐏ɪʟʟᴀ  • 𝐆ᴜʟᴀᴍ  • 𝐇ᴀꜱʏ
• 𝐋ᴜꜰꜰʏɢᴏᴅ  • 𝐅ɪʟᴛᴇʀɴᴄ
• 𝐕ᴇɢᴇᴛᴀɢᴀᴡᴅ  • 𝐆ʟɪᴛᴄʜɴᴄ  • 𝐂ᴜᴛᴇɴᴄ
━━━━━━━━━━━━━━━━━━━━
[ 🛡️ 𝐆ᴄ / 𝐂ʜᴀɴɴᴇʟ 𝐂ᴏɴᴛʀᴏʟ ]
• 𝐇ʏᴘᴇʀ  • 𝐔ɴʜʏᴘᴇʀ
• 𝐒ᴇᴛɢᴄɴᴀᴍᴇ  • 𝐒ᴇᴛɢᴄᴘɪᴄ
• 𝐃ꜱ (ᴛᴇxᴛ)  • 𝐏ᴜʀɢᴇ (ʀᴇᴘʟʏ)
• 𝐌ᴀᴀᴄʜᴜᴅᴀᴏ (ᴛᴇxᴛ)
━━━━━━━━━━━━━━━━━━━━
[ 📢 𝐁ʀᴏᴀᴅᴄᴀꜱᴛ ]
• 𝐁ᴅᴄ (ᴛᴇxᴛ)
━━━━━━━━━━━━━━━━━━━━
[ ☢️ 𝐒ᴛᴏᴘ / 𝐊ɪʟʟ ]
• 𝐒ᴛᴏᴘ  • 𝐙ᴇʀᴏ  • 𝐒ʜᴜᴛᴅᴏᴡɴ
• 𝐒ᴛᴏᴘᴀʟʟ  • 𝐏ᴀɴɪᴄ
• 𝐒ᴛᴏᴘɢᴇᴀʀ  • 𝐒ᴛᴏᴘꜱᴘᴀᴍ
• 𝐒ᴛᴏᴘꜱᴡ  • 𝐒ᴛᴏᴘɴᴄ
• 𝐒ᴘᴀᴍᴡᴀᴛᴄʜᴏꜰꜰ
• 𝐅ʀᴇᴇᴢᴇ (ᴍᴏᴅᴇꜱ)
━━━━━━━━━━━━━━━━━━━━
[ 🎨 𝐅ᴜɴ ]
• 𝐅  • 𝐕  • 𝐀ɪ
━━━━━━━━━━━━━━━━━━━━
[ 🔍 𝐈ɴᴛᴇʟ ]
• 𝐃ᴇᴛᴀɪʟꜱ  • 𝐁ᴏᴛꜱ  • 𝐒ᴛᴀᴛᴜꜱ
━━━━━━━━━━━━━━━━━━━━
𝐁ʏ ~ 𝐋ᴜꜰꜰʏ 🤍
"""
        )
        await guard.send_message(bot, chat_id, console,
            parse_mode="HTML",
            reply_to_message_id=msg.message_id); return

    if cmd == "status":
        lines = [fancy("🕸️ LUFFY STATUS PANEL 🕸️"), "━━━━━━━━━━━━━━━━━━━"]
        for a in ALL_APPS:
            info = BOT_INFO.get(a.bot.id, {})
            g    = get_limiter(a.bot.id)
            lines.append(
                f"🎴 <b>#{info.get('no','?')}</b> · @{info.get('username','?')}\n"
                f"   ⚡ rate <b>{g.rate:.0f}/s</b> · 🕒 delay <b>{g.delay:.2f}s</b>")
        lines.append("━━━━━━━━━━━━━━━━━━━")
        lines.append(f"“ {fancy('Only LUFFY CAN Control')} 🌊")
        await guard.send_message(bot, chat_id, "\n".join(lines),
            parse_mode="HTML", reply_to_message_id=msg.message_id); return

    if cmd == "bots":
        if not ALL_APPS:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("No bots online.")),
                reply_to_message_id=msg.message_id); return
        lines = [fancy("🕸️ LUFFY BOT ARMY 🕸️"), "━━━━━━━━━━━━━━━━━━━"]
        now = time.monotonic()
        for a in ALL_APPS:
            info = BOT_INFO.get(a.bot.id, {})
            up = int(now - START_TS)
            h, m, s = up//3600, (up%3600)//60, up%60
            lines.append(
                f"🧿 <b>#{info.get('no','?')}</b> · @{info.get('username','?')}\n"
                f"   🆔 <code>{a.bot.id}</code>\n"
                f"   ⏱️ up {h}h {m}m {s}s")
        lines.append("━━━━━━━━━━━━━━━━━━━")
        lines.append(f"“ {fancy('NPC EMPIRE ')} 🦁")
        await guard.send_message(bot, chat_id, "\n".join(lines),
            parse_mode="HTML", reply_to_message_id=msg.message_id); return

    # ─── auth wall ───
    if not is_authorized(uid, is_chan, chat_id):
        await send_denied(bot, chat_id, msg, guard); return

    # ═══ FUN / INTEL ═══
    if cmd == "ai":
        prompt = arg.strip()
        if not prompt:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Usage: ~ai <prompt>")),
                reply_to_message_id=msg.message_id); return
        await guard.send_message(bot, chat_id,
            prefixed(fancy("🎨 Cooking… wait... 🔁🩵")),
            reply_to_message_id=msg.message_id)
        try:
            seed = random.randint(1, 999999)
            url  = (f"https://image.pollinations.ai/prompt/"
                    f"{quote_plus(prompt)}?width=1024&height=1024"
                    f"&nologo=true&seed={seed}")
            async with httpx.AsyncClient(timeout=90) as cl:
                r = await cl.get(url)
                if r.status_code in (429, 402, 403) or "quota" in r.text.lower():
                    raise RuntimeError("__AI_LIMIT__")
                r.raise_for_status()
                img = BytesIO(r.content); img.name = "ai.jpg"
            await guard.send_photo(bot, chat_id, img,
                caption=prefixed(fancy(f"✨ {prompt[:180]}")),
                reply_to_message_id=msg.message_id)
        except Exception as e:
            err = str(e)
            msg_txt = (fancy("🛑 AI IS OFF NOW TRY AGAIN LATER")
                       if ("__AI_LIMIT__" in err or "429" in err
                           or "rate limit" in err.lower()
                           or "quota" in err.lower()
                           or "exceed" in err.lower()
                           or "too many" in err.lower())
                       else fancy(f"❌ AI failed: {err[:80]}"))
            await guard.send_message(bot, chat_id, prefixed(msg_txt),
                reply_to_message_id=msg.message_id)
        return

    if cmd == "f":
        raw = arg.strip()
        if not raw:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Usage: ~f <text>")),
                reply_to_message_id=msg.message_id); return
        if len(raw) > 60: raw = raw[:60]
        try:
            await guard.send_message(bot, chat_id, generate_fonts(raw),
                parse_mode="HTML", reply_to_message_id=msg.message_id)
        except Exception as e:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"❌ {str(e)[:80]}")),
                reply_to_message_id=msg.message_id)
        return

    if cmd == "v":
        raw = arg.strip()
        if not raw:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Usage: ~v <text>")),
                reply_to_message_id=msg.message_id); return
        if len(raw) > 200: raw = raw[:200]
        await guard.send_message(bot, chat_id,
            prefixed(fancy("🗣️ cooking voice…")),
            reply_to_message_id=msg.message_id)
        try:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, _tts_sync, raw)
            bio  = BytesIO(data); bio.name = "voice.mp3"
            await guard.send_voice(bot, chat_id, bio,
                caption=prefixed(fancy(raw[:120])),
                reply_to_message_id=msg.message_id)
        except Exception as e:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"❌ TTS failed: {str(e)[:80]}")),
                reply_to_message_id=msg.message_id)
        return

    # ═══ ENHANCED DETAILS — FULL HISTORY ═══
    if cmd == "details":
        ru = _reply_user(msg)
        if not ru:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to a user's message.")),
                reply_to_message_id=msg.message_id); return
        u = ru
        uid_s = str(u.id)
        hist = USER_HIST.get(uid_s, {})

        names     = hist.get("names", []) or []
        usernames = hist.get("usernames", []) or []
        first_s   = hist.get("first_seen", "—")
        last_s    = hist.get("last_seen", "—")

        current_name = (getattr(u, "first_name", None)
                        or getattr(u, "title", "") or "—")
        if getattr(u, "last_name", None):
            current_name = (current_name + " " + u.last_name).strip()
        current_un = getattr(u, "username", None)

        bio = "—"
        try:
            full = await bot.get_chat(u.id)
            bio = getattr(full, "bio", None) or "—"
        except Exception: pass

        is_bot  = "🤖 BOT" if getattr(u, "is_bot", False) else "🧑 HUMAN"
        premium = "⭐ YES" if getattr(u, "is_premium", False) else "NO"
        lang    = getattr(u, "language_code", None) or "—"

        # Build full history blocks
        if names:
            names_block = "\n".join(f"  • {n}" for n in names[-15:])
        else:
            names_block = f"  • {current_name}"

        if usernames:
            unames_block = "\n".join(f"  • @{x}" for x in usernames[-15:])
        else:
            unames_block = f"  • @{current_un}" if current_un else "  • —"

        lines = [
            fancy("🔍 FULL USER INTEL"),
            "━━━━━━━━━━━━━━━━━━━",
            f"🆔 <code>{u.id}</code>",
            f"👤 <b>{current_name}</b>",
            (f"🏷️ @{current_un}" if current_un else "🏷️ —"),
            f"🧬 {is_bot}   ⭐ {premium}   🌐 {lang}",
            "━━━━━━━━━━━━━━━━━━━",
            f"📛 <b>Names used ({len(names)}):</b>",
            names_block,
            "",
            f"🏷️ <b>Usernames used ({len(usernames)}):</b>",
            unames_block,
            "━━━━━━━━━━━━━━━━━━━",
            f"📅 <b>First seen:</b> {first_s}",
            f"🕒 <b>Last seen:</b>  {last_s}",
            f"📝 <b>Bio:</b> {bio}",
            "☎️ Phone: <i>NULL</i>",
            "📍 Address: <i>NULL</i>",
        ]
        await guard.send_message(bot, chat_id, "\n".join(lines),
            parse_mode="HTML", reply_to_message_id=msg.message_id); return

    if cmd == "text":
        ru = _reply_user(msg)
        if not ru:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to a user.")),
                reply_to_message_id=msg.message_id); return
        nm = (getattr(ru, "first_name", None) or getattr(ru, "title", "") or str(ru.id))
        textS.setdefault(chat_id, {})[ru.id] = nm
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"🎯 Locked: {nm} ({ru.id})")),
            reply_to_message_id=msg.message_id); return

    if cmd == "textlist":
        tgts = textS.get(chat_id, {})
        if not tgts:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("No texts yet.")),
                reply_to_message_id=msg.message_id); return
        lines = [fancy("🎯 text LIST")]
        for i, (tid, nm) in enumerate(tgts.items(), 1):
            lines.append(f"{i}. {nm}  —  <code>{tid}</code>")
        await guard.send_message(bot, chat_id, "\n".join(lines),
            parse_mode="HTML", reply_to_message_id=msg.message_id); return

    # ═══ GC / CHANNEL CONTROL ═══
    if cmd == "hyper":
        if HYPER.get(chat_id, {}).get("on"):
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Already hyper 🔒")),
                reply_to_message_id=msg.message_id); return
        try:
            ci = await bot.get_chat(chat_id)
            try:
                raw_prev = ci.permissions.to_dict() if ci.permissions else None
            except Exception:
                raw_prev = None
            prev = ({k: bool(v) for k, v in raw_prev.items() if v is not None}
                    if isinstance(raw_prev, dict) else None)
            HYPER[chat_id] = {"on": True, "prev": prev}
            await bot.set_chat_permissions(chat_id, ChatPermissions(
                can_send_messages=False, can_send_audios=False,
                can_send_documents=False, can_send_photos=False,
                can_send_videos=False, can_send_video_notes=False,
                can_send_voice_notes=False, can_send_polls=False,
                can_send_other_messages=False, can_add_web_page_previews=False,
                can_change_info=False, can_invite_users=False,
                can_pin_messages=False))
            await guard.send_message(bot, chat_id,
                prefixed(fancy("🔒 HYPER LOCKED")),
                reply_to_message_id=msg.message_id)
        except Exception as e:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"❌ {str(e)[:80]}")),
                reply_to_message_id=msg.message_id)
        return

    if cmd == "unhyper":
        if not HYPER.get(chat_id, {}).get("on"):
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Not locked.")),
                reply_to_message_id=msg.message_id); return
        prev = HYPER.get(chat_id, {}).get("prev")
        try:
            valid_keys = set(ChatPermissions.__slots__) \
                if hasattr(ChatPermissions, "__slots__") \
                else set(ChatPermissions().__dict__.keys())
        except Exception:
            valid_keys = {"can_send_messages","can_send_audios",
                "can_send_documents","can_send_photos","can_send_videos",
                "can_send_video_notes","can_send_voice_notes","can_send_polls",
                "can_send_other_messages","can_add_web_page_previews",
                "can_change_info","can_invite_users","can_pin_messages",
                "can_manage_topics"}
        sanitized = {k: v for k, v in (prev or {}).items()
                     if k in valid_keys and isinstance(v, bool)}
        restored = False
        if sanitized:
            try:
                await bot.set_chat_permissions(chat_id, ChatPermissions(**sanitized))
                restored = True
            except Exception: pass
        if not restored:
            try:
                await bot.set_chat_permissions(chat_id, ChatPermissions(
                    can_send_messages=True, can_send_audios=True,
                    can_send_documents=True, can_send_photos=True,
                    can_send_videos=True, can_send_video_notes=True,
                    can_send_voice_notes=True, can_send_polls=True,
                    can_send_other_messages=True, can_add_web_page_previews=True,
                    can_change_info=True, can_invite_users=True,
                    can_pin_messages=True))
            except Exception as e:
                await guard.send_message(bot, chat_id,
                    prefixed(fancy(f"❌ unlock failed: {str(e)[:100]}")),
                    reply_to_message_id=msg.message_id); return
        HYPER.pop(chat_id, None)
        await guard.send_message(bot, chat_id,
            prefixed(fancy("🔓 UNLOCKED ✅")),
            reply_to_message_id=msg.message_id)
        return

    if cmd in ("chup", "mute"):
        try:
            await bot.set_chat_permissions(chat_id, ChatPermissions(
                can_send_messages=False, can_send_audios=False,
                can_send_documents=False, can_send_photos=False,
                can_send_videos=False, can_send_video_notes=False,
                can_send_voice_notes=False, can_send_polls=False,
                can_send_other_messages=False, can_add_web_page_previews=False))
            MUTED[chat_id] = True
            await guard.send_message(bot, chat_id,
                prefixed(fancy("🤐 MUTED — chup ho jao sab 🩸")),
                reply_to_message_id=msg.message_id)
        except Exception as e:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"❌ {str(e)[:80]}")),
                reply_to_message_id=msg.message_id)
        return

    if cmd in ("bol", "unmute"):
        try:
            await bot.set_chat_permissions(chat_id, ChatPermissions(
                can_send_messages=True, can_send_audios=True,
                can_send_documents=True, can_send_photos=True,
                can_send_videos=True, can_send_video_notes=True,
                can_send_voice_notes=True, can_send_polls=True,
                can_send_other_messages=True, can_add_web_page_previews=True))
            MUTED.pop(chat_id, None)
            await guard.send_message(bot, chat_id,
                prefixed(fancy("🔊 UNMUTED — bol lo ab 🌊")),
                reply_to_message_id=msg.message_id)
        except Exception as e:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"❌ {str(e)[:80]}")),
                reply_to_message_id=msg.message_id)
        return

    if cmd == "ds":
        raw = arg.strip()
        if not raw:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Usage: ~ds <text>")),
                reply_to_message_id=msg.message_id); return
        await _kill_kinds(chat_id, {"desc"})
        DESC_LOOP[chat_id] = {"text": raw}
        for app in ALL_APPS:
            t = asyncio.create_task(
                desc_loop(app.bot, app.bot.id, chat_id, raw))
            add_task(chat_id, t, kind="desc")
            await asyncio.sleep(0.001)
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"✏️ Desc loop ON — {raw[:40]}")),
            reply_to_message_id=msg.message_id)
        return

    if cmd in ("stopds", "dsstop"):
        killed = await _kill_kinds(chat_id, {"desc"})
        DESC_LOOP.pop(chat_id, None)
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"Desc loop stopped (killed {killed})")),
            reply_to_message_id=msg.message_id)
        return

    if cmd == "setgcname":
        newname = arg.strip()
        if not newname:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Usage: ~setgcname <text>")),
                reply_to_message_id=msg.message_id); return
        try:
            await bot.set_chat_title(chat_id, newname[:128])
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"✅ name → {newname[:60]}")),
                reply_to_message_id=msg.message_id)
        except Exception as e:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"❌ {str(e)[:80]}")),
                reply_to_message_id=msg.message_id)
        return

    if cmd == "setgcpic":
        r = msg.reply_to_message
        if not r or not r.photo:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to a photo.")),
                reply_to_message_id=msg.message_id); return
        try:
            f    = await bot.get_file(r.photo[-1].file_id)
            data = await f.download_as_bytearray()
            bio  = BytesIO(bytes(data)); bio.name = "gc.jpg"
            await bot.set_chat_photo(chat_id, photo=bio)
            await guard.send_message(bot, chat_id,
                prefixed(fancy("✅ pic changed")),
                reply_to_message_id=msg.message_id)
        except Exception as e:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"❌ {str(e)[:80]}")),
                reply_to_message_id=msg.message_id)
        return

    if cmd == "setoverpic":
        r = msg.reply_to_message
        if not r or not r.photo:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to a photo.")),
                reply_to_message_id=msg.message_id); return
        try:
            f    = await bot.get_file(r.photo[-1].file_id)
            data = await f.download_as_bytearray()
            OVER_MEDIA[chat_id] = bytes(data)
            await guard.send_message(bot, chat_id,
                prefixed(fancy("✅ Over-pic set")),
                reply_to_message_id=msg.message_id)
        except Exception as e:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"❌ {str(e)[:80]}")),
                reply_to_message_id=msg.message_id)
        return

    if cmd == "menupic":
        r = msg.reply_to_message
        if not r or not r.photo:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to a photo.")),
                reply_to_message_id=msg.message_id); return
        try:
            f    = await bot.get_file(r.photo[-1].file_id)
            data = await f.download_as_bytearray()
            MENU_MEDIA[chat_id] = bytes(data)
            await guard.send_message(bot, chat_id,
                prefixed(fancy("✅ Menu-pic set")),
                reply_to_message_id=msg.message_id)
        except Exception as e:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"❌ {str(e)[:80]}")),
                reply_to_message_id=msg.message_id)
        return

    if cmd == "admin":
        if is_chan:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Channels me promote nahi hota boss man.")),
                reply_to_message_id=msg.message_id); return
        await guard.send_message(bot, chat_id,
            prefixed(fancy("Promoting all bots...")),
            reply_to_message_id=msg.message_id)
        results = await promote_all_bots(chat_id)
        await guard.send_message(bot, chat_id,
            prefixed(fancy("Admin results:") + "\n" + "\n".join(results)),
            reply_to_message_id=msg.message_id); return

    if cmd == "bdc":
        raw = arg.strip()
        if not raw:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Usage: ~bdc <text>")),
                reply_to_message_id=msg.message_id); return
        await guard.send_message(bot, chat_id,
            prefixed(fancy("📢 broadcasting…")),
            reply_to_message_id=msg.message_id)
        sent, failed = 0, 0
        seen = set()
        for app in ALL_APPS:
            b = app.bot
            for cid in list(_known_chats()):
                if cid in seen: continue
                seen.add(cid)
                try:
                    await get_limiter(b.id).send_message(
                        b, cid, prefixed(fancy(raw[:400])))
                    sent += 1
                except Exception:
                    failed += 1
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"📢 done · sent {sent} · failed {failed}")),
            reply_to_message_id=msg.message_id)
        return

    if cmd == "purge":
        r = msg.reply_to_message
        if not r:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to the first msg you want purged.")),
                reply_to_message_id=msg.message_id); return
        start_id = r.message_id
        end_id   = msg.message_id
        ok = 0
        for mid in range(start_id, end_id + 1):
            try:
                await bot.delete_message(chat_id, mid); ok += 1
            except Exception: pass
        try: await bot.delete_message(chat_id, msg.message_id)
        except Exception: pass
        try:
            m = await bot.send_message(chat_id, prefixed(fancy(f"🧹 purged {ok} msgs")))
            await asyncio.sleep(3)
            await bot.delete_message(chat_id, m.message_id)
        except Exception: pass
        return

    if cmd in ("maachudao", "machudao"):
        raw = arg.strip() or "MACHUDAO"
        for app in ALL_APPS:
            try:
                await app.bot.send_message(chat_id,
                    prefixed(fancy(f"{raw} 🩸 all bots leaving…")))
            except Exception: pass
        await asyncio.sleep(1.2)
        left, failed = 0, 0
        for app in ALL_APPS:
            try:
                await app.bot.leave_chat(chat_id); left += 1
            except Exception:
                failed += 1
        log.info(f"maachudao: left={left} failed={failed} chat={chat_id}")
        return

    # ═══ SPAMWATCH ═══
    if cmd == "spamwatchh":
        if is_chan:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Channels me spamwatch nahi chalta.")),
                reply_to_message_id=msg.message_id); return
        if chat_id in spamwatch_chats:
            cancel_tasks(chat_id, {"spamwatch_counter"})
            spamwatch_chats.pop(chat_id, None)
            _sw_bursts.pop(chat_id, None)
            await guard.send_message(bot, chat_id,
                prefixed(fancy("SpamWatch OFF 🛑")),
                reply_to_message_id=msg.message_id)
        else:
            spamwatch_chats[chat_id] = {
                "owner_id": uid, "last_trigger": 0.0,
                "active_rival": None, "counter_on": False}
            await guard.send_message(bot, chat_id,
                prefixed(fancy("SpamWatch ON 👁️")),
                reply_to_message_id=msg.message_id)
        return

    if cmd in ("spamwatchoff", "stopspamwatch"):
        spamwatch_chats.pop(chat_id, None)
        _sw_bursts.pop(chat_id, None)
        killed = await _kill_kinds(chat_id, {"spamwatch_counter"})
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"SpamWatch HARD OFF 🛑  (killed {killed})")),
            reply_to_message_id=msg.message_id); return

    # ═══ MASTER STOP — KILLS EVERYTHING ═══
    if cmd == "stop":
        stats = nuke_chat(chat_id, wipe_state=True)
        cancelled = 0
        for t in list(TASKS.get(chat_id, [])):
            try: t.cancel(); cancelled += 1
            except Exception: pass
        TASKS[chat_id] = []
        await guard.send_message(bot, chat_id,
            prefixed(fancy(
                f"🛑 MASTER STOP — SAB KUCH BAND\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"tasks killed : {stats['tasks_killed']}\n"
                f"swipe was on : {stats['swipe_was_on']}\n"
                f"state wiped  : YES\n"
                f"chat reset   : {chat_id}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"ab kuch nahi chalega 💀")),
            reply_to_message_id=msg.message_id)
        return

    # ═══ STOP CMDS ═══
    if cmd in ("stopgear", "sgearspam", "stopgearspam"):
        killed = await _kill_kinds(chat_id, {"gearspam"})
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"GearSpam stopped ❄️  (killed {killed})")),
            reply_to_message_id=msg.message_id); return

    if cmd in ("stopspam", "sspam2", "sspam"):
        killed = await _kill_kinds(chat_id, SPAM_KINDS)
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"Spam family stopped 🔥  (killed {killed})")),
            reply_to_message_id=msg.message_id); return

    if cmd in ("stopsw", "stopcounter"):
        killed = await _kill_kinds(chat_id, {"spamwatch_counter"})
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"Counter loop killed 👁️  (killed {killed})")),
            reply_to_message_id=msg.message_id); return

    if cmd in ("stopnc", "stopallnc", "zerogcnc", "zerogc"):
        killed = await _kill_kinds(chat_id, NC_KINDS)
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"All NC/title loops stopped 🕸️  (killed {killed})")),
            reply_to_message_id=msg.message_id); return

    if cmd in ("shutdown", "stopall", "panic"):
        stats = nuke_chat(chat_id, wipe_state=True)
        await guard.send_message(bot, chat_id,
            prefixed(fancy(
                f"SHUTDOWN DROPPED \n"
                f"tasks killed : {stats['tasks_killed']}\n"
                f"swipe was on : {stats['swipe_was_on']}\n"
                f"state wiped  : YES")),
            reply_to_message_id=msg.message_id)
        return

    if cmd == "zero":
        stats = nuke_chat(chat_id, wipe_state=False)
        await guard.send_message(bot, chat_id,
            prefixed(fancy(
                f"💀 ALL TASKS KILLED  ({stats['tasks_killed']})\n"
                f"LUFFY PANNEL")),
            reply_to_message_id=msg.message_id)
        return

    if cmd == "freeze":
        raw = (arg or "").strip()
        if not raw:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Usage: ~freeze <mode1,mode2,...>")),
                reply_to_message_id=msg.message_id); return
        kinds = {k.strip().lower() for k in raw.split(",") if k.strip()}
        if "all" in kinds or "*" in kinds:
            kinds = set(ALL_LOOP_KINDS)
        killed = await _kill_kinds(chat_id, kinds)
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"Frozen {sorted(kinds)}  (killed {killed})")),
            reply_to_message_id=msg.message_id)
        return

    if cmd == "freezeslide":
        killed = await _kill_kinds(chat_id, {"swipe"})
        SWIPE_ON[chat_id] = False
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"Slide stopped ✦  (killed {killed})")),
            reply_to_message_id=msg.message_id)
        return

    if cmd == "zeroslidespam":
        killed = await _kill_kinds(chat_id, {"swipe","spam","gearspam","chud"})
        SWIPE_ON[chat_id] = False
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"Slide+Spam stopped ✦  (killed {killed})")),
            reply_to_message_id=msg.message_id)
        return

    if cmd in ("spic", "stopspic"):
        killed = await _kill_kinds(chat_id, {"pfp"})
        photo_pool.clear()
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"PFP stopped ✦  (killed {killed})")),
            reply_to_message_id=msg.message_id)
        return

    # ═══ GEARS ═══
    if cmd == "delay":
        raw = arg.strip()
        if not raw:
            cur = get_delay(chat_id)
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"Current: {cur:.2f}s | Usage: ~delay <sec>")),
                reply_to_message_id=msg.message_id); return
        try: val = float(raw)
        except ValueError:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("❌ Use number e.g. ~delay 0.1")),
                reply_to_message_id=msg.message_id); return
        val = max(0.0, min(60.0, val))
        CHAT_DELAY[chat_id] = val; save_delays()
        await guard.send_message(bot, chat_id,
            prefixed(fancy("Delay OFF ⚡" if val == 0 else f"Delay: {val:.2f}s ✅")),
            reply_to_message_id=msg.message_id)
        return

    if cmd in ("autopin", "autopinon"):
        AUTOPIN[chat_id] = True
        await guard.send_message(bot, chat_id,
            prefixed(fancy("📌 autopin ON")),
            reply_to_message_id=msg.message_id); return
    if cmd in ("noautopin", "autopinoff"):
        AUTOPIN[chat_id] = False
        await guard.send_message(bot, chat_id,
            prefixed(fancy("📌 autopin OFF")),
            reply_to_message_id=msg.message_id); return

    # ═══ LOOP STARTERS ═══
    if cmd in TITLE_MODES and cmd in MODE_MAP:
        if not arg:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"Usage: ~{cmd} <text>")),
                reply_to_message_id=msg.message_id); return
        for app in ALL_APPS:
            t = asyncio.create_task(
                bot_loop(app.bot, app.bot.id, chat_id, arg, cmd, msg.message_id))
            add_task(chat_id, t, kind=cmd)
            await asyncio.sleep(0.001)
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"{cmd} started 🕸️")),
            reply_to_message_id=msg.message_id)
        return

    if cmd in ("spam","gearspam","msg","both","blast"):
        if not arg:
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"Usage: ~{cmd} <text>")),
                reply_to_message_id=msg.message_id); return
        for app in ALL_APPS:
            t = asyncio.create_task(
                bot_loop(app.bot, app.bot.id, chat_id, arg, cmd, msg.message_id))
            add_task(chat_id, t, kind=cmd)
            await asyncio.sleep(0.001)
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"{cmd} started 🔥")),
            reply_to_message_id=msg.message_id)
        return

    if cmd == "chud":
        ru = _reply_user(msg)
        if not ru:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to a user.")),
                reply_to_message_id=msg.message_id); return
        CHUD_TEXT[chat_id] = {"text": ru.id}
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"Chud → {ru.id}")),
            reply_to_message_id=msg.message_id); return

    if cmd == "ar":
        emoji = (arg or "🤣").strip()
        ru = _reply_user(msg)
        if ru:
            AR_text[chat_id] = {"text": ru.id, "emoji": emoji}
            save_ar()
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"🎯 AR ON {emoji} → {ru.id} (permanent)")),
                reply_to_message_id=msg.message_id)
        else:
            AR_text[chat_id] = {"text": "__ALL__", "emoji": emoji}
            save_ar()
            await guard.send_message(bot, chat_id,
                prefixed(fancy(f"🎯 AR ON {emoji} → EVERYONE (permanent)")),
                reply_to_message_id=msg.message_id)
        return

    if cmd == "sar":
        AR_text.pop(chat_id, None); save_ar()
        await guard.send_message(bot, chat_id,
            prefixed(fancy("AR OFF.")),
            reply_to_message_id=msg.message_id); return

    if cmd == "swipe":
        r = msg.reply_to_message
        if not r:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to a msg.")),
                reply_to_message_id=msg.message_id); return
        text = arg.strip() if arg.strip() else (r.text or r.caption or "")
        if not text:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("No text to swipe.")),
                reply_to_message_id=msg.message_id); return
        cancel_tasks(chat_id, {"swipe"})
        SWIPE_MSG[chat_id] = text
        SWIPE_SRC[chat_id] = r.message_id
        SWIPE_ON[chat_id]  = True
        for app in ALL_APPS:
            t = asyncio.create_task(
                swipe_loop(app.bot, app.bot.id, chat_id, text, r.message_id))
            add_task(chat_id, t, kind="swipe")
            await asyncio.sleep(0.001)
        await guard.send_message(bot, chat_id,
            prefixed(fancy("Swipe ON 🔁")),
            reply_to_message_id=msg.message_id); return

    if cmd == "zeroswipe":
        SWIPE_ON[chat_id] = False
        cancel_tasks(chat_id, {"swipe"})
        await guard.send_message(bot, chat_id,
            prefixed(fancy("Swipe OFF.")),
            reply_to_message_id=msg.message_id); return

    if cmd == "pfploop":
        r = msg.reply_to_message
        if not r or not r.photo:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to a photo.")),
                reply_to_message_id=msg.message_id); return
        f    = await bot.get_file(r.photo[-1].file_id)
        data = await f.download_as_bytearray()
        photo_pool.clear(); photo_pool.append(bytes(data))
        for app in ALL_APPS:
            t = asyncio.create_task(photo_loop(app.bot, app.bot.id, chat_id))
            add_task(chat_id, t, kind="pfp")
            await asyncio.sleep(0.001)
        await guard.send_message(bot, chat_id,
            prefixed(fancy("PFP loop ON 🖼️")),
            reply_to_message_id=msg.message_id); return

    if cmd == "over":
        cancel_tasks(chat_id, None)
        gc_name = "UNKNOWN"
        try:
            ci = await bot.get_chat(chat_id)
            gc_name = ci.title or getattr(ci, "full_name", None) or "UNKNOWN"
        except Exception: pass
        now = datetime.now(IST)
        time_str = now.strftime("%I:%M:%S %p").lstrip("0")
        date_str = now.strftime("%d-%m-%Y")
        day_str  = now.strftime("%A")
        text_nm = arg.strip() if arg and arg.strip() else "UNKNOWN"
        by_name   = (update.effective_user.first_name if update.effective_user
                     else (chat.title if chat else "Channel"))
        caption = (
            f"⸎❄️ <b>{text_nm.upper()} IS PILLE KA GAME OVER</b>\n\n"
            f"⏰ <b>TIME :</b> {time_str}\n"
            f"💬 <b>GC :</b> {gc_name}\n"
            f"📅 <b>DATE :</b> {date_str}  |  {day_str}\n\n"
            f"🎯 <b>GAME OVER BY {by_name}</b>")
        pic = OVER_MEDIA.get(chat_id)
        if pic:
            bio = BytesIO(pic); bio.name = "over.jpg"
            r = await guard.send_photo(bot, chat_id, bio,
                                       caption=caption, parse_mode="HTML")
            if r is None:
                await guard.send_message(bot, chat_id, caption, parse_mode="HTML")
        else:
            try:
                async with httpx.AsyncClient(timeout=60) as cl:
                    vr = await cl.get(DEFAULT_GAMEOVER_VIDEO_URL)
                    vr.raise_for_status()
                    vid = BytesIO(vr.content); vid.name = "over.mp4"
                await guard.send_video(bot, chat_id, vid,
                                       caption=caption, parse_mode="HTML")
            except Exception:
                await guard.send_message(bot, chat_id, caption, parse_mode="HTML")
        return

    # ═══ SUDO ═══
    if cmd == "addsudo":
        ru = _reply_user(msg)
        if not ru:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to a user.")),
                reply_to_message_id=msg.message_id); return
        SUDO_USERS.add(ru.id); save_sudo()
        await guard.send_message(bot, chat_id,
            prefixed(fancy(f"Added {ru.id}")),
            reply_to_message_id=msg.message_id); return

    if cmd == "delsudo":
        ru = _reply_user(msg)
        if not ru:
            await guard.send_message(bot, chat_id,
                prefixed(fancy("Reply to a user.")),
                reply_to_message_id=msg.message_id); return
        SUDO_USERS.discard(ru.id); save_sudo()
        await guard.send_message(bot, chat_id,
            prefixed(fancy("Removed.")),
            reply_to_message_id=msg.message_id); return

    if cmd == "listsudo":
        txt = "\n".join(map(str, SUDO_USERS)) or fancy("No sudo.")
        await guard.send_message(bot, chat_id,
            prefixed(fancy("Sudo:") + "\n" + txt),
            reply_to_message_id=msg.message_id); return


# ═══════════════════════════════════════════════════════════════
# 📡  KNOWN CHATS TRACKER
# ═══════════════════════════════════════════════════════════════
KNOWN_CHATS: set = set()

def _known_chats():
    return KNOWN_CHATS


# ═══════════════════════════════════════════════════════════════
# 📩  NON-COMMAND HANDLER
# ═══════════════════════════════════════════════════════════════
CHUD_POOL = [
    "{t} Tᴇʀɪ Dᴀᴅɪ ᴋ ᴄʜᴍᴜᴛ ᴍᴀɪ ᴛᴀɴɢ ᴀᴛᴋᴀ ᴅᴜɴɢᴀ ғɪʀ ᴛᴇʀʏ ᴅᴀᴅᴜ sᴜsᴜ ᴋᴀɪsᴀ ᴋʀᴇɢɪ😍?",
    "{t} ᴛᴇʀʏ ᴍᴍʏ ᴋ ᴄʜᴜᴛᴀᴅᴏ ᴍᴀɪ 𝐃ɪɴᴏsᴀᴜʀ ᴋɪ ᴘᴏᴛʏʏ😁",
    "{t} ᴍᴀᴊᴅᴜʀɪ ᴋʀᴇɢᴀ ɢᴀʀᴇᴇʙ ᴛᴇʀʏ ᴍᴍʏ ᴋɪ ᴛᴀɴɢ ᴜᴛʜᴀᴋᴇ👻 ᴄʜᴜᴛ ᴍᴀᴊ ғɪᴋᴀʀɪ ᴊᴀʟᴀ ᴅᴜɴɢᴀ🙈",
    "{t} ᴇᴋ ʙᴀᴀᴛ ʙᴛᴀᴜ ᴛᴇʀᴀ ᴘᴀᴘᴀ ᴛᴇʀʏ ᴍᴍʏ ᴋᴏ ᴍᴇʀsᴀ ᴄʜᴜᴅᴠᴀ ᴋʀ ɢʜᴀʀ ᴄʜᴀʟᴀᴛᴇ ᴇʏ🤣👻",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋ ᴄʜᴜᴛᴀᴅ ᴘᴀʀ ᴊᴏ ᴘʜᴜɴsɪ ʜᴀ ᴜsᴋᴏ👻 ʟᴀᴀᴛ ᴍᴀʀᴋᴀ ᴘʜᴏᴅ ᴅᴜ ᴄʏ?",
    "{t} Tᴇʀʏ ᴍᴍʏ ᴋᴀ england ᴡᴀʟᴇ ʙᴜs ᴍᴀɪ ɢᴀɴɢ ʙᴀɴɢ ᴋʀᴋᴇ ᴋʜɪᴅᴋɪ sᴀ ғᴇᴋ ᴅᴇɴɢᴇ😭🥺",
    "{t} ᴋᴀʟɪ ᴋᴜᴛᴛɪ ᴋɪ ᴄʜᴜᴛ sᴀ ɴɪᴋʟᴀ ᴋᴜᴛᴛᴀ ᴋᴀ ᴘɪʟʟᴀ👻 ᴛᴇʀʏ ᴍᴀᴀ ʜᴀᴄᴋʟᴀ ᴋʀ ᴍᴀʀ ᴊᴀʏᴇ🤣",
    "{t} ᴊʜᴀᴛᴜ ᴛᴇʀʏ ᴀᴜᴋᴀᴛ ʜᴀ? 𝐄Sᴘᴀᴅᴀ 𝐖ᴀʟᴏ sᴀ ʟᴀᴅɴᴇ ᴋɪ? Tᴇʀʏ ᴍᴍʏ ᴋɪ ᴘᴜsʏʏ ᴘʀ ᴀʙᴅᴜʟ ᴋɪ ᴄʜᴀᴘᴀʟ ᴍᴀʀᴅᴜɴɢᴀ😁🍃",
    "{t} ᴛᴇʀʏ ᴍᴍʏ ᴋᴏ 𝐋ᴜꜰꜰʏ ᴋ ᴀʟᴀᴠᴀ ᴋᴏɪ ᴏʀ ᴄʜᴏᴅ sᴀᴋᴛᴀ ᴇʏ ᴋᴛᴀ?😁",
    "{t} sᴜᴀʀ ᴛᴇʀʏ ᴍᴍʏ ᴋɪ ᴄʜᴜᴛ ᴋᴀɪsᴀ ʟᴀᴀᴅᴋʜᴀᴅᴀɪ?👻 Tᴇʀᴀ 𝐋ᴜꜰꜰʏ𖤍 Pᴀᴘᴀ ᴋᴀ ʟᴜɴ ᴅᴇᴋʜ ᴋʀ??😍",
    "{t} ᴛᴇʀɪ ᴅᴀᴅɪ ᴋᴀ ʙʜᴏsᴅᴀ ᴍᴀ 𝐒ʟᴀᴛᴇ ᴋɪ ᴍɪssɪʟᴇ ᴅᴀʟᴋᴇ ᴜᴅᴀ ᴅᴜɴɢᴀ😍",
    "{t} ᴛᴇʀʏ ᴍᴍʏ ᴋᴏ miya ᴋ sᴀᴛʜ ᴄʜᴏᴅᴇɢᴀᴀ🙈",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴊᴀʙ ᴛʀᴀɪɴ ᴍᴀɪ sᴏʏᴇɢɪ ᴛᴀʙ ᴜsᴋɪ ᴘᴀɴᴛʏ ᴜᴛᴀʀ ᴋʀ sᴜᴘ sᴜᴘ ᴋʀᴅᴜɴɢᴀ😍🦈🦈🦈",
    "{t} ᴛᴇʀʏ ᴅᴀᴅɪ ᴋ ᴄʜᴜᴛᴀᴅ ᴍᴀ ᴀᴀᴍ ᴋᴀ ᴛʀᴇᴇ ʟɢᴀᴋᴇ 𝐋ᴜɴ ғᴇᴋ ᴍʀ ᴍᴀʀᴋᴇ ᴛᴏʀᴜɴɢᴀ😘🤩",
    "{t} ᴛᴇʀɪ ᴍᴍʏ 𝐋ᴜꜰꜰʏ ᴋ ᴛᴀᴛᴛᴇ ᴋ ɴɪᴄʜᴇ 👻👻 ᴍᴀsʟɪ ɢʏɪ ᴀᴀʙ ᴛᴇʀᴀ ᴘᴀᴘᴀ ʀᴏʏᴇɢᴀ😘",
    "{t} ᴛᴇʀɪ ᴋᴀʟᴀ ᴄʜᴜᴛᴀᴅ ᴡᴀʟɪ ʙʜᴇɴ ᴋ ɢᴀɴᴅ ᴍᴀɪ👻 ᴊᴀᴅᴜɪ ᴄʜᴀᴅɪ ᴅᴀʟᴅᴜɴɢᴀ😈😈😈",
    "TERI BRHEN KI KALI BURR ME THOOK DOYA AB CHAAT JAA USE 👽",
    "{t} ᴋɪ ᴍᴀᴀ ʜᴏʀɴᴇʏ ʜᴏ ᴋʀ ᴀᴘɴᴇ ᴋᴜᴛᴛᴀ ᴋ ᴍᴜʜ ᴍᴀɪ ʟᴇ ʟᴇᴛɪ ᴇʏ?😱",
    "{t} ᴋɪ ᴍᴀᴀ ᴀᴅɪᴠᴀsɪ ᴏɪʟ ʟɢᴀᴋᴇ ᴊᴜɴɢʟᴇ ᴍᴀ ɢᴀɴᴅ ᴅᴇᴛɪ ᴇʏ😭😭",
    "{t} ᴋɪ ᴍᴍʏ 𝐋ᴜꜰꜰʏ ᴋᴀ ʟᴏʀᴀ ʟᴇᴛᴀ ʜᴜ ᴘᴀᴀᴅ ᴍᴀʀᴛɪ ᴇʏ ᴄʜɪ🤬🤬🤬",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ʙɪᴊʟɪ ᴋ ᴋʜᴀᴍʙᴀ ᴘʀ ᴡɪʀᴇ ᴄʜᴜᴛᴀᴅ ᴍᴀ ʟᴇᴋʀ ᴛᴀᴅᴀᴘ ᴋʀ ᴍᴀʀ ɢᴀɪ😭👻",
    "{t} ᴊɪs sɪᴍ sᴀ ᴛᴜ ɴᴇᴛ ᴄʜᴀʟᴀ ʀᴀʜᴀ ᴠᴏ ᴠ ᴍᴇʀᴀ ʟᴏᴅᴀ ᴋɪ ᴋʀɪᴘᴀ ʜᴀ ᴇʏ ɢᴀʀᴇᴇʙ ᴛᴇʀʏ ᴍᴀᴀ sᴀ ᴘᴜᴄʜ😁💣",
    "{t} ʜᴀᴄᴋʟᴇ ᴍssɢ ᴍᴛ ᴋʀ ᴡᴀʀɴᴀ ᴛᴇʀᴀ ᴋʜᴀɴᴅᴀɴ ᴋᴏ ʀᴀᴏᴅ ᴘʀ ɴᴀɴɢᴀ ᴋʀᴋʀ ᴍᴜʜ ᴘʀ ɢᴀʀᴀᴍ ᴍᴜᴛ ᴅᴜɴɢᴀ😍🦈",
    "{t} ᴋɪ ᴍᴀᴀ 𝐋ᴜꜰꜰʏ ᴋ ʟᴜɴ ᴋɪ ᴘʜᴏᴛᴏ ᴅᴇᴋʜ ᴋʀ ғɪɴɢᴇʀɪɴɢ ᴋʀᴛɪ ᴇʏ🦈😭",
    "{t} ᴛᴇʀʏ ᴍᴍʏ ᴋᴀʟᴀ ᴄʜᴜᴛᴀᴅ ᴡᴀʟɪ ᴄʜᴜᴅᴀᴋʀ😈💋",
    "{t} ᴋɪ ᴍᴜᴍᴍʏ ᴍᴜᴛʜɪ ᴍᴀʀ ᴛɪ ᴇʏ?😭????",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋ ᴄʜᴜᴛᴀᴅ 😘 ᴘʀ 𝐋ᴜꜰꜰʏ ᴀᴘɴᴀ ʟᴜɴ sᴀ ᴛᴀʟɪʏᴀ ʙᴀᴊᴀʏᴇɢᴀ😈😈💋",
    "{t} ᴋɪ ᴍᴜᴍᴍʏ ᴀᴘɴɪ ᴄʜᴜᴄʜɪʏᴀ ɢᴀᴛᴇ ᴋ ʙɪᴄʜ ᴅᴀʙᴀ ᴋʀ ᴍᴀʀ ɢᴀɪ?😭😭",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ʜɪᴢʀᴇ ʙᴀɴᴋʀ ᴛʀᴀɪɴ ᴍᴀ ᴀᴛɪ ᴛᴇʀᴀ ᴘᴀᴘᴀ sᴜsᴜ ᴄʜᴀᴛɴᴇ ᴋɪ ᴅᴜᴋᴀɴ ᴋʀᴛᴀ ᴇʏ ʙᴛᴀ ᴅʏ ᴄʏᴀ sᴀʙᴋᴏ👻👻👻💣💣",
    "ᴋʏᴀᴀ?😱 {t} ᴋɪ ᴍᴍʏ ᴊᴀʙ sᴜsᴜ ᴋʀ ʀɪ ᴛʜɪ Tᴀʙ ᴄʜᴜᴛ ᴍᴀɪ sᴀᴀᴘ ɢʜᴜs ɢʏᴀ ᴠᴏ ʙʜɪ ᴄᴏʙʀᴀ?😱😱",
    "{t} ᴋɪ ʙᴇʜᴇɴ ᴋʜᴀᴅɪ ʜᴏ ᴋʀ ᴍᴜᴛ ᴛɪ ᴇʏ?😱😱😱",
    "{t} ᴛᴇʀʏ ᴍᴍʏ ᴋᴏ 𝐋ᴜꜰꜰʏ ɴᴀ ɴᴀsʜᴇ ᴍᴀɪ sᴏғᴀ ᴘʀ ᴛᴀɴɢ ᴜᴛʜᴀ ᴋʀ ᴄʜᴏᴅ ᴅɪʏᴀ😁😁",
    "{t} ᴛᴇʀɪ ᴍᴍʏ 𝐋ᴜꜰꜰʏ ᴋ ᴛᴀᴛᴛᴇ ᴋ ɴɪᴄʜᴇ 👻👻 ᴍᴀsʟɪ ɢʏɪ ᴀᴀʙ ᴛᴇʀᴀ ᴘᴀᴘᴀ ʀᴏʏᴇɢᴀ😘",
    "{t} ᴛᴇʀɪ ᴍᴀᴀ ᴋɪ ᴄʜᴜᴛ ᴍᴀ ᴀᴀɢ ʟɢᴀ ᴋᴇ ʀᴀᴋʜ ᴅᴜɴɢᴀ🔥🥵",
    "{t} ᴛᴇʀᴀ ᴘᴀᴘᴀ ʀᴀɴᴅɪ ᴋʜᴀɴᴀ ᴍᴀ ɢᴀɴᴅ ᴍᴀʀ ᴋʀ ᴋᴀᴍᴀᴛᴀ ʜᴀ🩸💔",
    "{t} ᴛᴇʀɪ ʙʜᴇɴ ᴋᴏ ʀᴇᴅ ʟɪɢʜᴛ ᴍᴀ ᴄʜᴏᴅ ᴋᴇ ʙʜᴀɢᴀ ᴅᴜɴɢᴀ🚨🩸",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋɪ ɢᴀɴᴅ ᴍᴇ sᴀᴘ ᴅᴀʟ ᴋᴇ ɴᴀᴄʜᴡᴀᴜɴɢᴀ🐍💃",
    "{t} ᴛᴇʀᴀ ᴘᴜʀᴀ ᴋʜᴀɴᴅᴀɴ ʀᴀɴᴅɪ ᴋʜᴀɴᴀ ᴍᴇ ɴᴀᴄʜᴛᴀ ʜᴀ🎭🍺",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋᴏ ʟᴜғғʏ ᴋᴇ ʟᴜɴ sᴇ ɢᴀʀᴍɪ ᴅᴇᴛᴀ ʜᴜ🔥💦",
    "{t} ᴛᴇʀɪ ᴅᴀᴅɪ ʙʜᴇɴ ᴅᴏɴᴏ ᴋᴏ ᴇᴋ sᴀᴛʜ ᴄʜᴏᴅ ᴋᴇ ɴᴀᴄʜᴀᴜɴɢᴀ🎉🩸",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋɪ ᴄʜᴜᴛ ᴋɪ ʜᴏᴛᴇʟ ᴋʜᴏʟ ᴋᴇ ʀᴀᴋʜ ᴅᴜɴɢᴀ🏨🩵",
    "{t} ᴛᴇʀᴀ ʙᴀᴀᴘ ᴄʜᴀᴜᴋɪᴅᴀʀ ʜᴀ TERI MAKI ɢᴀɴᴅ ᴋᴀ👻🚔",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋᴏ ɢᴀɴɢ ʙᴀɴɢ ᴋʀᴋᴇ ᴛʀᴀɪɴ sᴇ ᴜᴛᴀʀᴡᴀᴜɴɢᴀ🚂🩸",
    "{t} ᴛᴇʀɪ ʙʜᴇɴ ᴋɪ ɢᴀɴᴅ ᴍᴇ ʟᴜғғʏ ᴋᴀ ʟᴏɢᴏ ᴛᴀᴛᴛᴏᴏ ᴋᴀʀᴀ ᴅᴜɴɢᴀ🕸️🔱",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋɪ ᴄʜᴜᴛ ᴍᴀ ᴛʀɪᴘʟᴇ x ᴠɪᴅᴇᴏ ʙᴀɴᴀᴋᴇ ᴠɪʀᴀʟ ᴋᴀʀ ᴅᴜɴɢᴀ📸🔥",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋᴏ ᴅᴏɢɢʏ sᴛʏʟᴇ ᴍᴀ ᴄʜᴏᴅ ᴋᴇ ɴᴀᴄʜᴇ ɢɪʀᴀ ᴅᴜɴɢᴀ🐕🩸",
    "{t} ᴛᴇʀɪ ʙʜᴇɴ ᴋɪ ᴄʜᴜᴛ ᴍᴀ ʟᴜғғʏ ɢᴀɴɢ ᴋᴀ ʀᴀᴠᴀ ʟɢᴀ ᴅᴜɴɢᴀ🔊🩵",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋɪ ɢᴀɴᴅ ᴍᴀ ᴛᴀʟᴀʙ ᴋᴀ ᴘᴀɴɪ ʙʜᴀʀ ᴋᴇ ɴᴀᴄʜᴀᴜɴɢᴀ🌊🩸",
    "{t} ᴛᴇʀᴀ ᴘᴀᴘᴀ ʀᴀɴᴅɪ ᴋʜᴀɴᴀ ᴍᴀ ᴍᴜᴛ ᴋᴇ ʙᴇᴄʜ ᴅᴜɴɢᴀ🍺🩸",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋᴏ ɢᴀʏ sᴛʏʟᴇ ᴍᴀ ᴄʜᴏᴅ ᴋᴇ ᴠɪʀᴀʟ ᴋᴀʀ ᴅᴜɴɢᴀ📱🔥",
    "{t} ᴛᴇʀɪ ᴅᴀᴅɪ ᴋɪ ᴄʜᴜᴛ ᴍᴀ ᴄᴏᴋᴇ sᴛᴜᴅɪᴏ ᴋʜᴏʟ ᴅᴜɴɢᴀ🥤🩸",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋɪ ɢᴀɴᴅ ᴍᴀ sᴛᴀᴅɪᴜᴍ ᴍᴀ ᴍᴀᴛᴄʜ ᴋᴀʀᴀ ᴅᴜɴɢᴀ🏟️🩸",
    "{t} ᴛᴇʀɪ ʙʜᴇɴ ᴋɪ ᴄʜᴜᴛ ᴍᴀ ʟᴜғғʏ ɢᴀɴɢ ᴋᴀ ᴛᴀᴛᴛᴏᴏ ʙᴀɴᴡᴀ ᴅᴜɴɢᴀ🕸️🩵",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋᴏ ᴘᴜʙʟɪᴄ ᴍᴀ ᴄʜᴏᴅ ᴋᴇ ᴠɪʀᴀʟ ᴋᴀʀ ᴅᴜɴɢᴀ📢🩸",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋɪ ɢᴀɴᴅ ᴍᴀ ᴅᴇᴇᴘғᴀᴋᴇ ʙᴀɴᴀᴋᴇ ᴘᴏsᴛ ᴋᴀʀ ᴅᴜɴɢᴀ📸🔥",
    "{t} ᴛᴇʀᴇ ᴋʜᴀɴᴅᴀɴ ᴋɪ ᴄʜᴜᴛ ᴍᴀ ᴅʀᴏɴᴇ ᴄᴀᴍᴇʀᴀ ʟᴀɢᴀ ᴅᴜɴɢᴀ🚁🩸",
    "{t} ᴛᴇʀɪ ᴍᴍʏ ᴋᴏ ʟᴜғғʏ ɢᴀɴɢ ᴋᴇ ʜᴀᴡᴀʟᴇ ᴋᴀʀ ᴅᴜɴɢᴀ🏴‍☠️🩸",
    "{t} ᴛᴇʀɪ ʙʜᴇɴ ᴋɪ ᴄʜᴜᴛ ᴍᴀ ʀᴀᴘ ʙᴀᴛᴛʟᴇ ᴋᴀʀᴡᴀ ᴅᴜɴɢᴀ🎤🩸",
]

async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not update.effective_chat: return

    chat    = update.effective_chat
    chat_id = chat.id
    is_chan = chat.type == "channel"
    uid     = update.effective_user.id if update.effective_user else 0
    guard   = get_limiter(ctx.bot.id)

    KNOWN_CHATS.add(chat_id)

    if update.effective_user:
        track_user(update.effective_user)

    if is_chan:
        return

    if chat_id in spamwatch_chats and uid and uid != ctx.bot.id:
        st = spamwatch_chats[chat_id]
        if uid != st.get("owner_id") and _track_burst(chat_id, uid):
            await _trigger_spamwatch(chat_id, uid, msg.message_id)

    ar = AR_text.get(chat_id)
    if ar:
        tgt = ar.get("text")
        if tgt == "__ALL__" or uid == tgt:
            if uid and uid != ctx.bot.id:
                await guard.set_message_reaction(
                    ctx.bot, chat_id=chat_id, message_id=msg.message_id,
                    reaction=ar["emoji"], is_big=False)

    ch = CHUD_TEXT.get(chat_id)
    if ch and uid == ch["text"]:
        txt = random.choice(CHUD_POOL).format(t=ch["text"])
        await guard.send_message(ctx.bot, chat_id, txt,
                                 reply_to_message_id=msg.message_id)


# ═══════════════════════════════════════════════════════════════
# 🚀  BOOTSTRAP
# ═══════════════════════════════════════════════════════════════
async def start_all_bots():
    for i, tok in enumerate(BOT_TOKENS, start=1):
        try:
            app = ApplicationBuilder().token(tok).build()

            app.add_handler(MessageHandler(
                filters.Regex(r"^~") & (
                    filters.ChatType.PRIVATE
                    | filters.ChatType.GROUPS
                    | filters.ChatType.CHANNEL
                ), route))

            app.add_handler(MessageHandler(
                filters.ALL
                & ~filters.Regex(r"^~")
                & ~filters.ChatType.CHANNEL, on_message))

            await app.initialize()
            await app.start()
            await app.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=["message", "channel_post",
                                 "edited_message", "edited_channel_post",
                                 "callback_query"],
            )

            me = await app.bot.get_me()
            BOT_INFO[app.bot.id] = {"no": i, "username": me.username}
            ALL_APPS.append(app)
            ALL_BOTS.append(app.bot)
            log.info(f"✅ Bot #{i} online → @{me.username}  [groups + channels]")
        except Exception as e:
            log.error(f"❌ Bot #{i} failed: {e}")


async def shutdown_all():
    for a in ALL_APPS:
        try:
            await a.updater.stop(); await a.stop(); await a.shutdown()
        except Exception: pass


async def main():
    log.info("🚀 LUFFY ENGINE V16 STARTED — NC7/SLAVENC FIXED · POWERFUL STOPS")
    await start_all_bots()
    if not ALL_APPS:
        log.error("No bots online."); return
    log.info(f"✅ {len(ALL_APPS)} bots running · adaptive flood-shield ON")
    try:
        await asyncio.Event().wait()
    finally:
        await shutdown_all()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutdown.")

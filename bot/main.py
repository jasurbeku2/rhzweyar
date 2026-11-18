import asyncio, io, logging, re, time
from asgiref.sync import sync_to_async
from django.conf import settings
from aiogram import Bot, BaseMiddleware, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (BufferedInputFile, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup,
                           ReplyKeyboardRemove)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from core import services as svc
from core.models import Payment, ServiceOrder
from . import tools

logging.basicConfig(level=logging.INFO, filename="bot.log", format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")
r = Router()


def db(f):
    return sync_to_async(f, thread_sensitive=True)


class Movie(StatesGroup):
    wait = State()


class Conv(StatesGroup):
    wait = State()


class Img(StatesGroup):
    photo = State()
    params = State()


class Pay(StatesGroup):
    check = State()


class AddMovie(StatesGroup):
    video = State(); title = State(); code = State(); photo = State(); vip = State(); price = State()


# ---------- yordamchilar ----------
def kb(rows, cols=2):
    b = InlineKeyboardBuilder()
    for text, data in rows:
        if data.startswith("http"):
            b.add(InlineKeyboardButton(text=text, url=data))
        else:
            b.button(text=text, callback_data=data)
    b.adjust(cols)
    return b.as_markup()


def menu_kb():
    return kb([("🎬 Kino ko'rish", "m_movie"), ("📄 Fayl konvertor", "m_conv"), ("🖼 Rasm tahrirlash", "m_img"),
               ("💎 Premium", "m_prem"), ("🪙 Profil / Coin", "m_prof"), ("🌐 Sayt", settings.SITE_URL)])


BACK = ("🏠 Menyu", "menu")


async def need_sub(bot, uid):
    bad = []
    for ch in await db(svc.channels)():
        try:
            m = await bot.get_chat_member(ch.chat, uid)
            if m.status in ("left", "kicked"):
                bad.append(ch)
        except Exception:
            pass
    return bad


async def show_menu(m, u):
    c = await db(svc.SiteConfig.get)()
    await m.answer(c.start_text, reply_markup=menu_kb())


async def after_start(m, state, bot, u, arg):
    bad = await need_sub(bot, u.tg_id)
    if bad:
        await m.answer("Botdan foydalanish uchun kanallarga obuna bo'ling:",
                       reply_markup=kb([(c.title, c.link) for c in bad] + [("✅ Tekshirish", "chk_sub")], 1))
        return
    if arg and re.match(r"^(pay|ord)_\d+$", arg):
        kind, pk = arg.split("_")
        M = Payment if kind == "pay" else ServiceOrder
        o = await db(lambda: M.objects.filter(pk=int(pk), user=u, status="wait").first())()
        if o:
            await state.set_state(Pay.check)
            await state.update_data(kind=kind, pk=o.pk)
            await m.answer(f"💳 Aynan {o.amount} so'm o'tkazing:\n{await db(svc.config_card)()}\n\nChek (skrinshot)ni shu yerga yuboring.")
            return
    await show_menu(m, u)


# ---------- middleware: bloklash, spam ----------
class Guard(BaseMiddleware):
    last = {}

    async def __call__(self, handler, event, data):
        tg = event.from_user
        now = time.monotonic()
        if now - self.last.get(tg.id, 0) < 0.3:
            return
        self.last[tg.id] = now
        u = await db(svc.get_user)(tg.id)
        if u and u.is_blocked:
            return
        data["u"] = u
        is_msg = hasattr(event, "text")
        if not u and not (is_msg and ((event.text or "").startswith("/start") or event.contact)):
            if is_msg:
                await event.answer("Avval /start bosing.")
            else:
                await event.answer("Avval /start bosing.", show_alert=True)
            return
        try:
            return await handler(event, data)
        except Exception:
            log.exception("handler xatosi")
            try:
                await (event.answer("Xatolik yuz berdi"))
            except Exception:
                pass


# ---------- start / menyu ----------
@r.message(CommandStart())
async def start(m, command: CommandObject, state: FSMContext, bot: Bot, u):
    await state.clear()
    if not u or not u.tg_id:
        await state.update_data(arg=command.args)
        k = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 Raqamni ulashish", request_contact=True)]],
                                resize_keyboard=True, one_time_keyboard=True)
        await m.answer("Salom! Davom etish uchun pastdagi tugma orqali raqamingizni ulashing.", reply_markup=k)
        return
    if u.tg_username != (m.from_user.username or ""):
        u.tg_username = m.from_user.username or ""
        await db(u.save)()
    await after_start(m, state, bot, u, command.args)


@r.message(F.contact)
async def contact(m, state: FSMContext, bot: Bot, u):
    if m.contact.user_id != m.from_user.id:
        await m.answer("Faqat o'z raqamingizni ulashing.")
        return
    d = await state.get_data()
    arg = d.get("arg") or ""
    ref = int(arg[4:]) if arg.startswith("ref_") and arg[4:].isdigit() else None
    u = await db(svc.register)(m.from_user.id, m.from_user.username, m.contact.phone_number, m.from_user.first_name, ref)
    await m.answer("✅ Raqam ulandi.", reply_markup=ReplyKeyboardRemove())
    if u.role == "super":
        await m.answer("👑 Siz super adminsiz. Buyruqlar: /addadmin, /deladmin, /admins")
    await after_start(m, state, bot, u, arg)


@r.callback_query(F.data == "chk_sub")
async def chk_sub(c, state: FSMContext, bot: Bot, u):
    if await need_sub(bot, u.tg_id):
        await c.answer("Hali obuna bo'lmadingiz", show_alert=True)
        return
    await c.message.delete()
    await show_menu(c.message, u)


@r.callback_query(F.data == "menu")
async def menu(c, state: FSMContext, u):
    await state.clear()
    await c.message.answer("Bosh menyu:", reply_markup=menu_kb())
    await c.answer()


# ---------- kino ----------
@r.callback_query(F.data == "m_movie")
async def m_movie(c, state: FSMContext, u):
    await state.set_state(Movie.wait)
    await c.message.answer("🎬 Kino kodini yuboring:", reply_markup=kb([BACK]))
    await c.answer()


async def send_movie(m, bot, u, code):
    bad = await need_sub(bot, u.tg_id)
    if bad:
        await m.answer("Avval kanallarga obuna bo'ling:", reply_markup=kb([(c.title, c.link) for c in bad], 1))
        return
    mv, err = await db(svc.open_movie)(u, code)
    if not mv:
        await m.answer(err)
        return
    await m.answer_video(mv.video_id, caption=f"🎬 {mv.title}\nKod: {mv.code}", protect_content=True)


@r.message(Movie.wait, F.text)
async def movie_code(m, bot: Bot, u):
    await send_movie(m, bot, u, m.text)


# ---------- fayl konvertor ----------
@r.callback_query(F.data == "m_conv")
async def m_conv(c, u):
    await c.message.answer("Qaysi konvertatsiya kerak?",
                           reply_markup=kb([(t, f"cv:{k}") for k, t in tools.CONVERT_MODES.items()] + [BACK]))
    await c.answer()


@r.callback_query(F.data.startswith("cv:"))
async def cv_pick(c, state: FSMContext, u):
    mode = c.data[3:]
    await state.set_state(Conv.wait)
    await state.update_data(mode=mode)
    await c.message.answer(f"{tools.CONVERT_MODES[mode]}\nFaylni yuboring (20 MB gacha).", reply_markup=kb([BACK]))
    await c.answer()


async def fetch(bot, m):
    if m.document:
        if (m.document.file_size or 0) > 20 * 1024 * 1024:
            raise ValueError("Fayl 20 MB dan katta.")
        fid, name = m.document.file_id, m.document.file_name or "fayl"
    else:
        fid, name = m.photo[-1].file_id, "rasm.jpg"
    buf = io.BytesIO()
    await bot.download(fid, destination=buf)
    return buf.getvalue(), name


@r.message(Conv.wait, F.document | F.photo)
async def conv_file(m, state: FSMContext, bot: Bot, u):
    mode = (await state.get_data())["mode"]
    try:
        data, name = await fetch(bot, m)
        files = await asyncio.to_thread(tools.convert, mode, data, name)
    except ValueError as e:
        await m.answer(str(e)); return
    except Exception:
        log.exception("convert")
        await m.answer("Bu faylni o'tkazib bo'lmadi. Fayl turi mos ekanini tekshiring."); return
    for n, b in files:
        await m.answer_document(BufferedInputFile(b, filename=n))
    await m.answer("✅ Tayyor. Yana fayl yuborishingiz mumkin.", reply_markup=kb([BACK]))


# ---------- rasm tahrirlash ----------
@r.callback_query(F.data == "m_img")
async def m_img(c, u):
    await c.message.answer("Rasm bilan nima qilamiz?", reply_markup=kb(
        [("✂️ Piksel bilan qirqish", "im:crop"), ("3 qism", "im:s3"), ("4 qism", "im:s4"), ("6 qism", "im:s6"), BACK]))
    await c.answer()


@r.callback_query(F.data.startswith("im:"))
async def im_pick(c, state: FSMContext, u):
    await state.set_state(Img.photo)
    await state.update_data(op=c.data[3:])
    await c.message.answer("Rasmni yuboring (sifat buzilmasligi uchun «Fayl» sifatida yuborgan ma'qul).",
                           reply_markup=kb([BACK]))
    await c.answer()


@r.message(Img.photo, F.document | F.photo)
async def im_photo(m, state: FSMContext, bot: Bot, u):
    op = (await state.get_data())["op"]
    fid = m.document.file_id if m.document else m.photo[-1].file_id
    if op == "crop":
        await state.update_data(fid=fid)
        await state.set_state(Img.params)
        await m.answer("O'lchamni yozing (piksel):\n• <code>800 600</code> — markazdan kenglik va balandlik\n"
                       "• <code>100 50 800 600</code> — x y kenglik balandlik", parse_mode="HTML")
        return
    try:
        data, _ = await fetch(bot, m)
        files = await asyncio.to_thread(tools.split, data, int(op[1:]))
    except Exception:
        log.exception("split")
        await m.answer("Rasmni qayta ishlab bo'lmadi."); return
    for n, b in files:
        await m.answer_document(BufferedInputFile(b, filename=n))
    await m.answer("✅ Tayyor.", reply_markup=kb([BACK]))


@r.message(Img.params, F.text)
async def im_params(m, state: FSMContext, bot: Bot, u):
    nums = [int(x) for x in re.findall(r"\d+", m.text)]
    fid = (await state.get_data())["fid"]
    buf = io.BytesIO()
    await bot.download(fid, destination=buf)
    try:
        files = await asyncio.to_thread(tools.crop, buf.getvalue(), nums)
    except ValueError as e:
        await m.answer(str(e)); return
    await m.answer_document(BufferedInputFile(files[0][1], filename=files[0][0]))
    await m.answer("✅ Tayyor. Boshqa o'lcham yuborsangiz shu rasmni yana qirqaman.", reply_markup=kb([BACK]))


# ---------- Premium va to'lov ----------
@r.callback_query(F.data == "m_prem")
async def m_prem(c, u):
    ts = await db(svc.tariffs)()
    if not ts:
        await c.message.answer("Tariflar hali qo'shilmagan.")
    else:
        await c.message.answer("💎 Tarifni tanlang:", reply_markup=kb(
            [(f"{t.name} — {t.price} so'm", f"buy:{t.id}") for t in ts] + [BACK], 1))
    await c.answer()


@r.callback_query(F.data.startswith("buy:"))
async def buy(c, state: FSMContext, u):
    p = await db(svc.create_payment)(u, int(c.data[4:]))
    await state.set_state(Pay.check)
    await state.update_data(kind="pay", pk=p.pk)
    await c.message.answer(f"💳 Aynan <b>{p.amount}</b> so'm o'tkazing:\n{await db(svc.config_card)()}\n\n"
                           "To'lagach chek (skrinshot)ni shu yerga yuboring.", parse_mode="HTML")
    await c.answer()


@r.message(Pay.check, F.photo | F.document)
async def got_check(m, state: FSMContext, bot: Bot, u):
    d = await state.get_data()
    uid = m.photo[-1].file_unique_id if m.photo else m.document.file_unique_id
    if await db(svc.check_dup)(uid):
        await m.answer("Bu chek avval yuborilgan."); return
    if not await db(svc.attach_check)(d["kind"], d["pk"], uid):
        await m.answer("Bu to'lov eskirgan yoki chek allaqachon yuborilgan."); return
    info = (await db(svc.payment_info)(d["pk"]))[1] if d["kind"] == "pay" else (await db(svc.order_info)(d["pk"]))[1]
    k = kb([("✅ Tasdiqlash", f"ap:{d['kind']}:{d['pk']}"), ("❌ Rad etish", f"rj:{d['kind']}:{d['pk']}")])
    for a in await db(svc.admins)():
        try:
            await bot.copy_message(a.tg_id, m.chat.id, m.message_id, caption=info, reply_markup=k)
        except Exception:
            log.exception("admin notify")
    await state.clear()
    await m.answer("✅ Chek adminga yuborildi. Tasdiqlangach xabar keladi.", reply_markup=kb([BACK]))


@r.callback_query(F.data.regexp(r"^(ap|rj):(pay|ord):\d+$"))
async def decide(c, u):
    if not u.is_admin_role:
        await c.answer("Ruxsat yo'q", show_alert=True); return
    act, kind, pk = c.data.split(":"); pk = int(pk)
    if kind == "pay":
        res = await db(svc.approve_payment if act == "ap" else svc.reject_payment)(pk, u)
    else:
        o = await db(lambda: ServiceOrder.objects.filter(pk=pk, status="pending").first())()
        res = o
        if o:
            await db(svc.finish_order)(pk, act == "ap")
    if not res:
        await c.answer("Allaqachon ko'rib chiqilgan", show_alert=True); return
    await c.message.edit_caption(caption=(c.message.caption or "") + ("\n\n✅ Tasdiqlandi" if act == "ap" else "\n\n❌ Rad etildi")
                                 + f" — @{u.tg_username}")
    await c.answer("Bajarildi")


# ---------- profil, promokod ----------
@r.callback_query(F.data == "m_prof")
async def m_prof(c, bot: Bot, u):
    me = await bot.get_me()
    prem = f"{u.premium_until:%d.%m.%Y %H:%M} gacha" if u.is_premium else "yo'q"
    await c.message.answer(f"👤 {u.phone}\n🪙 Coin: {u.coins}\n💎 Premium: {prem}\n\n"
                           f"🔗 Referal havola:\nhttps://t.me/{me.username}?start=ref_{u.tg_id}\n\n"
                           "🎟 Promokod: /promo KOD", reply_markup=kb([BACK]))
    await c.answer()


@r.message(Command("promo"))
async def promo(m, command: CommandObject, u):
    await m.answer(await db(svc.redeem)(u, command.args) if command.args else "Namuna: /promo KOD")


# ---------- admin buyruqlari ----------
def adm(f):
    async def w(m, *a, u=None, **kw):
        if not u or not u.is_admin_role:
            return
        return await f(m, *a, u=u, **kw)
    w.__name__ = f.__name__
    return w


def sup(f):
    async def w(m, *a, u=None, **kw):
        if not u or u.role != "super":
            return
        return await f(m, *a, u=u, **kw)
    w.__name__ = f.__name__
    return w


@r.message(Command("addadmin"))
@sup
async def addadmin(m, command: CommandObject, u):
    if not command.args:
        await m.answer("Namuna: /addadmin +998901234567 yoki /addadmin @username"); return
    x = await db(svc.set_admin)(command.args, True)
    await m.answer("Topilmadi. Username bo'yicha qo'shish uchun foydalanuvchi botga /start bosgan bo'lishi kerak."
                   if x is None else "Bu super admin." if x == "super" else f"✅ Admin qo'shildi: {x.phone}")


@r.message(Command("deladmin"))
@sup
async def deladmin(m, command: CommandObject, u):
    x = await db(svc.set_admin)(command.args or "", False)
    await m.answer("Topilmadi." if x is None else "Super adminni o'chirib bo'lmaydi." if x == "super" else "✅ Admin olib tashlandi.")


@r.message(Command("admins"))
@sup
async def admins(m, u):
    await m.answer("\n".join(f"{a.role}: {a.phone} @{a.tg_username}" for a in await db(svc.admins)()))


@r.message(Command("ban", "unban"))
@adm
async def ban(m, command: CommandObject, u):
    if not (command.args or "").isdigit():
        await m.answer("Namuna: /ban 123456789"); return
    n = await db(svc.set_ban)(int(command.args), command.command == "ban")
    await m.answer("✅ Bajarildi" if n else "Topilmadi")


@r.message(Command("stats"))
@adm
async def stats(m, u):
    s = await db(svc.stats)()
    await m.answer(f"📊 Foydalanuvchilar: {s['users']}\n💎 Premium: {s['premium']}\n🚫 Bloklangan: {s['blocked']}\n"
                   f"🎬 Kinolar: {s['movies']} (ko'rishlar: {s['views']})\n💰 Bugun: {s['today_pay']} ta, {s['today_sum']} so'm\n"
                   f"💰 Jami daromad: {s['all_sum']} so'm")


@r.message(Command("setcard"))
@adm
async def setcard(m, command: CommandObject, u):
    p = [x.strip() for x in (command.args or "").split("|")]
    if len(p) != 3:
        await m.answer("Namuna: /setcard 8600 1234 5678 9012 | Ism Familiya | Bank"); return
    await db(svc.set_card)(*p)
    await m.answer("✅ Karta yangilandi")


@r.message(Command("addchannel"))
@adm
async def addchannel(m, command: CommandObject, u):
    p = (command.args or "").split()
    if len(p) != 1 or not p[0].startswith("@"):
        await m.answer("Namuna: /addchannel @kanal_username (bot kanalda admin bo'lishi kerak)"); return
    await db(svc.add_channel)(p[0], p[0], f"https://t.me/{p[0][1:]}")
    await m.answer("✅ Majburiy kanal qo'shildi")


@r.message(Command("send"))
@adm
async def broadcast(m, bot: Bot, u):
    if not m.reply_to_message:
        await m.answer("Reklama xabariga reply qilib /send yozing (matn, rasm, video, forward — hammasi bo'ladi)."); return
    ok = 0
    for tid in await db(svc.all_tg_ids)():
        try:
            await bot.copy_message(tid, m.chat.id, m.reply_to_message.message_id); ok += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)
    await m.answer(f"📨 Yuborildi: {ok}")


@r.message(Command("delmovie"))
@adm
async def delmovie(m, command: CommandObject, u):
    await m.answer("✅ O'chirildi" if await db(svc.del_movie)(command.args or "") else "Topilmadi")


@r.message(Command("addmovie"))
@adm
async def addmovie(m, state: FSMContext, u):
    await state.set_state(AddMovie.video)
    await m.answer("🎬 Videoni yuboring:")


@r.message(AddMovie.video, F.video)
async def am_video(m, state: FSMContext):
    await state.update_data(video=m.video.file_id, duration=m.video.duration or 0)
    await state.set_state(AddMovie.title); await m.answer("Kino nomi?")


@r.message(AddMovie.title, F.text)
async def am_title(m, state: FSMContext):
    await state.update_data(title=m.text); await state.set_state(AddMovie.code); await m.answer("Kino kodi (noyob)?")


@r.message(AddMovie.code, F.text)
async def am_code(m, state: FSMContext):
    if await db(svc.movie_by_code)(m.text):
        await m.answer("Bu kod band. Boshqa kod yozing."); return
    await state.update_data(code=m.text.strip()); await state.set_state(AddMovie.photo); await m.answer("Rasm yuboring (yoki /skip):")


async def ask_vip(m, state):
    await state.set_state(AddMovie.vip)
    await m.answer("Turi?", reply_markup=kb([("Oddiy", "vip:0"), ("⭐ VIP", "vip:1")]))


@r.message(AddMovie.photo, F.photo)
async def am_photo(m, state: FSMContext):
    await state.update_data(photo=m.photo[-1].file_id); await ask_vip(m, state)


@r.message(AddMovie.photo, Command("skip"))
async def am_skip(m, state: FSMContext):
    await state.update_data(photo=""); await ask_vip(m, state)


async def finish_movie(m, state, price, vip):
    d = await state.get_data()
    await db(svc.add_movie)(d["title"], d["code"], d["video"], d["photo"], d["duration"], vip, price)
    await state.clear()
    await m.answer(f"✅ Qo'shildi: {d['title']} (kod: {d['code']})")


@r.callback_query(AddMovie.vip, F.data.startswith("vip:"))
async def am_vip(c, state: FSMContext):
    if c.data == "vip:0":
        await finish_movie(c.message, state, 0, False)
    else:
        await state.set_state(AddMovie.price); await c.message.answer("VIP narxi (coin)? 0 = standart narx")
    await c.answer()


@r.message(AddMovie.price, F.text)
async def am_price(m, state: FSMContext):
    await finish_movie(m, state, int(m.text) if m.text.isdigit() else 0, True)


# ---------- oddiy matn = kino kodi ----------
@r.message(StateFilter(None), F.text, ~F.text.startswith("/"))
async def default_text(m, bot: Bot, u):
    await send_movie(m, bot, u, m.text)


# ---------- fon vazifasi ----------
async def daily_loop(bot):
    while True:
        try:
            ids, n = await db(svc.daily_coins)()
            for i in ids:
                try:
                    await bot.send_message(i, f"💎 Premium sovg'a: +{n} coin")
                except Exception:
                    pass
        except Exception:
            log.exception("daily")
        await asyncio.sleep(3600)


async def main():
    await db(svc.ensure_superadmin)()
    bot = Bot(settings.BOT_TOKEN)
    dp = Dispatcher()
    dp.message.outer_middleware(Guard())
    dp.callback_query.outer_middleware(Guard())
    dp.include_router(r)
    asyncio.create_task(daily_loop(bot))
    await bot.delete_webhook()
    await dp.start_polling(bot)

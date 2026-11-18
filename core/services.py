import json, random, re, urllib.request
from datetime import timedelta
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F, Sum
from django.utils import timezone
from accounts.models import User
from .models import *


def norm_phone(p):
    d = re.sub(r"\D", "", p or "")
    if len(d) == 9:
        d = "998" + d
    return "+" + d if d else ""


def norm_user(u):
    return (u or "").strip().lstrip("@").lower()


def log(action, user_tg=None, info=""):
    Log.objects.create(action=action, user_tg=user_tg, info=info[:500])


def tg_send(chat_id, text):
    """Django tomondan Telegram'ga xabar yuborish (kod, bildirishnoma)."""
    if not (settings.BOT_TOKEN and chat_id):
        return False
    try:
        data = json.dumps({"chat_id": chat_id, "text": text}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
                                     data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:
        return False


def ensure_superadmin():
    phone = norm_phone(settings.SUPERADMIN_PHONE)
    u, _ = User.objects.get_or_create(phone=phone, defaults={"role": "super"})
    if u.role != "super":
        u.role = "super"
    if not u.tg_username:
        u.tg_username = norm_user(settings.SUPERADMIN_USERNAME)
    u.save()
    return u


def get_user(tg_id):
    return User.objects.filter(tg_id=tg_id).first()


def register(tg_id, username, phone, name, ref=None):
    phone = norm_phone(phone)
    u = User.objects.filter(tg_id=tg_id).first() or User.objects.filter(phone=phone).first()
    new = u is None or u.tg_id is None
    if not u:
        u = User(phone=phone)
    u.tg_id, u.tg_username, u.first_name = tg_id, username or "", (name or "")[:30]
    if phone == norm_phone(settings.SUPERADMIN_PHONE) and norm_user(username) == norm_user(settings.SUPERADMIN_USERNAME):
        u.role = "super"
    if new and ref and ref != tg_id:
        r = User.objects.filter(tg_id=ref).first()
        if r:
            u.referred_by = r
            User.objects.filter(pk=r.pk).update(coins=F("coins") + SiteConfig.get().referral_bonus)
    u.save()
    log("register", tg_id, phone)
    return u


def add_premium(user, days):
    base = user.premium_until if user.is_premium else timezone.now()
    user.premium_until = base + timedelta(days=days)
    user.save(update_fields=["premium_until"])


def spend_coins(uid, n):  # atomik: ikki marta bosib bo'lmaydi
    return User.objects.filter(pk=uid, coins__gte=n).update(coins=F("coins") - n) == 1


def _unique_amount(model, base):
    open_amounts = set(model.objects.filter(status__in=["wait", "pending"]).values_list("amount", flat=True))
    for add in range(0, 1000):
        if base + add not in open_amounts:
            return base + add
    raise ValueError("Noyob summa topilmadi")


def create_payment(user, tariff_id):
    t = Tariff.objects.get(pk=tariff_id, is_active=True)
    Payment.objects.filter(user=user, status="wait").update(status="expired")
    for _ in range(5):
        try:
            with transaction.atomic():
                return Payment.objects.create(user=user, tariff=t, amount=_unique_amount(Payment, t.price))
        except IntegrityError:
            continue


def create_order(user, kind, details, qty):
    c = SiteConfig.get()
    unit = {"stars": c.stars_price_som, "gift": c.gift_price_som, "number": c.number_price_som,
            "coin": c.coin_price_som}[kind]
    total = unit * (qty if kind in ("stars", "coin") else 1)
    ServiceOrder.objects.filter(user=user, status="wait").update(status="rejected")
    for _ in range(5):
        try:
            with transaction.atomic():
                return ServiceOrder.objects.create(user=user, kind=kind, details=details[:200],
                                                   amount=_unique_amount(ServiceOrder, total))
        except IntegrityError:
            continue


def check_dup(unique_id):
    return (Payment.objects.filter(check_unique_id=unique_id, status__in=["pending", "approved"]).exists()
            or ServiceOrder.objects.filter(check_unique_id=unique_id, status__in=["pending", "done"]).exists())


def attach_check(kind, pk, unique_id):
    M = Payment if kind == "pay" else ServiceOrder
    return M.objects.filter(pk=pk, status="wait").update(status="pending", check_unique_id=unique_id) == 1


def approve_payment(pid, admin_user):
    with transaction.atomic():
        p = Payment.objects.select_for_update().select_related("user", "tariff").get(pk=pid)
        if p.status not in ("pending", "wait"):
            return None
        p.status, p.decided_by = "approved", admin_user
        p.save()
        add_premium(p.user, p.tariff.days)
    log("payment_ok", p.user.tg_id, f"#{pid} {p.amount}")
    tg_send(p.user.tg_id, f"✅ To'lov tasdiqlandi. Premium {p.tariff.days} kunga faollashtirildi.")
    return p


def reject_payment(pid, admin_user):
    p = Payment.objects.select_related("user").get(pk=pid)
    if p.status not in ("pending", "wait"):
        return None
    p.status, p.decided_by = "rejected", admin_user
    p.save()
    log("payment_no", p.user.tg_id, f"#{pid}")
    tg_send(p.user.tg_id, "❌ To'lov rad etildi. Savol bo'lsa admin bilan bog'laning.")
    return p


def finish_order(oid, ok):
    o = ServiceOrder.objects.select_related("user").get(pk=oid)
    if o.status not in ("pending", "wait"):
        return
    if ok and o.kind == "coin":
        qty = int("".join(c for c in o.details if c.isdigit()) or 0)
        User.objects.filter(pk=o.user_id).update(coins=F("coins") + qty)
    o.status = "done" if ok else "rejected"
    o.save()
    tg_send(o.user.tg_id, f"✅ Buyurtma #{o.id} bajarildi." if ok else f"❌ Buyurtma #{o.id} rad etildi.")


def redeem(user, code):
    with transaction.atomic():
        p = PromoCode.objects.select_for_update().filter(code__iexact=code.strip(), is_active=True).first()
        if not p or p.used >= p.max_uses:
            return "Promokod topilmadi yoki tugagan."
        if PromoUse.objects.filter(promo=p, user=user).exists():
            return "Siz bu promokodni ishlatgansiz."
        PromoUse.objects.create(promo=p, user=user)
        PromoCode.objects.filter(pk=p.pk).update(used=F("used") + 1)
        if p.kind == "coin":
            User.objects.filter(pk=user.pk).update(coins=F("coins") + p.value)
            msg = f"🎁 {p.value} coin qo'shildi."
        else:
            user.refresh_from_db()
            add_premium(user, p.value)
            msg = f"🎁 Premium {p.value} kunga berildi."
    log("promo", user.tg_id, p.code)
    return msg


def admins():
    return list(User.objects.filter(role__in=["admin", "super"]).exclude(tg_id=None))


def set_admin(identifier, make):
    ident = identifier.strip()
    q = User.objects.filter(tg_username__iexact=norm_user(ident)) if ident.startswith("@") \
        else User.objects.filter(phone=norm_phone(ident))
    u = q.first()
    if not u:
        if not make or ident.startswith("@"):
            return None
        u = User.objects.create(phone=norm_phone(ident))  # raqam oldindan qo'shiladi, /start bosganda ulanadi
    if u.role == "super":
        return "super"
    u.role = "admin" if make else "user"
    u.save()
    log("admin_set", u.tg_id, f"{u.phone} {u.role}")
    return u


def set_ban(tg_id, flag):
    return User.objects.filter(tg_id=tg_id).update(is_blocked=flag)


def stats():
    now = timezone.now()
    today = Payment.objects.filter(status="approved", created__date=now.date())
    return {"users": User.objects.count(), "premium": User.objects.filter(premium_until__gt=now).count(),
            "blocked": User.objects.filter(is_blocked=True).count(), "movies": Movie.objects.count(),
            "views": Movie.objects.aggregate(s=Sum("views"))["s"] or 0, "today_pay": today.count(),
            "today_sum": today.aggregate(s=Sum("amount"))["s"] or 0,
            "all_sum": Payment.objects.filter(status="approved").aggregate(s=Sum("amount"))["s"] or 0}


def all_tg_ids():
    return list(User.objects.filter(is_blocked=False).exclude(tg_id=None).values_list("tg_id", flat=True))


def daily_coins():
    c = SiteConfig.get()
    today = timezone.localdate()
    qs = User.objects.filter(premium_until__gt=timezone.now()).exclude(last_coin_date=today)
    ids = list(qs.values_list("tg_id", flat=True))
    qs.update(coins=F("coins") + c.daily_coin, last_coin_date=today)
    return ids, c.daily_coin


def movie_by_code(code):
    return Movie.objects.filter(code__iexact=code.strip()).first()


def open_movie(user, code):
    """(movie, xabar). VIP bo'lsa Premium bepul, aks holda coin yechiladi."""
    m = movie_by_code(code)
    if not m:
        return None, "Bunday kodli kino topilmadi."
    if m.is_vip and not user.is_premium:
        price = m.price or SiteConfig.get().vip_coin_price
        if not spend_coins(user.pk, price):
            return None, f"Bu VIP kino. Narxi {price} coin. Coin yetarli emas yoki Premium oling."
    Movie.objects.filter(pk=m.pk).update(views=F("views") + 1)
    log("movie", user.tg_id, m.code)
    return m, ""


def add_movie(title, code, video_id, photo_id, duration, vip, price):
    return Movie.objects.create(title=title, code=code, video_id=video_id, photo_id=photo_id,
                                duration=duration, is_vip=vip, price=price)


def del_movie(code):
    return Movie.objects.filter(code__iexact=code).delete()[0]


def channels():
    return list(Channel.objects.all())


def add_channel(chat, title, link):
    return Channel.objects.create(chat=chat, title=title, link=link)


def tariffs():
    return list(Tariff.objects.filter(is_active=True))


def config_card():
    c = SiteConfig.get()
    return f"💳 {c.card_number}\n👤 {c.card_holder}\n🏦 {c.bank}"


def set_card(num, holder, bank):
    c = SiteConfig.get()
    c.card_number, c.card_holder, c.bank = num, holder, bank
    c.save()


def payment_info(pid):
    p = Payment.objects.select_related("user", "tariff").get(pk=pid)
    return p, f"#{pid} {p.user.phone} @{p.user.tg_username}\n{p.tariff.name if p.tariff else ''} — {p.amount} so'm"


def order_info(pid):
    o = ServiceOrder.objects.select_related("user").get(pk=pid)
    return o, f"Buyurtma #{pid} {o.get_kind_display()}\n{o.user.phone} @{o.user.tg_username}\n{o.details} — {o.amount} so'm"

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from accounts.models import LoginCode, User
from . import services as svc
from .models import Action, Payment, ServiceOrder, SiteConfig, Tariff


def globals(request):
    return {"bot_link": f"https://t.me/{settings.BOT_USERNAME}", "cfg": SiteConfig.get()}


def home(request):
    return render(request, "home.html", {"actions": Action.objects.filter(is_active=True)[:5]})


def login_view(request):
    if request.user.is_authenticated:
        return redirect(request.GET.get("next") or "home")
    ctx = {}
    if request.method == "POST":
        phone = svc.norm_phone(request.POST.get("phone"))
        uname = svc.norm_user(request.POST.get("username"))
        u = User.objects.filter(phone=phone).first()
        if not u or not u.tg_id or svc.norm_user(u.tg_username) != uname:
            ctx["error"] = "Avval botga kirib /start bosing va raqamingizni ulashing. Raqam va username botdagi bilan bir xil bo'lishi kerak."
            ctx["need_bot"] = True
        elif u.is_blocked:
            ctx["error"] = "Siz bloklangansiz."
        elif LoginCode.too_soon(u):
            ctx["error"] = "Kod yaqinda yuborilgan. 45 soniya kuting."
        else:
            code = LoginCode.issue(u)
            if svc.tg_send(u.tg_id, f"🔐 Saytga kirish kodi: {code}\n5 daqiqa amal qiladi. Hech kimga bermang."):
                request.session["pending_uid"] = u.pk
                request.session["next"] = request.GET.get("next", "")
                return redirect("verify")
            ctx["error"] = "Kodni yuborib bo'lmadi. Botni bloklamaganingizni tekshiring."
    return render(request, "login.html", ctx)


def verify_view(request):
    u = User.objects.filter(pk=request.session.get("pending_uid")).first()
    if not u:
        return redirect("login")
    ctx = {}
    if request.method == "POST":
        if LoginCode.verify(u, request.POST.get("code", "")):
            nxt = request.session.pop("next", "") or "/"
            request.session.pop("pending_uid", None)
            login(request, u, backend="django.contrib.auth.backends.ModelBackend")
            svc.log("site_login", u.tg_id)
            return redirect(nxt if nxt.startswith("/") else "/")
        ctx["error"] = "Kod noto'g'ri yoki muddati tugagan."
    return render(request, "verify.html", ctx)


def logout_view(request):
    logout(request)
    return redirect("home")


@login_required
def premium(request):
    if request.method == "POST":
        p = svc.create_payment(request.user, int(request.POST["tariff"]))
        return redirect("pay", kind="pay", pk=p.pk)
    return render(request, "premium.html", {"tariffs": Tariff.objects.filter(is_active=True)})


@login_required
def services(request):
    if request.method == "POST":
        kind = request.POST.get("kind")
        if kind not in ("stars", "gift", "number", "coin"):
            return redirect("services")
        try:
            qty = max(1, min(int(request.POST.get("qty") or 1), 100000))
        except ValueError:
            qty = 1
        details = request.POST.get("details", "").strip()
        if kind in ("stars", "coin"):
            details = f"{details} miqdor: {qty}"
        o = svc.create_order(request.user, kind, details, qty)
        return redirect("pay", kind="ord", pk=o.pk)
    return render(request, "services.html")


@login_required
def pay(request, kind, pk):
    obj = get_object_or_404(Payment if kind == "pay" else ServiceOrder, pk=pk, user=request.user)
    return render(request, "pay.html", {"obj": obj, "kind": kind,
                                        "deep": f"https://t.me/{settings.BOT_USERNAME}?start={kind}_{pk}"})


@login_required
def promo(request):
    if request.method == "POST":
        messages.info(request, svc.redeem(request.user, request.POST.get("code", "")))
    return redirect("profile")


@login_required
def profile(request):
    return render(request, "profile.html", {
        "payments": Payment.objects.filter(user=request.user)[:10],
        "orders": ServiceOrder.objects.filter(user=request.user)[:10]})

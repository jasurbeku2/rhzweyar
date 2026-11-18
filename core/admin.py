from django.contrib import admin, messages
from . import services as svc
from .models import *


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not SiteConfig.objects.exists()


@admin.register(Tariff)
class TariffAdmin(admin.ModelAdmin):
    list_display = ("name", "days", "price", "is_active")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "tariff", "amount", "status", "created")
    list_filter = ("status",)
    actions = ["approve", "reject"]

    @admin.action(description="Tasdiqlash (Premium berish)")
    def approve(self, request, qs):
        n = sum(bool(svc.approve_payment(p.id, request.user)) for p in qs)
        self.message_user(request, f"{n} ta to'lov tasdiqlandi", messages.SUCCESS)

    @admin.action(description="Rad etish")
    def reject(self, request, qs):
        n = sum(bool(svc.reject_payment(p.id, request.user)) for p in qs)
        self.message_user(request, f"{n} ta to'lov rad etildi")


@admin.register(ServiceOrder)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "kind", "details", "amount", "status", "created")
    list_filter = ("status", "kind")
    actions = ["done", "reject"]

    @admin.action(description="Bajarildi deb belgilash")
    def done(self, request, qs):
        for o in qs:
            svc.finish_order(o.id, True)

    @admin.action(description="Rad etish")
    def reject(self, request, qs):
        for o in qs:
            svc.finish_order(o.id, False)


@admin.register(PromoCode)
class PromoAdmin(admin.ModelAdmin):
    list_display = ("code", "kind", "value", "used", "max_uses", "is_active")


admin.site.register(Action)
admin.site.register(Movie)
admin.site.register(Channel)


@admin.register(Log)
class LogAdmin(admin.ModelAdmin):
    list_display = ("created", "action", "user_tg", "info")

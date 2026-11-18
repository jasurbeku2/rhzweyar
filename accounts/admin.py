from django.contrib import admin
from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("phone", "tg_username", "tg_id", "role", "coins", "premium_until", "is_blocked")
    search_fields = ("phone", "tg_username", "tg_id")
    list_filter = ("role", "is_blocked")
    fields = ("phone", "tg_username", "tg_id", "role", "coins", "premium_until", "is_blocked")

    def get_readonly_fields(self, request, obj=None):  # rolni faqat super admin o'zgartiradi
        ro = ["tg_id"]
        if request.user.role != "super":
            ro.append("role")
        return ro

    def has_add_permission(self, request):
        return request.user.role == "super"

    def has_delete_permission(self, request, obj=None):
        return request.user.role == "super"

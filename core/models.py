from django.conf import settings
from django.db import models
from django.db.models import Q


class SiteConfig(models.Model):
    """Bitta qator: admin hamma narx va matnlarni shu yerda o'zgartiradi."""
    card_number = models.CharField("Karta raqami", max_length=30, default="0000 0000 0000 0000")
    card_holder = models.CharField("Karta egasi", max_length=80, default="Ism Familiya")
    bank = models.CharField("Bank", max_length=50, default="Bank")
    start_text = models.TextField("Start matni", default="Xush kelibsiz! Quyidagi bo'limlardan birini tanlang.")
    daily_coin = models.PositiveIntegerField("Premium kunlik coin", default=30)
    referral_bonus = models.PositiveIntegerField("Referal bonusi (coin)", default=10)
    vip_coin_price = models.PositiveIntegerField("VIP kino narxi (coin)", default=20)
    coin_price_som = models.PositiveIntegerField("1 coin narxi (so'm)", default=500)
    stars_price_som = models.PositiveIntegerField("1 Stars narxi (so'm)", default=250)
    gift_price_som = models.PositiveIntegerField("Premium gift narxi (so'm)", default=60000)
    number_price_som = models.PositiveIntegerField("Premium raqam narxi (so'm)", default=100000)
    movie_channel = models.CharField("Kino kanal havolasi", max_length=200, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "Sozlamalar"

    @classmethod
    def get(cls):
        return cls.objects.first() or cls.objects.create()

    def __str__(self):
        return "Sozlamalar"


class Tariff(models.Model):
    name = models.CharField(max_length=60)
    days = models.PositiveIntegerField("Muddat (kun)")
    price = models.PositiveIntegerField("Narx (so'm)")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} — {self.price} so'm"


class Payment(models.Model):
    STATUS = [("wait", "Chek kutilmoqda"), ("pending", "Tekshiruvda"), ("approved", "Tasdiqlangan"),
              ("rejected", "Rad etilgan"), ("expired", "Eskirgan")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    tariff = models.ForeignKey(Tariff, on_delete=models.SET_NULL, null=True)
    amount = models.PositiveIntegerField("Noyob summa")
    status = models.CharField(max_length=10, choices=STATUS, default="wait")
    check_unique_id = models.CharField(max_length=100, blank=True, db_index=True)
    created = models.DateTimeField(auto_now_add=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["amount"], condition=Q(status__in=["wait", "pending"]),
                                               name="unique_open_amount")]
        ordering = ["-id"]


class PromoCode(models.Model):
    code = models.CharField(max_length=40, unique=True)
    kind = models.CharField(max_length=10, choices=[("coin", "Coin"), ("premium", "Premium (kun)")])
    value = models.PositiveIntegerField("Miqdor (coin yoki kun)")
    max_uses = models.PositiveIntegerField(default=100)
    used = models.PositiveIntegerField(default=0, editable=False)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.code


class PromoUse(models.Model):
    promo = models.ForeignKey(PromoCode, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("promo", "user")


class Action(models.Model):
    """Aksiyalar: saytning bosh sahifasida chiqadi."""
    title = models.CharField(max_length=100)
    text = models.TextField()
    is_active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return self.title


class ServiceOrder(models.Model):
    KINDS = [("stars", "Telegram Stars"), ("gift", "Premium gift"), ("number", "Premium raqam"),
             ("coin", "Coin")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    kind = models.CharField(max_length=10, choices=KINDS)
    details = models.CharField("Tafsilot (username, miqdor...)", max_length=200)
    amount = models.PositiveIntegerField("Summa")
    status = models.CharField(max_length=10, default="wait",
                              choices=[("wait", "Chek kutilmoqda"), ("pending", "Tekshiruvda"),
                                       ("done", "Bajarildi"), ("rejected", "Rad etildi")])
    check_unique_id = models.CharField(max_length=100, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        constraints = [models.UniqueConstraint(fields=["amount"], condition=Q(status__in=["wait", "pending"]),
                                               name="unique_open_order_amount")]


class Movie(models.Model):
    title = models.CharField(max_length=150)
    code = models.CharField(max_length=30, unique=True)
    photo_id = models.CharField(max_length=300, blank=True)
    video_id = models.CharField(max_length=300)
    duration = models.PositiveIntegerField(default=0)
    is_vip = models.BooleanField(default=False)
    price = models.PositiveIntegerField("VIP narxi (coin)", default=0)
    views = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.code} {self.title}"


class Channel(models.Model):
    title = models.CharField(max_length=100)
    chat = models.CharField("@username yoki chat id", max_length=100)
    link = models.CharField(max_length=200)

    def __str__(self):
        return self.title


class Log(models.Model):
    action = models.CharField(max_length=60)
    user_tg = models.BigIntegerField(null=True, blank=True)
    info = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]

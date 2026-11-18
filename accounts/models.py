import hashlib, secrets
from datetime import timedelta
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    phone = models.CharField("Telefon", max_length=20, unique=True)
    tg_username = models.CharField(max_length=64, blank=True)
    tg_id = models.BigIntegerField(unique=True, null=True, blank=True)
    role = models.CharField(max_length=10, default="user",
                            choices=[("user", "User"), ("admin", "Admin"), ("super", "Super admin")])
    coins = models.IntegerField(default=0)
    is_blocked = models.BooleanField(default=False)
    premium_until = models.DateTimeField(null=True, blank=True)
    last_coin_date = models.DateField(null=True, blank=True)
    referred_by = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)

    @property
    def is_premium(self):
        return bool(self.premium_until and self.premium_until > timezone.now())

    @property
    def is_admin_role(self):
        return self.role in ("admin", "super")

    def save(self, *a, **kw):
        if not self.username:
            self.username = "u" + "".join(c for c in self.phone if c.isdigit())
        self.is_staff = self.is_admin_role
        self.is_superuser = self.is_admin_role
        if self.password == "":
            self.set_unusable_password()
        super().save(*a, **kw)

    def __str__(self):
        return f"{self.phone} @{self.tg_username}"


class LoginCode(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    code_hash = models.CharField(max_length=64, db_index=True)
    created = models.DateTimeField(auto_now_add=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    used = models.BooleanField(default=False)

    @staticmethod
    def hash(code):
        return hashlib.sha256(code.encode()).hexdigest()

    @classmethod
    def issue(cls, user):
        cls.objects.filter(user=user, used=False).update(used=True)
        while True:
            code = f"{secrets.randbelow(10**6):06d}"
            h = cls.hash(code)
            if not cls.objects.filter(user=user, code_hash=h).exists():  # kod takrorlanmaydi
                cls.objects.create(user=user, code_hash=h)
                return code

    @classmethod
    def verify(cls, user, code):
        obj = cls.objects.filter(user=user, used=False,
                                 created__gte=timezone.now() - timedelta(minutes=5)).last()
        if not obj or obj.attempts >= 5:
            return False
        obj.attempts += 1
        ok = secrets.compare_digest(obj.code_hash, cls.hash(code.strip()))
        if ok:
            obj.used = True
        obj.save()
        return ok

    @classmethod
    def too_soon(cls, user):
        return cls.objects.filter(user=user, created__gte=timezone.now() - timedelta(seconds=45)).exists()

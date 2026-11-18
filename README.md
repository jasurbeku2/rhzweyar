# Telegram bot + Django sayt

## Ishga tushirish (Railway)
1. GitHub'ga **Private** repo qilib hamma fayllarni yuklang.
2. Railway → New Project → shu repo. **+ New → PostgreSQL** qo'shing (baza doimiy saqlanishi uchun shart).
3. Variables: `.env.example` dagi hammasini kiriting (`DATABASE_URL` ni PostgreSQL'dan ulang).
4. Deploy. Bot va sayt bitta serviceda ishlaydi (`start.sh`).
5. Botda `/start` bosing, raqamni ulashing: siz super admin bo'lasiz.
6. Saytda `/admin/` ga o'ting (kod botga keladi). Tariflar, karta, narxlarni shu yerda kiriting.

## Lokal sinov
pip install -r requirements.txt
export BOT_TOKEN=... BOT_USERNAME=... DEBUG=1
python manage.py makemigrations accounts core && python manage.py migrate
python manage.py ensure_super && python manage.py runbot &
python manage.py runserver

## Bot buyruqlari
Super admin: /addadmin, /deladmin, /admins
Admin: /addmovie, /delmovie KOD, /stats, /setcard, /addchannel @kanal, /ban ID, /unban ID, /send (xabarga reply)
Hamma: /start, /promo KOD

#!/bin/sh
python manage.py makemigrations accounts core --noinput
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py ensure_super
python manage.py runbot &
exec gunicorn config.wsgi --bind 0.0.0.0:${PORT:-8000} --workers 2

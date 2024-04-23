#!/bin/sh
echo "Running Migrations"
./manage.py migrate
echo "creating superuser"
./manage.py createsuperuser
echo "Starting Server"
./manage.py runserver 0.0.0.0:8001

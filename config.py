#This file stores database settings & secret key.
# config.py
# ------------------------------------
# This file holds all configurations
# like Secret Key, Database connection
# details, Email settings, Razorpay keys etc.
# ------------------------------------

SECRET_KEY = ""  # used for sessions

# MySQL Database Configuration
import os

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_PORT = int(os.getenv("DB_PORT", 3306))


# config.py
# ------------------------------------------
# Stores all configuration settings
# ------------------------------------------





# Email SMTP Settings
MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USERNAME = ''
MAIL_PASSWORD = ''   # Gmail App Password


# Razorpay Configuration
RAZORPAY_KEY_ID = ""
RAZORPAY_KEY_SECRET = ""

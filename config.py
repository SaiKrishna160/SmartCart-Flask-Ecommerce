#This file stores database settings & secret key.
# config.py
# ------------------------------------
# This file holds all configurations
# like Secret Key, Database connection
# details, Email settings, Razorpay keys etc.
# ------------------------------------

SECRET_KEY = "CHANTI"  # used for sessions

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
MAIL_USERNAME = 'mushamsaikrishna4@gmail.com'
MAIL_PASSWORD = 'fzpn sssf xmzn zkzg'   # Gmail App Password


# Razorpay Configuration
RAZORPAY_KEY_ID = "rzp_test_Sq2lxd6i9ukhJO"
RAZORPAY_KEY_SECRET = "bO6zXHc0BbqehgYUTHInap0W"
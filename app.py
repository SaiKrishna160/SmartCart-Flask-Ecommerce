# app.py
# ---------------------------------------------------------
# SmartCart — Full Flask E-Commerce App 
# ---------------------------------------------------------

from flask import Flask, render_template, request, redirect, session, flash, jsonify
from flask_mail import Mail, Message
import mysql.connector
import bcrypt
import random
import time
import config
import razorpay
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)

# ─────────────────────────────────────────────────────────
# RAZORPAY CLIENT
# ─────────────────────────────────────────────────────────
razorpay_client = razorpay.Client(
    auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET)
)

app.secret_key = config.SECRET_KEY

# ─────────────────────────────────────────────────────────
# EMAIL CONFIGURATION
# ─────────────────────────────────────────────────────────
app.config['MAIL_SERVER']   = config.MAIL_SERVER
app.config['MAIL_PORT']     = config.MAIL_PORT
app.config['MAIL_USE_TLS']  = config.MAIL_USE_TLS
app.config['MAIL_USERNAME'] = config.MAIL_USERNAME
app.config['MAIL_PASSWORD'] = config.MAIL_PASSWORD

mail = Mail(app)

# ─────────────────────────────────────────────────────────
# UPLOAD FOLDER CONFIGURATION
# ─────────────────────────────────────────────────────────
PRODUCT_UPLOAD_FOLDER = 'static/uploads/product_images'
ADMIN_UPLOAD_FOLDER   = 'static/uploads/admin_images'   # ✅ FIX: was missing in original

app.config['UPLOAD_FOLDER']       = PRODUCT_UPLOAD_FOLDER
app.config['ADMIN_UPLOAD_FOLDER'] = ADMIN_UPLOAD_FOLDER

os.makedirs(PRODUCT_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(ADMIN_UPLOAD_FOLDER,   exist_ok=True)

# ─────────────────────────────────────────────────────────
# OTP EXPIRY (seconds)
# ─────────────────────────────────────────────────────────
OTP_EXPIRY_SECONDS = 300  # 5 minutes


# =================================================================
# HELPERS
# =================================================================

def get_db_connection():
    """Return a fresh MySQL connection."""
    return mysql.connector.connect(
    host=config.DB_HOST,
    user=config.DB_USER,
    password=config.DB_PASSWORD,
    database=config.DB_NAME,
    port=config.DB_PORT
)
    )


def is_admin_logged_in():
    """Return True if an admin session exists."""
    return 'admin_id' in session


def is_user_logged_in():
    """Return True if a user session exists."""
    return 'user_id' in session


def hash_password(plain_password: str) -> bytes:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt())


def check_password(plain_password: str, hashed) -> bool:
    """
    Safely compare a plain password against a bcrypt hash.
    Accepts the hash as str or bytes.
    """
    if isinstance(hashed, str):
        hashed = hashed.encode('utf-8')
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed)


# =================================================================
# ROUTE 0: ROOT — Redirect to Login
# =================================================================
@app.route('/')
def home():
    return redirect('/admin-login')


# =================================================================
# ROUTE 1: ADMIN SIGNUP — Send OTP
# =================================================================
@app.route('/admin-signup', methods=['GET', 'POST'])
def admin_signup():

    if request.method == 'GET':
        return render_template('admin/admin_signup.html')

    name  = request.form['name'].strip()
    email = request.form['email'].strip().lower()

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT admin_id FROM admin WHERE email=%s", (email,))
    existing = cursor.fetchone()
    cursor.close()
    conn.close()

    if existing:
        flash("This email is already registered. Please login instead.", "danger")
        return redirect('/admin-signup')

    # Store signup data in session
    session['signup_name']  = name
    session['signup_email'] = email

    # Generate OTP with timestamp  ✅ FIX: OTP now has expiry
    otp = random.randint(100000, 999999)
    session['otp']          = otp
    session['otp_created']  = time.time()

    msg = Message(
        subject="SmartCart Admin OTP",
        sender=config.MAIL_USERNAME,
        recipients=[email]
    )
    msg.body = (
        f"Hello {name},\n\n"
        f"Your OTP for SmartCart Admin Registration is: {otp}\n"
        f"This OTP is valid for {OTP_EXPIRY_SECONDS // 60} minutes.\n\n"
        f"If you did not request this, please ignore this email."
    )
    mail.send(msg)

    flash("OTP sent to your email!", "success")
    return redirect('/verify-otp')


# =================================================================
# ROUTE 2: DISPLAY OTP PAGE
# =================================================================
@app.route('/verify-otp', methods=['GET'])
def verify_otp_get():
    return render_template('admin/verify_otp.html')


# =================================================================
# ROUTE 3: VERIFY OTP + SAVE ADMIN
# =================================================================
@app.route('/verify-otp', methods=['POST'])
def verify_otp_post():

    user_otp = request.form.get('otp', '').strip()
    password = request.form.get('password', '')

    # ✅ FIX: Check OTP expiry
    otp_created = session.get('otp_created', 0)
    if time.time() - otp_created > OTP_EXPIRY_SECONDS:
        flash("OTP has expired. Please sign up again.", "danger")
        session.pop('otp', None)
        session.pop('otp_created', None)
        return redirect('/admin-signup')

    if str(session.get('otp')) != user_otp:
        flash("Invalid OTP. Try again!", "danger")
        return redirect('/verify-otp')

    hashed_pw = hash_password(password)

    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO admin (name, email, password) VALUES (%s, %s, %s)",
        (session['signup_name'], session['signup_email'], hashed_pw)
    )
    conn.commit()
    cursor.close()
    conn.close()

    # Clear temporary session keys
    for key in ('otp', 'otp_created', 'signup_name', 'signup_email'):
        session.pop(key, None)

    flash("Admin Registered Successfully!", "success")
    return redirect('/admin-login')


# =================================================================
# ROUTE 4: ADMIN LOGIN
# =================================================================
@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():

    if request.method == 'GET':
        return render_template('admin/admin_login.html')

    email    = request.form['email'].strip().lower()
    password = request.form['password']

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM admin WHERE email=%s", (email,))
    admin = cursor.fetchone()
    cursor.close()
    conn.close()

    if not admin:
        flash("Email not found! Please register first.", "danger")
        return redirect('/admin-login')

    # ✅ FIX: use helper that handles str/bytes safely
    if not check_password(password, admin['password']):
        flash("Incorrect password! Try again.", "danger")
        return redirect('/admin-login')

    session['admin_id']    = admin['admin_id']
    session['admin_name']  = admin['name']
    session['admin_email'] = admin['email']

    flash("Login Successful!", "success")
    return redirect('/admin-dashboard')


# =================================================================
# ROUTE 5: ADMIN DASHBOARD (Protected)
# =================================================================
@app.route('/admin-dashboard')
def admin_dashboard():

    if not is_admin_logged_in():
        flash("Please login to access dashboard!", "danger")
        return redirect('/admin-login')

    return render_template('admin/dashboard.html', admin_name=session['admin_name'])


# =================================================================
# ROUTE 6: ADMIN LOGOUT
# =================================================================
@app.route('/admin-logout')
def admin_logout():

    for key in ('admin_id', 'admin_name', 'admin_email'):
        session.pop(key, None)

    flash("Logged out successfully.", "success")
    return redirect('/admin-login')


# =================================================================
# ROUTE 7 & 8: ADD PRODUCT (GET + POST)
# =================================================================
@app.route('/admin/add-item', methods=['GET', 'POST'])
def add_item():

    if not is_admin_logged_in():
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    if request.method == 'GET':
        return render_template('admin/add_item.html')

    name        = request.form['name'].strip()
    description = request.form['description'].strip()
    category    = request.form['category'].strip()
    price       = request.form['price']
    image_file  = request.files['image']

    if not image_file or image_file.filename == '':
        flash("Please upload a product image!", "danger")
        return redirect('/admin/add-item')

    filename   = secure_filename(image_file.filename)
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    image_file.save(image_path)

    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (name, description, category, price, image) VALUES (%s, %s, %s, %s, %s)",
        (name, description, category, price, filename)
    )
    conn.commit()
    cursor.close()
    conn.close()

    flash("Product added successfully!", "success")
    return redirect('/admin/add-item')


# =================================================================
# ROUTE 9: DISPLAY ALL PRODUCTS (Admin)
# =================================================================
@app.route('/admin/item-list')
def item_list():

    if not is_admin_logged_in():
        flash("Please login!", "danger")
        return redirect('/admin-login')

    search          = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT DISTINCT category FROM products")
    categories = cursor.fetchall()

    query  = "SELECT * FROM products WHERE 1=1"
    params = []

    if search:
        query += " AND name LIKE %s"
        params.append(f"%{search}%")

    if category_filter:
        query += " AND category = %s"
        params.append(category_filter)

    cursor.execute(query, params)
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'admin/item_list.html',
        products=products,
        categories=categories
    )


# =================================================================
# ROUTE 10: VIEW SINGLE PRODUCT
# =================================================================
@app.route('/admin/view-item/<int:item_id>')
def view_item(item_id):

    if not is_admin_logged_in():
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products WHERE product_id = %s", (item_id,))
    product = cursor.fetchone()
    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    return render_template('admin/view_item.html', product=product)


# =================================================================
# ROUTE 11 & 12: UPDATE PRODUCT (GET + POST)
# =================================================================
@app.route('/admin/update-item/<int:item_id>', methods=['GET', 'POST'])
def update_item(item_id):

    if not is_admin_logged_in():
        flash("Please login!", "danger")
        return redirect('/admin-login')

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products WHERE product_id = %s", (item_id,))
    product = cursor.fetchone()

    if not product:
        flash("Product not found!", "danger")
        cursor.close()
        conn.close()
        return redirect('/admin/item-list')

    if request.method == 'GET':
        cursor.close()
        conn.close()
        return render_template('admin/update_item.html', product=product)

    # POST
    name        = request.form['name'].strip()
    description = request.form['description'].strip()
    category    = request.form['category'].strip()
    price       = request.form['price']
    new_image   = request.files.get('image')

    old_image_name  = product['image']
    final_image_name = old_image_name

    if new_image and new_image.filename != '':
        new_filename = secure_filename(new_image.filename)
        new_image.save(os.path.join(app.config['UPLOAD_FOLDER'], new_filename))

        old_path = os.path.join(app.config['UPLOAD_FOLDER'], old_image_name)
        if old_image_name and os.path.exists(old_path):
            os.remove(old_path)

        final_image_name = new_filename

    cursor.execute(
        """UPDATE products
           SET name=%s, description=%s, category=%s, price=%s, image=%s
           WHERE product_id=%s""",
        (name, description, category, price, final_image_name, item_id)
    )
    conn.commit()
    cursor.close()
    conn.close()

    flash("Product updated successfully!", "success")
    return redirect('/admin/item-list')


# =================================================================
# ROUTE 13: DELETE PRODUCT
# =================================================================
@app.route('/admin/delete-item/<int:item_id>')
def delete_item(item_id):

    if not is_admin_logged_in():
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT image FROM products WHERE product_id=%s", (item_id,))
    product = cursor.fetchone()

    if not product:
        flash("Product not found!", "danger")
        cursor.close()
        conn.close()
        return redirect('/admin/item-list')

    image_path = os.path.join(app.config['UPLOAD_FOLDER'], product['image'])
    if product['image'] and os.path.exists(image_path):
        os.remove(image_path)

    cursor.execute("DELETE FROM products WHERE product_id=%s", (item_id,))
    conn.commit()
    cursor.close()
    conn.close()

    flash("Product deleted successfully!", "success")
    return redirect('/admin/item-list')


# =================================================================
# ROUTE 14 & 15: ADMIN PROFILE (GET + POST)
# =================================================================
@app.route('/admin/profile', methods=['GET', 'POST'])
def admin_profile():

    if not is_admin_logged_in():
        flash("Please login!", "danger")
        return redirect('/admin-login')

    admin_id = session['admin_id']

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM admin WHERE admin_id=%s", (admin_id,))
    admin = cursor.fetchone()

    if request.method == 'GET':
        cursor.close()
        conn.close()
        return render_template('admin/admin_profile.html', admin=admin)

    # POST — update profile
    name         = request.form['name'].strip()
    email        = request.form['email'].strip().lower()
    new_password = request.form.get('password', '').strip()
    new_image    = request.files.get('profile_image')

    old_image_name   = admin.get('profile_image')
    final_image_name = old_image_name

    # Password: only update if a new one was provided
    hashed_pw = hash_password(new_password) if new_password else admin['password']

    # Image handling
    if new_image and new_image.filename != '':
        new_filename = secure_filename(new_image.filename)
        new_image.save(os.path.join(app.config['ADMIN_UPLOAD_FOLDER'], new_filename))

        if old_image_name:
            old_path = os.path.join(app.config['ADMIN_UPLOAD_FOLDER'], old_image_name)
            if os.path.exists(old_path):
                os.remove(old_path)

        final_image_name = new_filename

    cursor.execute(
        """UPDATE admin
           SET name=%s, email=%s, password=%s, profile_image=%s
           WHERE admin_id=%s""",
        (name, email, hashed_pw, final_image_name, admin_id)
    )
    conn.commit()
    cursor.close()
    conn.close()

    session['admin_name']  = name
    session['admin_email'] = email

    flash("Profile updated successfully!", "success")
    return redirect('/admin/profile')


# =================================================================
# ROUTE 16: USER REGISTER
# =================================================================
@app.route('/user-register', methods=['GET', 'POST'])
def user_register():

    if request.method == 'GET':
        return render_template('user/user_register.html')

    name     = request.form['name'].strip()
    email    = request.form['email'].strip().lower()
    password = request.form['password']

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT user_id FROM users WHERE email=%s", (email,))
    existing = cursor.fetchone()

    if existing:
        cursor.close()
        conn.close()
        flash("Email already registered!", "danger")
        return redirect('/user-register')

    cursor.execute(
        "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
        (name, email, hash_password(password))
    )
    conn.commit()
    cursor.close()
    conn.close()

    flash("Registration successful! Please login.", "success")
    return redirect('/user-login')


# =================================================================
# ROUTE 17: USER LOGIN
# =================================================================
@app.route('/user-login', methods=['GET', 'POST'])
def user_login():

    if request.method == 'GET':
        return render_template('user/user_login.html')

    email    = request.form['email'].strip().lower()
    password = request.form['password']

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if not user:
        flash("Email not found!", "danger")
        return redirect('/user-login')

    # ✅ FIX: use helper — avoids double-encoding bug from original
    if not check_password(password, user['password']):
        flash("Incorrect password!", "danger")
        return redirect('/user-login')

    session['user_id']    = user['user_id']
    session['user_name']  = user['name']
    session['user_email'] = user['email']

    flash("Login successful!", "success")
    return redirect('/user-dashboard')


# =================================================================
# ROUTE 18: USER DASHBOARD
# =================================================================
@app.route('/user-dashboard')
def user_dashboard():

    if not is_user_logged_in():
        flash("Please login first!", "danger")
        return redirect('/user-login')

    return render_template('user/user_home.html', user_name=session['user_name'])


# =================================================================
# ROUTE 19: USER LOGOUT
# =================================================================
@app.route('/user-logout')
def user_logout():

    for key in ('user_id', 'user_name', 'user_email'):
        session.pop(key, None)

    flash("Logged out successfully!", "success")
    return redirect('/user-login')


# =================================================================
# ROUTE 20: USER PRODUCTS (Browse + Filter)
# =================================================================
@app.route('/user/products')
def user_products():

    if not is_user_logged_in():
        flash("Please login!", "danger")
        return redirect('/user-login')

    search          = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT DISTINCT category FROM products")
    categories = cursor.fetchall()

    query  = "SELECT * FROM products WHERE 1=1"
    params = []

    if search:
        query += " AND name LIKE %s"
        params.append(f"%{search}%")

    if category_filter:
        query += " AND category=%s"
        params.append(category_filter)

    cursor.execute(query, params)
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'user/user_products.html',
        products=products,
        categories=categories
    )


# =================================================================
# ROUTE 21: PRODUCT DETAILS
# =================================================================
@app.route('/user/product/<int:product_id>')
def user_product_details(product_id):

    if not is_user_logged_in():
        flash("Please login!", "danger")
        return redirect('/user-login')

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products WHERE product_id=%s", (product_id,))
    product = cursor.fetchone()
    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/user/products')

    return render_template('user/product_details.html', product=product)


# =================================================================
# ROUTE 22: ADD TO CART
# =================================================================
@app.route('/user/add-to-cart/<int:product_id>')
def add_to_cart(product_id):

    if not is_user_logged_in():
        flash("Please login first!", "danger")
        return redirect('/user-login')

    if 'cart' not in session:
        session['cart'] = {}

    cart = session['cart']

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products WHERE product_id=%s", (product_id,))
    product = cursor.fetchone()
    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/user/products')

    pid = str(product_id)

    if pid in cart:
        cart[pid]['quantity'] += 1
    else:
        cart[pid] = {
            'name':     product['name'],
            'price':    float(product['price']),
            'image':    product['image'],
            'quantity': 1
        }

    session['cart'] = cart
    flash("Item added to cart!", "success")
    return redirect('/user/cart')


# =================================================================
# ROUTE 23: VIEW CART
# =================================================================
@app.route('/user/cart')
def view_cart():

    if not is_user_logged_in():
        flash("Please login first!", "danger")
        return redirect('/user-login')

    cart        = session.get('cart', {})
    grand_total = sum(i['price'] * i['quantity'] for i in cart.values())

    return render_template('user/cart.html', cart=cart, grand_total=grand_total)


# =================================================================
# ROUTE 24: INCREASE QUANTITY
# =================================================================
@app.route('/user/cart/increase/<pid>')
def increase_quantity(pid):

    cart = session.get('cart', {})
    if pid in cart:
        cart[pid]['quantity'] += 1
    session['cart'] = cart
    return redirect('/user/cart')


# =================================================================
# ROUTE 25: DECREASE QUANTITY
# =================================================================
@app.route('/user/cart/decrease/<pid>')
def decrease_quantity(pid):

    cart = session.get('cart', {})
    if pid in cart:
        cart[pid]['quantity'] -= 1
        if cart[pid]['quantity'] <= 0:
            cart.pop(pid)
    session['cart'] = cart
    return redirect('/user/cart')


# =================================================================
# ROUTE 26: REMOVE ITEM FROM CART
# =================================================================
@app.route('/user/cart/remove/<pid>')
def remove_from_cart(pid):

    cart = session.get('cart', {})
    cart.pop(pid, None)
    session['cart'] = cart

    flash("Item removed!", "success")
    return redirect('/user/cart')


# =================================================================
# ROUTE 27: CHECKOUT — Create Razorpay Order
# =================================================================
@app.route('/checkout')
def checkout():

    if not is_user_logged_in():
        flash("Please login first!", "danger")
        return redirect('/user-login')

    cart = session.get('cart', {})
    if not cart:
        flash("Cart is empty!", "danger")
        return redirect('/user/products')

    grand_total      = sum(i['price'] * i['quantity'] for i in cart.values())
    amount_in_paise  = int(grand_total * 100)

    payment_order = razorpay_client.order.create({
        'amount':          amount_in_paise,
        'currency':        'INR',
        'payment_capture': '1'
    })

    return render_template(
        'user/payment.html',
        amount=grand_total,
        razorpay_key=config.RAZORPAY_KEY_ID,
        order_id=payment_order['id']
    )


# =================================================================
# ROUTE 28: PAYMENT SUCCESS — Verify Signature + Save Order
# ✅ FIX: Original had no verification; anyone could hit this URL
# =================================================================
@app.route('/payment-success', methods=['GET', 'POST'])
def payment_success():

    # Clear cart
    session.pop('cart', None)

    return '''

    <h1>Payment Successful!</h1>

    <a href="/user/products">
        Continue Shopping
    </a>

    '''
def payment_success():

    if not is_user_logged_in():
        return redirect('/user-login')

    # Razorpay sends these fields on successful payment
    razorpay_order_id   = request.form.get('razorpay_order_id')
    razorpay_payment_id = request.form.get('razorpay_payment_id')
    razorpay_signature  = request.form.get('razorpay_signature')

    # ✅ Verify payment signature
    params = {
        'razorpay_order_id':   razorpay_order_id,
        'razorpay_payment_id': razorpay_payment_id,
        'razorpay_signature':  razorpay_signature
    }

    try:
        razorpay_client.utility.verify_payment_signature(params)
    except razorpay.errors.SignatureVerificationError:
        flash("Payment verification failed! Please contact support.", "danger")
        return redirect('/user/cart')

    # ✅ Save order to database
    cart        = session.get('cart', {})
    grand_total = sum(i['price'] * i['quantity'] for i in cart.values())

    conn   = get_db_connection()
    cursor = conn.cursor()

    # Insert into orders table
    cursor.execute(
        """INSERT INTO orders (user_id, razorpay_order_id, razorpay_payment_id, total_amount, status)
           VALUES (%s, %s, %s, %s, 'paid')""",
        (session['user_id'], razorpay_order_id, razorpay_payment_id, grand_total)
    )
    order_db_id = cursor.lastrowid

    # Insert each cart item into order_items table
    for pid, item in cart.items():
        cursor.execute(
            """INSERT INTO order_items (order_id, product_id, quantity, price)
               VALUES (%s, %s, %s, %s)""",
            (order_db_id, int(pid), item['quantity'], item['price'])
        )

    conn.commit()
    cursor.close()
    conn.close()

    # Clear cart
    session.pop('cart', None)

    flash("Payment Successful! Your order has been placed.", "success")
    return redirect('/user/orders')


# =================================================================
# ROUTE 29: USER ORDER HISTORY
# =================================================================
@app.route('/user/orders')
def user_orders():

    if not is_user_logged_in():
        flash("Please login first!", "danger")
        return redirect('/user-login')

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM orders WHERE user_id=%s ORDER BY created_at DESC",
        (session['user_id'],)
    )
    orders = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('user/orders.html', orders=orders)


# =================================================================
# RUN
# =================================================================
if __name__ == '__main__':
    app.run(debug=True)
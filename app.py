import os
import sqlite3
from flask import Flask, render_template, g, redirect, url_for, request, jsonify, session
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

DATABASE = 'database.db'
template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.secret_key = 'change_this_to_random_secret_key'


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()

        if user and check_password_hash(user['password'], password):
            session['logged_in'] = True
            session['username'] = user['username']
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid username or password')

    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if not username or not password:
            return render_template('signup.html', error="All fields are required")

        db = get_db()
        cursor = db.cursor()

        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            return render_template('signup.html', error="Username already taken")

        hashed_pw = generate_password_hash(password)
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_pw))
        db.commit()

        return redirect(url_for('login'))

    return render_template('signup.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT COUNT(*) AS total_orders, SUM(total) AS total_revenue FROM transactions")
    summary = cursor.fetchone()
    total_orders = summary['total_orders'] or 0
    total_revenue = summary['total_revenue'] or 0

    cursor.execute("SELECT COUNT(id) FROM products")
    total_products = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT category) FROM products")
    total_categories = cursor.fetchone()[0]

    cursor.execute(
        "SELECT id, customer_name, order_date, total, payment_method FROM transactions ORDER BY id DESC LIMIT 5")
    recent_orders = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT p.id, p.name, SUM(oi.quantity) AS qty, p.price, SUM(oi.quantity * oi.price_at_sale) AS sales
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        GROUP BY p.id, p.name, p.price
        ORDER BY sales DESC LIMIT 5
    """)
    best_selling_products = [dict(row) for row in cursor.fetchall()]

    cursor.execute(
        "SELECT strftime('%Y-%m-%d', order_date) AS date, SUM(total) AS daily_revenue FROM transactions GROUP BY date ORDER BY date ASC")
    earnings_by_date = [dict(row) for row in cursor.fetchall()]
    revenue_values = [item['daily_revenue'] for item in earnings_by_date]

    context = {
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'total_products': total_products,
        'total_categories': total_categories,
        'recent_orders': recent_orders,
        'best_selling_products': best_selling_products,
        'earnings_by_date': revenue_values,
        'currency': 'PHP'
    }
    return render_template('dashboard.html', **context)


@app.route('/register')
@login_required
def index():
    return redirect(url_for('create_order'))


@app.route('/api/products', methods=['GET'])
@login_required
def api_products():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, name, price, category FROM products ORDER BY name ASC")
    products = [dict(row) for row in cursor.fetchall()]
    return jsonify({'products': products})


@app.route('/product_list')
@login_required
def product_list():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, name, price, category FROM products ORDER BY id DESC")
    products = [dict(row) for row in cursor.fetchall()]
    return render_template('product_list.html', products=products)


@app.route('/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        category = request.form['category']

        if not name or not price:
            return render_template('add_product.html', error='Name and price required.')

        try:
            price = float(price)
            db = get_db()
            db.execute("INSERT INTO products (name, price, category) VALUES (?, ?, ?)", (name, price, category))
            db.commit()
            return redirect(url_for('product_list'))
        except Exception as e:
            return render_template('add_product.html', error=f'Error: {e}')

    return render_template('add_product.html')


@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    db = get_db()
    cursor = db.cursor()

    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        category = request.form['category']

        try:
            price = float(price)
            cursor.execute("UPDATE products SET name = ?, price = ?, category = ? WHERE id = ?",
                           (name, price, category, product_id))
            db.commit()
            return redirect(url_for('product_list'))
        except Exception as e:
            return render_template('edit_product.html',
                                   product={'id': product_id, 'name': name, 'price': price, 'category': category},
                                   error=str(e))

    cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = cursor.fetchone()
    return render_template('edit_product.html', product=dict(product))


@app.route('/delete_product/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    db = get_db()
    db.execute("DELETE FROM products WHERE id = ?", (product_id,))
    db.commit()
    return redirect(url_for('product_list'))


@app.route('/create_order', methods=['GET', 'POST'])
@login_required
def create_order():
    if request.method == 'POST':
        db = get_db()
        cursor = db.cursor()
        try:
            data = request.get_json()
            customer_name = data.get('customer_name', 'Walk-in Customer')
            total = data.get('total')
            payment_method = data.get('payment_method')
            cart_items = data.get('cart', [])

            card_number = data.get('card_number', None)
            card_expiry = data.get('card_expiry', None)
            card_cvv = data.get('card_cvv', None)

            if not total or not payment_method or not cart_items:
                return jsonify({'success': False, 'message': 'Missing data'}), 400

            order_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            db.execute("BEGIN TRANSACTION")

            cursor.execute(
                """INSERT INTO transactions 
                   (customer_name, order_date, total, payment_method, card_number, card_expiry, card_cvv) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (customer_name, order_date, total, payment_method, card_number, card_expiry, card_cvv)
            )
            transaction_id = cursor.lastrowid

            for item in cart_items:
                cursor.execute(
                    "INSERT INTO order_items (transaction_id, product_id, quantity, price_at_sale) VALUES (?, ?, ?, ?)",
                    (transaction_id, item['id'], item['qty'], item['price'])
                )

            db.execute("COMMIT")
            return jsonify({'success': True, 'message': 'Billing Successful', 'transaction_id': transaction_id})

        except Exception as e:
            db.execute("ROLLBACK")
            return jsonify({'success': False, 'message': str(e)}), 500

    return render_template('create_order.html')


@app.route('/sales_report')
@login_required
def sales_report():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, customer_name, order_date, total, payment_method FROM transactions ORDER BY id DESC")
    transactions = [dict(row) for row in cursor.fetchall()]
    cursor.execute("SELECT SUM(total) FROM transactions")
    grand_total = cursor.fetchone()[0] or 0.00
    return render_template('sales_report.html', transactions=transactions, grand_total=grand_total)


@app.route('/delete_transaction/<int:transaction_id>', methods=['POST'])
@login_required
def delete_transaction(transaction_id):
    db = get_db()
    db.execute("DELETE FROM order_items WHERE transaction_id = ?", (transaction_id,))
    db.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
    db.commit()
    return redirect(url_for('dashboard'))


if __name__ == '__main__':
    app.run(debug=True)
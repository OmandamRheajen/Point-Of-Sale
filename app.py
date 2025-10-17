import os
import sqlite3
from flask import Flask, render_template, g, redirect, url_for, request
from datetime import datetime

DATABASE = 'database.db'
template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()

        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS products
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY
                           AUTOINCREMENT,
                           name
                           TEXT
                           NOT
                           NULL,
                           price
                           REAL
                           NOT
                           NULL,
                           category
                           TEXT
                       )
                       """)

        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS transactions
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY
                           AUTOINCREMENT,
                           customer_name
                           TEXT,
                           order_date
                           TEXT
                           NOT
                           NULL,
                           total
                           REAL
                           NOT
                           NULL,
                           payment_method
                           TEXT
                           NOT
                           NULL
                       )
                       """)

        db.commit()


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


@app.route('/')
def dashboard_redirect():
    return redirect(url_for('dashboard'))


@app.route('/register')
def index():
    return render_template('index.html')


@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        category = request.form['category']

        if not name or not price:
            return render_template('add_product.html', error='Product name and price are required.')

        try:
            price = float(price)
            db = get_db()
            cursor = db.cursor()
            cursor.execute(
                "INSERT INTO products (name, price, category) VALUES (?, ?, ?)",
                (name, price, category)
            )
            db.commit()
            return redirect(url_for('product_list'))
        except ValueError:
            return render_template('add_product.html', error='Invalid price format.')
        except Exception as e:
            return render_template('add_product.html', error=f'Database error: {e}')

    return render_template('add_product.html')


@app.route('/product_list')
def product_list():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, name, price, category FROM products ORDER BY id DESC")
    products = [dict(row) for row in cursor.fetchall()]
    return render_template('product_list.html', products=products)


@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    db = get_db()
    cursor = db.cursor()

    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        category = request.form['category']

        if not name or not price:
            cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
            product = dict(cursor.fetchone())
            return render_template('edit_product.html', product=product, error='Product name and price are required.')

        try:
            price = float(price)
            cursor.execute(
                "UPDATE products SET name = ?, price = ?, category = ? WHERE id = ?",
                (name, price, category, product_id)
            )
            db.commit()
            return redirect(url_for('product_list'))
        except ValueError:
            cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
            product = dict(cursor.fetchone())
            return render_template('edit_product.html', product=product, error='Invalid price format.')
        except Exception as e:
            cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
            product = dict(cursor.fetchone())
            return render_template('edit_product.html', product=product, error=f'Database error: {e}')

    cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = cursor.fetchone()

    if product is None:
        return redirect(url_for('product_list'))

    return render_template('edit_product.html', product=dict(product))


@app.route('/delete_product/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
    db.commit()
    return redirect(url_for('product_list'))


@app.route('/create_order', methods=['GET', 'POST'])
def create_order():
    if request.method == 'POST':
        customer_name = request.form.get('customer_name') or 'Walk-in Customer'
        total = request.form['total']
        payment_method = request.form['payment_method']
        order_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if not total or not payment_method:
            return render_template('create_order.html', error='Total amount and payment method are required.')

        try:
            total = float(total)
            db = get_db()
            cursor = db.cursor()
            cursor.execute(
                "INSERT INTO transactions (customer_name, order_date, total, payment_method) VALUES (?, ?, ?, ?)",
                (customer_name, order_date, total, payment_method)
            )
            db.commit()
            return redirect(url_for('dashboard'))
        except ValueError:
            return render_template('create_order.html', error='Invalid total amount format.')
        except Exception as e:
            return render_template('create_order.html', error=f'Database error: {e}')

    return render_template('create_order.html')


@app.route('/sales_report')
def sales_report():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, customer_name, order_date, total, payment_method FROM transactions ORDER BY id DESC")
    transactions = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT SUM(total) FROM transactions")
    grand_total = cursor.fetchone()[0] or 0.00

    return render_template('sales_report.html', transactions=transactions, grand_total=grand_total)


@app.route('/delete_transaction/<int:transaction_id>', methods=['POST'])
def delete_transaction(transaction_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
    db.commit()
    return redirect(url_for('dashboard'))


@app.route('/dashboard')
def dashboard():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT COUNT(*) AS total_orders, SUM(total) AS total_revenue FROM transactions")
    summary = cursor.fetchone()
    total_orders = summary['total_orders'] if summary and summary['total_orders'] is not None else 0
    total_revenue = summary['total_revenue'] if summary and summary['total_revenue'] is not None else 0

    cursor.execute("SELECT COUNT(id) FROM products")
    total_products = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT category) FROM products")
    total_categories = cursor.fetchone()[0]

    cursor.execute(
        "SELECT id, customer_name, order_date, total, payment_method FROM transactions ORDER BY id DESC LIMIT 5")
    recent_orders = [dict(row) for row in cursor.fetchall()]

    best_selling_products = []

    earnings_by_date = []

    context = {
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'total_products': total_products,
        'total_categories': total_categories,
        'recent_orders': recent_orders,
        'best_selling_products': best_selling_products,
        'earnings_by_date': earnings_by_date,
        'currency': 'PHP'
    }
    return render_template('dashboard.html', **context)


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
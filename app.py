from flask import Flask, Blueprint, render_template, redirect, url_for, request, jsonify, flash, session, make_response, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os, csv, io, zipfile, secrets, sqlite3, threading, webbrowser
from functools import wraps
from datetime import datetime
from urllib.parse import quote
from collections import defaultdict
from openai import OpenAI

SERVER_BOOT_ID = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')   # 本次启动唯一 ID

from alerts import alerts_bp  # 导入报警模块的蓝图
from water_data import water_data_bp  # 导入水质数据模块的蓝图
from fish_data import fish_data_bp  # 导入鱼类数据模块的蓝图
from ai_api import ai_api_bp  # 导入人工智能模块的蓝图
from image_recognition_api import image_recognition_bp  # 导入人工智能模块的蓝图
from data_prediction import data_prediction_bp

app = Flask(__name__)

# 注册蓝图
app.register_blueprint(alerts_bp)
app.register_blueprint(water_data_bp)
app.register_blueprint(fish_data_bp)
app.register_blueprint(ai_api_bp)
app.register_blueprint(image_recognition_bp)
app.register_blueprint(data_prediction_bp, url_prefix='/api')

# 每次启动都换新密钥
app.config['SECRET_KEY'] = secrets.token_hex(16) + SERVER_BOOT_ID
# ★关键：连 cookie 名也带上 boot_id → 浏览器找不到对应 cookie，自然发不过来
app.config['SESSION_COOKIE_NAME']  = f'session_{SERVER_BOOT_ID}'
app.config['REMEMBER_COOKIE_NAME'] = f'remember_{SERVER_BOOT_ID}'

# 初始化Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# 数据库配置
DATABASE1 = 'static/users.db'
DATABASE2 = 'static/date.db'

@app.before_request
def reject_stale_session():
    # 允许静态资源与登录/注册本身通过，避免重定向循环
    if request.endpoint in ('login', 'register', 'static'):
        return
    if session.get('boot_id') != SERVER_BOOT_ID:
        # 如果旧 cookie 恢复出了用户，这里会清掉它
        if current_user.is_authenticated:
            logout_user()
        session.clear()
        # 给浏览器一个全新的 “空” session
        session['boot_id'] = SERVER_BOOT_ID
        return redirect(url_for('login'))
    
@app.route('/')
def index():
    """
    - 已登录：直接进入主页面（/main_info）
    - 未登录：跳转到登录页
    """
    if current_user.is_authenticated:
        return redirect(url_for('main_info'))
    return redirect(url_for('login'))

# 连接用户数据库
def get_db_connection():
    conn = sqlite3.connect(DATABASE1)
    conn.row_factory = sqlite3.Row
    return conn

# 连接日志数据库
def get_log_connection():              
    conn = sqlite3.connect(DATABASE2)
    conn.row_factory = sqlite3.Row
    return conn

# ---------- 用户模型 ----------
class User(UserMixin):
    def __init__(self, user_id, username, role):
        self.id = user_id
        self.username = username
        self.role = role

    @staticmethod
    def get(user_id):
        conn = get_db_connection()
        user = conn.execute(
            'SELECT * FROM users WHERE id = ?', (user_id,)
        ).fetchone()
        conn.close()
        if not user:
            return None
        return User(user_id=user['id'],
                    username=user['username'],
                    role=user['role'])

# 初始化数据库表
def init_db():
    with app.app_context():
        conn = get_db_connection()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'operator'
            )
        ''')
        conn.commit()
        conn.close()

         # === 新增：创建 syslog 表 ===
        conn_log = get_log_connection()
        conn_log.execute('''
            CREATE TABLE IF NOT EXISTS syslog (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                time   TEXT,
                user   TEXT,
                action TEXT,
                detail TEXT
            )
        ''')
        conn_log.commit()
        conn_log.close()
init_db()

# Flask-Login用户加载器
@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

###########################
# 只有管理员可访问的装饰器
###########################

def admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        # 未登录：让 Flask-Login 自己处理
        if not current_user.is_authenticated:
            return login_manager.unauthorized()

        # 已登录但不是 admin
        if getattr(current_user, 'role', None) != 'admin':
            flash('只有管理员可以访问该页面')
            return redirect(url_for('index'))        # 或 abort(403)

        # 管理员通过
        return view_func(*args, **kwargs)
    return wrapper

###########################
# 认证相关路由
###########################

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        try:
            existing_user = conn.execute(
                'SELECT id FROM users WHERE username = ?', (username,)
            ).fetchone()
            
            if existing_user:
                flash('用户名已存在')
                return redirect(url_for('register'))
            
            conn.execute(
                'INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
                (username, generate_password_hash(password), 'operator')
            )
            conn.commit()
            flash('注册成功，请登录')
            return redirect(url_for('login'))
        finally:
            conn.close()
    return render_template('register.html')

###########################
# 登录管理路由
###########################
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute(
            'SELECT * FROM users WHERE username = ?', (username,)
        ).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            conn_log = get_log_connection()
            conn_log.execute(
                'INSERT INTO syslog (time, user, action, detail) VALUES (?,?,?,?)',
                (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                 user['username'],
                 '登录系统',
                 f'IP: {request.remote_addr}')
            )
            conn_log.commit()
            conn_log.close()

            login_user(User(user_id=user['id'],
                            username=user['username'],
                            role=user['role']))
            # ---------------------------
            session['boot_id'] = SERVER_BOOT_ID
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('用户名或密码错误')
    return render_template('login.html')

###########################
# 登出管理路由
###########################

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

###########################
# 权限管理装饰器
###########################

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('只有管理员可以访问此页面')
            return redirect(url_for('main_info'))
        return f(*args, **kwargs)
    return decorated_function

# 配置CSV文件存储目录
ALERTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'alerts')

# 确保目录存在
if not os.path.exists(ALERTS_DIR):
    os.makedirs(ALERTS_DIR)

###########################
# 用户名更新路由
###########################

@app.route('/update_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def update_user(user_id):
    if current_user.role != 'admin':
        return jsonify(msg='没有权限'), 403          # <-- 明确 403

    username = request.form.get('username', '').strip()
    role     = request.form.get('role', '').strip()

    if not username or not role:
        return jsonify(msg='参数缺失'), 400           # <-- 明确 400

    conn = get_db_connection()
    try:
        conn.execute('UPDATE users SET username=?, role=? WHERE id=?',
                     (username, role, user_id))
        conn.commit()
    except sqlite3.IntegrityError:                   # UNIQUE 冲突
        conn.close()
        return jsonify(msg='用户名已存在'), 409
    conn.close()
    return jsonify(id=user_id, username=username, role=role)  # 200

###########################
# 添加用户路由
###########################

@app.route('/add_user', methods=['POST'])
@login_required
@admin_required
def add_user():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': '没有权限'}), 403

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'operator').strip()

    if not username or not password:
        return jsonify({'success': False, 'message': '参数缺失'}), 400

    password_hash = generate_password_hash(password)
    conn = get_db_connection()
    try:
        cur = conn.execute(
            'INSERT INTO users (username, password_hash, role) '
            'VALUES (?, ?, ?)',
            (username, password_hash, role)
        )
        conn.commit()
        new_id = cur.lastrowid          # 获取自增 ID
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'success': False, 'message': '用户名已存在'}), 409
    conn.close()

    # 把完整记录返回给前端，直接插入表格
    return jsonify({'success': True,
                    'id': new_id,
                    'username': username,
                    'role': role})

###########################
# 删除用户路由
###########################

@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    if current_user.role != 'admin':
        return jsonify(msg='没有权限'), 403

    conn = get_db_connection()
    cur  = conn.execute(
        'DELETE FROM users WHERE id = ?',
        (user_id,)
    )
    conn.commit()
    conn.close()

    if cur.rowcount == 0:
        return jsonify(msg='该用户不存在'), 404
    return jsonify(success=True)



###########################
# 管理员页面控制路由
###########################

@app.route('/admin_ctrl')
@login_required
@admin_required
def admin_ctrl():
     # 获取所有用户
    conn = get_db_connection()
    users = conn.execute('SELECT id, username, role FROM users').fetchall()

    # 获取除了管理员之外的操作员数量
    operator_count = len([user for user in users if user['role'] != 'admin'])
    conn.close()

    conn_log = get_log_connection()
    logs = conn_log.execute(
        'SELECT time, user, action, detail FROM syslog ORDER BY id DESC'
    ).fetchall()
    conn_log.close()

    return render_template('admin_ctrl.html',
                           users=users,
                           operator_count=operator_count,
                           logs=logs)        # <- 传递日志


@app.route('/water_system')

def water_system():
    return render_template('water_system.html')

@app.route('/smart_center')

def smart_center():
    return render_template('smart_center.html')

@app.route('/data_center')
@login_required
def data_center():
    return render_template('data_center.html')

@app.route('/main_info')
@login_required
def main_info():
    return render_template('main_info.html')

def open_browser():
    webbrowser.open('http://127.0.0.1:5000/login')

if __name__ == '__main__':
    # 打开浏览器
    threading.Timer(1.0, open_browser).start()
    # 运行 Flask 应用
    app.run(debug=True, use_reloader=False)
from flask import Flask, Blueprint, render_template, redirect, url_for, request, jsonify, flash, session, make_response, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os, csv, io, zipfile, secrets, sqlite3, threading, webbrowser
from functools import wraps
from datetime import datetime
from urllib.parse import quote
from collections import defaultdict

fish_data_bp = Blueprint('fish_data', __name__)

# 鱼类数据导出接口
@fish_data_bp.route('/api/fish/export')
def export_fish_data():
    ranch = request.args.get('ranch')
    if not ranch:
        return '未指定牧场', 400
    # 文件名
    filename = f'Fish_{ranch}.csv'
    fish_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'Fish')
    file_path = os.path.join(fish_dir, filename)
    if not os.path.exists(file_path):
        return '数据文件不存在', 404
    encoded_utf8 = quote(filename.encode('utf-8'))
    encoded_rfc5987 = quote(filename, safe='')
    return send_file(file_path, mimetype='text/csv', as_attachment=True, download_name=filename)

# ====== 新增：鱼类数据上传与模板下载接口 ======
FISH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'Fish')
FISH_HEADER = ['Species', 'Weight(g)', 'Length1(cm)', 'Length2(cm)', 'Length3(cm)', 'Height(cm)', 'Width(cm)']

# 鱼类数据上传接口
@fish_data_bp.route('/api/fish/upload', methods=['POST'])
def upload_fish_data():
    ranch = request.form.get('ranch', '').strip()
    file = request.files.get('file')
    if not ranch or not file:
        return jsonify({'success': False, 'msg': '缺少参数'}), 400
    filename = f'Fish_{ranch}.csv'
    file_path = os.path.join(FISH_DIR, filename)
    # 读取上传内容
    try:
        content = file.read().decode('utf-8-sig')
    except Exception:
        return jsonify({'success': False, 'msg': '文件读取失败，请上传UTF-8编码的CSV'}), 400
    lines = [l for l in content.splitlines() if l.strip()]
    if not lines or lines[0].replace(' ', '') != ','.join(FISH_HEADER).replace(' ', ''):
        return jsonify({'success': False, 'msg': 'CSV首行格式不符'}), 400
    upload_data = [tuple(row.split(',')) for row in lines[1:] if row.strip()]
    # 校验每行字段数
    for row in upload_data:
        if len(row) != len(FISH_HEADER):
            return jsonify({'success': False, 'msg': 'CSV数据行字段数不符'}), 400
    # 读取原有数据
    old_data = set()
    if os.path.exists(file_path):
        with open(file_path, encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) == len(FISH_HEADER):
                    old_data.add(tuple(row))
    # 合并去重
    merged = old_data | set(upload_data)
    merged_rows = list(merged)
    merged_rows.sort()  # 可按需要排序
    # 写回文件
    with open(file_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(FISH_HEADER)
        writer.writerows(merged_rows)
    return jsonify({'success': True, 'msg': '上传并合并成功', 'rows': len(merged_rows)})

# 鱼类数据模板下载接口
@fish_data_bp.route('/api/fish/template')
def download_fish_template():
    ranch = request.args.get('ranch', '').strip()
    if not ranch:
        return jsonify({'success': False, 'msg': '缺少牧场参数'}), 400
    filename = f'Fish_{ranch}.csv'
    header = ','.join(FISH_HEADER) + '\n'
    response = make_response(header)
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    encoded_utf8 = quote(filename.encode('utf-8'))
    encoded_rfc5987 = quote(filename, safe='')
    content_disposition = (
        f'attachment; filename="{encoded_utf8}"; '
        f'filename*=UTF-8\'\'{encoded_rfc5987}'
    )
    response.headers['Content-Disposition'] = content_disposition
    return response
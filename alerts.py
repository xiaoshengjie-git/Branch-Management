from flask import Flask, Blueprint, render_template, redirect, url_for, request, jsonify, flash, session, make_response, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os, csv, io, zipfile, secrets, sqlite3, threading, webbrowser
from functools import wraps
from datetime import datetime
from urllib.parse import quote
from collections import defaultdict

alerts_bp = Blueprint('alerts', __name__)

ALERTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'alerts')

# 获取指定牧场的警报数据
@alerts_bp.route('/api/alerts/<ranch_name>', methods=['GET'])
def get_alerts(ranch_name):
    """获取指定牧场的警报数据"""
    try:
        # 构建CSV文件路径
        file_path = os.path.join(ALERTS_DIR, f"{ranch_name.replace(' ', '_')}_alerts.csv")
        
        # 如果文件不存在，返回空数组
        if not os.path.exists(file_path):
            return jsonify([])
        
        # 读取CSV文件
        alerts = []
        with open(file_path, 'r', encoding='utf-8') as file:
            reader = csv.reader(file)
            next(reader)  # 跳过表头
            for row in reader:
                if len(row) >= 4:
                    alert = {
                        'type': row[0],
                        'level': row[1],
                        'message': row[2],
                        'timestamp': row[3]
                    }
                    alerts.append(alert)
        
        return jsonify(alerts)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 更新指定牧场的警报数据
@alerts_bp.route('/api/alerts/<ranch_name>', methods=['POST'])
def update_alerts(ranch_name):
    """更新指定牧场的警报数据"""
    try:
        # 获取请求中的警报数据
        new_alerts = request.json
        
        # 构建CSV文件路径
        file_path = os.path.join(ALERTS_DIR, f"{ranch_name.replace(' ', '_')}_alerts.csv")
        
        # 如果文件不存在，创建一个新文件
        if not os.path.exists(file_path):
            with open(file_path, 'w', encoding='utf-8', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(['警报类别', '警报级别', '警报内容', '时间戳'])
            existing_alerts = []
        else:
            # 读取现有警报
            existing_alerts = []
            with open(file_path, 'r', encoding='utf-8') as file:
                reader = csv.reader(file)
                next(reader)  # 跳过表头
                for row in reader:
                    if len(row) >= 4:
                        alert = {
                            'type': row[0],
                            'level': row[1],
                            'message': row[2],
                            'timestamp': row[3]
                        }
                        existing_alerts.append(alert)
        
        # 合并警报，避免重复
        merged_alerts = existing_alerts.copy()
        for new_alert in new_alerts:
            # 检查是否重复（类型、消息和15分钟内的时间戳）
            is_duplicate = False
            for existing_alert in existing_alerts:
                if (existing_alert['type'] == new_alert['type'] and 
                    existing_alert['message'] == new_alert['message']):
                    # 计算时间差（毫秒）
                    time_diff = abs(
                        datetime.fromisoformat(existing_alert['timestamp'].replace('Z', '+00:00')) - 
                        datetime.fromisoformat(new_alert['timestamp'].replace('Z', '+00:00'))
                    ).total_seconds()
                    
                    # 如果时间差小于15分钟，则视为重复
                    if time_diff < 15 * 60:
                        is_duplicate = True
                        break
            
            # 如果不是重复警报，添加到合并列表
            if not is_duplicate:
                merged_alerts.append(new_alert)
        
        # 保存合并后的警报
        with open(file_path, 'w', encoding='utf-8', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['警报类别', '警报级别', '警报内容', '时间戳'])
            for alert in merged_alerts:
                writer.writerow([
                    alert['type'],
                    alert['level'],
                    alert['message'],
                    alert['timestamp']
                ])
        
        return jsonify(merged_alerts)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 删除指定牧场的特定警报
@alerts_bp.route('/api/alerts/<ranch_name>/<int:alert_index>', methods=['DELETE'])
def delete_alert(ranch_name, alert_index):
    """删除指定牧场的特定警报"""
    try:
        # 构建CSV文件路径
        file_path = os.path.join(ALERTS_DIR, f"{ranch_name.replace(' ', '_')}_alerts.csv")
        
        # 如果文件不存在，返回错误
        if not os.path.exists(file_path):
            return jsonify({'error': '警报文件不存在'}), 404
        
        # 读取现有警报
        alerts = []
        with open(file_path, 'r', encoding='utf-8') as file:
            reader = csv.reader(file)
            next(reader)  # 跳过表头
            for row in reader:
                if len(row) >= 4:
                    alert = {
                        'type': row[0],
                        'level': row[1],
                        'message': row[2],
                        'timestamp': row[3]
                    }
                    alerts.append(alert)
        
        # 检查索引是否有效
        if alert_index < 0 or alert_index >= len(alerts):
            return jsonify({'error': '警报索引无效'}), 400
        
        # 删除指定索引的警报
        alerts.pop(alert_index)
        
        # 保存更新后的警报
        with open(file_path, 'w', encoding='utf-8', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['警报类别', '警报级别', '警报内容', '时间戳'])
            for alert in alerts:
                writer.writerow([
                    alert['type'],
                    alert['level'],
                    alert['message'],
                    alert['timestamp']
                ])
        
        return jsonify({'success': True, 'alerts': alerts})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
# 删除所有警报
@alerts_bp.route('/api/alerts/<ranch_name>/all', methods=['DELETE'])
def delete_all_alerts(ranch_name):
    """删除指定牧场的所有警报"""
    try:
        # 构建CSV文件路径
        file_path = os.path.join(ALERTS_DIR, f"{ranch_name.replace(' ', '_')}_alerts.csv")
        
        # 如果文件不存在，返回错误
        if not os.path.exists(file_path):
            return jsonify({'error': '警报文件不存在'}), 404
        
        # 清空文件，只保留表头
        with open(file_path, 'w', encoding='utf-8', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['警报类别', '警报级别', '警报内容', '时间戳'])
        
        return jsonify({'success': True, 'message': '所有警报已删除', 'alerts': []})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# 初始化所有牧场的警报文件
@alerts_bp.route('/api/init_alerts', methods=['POST'])
def init_alerts():
    """初始化所有牧场的警报文件"""
    try:
        # 从请求中获取牧场列表
        ranch_names = request.json.get('ranch_names', [])
        
        for ranch_name in ranch_names:
            # 构建CSV文件路径
            file_path = os.path.join(ALERTS_DIR, f"{ranch_name.replace(' ', '_')}_alerts.csv")
            
            # 如果文件不存在，创建一个新文件
            if not os.path.exists(file_path):
                with open(file_path, 'w', encoding='utf-8', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow(['警报类别', '警报级别', '警报内容', '时间戳'])
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
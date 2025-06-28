from flask import Flask, Blueprint, render_template, redirect, url_for, request, jsonify, flash, session, make_response, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os, csv, io, zipfile, secrets, sqlite3, threading, webbrowser
from functools import wraps
from datetime import datetime
from urllib.parse import quote
from collections import defaultdict

water_data_bp = Blueprint('water_data', __name__)

# 水质类别转数值（用于平均）
WATER_QUALITY_LEVEL_MAP = {'Ⅰ': 1, 'Ⅱ': 2, 'Ⅲ': 3, 'Ⅳ': 4, 'Ⅴ': 5, '劣Ⅴ': 6}
WATER_QUALITY_LEVEL_MAP_REVERSE = {v: k for k, v in WATER_QUALITY_LEVEL_MAP.items()}

# 断面地理信息（如有可补充，否则返回空）
SECTION_GEO = {}

# 递归聚合水质数据
@water_data_bp.route('/api/water_quality/summary')
def water_quality_summary():
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'water_quality')
    if not os.path.exists(base_dir):
        base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'water_quality')
    result = []
    for province in os.listdir(base_dir):
        province_path = os.path.join(base_dir, province)
        if not os.path.isdir(province_path):
            continue
        province_data = {
            'province': province,
            'basins': [],
            'avg_level': None,
            'avg_metrics': {},
        }
        level_sum, level_count = 0, 0
        metrics_sum = defaultdict(float)
        metrics_count = defaultdict(int)
        for basin in os.listdir(province_path):
            basin_path = os.path.join(province_path, basin)
            if not os.path.isdir(basin_path):
                continue
            basin_data = {
                'basin': basin,
                'sections': [],
                'avg_level': None,
                'avg_metrics': {},
            }
            basin_level_sum, basin_level_count = 0, 0
            basin_metrics_sum = defaultdict(float)
            basin_metrics_count = defaultdict(int)
            for section in os.listdir(basin_path):
                section_path = os.path.join(basin_path, section)
                if not os.path.isdir(section_path):
                    continue
                # 只取2021-04下的csv
                month_dir = os.path.join(section_path, '2021-04')
                if not os.path.exists(month_dir):
                    continue
                csv_files = [f for f in os.listdir(month_dir) if f.endswith('.csv')]
                for csv_file in csv_files:
                    csv_path = os.path.join(month_dir, csv_file)
                    with open(csv_path, encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        section_level_sum, section_level_count = 0, 0
                        section_metrics_sum = defaultdict(float)
                        section_metrics_count = defaultdict(int)
                        for row in reader:
                            level = WATER_QUALITY_LEVEL_MAP.get(row.get('水质类别', '').strip(), None)
                            if level:
                                section_level_sum += level
                                section_level_count += 1
                            # 关键指标
                            for metric in ['水温(℃)', 'pH(无量纲)', '溶解氧(mg/L)', '电导率(μS/cm)', '浊度(NTU)']:
                                try:
                                    val = float(row.get(metric, '').replace('*', '').strip())
                                    section_metrics_sum[metric] += val
                                    section_metrics_count[metric] += 1
                                except:
                                    continue
                        # 断面聚合
                        section_avg_level = section_level_sum / section_level_count if section_level_count else None
                        section_avg_metrics = {k: section_metrics_sum[k]/section_metrics_count[k] for k in section_metrics_sum if section_metrics_count[k]}
                        basin_level_sum += section_level_sum
                        basin_level_count += section_level_count
                        for k in section_metrics_sum:
                            basin_metrics_sum[k] += section_metrics_sum[k]
                            basin_metrics_count[k] += section_metrics_count[k]
                        province_data['basins'].append({
                            'basin': basin,
                            'section': section,
                            'avg_level': section_avg_level,
                            'avg_level_label': WATER_QUALITY_LEVEL_MAP_REVERSE.get(round(section_avg_level), None) if section_avg_level else None,
                            'avg_metrics': section_avg_metrics,
                            'geo': SECTION_GEO.get(section, {}),
                        })
            # 流域聚合
            basin_avg_level = basin_level_sum / basin_level_count if basin_level_count else None
            basin_avg_metrics = {k: basin_metrics_sum[k]/basin_metrics_count[k] for k in basin_metrics_sum if basin_metrics_count[k]}
            basin_data['avg_level'] = basin_avg_level
            basin_data['avg_metrics'] = basin_avg_metrics
            province_data['basins'].append(basin_data)
            level_sum += basin_level_sum
            level_count += basin_level_count
            for k in basin_metrics_sum:
                metrics_sum[k] += basin_metrics_sum[k]
                metrics_count[k] += basin_metrics_count[k]
        # 省级聚合
        province_data['avg_level'] = level_sum / level_count if level_count else None
        province_data['avg_metrics'] = {k: metrics_sum[k]/metrics_count[k] for k in metrics_sum if metrics_count[k]}
        result.append(province_data)
    return jsonify(result)

@water_data_bp.route('/api/water_quality/section_data')
def section_data():
    province = request.args.get('province')
    basin = request.args.get('basin')
    section = request.args.get('section')
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    indicator = request.args.get('indicator')  # 逗号分隔
    # 路径拼接
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'water_quality')
    if not os.path.exists(base_dir):
        base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'water_quality')
    section_dir = os.path.join(base_dir, province, basin, section, '2021-04')
    if not os.path.exists(section_dir):
        return jsonify({'error': 'section not found'}), 404
    csv_files = [f for f in os.listdir(section_dir) if f.endswith('.csv')]
    timeseries = []
    for csv_file in csv_files:
        csv_path = os.path.join(section_dir, csv_file)
        with open(csv_path, encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # 时间过滤
                time_str = row.get('监测时间', '').strip()
                if start_time and time_str < start_time:
                    continue
                if end_time and time_str > end_time:
                    continue
                # 指标过滤
                data = {'time': time_str}
                if indicator:
                    for ind in indicator.split(','):
                        data[ind] = row.get(ind, None)
                else:
                    for k in row:
                        if k not in ['省份', '流域', '断面名称', '站点情况']:
                            data[k] = row[k]
                timeseries.append(data)
    return jsonify(timeseries)

# 水质数据上传接口
@water_data_bp.route('/api/water_quality/upload', methods=['POST'])
def upload_water_quality():
    province = request.form.get('province')
    basin = request.form.get('basin')
    section = request.form.get('section')
    file = request.files.get('file')
    if not (province and basin and section and file):
        return '缺少参数', 400
    # 读取上传内容
    content = file.read().decode('utf-8-sig')
    lines = [l for l in content.splitlines() if l.strip()]
    if len(lines) < 2:
        return 'CSV内容不足', 400
    header = '省份,流域,断面名称,监测时间,水质类别,水温(℃),pH(无量纲),溶解氧(mg/L),电导率(μS/cm),浊度(NTU),高锰酸盐指数(mg/L),氨氮(mg/L),总磷(mg/L),总氮(mg/L),叶绿素α(mg/L),藻密度(cells/L),站点情况'
    if lines[0].replace(' ', '') != header.replace(' ', ''):
        return 'CSV首行格式不符', 400
    upload_data = [row.split(',') for row in lines[1:]]
    # 路径拼接
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'water_quality')
    if not os.path.exists(base_dir):
        base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'water_quality')
    section_dir = os.path.join(base_dir, province, basin, section, '2021-04')
    os.makedirs(section_dir, exist_ok=True)
    csv_path = os.path.join(section_dir, f'{section}.csv')
    # 读取原有数据
    old_data = []
    if os.path.exists(csv_path):
        with open(csv_path, encoding='utf-8') as f:
            reader = csv.reader(f)
            old_header = next(reader, None)
            for row in reader:
                old_data.append(row)
    # 合并数据，按监测时间升序，时间冲突用上传数据覆盖
    # 以监测时间为key
    def get_time(row):
        return row[3]  # 监测时间
    merged = {}
    for row in old_data:
        merged[get_time(row)] = row
    for row in upload_data:
        merged[get_time(row)] = row  # 覆盖
    merged_rows = list(merged.values())
    merged_rows.sort(key=get_time)
    # 写回文件
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header.split(','))
        writer.writerows(merged_rows)
    return jsonify({'success': True, 'msg': '上传并合并成功', 'rows': len(merged_rows)})

# 水质数据导出接口
@water_data_bp.route('/api/water_quality/export')
def export_water_quality():
    province = request.args.get('province')
    basin = request.args.get('basin')
    section = request.args.get('section')
    fmt = request.args.get('format', 'csv')
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'water_quality')
    
    if not os.path.exists(base_dir):
        return '数据目录不存在', 404

    files_to_zip = []
    
    def walk_dir(root, rel_path=''):
        for entry in os.listdir(root):
            full_path = os.path.join(root, entry)
            rel = os.path.join(rel_path, entry)
            if os.path.isdir(full_path):
                walk_dir(full_path, rel)
            elif entry.endswith('.csv'):
                files_to_zip.append((full_path, rel))

    # 选择范围
    zip_root = []
    if province:
        province_dir = os.path.join(base_dir, province)
        if not os.path.exists(province_dir):
            return '省份不存在', 404
        if basin:
            basin_dir = os.path.join(province_dir, basin)
            if not os.path.exists(basin_dir):
                return '流域不存在', 404
            if section:
                section_dir = os.path.join(basin_dir, section)
                if not os.path.exists(section_dir):
                    return '断面不存在', 404
                # 只导出该断面下所有csv
                walk_dir(section_dir, os.path.join(province, basin, section))
                zip_root = [province, basin, section]
            else:
                # 导出该流域下所有断面
                walk_dir(basin_dir, os.path.join(province, basin))
                zip_root = [province, basin]
        else:
            # 导出该省所有流域
            walk_dir(province_dir, province)
            zip_root = [province]
    else:
        # 导出全部
        walk_dir(base_dir, '')
        zip_root = []
    if not files_to_zip:
        return '没有可导出的数据', 404

    mem_zip = io.BytesIO()
    with zipfile.ZipFile(mem_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for abs_path, rel_path in files_to_zip:
            zf.write(abs_path, rel_path)
    mem_zip.seek(0)

    name_parts = zip_root + ['水质监测数据']
    filename = '_'.join(name_parts) + '.zip'

    # 修改send_file调用方式
    return send_file(
        mem_zip,
        mimetype='application/zip',
        as_attachment=True,
        download_name=filename  # 关键修改点
    )

# 水质数据模板下载接口
@water_data_bp.route('/api/water_quality/template')
def download_water_quality_template():
    province = request.args.get('province')
    basin = request.args.get('basin')
    section = request.args.get('section')
    if not (province and basin and section):
        return jsonify({'success': False, 'msg': '参数不完整'}), 400

    header = '省份,流域,断面名称,监测时间,水质类别,水温(℃),pH(无量纲),溶解氧(mg/L),电导率(μS/cm),浊度(NTU),高锰酸盐指数(mg/L),氨氮(mg/L),总磷(mg/L),总氮(mg/L),叶绿素α(mg/L),藻密度(cells/L),站点情况\n'
    
    response = make_response(header)
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    
    filename = f'{section}.csv'
    
    # 双重编码方案兼容所有浏览器
    encoded_utf8 = quote(filename.encode('utf-8'))  # 传统编码方式
    encoded_rfc5987 = quote(filename, safe='')       # RFC 5987编码
    
    # 同时提供两种编码方案
    content_disposition = (
        f'attachment; filename="{encoded_utf8}"; '
        f'filename*=UTF-8\'\'{encoded_rfc5987}'
    )
    response.headers['Content-Disposition'] = content_disposition
    
    return response
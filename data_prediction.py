from flask import Blueprint, jsonify, request
from sklearn.linear_model import LinearRegression
from datetime import datetime, timedelta
import pandas as pd

data_prediction_bp = Blueprint('data_prediction', __name__)

# 鱼类生长预测模型
def predict_fish_growth(data, months_ahead=3):
    """
    基于当前鱼类数据进行生长预测
    :param data: 包含鱼类数据的DataFrame
    :param months_ahead: 预测未来几个月(3/6/12)
    :return: 预测结果的DataFrame
    """
    # 这里使用简单的线性回归模型作为示例
    # 实际应用中可以使用更复杂的模型
    
    # 准备预测结果容器
    predictions = []
    
    # 对每个数值特征进行预测
    features = ['Weight(g)', 'Length1(cm)', 'Length2(cm)', 'Length3(cm)', 'Height(cm)', 'Width(cm)']
    
    for feature in features:
        # 创建模型
        model = LinearRegression()
        
        # 假设时间序列是线性增长的简单模型
        # 实际应用中可能需要更复杂的时间序列处理
        X = [[i] for i in range(len(data))]
        y = data[feature].values
        
        # 训练模型
        model.fit(X, y)
        
        # 预测未来值
        future_X = [[len(data) + months_ahead]]
        predicted_value = model.predict(future_X)[0]
        
        # 确保预测值不会小于0
        predicted_value = max(0, predicted_value)
        
        predictions.append({
            'feature': feature,
            'current_avg': data[feature].mean(),
            'predicted_value': predicted_value,
            'growth_rate': (predicted_value - data[feature].mean()) / data[feature].mean() * 100
        })
    
    return predictions

# 预测接口
@data_prediction_bp.route('/predict', methods=['POST'])
def predict():
    try:
        # 获取请求数据
        data = request.json
        fish_data = pd.DataFrame(data['fish_data'])
        months = int(data['months'])
        
        # 进行预测
        predictions = predict_fish_growth(fish_data, months_ahead=months)
        
        # 计算预测日期
        prediction_date = datetime.now() + timedelta(days=30 * months)
        
        return jsonify({
            'success': True,
            'predictions': predictions,
            'prediction_date': prediction_date.strftime('%Y-%m-%d')
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
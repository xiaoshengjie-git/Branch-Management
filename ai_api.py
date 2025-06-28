from flask import Blueprint, request, jsonify
from openai import OpenAI

ai_api_bp = Blueprint('ai_api', __name__)

# 配置 OpenAI 客户端
client = OpenAI(
    api_key="bce-v3/ALTAK-0IgCdhsnLXwRKZadr2muI/5259a057d17909fabb25d37013e6af4ccc66a6d9",  # 你的 API Key
    base_url="https://qianfan.baidubce.com/v2",  # 千帆域名
    default_headers={"appid": "app-AMipy7QU"}   # 你的 App ID
)

# 处理用户输入并调用 API 返回响应
@ai_api_bp.route('/ask', methods=['POST'])
def ask():
    user_input = request.form['user_input']
    
    # 调用千帆 OpenAI API
    completion = client.chat.completions.create(
        model="ernie-4.0-turbo-8k", 
        messages=[{'role': 'system', 'content': 'You are a helpful assistant.'},
                  {'role': 'user', 'content': user_input}]
    )

    # 获取 API 的响应结果
    response_message = completion.choices[0].message.content

    return jsonify({'response': response_message})
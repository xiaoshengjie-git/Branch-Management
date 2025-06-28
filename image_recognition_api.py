import base64
from flask import Blueprint, request, jsonify
from openai import OpenAI

# 创建图片识别的蓝图
image_recognition_bp = Blueprint('image_recognition', __name__)

# 配置 OpenAI 客户端
client = OpenAI(
    api_key="bce-v3/ALTAK-0IgCdhsnLXwRKZadr2muI/5259a057d17909fabb25d37013e6af4ccc66a6d9",  # 你的 API Key
    base_url="https://qianfan.baidubce.com/v2"  # OpenAI 或其他图片识别API的URL
)

# 图片识别的逻辑
@image_recognition_bp.route('/recognize_image', methods=['POST'])
def recognize_image():
    # 获取上传的图片
    image_data = request.form['image_data']
    
    # 调用 OpenAI API 进行图片识别
    response = client.chat.completions.create(
        model="deepseek-vl2",  # 模型名称，需根据实际情况调整
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请你用中文回答，图片中有什么鱼类，并详细的描述图片和相应的鱼类信息。"},  # 你可以自定义要提问的内容
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_data}"  # 转换为Base64图像
                        }
                    }
                ]
            }
        ]
    )
    
    # 处理响应并返回给前端
    result = response.choices[0].message.content
    return jsonify({'response': result})


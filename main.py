import os
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client

# 加密库依赖
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
import base64

# ================= 配置区 =================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
RSA_PRIVATE_KEY_PEM = os.environ.get("RSA_PRIVATE_KEY")

# 你的发件邮箱配置 (GitHub Secrets 中配置)
SENDER_EMAIL = os.environ.get("EMAIL_USER")  
SENDER_PASSWORD = os.environ.get("EMAIL_PASS")

def get_db():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def rsa_decrypt(encrypted_b64, private_key_pem):
    """ 使用 RSA 私钥解密，并解析 V5.0 的 JSON 包 """
    try:
        # 1. 加载私钥
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(),
            password=None,
            backend=default_backend()
        )
        
        # 2. 解码 Base64
        encrypted_bytes = base64.b64decode(encrypted_b64)
        
        # 3. RSA 解密
        decrypted_bytes = private_key.decrypt(
            encrypted_bytes,
            padding.PKCS1v15() # 前端 JSEncrypt 默认使用 PKCS1v15
        )
        
        # 4. 转换字符串并解析 JSON
        decrypted_str = decrypted_bytes.decode('utf-8')
        
        # 尝试解析 JSON (V5.0 逻辑)
        try:
            data = json.loads(decrypted_str)
            return data # 返回字典 {'k': '...', 't': '...'}
        except json.JSONDecodeError:
            # 兼容旧版本 (V4.5): 如果不是JSON，说明直接就是 key
            return {'k': decrypted_str, 't': None}
            
    except Exception as e:
        print(f"❌ 解密底层错误: {e}")
        return None

def send_email_via_smtp(to_email, aes_key, user_id):
    """ 发送含有解密链接的邮件 """
    if not to_email:
        print("❌ 错误: 未找到目标邮箱 (可能仍是旧版本数据)")
        return False

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email
    msg['Subject'] = "【Relic】数字信托移交 (V5.0)"

    # 生成解密链接
    link = f"https://jijglingw-ux.github.io/ghost-watcher/#id={user_id}&key={aes_key}"
    
    body = f"""
    尊敬的受益人：
    
    这是一封由自动化“死手开关”触发的信托移交邮件。
    委托人已长时间未签到，系统判断为“失联”。
    
    根据凤凰协议 V5.0，以下是解密密钥：
    --------------------------------
    {aes_key}
    --------------------------------
    
    请点击下方链接查看完整内容（链接有效性取决于数据库留存）：
    {link}
    
    (本邮件由自动化程序发出，请勿回复)
    """
    msg.attach(MIMEText(body, 'plain'))

    try:
        # 自动识别 SMTP 服务器 (这里以 Gmail 和 QQ 为例，默认用 QQ 端口 465)
        smtp_server = "smtp.qq.com" if "qq.com" in SENDER_EMAIL else "smtp.gmail.com"
        port = 465 if "qq.com" in SENDER_EMAIL else 587
        
        server = smtplib.SMTP_SSL(smtp_server, 465) if port == 465 else smtplib.SMTP(smtp_server, port)
        
        if port == 587: server.starttls()
        
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")
        return False

def watchdog():
    print("🐕 凤凰看门狗 V5.0 (隐形版) 启动...")
    
    db = get_db()
    
    # 1. 获取所有活跃的信托
    try:
        response = db.table("vaults").select("*").eq("status", "active").execute()
        users = response.data
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return

    now = datetime.now(timezone.utc)
    
    for row in users:
        user_id = row['id']
        # 兼容处理：V5.0 可能没有 beneficiary_email，V4.5 有
        # 我们优先从 encrypted_payload 里取，如果取不到再看数据库字段
        db_email = row.get('beneficiary_email') 
        
        last_checkin_str = row['last_checkin_at']
        timeout_minutes = row['timeout_minutes']
        
        last_checkin = datetime.fromisoformat(last_checkin_str.replace('Z', '+00:00'))
        time_diff = (now - last_checkin).total_seconds() / 60
        
        if time_diff > timeout_minutes:
            print(f"⚠️ 用户 {user_id[:8]}... 已超时 ({int(time_diff)}min > {timeout_minutes}min)。准备拆包...")
            
            # 解密 key_storage (里面现在有 email + key)
            payload_data = rsa_decrypt(row['key_storage'], RSA_PRIVATE_KEY_PEM)
            
            if payload_data:
                aes_key = payload_data.get('k')
                # 优先用隐形邮箱，如果没有则回退到数据库字段 (兼容旧版)
                target_email = payload_data.get('t') or db_email 
                
                if aes_key and target_email:
                    success = send_email_via_smtp(target_email, aes_key, user_id)
                    
                    if success:
                        print(f"✅ 邮件已向隐形目标发送成功。")
                        
                        # 【重要】为了安全，我们把 key_storage 清空，把 status 改为 dispatched
                        # 这样黑客再也不能发邮件，但用户点击链接依然可以从数据库取 encrypted_data 解密
                        db.table("vaults").update({
                            "status": "dispatched",
                            "key_storage": "BURNED", # 销毁钥匙
                            # "encrypted_data": "BURNED" # 如果你想阅后即焚，把这行注释打开，但那样受益人就看不了了
                        }).eq("id", user_id).execute()
                        print("🔥 钥匙已销毁，状态已更新。")
                else:
                    print("❌ 解包数据不完整 (Key 或 Email 缺失)")
            else:
                print("❌ 解密失败 (私钥错误或数据损坏)")
        else:
            print(f"✅ 用户 {user_id[:8]}... 状态正常 (剩余 {timeout_minutes - int(time_diff)} min)")

if __name__ == "__main__":
    if not RSA_PRIVATE_KEY_PEM:
        print("❌ 致命错误: 未检测到 RSA 私钥。")
    else:
        watchdog()

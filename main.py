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
# 这里的变量名对应 main.yml 里的配置
SENDER_EMAIL = os.environ.get("EMAIL_USER")  
SENDER_PASSWORD = os.environ.get("EMAIL_PASS")

def get_db():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def rsa_decrypt(encrypted_b64, private_key_pem):
    """ 解密 RSA 包，提取隐藏的邮箱和密钥 """
    try:
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(), password=None, backend=default_backend()
        )
        encrypted_bytes = base64.b64decode(encrypted_b64)
        decrypted_bytes = private_key.decrypt(encrypted_bytes, padding.PKCS1v15())
        decrypted_str = decrypted_bytes.decode('utf-8')
        
        try:
            return json.loads(decrypted_str)
        except json.JSONDecodeError:
            return {'k': decrypted_str, 't': None}
    except Exception as e:
        print(f"❌ 解密底层错误: {e}")
        return None

def send_email_via_smtp(to_email, aes_key, user_id):
    """ 发送伪装成系统通知的邮件 """
    
    # 1. 强制类型转换，防止报错
    to_email = str(to_email).strip()
    aes_key = str(aes_key).strip()
    sender = str(SENDER_EMAIL).strip()
    
    print(f"📧 正在尝试发信 -> 收件人: {to_email}")

    if not to_email or "None" in to_email:
        print("❌ 错误: 目标邮箱无效")
        return False

    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = to_email
    
    # ==========================================
    # 🕵️‍♂️ 伪装核心：修改标题和正文
    # ==========================================
    
    # 标题：看起来像普通的系统自动邮件
    msg['Subject'] = "【系统通知】云端数据自动归档完成 (Ref: 2026-AUTO)"

    # 生成链接
    link = f"https://jijglingw-ux.github.io/ghost-watcher/#id={user_id}&key={aes_key}"
    
    # 正文：去掉敏感词，只保留业务术语
    body = f"""
    尊敬的用户：
    
    系统检测到您的账户长时间未活跃。
    根据预设的安全策略，您的数据已完成自动封装归档。
    
    请点击下方安全链接进行身份验证并提取归档数据：
    {link}
    
    --------------------------------
    (此链接包含身份验证令牌，请勿转发)
    系统自动发送，无需回复。
    """
    msg.attach(MIMEText(body, 'plain'))

    try:
        # 自动识别 SMTP 服务器
        smtp_server = "smtp.qq.com" if "qq.com" in sender else "smtp.gmail.com"
        port = 465 if "qq.com" in sender else 587
        
        print(f"🔌 连接 SMTP 服务器: {smtp_server}:{port}")
        
        if port == 465:
            server = smtplib.SMTP_SSL(smtp_server, 465)
        else:
            server = smtplib.SMTP(smtp_server, port)
            server.starttls()
        
        server.login(sender, SENDER_PASSWORD)
        server.sendmail(sender, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")
        return False

def watchdog():
    print("🐕 凤凰看门狗 V5.0 (反拦截版) 启动...")
    db = get_db()
    
    try:
        # 只查询 active 状态的
        response = db.table("vaults").select("*").eq("status", "active").execute()
        users = response.data
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return

    now = datetime.now(timezone.utc)
    
    if not users:
        print("💤暂无活跃信托任务")

    for row in users:
        user_id = row['id']
        db_email = row.get('beneficiary_email')
        
        last_checkin = datetime.fromisoformat(row['last_checkin_at'].replace('Z', '+00:00'))
        timeout_minutes = row['timeout_minutes']
        time_diff = (now - last_checkin).total_seconds() / 60
        
        if time_diff > timeout_minutes:
            print(f"⚠️ 用户 {user_id[:8]}... 已超时 ({int(time_diff)}min > {timeout_minutes}min)。准备拆包...")
            
            payload_data = rsa_decrypt(row['key_storage'], RSA_PRIVATE_KEY_PEM)
            
            if payload_data:
                aes_key = payload_data.get('k')
                target_email = payload_data.get('t') or db_email 
                
                if aes_key and target_email:
                    success = send_email_via_smtp(target_email, aes_key, user_id)
                    
                    if success:
                        print(f"✅ 邮件发送成功！正在销毁钥匙...")
                        # 发送成功后更新状态
                        db.table("vaults").update({
                            "status": "dispatched",
                            "key_storage": "BURNED" 
                        }).eq("id", user_id).execute()
                        print("🔥 钥匙已销毁，任务完成。")
                else:
                    print(f"❌ 数据缺失: Key或Email无法提取")
            else:
                print("❌ RSA解密失败")
        else:
            print(f"✅ 用户 {user_id[:8]}... 状态正常")

if __name__ == "__main__":
    if not RSA_PRIVATE_KEY_PEM:
        print("❌ 错误: 未检测到 RSA 私钥")
    elif not SENDER_EMAIL:
        print("❌ 错误: 未检测到发件人邮箱")
    else:
        watchdog()

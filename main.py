import os
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
import base64

# ================= 配置区 =================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
RSA_PRIVATE_KEY_PEM = os.environ.get("RSA_PRIVATE_KEY")
SENDER_EMAIL = os.environ.get("EMAIL_USER")
SENDER_PASSWORD = os.environ.get("EMAIL_PASS")

# 您的网页首页地址
BASE_URL = "https://jijglingw-ux.github.io/ghost-watcher/"

def get_db():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def parse_time_safe(time_str):
    try:
        clean_str = time_str.replace('Z', '+00:00')
        if '.' in clean_str:
            clean_str = clean_str.split('.')[0] + '+00:00'
        return datetime.fromisoformat(clean_str)
    except:
        return None

def rsa_decrypt(encrypted_b64, private_key_pem):
    """ 解密 RSA 包 """
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
    """ V5.8: 极简文案版 """
    to_email = str(to_email).strip()
    aes_key = str(aes_key).strip()
    user_id = str(user_id).strip()
    sender = str(SENDER_EMAIL).strip()
    
    print(f"📧 正在尝试发信 -> 收件人: {to_email}")

    if not to_email or "None" in to_email:
        print("❌ 错误: 目标邮箱无效")
        return False

    msg = MIMEMultipart('alternative')
    msg['From'] = sender
    msg['To'] = to_email
    msg['Subject'] = "【绝密】数字资产提取通知"

    # ================= HTML 邮件正文 =================
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f4f4f4; margin: 0; padding: 0; }}
            .container {{ max-width: 600px; margin: 20px auto; background-color: #ffffff; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .header {{ border-bottom: 2px solid #d9534f; padding-bottom: 20px; margin-bottom: 30px; }}
            .header h2 {{ margin: 0; color: #d9534f; }}
            .step {{ margin-bottom: 30px; background: #fff; border-left: 4px solid #007bff; padding-left: 15px; }}
            .step-title {{ font-weight: bold; font-size: 16px; color: #2c3e50; margin-bottom: 5px; display: block; }}
            .label {{ font-size: 12px; color: #666; margin-top: 15px; margin-bottom: 5px; font-weight: bold; }}
            .backup-box {{ background-color: #f8f9fa; border: 1px dashed #999; padding: 12px; border-radius: 4px; font-size: 13px; color: #333; word-break: break-all; font-family: monospace; letter-spacing: 1px; }}
            .manual-link {{ color: #007bff; text-decoration: underline; font-weight: bold; }}
            .footer {{ margin-top: 40px; font-size: 12px; color: #999; text-align: center; border-top: 1px solid #eee; padding-top: 20px; }}
            .warn {{ color: #d9534f; font-weight: bold; font-size: 12px; margin-top: 10px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>凤凰协议 | 资产提取通知</h2>
            </div>
            
            <p>尊敬的受益人：</p>
            <p>委托人留存的“数字信托”已激活。以下数据已为您准备就绪。</p>
            <p>为确保数据安全，请在<strong>电脑端</strong>执行以下操作：</p>
            
            <hr style="border: 0; border-top: 1px solid #eee; margin: 25px 0;">

            <div class="step">
                <span class="step-title">第一步：访问信托终端</span>
                <p>点击访问：<a href="{BASE_URL}" class="manual-link">{BASE_URL}</a></p>
                <p style="font-size:12px; color:#666;">(进入页面后，请点击“我是受益人”)</p>
            </div>

            <div class="step">
                <span class="step-title">第二步：输入安全凭证</span>
                <p>请在网页中依次输入以下两项信息：</p>
                
                <div class="label">1. 保险箱 ID (Vault ID):</div>
                <div class="backup-box">{user_id}</div>

                <div class="label">2. 提取密钥 (AES Key):</div>
                <div class="backup-box">{aes_key}</div>
            </div>

            <div class="warn">⚠️ 注意：解密后数据将在 24 小时后自动销毁。</div>

            <div class="footer">
                <p>Phoenix Protocol Automated System</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_content = f"""
    【绝密】数字资产提取通知
    
    委托人留存的“数字信托”已激活。请在电脑端按以下步骤提取：
    
    1. 访问信托终端：{BASE_URL}
    2. 选择“我是受益人”，并输入以下信息：
    
    [ 保险箱 ID ]: {user_id}
    [ 提取密钥 ]: {aes_key}
    
    注意：数据解密后将在24小时后自动销毁。
    """
    
    msg.attach(MIMEText(text_content, 'plain'))
    msg.attach(MIMEText(html_content, 'html'))

    try:
        smtp_server = "smtp.qq.com" if "qq.com" in sender else "smtp.gmail.com"
        port = 465 if "qq.com" in sender else 587
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
    print("🐕 凤凰看门狗 V5.8 (极简文案版) 启动...")
    db = get_db()
    
    try:
        response = db.table("vaults").select("*").eq("status", "active").execute()
        users = response.data
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return

    now = datetime.now(timezone.utc)
    
    if not users:
        print("💤 暂无活跃信托任务")

    for row in users:
        user_id = row['id']
        db_email = row.get('beneficiary_email')
        
        last_checkin = parse_time_safe(row['last_checkin_at'])
        if not last_checkin: continue
            
        timeout_minutes = row['timeout_minutes']
        time_diff = (now - last_checkin).total_seconds() / 60
        
        if time_diff > timeout_minutes:
            print(f"⚠️ 用户 {user_id[:8]}... 已超时。准备拆包...")
            
            payload_data = rsa_decrypt(row['key_storage'], RSA_PRIVATE_KEY_PEM)
            
            if payload_data:
                aes_key = payload_data.get('k')
                target_email = payload_data.get('t') or db_email 
                
                if aes_key and target_email:
                    success = send_email_via_smtp(target_email, aes_key, user_id)
                    if success:
                        print(f"✅ 邮件发送成功！正在销毁钥匙...")
                        db.table("vaults").update({
                            "status": "dispatched",
                            "key_storage": "BURNED" 
                        }).eq("id", user_id).execute()
                        print("🔥 钥匙已销毁，任务完成。")
                else:
                    print(f"❌ 数据缺失")
            else:
                print("❌ RSA解密失败")
        else:
            print(f"✅ 用户 {user_id[:8]}... 状态正常")

if __name__ == "__main__":
    if not RSA_PRIVATE_KEY_PEM:
        print("❌ 错误: 未检测到 RSA 私钥")
    else:
        watchdog()

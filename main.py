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
SENDER_EMAIL = os.environ.get("EMAIL_USER")
SENDER_PASSWORD = os.environ.get("EMAIL_PASS")

# ⚠️⚠️⚠️ 请确保这里是您的 GitHub Pages 链接 ⚠️⚠️⚠️
BASE_URL = "https://jijglingw-ux.github.io/ghost-watcher/"

def get_db():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def parse_timestamp(ts_str):
    """ 
    强力时间解析器：处理各种奇怪的时间格式
    比如: 2026-01-27T12:15:24.02+00:00 (这种2位毫秒Python3.9不认)
    """
    try:
        # 1. 尝试标准解析
        return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    except ValueError:
        # 2. 如果失败，说明毫秒精度有问题。我们直接粗暴处理：
        # 截断到秒级 (对于死手开关来说，毫秒不重要)
        try:
            # 拿到 '.' 之前的部分 (2026-01-27T12:15:24)
            base_time_str = ts_str.split('.')[0]
            # 重新解析并强制加上 UTC 时区
            dt = datetime.strptime(base_time_str, "%Y-%m-%dT%H:%M:%S")
            return dt.replace(tzinfo=timezone.utc)
        except Exception as e:
            print(f"❌ 时间格式严重错误: {ts_str} -> {e}")
            return None

def rsa_decrypt(encrypted_b64, private_key_pem):
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
    to_email = str(to_email).strip()
    aes_key = str(aes_key).strip()
    sender = str(SENDER_EMAIL).strip()
    
    print(f"📧 正在尝试发信 (HTML版) -> 收件人: {to_email}")

    if not to_email or "None" in to_email:
        print("❌ 错误: 目标邮箱无效")
        return False

    msg = MIMEMultipart('alternative')
    msg['From'] = sender
    msg['To'] = to_email
    msg['Subject'] = "【重要】数字资产交接：请查收解密指引 (Ref: V5.0)"

    link = f"{BASE_URL}#id={user_id}&key={aes_key}"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f4f4f4; margin: 0; padding: 0; }}
            .container {{ max-width: 600px; margin: 20px auto; background-color: #ffffff; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .header {{ border-bottom: 2px solid #00ff41; padding-bottom: 20px; margin-bottom: 30px; }}
            .header h2 {{ margin: 0; color: #333; }}
            .step {{ margin-bottom: 30px; background: #fff; }}
            .step-title {{ font-weight: bold; font-size: 18px; color: #2c3e50; margin-bottom: 10px; display: block; }}
            .btn {{ display: block; width: 100%; text-align: center; background-color: #007bff; color: #ffffff !important; padding: 18px 0; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 18px; margin: 15px 0; }}
            .btn:hover {{ background-color: #0056b3; }}
            .backup-box {{ background-color: #f8f9fa; border: 1px dashed #999; padding: 15px; border-radius: 5px; font-size: 14px; color: #333; word-break: break-all; font-family: monospace; }}
            .footer {{ margin-top: 40px; font-size: 12px; color: #999; text-align: center; border-top: 1px solid #eee; padding-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>凤凰协议 | 资产交接通知</h2>
            </div>
            
            <p>尊敬的受益人：</p>
            <p>您收到这封邮件，是因为委托人设置的“数字信托”已触发交接条件。以下数据已为您准备就绪：</p>
            
            <hr style="border: 0; border-top: 1px solid #eee; margin: 25px 0;">

            <div class="step">
                <span class="step-title">方式一：自动解密（推荐）</span>
                <p style="color:#666; margin:5px 0;">请直接点击下方蓝色按钮。系统将自动验证身份并解密内容。</p>
                <a href="{link}" class="btn">👉 点击此处提取秘密</a>
            </div>

            <div class="step">
                <span class="step-title" style="margin-top: 30px;">方式二：手动提取（备用）</span>
                <p style="color:#666;">如果上方按钮无法点击，请保留以下<strong>安全凭证</strong>作为恢复钥匙：</p>
                <div class="backup-box">{aes_key}</div>
            </div>

            <div class="footer">
                <p>安全提示：此凭证是解密的唯一钥匙，请妥善保管。</p>
                <p>Phoenix Protocol Automated System</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_content = f"""
    【重要】数字资产交接通知
    
    方式一：点击链接自动解密（推荐）
    {link}
    
    方式二：手动解密（备用）
    如果链接失效，请复制以下密钥作为凭证：
    {aes_key}
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
    print("🐕 凤凰看门狗 V5.0 (兼容性增强版) 启动...")
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
        
        # === 核心修复点：使用自定义的强力解析函数 ===
        last_checkin = parse_timestamp(row['last_checkin_at'])
        
        if last_checkin is None:
            continue # 跳过无法解析的时间
            
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

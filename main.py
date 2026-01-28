import os
import smtplib
import json
import time
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
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") # 必须是 Service Role Key (能够绕过 RLS)
RSA_PRIVATE_KEY_PEM = os.environ.get("RSA_PRIVATE_KEY")
SENDER_EMAIL = os.environ.get("EMAIL_USER")
SENDER_PASSWORD = os.environ.get("EMAIL_PASS")
BASE_URL = "https://jijglingw-ux.github.io/ghost-watcher/"

def get_db():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ 环境变量缺失: SUPABASE_URL 或 SUPABASE_KEY")
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def parse_time_safe(time_str):
    if not time_str: return None
    try:
        clean_str = time_str.replace('Z', '+00:00')
        if '.' in clean_str:
            clean_str = clean_str.split('.')[0] + '+00:00'
        return datetime.fromisoformat(clean_str)
    except Exception as e:
        print(f"⚠️ 时间解析错误: {e}")
        return None

def rsa_decrypt(encrypted_b64, private_key_pem):
    if not encrypted_b64 or not private_key_pem:
        return None
    try:
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(), password=None, backend=default_backend()
        )
        encrypted_bytes = base64.b64decode(encrypted_b64)
        decrypted_bytes = private_key.decrypt(encrypted_bytes, padding.PKCS1v15())
        
        # 尝试解析为 JSON
        try:
            return json.loads(decrypted_bytes.decode('utf-8'))
        except json.JSONDecodeError:
            # 兼容旧版本纯文本 Key 的情况
            return {'k': decrypted_bytes.decode('utf-8'), 't': None}
            
    except Exception as e:
        print(f"❌ RSA 解密失败: {e}")
        return None

def send_email(to_email, subject, html_content):
    if not to_email or "None" in str(to_email) or "@" not in str(to_email):
        print(f"⚠️ 无效邮箱地址: {to_email}")
        return False
        
    msg = MIMEMultipart('alternative')
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(html_content, 'html'))
    
    try:
        server_host = "smtp.qq.com" if "qq.com" in SENDER_EMAIL else "smtp.gmail.com"
        port = 465 if "qq.com" in SENDER_EMAIL else 587
        
        if port == 465:
            server = smtplib.SMTP_SSL(server_host, 465)
        else:
            server = smtplib.SMTP(server_host, port)
            server.starttls()
            
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"❌ 发信异常: {e}")
        return False

def send_warning(to_email, remaining_sec):
    """ 发送唤醒邮件 """
    print(f"⏰ 发送唤醒 -> {to_email}")
    time_str = str(timedelta(seconds=int(remaining_sec)))
    html = f"""
    <div style="border:2px solid #ffcc00; padding:20px; color:#333; font-family: sans-serif;">
        <h2 style="color:#e6b800;">⚠ 凤凰协议：心跳即将停止</h2>
        <p>您的死手开关倒计时仅剩：<strong style="font-size:1.2em">{time_str}</strong></p>
        <p>如果您还安全，请立即点击下方按钮重置系统：</p>
        <a href="{BASE_URL}" style="background:#ffcc00; color:#000; padding:15px 30px; text-decoration:none; font-weight:bold; display:inline-block; margin-top:10px; border-radius: 4px;">我是本人，立即签到</a>
        <p style="font-size:12px; color:#666; margin-top:20px;">(若不操作，系统将按计划发送遗嘱)</p>
    </div>
    """
    return send_email(to_email, "【警报】请确认您的安全状态", html)

def send_final(to_email, key, uid):
    """ 发送最终遗嘱 """
    print(f"🚀 发送遗嘱 -> {to_email}")
    html = f"""
    <div style="border-left:5px solid #ff3333; padding:20px; font-family: sans-serif;">
        <h2>凤凰协议 | 资产提取通知</h2>
        <p>委托人设定的信托已激活。请在电脑端访问：<br>
        <a href="{BASE_URL}">{BASE_URL}</a></p>
        <div style="background:#f4f4f4; padding:15px; margin:15px 0; font-family:monospace; border-radius: 4px;">
            <strong>Vault ID:</strong> {uid}<br>
            <strong>AES Key:</strong> {key}
        </div>
        <p style="color:red; font-size:12px;">数据将在解密后24小时销毁。</p>
    </div>
    """
    return send_email(to_email, "【绝密】数字资产提取通知", html)

def watchdog():
    print("🐕 凤凰看门狗 V7.1 (安全加固版) 启动...")
    db = get_db()
    if not db: return

    try:
        # 使用 Service Role Key 可以无视 RLS 读取所有 active 用户
        response = db.table("vaults").select("*").eq("status", "active").execute()
        users = response.data
    except Exception as e:
        print(f"❌ 数据库读取失败: {e}")
        return

    now = datetime.now(timezone.utc)

    for row in users:
        try:
            uid = row.get('id')
            last_check = parse_time_safe(row.get('last_checkin_at'))
            
            # 数据完整性检查
            if not uid or not last_check: 
                print(f"⚠️ 跳过无效记录: {uid}")
                continue

            # 1. 计算时间
            elapsed = (now - last_check).total_seconds()
            timeout = row.get('timeout_seconds', 0)
            remaining = timeout - elapsed

            # 预警配置
            warn_start = row.get('warn_start_seconds', 0)
            warn_interval = row.get('warn_interval_seconds', 3600)
            warn_max = row.get('warn_max_count', 0)
            warn_sent = row.get('warn_sent_count', 0)
            last_warn = parse_time_safe(row.get('last_warn_at'))
            owner_email = row.get('owner_email')

            print(f"🔍 [{uid[:4]}] 剩余: {int(remaining)}s | 预警: {warn_sent}/{warn_max}")

            # --- 阶段 A: 最终触发 ---
            if remaining <= 0:
                print(f"⚡ [{uid[:4]}] 倒计时归零，执行发射程序...")
                
                # 解密 Payload
                payload = rsa_decrypt(row.get('key_storage'), RSA_PRIVATE_KEY_PEM)
                
                if payload and payload.get('t') and payload.get('k'):
                    # 尝试发送
                    if send_final(payload['t'], payload['k'], uid):
                        # 成功后，标记为 dispatched 并销毁 key_storage
                        db.table("vaults").update({
                            "status": "dispatched", 
                            "key_storage": "BURNED",
                            "encrypted_data": "BURNED_METADATA" # 可选：如需保留密文供手动提取则不销毁此项
                        }).eq("id", uid).execute()
                        print(f"🔥 [{uid[:4]}] 发射完成，密钥已销毁")
                    else:
                        print(f"❌ [{uid[:4]}] 发送失败，保持 active 状态等待重试")
                else:
                    print(f"❌ [{uid[:4]}] 解密失败或数据损坏，无法发送")

            # --- 阶段 B: 智能唤醒 ---
            elif remaining <= warn_start and warn_sent < warn_max and owner_email:
                time_since_last_warn = (now - last_warn).total_seconds() if last_warn else 999999999
                
                if time_since_last_warn >= warn_interval:
                    if send_warning(owner_email, remaining):
                        db.table("vaults").update({
                            "warn_sent_count": warn_sent + 1,
                            "last_warn_at": datetime.now().isoformat()
                        }).eq("id", uid).execute()
                        print(f"✅ [{uid[:4]}] 唤醒邮件已发送 ({warn_sent+1}/{warn_max})")
                else:
                    pass # 冷却中

        except Exception as inner_e:
            print(f"⚠️ 处理用户 {row.get('id', 'Unknown')} 时出错: {inner_e}")
            continue

if __name__ == "__main__":
    if RSA_PRIVATE_KEY_PEM: 
        watchdog()
    else: 
        print("❌ 致命错误: 未配置 RSA_PRIVATE_KEY")

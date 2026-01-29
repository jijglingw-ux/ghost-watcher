import os
import smtplib
import json
from email.message import EmailMessage
from datetime import datetime, timezone, timedelta
from supabase import create_client

# ================= 依赖库 =================
# pip install supabase cryptography
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
import base64

# ================= 环境变量配置 =================
# 这些必须在 GitHub Secrets 中配置
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
RSA_PRIVATE_KEY_PEM = os.environ.get("RSA_PRIVATE_KEY")
SENDER_EMAIL = os.environ.get("EMAIL_USER")
SENDER_PASSWORD = os.environ.get("EMAIL_PASS")
BASE_URL = "https://your-username.github.io/phoenix-protocol/" # 替换为你的前端网址

def get_db():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def parse_time_safe(time_str):
    """ 安全解析时间字符串，处理带时区和不带时区的情况 """
    if not time_str: return None
    try:
        clean_str = time_str.replace('Z', '+00:00')
        # 截断微秒部分以兼容旧版本 Python ISO 解析
        if '.' in clean_str:
            clean_str = clean_str.split('.')[0] + '+00:00'
        return datetime.fromisoformat(clean_str)
    except Exception as e:
        print(f"⚠️ 时间解析错误: {e}")
        return None

def rsa_decrypt(encrypted_b64, private_key_pem):
    """ 使用 RSA 私钥解密 AES Key """
    try:
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(), password=None, backend=default_backend()
        )
        encrypted_bytes = base64.b64decode(encrypted_b64)
        decrypted_bytes = private_key.decrypt(encrypted_bytes, padding.PKCS1v15())
        
        # 尝试解析为 JSON (新版), 失败则返回原始字符串 (旧版兼容)
        try:
            return json.loads(decrypted_bytes.decode('utf-8'))
        except:
            return {'k': decrypted_bytes.decode('utf-8'), 't': None}
    except Exception as e:
        print(f"❌ RSA 解密失败: {e}")
        return None

def send_email(to_email, subject, html_content):
    """ 发送邮件核心逻辑 (支持 SSL/TLS) """
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("❌ 错误: 环境变量缺少邮箱配置")
        return False
    
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email
    msg.set_content(html_content, subtype='html', charset='utf-8')
    
    try:
        # 自动判断 QQ 邮箱 (SSL 465) 或 Gmail (TLS 587)
        server_host = "smtp.qq.com" if "qq.com" in SENDER_EMAIL else "smtp.gmail.com"
        port = 465 if "qq.com" in SENDER_EMAIL else 587
        
        if port == 465:
            server = smtplib.SMTP_SSL(server_host, 465)
        else:
            server = smtplib.SMTP(server_host, port)
            server.starttls()
            
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"❌ 邮件发送异常: {e}")
        return False

def send_warning(to_email, remaining_sec):
    """ 发送唤醒/预警邮件 """
    time_str = str(timedelta(seconds=int(remaining_sec)))
    html = f"""
    <div style="border:2px solid #ffcc00; padding:20px; color:#333; font-family:sans-serif; background:#fff;">
        <h2 style="color:#e6b800;">⚠ 凤凰协议：最后唤醒呼叫</h2>
        <p>您的死手开关倒计时仅剩：<strong>{time_str}</strong></p>
        <p>若您确认安全，请立即重置系统：</p>
        <a href="{BASE_URL}" style="background:#ffcc00; color:#000; padding:15px 30px; text-decoration:none; font-weight:bold; display:inline-block; border-radius:4px;">我是本人，立即签到</a>
        <p style="font-size:12px; color:#999; margin-top:20px;">此邮件由自动化看门狗发出。</p>
    </div>
    """
    return send_email(to_email, "【警报】请确认您的安全状态", html)

def send_final(to_email, key, uid):
    """ 发送最终遗嘱提取凭证 """
    safe_uid = str(uid)
    safe_key = str(key)
    
    html = f"""
    <div style="border-left:5px solid #ff3333; padding:20px; font-family:sans-serif; background:#fff;">
        <h2 style="color:#ff3333;">凤凰协议 | 资产提取通知</h2>
        <p>委托人设定的信托条件已触发。请在<strong>安全的电脑端</strong>访问：<br>
        <a href="{BASE_URL}" style="color:#ff3333;">{BASE_URL}</a></p>
        
        <div style="background:#f4f4f4; padding:15px; margin:15px 0; font-family:monospace; border-radius:4px; border:1px solid #ddd;">
            <strong>Vault ID:</strong> {safe_uid}<br>
            <strong>AES Key:</strong> {safe_key}
        </div>
        
        <div style="color:red; font-size:13px; font-weight:bold; margin-top:10px;">
            ⚠ 警告：这是一次性提取凭证。<br>
            一旦您解密查看，服务器上的数据将立即物理销毁。<br>
            请准备好纸笔，勿使用截图或云笔记。
        </div>
    </div>
    """
    return send_email(to_email, "【绝密】数字资产提取通知", html)

def watchdog():
    print("🐕 凤凰看门狗 V7.5 (Burn-on-Read Compatible) 启动...")
    db = get_db()
    
    # 关键逻辑：只获取 'active' 状态
    # 过滤掉已发送(dispatched)和已销毁(burned)的记录
    try:
        response = db.table("vaults").select("*").eq("status", "active").execute()
        users = response.data
    except Exception as e:
        print(f"⚠️ 数据库连接失败: {e}")
        return

    if not users:
        print("💤 当前无活跃监控目标")
        return

    now = datetime.now(timezone.utc)

    for row in users:
        uid = row['id']
        # 容错处理：如果时间字段为空，跳过
        if not row.get('last_checkin_at'): continue
        
        last_check = parse_time_safe(row['last_checkin_at'])
        if not last_check: continue

        elapsed = (now - last_check).total_seconds()
        timeout = row.get('timeout_seconds', 60*60*24) # 默认一天
        remaining = timeout - elapsed
        
        # 预警参数
        warn_start = row.get('warn_start_seconds', 300)
        warn_interval = row.get('warn_interval_seconds', 3600)
        warn_max = row.get('warn_max_count', 3)
        warn_sent = row.get('warn_sent_count', 0)
        last_warn = parse_time_safe(row.get('last_warn_at'))
        owner_email = row.get('owner_email')

        print(f"🔍 ID[{uid[:4]}] 剩余: {int(remaining)}s | 状态: {row.get('status')}")

        # === 阶段 A: 触发死手开关 ===
        if remaining <= 0:
            print("⚡ 倒计时归零，准备发射...")
            
            # 1. 解密获得 AES Key (仅在内存中存在)
            payload = rsa_decrypt(row['key_storage'], RSA_PRIVATE_KEY_PEM)
            
            if payload and payload.get('t') and payload.get('k'):
                # 2. 发送邮件给受益人
                if send_final(payload['t'], payload['k'], uid):
                    # 3. 关键更新：状态改为 dispatched，记录发送时间
                    # 注意：这里不删除数据，数据留给受益人提取时"阅后即焚"
                    db.table("vaults").update({
                        "status": "dispatched", 
                        "dispatched_at": datetime.now().isoformat()
                    }).eq("id", uid).execute()
                    print("🔥 邮件已投递。状态已更新为 [dispatched]。")
                else:
                    print("❌ 邮件发送失败，将在下个周期重试")
            else:
                print("❌ 致命错误：私钥解密失败，无法获取明文 Key")

        # === 阶段 B: 发送唤醒预警 ===
        elif remaining <= warn_start and warn_sent < warn_max and owner_email:
            time_since_last_warn = (now - last_warn).total_seconds() if last_warn else 999999
            
            if time_since_last_warn >= warn_interval:
                if send_warning(owner_email, remaining):
                    db.table("vaults").update({
                        "warn_sent_count": warn_sent + 1,
                        "last_warn_at": datetime.now().isoformat()
                    }).eq("id", uid).execute()
                    print(f"✅ 唤醒邮件已发送 ({warn_sent+1}/{warn_max})")
            else:
                print(f"⏳ 预警冷却中 ({int(warn_interval - time_since_last_warn)}s)")

if __name__ == "__main__":
    if RSA_PRIVATE_KEY_PEM and SUPABASE_URL:
        watchdog()
    else:
        print("❌ 启动失败：缺少必要环境变量 (Secrets)")

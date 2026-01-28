import os
import smtplib
import json
import time
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from supabase import create_client
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

# ================= 配置区 =================
# 环境变量获取 (本地运行时可直接填入字符串)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
RSA_PRIVATE_KEY_PEM = os.environ.get("RSA_PRIVATE_KEY")
SENDER_EMAIL = os.environ.get("EMAIL_USER")
SENDER_PASSWORD = os.environ.get("EMAIL_PASS")
BASE_URL = "https://jijglingw-ux.github.io/ghost-watcher/"  # 你的前端地址

def get_db():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def parse_time_safe(time_str):
    if not time_str: return None
    try:
        clean_str = time_str.replace('Z', '+00:00')
        if '.' in clean_str:
            clean_str = clean_str.split('.')[0] + '+00:00'
        return datetime.fromisoformat(clean_str)
    except Exception as e:
        print(f"⚠️ 时间格式错误: {e}")
        return None

def rsa_decrypt(encrypted_b64):
    try:
        private_key = serialization.load_pem_private_key(
            RSA_PRIVATE_KEY_PEM.encode(), password=None, backend=default_backend()
        )
        encrypted_bytes = base64.b64decode(encrypted_b64)
        decrypted_bytes = private_key.decrypt(encrypted_bytes, padding.PKCS1v15())
        try:
            return json.loads(decrypted_bytes.decode('utf-8'))
        except:
            return {'k': decrypted_bytes.decode('utf-8'), 't': None}
    except Exception as e:
        print(f"❌ 解密失败: {e}")
        return None

def send_email(to_email, subject, html_content):
    if not to_email or "None" in str(to_email): return False
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

def send_warning(to_email, remaining_sec, count_info):
    """ 发送唤醒邮件 """
    print(f"⏰ [唤醒] 发送给 -> {to_email}")
    time_str = str(timedelta(seconds=int(remaining_sec)))
    html = f"""
    <div style="border:4px solid #ffcc00; padding:20px; color:#333; font-family: sans-serif; background-color: #fffdf5;">
        <h2 style="color:#b45309; margin-top:0;">⚠ 凤凰协议：心跳即将停止</h2>
        <p>您的死手开关倒计时仅剩：<strong style="font-size:1.2em; color:#d97706;">{time_str}</strong></p>
        <p>进度：<strong>{count_info}</strong></p>
        <hr style="border:0; border-top:1px solid #eee; margin: 20px 0;">
        <p>如果您还安全，请立即点击下方按钮重置系统：</p>
        <a href="{BASE_URL}" style="background:#ffcc00; color:#000; padding:15px 30px; text-decoration:none; font-weight:bold; display:inline-block; border-radius: 4px; border:1px solid #e6b800;">我是本人，立即签到</a>
        <p style="font-size:12px; color:#666; margin-top:20px;">(若不操作，系统将消耗剩余次数，直至触发遗嘱发送)</p>
    </div>
    """
    return send_email(to_email, f"【警报】请确认安全 (剩余 {time_str})", html)

def send_final(to_email, key, uid):
    """ 发送最终遗嘱 """
    print(f"🚀 [发射] 发送给 -> {to_email}")
    html = f"""
    <div style="border-left:6px solid #ff3333; padding:20px; font-family: monospace; background: #f9f9f9;">
        <h2 style="color:#d32f2f;">PHOENIX PROTOCOL | 资产提取通知</h2>
        <p>委托人设定的信托已激活。请在电脑端访问：</p>
        <p><a href="{BASE_URL}" style="color: #d32f2f; font-weight:bold;">{BASE_URL}</a></p>
        <div style="background:#111; color: #0f0; padding:15px; margin:20px 0; border-radius: 4px; border:1px solid #333;">
            <div>Vault ID: <span style="color:#fff;">{uid}</span></div>
            <div style="margin-top:5px;">AES Key: <span style="color:#fff;">{key}</span></div>
        </div>
        <p style="color:#666; font-size:12px;">此为最终通信。数据将在解密后销毁。</p>
    </div>
    """
    return send_email(to_email, "【绝密】数字资产提取通知", html)

def run_watchdog():
    print(f"🦅 凤凰看门狗 V16.4 扫描中... [{datetime.now().strftime('%H:%M:%S')}]")
    db = get_db()
    # 仅获取活跃状态的包裹
    response = db.table("vaults").select("*").eq("status", "active").execute()
    users = response.data
    now = datetime.now(timezone.utc)

    for row in users:
        try:
            uid = row['id']
            last_check = parse_time_safe(row['last_checkin_at'])
            if not last_check: continue

            # === 1. 时间计算 ===
            elapsed = (now - last_check).total_seconds()
            timeout = row.get('timeout_seconds', 0)
            remaining = timeout - elapsed

            # === 2. 读取配置 ===
            warn_start = row.get('warn_start_seconds', 0)    # 剩余多少秒开始叫
            warn_interval = row.get('warn_interval_seconds', 300) # 间隔
            warn_max = row.get('warn_max_count', 0)          # 总次数
            warn_sent = row.get('warn_sent_count', 0)        # 已发送次数
            last_warn_str = row.get('last_warn_at')
            owner_email = row.get('owner_email')

            # === 3. 逻辑判断 ===
            
            # --- 场景A: 彻底超时 (Dead) ---
            if remaining <= 0:
                print(f"⚡ [触发] ID:{uid[:4]} 超时！执行分发...")
                if row.get('key_storage') == "BURNED": continue # 防止重复处理

                payload = rsa_decrypt(row['key_storage'])
                if payload and payload.get('t'):
                    # 发送遗嘱
                    if send_final(payload['t'], payload['k'], uid):
                        # 销毁密钥，标记完成
                        db.table("vaults").update({
                            "status": "dispatched", 
                            "key_storage": "BURNED"
                        }).eq("id", uid).execute()
                        print("🔥 发射完成，密钥已销毁")
                else:
                    print("❌ 无法解密，跳过")

            # --- 场景B: 唤醒预警 (Warning) ---
            # 条件：进入预警区 AND 次数没用完 AND 有邮箱
            elif remaining <= warn_start and warn_sent < warn_max and owner_email:
                
                # 计算冷却时间
                time_since_last = 9999999
                if last_warn_str:
                    last_warn = parse_time_safe(last_warn_str)
                    if last_warn:
                        time_since_last = (now - last_warn).total_seconds()
                
                # 强制防抖：间隔必须满足设定值，且至少大于60秒（防止并发双发）
                # 逻辑解释：如果用户设间隔10秒，也强制等60秒，防止刷屏
                safe_interval = max(warn_interval, 60)

                if time_since_last >= safe_interval:
                    current_idx = warn_sent + 1
                    count_str = f"第 {current_idx} / {warn_max} 次唤醒"
                    
                    # 发送邮件
                    if send_warning(owner_email, remaining, count_str):
                        # 关键：发送成功后，立即更新数据库，扣除次数
                        db.table("vaults").update({
                            "warn_sent_count": warn_sent + 1,
                            "last_warn_at": datetime.now().isoformat()
                        }).eq("id", uid).execute()
                        print(f"✅ 邮件发送成功 ({current_idx}/{warn_max})")
                else:
                    # 冷却中，静默
                    pass

        except Exception as e:
            print(f"❌ 处理 ID:{row.get('id', '未知')} 出错: {e}")

if __name__ == "__main__":
    if not RSA_PRIVATE_KEY_PEM:
        print("❌ 错误：未配置 RSA 私钥")
    else:
        # 持续运行模式
        while True:
            run_watchdog()
            time.sleep(30) # 30秒轮询一次

// 引入必要的库 (极其精简，只用这两个)
const { createClient } = require('@supabase/supabase-js');
const nodemailer = require('nodemailer');

// 1. 初始化连接
const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_KEY);
const DEAD_MAN_LIMIT_HOURS = 24 * 30; // 设定：30天不登录视为"失联" (可自行修改)

async function runWatchdog() {
    console.log("🐺 守望者启动...");

    // 2. 查库：只查"最后登录时间"比较久的人，且还没发过遗嘱的人
    // 我们假设 user_vault 表里有一个 status 字段，'active' 或者是 'dead'
    const limitDate = new Date();
    limitDate.setHours(limitDate.getHours() - DEAD_MAN_LIMIT_HOURS);

    const { data: lostUsers, error } = await supabase
        .from('user_vault')
        .select('credential_id, last_login, email_to_notify, encrypted_data')
        .lt('last_login', limitDate.toISOString()) // last_login < 30天前
        .is('status', null); // 确保还没处理过 (防止重复发邮件)

    if (error) return console.error("❌ 查询失败:", error);
    if (!lostUsers || lostUsers.length === 0) return console.log("✅ 一切正常: 没有人失联。");

    console.log(`⚠️ 检测到 ${lostUsers.length} 位用户失联！开始执行协议...`);

    // 3. 配置发信服务 (以 Gmail 为例，需要去申请 App Password)
    const transporter = nodemailer.createTransport({
        service: 'Gmail',
        auth: {
            user: process.env.EMAIL_USER, // 你的 Gmail 账号
            pass: process.env.EMAIL_PASS  // 你的 Gmail 应用专用密码
        }
    });

    // 4. 循环处理失联用户
    for (const user of lostUsers) {
        try {
            console.log(`正在向受益人发送用户 ${user.credential_id.slice(0, 5)}... 的遗嘱信标`);

            // A. 发送邮件
            await transporter.sendMail({
                from: '"Phoenix Protocol" <no-reply@phoenix.io>',
                to: user.email_to_notify, // 受益人邮箱
                subject: '【绝密】凤凰协议已触发 - 遗嘱交付',
                text: `
                受益人您好：
                
                如果您收到这封邮件，说明立嘱人已失联超过 ${DEAD_MAN_LIMIT_HOURS / 24} 天。
                根据凤凰协议，无论是死亡还是不可抗力，现在的控制权已移交给您。
                
                请点击下方链接，并使用您的生物密钥（人脸/指纹）提取加密资产：
                https://你的域名.github.io/phoenix/heir.html
                
                (这封邮件是自动发送的，请勿回复)
                `
            });

            // B. 标记为已处理 (防止每5分钟发一次)
            await supabase
                .from('user_vault')
                .update({ status: 'dead', triggered_at: new Date() })
                .eq('credential_id', user.credential_id);

            console.log("✅ 邮件已发送，状态已更新。");

        } catch (err) {
            console.error("❌ 发送失败:", err);
        }
    }
}

runWatchdog();

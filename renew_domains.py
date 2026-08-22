import requests
import os
import smtplib
import ssl
import time
from datetime import datetime
from email.message import EmailMessage

# ============================================================
# DNSHE 多账号域名自动续期脚本（基于 clown145/DNSHE-Auto-Renew）
# 运行环境：GitHub Actions，工作流见 .github/workflows/renew.yml
#
# 需要在仓库 Settings -> Secrets and variables -> Actions 中配置：
#
#  【DNSHE 多账号密钥】（支持多个账号，编号从 1 开始，最多 10 个）
#    DNSHE_API_KEY_1      第 1 个账号的 API Key
#    DNSHE_API_SECRET_1   第 1 个账号的 API Secret
#    DNSHE_API_KEY_2      第 2 个账号的 API Key（可选）
#    DNSHE_API_SECRET_2   第 2 个账号的 API Secret（可选）
#    ... 以此类推，可继续配置 DNSHE_API_KEY_3 ~ DNSHE_API_KEY_10
#
#  【SMTP 邮件通知】（逻辑保持原有不变）
#    SMTP_HOST            SMTP 服务器地址
#    SMTP_PORT            SMTP 端口（默认 465）
#    SMTP_USER            SMTP 登录账号
#    SMTP_PASSWORD        SMTP 密码或授权码
#    SMTP_FROM            发件人地址（可选，默认使用 SMTP_USER）
#    SMTP_TO              收件人地址，多个用英文逗号分隔
#    SMTP_USE_SSL         是否使用 SSL（可选）
#    SMTP_USE_STARTTLS    是否使用 STARTTLS（可选）
# ============================================================

# 从环境变量获取 SMTP 配置（DNSHE 账号密钥由 _collect_accounts 统一读取）
SMTP_HOST = os.environ.get('SMTP_HOST')
SMTP_PORT = os.environ.get('SMTP_PORT') or '465'
SMTP_USER = os.environ.get('SMTP_USER')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
SMTP_FROM = os.environ.get('SMTP_FROM') or SMTP_USER
SMTP_TO = os.environ.get('SMTP_TO')

BASE_URL = "https://api005.dnshe.com/index.php?m=domain_hub"

# 续期阈值：到期时间小于该天数则执行续期
RENEW_THRESHOLD_DAYS = 180

# 最多支持的 DNSHE 账号数量
MAX_ACCOUNTS = 10

# 账号之间的处理间隔（秒），避免触发速率限制
ACCOUNT_SLEEP_SECONDS = 2

def _get_bool_env(name, default):
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default

    normalized = value.strip().lower()
    if normalized in {'1', 'true', 'yes', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'off'}:
        return False
    raise ValueError(f"{name} 必须是 true/false")


def _collect_accounts():
    """从环境变量收集全部 DNSHE 账号（DNSHE_API_KEY_N / DNSHE_API_SECRET_N，N 从 1 开始）"""
    accounts = []
    for index in range(1, MAX_ACCOUNTS + 1):
        key = os.environ.get(f'DNSHE_API_KEY_{index}')
        secret = os.environ.get(f'DNSHE_API_SECRET_{index}')
        if not key and not secret:
            continue
        if not key or not secret:
            print(f"警告: 账号{index} 缺少 API Key 或 API Secret，已跳过")
            continue
        accounts.append({
            'name': f'账号{index}',
            'key': key,
            'secret': secret,
        })
    return accounts


def send_smtp(content):
    if not SMTP_HOST or not SMTP_TO:
        print("未配置 SMTP_HOST 或 SMTP_TO，跳过邮件推送")
        return

    recipients = [address.strip() for address in SMTP_TO.split(',') if address.strip()]
    if not recipients:
        print("SMTP_TO 未包含有效的收件人，跳过邮件推送")
        return
    if not SMTP_FROM:
        print("未配置 SMTP_FROM 或 SMTP_USER，跳过邮件推送")
        return

    try:
        port = int(SMTP_PORT)
        use_ssl = _get_bool_env('SMTP_USE_SSL', port == 465)
        use_starttls = _get_bool_env('SMTP_USE_STARTTLS', not use_ssl)
        if use_ssl and use_starttls:
            raise ValueError("SMTP_USE_SSL 和 SMTP_USE_STARTTLS 不能同时启用")
        if bool(SMTP_USER) != bool(SMTP_PASSWORD):
            raise ValueError("SMTP_USER 和 SMTP_PASSWORD 必须同时配置")

        message = EmailMessage()
        message['Subject'] = 'DNSHE 域名自动续期报告'
        message['From'] = SMTP_FROM
        message['To'] = ', '.join(recipients)
        message.set_content(content)

        smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        with smtp_class(SMTP_HOST, port, timeout=30) as server:
            if use_starttls:
                server.starttls(context=ssl.create_default_context())
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(message, from_addr=SMTP_FROM, to_addrs=recipients)
        print("SMTP 邮件推送成功")
    except Exception as e:
        print(f"SMTP 邮件推送失败: {str(e)}")

def _process_account(account, today, message_parts):
    """处理单个 DNSHE 账号：获取域名列表并执行智能续期，结果按账号追加到汇总内容"""
    headers = {
        "X-API-Key": account['key'],
        "X-API-Secret": account['secret'],
        "Content-Type": "application/json"
    }

    # 1. 获取所有子域名（显式请求到期时间字段）
    list_url = f"{BASE_URL}&endpoint=subdomains&action=list&fields=id,subdomain,rootdomain,full_domain,status,expires_at,never_expires"
    try:
        resp = requests.get(list_url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"获取域名列表失败: {str(e)}")

    # 接口返回失败（如认证失败）时抛出异常，交由外层标注失败账号
    if not data.get('success', True):
        raise RuntimeError(f"获取域名列表失败: {data.get('message') or data.get('msg') or str(data)}")
    subdomains = data.get('subdomains', [])

    renewal_results = []  # 第一段：本次续期结果
    expiry_info = []      # 第二段：所有域名到期时间

    # 2. 遍历域名，检查到期时间并选择性续期（智能续期/永不过期跳过/到期计算逻辑保持原有不变）
    for domain in subdomains:
        domain_id = domain['id']
        full_domain = domain['full_domain']
        expires_at_str = domain.get('expires_at')
        never_expires = domain.get('never_expires', 0)

        # 检查是否为永不过期域名
        if never_expires:
            expiry_info.append(f"{full_domain}: 到期时间 永久有效")
            renewal_results.append(f"⏭️ {full_domain}: 已设置为永不过期，跳过续期")
            continue

        # 计算剩余天数
        expires_at = None
        if expires_at_str:
            expires_at = datetime.strptime(expires_at_str, '%Y-%m-%d %H:%M:%S')
            days_remaining = (expires_at - today).days
        else:
            days_remaining = None

        # 记录到期信息（第二段用）
        if days_remaining is not None:
            expiry_info.append(f"{full_domain}: 到期时间 {expires_at_str} (剩余 {days_remaining}天)")
        else:
            expiry_info.append(f"{full_domain}: 到期时间 未知")

        # 判断是否需要续期：剩余天数 < 180天 才续期
        if days_remaining is not None and days_remaining >= RENEW_THRESHOLD_DAYS:
            renewal_results.append(f"⏭️ {full_domain}: 剩余 {days_remaining}天 >= {RENEW_THRESHOLD_DAYS}天，跳过续期")
            continue

        # 执行续期
        renew_url = f"{BASE_URL}&endpoint=subdomains&action=renew"
        payload = {"subdomain_id": domain_id}

        try:
            r_resp = requests.post(renew_url, headers=headers, json=payload).json()
            if r_resp.get('success'):
                new_expiry = r_resp.get('new_expires_at', '未知')
                charged = r_resp.get('charged_amount', 0)
                renewal_results.append(f"✅ {full_domain}: 续期成功 (新到期: {new_expiry}, 消耗: {charged}积分)")
            else:
                msg = r_resp.get('message', '未知错误')
                renewal_results.append(f"❌ {full_domain}: 续期失败 ({msg})")
        except Exception as e:
            renewal_results.append(f"❌ {full_domain}: 请求异常 ({str(e)})")

    # 3. 将该账号的续期结果与到期时间追加到汇总内容
    message_parts.append("=== 本次续期结果 ===")
    if renewal_results:
        message_parts.extend(renewal_results)
    else:
        message_parts.append("（所有域名剩余天数 >= 180天，本次无需续期）")

    message_parts.append("=== 所有域名到期时间 ===")
    message_parts.extend(expiry_info)


def main():
    accounts = _collect_accounts()
    if not accounts:
        message = "未检测到任何 DNSHE 账号配置，请在仓库 Secrets 中配置 DNSHE_API_KEY_1 / DNSHE_API_SECRET_1"
        print(message)
        send_smtp(message)
        return

    today = datetime.now()
    message_parts = []  # 汇总邮件内容，按账号分段

    # 遍历所有账号：单账号异常不中断整体流程，最终只发一封汇总邮件
    for index, account in enumerate(accounts):
        if index > 0:
            time.sleep(ACCOUNT_SLEEP_SECONDS)  # 账号间间隔，避免触发速率限制
        message_parts.append(f"========== {account['name']} ==========")
        try:
            _process_account(account, today, message_parts)
        except Exception as e:
            # 失败账号标注名称与错误，继续处理其他账号
            message_parts.append(f"❌ {account['name']}: 处理失败 ({str(e)})")
            print(f"{account['name']} 处理异常，继续处理其他账号: {str(e)}")

    message = "\n".join(message_parts)
    print(message)
    send_smtp(message)

if __name__ == "__main__":
    main()

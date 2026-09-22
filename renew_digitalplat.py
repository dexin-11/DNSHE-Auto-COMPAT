import requests
import os
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from urllib.parse import quote
from uuid import uuid4

# ============================================================
# DIGITALPLAT 域名自动续期脚本（结构仿照 DNSHE 自动续期脚本）
# 运行环境：GitHub Actions，工作流见 .github/workflows/renew-digitalplat.yml
#
# 需要在仓库 Settings -> Secrets and variables -> Actions 中配置：
#
#  【DigitalPlat API 密钥】（单账号）
#    DIGITALPLAT_API_KEY       在 DigitalPlat 后台 Account & security 创建的 API Key
#
#  【续期参数】（可选，有默认值）
#    DIGITALPLAT_PAYMENT_METHOD  续费支付方式，默认 sandbox（免费域名；如实际环境不同请按需修改）
#    DIGITALPLAT_RENEW_YEARS     续费年数，默认 1
#    DIGITALPLAT_RENEW_THRESHOLD_DAYS  续期阈值天数（到期小于该天数才续期），默认 180
#
#  【SMTP 邮件通知】（与 DNSHE 共用同一套配置）
#    SMTP_HOST            SMTP 服务器地址
#    SMTP_PORT            SMTP 端口（默认 465）
#    SMTP_USER            SMTP 登录账号
#    SMTP_PASSWORD        SMTP 密码或授权码
#    SMTP_FROM            发件人地址（可选，默认使用 SMTP_USER）
#    SMTP_TO              收件人地址，多个用英文逗号分隔
#    SMTP_USE_SSL         是否使用 SSL（可选）
#    SMTP_USE_STARTTLS    是否使用 STARTTLS（可选）
# ============================================================

# 从环境变量获取 SMTP 配置（DigitalPlat API 密钥由 main 统一读取）
SMTP_HOST = os.environ.get('SMTP_HOST')
SMTP_PORT = os.environ.get('SMTP_PORT') or '465'
SMTP_USER = os.environ.get('SMTP_USER')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
SMTP_FROM = os.environ.get('SMTP_FROM') or SMTP_USER
SMTP_TO = os.environ.get('SMTP_TO')

API_BASE = "https://domain-api.digitalplat.org/api/v1"

# 续期阈值：到期时间小于该天数则执行续期
RENEW_THRESHOLD_DAYS = int(os.environ.get('DIGITALPLAT_RENEW_THRESHOLD_DAYS') or '180')

# 续费年数与支付方式（免费域名默认 sandbox，实际环境不同请配置 DIGITALPLAT_PAYMENT_METHOD）
RENEW_YEARS = int(os.environ.get('DIGITALPLAT_RENEW_YEARS') or '1')
PAYMENT_METHOD = os.environ.get('DIGITALPLAT_PAYMENT_METHOD') or 'sandbox'


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
        message['Subject'] = 'DigitalPlat 域名自动续期报告'
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


def _extract_error(data):
    """从 DigitalPlat 错误响应中提取可读错误信息（错误格式: {"error": {"message": "...", "status": ...}}）"""
    error = data.get('error') if isinstance(data, dict) else None
    if isinstance(error, dict):
        return error.get('message') or str(error)
    if error:
        return str(error)
    return str(data)


def _parse_expiry(expiry_str):
    """解析到期时间，兼容文档（%Y-%m-%d）与实际接口（%Y%m%d，如 20270921）等多种格式"""
    for fmt in ('%Y-%m-%d', '%Y%m%d', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(str(expiry_str).strip(), fmt)
        except ValueError:
            continue
    return None


def _process_domains(api_key, today, message_parts):
    """处理 DigitalPlat 账号：获取域名列表并执行智能续期，结果追加到汇总内容"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 1. 获取所有域名
    list_url = f"{API_BASE}/domains"
    try:
        resp = requests.get(list_url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"获取域名列表失败: {str(e)}")

    # 接口返回失败（如认证失败）时抛出异常，交由外层标注失败账号
    if not data.get('success', True):
        raise RuntimeError(f"获取域名列表失败: {_extract_error(data)}")
    domains = data.get('data', [])
    if not isinstance(domains, list):
        raise RuntimeError(f"获取域名列表失败: data 字段格式异常 ({str(data.get('data'))[:200]})")

    renewal_results = []  # 第一段：本次续期结果
    expiry_info = []      # 第二段：所有域名到期时间

    # 2. 遍历域名，检查到期时间并选择性续期（智能续期/订阅制域名跳过/到期计算逻辑与 DNSHE 一致）
    for domain in domains:
        # 实际接口字段为 domain/expires_at，文档字段为 name/expiry_date，两者兼容
        name = domain.get('domain') or domain.get('name')
        if not name:
            continue
        lifecycle_type = domain.get('lifecycle_type')
        expiry_str = domain.get('expires_at') or domain.get('expiry_date')

        # 跳过订阅制域名（由订阅自动续期，无需手动续费，类似 DNSHE 的永不过期域名）
        if lifecycle_type == 'subscription':
            expiry_info.append(f"{name}: 订阅制域名，跳过续期")
            renewal_results.append(f"⏭️ {name}: 订阅制域名，跳过续期")
            continue

        # 计算剩余天数
        expires_at = _parse_expiry(expiry_str) if expiry_str else None
        days_remaining = (expires_at - today).days if expires_at else None

        # 记录到期信息（第二段用）
        if days_remaining is not None:
            expiry_info.append(f"{name}: 到期时间 {expiry_str} (剩余 {days_remaining}天)")
        else:
            expiry_info.append(f"{name}: 到期时间 未知")

        # 判断是否需要续期：剩余天数 < 阈值天才续期
        if days_remaining is not None and days_remaining >= RENEW_THRESHOLD_DAYS:
            renewal_results.append(f"⏭️ {name}: 剩余 {days_remaining}天 >= {RENEW_THRESHOLD_DAYS}天，跳过续期")
            continue

        # 执行续期（续费接口要求 Idempotency-Key 请求头，文档未提及，缺失会报 idempotency_key_required）
        renew_url = f"{API_BASE}/domains/{quote(name, safe='')}/renew"
        payload = {"years": RENEW_YEARS, "payment_method": PAYMENT_METHOD}
        renew_headers = dict(headers)
        renew_headers["Idempotency-Key"] = str(uuid4())

        try:
            r_resp = requests.post(renew_url, headers=renew_headers, json=payload).json()
            if r_resp.get('success'):
                r_data = r_resp.get('data') or {}
                registry_status = r_data.get('registry_status', '未知')
                renewal_results.append(f"✅ {name}: 续期成功 (registry_status: {registry_status}, 续费{RENEW_YEARS}年)")
            else:
                renewal_results.append(f"❌ {name}: 续期失败 ({_extract_error(r_resp)})")
        except Exception as e:
            renewal_results.append(f"❌ {name}: 请求异常 ({str(e)})")

    # 3. 将该账号的续期结果与到期时间追加到汇总内容
    message_parts.append("=== 本次续期结果 ===")
    if renewal_results:
        message_parts.extend(renewal_results)
    else:
        message_parts.append(f"（所有域名剩余天数 >= {RENEW_THRESHOLD_DAYS}天，本次无需续期）")

    message_parts.append("=== 所有域名到期时间 ===")
    message_parts.extend(expiry_info)


def main():
    api_key = os.environ.get('DIGITALPLAT_API_KEY')
    if not api_key:
        message = "未检测到 DIGITALPLAT_API_KEY 配置，请在仓库 Secrets 中配置 DIGITALPLAT_API_KEY"
        print(message)
        send_smtp(message)
        return

    today = datetime.now()
    message_parts = []  # 汇总邮件内容

    message_parts.append("========== DigitalPlat 账号 ==========")
    try:
        _process_domains(api_key, today, message_parts)
    except Exception as e:
        # 处理失败时标注错误，仍发送通知
        message_parts.append(f"❌ DigitalPlat 账号: 处理失败 ({str(e)})")
        print(f"DigitalPlat 账号处理异常: {str(e)}")

    message = "\n".join(message_parts)
    print(message)
    send_smtp(message)


if __name__ == "__main__":
    main()

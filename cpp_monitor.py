import os
import json
import time
import smtplib
import requests
from email.mime.text import MIMEText
from datetime import datetime

API_URL = "https://www.allcpp.cn/allcpp/event/getEventListApprove.do"
API_PARAMS = {
    "eventmainid": 0, "pageindex": 1, "pagesize": 8,
    "showapprove": 1, "eventEnabled": 1, "cityId": -1, "typeId": -1,
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.allcpp.cn/mng/apply.do?t=1&pageNo=1",
    "X-Requested-With": "XMLHttpRequest",
}

def log(msg):
    print("[" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "] " + msg)

def get_last_status():
    try:
        r = requests.get("https://api.github.com/gists/" + os.environ["GIST_ID"],
                         headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"]},
                         timeout=10)
        if r.status_code == 200:
            files = r.json().get("files", {})
            if "state.json" in files:
                return json.loads(files["state.json"]["content"])
    except Exception as e:
        log("读取历史状态失败: " + str(e))
    return None

def save_status(state):
    try:
        payload = {"files": {"state.json": {"content": json.dumps(state)}}}
        requests.patch("https://api.github.com/gists/" + os.environ["GIST_ID"],
                       headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
                                "Accept": "application/vnd.github.v3+json"},
                       json=payload, timeout=10)
    except Exception as e:
        log("保存状态失败: " + str(e))

def send_mail(title, body):
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = title
        msg["From"] = os.environ["EMAIL_SENDER"]
        msg["To"] = os.environ["EMAIL_RECEIVER"]
        smtp = smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=10)
        smtp.login(os.environ["EMAIL_SENDER"], os.environ["EMAIL_AUTH"])
        smtp.sendmail(os.environ["EMAIL_SENDER"],
                      os.environ["EMAIL_RECEIVER"].split(","),
                      msg.as_string())
        smtp.quit()
        log("邮件已发送: " + title)
    except Exception as e:
        log("邮件发送失败: " + str(e))

def fetch_status():
    headers = dict(HEADERS)
    headers["Cookie"] = os.environ["COOKIE"]
    resp = requests.get(API_URL, params=API_PARAMS, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    evt = data["result"]["list"][0]
    ec = evt["eventCircle"]
    name = evt.get("totalName", "")
    circle = evt.get("circle", {}).get("name", "")

    event_enabled = ec.get("eventEnabled", -1)
    is_ready = ec.get("isReadyPublish", False)
    pre_count = ec.get("prePositionCount", 0)

    if event_enabled == 1 and is_ready:
        status_text = "预审通过 等待签约（" + str(pre_count) + "摊）"
        status_key = "approved"
    else:
        mapping = {-1: "未完善信息", -2: "非管理员", 0: "已过审", 1: "审核中",
                   2: "未过审", 3: "未抽中", 4: "已退摊"}
        status_text = mapping.get(event_enabled, "未知(" + str(event_enabled) + ")")
        if event_enabled == 0:
            pos = ec.get("position", "")
            if pos:
                status_text += " 摊位号:" + pos
        status_key = str(event_enabled)

    return {"name": name, "circle": circle, "text": status_text, "key": status_key}

def main():
    if not os.environ.get("COOKIE"):
        log("未配置 CPP_COOKIE Secret")
        return

    log("=== CPP 监控启动 ===")

    try:
        current = fetch_status()
    except Exception as e:
        log("获取状态失败: " + str(e))
        return

    last = get_last_status()

    log("当前状态: " + current["text"])
    if last:
        log("上次状态: " + last.get("text", "未知"))

    if last is None:
        log("首次运行，发送上线通知")
        send_mail("【CPP监控已上线】",
                  current["name"] + "  " + current["circle"] +
                  "\n当前状态: " + current["text"])
    elif last.get("key") != current["key"]:
        log("★★★ 状态变化 ★★★  [" + last["text"] + "] -> [" + current["text"] + "]")
        send_mail("CPP摊位审核状态变化",
                  current["name"] + "  " + current["circle"] +
                  "\n状态: " + last["text"] + " -> " + current["text"])

        if current["key"] == "approved":
            send_mail("🎉 预审通过！恭喜！",
                      current["name"] + " " + current["circle"] + "\n恭喜预审通过！")
        elif current["key"] == "0":
            send_mail("🎊 已过审！",
                      current["name"] + " " + current["circle"] + "\n摊位已过审！")
        elif current["key"] == "2":
            send_mail("⚠️ 审核未通过！",
                      current["name"] + " " + current["circle"] + "\n请及时查看原因！")
    else:
        log("状态无变化，跳过邮件")

    save_status(current)
    log("状态已保存")
    log("=== 监控结束 ===")

if __name__ == "__main__":
    main()

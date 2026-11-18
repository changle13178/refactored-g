import os, json, base64, smtplib, requests
from email.mime.text import MIMEText
from datetime import datetime

OWNER = os.environ["GITHUB_REPOSITORY"].split("/")[0]
REPO = os.environ["GITHUB_REPOSITORY"].split("/")[1]
TOKEN = os.environ["GITHUB_TOKEN"]
STATE_FILE = "state.json"

API_URL = "https://www.allcpp.cn/allcpp/event/getEventListApprove.do"
API_PARAMS = {"eventmainid":0,"pageindex":1,"pagesize":8,"showapprove":1,"eventEnabled":1,"cityId":-1,"typeId":-1}
HEADERS = {"User-Agent":"Mozilla/5.0","Accept":"application/json","Referer":"https://www.allcpp.cn/mng/apply.do?t=1","X-Requested-With":"XMLHttpRequest"}

GH_API = "https://api.github.com/repos/" + OWNER + "/" + REPO + "/contents/" + STATE_FILE

def log(m):
    print("[" + datetime.now().strftime("%H:%M:%S") + "] " + m)

def get_state():
    r = requests.get(GH_API, headers={"Authorization":"Bearer "+TOKEN}, timeout=10)
    if r.status_code == 200:
        d = r.json()
        content = base64.b64decode(d["content"]).decode("utf-8")
        return json.loads(content), d["sha"]
    return None, None

def save_state(state, sha):
    content = base64.b64encode(json.dumps(state).encode("utf-8")).decode("utf-8")
    body = {"message":"update state","content":content}
    if sha:
        body["sha"] = sha
    requests.put(GH_API, json=body, headers={"Authorization":"Bearer "+TOKEN,"Accept":"application/vnd.github.v3+json"}, timeout=10)

def send_mail(title, body):
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = title
        msg["From"] = os.environ["EMAIL_SENDER"]
        msg["To"] = os.environ["EMAIL_RECEIVER"]
        s = smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=10)
        s.login(os.environ["EMAIL_SENDER"], os.environ["EMAIL_AUTH"])
        s.sendmail(os.environ["EMAIL_SENDER"], os.environ["EMAIL_RECEIVER"].split(","), msg.as_string())
        s.quit()
        log("✅ 邮件已发送: " + title)
    except Exception as e:
        log("❌ 邮件失败: " + str(e))

def fetch():
    h = dict(HEADERS)
    h["Cookie"] = os.environ["COOKIE"]
    r = requests.get(API_URL, params=API_PARAMS, headers=h, timeout=15)
    r.raise_for_status()
    evt = r.json()["result"]["list"][0]
    ec = evt["eventCircle"]
    name = evt.get("totalName","")
    circle = evt.get("circle",{}).get("name","")
    ev = ec.get("eventEnabled",-1)
    ready = ec.get("isReadyPublish",False)
    pc = ec.get("prePositionCount",0)
    if ev == 1 and ready:
        text = "预审通过 等待签约(" + str(pc) + "摊)"
        key = "approved"
    else:
        mp = {-1:"未完善信息",-2:"非管理员",0:"已过审",1:"审核中",2:"未过审",3:"未抽中",4:"已退摊"}
        text = mp.get(ev, "未知("+str(ev)+")")
        if ev == 0 and ec.get("position"):
            text += " 摊位号:" + ec["position"]
        key = str(ev) + "_" + str(ready)
    return {"name":name,"circle":circle,"text":text,"key":key}

def main():
    log("=== CPP 监控 ===")
    try:
        cur = fetch()
    except Exception as e:
        log("❌ 获取失败: " + str(e))
        return

    last, sha = get_state()
    log("当前: " + cur["text"])
    if last:
        log("上次: " + last.get("text",""))

    if last is None:
        log("首次运行，发送上线通知")
        send_mail("【CPP监控已上线】", cur["name"] + " " + cur["circle"] + "\n当前: " + cur["text"])
    elif last.get("key") != cur["key"]:
        log("★★★ 状态变化 ★★★  [" + last["text"] + "] -> [" + cur["text"] + "]")
        send_mail("CPP摊位审核状态变化", cur["name"] + " " + cur["circle"] + "\n" + last["text"] + " -> " + cur["text"])
        if cur["key"] == "approved":
            send_mail("🎉 预审通过！恭喜！", cur["name"] + " " + cur["circle"])
        elif cur["key"].startswith("0") and cur["key"] != "approved":
            send_mail("🎊 已过审！", cur["name"] + " " + cur["circle"])
        elif cur["key"].startswith("2"):
            send_mail("⚠️ 审核未通过！", cur["name"] + " " + cur["circle"])
    else:
        log("状态无变化")

    save_state(cur, sha)
    log("=== 结束 ===")

if __name__ == "__main__":
    main()

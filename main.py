import gspread
from oauth2client.service_account import ServiceAccountCredentials
from fastapi import FastAPI
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import uvicorn
import os
from dotenv import load_dotenv

# ---------------- بارگذاری متغیرهای محیطی ----------------
load_dotenv()

MAIL_HOST = os.getenv("MAIL_HOST")
MAIL_PORT = int(os.getenv("MAIL_PORT", 465))
MAIL_USER = os.getenv("MAIL_USER")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
MAIL_FROM = os.getenv("MAIL_FROM_ADDRESS")
PURCHASE_MANAGER_EMAIL = os.getenv("PURCHASE_MANAGER_EMAIL")

# ---------------- Google Sheets ----------------
JSON_FILE = "agent-project-473411-c4c269e52211.json"
SHEET_ID = "1JO71SG-BX6TvwLPnKQCHOJn1ADZ46C4eSc4n951r5Qs"

# ---------------- FastAPI ----------------
app = FastAPI()

# آیتم‌هایی که نیاز به سفارش دارند (حافظه موقت)
pending_items = []


def read_items_from_sheet():
    """خواندن آیتم‌ها از Google Sheets"""
    global pending_items
    scope = ["https://spreadsheets.google.com/feeds",
             "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_FILE, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID).sheet1
    data = sheet.get_all_records()

    pending_items = []
    for row in data:
        try:
            on_hand = int(row["on_hand_qty"])
            reorder = int(row["reorder_threshold"])
            if on_hand <= reorder:
                pending_items.append(row)
        except Exception:
            continue


def send_email(to_email, subject, body):
    """ارسال ایمیل"""
    msg = MIMEMultipart()
    msg["From"] = MAIL_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    with smtplib.SMTP_SSL(MAIL_HOST, MAIL_PORT) as server:
        server.set_debuglevel(1)
        #server.starttls()
        server.login(MAIL_USER, MAIL_PASSWORD)
        server.sendmail(MAIL_FROM, to_email, msg.as_string())


def notify_user():
    """ارسال ایمیل اولیه به کاربر برای تایید یا رد"""
    if not pending_items:
        return

    items_text = "<br>".join(
        [f"{item['item_name']} (SKU: {item['item_sku']}) - موجودی: {item['on_hand_qty']} - "
         f"آستانه: {item['reorder_threshold']} - مقدار سفارش: {item['order_qty']}"
         for item in pending_items]
    )

    approve_link = "http://127.0.0.1:8000/approve?decision=yes"
    reject_link = "http://127.0.0.1:8000/approve?decision=no"

    body = f"""
    <p>لیست آیتم‌هایی که نیاز به سفارش دارند:</p>
    <p>{items_text}</p>
    <br>
    <a href="{approve_link}" style="padding:10px 20px; background-color:green; color:white; text-decoration:none;">بله</a>
    <a href="{reject_link}" style="padding:10px 20px; background-color:red; color:white; text-decoration:none;">خیر</a>
    """

    send_email(PURCHASE_MANAGER_EMAIL, "تایید سفارش خرید", body)


def notify_suppliers():
    """ارسال ایمیل به تأمین‌کنندگان بعد از تایید کاربر"""
    for item in pending_items:
        subject = f"سفارش خرید: {item['item_name']}"
        body = (
            f"سلام {item['supplier_name']},<br><br>"
            f"لطفاً سفارش زیر ثبت گردد:<br><br>"
            f"کالا: {item['item_name']} (SKU: {item['item_sku']})<br>"
            f"موجودی فعلی: {item['on_hand_qty']}<br>"
            f"آستانه سفارش: {item['reorder_threshold']}<br>"
            f"مقدار سفارش پیشنهادی: {item['order_qty']}<br><br>"
            f"با تشکر."
        )
        send_email(item["supplier_email"], subject, body)


# ---------------- FastAPI Endpoints ----------------
@app.get("/start")
def start_process():
    """شروع فرآیند: خواندن آیتم‌ها و ارسال ایمیل به کاربر"""
    read_items_from_sheet()
    if pending_items:
        notify_user()
        return {"message": "📧 ایمیل تایید به مدیر خرید ارسال شد."}
    else:
        return {"message": "✅ آیتمی نیاز به سفارش ندارد."}


@app.get("/approve")
def approve_order(decision: str):
    """کاربر تصمیم می‌گیرد"""
    if decision == "yes":
        notify_suppliers()
        return {"message": "✅ سفارش تایید شد و ایمیل به تامین‌کنندگان ارسال شد."}
    else:
        return {"message": "❌ سفارش رد شد. هیچ اقدامی انجام نشد."}


# ---------------- Run ----------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

# คู่มือภาษาไทย Auditslip สำหรับติดตั้ง ตั้งค่า และใช้งานจริง

เอกสารนี้เขียนสำหรับ operator/developer ที่ต้องเอาระบบ Auditslip ไปใช้งานจริง ตั้งแต่สร้างบอท ใส่บอทเข้ากลุ่ม เชื่อม API ตั้งค่า dashboard จนถึงตรวจระบบหลัง deploy

กฎสำคัญที่สุด: token/API key/password จริงต้องอยู่ใน `/etc/auditslip/auditslip.env` เท่านั้น ห้ามใส่ลง git, README, docs, commit, issue หรือ chat สาธารณะ

## 1. Auditslip คืออะไร

Auditslip คือระบบตรวจสลิปที่ทำงานบน VPS โดยรับรูปจาก Telegram แล้วใช้ OCR อ่านข้อมูลสลิป จากนั้นนำข้อมูลไปแสดงใน dashboard และ export/reconcile เพื่อใช้ตรวจบัญชี

ระบบหลักมี 4 ส่วน:

1. **Telegram bot** — รับรูปสลิปจาก group/chat
2. **OCR provider** — อ่านรูปสลิป เช่น Gemini/OpenAI
3. **SQLite database** — เก็บข้อมูลสลิป, คิว OCR, audit log, pending action
4. **Dashboard API/UI** — แสดงยอด, export, reconcile, ledger, approval

## 2. ต้องเตรียมอะไรก่อนติดตั้ง

- VPS/Ubuntu ที่รัน systemd ได้
- Git repo นี้: `https://github.com/aamsainz1-ui/auditslip.git`
- Telegram bot token จาก `@BotFather`
- API key ของ OCR อย่างน้อย 1 ตัว:
  - `GEMINI_API_KEY` หรือ
  - `OPENAI_API_KEY`
- รหัส dashboard owner:
  - `AUDITSLIP_DASHBOARD_OWNER_USER`
  - `AUDITSLIP_DASHBOARD_OWNER_PASSWORD`
- ถ้ามีหลายบริษัท/หลายบอท ต้องเตรียมชื่อบริษัทและ bot key เช่น `bot1`, `bot2`
- ถ้าแยกกลุ่มฝาก/ถอน ต้องหา `chat_id` ของแต่ละ group

## 3. ติดตั้งระบบบน VPS ใหม่

ติดตั้ง package:

```bash
sudo apt update
sudo apt install -y git python3 python3-requests python3-openpyxl sqlite3 curl
```

Clone repo:

```bash
sudo mkdir -p /root/projects
cd /root/projects
git clone https://github.com/aamsainz1-ui/auditslip.git
cd /root/projects/auditslip
```

สร้าง directory สำหรับ runtime:

```bash
sudo mkdir -p \
  /etc/auditslip \
  /root/projects/auditslip/data/slip-images \
  /root/projects/auditslip/exports \
  /root/projects/auditslip/imports/backend \
  /root/projects/auditslip/backups/db
```

สร้าง env จริงจากตัวอย่าง:

```bash
sudo cp /root/projects/auditslip/.env.example /etc/auditslip/auditslip.env
sudo chmod 600 /etc/auditslip/auditslip.env
sudo nano /etc/auditslip/auditslip.env
```

## 4. สร้าง Telegram bot

ทำใน Telegram:

1. เปิด `@BotFather`
2. ส่ง `/newbot`
3. ตั้งชื่อบอท เช่น `Auditslip Company 1`
4. ตั้ง username เช่น `auditslip_company1_bot`
5. คัดลอก token ไปใส่ใน `/etc/auditslip/auditslip.env`
6. ห้ามใส่ token ลง git

ตั้งค่า BotFather เพิ่ม:

```text
/setprivacy → เลือกบอท → Disable
/setjoingroups → เลือกบอท → Enable
/setcommands → ใส่ command list ของระบบ
```

เหตุผลที่ควรปิด privacy: ถ้าเปิด privacy mode บอทใน group อาจไม่เห็นรูปสลิปที่ไม่ได้ mention บอท

## 5. ใส่บอทเข้ากลุ่ม Telegram

1. เปิด group ที่จะรับสลิป
2. Add member แล้วเลือก bot
3. แนะนำให้ตั้ง bot เป็น admin ถ้า group permission เข้ม
4. ส่ง `/help` เช็คว่าบอทตอบได้
5. ส่งรูปสลิปทดสอบ 1 ใบ
6. เช็ค `/recent` หรือ dashboard ว่าข้อมูลเข้าแล้ว

ถ้าไม่อยากให้บอทตอบเยอะในกลุ่ม:

```env
AUDITSLIP_REPLY_ON_QUEUE=0
AUDITSLIP_REPLY_ON_RESULT=1
```

ถ้าต้องการ silent mode:

```env
AUDITSLIP_REPLY_ON_QUEUE=0
AUDITSLIP_REPLY_ON_RESULT=0
```

## 6. ตั้งค่า env สำหรับบอทเดียว

ใช้เมื่อมี Telegram bot ตัวเดียว:

```env
BOT_TOKEN=
BOT_DISPLAY_NAME=Auditslip
AUDITSLIP_TELEGRAM_BOTS=
```

## 7. ตั้งค่า env สำหรับหลายบอท/หลายบริษัท

ใช้เมื่อหนึ่ง service ต้องรันหลาย Telegram bots:

```env
BOT_TOKEN_1=
BOT_TOKEN_2=
BOT_TOKEN_3=
AUDITSLIP_TELEGRAM_BOTS="bot1:BOT_TOKEN_1:บริษัท 1,bot2:BOT_TOKEN_2:บริษัท 2,bot3:BOT_TOKEN_3:บริษัท 3"
```

ความหมาย:

- `bot1` = key ภายในระบบ ใช้ filter dashboard/export/API
- `BOT_TOKEN_1` = ชื่อ env var ที่เก็บ token จริง
- `บริษัท 1` = ชื่อที่ operator เห็นใน dashboard/export

## 8. ตั้งค่ากลุ่มฝาก/ถอน

ถ้าชื่อกลุ่มไม่ชัด ให้กำหนดเองด้วย `AUDITSLIP_FLOW_MAP`:

```env
AUDITSLIP_FLOW_MAP="bot1|-1001111111111=deposit,bot1|-1002222222222=withdraw"
```

ค่าที่ใช้ได้:

- `deposit` = กลุ่มฝาก/เติมมือ
- `withdraw` = กลุ่มถอน
- `other` = อื่นๆ

ถ้ายังไม่รู้ `chat_id` ให้ส่งสลิปทดสอบก่อน แล้วดูจาก DB:

```bash
cd /root/projects/auditslip
sqlite3 data/auditslip.db "
SELECT bot_key, chat_id, chat_title, COUNT(*) AS rows
FROM slips
GROUP BY bot_key, chat_id, chat_title
ORDER BY MAX(created_at_iso) DESC;
"
```

## 9. เชื่อม OCR API

ตั้ง provider order:

```env
OCR_PROVIDERS=gemini,openai
```

Gemini:

```env
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
GEMINI_THINKING_BUDGET=0
GEMINI_THINKING_FALLBACK_ENABLED=1
GEMINI_FALLBACK_THINKING_BUDGET=-1
```

OpenAI:

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

ตั้ง retry/circuit breaker:

```env
OCR_RETRY_ATTEMPTS=3
OCR_RETRY_BASE_DELAY=2
OCR_PROVIDER_BREAKER_ENABLED=1
OCR_PROVIDER_BREAKER_FAILURE_THRESHOLD=3
OCR_PROVIDER_BREAKER_COOLDOWN_SECONDS=300
OCR_PROVIDER_HEALTH_PATH=/root/projects/auditslip/data/ocr-provider-health.json
```

## 10. ตั้งค่า dashboard/admin

```env
AUDITSLIP_DASHBOARD_HOST=0.0.0.0
AUDITSLIP_DASHBOARD_PORT=8095
AUDITSLIP_DASHBOARD_TOKEN=
AUDITSLIP_DASHBOARD_OWNER_USER=owner
AUDITSLIP_DASHBOARD_OWNER_PASSWORD=
AUDITSLIP_SIMPLE_APPROVAL=1
AUDITSLIP_ALERT_ON_MUTATION=1
```

เปิด dashboard:

```text
http://SERVER_IP:8095/
```

แนะนำให้ login ด้วย owner/password แทนการส่ง token ใน URL เพราะปลอดภัยกว่า

## 11. เปิด service

```bash
cd /root/projects/auditslip
sudo cp systemd/auditslip-bot.service /etc/systemd/system/
sudo cp systemd/auditslip-dashboard.service /etc/systemd/system/
sudo cp systemd/auditslip-bot-watchdog.service /etc/systemd/system/
sudo cp systemd/auditslip-bot-watchdog.timer /etc/systemd/system/
sudo cp systemd/auditslip-backup.service /etc/systemd/system/
sudo cp systemd/auditslip-backup.timer /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now auditslip-bot.service auditslip-dashboard.service
sudo systemctl enable --now auditslip-bot-watchdog.timer auditslip-backup.timer
```

## 12. เช็คหลังติดตั้ง

```bash
cd /root/projects/auditslip
python3 -m py_compile auditslip_bot.py auditslip_dashboard.py auditslip_watchdog.py auditslip_bank_ledger.py
python3 tests/check_auditslip_product_contract.py
systemctl is-active auditslip-bot.service auditslip-dashboard.service
curl -fsS 'http://127.0.0.1:8095/api/health?quick=1'
```

ถ้าขึ้น `ok=true` และ service active แปลว่าระบบหลักพร้อมใช้งาน

## 13. วิธีใช้งาน Telegram commands

- `/help` — ดูคำสั่งทั้งหมด
- `/summary today` — ยอดวันนี้
- `/summary open` — ยอดรอบที่ยังไม่ปิด
- `/summary all` — ยอดทั้งหมด
- `/daily all` — ยอดแยกรายวัน
- `/names today` — ยอดแยกตามชื่อผู้โอน
- `/excel today` — export Excel วันนี้
- `/close note` — ปิดรอบปัจจุบันแบบเก็บประวัติ
- `/queue` หรือ `/failed` — ดูรายการ OCR มีปัญหา
- `/reprocess ID` — OCR รายการที่มีปัญหาใหม่
- `/recent` — รายการล่าสุด
- `/dupes` — รายการซ้ำ
- `/providers` — สถานะ Gemini/OpenAI
- `/usage today` — usage/cost ที่บันทึกไว้

## 14. วิธีใช้ dashboard

1. เปิด dashboard
2. เลือกบริษัท/bot
3. เลือก flow: `all`, `deposit`, `withdraw`, `other`
4. เลือก scope: วันนี้, วันที่, ช่วงวันที่, open, all
5. ตรวจยอดรวม, รายการล่าสุด, duplicate, queue, review
6. ใช้ export/reconcile/ledger หลังตรวจ scope ถูกแล้ว
7. งานเสี่ยงให้ใช้ pending approval ไม่กด execute สุ่ม

## 15. Export, reconcile, ledger

แนวทางปลอดภัย:

1. ใช้ preview/dry-run ก่อนเสมอ
2. ตรวจ company/bot, flow, date/scope ให้ตรง
3. ตรวจไฟล์ Excel/statement อยู่ใต้ `/root/projects/auditslip/imports/backend`
4. ถ้า preview ถูกต้อง ค่อย request import/run reconcile
5. งาน import จริงต้องผ่าน approval
6. หลังทำ mutation ให้ verify audit chain

API หลัก:

```text
GET  /api/export/preview
GET  /api/export
POST /api/reconcile/preview
POST /api/ledger/preview
POST /api/ledger/import?approval=request
POST /api/pending/approve
```

## 16. เพิ่มบอทหรือบริษัทใหม่

1. สร้าง bot ใหม่ใน BotFather
2. ปิด privacy หรือให้ bot เป็น admin ในกลุ่ม
3. backup env ก่อนแก้

```bash
sudo cp /etc/auditslip/auditslip.env /etc/auditslip/auditslip.env.bak.$(date +%Y%m%d-%H%M%S)
```

4. เพิ่ม token และ config:

```env
BOT_TOKEN_6=
AUDITSLIP_TELEGRAM_BOTS="bot1:BOT_TOKEN_1:บริษัท 1,bot2:BOT_TOKEN_2:บริษัท 2,bot6:BOT_TOKEN_6:บริษัท 6"
AUDITSLIP_FLOW_MAP="bot6|-1006661111111=deposit,bot6|-1006662222222=withdraw"
```

5. restart bot service:

```bash
sudo systemctl restart auditslip-bot.service
journalctl -u auditslip-bot.service -n 120 --no-pager
```

6. เช็ค dashboard:

```bash
curl -fsS 'http://127.0.0.1:8095/api/summary?bot_key=bot6&scope=today&detail=lite' | python3 -m json.tool
```

## 17. แก้ปัญหาที่พบบ่อย

### บอทไม่รับสลิป

- token ถูกตัวไหม: เรียก Telegram `getMe`
- bot อยู่ใน group แล้วไหม
- privacy mode ปิดหรือยัง
- bot เป็น admin หรือเห็นรูปได้ไหม
- service active ไหม
- มี webhook ค้างไหม

### OCR ไม่ทำงาน

- `GEMINI_API_KEY` หรือ `OPENAI_API_KEY` อยู่ใน env จริงไหม
- `/providers` แสดง provider พร้อมไหม
- circuit breaker เปิดอยู่หรือไม่
- queue มี failed/stale ไหม

### Dashboard 401/403

- login owner/password หรือส่ง `Authorization: Bearer ***` แล้วหรือยัง
- POST มี `X-Auditslip-Action: dashboard` แล้วหรือยัง
- token ถูก revoke แล้วหรือไม่

### ยอดฝาก/ถอนผิดฝั่ง

- อย่าเดาจากชื่อกลุ่มอย่างเดียว
- หา `chat_id` จริง
- ใส่ `AUDITSLIP_FLOW_MAP`
- restart service แล้วลอง `/api/summary?flow_type=deposit` และ `flow_type=withdraw`

## 18. Checklist ก่อนรายงานว่าเสร็จ

- เอกสารอยู่ใน git แล้ว
- ไม่มี secret จริงใน staged diff/commit
- `main == origin/main`
- `py_compile` ผ่าน
- tests ที่เกี่ยวข้องผ่าน
- bot/dashboard service active
- `/api/health?quick=1` ok
- audit chain `RESULT: OK` ถ้ามี mutation

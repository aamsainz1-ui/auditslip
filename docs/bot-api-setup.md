# Auditslip bot and API setup guide

คู่มือนี้คือขั้นตอนแบบครบสำหรับการสร้าง Telegram bot, ใส่บอทเข้ากลุ่ม, เชื่อม OCR/API providers, เชื่อม Dashboard API, และตรวจว่าทุกส่วนทำงานจริงหลัง deploy

กฎสำคัญ: ห้ามใส่ token/API key จริงใน git เด็ดขาด ให้เก็บค่าจริงเฉพาะใน `/etc/auditslip/auditslip.env` บนเครื่อง production เท่านั้น ส่วนใน repo ใช้ `.env.example` เป็นแม่แบบ placeholder

## 1. ภาพรวมส่วนที่ต้องเชื่อมกัน

Flow หลักของระบบ:

1. Operator ส่งรูปสลิปเข้า Telegram group หรือ direct chat
2. Auditslip bot service ใช้ Telegram Bot API แบบ polling (`getUpdates`) เพื่อรับ message/photo
3. Bot ดาวน์โหลดรูปผ่าน Telegram `getFile` + file download API
4. Bot ส่งรูปให้ OCR provider ตาม `OCR_PROVIDERS` เช่น Gemini ก่อน แล้ว fallback OpenAI
5. ผล OCR ถูก normalize แล้วบันทึกลง SQLite (`data/auditslip.db`) พร้อม duplicate/evidence metadata
6. Dashboard service เปิด UI + JSON API ที่พอร์ต `AUDITSLIP_DASHBOARD_PORT` เช่น `8095`
7. Operator ใช้ dashboard เพื่อดูยอด, export Excel/ZIP, reconcile, preview/import bank statement ledger, ตั้งค่า account/company, approve pending actions
8. Watchdog/backup timers ตรวจ health/queue และ backup DB ตามรอบ

ส่วน external API ที่เกี่ยวข้อง:

- Telegram Bot API: สร้าง/รับ message/ดาวน์โหลดรูป/ส่งข้อความ/ส่ง Excel
- Google Gemini API: OCR provider หลักหรือ fallback
- OpenAI API: OCR provider หลักหรือ fallback และ bank recheck บาง workflow
- Auditslip Dashboard API: local/public JSON endpoints สำหรับ summary/export/reconcile/ledger/admin
- Optional TrueWallet dashboard API: อ่านข้อมูลจาก dashboard ภายนอกถ้าตั้ง `AUDITSLIP_TWALLET_DASHBOARD_URL`
- Optional watchdog Telegram alert: ส่ง alert ไป owner/admin chat

## 2. สร้าง Telegram bot ด้วย BotFather

ทำใน Telegram:

1. เปิด chat กับ `@BotFather`
2. ส่งคำสั่ง `/newbot`
3. ตั้งชื่อบอท เช่น `Auditslip Company 1`
4. ตั้ง username ที่ลงท้ายด้วย `bot` เช่น `auditslip_company1_bot`
5. BotFather จะให้ token รูปแบบประมาณ `123456789:AA...`
6. เก็บ token ไว้ใน password manager หรือใส่ตรง `/etc/auditslip/auditslip.env` เท่านั้น ห้าม commit ลง git

ตั้งค่า BotFather ที่ควรทำ:

1. `/setprivacy`
   - เลือกบอท
   - เลือก `Disable`
   - เหตุผล: สลิปใน group เป็นรูป ไม่ใช่คำสั่งที่ mention bot เสมอ ถ้า privacy เปิด บอทอาจไม่เห็นรูปทั้งหมด
2. `/setjoingroups`
   - เลือกบอท
   - เลือก `Enable`
   - เหตุผล: ให้เพิ่มบอทเข้ากลุ่มได้
3. `/setcommands`
   - เลือกบอท
   - ใส่ชุดคำสั่งนี้

```text
start - เริ่มใช้งาน Auditslip
help - ดูคำสั่งทั้งหมด
summary - สรุปยอด
today - สรุปยอดวันนี้
daily - สรุปยอดแยกตามวัน
names - สรุปยอดแยกตามชื่อผู้โอน
userall - alias สรุปยอดแยกตามชื่อผู้โอน
excel - ส่งออก Excel
close - เคลียร์ยอด/ปิดรอบแบบเก็บประวัติ
clear - ล้างข้อมูลถาวร ต้อง confirm
queue - ดูคิว fail/อ่านไม่ชัด
failed - ดูรายการ fail/unclear
reprocess - OCR รายการใหม่
recent - ดูรายการล่าสุด
stats - ดูสถิติบอท
dupes - ดูรายการซ้ำ
providers - ดูสถานะ OCR providers
usage - สรุปการใช้งาน OCR API
```

หมายเหตุ: ตอน service เริ่มทำงาน โค้ดจะเรียก `setMyCommands` อีกครั้งจาก `COMMANDS` ใน `auditslip_bot.py` ดังนั้นถ้ารายการคำสั่งใน code เปลี่ยน ให้ restart bot แล้ว Telegram command menu จะอัปเดตตาม code

## 3. ใส่บอทเข้ากลุ่ม Telegram

ทำต่อหนึ่งกลุ่มที่ต้องรับสลิป:

1. เปิด Telegram group
2. Add member → เลือก bot username ที่สร้างไว้
3. แนะนำให้ตั้ง bot เป็น admin อย่างน้อยให้มองเห็น message/photo ได้ โดยเฉพาะ group ที่มี privacy/permission เข้ม
4. ส่ง `/help` หรือ `/start` ในกลุ่มเพื่อเช็คว่าบอทตอบได้
5. ส่งรูปสลิปทดสอบ 1 ใบ
6. เช็ค dashboard `/api/summary` หรือคำสั่ง `/recent`

สำหรับ production ที่ไม่อยากให้บอท spam กลุ่ม:

```env
AUDITSLIP_REPLY_ON_QUEUE=0
AUDITSLIP_REPLY_ON_RESULT=1
```

ถ้าต้องเงียบสนิทในกลุ่ม:

```env
AUDITSLIP_REPLY_ON_QUEUE=0
AUDITSLIP_REPLY_ON_RESULT=0
```

## 4. ตั้งค่า token ใน `/etc/auditslip/auditslip.env`

### 4.1 Single-bot mode

ใช้เมื่อมีบอทเดียวรับทุก group/chat:

```env
# ใส่ token จริงเฉพาะใน /etc/auditslip/auditslip.env ห้ามใส่ใน git
BOT_TOKEN=
BOT_DISPLAY_NAME=Auditslip
AUDITSLIP_TELEGRAM_BOTS=
```

ระบบรองรับชื่อ env fallback `TELEGRAM_BOT_TOKEN` ด้วย แต่แนะนำใช้ `BOT_TOKEN` ให้ตรงกับ service/template

### 4.2 Multi-bot / multi-company mode

ใช้เมื่อหนึ่ง service รันหลาย Telegram bots แยกบริษัท:

```env
# ใส่ token จริงเฉพาะใน /etc/auditslip/auditslip.env ห้ามใส่ใน git
BOT_TOKEN_1=
BOT_TOKEN_2=
BOT_TOKEN_3=

AUDITSLIP_TELEGRAM_BOTS="bot1:BOT_TOKEN_1:บริษัท 1,bot2:BOT_TOKEN_2:บริษัท 2,bot3:BOT_TOKEN_3:บริษัท 3"
```

รูปแบบ `AUDITSLIP_TELEGRAM_BOTS`:

```text
bot_key:TOKEN_ENV_NAME:company_name
```

ตัวอย่าง:

- `bot1` = key ภายในระบบ ใช้ใน DB/dashboard/API
- `BOT_TOKEN_1` = ชื่อ env var ที่เก็บ token จริง
- `บริษัท 1` = ชื่อแสดงใน dashboard/export

ห้ามใส่ token จริงลงตรง `AUDITSLIP_TELEGRAM_BOTS` ในไฟล์ที่จะ commit ให้ใส่ชื่อ env var เท่านั้น

### 4.3 JSON format สำหรับ multi-bot ถ้าต้องการชัดเจนกว่า CSV

ใช้ได้ใน env จริง แต่ต้อง quote ให้ shell อ่านได้ถูกต้อง:

```env
AUDITSLIP_TELEGRAM_BOTS='[
  {"bot_key":"bot1","token_env":"BOT_TOKEN_1","company_name":"บริษัท 1"},
  {"bot_key":"bot2","token_env":"BOT_TOKEN_2","company_name":"บริษัท 2"}
]'
```

ถ้าใช้ systemd `EnvironmentFile=` ธรรมดา แนะนำ CSV เพราะแก้/อ่านง่ายกว่า

## 5. ผูกกลุ่มฝาก/ถอนกับ bot/company

ระบบมี `flow_type` หลัก:

- `deposit` = กลุ่มฝาก/เติมมือ
- `withdraw` = กลุ่มถอน
- `other` = กลุ่มอื่น/ยังไม่จัดประเภท
- `all` = ใช้เป็น filter รวมใน dashboard/API ไม่ใช่ค่าที่ map group

ถ้าชื่อ group ชัดเจน ระบบอาจเดาจากชื่อกลุ่มได้ แต่ production ควรใช้ explicit mapping เพื่อกันยอดเพี้ยน

ตัวอย่าง map group ID:

```env
AUDITSLIP_FLOW_MAP="bot1|-1001111111111=deposit,bot1|-1002222222222=withdraw,bot2|-1003333333333=deposit,bot2|-1004444444444=withdraw"
```

รูปแบบ:

```text
bot_key|chat_id=flow_type
```

ถ้าต้อง map เฉพาะ chat id ไม่สน bot:

```env
AUDITSLIP_FLOW_MAP="*|-1001111111111=deposit,*|-1002222222222=withdraw"
```

ระบบยังรองรับ alias `AUDITSLIP_GROUP_FLOW_MAP` แต่แนะนำใช้ `AUDITSLIP_FLOW_MAP`

## 6. วิธีหา chat_id ของ Telegram group

วิธีปลอดภัยที่สุดหลังบอทรับสลิปแล้ว:

```bash
cd /root/projects/auditslip
sqlite3 data/auditslip.db "
SELECT bot_key, chat_id, chat_title, COUNT(*) AS rows
FROM slips
GROUP BY bot_key, chat_id, chat_title
ORDER BY MAX(created_at_iso) DESC;
"
```

ถ้ายังไม่มีสลิปใน DB และจำเป็นต้องใช้ Telegram API เพื่อดู update:

1. หยุด bot service ชั่วคราว เพื่อไม่ให้ชน long polling

```bash
sudo systemctl stop auditslip-bot.service
```

2. ส่งข้อความทดสอบใน group เช่น `/help` หรือส่งรูปทดสอบ
3. อ่าน update โดยไม่ใส่ offset ใหม่ที่จะ skip ข้อความโดยไม่ตั้งใจ

```bash
set -a
. /etc/auditslip/auditslip.env
set +a
curl -sG "https://api.telegram.org/bot${BOT_TOKEN_1}/getUpdates" \
  --data-urlencode 'timeout=0' \
  --data-urlencode 'allowed_updates=["message","edited_message"]' \
  | python3 -m json.tool
```

4. ดู `message.chat.id` ซึ่งมักเป็นเลขติดลบ เช่น `-100...`
5. เริ่ม service กลับ

```bash
sudo systemctl start auditslip-bot.service
```

ข้อควรระวัง:

- Bot นี้ใช้ polling (`getUpdates`) ไม่ใช่ webhook
- ตอน startup bot จะเรียก `deleteWebhook(drop_pending_updates=false)` เพื่อเคลียร์ webhook เก่า
- อย่า probe `getUpdates` ขณะ service polling อยู่ เพราะอาจเจอ Telegram 409 conflict
- อย่าใช้ `offset` แบบเดาสุ่ม เพราะอาจทำให้ update ที่ยังไม่ได้ประมวลผลถูกข้าม

## 7. เชื่อม OCR provider APIs

### 7.1 Gemini

ค่าที่ใช้:

```env
OCR_PROVIDERS=gemini,openai
# ใส่ key จริงใน /etc/auditslip/auditslip.env เท่านั้น
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
GEMINI_FALLBACK_MODELS=gemini-2.5-flash-lite,gemini-2.0-flash-lite
GEMINI_THINKING_BUDGET=0
GEMINI_THINKING_FALLBACK_ENABLED=1
GEMINI_FALLBACK_THINKING_BUDGET=-1
```

ระบบรองรับ `GOOGLE_API_KEY` เป็น fallback ของ `GEMINI_API_KEY` แต่แนะนำใช้ `GEMINI_API_KEY` เพื่ออ่านง่าย

Endpoint ที่ code เรียก:

```text
POST https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key=GEMINI_API_KEY
```

แนว production:

- ใช้ `GEMINI_THINKING_BUDGET=0` เป็นค่าแรกเพื่อลด cost กับสลิปธรรมดา
- เปิด fallback thinking (`-1`) เฉพาะเคส parse ไม่ชัด/ขาดยอด/ขาดวันที่/confidence ต่ำ
- อย่า log key หรือ raw provider response ที่มีข้อมูลอ่อนไหว

### 7.2 OpenAI

ค่าที่ใช้:

```env
# ใส่ key จริงใน /etc/auditslip/auditslip.env เท่านั้น
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

Endpoint ที่ code เรียก:

```text
POST https://api.openai.com/v1/chat/completions
Authorization: Bearer OPENAI_API_KEY
```

OpenAI ใช้เป็น provider fallback หรือใช้กับ workflow recheck ธนาคารจาก dashboard เช่น `/api/bank-review/openai`

### 7.3 Provider order, retry, circuit breaker

ค่าที่ควรมี:

```env
OCR_PROVIDERS=gemini,openai
OCR_RETRY_ATTEMPTS=3
OCR_RETRY_BASE_DELAY=2
OCR_PROVIDER_BREAKER_ENABLED=1
OCR_PROVIDER_BREAKER_FAILURE_THRESHOLD=3
OCR_PROVIDER_BREAKER_COOLDOWN_SECONDS=300
OCR_PROVIDER_HEALTH_PATH=/root/projects/auditslip/data/ocr-provider-health.json
```

ความหมาย:

- `OCR_PROVIDERS=gemini,openai`: ลอง Gemini ก่อน ถ้าล้มเหลวค่อย fallback OpenAI
- circuit breaker จะพัก provider ที่ fail ต่อเนื่อง เพื่อไม่เผา attempt/cost ซ้ำ
- health state เก็บแบบ secret-free ที่ `OCR_PROVIDER_HEALTH_PATH`

## 8. ตั้งค่า Dashboard API และ admin access

ค่าพื้นฐาน:

```env
AUDITSLIP_DASHBOARD_HOST=0.0.0.0
AUDITSLIP_DASHBOARD_PORT=8095
# ใส่ค่าสุ่มยาวจริงใน /etc/auditslip/auditslip.env เท่านั้น
AUDITSLIP_DASHBOARD_TOKEN=
AUDITSLIP_DASHBOARD_OWNER_USER=owner
AUDITSLIP_DASHBOARD_OWNER_PASSWORD=
AUDITSLIP_SIMPLE_APPROVAL=1
AUDITSLIP_ALERT_ON_MUTATION=1
```

บทบาทใน dashboard token DB:

- `admin`: จัดการทุกอย่าง, สร้าง/revoke token, request/execute mutation
- `operator`: reprocess/unmark/recheck บางงาน แต่ลบ/close/reconcile/import บางอย่างไม่ได้
- `auditor`: ดู audit/pending และ approve/reject บาง action
- `viewer`: ดูอย่างเดียว

วิธี login แบบ UI:

1. เปิด dashboard เช่น `http://SERVER_IP:8095/`
2. ใส่ `AUDITSLIP_DASHBOARD_OWNER_USER`
3. ใส่ `AUDITSLIP_DASHBOARD_OWNER_PASSWORD`
4. ระบบจะ set HttpOnly cookie สำหรับ admin session

วิธีเรียก API ด้วย token:

```bash
set -a
. /etc/auditslip/auditslip.env
set +a
curl -s "http://127.0.0.1:8095/api/summary?bot_key=bot1&flow_type=all&scope=today&detail=lite" \
  -H "Authorization: Bearer ${AUDITSLIP_DASHBOARD_TOKEN}" \
  | python3 -m json.tool
```

สำหรับ POST mutation ต้องมี header กัน CSRF/action:

```text
X-Auditslip-Action: dashboard
Content-Type: application/json
Authorization: Bearer <dashboard-token>
```

ตัวอย่างสร้าง token สำหรับ operator:

```bash
curl -s -X POST "http://127.0.0.1:8095/api/tokens/create" \
  -H "Authorization: Bearer ${AUDITSLIP_DASHBOARD_TOKEN}" \
  -H "X-Auditslip-Action: dashboard" \
  -H "Content-Type: application/json" \
  -d '{"role":"operator","label":"operator phone"}' \
  | python3 -m json.tool
```

คำเตือน: raw token จาก `/api/tokens/create` แสดงครั้งเดียว ให้เก็บนอก git ถ้าหายให้ revoke/create ใหม่

## 9. Dashboard API endpoint map

### 9.1 Read/dashboard endpoints

- `GET /` หรือ `/index.html`
  - เปิด dashboard HTML
  - รองรับ legacy `?token=...` เฉพาะหน้านี้เพื่อ set cookie แล้ว scrub token ออกจาก URL
- `GET /api/health?quick=1`
  - quick health สำหรับ watchdog/readiness
  - public/read-only ตาม code ปัจจุบัน
- `GET /api/health`
  - operational health เต็มกว่า quick mode
- `GET /api/summary`
  - summary/dashboard snapshot
  - query สำคัญ: `bot_key`, `chat_id`, `flow_type`, `scope`, `detail=lite|full`, `slip_filter`, `slip_search`, `account_search_mode`
- `GET /api/ledger`
  - อ่าน account ledger rows
  - query สำคัญ: `bot_key`, `chat_id`, `account_key`, `date_from`, `date_to`, `flow_type`, `limit`
- `GET /api/slip-image?id=SLIP_ID`
  - โหลดรูปสลิปตาม id
  - ถ้าเปิด public dashboard ต้องถือว่ารูปสลิปเป็นข้อมูลอ่อนไหว ควรอยู่หลัง network/auth ที่เหมาะสม
- `GET /api/export/preview`
  - preview export แบบไม่ต้องเขียน artifact หลัก
  - query สำคัญ: `bot_key`, `chat_id`, `flow_type`, `scope`, `start_date`, `end_date`, `cross_account_search`
- `GET /api/export`
  - สร้าง/ดาวน์โหลด Excel หรือ ZIP
  - ใส่ `dry_run=1` เพื่อ preview ผ่าน endpoint เดียวกันได้
- `GET /api/pending`
  - public จะได้ข้อมูล redacted
  - admin/operator/auditor จะเห็น pending action จริง
- `GET /api/tokens`
  - admin เท่านั้น
- `GET /api/audit-chain/verify`
  - admin/auditor เท่านั้น
- `GET /api/audit-chain/tail?limit=50`
  - admin/auditor เท่านั้น

ตัวอย่าง summary:

```bash
curl -s "http://127.0.0.1:8095/api/summary?bot_key=bot1&flow_type=withdraw&scope=today&detail=lite" \
  | python3 -m json.tool
```

ตัวอย่าง export preview:

```bash
curl -s "http://127.0.0.1:8095/api/export/preview?bot_key=bot1&flow_type=withdraw&scope=today" \
  | python3 -m json.tool
```

### 9.2 Admin/mutation POST endpoints

ทุก endpoint ในกลุ่มนี้ต้องมี authorized role และ header `X-Auditslip-Action: dashboard`

- `POST /api/login`
  - payload: `username`, `password`
  - ใช้ owner login เพื่อ set session cookie
- `POST /api/logout`
  - clear owner session cookie
- `POST /api/tokens/create`
  - admin
  - payload: `role`, `label`
- `POST /api/tokens/revoke`
  - admin
  - payload: `token_hash_prefix`
- `POST /api/slip/reprocess`
  - admin/operator
  - payload: `id` หรือ `slip_id`, `bot_key`
- `POST /api/slip/delete?approval=request`
  - admin
  - สร้าง pending delete; ใช้ approve/execute ก่อนลบจริง
- `POST /api/duplicate/unmark`
  - admin/operator
  - payload: `id` หรือ `slip_id`, `bot_key`
- `POST /api/slip/mark-reviewed`
  - admin/operator/auditor
  - payload: `id` หรือ `slip_id`, `note`
- `POST /api/bank-review/openai`
  - admin/operator
  - payload: `id`, `apply=true|false`
- `POST /api/bank-review/openai-all`
  - admin
  - payload/query: `bot_key`, `chat_id`, `scope`, `flow_type`, `slip_search`, `apply`
- `POST /api/account-limit?approval=request|execute`
  - admin
  - ตั้ง daily/account limit ผ่าน pending action
- `POST /api/company-account?approval=request|execute`
  - admin
  - ตั้งบัญชีบริษัท/บัญชีปลายทาง/วงเงิน
- `POST /api/close?approval=request|execute`
  - admin
  - ปิดรอบ/เคลียร์ยอดแบบเก็บประวัติ
- `POST /api/reconcile/preview` หรือ `/api/reconcile?dry_run=1`
  - admin
  - preview เทียบ backend Excel กับ slip โดยไม่สร้าง pending/mutation หลัก
- `POST /api/reconcile?approval=request|execute`
  - admin
  - run reconcile ผ่าน pending action
- `POST /api/reconcile/statement`
  - admin
  - เทียบ backend Excel + bank statement + slips แบบ preview/compare
- `POST /api/ledger/preview`
  - admin
  - preview bank statement ledger import แบบ dry-run ไม่มี insert
- `POST /api/ledger/import?approval=request|execute`
  - admin
  - import statement ledger ผ่าน pending action
- `POST /api/pending/approve`
  - admin/auditor
  - payload: `pending_id`
- `POST /api/pending/approve?approval=execute`
  - admin/auditor
  - approve แล้ว execute pending action ใน call เดียว ถ้า policy อนุญาต
- `POST /api/pending/reject`
  - admin/auditor
  - payload: `pending_id`, `reason`
- `POST /api/pending/cancel`
  - requester/current actor ตาม policy
  - payload: `pending_id`

ตัวอย่าง ledger preview:

```bash
curl -s -X POST "http://127.0.0.1:8095/api/ledger/preview" \
  -H "Authorization: Bearer ${AUDITSLIP_DASHBOARD_TOKEN}" \
  -H "X-Auditslip-Action: dashboard" \
  -H "Content-Type: application/json" \
  -d '{
    "bot_key":"bot1",
    "flow_type":"withdraw",
    "scope":"today",
    "bank":"SCB",
    "account_no":"1234567890",
    "account_name":"บริษัท 1",
    "statement_path":"/root/projects/auditslip/imports/backend/example-statement.xlsx"
  }' \
  | python3 -m json.tool
```

ตัวอย่าง request import หลัง preview ถูกต้อง:

```bash
curl -s -X POST "http://127.0.0.1:8095/api/ledger/import?approval=request" \
  -H "Authorization: Bearer ${AUDITSLIP_DASHBOARD_TOKEN}" \
  -H "X-Auditslip-Action: dashboard" \
  -H "Content-Type: application/json" \
  -d '{
    "bot_key":"bot1",
    "flow_type":"withdraw",
    "scope":"today",
    "bank":"SCB",
    "account_no":"1234567890",
    "account_name":"บริษัท 1",
    "statement_path":"/root/projects/auditslip/imports/backend/example-statement.xlsx"
  }' \
  | python3 -m json.tool
```

## 10. Backend Excel, statement ledger, and import paths

ตั้ง path ใน env:

```env
AUDITSLIP_BACKEND_IMPORT_DIR=/root/projects/auditslip/imports/backend
AUDITSLIP_EXPORT_DIR=/root/projects/auditslip/exports
```

แนวปฏิบัติ:

1. วางไฟล์ backend Excel หรือ statement ไว้ใต้ `AUDITSLIP_BACKEND_IMPORT_DIR`
2. ใช้ preview/dry-run ก่อนเสมอ
3. ตรวจ company/bot, flow, date/scope, bank, account number ให้ตรงก่อน import จริง
4. Import จริงต้องผ่าน pending approval (`approval=request` แล้ว approve/execute)
5. Import ต้อง idempotent: รันซ้ำแล้วไม่ควร insert ซ้ำ
6. อย่า smoke production ด้วย real import ถ้าไม่จำเป็น ให้ใช้ fixture เล็กแล้วลบทิ้ง

## 11. Optional TrueWallet dashboard API

ถ้ามี dashboard TrueWallet ภายนอก ให้ตั้ง:

```env
AUDITSLIP_TWALLET_DASHBOARD_URL=https://example.internal-or-private-url
AUDITSLIP_TWALLET_TIMEOUT=2.5
AUDITSLIP_TWALLET_CACHE_TTL=20
```

Auditslip จะอ่าน endpoint ต่อไปนี้จาก URL นั้นถ้าตั้งค่าไว้:

```text
/api/tm/balance
/api/stats/daily?days=1
/api/tm/my-last-receive
```

ถ้าไม่ได้ใช้ ให้ปล่อย `AUDITSLIP_TWALLET_DASHBOARD_URL=` ว่างไว้

## 12. Watchdog, owner alert, and backup

ค่าที่เกี่ยวข้อง:

```env
AUDITSLIP_BOT_SERVICE=auditslip-bot.service
AUDITSLIP_DASHBOARD_SERVICE=auditslip-dashboard.service
AUDITSLIP_WATCHDOG_TIMER=auditslip-bot-watchdog.timer
AUDITSLIP_WATCHDOG_BOT_TOKEN=
AUDITSLIP_WATCHDOG_ALERT_CHAT_ID=
AUDITSLIP_ADMIN_IDS=123456789,987654321
AUDITSLIP_WATCHDOG_HEALTH_URL=http://127.0.0.1:8095/api/health?quick=1
AUDITSLIP_WATCHDOG_STALE_MINUTES=15
AUDITSLIP_WATCHDOG_FAILED_THRESHOLD=1
AUDITSLIP_WATCHDOG_ALERT_THROTTLE_SEC=1800
AUDITSLIP_BACKUP_DIR=/root/projects/auditslip/backups/db
AUDITSLIP_BACKUP_RETENTION_DAYS=14
```

หมายเหตุ:

- ถ้า `AUDITSLIP_WATCHDOG_BOT_TOKEN` ว่าง watchdog จะ fallback ไปใช้ `BOT_TOKEN` หรือ `TELEGRAM_BOT_TOKEN`
- `AUDITSLIP_ADMIN_IDS` คือ Telegram user id ที่ใช้จำกัดคำสั่ง admin เช่น `/close`
- `AUDITSLIP_WATCHDOG_ALERT_CHAT_ID` คือ chat id ที่รับ alert
- อย่าส่ง token/key/raw provider error ใน alert

## 13. Restart และ verify หลังแก้ config

หลังแก้ `/etc/auditslip/auditslip.env`:

```bash
sudo systemctl daemon-reload
sudo systemctl restart auditslip-bot.service auditslip-dashboard.service
sudo systemctl status auditslip-bot.service --no-pager -l
sudo systemctl status auditslip-dashboard.service --no-pager -l
curl -fsS 'http://127.0.0.1:8095/api/health?quick=1'
```

ตรวจว่า config multi-bot parse ได้:

```bash
cd /root/projects/auditslip
set -a
. /etc/auditslip/auditslip.env
set +a
python3 - <<'PY'
import auditslip_bot
for cfg in auditslip_bot.telegram_bot_configs():
    print({"bot_key": cfg["bot_key"], "token_env": cfg.get("token_env"), "company_name": cfg["company_name"], "has_token": bool(cfg.get("token"))})
PY
```

ตรวจ Telegram token ทีละตัวโดยไม่ print token:

```bash
set -a
. /etc/auditslip/auditslip.env
set +a
for var in BOT_TOKEN BOT_TOKEN_1 BOT_TOKEN_2 BOT_TOKEN_3 BOT_TOKEN_4 BOT_TOKEN_5; do
  token="${!var:-}"
  [ -z "$token" ] && continue
  echo "checking $var"
  curl -fsS "https://api.telegram.org/bot${token}/getMe" \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); r=d.get("result",{}); print({"ok":d.get("ok"),"id":r.get("id"),"username":r.get("username")})'
done
```

ตรวจ summary จาก dashboard:

```bash
curl -fsS 'http://127.0.0.1:8095/api/summary?bot_key=bot1&flow_type=all&scope=today&detail=lite' \
  | python3 -m json.tool | head -80
```

ตรวจ queue ใน DB:

```bash
sqlite3 /root/projects/auditslip/data/auditslip.db "SELECT status, COUNT(*) FROM ocr_jobs GROUP BY status;"
```

## 14. ขั้นตอนเพิ่มบอทใหม่เข้า production ที่รันอยู่แล้ว

1. สร้าง bot ใหม่ใน BotFather ตาม section 2
2. ปิด privacy หรือทำให้ bot อ่านรูปใน group ได้
3. Backup env ก่อนแก้

```bash
sudo cp /etc/auditslip/auditslip.env /etc/auditslip/auditslip.env.bak.$(date +%Y%m%d-%H%M%S)
```

4. เพิ่ม token ใหม่ใน `/etc/auditslip/auditslip.env`

```env
BOT_TOKEN_6=
AUDITSLIP_TELEGRAM_BOTS="bot1:BOT_TOKEN_1:บริษัท 1,bot2:BOT_TOKEN_2:บริษัท 2,bot6:BOT_TOKEN_6:บริษัท 6"
```

5. Add bot ใหม่เข้ากลุ่ม Telegram ที่ต้องใช้งาน
6. ส่ง test message/slip เพื่อหา `chat_id`
7. เพิ่ม `AUDITSLIP_FLOW_MAP` ถ้าต้องแยกฝาก/ถอนชัดเจน

```env
AUDITSLIP_FLOW_MAP="bot6|-1006661111111=deposit,bot6|-1006662222222=withdraw"
```

8. Restart bot service

```bash
sudo systemctl restart auditslip-bot.service
journalctl -u auditslip-bot.service -n 120 --no-pager
```

9. เช็ค dashboard ว่า company ใหม่ขึ้น selector

```bash
curl -fsS 'http://127.0.0.1:8095/api/summary?bot_key=bot6&scope=today&detail=lite' \
  | python3 -m json.tool | head -80
```

10. ส่งสลิปทดสอบใน group แล้วตรวจ `/recent`, dashboard recent rows, และ queue status

## 15. Troubleshooting เฉพาะ bot/API connection

### Bot ไม่รับรูปใน group

เช็คตามลำดับ:

1. Token ถูกบอทตัวจริงไหม

```bash
curl -fsS "https://api.telegram.org/bot${BOT_TOKEN_1}/getMe" | python3 -m json.tool
```

2. Bot อยู่ใน group แล้วหรือยัง
3. Privacy mode ปิดหรือ bot เป็น admin แล้วหรือยัง
4. Service active ไหม

```bash
systemctl is-active auditslip-bot.service
journalctl -u auditslip-bot.service -n 120 --no-pager
```

5. มี webhook เก่าค้างไหม

```bash
curl -fsS "https://api.telegram.org/bot${BOT_TOKEN_1}/getWebhookInfo" | python3 -m json.tool
```

ถ้ามี webhook ค้าง ตัว bot จะล้างตอน startup แต่ถ้าต้องล้างเอง:

```bash
curl -fsS -X POST "https://api.telegram.org/bot${BOT_TOKEN_1}/deleteWebhook" \
  -d 'drop_pending_updates=false' \
  | python3 -m json.tool
```

### OCR provider ใช้ไม่ได้

1. เช็ค key อยู่ใน env จริง ไม่ใช่ `.env.example`
2. เช็ค `/providers` ใน Telegram หรือ dashboard health
3. เช็ค circuit breaker state

```bash
python3 - <<'PY'
import json, os
p=os.environ.get('OCR_PROVIDER_HEALTH_PATH','/root/projects/auditslip/data/ocr-provider-health.json')
print(p)
try:
    print(json.dumps(json.load(open(p)), ensure_ascii=False, indent=2)[:4000])
except FileNotFoundError:
    print('provider health file not found yet')
PY
```

### Dashboard API 401/403

- GET read-only บาง endpoint อาจเปิด public ตาม code ปัจจุบัน แต่ mutation ต้อง auth
- POST ต้องมี `Authorization: Bearer ***` หรือ owner session cookie
- POST ต้องมี `X-Auditslip-Action: dashboard`
- ถ้า token ถูก revoke แล้ว legacy env token จะไม่ bypass DB token table

### Group ฝาก/ถอนยอดผิดฝั่ง

- อย่าเดาจากชื่อ group อย่างเดียว
- หา `chat_id` จริง แล้วใส่ `AUDITSLIP_FLOW_MAP`
- Restart dashboard/bot แล้วตรวจ `/api/summary?flow_type=deposit` และ `flow_type=withdraw`

## 16. Pre-push checklist สำหรับเอกสาร/config

ก่อน commit/push เอกสารหรือ config template:

```bash
cd /root/projects/auditslip
git status --short
git diff --stat
# scan staged diff after git add
git diff --cached | grep '^+' | grep -Ei '(api_key|secret|password|token|private_key)\s*[:=]\s*[^[:space:]]{12,}' || true
```

ต้องไม่มี token/key จริงในผล scan ถ้าเจอ ให้ unstage และแก้เป็น placeholder ก่อน push

# คู่มือ Audit ยอดพนักงาน

เอกสารนี้ตอบว่า “ระบบตอนนี้มีอะไรแล้ว” และ “ยังควรเพิ่มอะไร” ถ้าจะใช้ Auditslip เป็นเครื่องมือ audit ยอดพนักงาน/คนทำรายการแบบจริงจัง

## 1. สถานะปัจจุบันที่มีแล้ว

ระบบมีฐานข้อมูลหลักที่ช่วย audit ได้อยู่แล้ว:

- `slips` เก็บหลักฐานสลิป: บริษัท/bot, group, ผู้ส่งรูป, ชื่อผู้โอน, ธนาคาร, เลขบัญชี, ยอด, วันที่/เวลา, รูป, reference, duplicate status
- `ocr_jobs` เก็บคิว OCR และ error/retry
- `company_accounts` เก็บบัญชีบริษัท/บัญชีรับเงิน/วงเงินรายวัน
- `account_limits` เก็บวงเงินรายวันรายบัญชี — เป็นการตั้งค่าตรง ไม่ต้อง approval
- `bank_ledger_*` รองรับ preview/import รายการเดินบัญชีเพื่อเทียบกับสลิป
- `dashboard_mutation_log` + audit chain ใช้ตรวจว่ามีใครทำ mutation สำคัญเมื่อไร
- Dashboard มีมุมมองแยกบริษัท, ฝาก/ถอน, รายวัน, รายบัญชี, สลิปซ้ำ, export, reconcile, ledger preview/import

มี endpoint audit เฉพาะทางแล้ว:

```text
GET /api/audit/daily-variance?bot_key=__all__&scope=today&flow_type=all&threshold=100
GET /api/audit/reconcile?bot_key=bot1&account_key=<account>&scope=today&flow_type=withdraw
GET /api/audit/cross-dup?bot_key=__all__&scope=today
```

ความหมาย:

- `daily-variance` — รวมยอดรายวันตามชื่อที่ระบบมองเป็นพนักงาน/ผู้เกี่ยวข้อง แล้วเทียบ variance ถ้ามี ledger
- `reconcile` — เทียบสลิปกับ bank ledger รายบัญชี
- `cross-dup` — หา transaction fingerprint ที่โผล่ข้าม bot/chat หลายแหล่ง

## 2. ข้อจำกัดสำคัญตอนนี้

คำว่า “พนักงาน” ในข้อมูลปัจจุบันยังไม่ใช่ master data ที่ชัดเจน ระบบอาศัย field จากสลิป/Telegram เช่น:

- `sender_name`, `username`, `user_id` = คนส่งรูปใน Telegram
- `transferor_name` = ชื่อผู้โอนบนสลิป ซึ่งอาจเป็นลูกค้า/บัญชีต้นทาง ไม่ใช่พนักงาน
- `company_name`, `bot_key`, `chat_id` = บริษัท/กลุ่มที่สลิปเข้ามา

ดังนั้นถ้าจะ audit พนักงานจริง ต้องแยกให้ชัดว่า “พนักงาน” หมายถึง:

1. คนส่งรูปใน Telegram
2. คนทำรายการถอน/ฝากในหลังบ้าน
3. เจ้าของบัญชีต้นทาง/ปลายทาง
4. คนปิดรอบ/คน import/คนแก้ข้อมูล

ถ้าไม่แยก ระบบจะรวมยอดได้ แต่ยังฟันธงความรับผิดชอบรายคนไม่ได้ 100%

## 3. สิ่งที่ควรเพิ่มเพื่อ audit ยอดพนักงานให้แข็งแรง

### P0 — ทำเพิ่มแล้วรอบแรก / ยังควรต่อยอด

1. **Employee master table + Telegram sender mapping — มีแล้วรอบแรก**
   - เพิ่มตาราง `employee_master` และ `employee_aliases`
   - sync จาก `user_id`, `username`, `sender_name` ของ Telegram โดยไม่แก้ข้อมูลสลิปเดิม
   - `daily-variance` ใช้ `employee_id`/`display_name` จาก master ก่อน แล้วค่อย fallback raw sender/transferor
   - ยังควรเพิ่มหน้าจอจัดการ alias/manual merge ถ้าคนเดียวมีหลายบัญชี Telegram

2. **Employee assignment ต่อสลิป — มีแบบ derived แล้ว / ยังขาด manual assign**
   - ตอนนี้ map ด้วย alias จาก Telegram sender โดยไม่เขียนทับ slip row
   - ยังควรมี manual assignment ต่อสลิป/ต่อกลุ่มรายการ เช่น `employee_id`, `employee_source` (`telegram_sender`, `manual_assign`, `backoffice_import`)
   - มีคิว “ยังไม่รู้พนักงาน” ให้ operator แก้

3. **Employee daily close / shift close — ยังขาด**
   - เปิดรอบพนักงาน, ปิดรอบพนักงาน, ยอดตั้งต้น, ยอดส่งมอบ, diff
   - เก็บลายเซ็น/ack หรืออย่างน้อย actor + timestamp

4. **Employee audit dashboard**
   - ยอดฝาก/ถอนรายพนักงาน
   - จำนวนสลิป, ยอดรวม, duplicate, missing bank, OCR issue
   - drill-down เห็นรูปสลิปและ reference ได้ทันที

5. **Employee audit export workbook**
   - `SummaryByEmployee`
   - `EmployeeDaily`
   - `EmployeeSlipEvidence`
   - `EmployeeExceptions`
   - ซ่อน internal id/token/file_id แต่เก็บหลักฐาน business fields ครบ

### P1 — เพิ่มเพื่อจับความเสี่ยง/โกง/ผิดพลาด

6. **Variance rules**
   - ยอดสลิป vs ledger vs หลังบ้าน ต่อพนักงาน/วัน
   - flag เมื่อ diff เกิน threshold

7. **Cross-employee / cross-company duplicate detection**
   - รายการเดียวกันถูกส่งหลายคน/หลายบริษัท/หลายกลุ่ม
   - แยก duplicate ที่ระบบ mark แล้วกับ suspicious duplicate ที่ยังไม่ mark

8. **Manual adjustment log**
   - เหตุผลการแก้ยอด/แก้ธนาคาร/แก้พนักงาน
   - actor, before/after, timestamp, audit-chain hash

9. **Role/RBAC เฉพาะ audit พนักงาน**
   - employee เห็นเฉพาะยอดตัวเอง
   - auditor เห็นทุกคนแต่ mutate ไม่ได้
   - admin ปรับ mapping/close ได้

10. **Exception queue แบบรายพนักงาน**
    - ไม่มี employee_id
    - สลิปไม่มีธนาคาร/บัญชี
    - OCR confidence ต่ำ
    - ยอดเกินวงเงิน
    - เวลาส่งรูปนอกกะ
    - รายการตรงยอดแต่ผิดบัญชี

### P2 — เสริมเมื่อข้อมูลเยอะ

11. **Trend/anomaly รายพนักงาน**
    - ยอดเฉลี่ย, จำนวนสลิปเฉลี่ย, sudden spike
    - สัดส่วนสลิปซ้ำ/แก้ไข/รีเช็คสูงผิดปกติ

12. **Evidence pack ต่อวัน**
    - zip/pdf รวม summary + Excel + รูปสลิปสำคัญ + audit-chain tail
    - ใช้ส่งให้บัญชี/หัวหน้างานตรวจย้อนหลัง

## 4. ขั้นตอนใช้งาน audit ที่ทำได้ตอนนี้

```bash
# ภาพรวม variance รายวัน
curl -fsS 'http://127.0.0.1:8095/api/audit/daily-variance?bot_key=__all__&scope=today&flow_type=all&threshold=100' \
  | python3 -m json.tool

# ตรวจซ้ำข้าม bot/chat
curl -fsS 'http://127.0.0.1:8095/api/audit/cross-dup?bot_key=__all__&scope=today' \
  | python3 -m json.tool

# เทียบสลิปกับ ledger รายบัญชี หลัง import ledger แล้ว
curl -fsS 'http://127.0.0.1:8095/api/audit/reconcile?bot_key=bot1&scope=today&flow_type=withdraw&account_key=<account>' \
  | python3 -m json.tool
```

## 5. คำแนะนำสั้น ๆ

ถ้าจะ audit ยอดพนักงานจริง ขั้นต่อไปที่คุ้มที่สุดหลังจากมี **Employee master + Telegram sender mapping** แล้ว คือเพิ่ม **manual alias/assignment + Employee daily close/shift close** เพื่อให้ identity ของ “พนักงานคนไหนรับผิดชอบรายการไหน” แข็งแรงพอสำหรับ audit เชิงความรับผิดชอบ

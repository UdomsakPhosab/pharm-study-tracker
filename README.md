# Pharm Group Navigator (Flask)

เว็บแอปสำหรับจัดข้อมูลอ่านสอบแบบคลิกเป็นชั้น:

1. กลุ่มโรค
2. กลุ่มยาในกลุ่มโรคนั้น
3. รายการยาในกลุ่มยา
4. รายละเอียดยาแต่ละตัว

## Run Local

```bash
cd "/Users/udomsak/Documents/New project"
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
export $(grep -v '^#' .env | xargs)
python3 app.py
```

เปิด [http://127.0.0.1:5000](http://127.0.0.1:5000)

## โครงสร้างข้อมูล

- `disease_groups`
- `drug_groups` (ผูกกับ disease_group)
- `drugs` (ผูกกับ drug_group)

ถ้าลบชั้นบน ข้อมูลชั้นล่างจะถูกลบตามอัตโนมัติ (cascade delete)

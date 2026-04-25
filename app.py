import os
import sqlite3
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "pharm_study.db"))).expanduser()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me-in-production")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db_connection()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS disease_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name_th TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS drug_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            disease_group_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (disease_group_id, name),
            FOREIGN KEY (disease_group_id) REFERENCES disease_groups(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS drugs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_group_id INTEGER NOT NULL,
            generic_name TEXT NOT NULL,
            brand_names TEXT,
            mechanism TEXT,
            indication_note TEXT,
            dose TEXT,
            side_effects TEXT,
            precautions TEXT,
            monitoring TEXT,
            exam_tip TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (drug_group_id, generic_name),
            FOREIGN KEY (drug_group_id) REFERENCES drug_groups(id) ON DELETE CASCADE
        );
        """
    )

    # Lightweight migration for users who already have an older `drugs` table.
    drug_cols = {row["name"] for row in conn.execute("PRAGMA table_info(drugs)").fetchall()}

    if "drug_group_id" not in drug_cols:
        conn.execute("INSERT OR IGNORE INTO disease_groups (name_th, description) VALUES (?, ?)", ("Uncategorized", "Auto-created from old schema"))
        uncategorized_group = conn.execute(
            "SELECT id FROM disease_groups WHERE name_th = ?",
            ("Uncategorized",),
        ).fetchone()["id"]
        conn.execute(
            "INSERT OR IGNORE INTO drug_groups (disease_group_id, name, description) VALUES (?, ?, ?)",
            (uncategorized_group, "Uncategorized Drugs", "Auto-created from old schema"),
        )
        default_drug_group = conn.execute(
            "SELECT id FROM drug_groups WHERE disease_group_id = ? AND name = ?",
            (uncategorized_group, "Uncategorized Drugs"),
        ).fetchone()["id"]
        conn.execute("ALTER TABLE drugs ADD COLUMN drug_group_id INTEGER")
        conn.execute("UPDATE drugs SET drug_group_id = ? WHERE drug_group_id IS NULL", (default_drug_group,))

    if "indication_note" not in drug_cols:
        conn.execute("ALTER TABLE drugs ADD COLUMN indication_note TEXT")
    if "dose" not in drug_cols:
        conn.execute("ALTER TABLE drugs ADD COLUMN dose TEXT")
    if "side_effects" not in drug_cols:
        conn.execute("ALTER TABLE drugs ADD COLUMN side_effects TEXT")
    if "precautions" not in drug_cols:
        conn.execute("ALTER TABLE drugs ADD COLUMN precautions TEXT")
    if "exam_tip" not in drug_cols:
        conn.execute("ALTER TABLE drugs ADD COLUMN exam_tip TEXT")

    # Map old column names to new names (best-effort, only when new columns are empty).
    if "common_dose" in drug_cols:
        conn.execute(
            "UPDATE drugs SET dose = common_dose WHERE (dose IS NULL OR dose = '') AND common_dose IS NOT NULL"
        )
    if "major_adrs" in drug_cols:
        conn.execute(
            "UPDATE drugs SET side_effects = major_adrs WHERE (side_effects IS NULL OR side_effects = '') AND major_adrs IS NOT NULL"
        )
    if "contraindications" in drug_cols:
        conn.execute(
            "UPDATE drugs SET precautions = contraindications WHERE (precautions IS NULL OR precautions = '') AND contraindications IS NOT NULL"
        )

    conn.commit()
    conn.close()


@app.route("/")
def home():
    conn = get_db_connection()
    groups = conn.execute(
        """
        SELECT dg.*, COUNT(DISTINCT gg.id) AS drug_group_count, COUNT(DISTINCT d.id) AS drug_count
        FROM disease_groups dg
        LEFT JOIN drug_groups gg ON gg.disease_group_id = dg.id
        LEFT JOIN drugs d ON d.drug_group_id = gg.id
        GROUP BY dg.id
        ORDER BY dg.name_th COLLATE NOCASE
        """
    ).fetchall()
    conn.close()
    return render_template("disease_groups.html", groups=groups)


@app.route("/disease-groups", methods=["POST"])
def create_disease_group():
    name_th = request.form.get("name_th", "").strip()
    description = request.form.get("description", "").strip()

    if not name_th:
        flash("กรุณาใส่ชื่อกลุ่มโรค", "error")
        return redirect(url_for("home"))

    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO disease_groups (name_th, description) VALUES (?, ?)",
            (name_th, description),
        )
        conn.commit()
        flash("เพิ่มกลุ่มโรคเรียบร้อย", "success")
    except sqlite3.IntegrityError:
        flash("มีกลุ่มโรคชื่อนี้แล้ว", "error")
    finally:
        conn.close()

    return redirect(url_for("home"))


@app.route("/disease-groups/<int:disease_group_id>")
def disease_group_detail(disease_group_id):
    conn = get_db_connection()
    group = conn.execute(
        "SELECT * FROM disease_groups WHERE id = ?", (disease_group_id,)
    ).fetchone()

    if not group:
        conn.close()
        flash("ไม่พบกลุ่มโรค", "error")
        return redirect(url_for("home"))

    drug_groups = conn.execute(
        """
        SELECT gg.*, COUNT(d.id) AS drug_count
        FROM drug_groups gg
        LEFT JOIN drugs d ON d.drug_group_id = gg.id
        WHERE gg.disease_group_id = ?
        GROUP BY gg.id
        ORDER BY gg.name COLLATE NOCASE
        """,
        (disease_group_id,),
    ).fetchall()
    conn.close()

    return render_template("drug_groups.html", group=group, drug_groups=drug_groups)


@app.route("/disease-groups/<int:disease_group_id>/drug-groups", methods=["POST"])
def create_drug_group(disease_group_id):
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()

    if not name:
        flash("กรุณาใส่ชื่อกลุ่มยา", "error")
        return redirect(url_for("disease_group_detail", disease_group_id=disease_group_id))

    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO drug_groups (disease_group_id, name, description) VALUES (?, ?, ?)",
            (disease_group_id, name, description),
        )
        conn.commit()
        flash("เพิ่มกลุ่มยาเรียบร้อย", "success")
    except sqlite3.IntegrityError:
        flash("มีกลุ่มยาชื่อนี้ในกลุ่มโรคนี้แล้ว", "error")
    finally:
        conn.close()

    return redirect(url_for("disease_group_detail", disease_group_id=disease_group_id))


@app.route("/drug-groups/<int:drug_group_id>")
def drug_group_detail(drug_group_id):
    conn = get_db_connection()
    drug_group = conn.execute(
        """
        SELECT gg.*, dg.name_th AS disease_group_name, dg.id AS disease_group_id
        FROM drug_groups gg
        JOIN disease_groups dg ON dg.id = gg.disease_group_id
        WHERE gg.id = ?
        """,
        (drug_group_id,),
    ).fetchone()

    if not drug_group:
        conn.close()
        flash("ไม่พบกลุ่มยา", "error")
        return redirect(url_for("home"))

    drugs = conn.execute(
        "SELECT * FROM drugs WHERE drug_group_id = ? ORDER BY generic_name COLLATE NOCASE",
        (drug_group_id,),
    ).fetchall()
    conn.close()

    return render_template("drugs.html", drug_group=drug_group, drugs=drugs)


@app.route("/drug-groups/<int:drug_group_id>/drugs", methods=["POST"])
def create_drug(drug_group_id):
    generic_name = request.form.get("generic_name", "").strip()

    if not generic_name:
        flash("กรุณาใส่ชื่อยา", "error")
        return redirect(url_for("drug_group_detail", drug_group_id=drug_group_id))

    conn = get_db_connection()
    try:
        conn.execute(
            """
            INSERT INTO drugs (
                drug_group_id, generic_name, brand_names, mechanism, indication_note,
                dose, side_effects, precautions, monitoring, exam_tip
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                drug_group_id,
                generic_name,
                request.form.get("brand_names", "").strip(),
                request.form.get("mechanism", "").strip(),
                request.form.get("indication_note", "").strip(),
                request.form.get("dose", "").strip(),
                request.form.get("side_effects", "").strip(),
                request.form.get("precautions", "").strip(),
                request.form.get("monitoring", "").strip(),
                request.form.get("exam_tip", "").strip(),
            ),
        )
        conn.commit()
        flash("เพิ่มยาเรียบร้อย", "success")
    except sqlite3.IntegrityError:
        flash("มียาชื่อนี้ในกลุ่มนี้แล้ว", "error")
    finally:
        conn.close()

    return redirect(url_for("drug_group_detail", drug_group_id=drug_group_id))


@app.route("/drugs/<int:drug_id>", methods=["GET", "POST"])
def drug_detail(drug_id):
    conn = get_db_connection()
    drug = conn.execute(
        """
        SELECT d.*, gg.name AS drug_group_name, gg.id AS drug_group_id,
               dg.id AS disease_group_id, dg.name_th AS disease_group_name
        FROM drugs d
        JOIN drug_groups gg ON gg.id = d.drug_group_id
        JOIN disease_groups dg ON dg.id = gg.disease_group_id
        WHERE d.id = ?
        """,
        (drug_id,),
    ).fetchone()

    if not drug:
        conn.close()
        flash("ไม่พบข้อมูลยา", "error")
        return redirect(url_for("home"))

    if request.method == "POST":
        generic_name = request.form.get("generic_name", "").strip()
        if not generic_name:
            conn.close()
            flash("ชื่อยาห้ามว่าง", "error")
            return redirect(url_for("drug_detail", drug_id=drug_id))

        try:
            conn.execute(
                """
                UPDATE drugs
                SET generic_name = ?, brand_names = ?, mechanism = ?, indication_note = ?,
                    dose = ?, side_effects = ?, precautions = ?, monitoring = ?, exam_tip = ?
                WHERE id = ?
                """,
                (
                    generic_name,
                    request.form.get("brand_names", "").strip(),
                    request.form.get("mechanism", "").strip(),
                    request.form.get("indication_note", "").strip(),
                    request.form.get("dose", "").strip(),
                    request.form.get("side_effects", "").strip(),
                    request.form.get("precautions", "").strip(),
                    request.form.get("monitoring", "").strip(),
                    request.form.get("exam_tip", "").strip(),
                    drug_id,
                ),
            )
            conn.commit()
            flash("อัปเดตรายละเอียดยาเรียบร้อย", "success")
        except sqlite3.IntegrityError:
            flash("มียาชื่อนี้ซ้ำในกลุ่มยาเดียวกัน", "error")

        conn.close()
        return redirect(url_for("drug_detail", drug_id=drug_id))

    conn.close()
    return render_template("drug_detail.html", drug=drug)


@app.route("/disease-groups/<int:disease_group_id>/delete", methods=["POST"])
def delete_disease_group(disease_group_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM disease_groups WHERE id = ?", (disease_group_id,))
    conn.commit()
    conn.close()
    flash("ลบกลุ่มโรคเรียบร้อย", "success")
    return redirect(url_for("home"))


@app.route("/drug-groups/<int:drug_group_id>/delete", methods=["POST"])
def delete_drug_group(drug_group_id):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT disease_group_id FROM drug_groups WHERE id = ?", (drug_group_id,)
    ).fetchone()

    if not row:
        conn.close()
        flash("ไม่พบกลุ่มยา", "error")
        return redirect(url_for("home"))

    conn.execute("DELETE FROM drug_groups WHERE id = ?", (drug_group_id,))
    conn.commit()
    conn.close()
    flash("ลบกลุ่มยาเรียบร้อย", "success")
    return redirect(url_for("disease_group_detail", disease_group_id=row["disease_group_id"]))


@app.route("/drugs/<int:drug_id>/delete", methods=["POST"])
def delete_drug(drug_id):
    conn = get_db_connection()
    row = conn.execute("SELECT drug_group_id FROM drugs WHERE id = ?", (drug_id,)).fetchone()

    if not row:
        conn.close()
        flash("ไม่พบยา", "error")
        return redirect(url_for("home"))

    conn.execute("DELETE FROM drugs WHERE id = ?", (drug_id,))
    conn.commit()
    conn.close()
    flash("ลบยาเรียบร้อย", "success")
    return redirect(url_for("drug_group_detail", drug_group_id=row["drug_group_id"]))


if __name__ == "__main__":
    init_db()
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")
else:
    init_db()

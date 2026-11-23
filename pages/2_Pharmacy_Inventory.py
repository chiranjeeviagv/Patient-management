import streamlit as st
import pandas as pd
import sqlite3
from utils import load_clinical_data, apply_custom_ui, render_hero, require_login

st.set_page_config(page_title="Pharmacy Inventory", page_icon="📦", layout="wide")
apply_custom_ui()

# Default catalog mapping for the 22 newly added specialty medicines (Category, Default INR Price)
NEW_MEDICINE_CATALOG = {
    "Telmisartan 40mg": ("Cardiology", 145.0),
    "Torsemide 10mg": ("Cardiology", 95.0),
    "Cetirizine 10mg": ("Dermatology", 35.0),
    "Clotrimazole Cream": ("Dermatology", 85.0),
    "Aceclofenac Combo": ("Orthopedics", 110.0),
    "Etoricoxib 90mg": ("Orthopedics", 160.0),
    "Mebeverine 135mg": ("Gastroenterology", 180.0),
    "Esomeprazole 40mg": ("Gastroenterology", 130.0),
    "Tiotropium Rotacaps": ("Pulmonology", 320.0),
    "Fluticasone Spray": ("Pulmonology", 290.0),
    "Metformin 500mg": ("Endocrinology", 65.0),
    "Levothyroxine 50mcg": ("Endocrinology", 115.0),
    "Renal Diet Protocol": ("Nephrology", 250.0),
    "Potassium Citrate Syr.": ("Nephrology", 140.0),
    "Tamsulosin 0.4mg": ("Urology", 210.0),
    "Nitrofurantoin 100mg": ("Urology", 125.0),
    "Ondansetron 8mg": ("Oncology", 90.0),
    "Hydroxychloroquine 200mg": ("Rheumatology", 175.0),
    "Indomethacin 75mg": ("Rheumatology", 120.0),
    "IFT Rehab Protocol": ("Physiotherapy", 400.0),
    "Ultrasound & Exercise": ("Physiotherapy", 350.0),
}

def sync_clinical_medicines_to_db(rules_df: pd.DataFrame):
    """Ensures every medicine referenced in the clinical CSV exists in SQLite inventory."""
    conn = sqlite3.connect("hospital_v2.db")
    cursor = conn.cursor()
    existing = {
        row[0].strip()
        for row in cursor.execute("SELECT medicine_name FROM inventory").fetchall()
        if row[0]
    }
    
    # Combine CSV medicines with the catalog so all 20 specialties are covered
    csv_meds = {
        str(m).strip()
        for m in rules_df["medicine"].dropna().unique()
        if str(m).strip() not in ("", "None", "Diagnostic Workup")
    }
    all_target_meds = csv_meds.union(NEW_MEDICINE_CATALOG.keys())

    inserted = 0
    for med in sorted(all_target_meds):
        if med not in existing:
            cat, price = NEW_MEDICINE_CATALOG.get(med, ("General", 100.0))
            cursor.execute(
                "INSERT INTO inventory (medicine_name, category, stock_qty, min_required, unit_price) VALUES (?, ?, ?, ?, ?)",
                (med, cat, 50, 10, price),
            )
            inserted += 1

    if inserted > 0:
        conn.commit()
    conn.close()
    return inserted

if require_login("Pharmacy Inventory", "pharma123"):
    render_hero("📦 Medical Dispensary & Pharmacy Stock", "Monitor stock levels, unit pricing, and reorder alerts.")
    
    _, rules_df = load_clinical_data()
    newly_synced = sync_clinical_medicines_to_db(rules_df)
    if newly_synced > 0:
        st.toast(f"Synced {newly_synced} new specialty formulas into pharmacy stock!", icon="✅")

    conn = sqlite3.connect("hospital_v2.db")
    df_inv = pd.read_sql_query(
        "SELECT id AS ID, medicine_name AS [Medicine Name], category AS [Category], "
        "stock_qty AS [Stock], min_required AS [Min Limit], unit_price AS [Price (₹)] "
        "FROM inventory ORDER BY category, medicine_name",
        conn
    )
    conn.close()

    low_stock = df_inv[df_inv["Stock"] <= df_inv["Min Limit"]]
    total_val = (df_inv["Stock"] * df_inv["Price (₹)"]).sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Formulas", len(df_inv))
    c2.metric("Low Stock Alerts", len(low_stock), delta=-len(low_stock) if len(low_stock) else 0, delta_color="inverse")
    c3.metric("Total Stock Valuation", f"₹{total_val:,.2f}")

    if not low_stock.empty:
        st.error("⚠️ Low Stock Warning — Reorder Required:")
        st.dataframe(low_stock, use_container_width=True, hide_index=True)

    # Filter bar
    f_col1, f_col2 = st.columns([2, 1])
    search_med = f_col1.text_input("🔍 Search Medicine:", placeholder="Type medicine name...")
    categories = ["All Categories"] + sorted(df_inv["Category"].dropna().unique().tolist())
    selected_cat = f_col2.selectbox("Filter by Category:", categories)

    filtered_inv = df_inv.copy()
    if search_med:
        filtered_inv = filtered_inv[filtered_inv["Medicine Name"].str.contains(search_med, case=False, na=False)]
    if selected_cat != "All Categories":
        filtered_inv = filtered_inv[filtered_inv["Category"] == selected_cat]

    edited_inv = st.data_editor(
        filtered_inv,
        column_config={
            "Stock": st.column_config.NumberColumn("Stock", min_value=0, step=1, required=True),
            "Min Limit": st.column_config.NumberColumn("Min Limit", min_value=0, step=1, required=True),
            "Price (₹)": st.column_config.NumberColumn("Price (₹)", min_value=0.0, step=5.0, format="₹%.2f", required=True),
        },
        disabled=["ID", "Medicine Name", "Category"],
        use_container_width=True,
        hide_index=True,
    )

    if st.button("💾 Save Inventory Updates", type="primary"):
        conn = sqlite3.connect("hospital_v2.db")
        for _, row in edited_inv.iterrows():
            conn.execute(
                "UPDATE inventory SET stock_qty = ?, min_required = ?, unit_price = ? WHERE id = ?",
                (int(row["Stock"]), int(row["Min Limit"]), float(row["Price (₹)"]), int(row["ID"]))
            )
        conn.commit()
        conn.close()
        st.success("Inventory updated!")
        st.rerun()

    # Manual entry form for new medicines
    with st.expander("➕ Add New Medicine to Dispensary"):
        with st.form("add_med_form", clear_on_submit=True):
            a1, a2, a3, a4, a5 = st.columns([2, 1.5, 1, 1, 1])
            new_name = a1.text_input("Medicine Name")
            new_cat = a2.text_input("Category / Specialty", value="General")
            new_stock = a3.number_input("Initial Stock", min_value=0, value=50, step=1)
            new_min = a4.number_input("Min Limit", min_value=0, value=10, step=1)
            new_price = a5.number_input("Unit Price (₹)", min_value=0.0, value=100.0, step=5.0)
            if st.form_submit_button("Add Formula"):
                if new_name.strip():
                    conn = sqlite3.connect("hospital_v2.db")
                    exists = conn.execute("SELECT 1 FROM inventory WHERE medicine_name = ?", (new_name.strip(),)).fetchone()
                    if exists:
                        st.warning(f"'{new_name.strip()}' already exists in inventory.")
                    else:
                        conn.execute(
                            "INSERT INTO inventory (medicine_name, category, stock_qty, min_required, unit_price) VALUES (?, ?, ?, ?, ?)",
                            (new_name.strip(), new_cat.strip(), int(new_stock), int(new_min), float(new_price))
                        )
                        conn.commit()
                        st.success(f"Added '{new_name.strip()}' to inventory!")
                        st.rerun()
                    conn.close()
                else:
                    st.error("Please enter a valid medicine name.")

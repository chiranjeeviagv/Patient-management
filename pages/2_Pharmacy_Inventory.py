import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
from datetime import datetime
from utils import load_clinical_data, apply_custom_ui, render_hero, require_login
from security_utils import log_audit_event

st.set_page_config(page_title="Pharmacy Inventory", page_icon="📦", layout="wide")
apply_custom_ui()

DB_PATH = "hospital_v2.db"

# Default catalog mapping for specialty medicines (Category, Default INR Price)
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    existing = {
        row[0].strip()
        for row in cursor.execute("SELECT medicine_name FROM inventory").fetchall()
        if row[0]
    }
    
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
    render_hero("📦 Medical Dispensary & Predictive Supply Chain", "Monitor live stock levels, consumption velocity, stockout forecasts, and automated reorder POs.")
    
    _, rules_df = load_clinical_data()
    newly_synced = sync_clinical_medicines_to_db(rules_df)
    if newly_synced > 0:
        st.toast(f"Synced {newly_synced} new specialty formulas into pharmacy stock!", icon="✅")

    conn = sqlite3.connect(DB_PATH)
    df_inv = pd.read_sql_query(
        "SELECT id AS ID, medicine_name AS [Medicine Name], category AS [Category], "
        "stock_qty AS [Stock], min_required AS [Min Limit], unit_price AS [Price (₹)] "
        "FROM inventory ORDER BY category, medicine_name",
        conn
    )
    df_dispensed = pd.read_sql_query(
        "SELECT medicine_dispensed FROM consultations WHERE medicine_dispensed IS NOT NULL AND medicine_dispensed != 'None'",
        conn
    )
    conn.close()

    # --- PREDICTIVE DEMAND & RUNWAY ANALYTICS ---
    dispense_counts = df_dispensed["medicine_dispensed"].str.strip().value_counts().to_dict() if not df_dispensed.empty else {}
    
    def compute_forecast(row):
        med = str(row["Medicine Name"]).strip()
        stock = int(row["Stock"])
        min_lim = int(row["Min Limit"])
        # Baseline clinical velocity + observed consultation dispensing rate
        observed = dispense_counts.get(med, 0)
        est_daily_burn = round(max(1.2, observed * 1.5), 1)
        days_left = round(stock / est_daily_burn, 1)
        target_buffer = max(min_lim * 3, int(est_daily_burn * 14))
        reorder_qty = max(0, target_buffer - stock) if stock <= (min_lim * 1.5) else 0
        return pd.Series([observed, est_daily_burn, days_left, reorder_qty])

    df_inv[["Dispensed (Rx)", "Est. Daily Burn", "Days to Stockout", "Suggested Reorder Qty"]] = df_inv.apply(compute_forecast, axis=1)

    low_stock = df_inv[df_inv["Stock"] <= df_inv["Min Limit"]]
    at_risk_stock = df_inv[(df_inv["Days to Stockout"] <= 14) | (df_inv["Stock"] <= df_inv["Min Limit"])].sort_values("Days to Stockout")
    total_val = (df_inv["Stock"] * df_inv["Price (₹)"]).sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Formulas", len(df_inv))
    c2.metric("Critical Low Stock", len(low_stock), delta=-len(low_stock) if len(low_stock) else 0, delta_color="inverse")
    c3.metric("14-Day Stockout Risk", len(at_risk_stock))
    c4.metric("Total Stock Valuation", f"₹{total_val:,.2f}")

    tab_stock, tab_forecast, tab_add = st.tabs([
        "📋 Live Stock Ledger",
        "📈 Predictive Demand & Auto-Reorder PO",
        "➕ Add New Formula"
    ])

    with tab_stock:
        if not low_stock.empty:
            st.error("⚠️ Immediate Reorder Required (Below Minimum Safety Threshold):")
            st.dataframe(low_stock[["Medicine Name", "Category", "Stock", "Min Limit", "Days to Stockout", "Suggested Reorder Qty"]], use_container_width=True, hide_index=True)

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
            filtered_inv[["ID", "Medicine Name", "Category", "Stock", "Min Limit", "Price (₹)", "Days to Stockout"]],
            column_config={
                "Stock": st.column_config.NumberColumn("Stock", min_value=0, step=1, required=True),
                "Min Limit": st.column_config.NumberColumn("Min Limit", min_value=0, step=1, required=True),
                "Price (₹)": st.column_config.NumberColumn("Price (₹)", min_value=0.0, step=5.0, format="₹%.2f", required=True),
            },
            disabled=["ID", "Medicine Name", "Category", "Days to Stockout"],
            use_container_width=True,
            hide_index=True,
        )

        if st.button("💾 Save Inventory Updates", type="primary"):
            conn = sqlite3.connect(DB_PATH)
            for _, row in edited_inv.iterrows():
                conn.execute(
                    "UPDATE inventory SET stock_qty = ?, min_required = ?, unit_price = ? WHERE id = ?",
                    (int(row["Stock"]), int(row["Min Limit"]), float(row["Price (₹)"]), int(row["ID"]))
                )
            conn.commit()
            conn.close()
            log_audit_event("Pharmacist", "Dispensary_Desk", "UPDATE_INVENTORY", f"{len(edited_inv)} records", db_path=DB_PATH)
            st.success("✅ Inventory updated and logged to audit trail!")
            st.rerun()

    with tab_forecast:
        st.subheader("🔮 Supply Runway & Automated Reorder Forecasting")
        st.caption("Calculates expected days remaining using clinical dispensing velocity and generates 14-day safety-buffer purchase orders.")

        # Top 15 shortest-runway items bar chart
        top_risk_chart = df_inv.sort_values("Days to Stockout").head(15)
        fig_runway = px.bar(
            top_risk_chart,
            x="Days to Stockout",
            y="Medicine Name",
            color="Category",
            orientation="h",
            title="Top 15 Medications by Shortest Stock Runway (Days Remaining)",
            text_auto=True
        )
        fig_runway.update_layout(yaxis={"categoryorder": "total descending"}, height=450)
        st.plotly_chart(fig_runway, use_container_width=True)

        # Automated Purchase Order Table & CSV Download
        po_df = df_inv[df_inv["Suggested Reorder Qty"] > 0][
            ["Medicine Name", "Category", "Stock", "Est. Daily Burn", "Days to Stockout", "Suggested Reorder Qty", "Price (₹)"]
        ].copy()
        po_df["Estimated PO Cost (₹)"] = (po_df["Suggested Reorder Qty"] * po_df["Price (₹)"]).round(2)

        if not po_df.empty:
            st.markdown("#### 🧾 Generated Supplier Purchase Order (14-Day Replenishment Buffer)")
            st.dataframe(po_df, use_container_width=True, hide_index=True)
            po_csv = po_df.to_csv(index=False).encode("utf-8")
            if st.download_button(
                label=f"📥 Download Purchase Order CSV (Total: ₹{po_df['Estimated PO Cost (₹)'].sum():,.2f})",
                data=po_csv,
                file_name=f"Sunrise_Pharmacy_PO_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                type="primary"
            ):
                log_audit_event("Pharmacist", "Dispensary_Desk", "EXPORT_PURCHASE_ORDER", f"{len(po_df)} items", db_path=DB_PATH)
        else:
            st.success("✅ All formulas currently exceed the 14-day safety stock buffer. No immediate purchase order needed.")

    with tab_add:
        st.subheader("➕ Register New Formula in Dispensary")
        with st.form("add_med_form", clear_on_submit=True):
            a1, a2, a3, a4, a5 = st.columns([2, 1.5, 1, 1, 1])
            new_name = a1.text_input("Medicine Name")
            new_cat = a2.text_input("Category / Specialty", value="General")
            new_stock = a3.number_input("Initial Stock", min_value=0, value=50, step=1)
            new_min = a4.number_input("Min Limit", min_value=0, value=10, step=1)
            new_price = a5.number_input("Unit Price (₹)", min_value=0.0, value=100.0, step=5.0)
            if st.form_submit_button("Add Formula", type="primary"):
                if new_name.strip():
                    conn = sqlite3.connect(DB_PATH)
                    exists = conn.execute("SELECT 1 FROM inventory WHERE medicine_name = ?", (new_name.strip(),)).fetchone()
                    if exists:
                        st.warning(f"'{new_name.strip()}' already exists in inventory.")
                    else:
                        conn.execute(
                            "INSERT INTO inventory (medicine_name, category, stock_qty, min_required, unit_price) VALUES (?, ?, ?, ?, ?)",
                            (new_name.strip(), new_cat.strip(), int(new_stock), int(new_min), float(new_price))
                        )
                        conn.commit()
                        log_audit_event("Pharmacist", "Dispensary_Desk", "ADD_NEW_MEDICINE", new_name.strip(), db_path=DB_PATH)
                        st.success(f"Added '{new_name.strip()}' to inventory!")
NEW_SPECIALTY_MEDICINES = [
    ("Potassium Citrate Syr.", "Urology", 85, 145.0, "2027-08-31"),
    ("Hydroxychloroquine 200mg", "Rheumatology", 110, 180.0, "2027-10-15"),
    ("Ferrous Ascorbate", "Hematology", 150, 160.0, "2027-11-30"),
    ("Diosmin 500mg", "Vascular Surgery", 75, 290.0, "2027-07-31"),
    ("Silicone Scar Gel", "Plastic Surgery", 40, 550.0, "2027-09-30"),
    ("Donepezil 5mg", "Geriatrics", 65, 240.0, "2027-12-31"),
    ("Gabapentin 300mg", "Neurosurgery", 95, 210.0, "2027-08-15"),
    ("Atorvastatin 40mg", "Cardiothoracic Surgery", 140, 195.0, "2027-10-31"),
    ("Ursodeoxycholic Acid", "Hepatology", 70, 380.0, "2027-06-30"),
    ("Duloxetine 30mg", "Pain & Palliative Care", 80, 225.0, "2027-09-15"),
    ("Nitrofurantoin 100mg", "Urology", 90, 135.0, "2027-07-15"),
    ("Clopidogrel 75mg", "Cardiothoracic Surgery", 120, 175.0, "2027-11-15"),
    ("Surgical Consumables & Dressing Kit", "General Surgery / OT", 60, 450.0, "2028-01-31"),
]                        st.rerun()
                    conn.close()
                else:
                    st.error("Please enter a valid medicine name.")

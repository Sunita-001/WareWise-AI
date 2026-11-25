from __future__ import annotations
import sqlite3
from pathlib import Path
from datetime import date, datetime, timedelta
import pandas as pd
import streamlit as st
import plotly.express as px

DB = Path(__file__).with_name("warewise.db")
st.set_page_config(page_title="WareWise AI", page_icon="📦", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@600;700;800&display=swap');
.stApp{background:#F6F8F9;font-family:'DM Sans',sans-serif}
.block-container{max-width:1450px;padding-top:1.5rem}
h1,h2,h3{font-family:Manrope,sans-serif;color:#172B3A;letter-spacing:-.03em}
section[data-testid="stSidebar"]{background:#fff;border-right:1px solid #E7EDF1}
div[data-testid="stMetric"]{background:white;border:1px solid #E7EDF1;border-radius:14px;padding:16px}
.stButton>button,.stDownloadButton>button{border-radius:10px;font-weight:600}
.stButton>button[kind="primary"]{background:#167D78;border-color:#167D78}
div[data-testid="stDataFrame"]{border:1px solid #E7EDF1;border-radius:12px}
</style>
""", unsafe_allow_html=True)

def db():
    c=sqlite3.connect(DB,timeout=20); c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); return c

def init():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS products(sku TEXT PRIMARY KEY,name TEXT NOT NULL,category TEXT DEFAULT 'Other',quantity INTEGER NOT NULL DEFAULT 0,reorder_level INTEGER NOT NULL DEFAULT 0,unit_cost REAL NOT NULL DEFAULT 0,location TEXT DEFAULT '',supplier TEXT DEFAULT '',expiry_date TEXT DEFAULT '',created_at TEXT NOT NULL,barcode TEXT DEFAULT '',updated_at TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT,sku TEXT,movement_type TEXT,quantity INTEGER,before_qty INTEGER,after_qty INTEGER,reference TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS sales(id INTEGER PRIMARY KEY AUTOINCREMENT,sold_on TEXT NOT NULL,sku TEXT NOT NULL,quantity INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS purchase_orders(id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT NOT NULL,supplier TEXT DEFAULT '',sku TEXT NOT NULL,product_name TEXT NOT NULL,quantity INTEGER NOT NULL,unit_cost REAL NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'Draft',notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS activity_log(id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT NOT NULL,action TEXT NOT NULL,detail TEXT DEFAULT '');
        """)
        cols={r["name"] for r in c.execute("PRAGMA table_info(products)")}
        for col in ("barcode","updated_at"):
            if col not in cols: c.execute(f"ALTER TABLE products ADD COLUMN {col} TEXT DEFAULT ''")
        if c.execute("SELECT COUNT(*) FROM products").fetchone()[0]==0:
            today=date.today()
            samples=[
            ("SKU101","Wireless Mouse","Electronics",42,15,450,"Aisle A / Shelf 02","TechSource",""),
            ("SKU102","USB-C Cable","Electronics",8,20,180,"Aisle A / Shelf 04","ConnectPro",""),
            ("SKU103","Notebook A4","Stationery",120,30,45,"Aisle B / Shelf 01","PaperWorld",""),
            ("SKU104","Printer Paper Ream","Stationery",18,25,220,"Aisle B / Shelf 03","PaperWorld",""),
            ("SKU105","Hand Sanitizer 500ml","Essentials",14,20,95,"Aisle C / Shelf 02","CleanCare",(today+timedelta(days=22)).isoformat()),
            ("SKU106","LED Desk Lamp","Electronics",31,10,780,"Aisle A / Shelf 07","BrightHome",""),
            ("SKU107","Bottled Water Pack","Essentials",55,25,120,"Aisle C / Shelf 01","AquaSupply",(today+timedelta(days=5)).isoformat()),
            ("SKU108","Packing Tape","Packaging",6,18,65,"Aisle D / Shelf 02","PackRight",""),
            ("SKU109","Cardboard Box Medium","Packaging",90,25,28,"Aisle D / Shelf 01","PackRight",""),
            ("SKU110","AA Batteries Pack","Electronics",12,15,160,"Aisle A / Shelf 09","PowerPlus","")]
            now=datetime.now().isoformat(timespec="seconds")
            c.executemany("INSERT INTO products(sku,name,category,quantity,reorder_level,unit_cost,location,supplier,expiry_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",[(*p,now,now) for p in samples])
            for i,p in enumerate(samples):
                for offset in range(30,0,-1):
                    q=((i+offset)%5)+(1 if i%3==0 else 0)
                    if q:c.execute("INSERT INTO sales(sold_on,sku,quantity) VALUES(?,?,?)",((today-timedelta(days=offset)).isoformat(),p[0],q))
        c.commit()

def products():
    with db() as c:return pd.read_sql_query("SELECT * FROM products ORDER BY name",c)
def movements():
    with db() as c:return pd.read_sql_query("SELECT * FROM movements ORDER BY id DESC LIMIT 500",c)
def low(df):return df[df.quantity<=df.reorder_level].copy()
def expiring(df,days=30):
    x=df[df.expiry_date.fillna("").astype(str)!=""].copy()
    if x.empty:return x.assign(days_left=pd.Series(dtype=int))
    x["days_left"]=(pd.to_datetime(x.expiry_date,errors="coerce").dt.date-date.today()).apply(lambda d:d.days if pd.notna(d) else 99999)
    return x[(x.days_left>=0)&(x.days_left<=days)].sort_values("days_left")
def stock_change(sku,kind,qty,ref):
    if qty<=0:raise ValueError("Quantity must be positive")
    with db() as c:
        r=c.execute("SELECT quantity FROM products WHERE sku=?",(sku,)).fetchone()
        if not r:raise ValueError("SKU not found")
        before=int(r["quantity"]); after=before+qty if kind=="Stock In" else before-qty
        if after<0:raise ValueError(f"Only {before} units are available")
        now=datetime.now().isoformat(timespec="seconds")
        c.execute("UPDATE products SET quantity=?,updated_at=? WHERE sku=?",(after,now,sku))
        c.execute("INSERT INTO movements(created_at,sku,movement_type,quantity,before_qty,after_qty,reference) VALUES(?,?,?,?,?,?,?)",(now,sku,kind,qty,before,after,ref))
        c.commit()
    return before,after
def forecast(sku,days):
    with db() as c:x=pd.read_sql_query("SELECT sold_on,quantity FROM sales WHERE sku=?",(sku,),c)
    if x.empty:return 0.0,0
    x["sold_on"]=pd.to_datetime(x.sold_on); d=x.groupby("sold_on").quantity.sum()
    d=d.reindex(pd.date_range(d.index.min(),d.index.max(),freq="D"),fill_value=0)
    avg=float(d.tail(14).mean());return avg,round(avg*days)
def answer(q,df):
    q=q.lower().strip()
    if any(k in q for k in ["low stock","running low","shortage","out of stock","below reorder"]):
        x=low(df)
        return "No low-stock items." if x.empty else "\n".join(f"- **{r['name']} ({r.sku})**: {r.quantity} left; reorder level {r.reorder_level}; {r.location}" for _,r in x.iterrows())
    if any(k in q for k in ["expir","expire"]):
        x=expiring(df,45)
        return "No upcoming expiries recorded." if x.empty else "\n".join(f"- **{r['name']}**: {r.days_left} days left · {r.quantity} units · {r.location}" for _,r in x.iterrows())
    if any(k in q for k in ["reorder","restock","purchase","buy more"]):
        rows=[]
        for _,r in df.iterrows():
            avg,d=forecast(r.sku,14); n=max(0,max(int(r.reorder_level)*2,d)-int(r.quantity))
            if n:rows.append(f"- **{r['name']}** ({r.sku}): order {n} from {r.supplier or 'supplier not set'}")
        return "\n".join(rows) if rows else "No replenishment suggested."
    if "forecast" in q or "demand" in q:
        days=7 if "7" in q else 14
        return "\n".join(f"- {r['name']}: {forecast(r.sku,days)[1]} units expected in {days} days" for _,r in df.iterrows())
    if any(k in q for k in ["value","worth","stock value"]):return f"Recorded inventory value: ₹{(df.quantity*df.unit_cost).sum():,.2f}"
    for _,r in df.iterrows():
        if r.sku.lower() in q or r["name"].lower() in q or (str(r.barcode).strip() and str(r.barcode).lower() in q):
            return f"**{r['name']} · {r.sku}**\n\n- Quantity: {r.quantity}\n- Location: {r.location}\n- Reorder level: {r.reorder_level}\n- Supplier: {r.supplier}\n- Expiry: {r.expiry_date or 'Not recorded'}"
    return "Try: Where is SKU102? · Which products are running low? · What is expiring soon? · What should I reorder? · Forecast demand for 14 days · What is my stock value?"

init()
df=products()
with st.sidebar:
    st.markdown("## warewise<span style='color:#167D78'>.</span>",unsafe_allow_html=True)
    st.caption("WAREHOUSE INTELLIGENCE")
    page=st.radio("WORKSPACE",["Overview","AI Assistant","Inventory","Stock Movements","Warehouse Map","Demand & Reorder","Purchase Orders","Reports"])
    st.divider();st.success("Local database connected")
    st.caption("WareWise AI · Minimal Edition")

def header(title,sub):
    st.caption("WAREWISE / OPERATIONS");st.title(title);st.caption(sub)

if page=="Overview":
    header("Warehouse overview","A clear view of inventory health and operational priorities.")
    a,b,c,d=st.columns(4);a.metric("Total SKUs",len(df));b.metric("Units on hand",f"{int(df.quantity.sum()):,}");c.metric("Inventory value",f"₹{(df.quantity*df.unit_cost).sum():,.0f}");d.metric("Needs attention",len(low(df))+len(expiring(df)))
    l,r=st.columns([1.3,1])
    with l:
        st.subheader("Inventory by category")
        if not df.empty:st.plotly_chart(px.pie(df.groupby("category",as_index=False).quantity.sum(),names="category",values="quantity",hole=.65,color_discrete_sequence=["#167D78","#72B7AE","#A9D8D1","#D8EAE7","#AAB7C4"]),use_container_width=True)
    with r:
        st.subheader("Attention required")
        for _,x in low(df).iterrows():st.warning(f"{x['name']}: {x.quantity} units (reorder at {x.reorder_level})")
        for _,x in expiring(df).iterrows():st.warning(f"{x['name']} expires in {x.days_left} days")
    st.subheader("Recent stock activity");st.dataframe(movements(),use_container_width=True,hide_index=True)
elif page=="AI Assistant":
    header("AI command center","Ask operational questions about your live inventory.")
    prompts=["Where is SKU102?","Which products are running low?","What is expiring soon?","What should I reorder?","Forecast demand for 14 days","What is my stock value?"]
    cols=st.columns(3)
    for i,p in enumerate(prompts):
        if cols[i%3].button(p,key=f"p{i}",use_container_width=True):st.session_state.question=p
    q=st.text_input("Message WareWise",key="question",placeholder="Ask about stock, location, expiry or demand")
    if st.button("Send message",type="primary"):
        st.session_state.setdefault("history",[]).extend([("You",q),("WareWise",answer(q,products()))])
    for who,msg in st.session_state.get("history",[])[-12:]:
        with st.chat_message("user" if who=="You" else "assistant"):st.markdown(msg)
    if st.button("Clear conversation"):st.session_state.history=[];st.rerun()
elif page=="Inventory":
    header("Inventory","Search, filter and maintain product records.")
    search=st.text_input("Search by SKU, name, category, supplier or location")
    cat=st.selectbox("Category",["All"]+sorted(df.category.dropna().unique().tolist()))
    view=df.copy()
    if search:view=view[view.astype(str).apply(lambda col:col.str.contains(search,case=False,na=False)).any(axis=1)]
    if cat!="All":view=view[view.category==cat]
    st.dataframe(view,use_container_width=True,hide_index=True)
    st.download_button("Export inventory CSV",view.to_csv(index=False).encode("utf-8-sig"),"warewise_inventory.csv")
    with st.expander("Add product"):
        with st.form("add"):
            a,b,c=st.columns(3);sku=a.text_input("SKU").strip().upper();name=b.text_input("Name");category=c.selectbox("Category",["Electronics","Stationery","Essentials","Packaging","Food","Other"])
            a,b,c=st.columns(3);qty=a.number_input("Quantity",min_value=0);reorder=b.number_input("Reorder level",min_value=0);cost=c.number_input("Unit cost ₹",min_value=0.0)
            a,b,c=st.columns(3);loc=a.text_input("Location");supplier=b.text_input("Supplier");barcode=c.text_input("Barcode")
            expiry=st.text_input("Expiry YYYY-MM-DD (optional)");save=st.form_submit_button("Save product",type="primary")
        if save:
            try:
                if not sku or not name:raise ValueError("SKU and name required")
                if expiry:date.fromisoformat(expiry)
                with db() as con:con.execute("INSERT INTO products(sku,name,category,quantity,reorder_level,unit_cost,location,supplier,expiry_date,created_at,barcode,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(sku,name,category,int(qty),int(reorder),cost,loc,supplier,expiry,datetime.now().isoformat(),barcode,datetime.now().isoformat()))
                st.success("Product added");st.rerun()
            except Exception as e:st.error(str(e))
    with st.expander("Import CSV"):
        up=st.file_uploader("Inventory CSV",type="csv")
        if up and st.button("Import CSV"):
            try:
                incoming=pd.read_csv(up);required=["sku","name","category","quantity","reorder_level","unit_cost","location","supplier","expiry_date"]
                if not set(required).issubset(incoming.columns):raise ValueError("Missing columns: "+", ".join(required))
                with db() as con:
                    for _,r in incoming.iterrows():
                        con.execute("INSERT INTO products(sku,name,category,quantity,reorder_level,unit_cost,location,supplier,expiry_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(sku) DO UPDATE SET name=excluded.name,category=excluded.category,quantity=excluded.quantity,reorder_level=excluded.reorder_level,unit_cost=excluded.unit_cost,location=excluded.location,supplier=excluded.supplier,expiry_date=excluded.expiry_date,updated_at=excluded.updated_at",(str(r.sku),str(r['name']),str(r.category),int(r.quantity),int(r.reorder_level),float(r.unit_cost),str(r.location),str(r.supplier),str(r.expiry_date) if pd.notna(r.expiry_date) else "",datetime.now().isoformat(),datetime.now().isoformat()))
                st.success(f"Imported {len(incoming)} records");st.rerun()
            except Exception as e:st.error(str(e))
elif page=="Stock Movements":
    header("Stock movements","Record receipts and dispatches with a quantity audit trail.")
    with st.form("movement"):
        sku=st.selectbox("Product",df.sku.tolist(),format_func=lambda s:f"{s} · {df[df.sku==s].iloc[0]['name']}")
        kind=st.radio("Movement",["Stock In","Stock Out"],horizontal=True);qty=st.number_input("Quantity",min_value=1);ref=st.text_input("Reference / note");submit=st.form_submit_button("Confirm movement",type="primary")
    if submit:
        try:before,after=stock_change(sku,kind,int(qty),ref);st.success(f"Stock updated: {before} → {after}");st.rerun()
        except Exception as e:st.error(str(e))
    st.dataframe(movements(),use_container_width=True,hide_index=True)
elif page=="Warehouse Map":
    header("Warehouse map","Browse storage zones, shelves and product locations.")
    if df.empty:st.info("No products")
    else:
        df["aisle"]=df.location.fillna("").str.extract(r"(Aisle\s*[^/]+)",expand=False).fillna("Unassigned")
        for aisle,items in df.groupby("aisle"):
            with st.expander(f"{aisle} · {len(items)} SKUs · {int(items.quantity.sum())} units",expanded=True):
                st.dataframe(items[["sku","name","quantity","reorder_level","location"]],use_container_width=True,hide_index=True)
    q=st.text_input("Locate SKU, barcode or product")
    if q:
        m=df[df.apply(lambda r:q.lower() in str(r.sku).lower() or q.lower() in str(r['name']).lower() or q.lower() in str(r.barcode).lower(),axis=1)]
        st.dataframe(m[["sku","name","quantity","location"]],use_container_width=True,hide_index=True)
elif page=="Demand & Reorder":
    header("Demand & replenishment","Baseline sales forecast and suggested reorder quantities.")
    days=st.select_slider("Forecast horizon",options=[7,14,21,30],value=14)
    rows=[]
    for _,r in df.iterrows():
        avg,d=forecast(r.sku,days);target=max(int(r.reorder_level)*2,d);order=max(0,target-int(r.quantity))
        rows.append({"SKU":r.sku,"Product":r['name'],"On hand":r.quantity,"Avg daily sales":round(avg,2),"Forecast demand":d,"Suggested order":order,"Supplier":r.supplier,"Estimated cost":order*r.unit_cost})
    rec=pd.DataFrame(rows);st.dataframe(rec,use_container_width=True,hide_index=True)
    st.metric("Estimated reorder value",f"₹{rec['Estimated cost'].sum():,.2f}")
    if st.button("Create draft purchase orders",type="primary"):
        with db() as con:
            for _,r in rec[rec["Suggested order"]>0].iterrows():
                con.execute("INSERT INTO purchase_orders(created_at,supplier,sku,product_name,quantity,unit_cost,status,notes) VALUES(?,?,?,?,?,?,?,?)",(datetime.now().isoformat(),r.Supplier,r.SKU,r.Product,int(r["Suggested order"]),float(r["Estimated cost"])/int(r["Suggested order"]),"Draft",f"{days}-day forecast"))
        st.success("Draft purchase orders created");st.rerun()
elif page=="Purchase Orders":
    header("Purchase orders","Review draft orders and receive goods.")
    with db() as con:po=pd.read_sql_query("SELECT * FROM purchase_orders ORDER BY id DESC",con)
    st.dataframe(po,use_container_width=True,hide_index=True)
    if not po.empty:
        selected=st.selectbox("Select order line",po[po.status.isin(["Draft","Ordered"])].id.tolist())
        row=po[po.id==selected].iloc[0]
        a,b=st.columns(2)
        if row.status=="Draft" and a.button("Mark ordered"):
            with db() as con:con.execute("UPDATE purchase_orders SET status='Ordered' WHERE id=?",(int(selected),))
            st.rerun()
        if b.button("Receive into stock",type="primary"):
            try:stock_change(row.sku,"Stock In",int(row.quantity),f"Purchase order {selected}")
            except Exception as e:st.error(str(e))
            else:
                with db() as con:con.execute("UPDATE purchase_orders SET status='Received' WHERE id=?",(int(selected),))
                st.success("Goods received");st.rerun()
elif page=="Reports":
    header("Reports & activity","Export warehouse records and download a local database backup.")
    st.subheader("Inventory");st.dataframe(df,use_container_width=True,hide_index=True)
    st.download_button("Download inventory CSV",df.to_csv(index=False).encode("utf-8-sig"),"warewise_inventory.csv")
    st.subheader("Movement ledger");mv=movements();st.dataframe(mv,use_container_width=True,hide_index=True)
    st.download_button("Download movements CSV",mv.to_csv(index=False).encode("utf-8-sig"),"warewise_movements.csv")
    if DB.exists():st.download_button("Download SQLite database backup",DB.read_bytes(),"warewise_backup.db")
st.divider();st.caption("WareWise AI · Academic prototype · SQLite local storage · Forecasts are estimates.")

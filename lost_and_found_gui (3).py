"""
Lost And Found - Data Entry GUI
Pure Python (tkinter + sqlite3, both in the standard library).
Run:  python lost_and_found_gui.py
A database file called lost_and_found.db is created next to this script.
"""
import os
import re
import sqlite3
import tkinter as tk
from datetime import date
from tkinter import ttk, messagebox, filedialog

DB_FILE = "lost_and_found.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS Users (
    UserID   INTEGER PRIMARY KEY AUTOINCREMENT,
    Email    TEXT NOT NULL UNIQUE,
    Name     TEXT NOT NULL,
    Verified INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS Student (
    StudentID INTEGER PRIMARY KEY,
    FOREIGN KEY (StudentID) REFERENCES Users(UserID) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS Staff (
    StaffID    INTEGER PRIMARY KEY,
    Department TEXT NOT NULL,
    FOREIGN KEY (StaffID) REFERENCES Users(UserID) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS Category (
    CategoryID INTEGER PRIMARY KEY AUTOINCREMENT,
    Name       TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS Item (
    ItemID      INTEGER PRIMARY KEY AUTOINCREMENT,
    Title       TEXT NOT NULL,
    Place       TEXT NOT NULL,
    ItemDate    TEXT NOT NULL,
    Description TEXT,
    Status      TEXT NOT NULL DEFAULT 'Open'
                CHECK (Status IN ('Open','Claimed','Returned')),
    UserID      INTEGER NOT NULL,
    CategoryID  INTEGER NOT NULL,
    FOREIGN KEY (UserID)     REFERENCES Users(UserID),
    FOREIGN KEY (CategoryID) REFERENCES Category(CategoryID)
);
CREATE TABLE IF NOT EXISTS Lost_Item (
    ItemID        INTEGER PRIMARY KEY,
    RewardOffered REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (ItemID) REFERENCES Item(ItemID) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS Found_Item (
    ItemID          INTEGER PRIMARY KEY,
    StorageLocation TEXT NOT NULL,
    FOREIGN KEY (ItemID) REFERENCES Item(ItemID) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS Claim (
    ClaimID   INTEGER PRIMARY KEY AUTOINCREMENT,
    Proof     TEXT NOT NULL,
    Status    TEXT NOT NULL DEFAULT 'Pending'
              CHECK (Status IN ('Pending','Approved','Rejected')),
    ClaimDate TEXT NOT NULL,
    UserID    INTEGER NOT NULL,
    ItemID    INTEGER NOT NULL,
    FOREIGN KEY (UserID) REFERENCES Users(UserID),
    FOREIGN KEY (ItemID) REFERENCES Item(ItemID)
);
"""

DEFAULT_CATEGORIES = ["Electronics", "Wallets & Cards", "Keys", "Bags & Backpacks",
                      "Clothing", "Books & Stationery", "Jewelry & Accessories",
                      "Water Bottles"]


# ----------------------------------------------------------------- database
def connect():
    con = sqlite3.connect(DB_FILE)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    if con.execute("SELECT COUNT(*) FROM Category").fetchone()[0] == 0:
        con.executemany("INSERT INTO Category (Name) VALUES (?)",
                        [(c,) for c in DEFAULT_CATEGORIES])
    con.commit()
    return con


TABLE_ORDER = ["Users", "Student", "Staff", "Category", "Item",
               "Lost_Item", "Found_Item", "Claim"]


def import_sql_file(con, path):
    """Run only the INSERT statements of a .sql file (e.g. lost_and_found.sql).
    Existing rows with the same primary key are skipped. Returns {table: rows_added}."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    counts, buf = {}, ""
    with con:  # one transaction: all or nothing
        for line in lines:
            if not buf and (not line.strip() or line.lstrip().startswith("--")):
                continue
            buf += line + "\n"
            if sqlite3.complete_statement(buf):
                stmt, buf = buf.strip(), ""
                m = re.match(r"INSERT\s+INTO\s+`?(\w+)`?", stmt, re.I)
                if m:  # CREATE / USE / SELECT / UPDATE / DELETE lines are ignored
                    stmt = re.sub(r"^INSERT\s+INTO", "INSERT OR IGNORE INTO", stmt, count=1, flags=re.I)
                    cur = con.execute(stmt)
                    counts[m.group(1)] = counts.get(m.group(1), 0) + max(cur.rowcount, 0)
    return counts


def import_db_file(con, path):
    """Copy all rows from another SQLite .db file (same table layout)."""
    counts = {}
    con.commit()
    con.execute("ATTACH DATABASE ? AS src", (path,))
    try:
        with con:
            for t in TABLE_ORDER:
                exists = con.execute("SELECT 1 FROM src.sqlite_master WHERE name = ?", (t,)).fetchone()
                if exists:
                    cur = con.execute(f"INSERT OR IGNORE INTO main.{t} SELECT * FROM src.{t}")
                    counts[t] = max(cur.rowcount, 0)
    finally:
        con.commit()
        con.execute("DETACH DATABASE src")
    return counts


# --------------------------------------------------------------------- GUI
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Lost & Found - Data Entry")
        self.geometry("980x640")
        self.con = connect()

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self.tab_users = ttk.Frame(nb)
        self.tab_cats = ttk.Frame(nb)
        self.tab_items = ttk.Frame(nb)
        self.tab_claims = ttk.Frame(nb)
        nb.add(self.tab_users, text="  Users  ")
        nb.add(self.tab_cats, text="  Categories  ")
        nb.add(self.tab_items, text="  Items  ")
        nb.add(self.tab_claims, text="  Claims  ")

        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=0)
        file_menu.add_command(label="Reload lost_and_found.sql", command=self.reload_sql)
        file_menu.add_command(label="Import data from .sql file...", command=self.import_sql)
        file_menu.add_command(label="Import data from .db file...", command=self.import_db)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menu.add_cascade(label="File", menu=file_menu)
        self.config(menu=menu)

        self.build_users_tab()
        self.build_categories_tab()
        self.build_items_tab()
        self.build_claims_tab()
        self.refresh_all()
        self.after(200, self.auto_load_sql)

    # ----------------------------------------------------------- import
    def show_import_result(self, counts):
        self.refresh_all()
        lines = "\n".join(f"{t}: {n} new rows" for t, n in counts.items()) or "No rows found."
        messagebox.showinfo("Import finished", lines + "\n\n(Rows that already existed were skipped.)")

    def import_sql(self, path=None):
        path = path or filedialog.askopenfilename(
            title="Choose a .sql file", filetypes=[("SQL files", "*.sql"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.show_import_result(import_sql_file(self.con, path))
        except (sqlite3.Error, OSError, UnicodeDecodeError) as e:
            messagebox.showerror("Import failed", f"Nothing was imported.\n\n{e}")

    def import_db(self):
        path = filedialog.askopenfilename(
            title="Choose a .db file", filetypes=[("SQLite database", "*.db *.sqlite *.sqlite3"),
                                                  ("All files", "*.*")])
        if not path:
            return
        try:
            self.show_import_result(import_db_file(self.con, path))
        except sqlite3.Error as e:
            messagebox.showerror("Import failed", f"{e}")

    def find_sql_file(self):
        """Look for lost_and_found.sql next to this script, then in the current folder."""
        for folder in (os.path.dirname(os.path.abspath(__file__)), os.getcwd()):
            path = os.path.join(folder, "lost_and_found.sql")
            if os.path.exists(path):
                return path
        return None

    def auto_load_sql(self):
        """Once per database file: load the old records from lost_and_found.sql automatically.
        (Later runs do not re-add rows you deleted. Use File > Reload to load them again.)"""
        if self.con.execute("PRAGMA user_version").fetchone()[0] != 0:
            return
        path = self.find_sql_file()
        if not path:
            return
        try:
            counts = import_sql_file(self.con, path)
            self.con.execute("PRAGMA user_version = 1")
            self.con.commit()
        except (sqlite3.Error, OSError, UnicodeDecodeError) as e:
            return messagebox.showerror("Auto-load failed", f"Could not load lost_and_found.sql:\n\n{e}")
        self.refresh_all()
        total = sum(counts.values())
        if total:
            messagebox.showinfo("Old records loaded",
                                f"Loaded {total} records from lost_and_found.sql.")

    def reload_sql(self):
        path = self.find_sql_file()
        if not path:
            return messagebox.showwarning("Not found", "lost_and_found.sql was not found next to the script.")
        self.import_sql(path)

    # ---------------------------------------------------------- helpers
    def make_table(self, parent, columns, widths):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=10)
        for c, w in zip(columns, widths):
            tree.heading(c, text=c)
            tree.column(c, width=w, anchor="w")
        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return tree

    def fill_table(self, tree, query):
        tree.delete(*tree.get_children())
        for row in self.con.execute(query):
            tree.insert("", "end", values=row)

    def run(self, sql, params=()):
        """Execute a write statement; show friendly errors. Returns True on success."""
        try:
            with self.con:
                self.con.execute(sql, params)
            return True
        except sqlite3.IntegrityError as e:
            messagebox.showerror("Database error", f"Could not save:\n{e}")
        return False

    def combo_values(self, query):
        return [f"{r[0]} - {r[1]}" for r in self.con.execute(query)]

    @staticmethod
    def combo_id(text):
        return int(text.split(" - ")[0]) if text else None

    @staticmethod
    def valid_date(text):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return False
        try:
            date.fromisoformat(text)
            return True
        except ValueError:
            return False

    def delete_selected(self, tree, table, id_col):
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("Delete", "Select a row first.")
            return
        rid = tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Confirm", f"Delete {table} #{rid}?"):
            if self.run(f"DELETE FROM {table} WHERE {id_col} = ?", (rid,)):
                self.refresh_all()

    # ------------------------------------------------------------ users
    def build_users_tab(self):
        f = ttk.LabelFrame(self.tab_users, text="Add user")
        f.pack(fill="x", padx=8, pady=8)

        self.u_name = tk.StringVar()
        self.u_email = tk.StringVar()
        self.u_verified = tk.IntVar()
        self.u_type = tk.StringVar(value="Student")
        self.u_dept = tk.StringVar()

        ttk.Label(f, text="Name").grid(row=0, column=0, sticky="e", padx=5, pady=4)
        ttk.Entry(f, textvariable=self.u_name, width=30).grid(row=0, column=1, padx=5)
        ttk.Label(f, text="Email").grid(row=0, column=2, sticky="e", padx=5)
        ttk.Entry(f, textvariable=self.u_email, width=30).grid(row=0, column=3, padx=5)

        ttk.Label(f, text="Type").grid(row=1, column=0, sticky="e", padx=5, pady=4)
        cb = ttk.Combobox(f, textvariable=self.u_type, state="readonly",
                          values=["Student", "Staff Member"], width=27)
        cb.grid(row=1, column=1, padx=5)
        cb.bind("<<ComboboxSelected>>", self.toggle_dept)
        ttk.Label(f, text="Department").grid(row=1, column=2, sticky="e", padx=5)
        self.dept_entry = ttk.Entry(f, textvariable=self.u_dept, width=30, state="disabled")
        self.dept_entry.grid(row=1, column=3, padx=5)

        ttk.Checkbutton(f, text="Verified", variable=self.u_verified).grid(
            row=2, column=1, sticky="w", padx=5, pady=4)
        ttk.Button(f, text="Add User", command=self.add_user).grid(
            row=2, column=3, sticky="e", padx=5, pady=6)

        self.users_tree = self.make_table(
            self.tab_users, ("UserID", "Name", "Email", "Verified", "Type", "Department"),
            (60, 180, 240, 70, 110, 180))
        ttk.Button(self.tab_users, text="Delete selected",
                   command=lambda: self.delete_selected(self.users_tree, "Users", "UserID")
                   ).pack(anchor="e", padx=8, pady=(0, 8))

    def toggle_dept(self, _=None):
        staff = self.u_type.get() == "Staff Member"
        self.dept_entry.configure(state="normal" if staff else "disabled")
        if not staff:
            self.u_dept.set("")

    def add_user(self):
        name, email = self.u_name.get().strip(), self.u_email.get().strip()
        staff = self.u_type.get() == "Staff Member"
        dept = self.u_dept.get().strip()
        if not name or not email:
            return messagebox.showwarning("Missing data", "Name and email are required.")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return messagebox.showwarning("Invalid email", "Please enter a valid email.")
        if staff and not dept:
            return messagebox.showwarning("Missing data", "Department is required for staff.")
        try:
            with self.con:  # one transaction: Users row + specialization row
                cur = self.con.execute(
                    "INSERT INTO Users (Email, Name, Verified) VALUES (?, ?, ?)",
                    (email, name, self.u_verified.get()))
                uid = cur.lastrowid
                if staff:
                    self.con.execute("INSERT INTO Staff (StaffID, Department) VALUES (?, ?)",
                                     (uid, dept))
                else:
                    self.con.execute("INSERT INTO Student (StudentID) VALUES (?)", (uid,))
        except sqlite3.IntegrityError as e:
            return messagebox.showerror("Database error", f"Could not save:\n{e}")
        self.u_name.set(""); self.u_email.set(""); self.u_dept.set(""); self.u_verified.set(0)
        self.refresh_all()
        messagebox.showinfo("Saved", f"User #{uid} added.")

    # ------------------------------------------------------- categories
    def build_categories_tab(self):
        f = ttk.LabelFrame(self.tab_cats, text="Add category")
        f.pack(fill="x", padx=8, pady=8)
        self.c_name = tk.StringVar()
        ttk.Label(f, text="Name").grid(row=0, column=0, padx=5, pady=6)
        ttk.Entry(f, textvariable=self.c_name, width=35).grid(row=0, column=1, padx=5)
        ttk.Button(f, text="Add Category", command=self.add_category).grid(row=0, column=2, padx=5)

        self.cats_tree = self.make_table(self.tab_cats, ("CategoryID", "Name"), (90, 300))
        ttk.Button(self.tab_cats, text="Delete selected",
                   command=lambda: self.delete_selected(self.cats_tree, "Category", "CategoryID")
                   ).pack(anchor="e", padx=8, pady=(0, 8))

    def add_category(self):
        name = self.c_name.get().strip()
        if not name:
            return messagebox.showwarning("Missing data", "Category name is required.")
        if self.run("INSERT INTO Category (Name) VALUES (?)", (name,)):
            self.c_name.set("")
            self.refresh_all()

    # ------------------------------------------------------------ items
    def build_items_tab(self):
        f = ttk.LabelFrame(self.tab_items, text="Post item")
        f.pack(fill="x", padx=8, pady=8)

        self.i_kind = tk.StringVar(value="Lost")
        self.i_title = tk.StringVar()
        self.i_place = tk.StringVar()
        self.i_date = tk.StringVar(value=date.today().isoformat())
        self.i_status = tk.StringVar(value="Open")
        self.i_user = tk.StringVar()
        self.i_cat = tk.StringVar()
        self.i_extra = tk.StringVar()

        ttk.Label(f, text="Kind").grid(row=0, column=0, sticky="e", padx=5, pady=4)
        kind = ttk.Combobox(f, textvariable=self.i_kind, state="readonly",
                            values=["Lost", "Found"], width=27)
        kind.grid(row=0, column=1, padx=5)
        kind.bind("<<ComboboxSelected>>", self.update_extra_label)
        ttk.Label(f, text="Title").grid(row=0, column=2, sticky="e", padx=5)
        ttk.Entry(f, textvariable=self.i_title, width=30).grid(row=0, column=3, padx=5)

        ttk.Label(f, text="Place").grid(row=1, column=0, sticky="e", padx=5, pady=4)
        ttk.Entry(f, textvariable=self.i_place, width=30).grid(row=1, column=1, padx=5)
        ttk.Label(f, text="Date (YYYY-MM-DD)").grid(row=1, column=2, sticky="e", padx=5)
        ttk.Entry(f, textvariable=self.i_date, width=30).grid(row=1, column=3, padx=5)

        ttk.Label(f, text="Posted by").grid(row=2, column=0, sticky="e", padx=5, pady=4)
        self.i_user_cb = ttk.Combobox(f, textvariable=self.i_user, state="readonly", width=27)
        self.i_user_cb.grid(row=2, column=1, padx=5)
        ttk.Label(f, text="Category").grid(row=2, column=2, sticky="e", padx=5)
        self.i_cat_cb = ttk.Combobox(f, textvariable=self.i_cat, state="readonly", width=27)
        self.i_cat_cb.grid(row=2, column=3, padx=5)

        ttk.Label(f, text="Status").grid(row=3, column=0, sticky="e", padx=5, pady=4)
        ttk.Combobox(f, textvariable=self.i_status, state="readonly",
                     values=["Open", "Claimed", "Returned"], width=27
                     ).grid(row=3, column=1, padx=5)
        self.extra_label = ttk.Label(f, text="Reward offered")
        self.extra_label.grid(row=3, column=2, sticky="e", padx=5)
        ttk.Entry(f, textvariable=self.i_extra, width=30).grid(row=3, column=3, padx=5)

        ttk.Label(f, text="Description").grid(row=4, column=0, sticky="ne", padx=5, pady=4)
        self.i_desc = tk.Text(f, width=60, height=3)
        self.i_desc.grid(row=4, column=1, columnspan=3, sticky="w", padx=5)
        ttk.Button(f, text="Add Item", command=self.add_item).grid(
            row=5, column=3, sticky="e", padx=5, pady=6)

        self.items_tree = self.make_table(
            self.tab_items,
            ("ItemID", "Kind", "Title", "Place", "Date", "Status", "Posted by",
             "Category", "Reward / Storage"),
            (55, 55, 130, 130, 85, 70, 120, 120, 130))
        ttk.Button(self.tab_items, text="Delete selected",
                   command=lambda: self.delete_selected(self.items_tree, "Item", "ItemID")
                   ).pack(anchor="e", padx=8, pady=(0, 8))

    def update_extra_label(self, _=None):
        self.extra_label.configure(
            text="Reward offered" if self.i_kind.get() == "Lost" else "Storage location")
        self.i_extra.set("")

    def add_item(self):
        title, place = self.i_title.get().strip(), self.i_place.get().strip()
        d = self.i_date.get().strip()
        lost = self.i_kind.get() == "Lost"
        extra = self.i_extra.get().strip()
        if not title or not place:
            return messagebox.showwarning("Missing data", "Title and place are required.")
        if not self.valid_date(d):
            return messagebox.showwarning("Invalid date", "Use the format YYYY-MM-DD.")
        if not self.i_user.get() or not self.i_cat.get():
            return messagebox.showwarning("Missing data", "Choose a user and a category.")
        if lost:
            try:
                reward = float(extra) if extra else 0.0
                if reward < 0:
                    raise ValueError
            except ValueError:
                return messagebox.showwarning("Invalid reward", "Reward must be a number >= 0.")
        elif not extra:
            return messagebox.showwarning("Missing data", "Storage location is required for found items.")
        try:
            with self.con:
                cur = self.con.execute(
                    "INSERT INTO Item (Title, Place, ItemDate, Description, Status, UserID, CategoryID) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (title, place, d, self.i_desc.get("1.0", "end").strip(), self.i_status.get(),
                     self.combo_id(self.i_user.get()), self.combo_id(self.i_cat.get())))
                iid = cur.lastrowid
                if lost:
                    self.con.execute("INSERT INTO Lost_Item (ItemID, RewardOffered) VALUES (?, ?)",
                                     (iid, reward))
                else:
                    self.con.execute("INSERT INTO Found_Item (ItemID, StorageLocation) VALUES (?, ?)",
                                     (iid, extra))
        except sqlite3.IntegrityError as e:
            return messagebox.showerror("Database error", f"Could not save:\n{e}")
        self.i_title.set(""); self.i_place.set(""); self.i_extra.set("")
        self.i_desc.delete("1.0", "end")
        self.refresh_all()
        messagebox.showinfo("Saved", f"Item #{iid} added.")

    # ----------------------------------------------------------- claims
    def build_claims_tab(self):
        f = ttk.LabelFrame(self.tab_claims, text="Submit claim")
        f.pack(fill="x", padx=8, pady=8)

        self.cl_user = tk.StringVar()
        self.cl_item = tk.StringVar()
        self.cl_proof = tk.StringVar()
        self.cl_status = tk.StringVar(value="Pending")
        self.cl_date = tk.StringVar(value=date.today().isoformat())

        ttk.Label(f, text="Claimant").grid(row=0, column=0, sticky="e", padx=5, pady=4)
        self.cl_user_cb = ttk.Combobox(f, textvariable=self.cl_user, state="readonly", width=32)
        self.cl_user_cb.grid(row=0, column=1, padx=5)
        ttk.Label(f, text="Item").grid(row=0, column=2, sticky="e", padx=5)
        self.cl_item_cb = ttk.Combobox(f, textvariable=self.cl_item, state="readonly", width=32)
        self.cl_item_cb.grid(row=0, column=3, padx=5)

        ttk.Label(f, text="Proof").grid(row=1, column=0, sticky="e", padx=5, pady=4)
        ttk.Entry(f, textvariable=self.cl_proof, width=35).grid(row=1, column=1, padx=5)
        ttk.Label(f, text="Claim date").grid(row=1, column=2, sticky="e", padx=5)
        ttk.Entry(f, textvariable=self.cl_date, width=35).grid(row=1, column=3, padx=5)

        ttk.Label(f, text="Status").grid(row=2, column=0, sticky="e", padx=5, pady=4)
        ttk.Combobox(f, textvariable=self.cl_status, state="readonly",
                     values=["Pending", "Approved", "Rejected"], width=32
                     ).grid(row=2, column=1, padx=5)
        ttk.Button(f, text="Add Claim", command=self.add_claim).grid(
            row=2, column=3, sticky="e", padx=5, pady=6)

        self.claims_tree = self.make_table(
            self.tab_claims, ("ClaimID", "Claimant", "Item", "Proof", "Status", "Date"),
            (60, 150, 170, 270, 80, 90))
        bar = ttk.Frame(self.tab_claims)
        bar.pack(anchor="e", padx=8, pady=(0, 8))
        for text, status in (("Approve selected", "Approved"), ("Reject selected", "Rejected")):
            ttk.Button(bar, text=text,
                       command=lambda s=status: self.set_claim_status(s)).pack(side="left", padx=3)
        ttk.Button(bar, text="Delete selected",
                   command=lambda: self.delete_selected(self.claims_tree, "Claim", "ClaimID")
                   ).pack(side="left", padx=3)

    def add_claim(self):
        d = self.cl_date.get().strip()
        proof = self.cl_proof.get().strip()
        if not self.cl_user.get() or not self.cl_item.get():
            return messagebox.showwarning("Missing data", "Choose a claimant and an item.")
        if not proof:
            return messagebox.showwarning("Missing data", "Proof is required.")
        if not self.valid_date(d):
            return messagebox.showwarning("Invalid date", "Use the format YYYY-MM-DD.")
        uid, iid = self.combo_id(self.cl_user.get()), self.combo_id(self.cl_item.get())
        owner = self.con.execute("SELECT UserID FROM Item WHERE ItemID = ?", (iid,)).fetchone()[0]
        if owner == uid:
            return messagebox.showwarning("Not allowed", "A user cannot claim their own posted item.")
        if self.run("INSERT INTO Claim (Proof, Status, ClaimDate, UserID, ItemID) VALUES (?, ?, ?, ?, ?)",
                    (proof, self.cl_status.get(), d, uid, iid)):
            self.cl_proof.set("")
            self.refresh_all()
            messagebox.showinfo("Saved", "Claim added.")

    def set_claim_status(self, status):
        sel = self.claims_tree.selection()
        if not sel:
            return messagebox.showinfo("Claim", "Select a claim first.")
        cid = self.claims_tree.item(sel[0])["values"][0]
        if self.run("UPDATE Claim SET Status = ? WHERE ClaimID = ?", (status, cid)):
            self.refresh_all()

    # ---------------------------------------------------------- refresh
    def refresh_all(self):
        self.fill_table(self.users_tree, """
            SELECT u.UserID, u.Name, u.Email,
                   CASE u.Verified WHEN 1 THEN 'Yes' ELSE 'No' END,
                   CASE WHEN st.StaffID IS NOT NULL THEN 'Staff Member' ELSE 'Student' END,
                   COALESCE(st.Department, '')
            FROM Users u LEFT JOIN Staff st ON st.StaffID = u.UserID
            ORDER BY u.UserID""")
        self.fill_table(self.cats_tree, "SELECT CategoryID, Name FROM Category ORDER BY CategoryID")
        self.fill_table(self.items_tree, """
            SELECT i.ItemID,
                   CASE WHEN l.ItemID IS NOT NULL THEN 'Lost' ELSE 'Found' END,
                   i.Title, i.Place, i.ItemDate, i.Status, u.Name, c.Name,
                   CASE WHEN l.ItemID IS NOT NULL THEN l.RewardOffered ELSE f.StorageLocation END
            FROM Item i
            JOIN Users u ON u.UserID = i.UserID
            JOIN Category c ON c.CategoryID = i.CategoryID
            LEFT JOIN Lost_Item l ON l.ItemID = i.ItemID
            LEFT JOIN Found_Item f ON f.ItemID = i.ItemID
            ORDER BY i.ItemID""")
        self.fill_table(self.claims_tree, """
            SELECT cl.ClaimID, u.Name, i.Title, cl.Proof, cl.Status, cl.ClaimDate
            FROM Claim cl
            JOIN Users u ON u.UserID = cl.UserID
            JOIN Item i ON i.ItemID = cl.ItemID
            ORDER BY cl.ClaimID""")

        users = self.combo_values("SELECT UserID, Name FROM Users ORDER BY Name")
        self.i_user_cb["values"] = users
        self.cl_user_cb["values"] = users
        self.i_cat_cb["values"] = self.combo_values("SELECT CategoryID, Name FROM Category ORDER BY Name")
        self.cl_item_cb["values"] = self.combo_values("SELECT ItemID, Title FROM Item ORDER BY ItemID")


if __name__ == "__main__":
    App().mainloop()

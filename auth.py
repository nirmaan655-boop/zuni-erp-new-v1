"""Auth helpers for Zuni ERP — login gate + role-based page guard."""
import streamlit as st
from db import verify_user, role_can_access, query, execute, hash_password


# ---------------- Sidebar CSS (injected on every page) ----------------
_SIDEBAR_CSS = """
<style>
/* Dark sidebar background */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #2C3E50 0%, #34495E 100%) !important;
    border-right: 1px solid #1F2D3D;
}
/* Hide Streamlit's default flat page navigation (all variants across versions) */
[data-testid="stSidebarNav"],
[data-testid="stSidebarNavItems"],
[data-testid="stSidebarNavSeparator"],
[data-testid="stSidebarNavLink"],
section[data-testid="stSidebar"] > div > div > ul:first-of-type,
[data-testid="stSidebar"] nav { display: none !important; visibility: hidden !important; height: 0 !important; }

/* All sidebar text white */
[data-testid="stSidebar"], [data-testid="stSidebar"] *,
[data-testid="stSidebar"] p, [data-testid="stSidebar"] span,
[data-testid="stSidebar"] a, [data-testid="stSidebar"] div,
[data-testid="stSidebar"] label, [data-testid="stSidebar"] li,
[data-testid="stSidebar"] strong, [data-testid="stSidebar"] em,
[data-testid="stSidebar"] small, [data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3,
[data-testid="stSidebar"] h4 {
    color: #FFFFFF !important;
}
[data-testid="stSidebar"] svg { fill: #FFFFFF !important; color: #FFFFFF !important; }
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.20) !important; margin: 12px 0 !important; }
[data-testid="stSidebarCollapseButton"] svg,
[data-testid="stSidebarCollapsedControl"] svg { color: #FFFFFF !important; }

/* Grouped nav: expanders */
[data-testid="stSidebar"] [data-testid="stExpander"] {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    border-radius: 8px !important;
    margin-bottom: 8px !important;
    box-shadow: none !important;
    overflow: hidden;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary,
[data-testid="stSidebar"] [data-testid="stExpander"] details > summary {
    background: rgba(26,188,156,0.12) !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
    font-size: 12.5px !important;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    padding: 10px 12px !important;
    border-left: 3px solid #1ABC9C !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {
    background: rgba(26,188,156,0.22) !important;
}

/* Page link items inside grouped nav */
[data-testid="stSidebar"] [data-testid="stPageLink"] a,
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {
    background: transparent !important;
    color: #ECF0F1 !important;
    font-weight: 500 !important;
    font-size: 13.5px !important;
    padding: 7px 10px !important;
    border-radius: 6px !important;
    margin: 1px 4px !important;
    text-decoration: none !important;
    transition: all 0.15s ease;
    border-left: 2px solid transparent;
}
[data-testid="stSidebar"] [data-testid="stPageLink"] a *,
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] * {
    color: #ECF0F1 !important;
}
[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover,
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover {
    background: rgba(26,188,156,0.22) !important;
    border-left: 2px solid #1ABC9C !important;
    padding-left: 12px !important;
}
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"],
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][aria-current="page"] {
    background: linear-gradient(90deg, rgba(26,188,156,0.32) 0%, rgba(26,188,156,0.05) 100%) !important;
    border-left: 3px solid #1ABC9C !important;
    color: #FFFFFF !important;
    font-weight: 600 !important;
}

/* Sidebar buttons */
[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,255,255,0.10) !important;
    border: 1px solid rgba(255,255,255,0.30) !important;
    color: #FFFFFF !important;
    font-weight: 600 !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(26,188,156,0.25) !important;
    border-color: #1ABC9C !important;
    color: #FFFFFF !important;
}
</style>
"""


def inject_sidebar_css():
    """Inject sidebar CSS — call from any page or login form."""
    st.markdown(_SIDEBAR_CSS, unsafe_allow_html=True)


# ---------------- Sidebar navigation groups ----------------
# Each entry: (page_path, page_key_for_role_check, label, icon)
NAV_GROUPS = [
    ("🐄 Livestock", [
        ("pages/1_Livestock.py",     "1_Livestock",     "Animals",       "🐄"),
        ("pages/2_RFID.py",          "2_RFID",          "RFID Tags",     "📡"),
        ("pages/5_Pens.py",          "5_Pens",          "Pens",          "🏠"),
        ("pages/6_Weights.py",       "6_Weights",       "Weights",       "⚖️"),
        ("pages/4_Calving.py",       "4_Calving",       "Calving",       "🐂"),
        ("pages/15_Breeding.py",     "15_Breeding",     "Breeding",      "💞"),
        ("pages/17_Vaccinations.py", "17_Vaccinations", "Vaccinations",  "💉"),
        ("pages/8_Treatments.py",    "8_Treatments",    "Treatments",    "🩺"),
    ]),
    ("🥛 Operations", [
        ("pages/3_Milk.py",          "3_Milk",          "Milk",          "🥛"),
        ("pages/7_Feed.py",          "7_Feed",          "Feed",          "🌾"),
        ("pages/9_Inventory.py",     "9_Inventory",     "Inventory",     "📦"),
    ]),
    ("💰 Accounts & Sales", [
        ("pages/10_Sales_Purchase.py", "10_Sales_Purchase", "Sales / Purchase", "🛒"),
        ("pages/11_Accounting.py",     "11_Accounting",     "Accounting",       "📒"),
        ("pages/14_Animal_PL.py",      "14_Animal_PL",      "Animal P&L",       "💹"),
    ]),
    ("👥 HR", [
        ("pages/12_Employees.py",    "12_Employees",    "Employees",     "👷"),
        ("pages/16_Users.py",        "16_Users",        "Users",         "👤"),
    ]),
    ("📈 Reports & Admin", [
        ("pages/13_Reports.py",      "13_Reports",      "Reports",       "📊"),
        ("pages/18_Admin_Edit.py",   "18_Admin_Edit",   "Admin Edit Log","🛠️"),
    ]),
]


def _login_form():
    inject_sidebar_css()
    st.markdown(
        "<div style='max-width:420px;margin:60px auto 20px auto;"
        "background:#FFFFFF;padding:30px;border-radius:8px;"
        "box-shadow:0 2px 12px rgba(0,0,0,0.08);border:1px solid #E1E5EB;'>"
        "<h1 style='color:#2C3E50;text-align:center;margin:0;font-size:28px;"
        "border:none;padding:0;'>Zuni Dairy ERP</h1>"
        "<p style='color:#7B8A9C;text-align:center;margin-top:6px;'>"
        "Login to continue</p></div>",
        unsafe_allow_html=True,
    )
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        ok = st.form_submit_button("Login", type="primary", use_container_width=True)
    if ok:
        user = verify_user(u.strip(), p)
        if user:
            st.session_state["user"] = dict(user)
            st.rerun()
        else:
            st.error("Invalid username or password.")
    with st.expander("Default test logins"):
        st.markdown(
            "- **admin / admin123** — full access (all modules)\n"
            "- **vet / vet123** — Animals, Pens, Calving, Weights, Treatments, Breeding, RFID\n"
            "- **account / account123** — Milk, Feed, Inventory, Sales/Purchase, "
            "Accounting, Employees, Reports, Animal P&L"
        )


def require_login():
    """Call at the top of every page. Returns the user dict."""
    if "user" not in st.session_state:
        _login_form()
        st.stop()
    return st.session_state["user"]


def require_role(page_key: str):
    """Page-level guard: shows access denied if role lacks permission."""
    user = require_login()
    if not role_can_access(user["role"], page_key):
        st.error(f"Access denied — your role ({user['role']}) cannot view this page.")
        st.info("Contact Admin to request access.")
        st.stop()
    return user


def _render_grouped_nav(role: str):
    """Render grouped navigation links in the sidebar, filtered by role."""
    st.markdown(
        "<div style='color:#FFFFFF;font-weight:700;font-size:12px;"
        "letter-spacing:1px;text-transform:uppercase;margin:4px 0 8px 0;"
        "opacity:0.7;'>NAVIGATION</div>",
        unsafe_allow_html=True,
    )
    # Home / Dashboard link
    try:
        st.page_link("app.py", label="Dashboard", icon="🏠")
    except Exception:
        pass

    for group_label, items in NAV_GROUPS:
        # Filter items by role permission
        visible = [it for it in items if role_can_access(role, it[1])]
        if not visible:
            continue
        with st.expander(group_label, expanded=True):
            for page_path, _key, label, icon in visible:
                try:
                    st.page_link(page_path, label=label, icon=icon)
                except Exception:
                    pass


def render_user_sidebar():
    """Show current user + grouped navigation + logout in sidebar."""
    # Always inject sidebar CSS (hides default flat nav, applies dark theme)
    # Required on every authenticated page since direct URL loads / hard refreshes
    # do NOT execute app.py's CSS block.
    inject_sidebar_css()

    user = st.session_state.get("user")
    if not user:
        return
    role = user.get("role", "")
    display_name = user.get("full_name") or user.get("username", "User")
    with st.sidebar:
        st.markdown(
            f"<div style='padding:12px;background:rgba(255,255,255,0.08);"
            f"border-radius:6px;border-left:3px solid #26C6DA;margin-bottom:10px;'>"
            f"<b style='color:#FFFFFF;font-size:14px;'>"
            f"{display_name}</b><br>"
            f"<span style='color:#BDC3C7;font-size:12px;'>Role: {role or '—'}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        _render_grouped_nav(role)
        st.markdown("---")
        if st.button("Logout", use_container_width=True):
            st.session_state.pop("user", None)
            st.rerun()

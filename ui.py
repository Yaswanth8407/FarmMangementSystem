import csv
import threading
from tkinter import filedialog
from datetime import date, datetime

import customtkinter as ctk

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import weather as weatherModule
import ai_engine as aiModule
import db

db.init_db()

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("green")

app = ctk.CTk()
app.title("Farm Management System")
app.geometry("1250x750")
app.minsize(1120, 680)

BG = "#F2F5F1"
BG_CARD = "#FFFFFF"
SIDEBAR = "#12231A"
SIDEBAR_DIM = "#1B3125"
PRIMARY = "#2E7D32"
PRIMARY_DARK = "#1B5E20"
ACCENT = "#66BB6A"
TEXT = "#1F2A24"
SUBTEXT = "#728072"
DANGER = "#C62828"
DANGER_HOVER = "#8E0000"
WARN = "#E8A00C"
WARN_BG = "#FDF3DC"
INFO_BG = "#E7F0E9"
BLUE = "#1E88E5"
BORDER = "#E3EAE3"
FONT = "Segoe UI"

menu_items = ["Dashboard", "Weather", "AI Assistant", "Crops", "Inventory", "Sales", "Expenses"]

MENU_ICONS = {
    "Dashboard": "◈",
    "Weather": "☁",
    "AI Assistant": "🤖",
    "Crops": "🌱",
    "Inventory": "📦",
    "Sales": "💰",
    "Expenses": "🧾",
    "Charts": "📈",
}

STAT_ICONS = {
    "Active Crops": "🌾",
    "Inventory": "📦",
    "Sales": "💵",
    "Expenses": "💸",
    "Net Profit": "📈",
}

STATUS_STYLES = {
    "Planted": ("● Planted", PRIMARY, INFO_BG),
    "Growing": ("● Growing", ACCENT, INFO_BG),
    "Ready": ("● Ready", WARN, WARN_BG),
    "Harvested": ("● Harvested", BLUE, "#E3F2FD"),
}

SALES_SORTS = ["Newest first", "Oldest first", "Highest amount", "Lowest amount", "Crop A-Z"]
EXPENSE_SORTS = ["Newest first", "Oldest first", "Highest amount", "Lowest amount", "Category A-Z"]

PIE_COLORS = [
    "#2E7D32", "#66BB6A", "#1E88E5", "#E8A00C", "#C62828",
    "#8E24AA", "#00897B", "#F4511E", "#5C6BC0", "#9E9D24",
]


def clear_window():
    for widget in app.winfo_children():
        widget.destroy()


def make_page_header(page, title, subtitle=None):
    head = ctk.CTkFrame(page, fg_color="transparent")
    head.pack(fill="x", pady=(0, 18))
    title_col = ctk.CTkFrame(head, fg_color="transparent")
    title_col.pack(side="left")
    ctk.CTkLabel(
        title_col, text=title, font=(FONT, 26, "bold"), text_color=TEXT,
        anchor="w"
    ).pack(anchor="w")
    if subtitle:
        ctk.CTkLabel(
            title_col, text=subtitle, font=(FONT, 12), text_color=SUBTEXT,
            anchor="w"
        ).pack(anchor="w", pady=(2, 0))


def make_form_card(page):
    form = ctk.CTkFrame(page, fg_color=BG_CARD, corner_radius=14)
    form.pack(fill="x", pady=(0, 16))
    return form


def make_list_area(page):
    list_frame = ctk.CTkScrollableFrame(
        page, fg_color="transparent", corner_radius=0
    )
    list_frame.pack(fill="both", expand=True)
    return list_frame


def make_badge(parent, text, fg=PRIMARY, bg=INFO_BG):
    badge = ctk.CTkFrame(parent, fg_color=bg, corner_radius=20)
    ctk.CTkLabel(
        badge, text=text, font=(FONT, 12, "bold"), text_color=fg
    ).pack(padx=12, pady=3)
    return badge


def badge_for_status(status):
    if status in STATUS_STYLES:
        return STATUS_STYLES[status]
    return (status.title() if status else "—", PRIMARY, INFO_BG)


def make_row_actions(row, edit_command, delete_command, column, rowspan=1, padx=(0, 12),
                     extra_buttons=None):
    box = ctk.CTkFrame(row, fg_color="transparent")
    box.grid(row=0, column=column, rowspan=rowspan, padx=padx, pady=8, sticky="e")
    for spec in (extra_buttons or []):
        ctk.CTkButton(
            box, text=spec["text"], width=34, height=30, corner_radius=8,
            fg_color=spec.get("fg", "#E7F0E9"), hover_color=spec.get("hover", "#CFE3D4"),
            text_color=spec.get("color", PRIMARY), font=(FONT, 13, "bold"),
            command=spec["command"]
        ).pack(side="left", padx=(0, 6))
    ctk.CTkButton(
        box, text="✎", width=34, height=30, corner_radius=8,
        fg_color="#E7F0E9", hover_color="#CFE3D4", text_color=PRIMARY,
        font=(FONT, 14, "bold"), command=edit_command
    ).pack(side="left", padx=(0, 6))
    ctk.CTkButton(
        box, text="✕", width=34, height=30, corner_radius=8,
        fg_color="#FBE9E7", hover_color="#FFCDD2", text_color=DANGER,
        font=(FONT, 14, "bold"), command=delete_command
    ).pack(side="left")
    return box


def make_table_header(parent, columns):
    header = ctk.CTkFrame(parent, fg_color="transparent")
    header.pack(fill="x", padx=4)
    for col, (text, width) in enumerate(columns):
        ctk.CTkLabel(
            header, text=text, font=(FONT, 11, "bold"), text_color=SUBTEXT,
            anchor="w", width=width
        ).grid(row=0, column=col, padx=(8, 8), sticky="w")
    return header


def harvest_label(date_str):
    days = db.days_until(date_str)
    if days is None:
        return "—"
    if days < 0:
        return f"Overdue {abs(days)}d"
    if days == 0:
        return "Today"
    return f"{days}d left"


def build_inline_form(form, fields):
    """Add form. Fields default to a single row and support kind 'entry'/'menu'."""
    widgets = {}
    for index, field in enumerate(fields):
        kind = field.get("kind", "entry")
        if kind == "menu":
            values = list(field["values"]) or [""]
            var = ctk.StringVar(value=str(field.get("value") or values[0]))
            widget = ctk.CTkOptionMenu(
                form, values=values, variable=var, width=field.get("width", 150),
                height=38, corner_radius=8, fg_color=PRIMARY,
                button_color=PRIMARY_DARK, font=(FONT, 13),
                dropdown_font=(FONT, 13)
            )
        else:
            widget = ctk.CTkEntry(
                form, placeholder_text=field.get("placeholder", ""),
                width=field.get("width", 160), height=38,
                border_color="#CBD8CB", corner_radius=8
            )
            if field.get("value"):
                widget.insert(0, str(field["value"]))
            widget._default = field.get("value")
        widget.grid(
            row=field.get("row", 0), column=field.get("col", index),
            padx=(8, 8), pady=(14, 4), sticky="w"
        )
        widgets[field["key"]] = widget
    return widgets


def add_form_button(form, text, command, column, color=PRIMARY, hover=PRIMARY_DARK,
                    width=120, row=0):
    ctk.CTkButton(
        form, text=text, width=width, height=38, corner_radius=9,
        fg_color=color, hover_color=hover, font=(FONT, 13, "bold"),
        command=command
    ).grid(row=row, column=column, padx=(12, 16), pady=(14, 4), sticky="w")


def reset_inline_form(widgets):
    for widget in widgets.values():
        if isinstance(widget, ctk.CTkOptionMenu):
            continue
        widget.delete(0, "end")
        default = getattr(widget, "_default", None)
        if default:
            widget.insert(0, str(default))


def bind_form_enter(widgets, handler):
    for widget in widgets.values():
        widget.bind("<Return>", lambda e: handler())


def open_form_dialog(title, fields, on_save, save_text="Save changes", width=470):
    """Modal CTkToplevel with labelled fields; `fields` support entry/menu."""
    dialog = ctk.CTkToplevel(app)
    dialog.title(title)
    dialog.configure(fg_color=BG)
    dialog.resizable(False, False)
    dialog.transient(app)

    height = 170 + len(fields) * 68
    dialog.update_idletasks()
    x = app.winfo_rootx() + max((app.winfo_width() - width) // 2, 0)
    y = app.winfo_rooty() + max((app.winfo_height() - height) // 2, 0)
    dialog.geometry(f"{width}x{height}+{x}+{y}")

    ctk.CTkLabel(
        dialog, text=title, font=(FONT, 18, "bold"), text_color=TEXT
    ).pack(anchor="w", padx=24, pady=(20, 4))

    body = ctk.CTkFrame(dialog, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=24, pady=(6, 0))

    widgets = {}
    for field in fields:
        ctk.CTkLabel(
            body, text=field["label"], font=(FONT, 12, "bold"),
            text_color=SUBTEXT, anchor="w"
        ).pack(fill="x", pady=(8, 2))

        kind = field.get("kind", "entry")
        if kind == "menu":
            values = list(field["values"]) or [""]
            var = ctk.StringVar(value=str(field.get("value") or values[0]))
            widget = ctk.CTkOptionMenu(
                body, values=values, variable=var, height=38, corner_radius=8,
                fg_color=PRIMARY, button_color=PRIMARY_DARK, font=(FONT, 13),
                dropdown_font=(FONT, 13)
            )
        else:
            widget = ctk.CTkEntry(
                body, height=38, corner_radius=8, border_color="#CBD8CB",
                font=(FONT, 13), placeholder_text=field.get("placeholder", "")
            )
            if field.get("value") not in (None, ""):
                widget.insert(0, str(field["value"]))
        widget.pack(fill="x")
        widgets[field["key"]] = widget

    def collect():
        return {key: widget.get().strip() for key, widget in widgets.items()}

    def save():
        values = collect()
        dialog.destroy()
        on_save(values)

    def cancel():
        dialog.destroy()

    buttons = ctk.CTkFrame(dialog, fg_color="transparent")
    buttons.pack(fill="x", padx=24, pady=18)
    ctk.CTkButton(
        buttons, text="Cancel", width=110, height=38, corner_radius=9,
        fg_color="transparent", border_width=1, border_color="#CBD8CB",
        text_color=SUBTEXT, hover_color="#E6EDE7", font=(FONT, 13, "bold"),
        command=cancel
    ).pack(side="right", padx=(8, 0))
    ctk.CTkButton(
        buttons, text=save_text, width=140, height=38, corner_radius=9,
        fg_color=PRIMARY, hover_color=PRIMARY_DARK, font=(FONT, 13, "bold"),
        command=save
    ).pack(side="right")

    dialog.bind("<Escape>", lambda e: cancel())

    def grab():
        try:
            dialog.lift()
            dialog.grab_set()
        except Exception:
            pass

    dialog.after(120, grab)
    return dialog


def build_filter_bar(parent, sort_options, on_change, on_export_csv, on_export_pdf):
    bar = ctk.CTkFrame(
        parent, fg_color=BG_CARD, corner_radius=12,
        border_width=1, border_color=BORDER
    )
    bar.pack(fill="x", pady=(0, 10))

    search = ctk.CTkEntry(
        bar, placeholder_text="🔍  Search", width=180, height=36,
        border_color="#CBD8CB", corner_radius=8, font=(FONT, 12)
    )
    search.grid(row=0, column=0, padx=(14, 6), pady=12)

    date_from = ctk.CTkEntry(
        bar, placeholder_text="From YYYY-MM-DD", width=140, height=36,
        border_color="#CBD8CB", corner_radius=8, font=(FONT, 12)
    )
    date_from.grid(row=0, column=1, padx=6, pady=12)

    date_to = ctk.CTkEntry(
        bar, placeholder_text="To YYYY-MM-DD", width=140, height=36,
        border_color="#CBD8CB", corner_radius=8, font=(FONT, 12)
    )
    date_to.grid(row=0, column=2, padx=6, pady=12)

    sort_menu = ctk.CTkOptionMenu(
        bar, values=sort_options, width=150, height=36, corner_radius=8,
        fg_color=PRIMARY, button_color=PRIMARY_DARK, font=(FONT, 12),
        dropdown_font=(FONT, 12), command=lambda _: on_change()
    )
    sort_menu.grid(row=0, column=3, padx=6, pady=12)

    def clear():
        search.delete(0, "end")
        date_from.delete(0, "end")
        date_to.delete(0, "end")
        sort_menu.set(sort_options[0])
        on_change()

    ctk.CTkButton(
        bar, text="Clear", width=70, height=36, corner_radius=8,
        fg_color="transparent", border_width=1, border_color="#CBD8CB",
        text_color=SUBTEXT, hover_color="#E6EDE7", font=(FONT, 12, "bold"),
        command=clear
    ).grid(row=0, column=4, padx=6, pady=12)

    bar.grid_columnconfigure(5, weight=1)

    ctk.CTkButton(
        bar, text="⬇  CSV", width=90, height=36, corner_radius=8,
        fg_color=BLUE, hover_color="#1565C0", font=(FONT, 12, "bold"),
        command=on_export_csv
    ).grid(row=0, column=6, padx=(6, 4), pady=12)

    ctk.CTkButton(
        bar, text="⬇  PDF", width=90, height=36, corner_radius=8,
        fg_color=DANGER, hover_color=DANGER_HOVER, font=(FONT, 12, "bold"),
        command=on_export_pdf
    ).grid(row=0, column=7, padx=(4, 14), pady=12)

    for widget in (search, date_from, date_to):
        widget.bind("<KeyRelease>", lambda e: on_change())

    return {
        "search": search,
        "date_from": date_from,
        "date_to": date_to,
        "sort": sort_menu,
        "clear": clear,
    }


def apply_filters(records, query, search_fields, date_field, date_from, date_to):
    query = (query or "").strip().lower()
    date_from = (date_from or "").strip()
    date_to = (date_to or "").strip()

    filtered = []
    for record in records:
        if query:
            haystack = " ".join(str(record[f] or "") for f in search_fields).lower()
            if query not in haystack:
                continue
        value = str(record[date_field] or "")
        if date_from and value and value < date_from:
            continue
        if date_to and value and value > date_to:
            continue
        filtered.append(record)
    return filtered


def save_csv(path, headers, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def save_pdf(path, title, headers, rows):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(path, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
    elements = [Paragraph(title, styles["Title"]), Spacer(1, 10)]

    data = [headers] + [[str(cell) for cell in row] for row in rows]
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E7D32")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD8CB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5F1")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(table)
    document.build(elements)


def flash(label, text, color=PRIMARY):
    label.configure(text=text, text_color=color)
    app.after(4000, lambda: label.configure(text=""))


# ---------------------------------------------------------------------------
# AI feature helpers: photo scanning, diagnosis and crop calendars
# ---------------------------------------------------------------------------

IMAGE_FILETYPES = [
    ("Images", "*.jpg *.jpeg *.png *.webp *.bmp"),
    ("All files", "*.*"),
]

SEVERITY_STYLES = {
    "Low": (PRIMARY, INFO_BG),
    "Moderate": (WARN, WARN_BG),
    "High": (DANGER, "#FBE9E7"),
    "Unknown": (SUBTEXT, "#EEF1EE"),
}

TASK_TYPE_COLORS = {
    "Irrigation": BLUE,
    "Fertilizer": PRIMARY,
    "Pest check": WARN,
    "Harvest": ACCENT,
    "Other": SUBTEXT,
}


def _severity_style(severity):
    return SEVERITY_STYLES.get((severity or "").title(), SEVERITY_STYLES["Unknown"])


def make_thumbnail(path, max_size=(300, 200)):
    """Return a CTkImage thumbnail for an image path, or None on failure."""
    try:
        from PIL import Image
        image = Image.open(path).convert("RGB")
        image.thumbnail(max_size)
        return ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
    except Exception:
        return None


def task_due_label(due_date):
    days = db.days_until(due_date)
    if days is None:
        return ("No date", SUBTEXT)
    if days < 0:
        return (f"Overdue {abs(days)}d", DANGER)
    if days == 0:
        return ("Due today", WARN)
    return (f"In {days}d", SUBTEXT)


def center_dialog(dialog, width, height):
    dialog.update_idletasks()
    x = app.winfo_rootx() + max((app.winfo_width() - width) // 2, 0)
    y = app.winfo_rooty() + max((app.winfo_height() - height) // 2, 0)
    dialog.geometry(f"{width}x{height}+{x}+{y}")


def generate_calendar_for_crop(crop_id, crop_name, planting_date, area=None, on_done=None):
    """Generate (and store) a crop calendar in the background, then call on_done."""
    def worker():
        try:
            tasks = aiModule.generate_crop_calendar(crop_name, planting_date, area)
        except Exception:
            tasks = []

        def store():
            try:
                if db.get_crop(crop_id) is None:
                    return
                db.clear_crop_tasks(crop_id)
                if tasks:
                    db.add_crop_tasks(crop_id, crop_name, tasks)
            except Exception:
                return
            if on_done:
                on_done()

        app.after(0, store)

    threading.Thread(target=worker, daemon=True).start()


def open_diagnose_dialog(crop, on_logged=None):
    """Leaf-photo disease diagnosis dialog for a single crop."""
    dialog = ctk.CTkToplevel(app)
    dialog.title(f"Diagnose - {crop['name']}")
    dialog.configure(fg_color=BG)
    dialog.transient(app)
    center_dialog(dialog, 600, 700)

    state = {"path": None, "result": None, "busy": False}

    body = ctk.CTkScrollableFrame(dialog, fg_color="transparent", corner_radius=0)
    body.pack(fill="both", expand=True, padx=8, pady=8)

    ctk.CTkLabel(
        body, text=f"🔬  Diagnose {crop['name']}", font=(FONT, 19, "bold"),
        text_color=TEXT
    ).pack(anchor="w", padx=16, pady=(12, 2))
    ctk.CTkLabel(
        body,
        text="Photograph one affected leaf in good light, then let the AI suggest "
             "the likely problem. Always confirm before treating a whole field.",
        font=(FONT, 12), text_color=SUBTEXT, wraplength=520, justify="left"
    ).pack(anchor="w", padx=16)

    preview = ctk.CTkLabel(
        body, text="No photo selected", width=320, height=200,
        fg_color=BG_CARD, corner_radius=12, text_color=SUBTEXT, font=(FONT, 12)
    )
    preview.pack(padx=16, pady=14)

    actions = ctk.CTkFrame(body, fg_color="transparent")
    actions.pack(fill="x", padx=16)

    result_frame = ctk.CTkFrame(body, fg_color="transparent")
    status = ctk.CTkLabel(body, text="", font=(FONT, 12), text_color=SUBTEXT)

    log_btn = ctk.CTkButton(
        body, text="✓  Log diagnosis to this crop", height=40, corner_radius=9,
        fg_color=PRIMARY, hover_color=PRIMARY_DARK, font=(FONT, 13, "bold"),
        state="disabled", command=lambda: log()
    )
    choose_btn = ctk.CTkButton(
        actions, text="📷  Choose photo", width=170, height=40, corner_radius=9,
        fg_color="#EDF3ED", hover_color="#DCE8DC", text_color=PRIMARY,
        font=(FONT, 13, "bold"), command=lambda: choose()
    )
    choose_btn.pack(side="left")
    diagnose_btn = ctk.CTkButton(
        actions, text="🔬  Diagnose", width=150, height=40, corner_radius=9,
        fg_color=PRIMARY, hover_color=PRIMARY_DARK, font=(FONT, 13, "bold"),
        state="disabled", command=lambda: diagnose()
    )
    diagnose_btn.pack(side="left", padx=(10, 0))

    result_frame.pack(fill="x", padx=16)
    status.pack(anchor="w", padx=16, pady=(6, 0))
    log_btn.pack(fill="x", padx=16, pady=(10, 6))

    ctk.CTkLabel(
        body, text="Previous diagnoses", font=(FONT, 13, "bold"), text_color=TEXT
    ).pack(anchor="w", padx=16, pady=(14, 4))
    history = ctk.CTkFrame(body, fg_color="transparent")
    history.pack(fill="x", padx=16, pady=(0, 16))

    def render_previous():
        for widget in history.winfo_children():
            widget.destroy()
        rows = db.get_diagnoses(crop["id"])
        if not rows:
            ctk.CTkLabel(
                history, text="No diagnoses logged yet.", font=(FONT, 12),
                text_color=SUBTEXT
            ).pack(anchor="w")
            return
        for row in rows[:8]:
            card = ctk.CTkFrame(
                history, fg_color=BG_CARD, corner_radius=10,
                border_width=1, border_color=BORDER
            )
            card.pack(fill="x", pady=3)
            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=12, pady=(8, 2))
            ctk.CTkLabel(
                top, text=row["problem"], font=(FONT, 12, "bold"), text_color=TEXT
            ).pack(side="left")
            fg, _ = _severity_style(row["severity"])
            ctk.CTkLabel(
                top, text=row["severity"], font=(FONT, 10, "bold"), text_color=fg
            ).pack(side="right")
            when = (row["created_at"] or "")[:10]
            consult = "  ·  advised to consult an agronomist" if row["consult_agronomist"] else ""
            ctk.CTkLabel(
                card, text=f"{when}{consult}", font=(FONT, 10), text_color=SUBTEXT
            ).pack(anchor="w", padx=12)
            if row["treatment"]:
                ctk.CTkLabel(
                    card, text=row["treatment"], font=(FONT, 11), text_color=SUBTEXT,
                    wraplength=500, justify="left"
                ).pack(anchor="w", padx=12, pady=(2, 8))

    def show_result(result):
        state["result"] = result
        state["busy"] = False
        diagnose_btn.configure(state="normal", text="🔬  Diagnose")
        for widget in result_frame.winfo_children():
            widget.destroy()

        card = ctk.CTkFrame(
            result_frame, fg_color=BG_CARD, corner_radius=12,
            border_width=1, border_color=BORDER
        )
        card.pack(fill="x", pady=6)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 2))
        ctk.CTkLabel(
            top, text=result["problem"], font=(FONT, 15, "bold"), text_color=TEXT,
            wraplength=380, justify="left"
        ).pack(side="left")
        fg, _ = _severity_style(result["severity"])
        ctk.CTkLabel(
            top, text=result["severity"], font=(FONT, 11, "bold"), text_color=fg
        ).pack(side="right")

        if result.get("consult_agronomist"):
            ctk.CTkLabel(
                card, text="⚠  Not sure from this photo — consult an agronomist.",
                font=(FONT, 12, "bold"), text_color=WARN
            ).pack(anchor="w", padx=14, pady=(4, 0))

        ctk.CTkLabel(
            card, text="Suggested treatment", font=(FONT, 11, "bold"), text_color=SUBTEXT
        ).pack(anchor="w", padx=14, pady=(8, 0))
        ctk.CTkLabel(
            card, text=result.get("treatment") or "—", font=(FONT, 12), text_color=TEXT,
            wraplength=500, justify="left"
        ).pack(anchor="w", padx=14)
        confidence = result.get("confidence") or 0
        ctk.CTkLabel(
            card, text=f"Confidence: {int(round(confidence * 100))}%",
            font=(FONT, 11), text_color=SUBTEXT
        ).pack(anchor="w", padx=14, pady=(6, 0))
        ctk.CTkLabel(
            card, text=result.get("notes", ""), font=(FONT, 11), text_color=SUBTEXT,
            wraplength=500, justify="left"
        ).pack(anchor="w", padx=14, pady=(2, 12))

        log_btn.configure(text="✓  Log diagnosis to this crop", state="normal")
        status.configure(text="")

    def choose():
        path = filedialog.askopenfilename(title="Choose a leaf photo", filetypes=IMAGE_FILETYPES)
        if not path:
            return
        state["path"] = path
        state["result"] = None
        thumbnail = make_thumbnail(path, (300, 200))
        if thumbnail:
            preview.configure(image=thumbnail, text="")
            preview.image = thumbnail
        else:
            preview.configure(image=None, text="Preview unavailable")
        for widget in result_frame.winfo_children():
            widget.destroy()
        diagnose_btn.configure(state="normal")
        log_btn.configure(text="✓  Log diagnosis to this crop", state="disabled")
        status.configure(text="Photo selected. Tap Diagnose.", text_color=SUBTEXT)

    def diagnose():
        if state["busy"] or not state["path"]:
            return
        state["busy"] = True
        diagnose_btn.configure(state="disabled", text="Analysing…")
        log_btn.configure(state="disabled")
        status.configure(text="Analysing the leaf photo…", text_color=SUBTEXT)

        def worker():
            try:
                result = aiModule.diagnose_crop_disease(state["path"], crop["name"])
            except Exception as exc:
                result = {
                    "problem": "Uncertain", "severity": "Unknown", "treatment": "",
                    "confidence": 0.0, "consult_agronomist": True,
                    "notes": f"Diagnosis failed ({exc}). Consult an agronomist.",
                }
            app.after(0, lambda: show_result(result))

        threading.Thread(target=worker, daemon=True).start()

    def log():
        result = state["result"]
        if not result:
            return
        db.add_diagnosis(
            crop["id"], crop["name"], state["path"] or "", result["problem"],
            result["severity"], result.get("treatment", ""),
            1 if result.get("consult_agronomist") else 0
        )
        log_btn.configure(text="✓  Logged to this crop", state="disabled")
        status.configure(text="Diagnosis saved against this crop.", text_color=PRIMARY)
        render_previous()
        if on_logged:
            on_logged()

    render_previous()
    try:
        dialog.lift()
        dialog.focus_force()
    except Exception:
        pass


def open_calendar_dialog(crop, on_change=None):
    """Show and manage the AI-generated care schedule for a crop."""
    dialog = ctk.CTkToplevel(app)
    dialog.title(f"Crop calendar - {crop['name']}")
    dialog.configure(fg_color=BG)
    dialog.transient(app)
    center_dialog(dialog, 600, 700)

    state = {"busy": False}

    body = ctk.CTkScrollableFrame(dialog, fg_color="transparent", corner_radius=0)
    body.pack(fill="both", expand=True, padx=8, pady=8)

    head = ctk.CTkFrame(body, fg_color="transparent")
    head.pack(fill="x", padx=16, pady=(12, 0))
    title_col = ctk.CTkFrame(head, fg_color="transparent")
    title_col.pack(side="left")
    ctk.CTkLabel(
        title_col, text=f"📅  {crop['name']} calendar", font=(FONT, 19, "bold"),
        text_color=TEXT
    ).pack(anchor="w")
    planted = crop["planting_date"] or "not set"
    harvest = harvest_label(crop["expected_harvest_date"])
    ctk.CTkLabel(
        title_col, text=f"Planted {planted}  ·  harvest {harvest}",
        font=(FONT, 12), text_color=SUBTEXT
    ).pack(anchor="w")

    regen_btn = ctk.CTkButton(
        head, text="✨  Regenerate", width=140, height=38, corner_radius=9,
        fg_color=PRIMARY, hover_color=PRIMARY_DARK, font=(FONT, 12, "bold"),
        command=lambda: regenerate()
    )
    regen_btn.pack(side="right")

    status = ctk.CTkLabel(body, text="", font=(FONT, 12), text_color=SUBTEXT)
    status.pack(anchor="w", padx=16, pady=(4, 0))

    list_frame = ctk.CTkFrame(body, fg_color="transparent")
    list_frame.pack(fill="x", padx=16, pady=8)

    def render():
        for widget in list_frame.winfo_children():
            widget.destroy()
        tasks = db.get_crop_tasks(crop["id"])
        if not tasks:
            empty = ctk.CTkFrame(
                list_frame, fg_color=BG_CARD, corner_radius=12,
                border_width=1, border_color=BORDER
            )
            empty.pack(fill="x")
            ctk.CTkLabel(
                empty, text="No schedule yet.", font=(FONT, 13, "bold"), text_color=TEXT
            ).pack(anchor="w", padx=16, pady=(14, 2))
            ctk.CTkLabel(
                empty,
                text="Generate a season plan covering irrigation, fertilizer, pest "
                     "checks and the harvest window. It appears on the dashboard.",
                font=(FONT, 12), text_color=SUBTEXT, wraplength=500, justify="left"
            ).pack(anchor="w", padx=16, pady=(0, 14))
            return

        for task in tasks:
            done = bool(task["done"])
            card = ctk.CTkFrame(
                list_frame, fg_color="#F6F8F5" if done else BG_CARD,
                corner_radius=12, border_width=1, border_color=BORDER
            )
            card.pack(fill="x", pady=4)
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=(10, 2))
            type_color = TASK_TYPE_COLORS.get(task["task_type"], SUBTEXT)
            ctk.CTkLabel(
                row, text=(task["task_type"] or "Task").upper(),
                font=(FONT, 10, "bold"), text_color=type_color
            ).pack(side="left")
            due_text, due_color = task_due_label(task["due_date"])
            ctk.CTkLabel(
                row, text=due_text, font=(FONT, 10, "bold"), text_color=due_color
            ).pack(side="right")
            ctk.CTkLabel(
                card, text=task["title"], font=(FONT, 13, "bold"),
                text_color=SUBTEXT if done else TEXT, wraplength=460, justify="left"
            ).pack(anchor="w", padx=14)
            if task["notes"]:
                ctk.CTkLabel(
                    card, text=task["notes"], font=(FONT, 11), text_color=SUBTEXT,
                    wraplength=460, justify="left"
                ).pack(anchor="w", padx=14, pady=(2, 0))
            bottom = ctk.CTkFrame(card, fg_color="transparent")
            bottom.pack(fill="x", padx=14, pady=(6, 10))
            ctk.CTkButton(
                bottom, text="↺  Reopen" if done else "✓  Mark done",
                width=110, height=30, corner_radius=8,
                fg_color="#EEF1EE" if done else "#E7F0E9",
                hover_color="#CFE3D4", text_color=SUBTEXT if done else PRIMARY,
                font=(FONT, 12, "bold"),
                command=lambda tid=task["id"], d=done: toggle(tid, d)
            ).pack(side="left")
            ctk.CTkButton(
                bottom, text="Delete", width=80, height=30, corner_radius=8,
                fg_color="transparent", border_width=1, border_color="#E0D3D3",
                text_color=DANGER, hover_color="#FBE9E7", font=(FONT, 12, "bold"),
                command=lambda tid=task["id"]: remove(tid)
            ).pack(side="right")

    def toggle(task_id, was_done):
        db.mark_task_done(task_id, 0 if was_done else 1)
        render()
        if on_change:
            on_change()

    def remove(task_id):
        db.delete_crop_task(task_id)
        render()
        if on_change:
            on_change()

    def regenerate():
        if state["busy"]:
            return
        state["busy"] = True
        regen_btn.configure(state="disabled", text="Generating…")
        status.configure(text="Generating the crop calendar…", text_color=SUBTEXT)

        def worker():
            try:
                tasks = aiModule.generate_crop_calendar(
                    crop["name"], crop["planting_date"], crop["area"]
                )
            except Exception:
                tasks = []

            def store():
                db.clear_crop_tasks(crop["id"])
                if tasks:
                    db.add_crop_tasks(crop["id"], crop["name"], tasks)
                state["busy"] = False
                regen_btn.configure(state="normal", text="✨  Regenerate")
                status.configure(text="Calendar updated.", text_color=PRIMARY)
                app.after(4000, lambda: status.configure(text=""))
                render()
                if on_change:
                    on_change()

            app.after(0, store)

        threading.Thread(target=worker, daemon=True).start()

    render()
    try:
        dialog.lift()
        dialog.focus_force()
    except Exception:
        pass



# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def build_dashboard_page(container, refresh_callbacks):
    page = ctk.CTkScrollableFrame(container, fg_color="transparent", corner_radius=0)

    header = ctk.CTkFrame(page, fg_color="transparent")
    header.pack(fill="x", pady=(0, 8))
    ctk.CTkLabel(
        header, text="Dashboard", font=(FONT, 26, "bold"), text_color=TEXT,
        anchor="w"
    ).pack(side="left")
    ctk.CTkLabel(
        header, text=datetime.now().strftime("%A, %d %B %Y"),
        font=(FONT, 12), text_color=SUBTEXT, anchor="e"
    ).pack(side="right")

    stat_value_labels = {}
    stats_frame = ctk.CTkFrame(page, fg_color="transparent")
    stats_frame.pack(fill="x", pady=(14, 4))

    accents = {
        "Active Crops": ("#2E7D32", INFO_BG),
        "Inventory": ("#F57C00", "#FFF3E0"),
        "Sales": (BLUE, "#E3F2FD"),
        "Expenses": (DANGER, "#FBE9E7"),
        "Net Profit": (PRIMARY, INFO_BG),
    }

    for title in ["Active Crops", "Inventory", "Sales", "Expenses", "Net Profit"]:
        accent, soft = accents[title]
        card = ctk.CTkFrame(stats_frame, corner_radius=16, fg_color=BG_CARD)
        card.pack(side="left", fill="x", expand=True, padx=6)
        card.configure(border_width=1, border_color=BORDER)

        ctk.CTkFrame(
            card, height=5, corner_radius=0, fg_color=accent, width=100
        ).pack(fill="x")

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 4))
        ctk.CTkLabel(
            top, text=STAT_ICONS[title], font=(FONT, 18), text_color=accent
        ).pack(side="left")
        ctk.CTkLabel(
            top, text=title, font=(FONT, 12), text_color=SUBTEXT
        ).pack(side="left", padx=6)

        value_label = ctk.CTkLabel(
            card, text="0", font=(FONT, 24, "bold"), text_color=TEXT
        )
        value_label.pack(anchor="w", padx=14, pady=(0, 14))
        stat_value_labels[title] = value_label

    alert_frame = ctk.CTkFrame(page, fg_color=INFO_BG, corner_radius=12)
    alert_frame.pack(fill="x", pady=(10, 4))
    alert_label = ctk.CTkLabel(
        alert_frame, text="", font=(FONT, 13, "bold"), text_color=PRIMARY
    )
    alert_label.pack(anchor="w", padx=16, pady=12)

    lower = ctk.CTkFrame(page, fg_color="transparent")
    lower.pack(fill="both", expand=True, pady=(10, 0))

    weather_card = ctk.CTkFrame(
        lower, width=340, corner_radius=16, fg_color=BG_CARD,
        border_width=1, border_color=BORDER
    )
    weather_card.pack(side="left", fill="y", ipady=10, padx=(0, 14))
    weather_card.pack_propagate(False)

    ctk.CTkLabel(
        weather_card, text="☁  Weather", font=(FONT, 17, "bold"),
        text_color=TEXT
    ).pack(pady=(16, 2))
    ctk.CTkLabel(
        weather_card, text="Mumbai, IN", font=(FONT, 12), text_color=SUBTEXT
    ).pack()

    weather_data = weatherModule.get_weather("Mumbai")

    condition_emoji = {
        "Rain": "🌧", "Clear": "☀", "Clouds": "☁", "Mist": "🌫",
        "Thunderstorm": "⛈", "Haze": "🌫", "Snow": "❄", "Drizzle": "🌦"
    }

    if weather_data:
        ctk.CTkLabel(
            weather_card,
            text=condition_emoji.get(weather_data["condition"], "🌤"),
            font=(FONT, 40), text_color=PRIMARY
        ).pack(pady=(8, 0))
        ctk.CTkLabel(
            weather_card, text=f"{weather_data['temperature']:.0f} °C",
            font=(FONT, 28, "bold"), text_color=PRIMARY
        ).pack()
        ctk.CTkLabel(
            weather_card, text=weather_data["condition"],
            font=(FONT, 13), text_color=SUBTEXT
        ).pack(pady=(0, 8))

        for label, value in [
            ("💧 Humidity", f"{weather_data['humidity']}%"),
            ("🌬 Wind", f"{weather_data['wind']} km/h"),
        ]:
            row = ctk.CTkFrame(weather_card, fg_color="transparent")
            row.pack(fill="x", padx=24, pady=3)
            ctk.CTkLabel(row, text=label, font=(FONT, 13), text_color=SUBTEXT).pack(side="left")
            ctk.CTkLabel(row, text=value, font=(FONT, 13, "bold"), text_color=TEXT).pack(side="right")
    else:
        ctk.CTkLabel(
            weather_card, text="Weather unavailable",
            font=(FONT, 14), text_color=SUBTEXT
        ).pack(pady=20)

    suggest_card = ctk.CTkFrame(
        lower, corner_radius=16, fg_color=BG_CARD,
        border_width=1, border_color=BORDER
    )
    suggest_card.pack(side="left", fill="both", expand=True)

    ctk.CTkLabel(
        suggest_card, text="🌿 Recommended Actions",
        font=(FONT, 17, "bold"), text_color=TEXT
    ).pack(anchor="w", padx=20, pady=(16, 6))

    tips_container = ctk.CTkFrame(suggest_card, fg_color="transparent")
    tips_container.pack(fill="both", expand=True, padx=20, pady=(0, 12))

    tasks_card = ctk.CTkFrame(
        page, corner_radius=16, fg_color=BG_CARD,
        border_width=1, border_color=BORDER
    )
    tasks_card.pack(fill="x", pady=(14, 0))
    tasks_head = ctk.CTkFrame(tasks_card, fg_color="transparent")
    tasks_head.pack(fill="x", padx=20, pady=(14, 2))
    ctk.CTkLabel(
        tasks_head, text="📅  Upcoming Tasks", font=(FONT, 15, "bold"),
        text_color=TEXT
    ).pack(side="left")
    ctk.CTkLabel(
        tasks_head, text="from AI crop calendars", font=(FONT, 11),
        text_color=SUBTEXT
    ).pack(side="right")

    tasks_strip = ctk.CTkScrollableFrame(
        tasks_card, orientation="horizontal", height=96,
        fg_color="transparent", corner_radius=0
    )
    tasks_strip.pack(fill="x", padx=14, pady=(0, 12))

    bottom = ctk.CTkFrame(page, fg_color="transparent")
    bottom.pack(fill="x", pady=(14, 0))

    finance = ctk.CTkFrame(page, fg_color="transparent")
    finance.pack(fill="x", pady=(14, 0))

    trend_card = ctk.CTkFrame(
        finance, corner_radius=16, fg_color=BG_CARD,
        border_width=1, border_color=BORDER
    )
    trend_card.pack(side="left", fill="both", expand=True, padx=(0, 14))
    ctk.CTkLabel(
        trend_card, text="📊  Revenue vs costs", font=(FONT, 15, "bold"),
        text_color=TEXT
    ).pack(anchor="w", padx=20, pady=(14, 0))
    ctk.CTkLabel(
        trend_card, text="Monthly performance", font=(FONT, 11), text_color=SUBTEXT
    ).pack(anchor="w", padx=20, pady=(1, 2))
    trend_fig = Figure(figsize=(5.4, 2.2), dpi=100, facecolor=BG_CARD)
    trend_canvas = FigureCanvasTkAgg(trend_fig, master=trend_card)
    trend_widget = trend_canvas.get_tk_widget()
    trend_widget.configure(bg=BG_CARD, highlightthickness=0)
    trend_widget.pack(fill="x", padx=12, pady=(0, 10))

    health_card = ctk.CTkFrame(
        finance, width=300, corner_radius=16, fg_color=BG_CARD,
        border_width=1, border_color=BORDER
    )
    health_card.pack(side="left", fill="y")
    health_card.pack_propagate(False)
    ctk.CTkLabel(
        health_card, text="📌  Financial health", font=(FONT, 15, "bold"),
        text_color=TEXT
    ).pack(anchor="w", padx=18, pady=(14, 8))
    health_rows = ctk.CTkFrame(health_card, fg_color="transparent")
    health_rows.pack(fill="both", expand=True, padx=18, pady=(0, 12))

    charts_row = ctk.CTkFrame(page, fg_color="transparent")
    charts_row.pack(fill="x", pady=(14, 0))

    expense_chart_card = ctk.CTkFrame(
        charts_row, corner_radius=16, fg_color=BG_CARD,
        border_width=1, border_color=BORDER
    )
    expense_chart_card.pack(side="left", fill="both", expand=True, padx=(0, 14))
    ctk.CTkLabel(
        expense_chart_card, text="🧾  Expense mix", font=(FONT, 15, "bold"),
        text_color=TEXT
    ).pack(anchor="w", padx=20, pady=(14, 0))
    expense_fig = Figure(figsize=(4.2, 2.8), dpi=100, facecolor=BG_CARD)
    expense_canvas = FigureCanvasTkAgg(expense_fig, master=expense_chart_card)
    expense_widget = expense_canvas.get_tk_widget()
    expense_widget.configure(bg=BG_CARD, highlightthickness=0)
    expense_widget.pack(fill="x", padx=10, pady=(0, 8))

    crop_chart_card = ctk.CTkFrame(
        charts_row, corner_radius=16, fg_color=BG_CARD,
        border_width=1, border_color=BORDER
    )
    crop_chart_card.pack(side="left", fill="both", expand=True)
    ctk.CTkLabel(
        crop_chart_card, text="🌾  Profit by crop", font=(FONT, 15, "bold"),
        text_color=TEXT
    ).pack(anchor="w", padx=20, pady=(14, 0))
    crop_fig = Figure(figsize=(4.2, 2.8), dpi=100, facecolor=BG_CARD)
    crop_canvas = FigureCanvasTkAgg(crop_fig, master=crop_chart_card)
    crop_widget = crop_canvas.get_tk_widget()
    crop_widget.configure(bg=BG_CARD, highlightthickness=0)
    crop_widget.pack(fill="x", padx=10, pady=(0, 8))

    profit_card = ctk.CTkFrame(
        bottom, width=380, corner_radius=16, fg_color=BG_CARD,
        border_width=1, border_color=BORDER
    )
    profit_card.pack(side="left", fill="y", padx=(0, 14))
    profit_card.pack_propagate(False)
    ctk.CTkLabel(
        profit_card, text="💹  Profit by Crop", font=(FONT, 15, "bold"),
        text_color=TEXT
    ).pack(anchor="w", padx=20, pady=(14, 6))
    profit_rows = ctk.CTkFrame(profit_card, fg_color="transparent")
    profit_rows.pack(fill="both", expand=True, padx=20, pady=(0, 12))

    activity = ctk.CTkFrame(
        bottom, corner_radius=16, fg_color=BG_CARD,
        border_width=1, border_color=BORDER
    )
    activity.pack(side="left", fill="both", expand=True)

    ctk.CTkLabel(
        activity, text="🕓  Recent Activity", font=(FONT, 15, "bold"),
        text_color=TEXT
    ).pack(anchor="w", padx=20, pady=(14, 8))

    activity_rows = ctk.CTkFrame(activity, fg_color="transparent")
    activity_rows.pack(fill="both", expand=True, padx=20, pady=(0, 12))

    def complete_task(task_id):
        db.mark_task_done(task_id)
        refresh()

    def refresh():
        crops = db.get_crops()
        low_stock = db.get_low_stock_items()
        total_sales = db.get_total_sales()
        total_expenses = db.get_total_expenses()
        profit = total_sales - total_expenses

        stat_value_labels["Active Crops"].configure(text=str(len(crops)))
        stat_value_labels["Inventory"].configure(text=str(len(db.get_inventory())))
        stat_value_labels["Sales"].configure(text=f"₹{total_sales:,.0f}")
        stat_value_labels["Expenses"].configure(text=f"₹{total_expenses:,.0f}")
        stat_value_labels["Net Profit"].configure(
            text=f"₹{profit:,.0f}",
            text_color=PRIMARY if profit >= 0 else DANGER
        )

        trend_fig.clear()
        trend_axis = trend_fig.add_subplot(111)
        monthly = db.get_monthly_totals()
        if monthly:
            months = [row[0][2:] for row in monthly[-6:]]
            sales_values = [row[1] for row in monthly[-6:]]
            expense_values = [row[2] for row in monthly[-6:]]
            positions = list(range(len(months)))
            trend_axis.plot(positions, sales_values, marker="o", linewidth=2, color=PRIMARY, label="Sales")
            trend_axis.plot(positions, expense_values, marker="o", linewidth=2, color=DANGER, label="Expenses")
            trend_axis.set_xticks(positions)
            trend_axis.set_xticklabels(months, fontsize=8)
            trend_axis.grid(axis="y", alpha=0.2)
            trend_axis.legend(fontsize=8, frameon=False, loc="upper left")
            trend_axis.tick_params(axis="y", labelsize=8)
        else:
            trend_axis.text(0.5, 0.5, "Add sales and expenses to see trends", ha="center", va="center", color=SUBTEXT)
            trend_axis.axis("off")
        trend_axis.set_facecolor(BG_CARD)
        trend_fig.tight_layout(pad=1.2)
        trend_canvas.draw()

        expense_fig.clear()
        expense_axis = expense_fig.add_subplot(111)
        expense_data = db.get_expenses_by_category()
        if expense_data:
            expense_axis.pie(
                [value for _, value in expense_data],
                labels=[label for label, _ in expense_data],
                autopct="%1.0f%%", startangle=90,
                colors=[PIE_COLORS[i % len(PIE_COLORS)] for i in range(len(expense_data))],
                textprops={"fontsize": 8}
            )
            expense_axis.axis("equal")
        else:
            expense_axis.text(0.5, 0.5, "No expenses recorded", ha="center", va="center", color=SUBTEXT)
            expense_axis.axis("off")
        expense_fig.tight_layout(pad=1.0)
        expense_canvas.draw()

        crop_fig.clear()
        crop_axis = crop_fig.add_subplot(111)
        crop_data = [entry for entry in db.get_profit_by_crop() if entry["sales"] or entry["expenses"]]
        if crop_data:
            crop_data = sorted(crop_data, key=lambda entry: entry["profit"], reverse=True)[:6]
            crop_axis.barh(
                [entry["name"] for entry in crop_data],
                [entry["profit"] for entry in crop_data],
                color=[PRIMARY if entry["profit"] >= 0 else DANGER for entry in crop_data]
            )
            crop_axis.axvline(0, color="#9AA89D", linewidth=0.8)
            crop_axis.tick_params(axis="both", labelsize=8)
            crop_axis.grid(axis="x", alpha=0.2)
        else:
            crop_axis.text(0.5, 0.5, "Link sales and expenses to crops", ha="center", va="center", color=SUBTEXT)
            crop_axis.axis("off")
        crop_fig.tight_layout(pad=1.0)
        crop_canvas.draw()

        for widget in health_rows.winfo_children():
            widget.destroy()
        margin = (profit / total_sales * 100) if total_sales else 0
        categories = db.get_expenses_by_category()
        top_cost = categories[0] if categories else None
        low_stock_count = len(low_stock)
        health_data = [
            ("Net margin", f"{margin:.1f}%", PRIMARY if margin >= 0 else DANGER),
            ("Largest cost", top_cost[0] if top_cost else "No expenses", TEXT),
            ("Low stock", f"{low_stock_count} item(s)", WARN if low_stock_count else PRIMARY),
        ]
        for label, value, color in health_data:
            row = ctk.CTkFrame(health_rows, fg_color="transparent")
            row.pack(fill="x", pady=5)
            ctk.CTkLabel(row, text=label, font=(FONT, 11), text_color=SUBTEXT).pack(side="left")
            ctk.CTkLabel(row, text=value, font=(FONT, 12, "bold"), text_color=color).pack(side="right")

        upcoming = []
        for crop in crops:
            if (crop["status"] or "") == "Harvested":
                continue
            days = db.days_until(crop["expected_harvest_date"])
            if days is not None and days <= 7:
                upcoming.append((crop["name"], days))

        parts = []
        if low_stock:
            parts.append(f"{len(low_stock)} item(s) low on stock")
        if upcoming:
            parts.append(f"{len(upcoming)} crop(s) nearing harvest")

        forecast_alerts = aiModule.build_forecast_alerts()
        if forecast_alerts:
            parts.append(forecast_alerts[0].rstrip("."))

        if parts:
            alert_frame.configure(fg_color=WARN_BG)
            alert_label.configure(
                text="⚠  " + ", ".join(parts) + " — review soon.",
                text_color="#6B5A00"
            )
        else:
            alert_frame.configure(fg_color=INFO_BG)
            alert_label.configure(
                text="✓  All systems healthy. No alerts.",
                text_color=PRIMARY
            )

        for widget in tips_container.winfo_children():
            widget.destroy()
        for tip in aiModule.build_insights():
            tip_box = ctk.CTkFrame(tips_container, fg_color=BG, corner_radius=10)
            tip_box.pack(fill="x", pady=3)
            ctk.CTkLabel(
                tip_box, text=tip, font=(FONT, 12), text_color=TEXT,
                anchor="w", justify="left", wraplength=520
            ).pack(anchor="w", padx=14, pady=8)

        for widget in profit_rows.winfo_children():
            widget.destroy()
        crop_profits = db.get_profit_by_crop()
        if crop_profits:
            for entry in crop_profits[:6]:
                row = ctk.CTkFrame(profit_rows, fg_color="transparent")
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(
                    row, text=entry["name"], font=(FONT, 13),
                    text_color=TEXT, anchor="w"
                ).pack(side="left")
                ctk.CTkLabel(
                    row, text=f"₹{entry['profit']:,.0f}", font=(FONT, 13, "bold"),
                    text_color=PRIMARY if entry["profit"] >= 0 else DANGER,
                    anchor="e"
                ).pack(side="right")
        else:
            ctk.CTkLabel(
                profit_rows, text="No crops yet.", font=(FONT, 12),
                text_color=SUBTEXT
            ).pack(anchor="w")

        for widget in activity_rows.winfo_children():
            widget.destroy()
        activity_list = get_recent_activity()
        if activity_list:
            for date_str, text in activity_list:
                row = ctk.CTkFrame(activity_rows, fg_color="transparent")
                row.pack(fill="x", pady=3)
                ctk.CTkLabel(
                    row, text=date_str, width=100, font=(FONT, 12),
                    text_color=SUBTEXT, anchor="w"
                ).pack(side="left")
                ctk.CTkLabel(
                    row, text=text, font=(FONT, 13), text_color=TEXT, anchor="w"
                ).pack(side="left", padx=(8, 0))
        else:
            ctk.CTkLabel(
                activity_rows, text="No activity yet.", font=(FONT, 13),
                text_color=SUBTEXT
            ).pack(anchor="w")

        for widget in tasks_strip.winfo_children():
            widget.destroy()
        tasks = db.get_upcoming_tasks(14)
        rainy_days = {
            day["date"] for day in aiModule._cached_forecast() if day.get("will_rain")
        }
        if tasks:
            for task in tasks[:12]:
                day_count = db.days_until(task["due_date"])
                if day_count is not None and day_count < 0:
                    due_color, due_text = DANGER, f"Overdue {abs(day_count)}d"
                elif day_count == 0:
                    due_color, due_text = WARN, "Due today"
                else:
                    due_color, due_text = SUBTEXT, f"in {day_count}d"

                rain_here = task["due_date"] in rainy_days
                if rain_here:
                    due_color, due_text = BLUE, f"🌧 rain · {due_text}"

                chip = ctk.CTkFrame(
                    tasks_strip, fg_color="#EAF2FB" if rain_here else BG, corner_radius=10,
                    border_width=1, border_color="#BFD6EE" if rain_here else BORDER
                )
                chip.pack(side="left", padx=6, pady=4)
                ctk.CTkLabel(
                    chip, text=(task["task_type"] or "Task").upper(),
                    font=(FONT, 9, "bold"),
                    text_color=TASK_TYPE_COLORS.get(task["task_type"], SUBTEXT)
                ).pack(anchor="w", padx=12, pady=(8, 0))
                ctk.CTkLabel(
                    chip, text=task["title"], font=(FONT, 12, "bold"),
                    text_color=TEXT, wraplength=190, justify="left", anchor="w"
                ).pack(anchor="w", padx=12)
                meta = ctk.CTkFrame(chip, fg_color="transparent")
                meta.pack(fill="x", padx=12, pady=(2, 8))
                ctk.CTkLabel(
                    meta, text=f"{task['crop_name']}  ·  {due_text}",
                    font=(FONT, 10), text_color=due_color
                ).pack(side="left")
                ctk.CTkButton(
                    meta, text="✓", width=24, height=22, corner_radius=6,
                    fg_color="#E7F0E9", hover_color="#CFE3D4", text_color=PRIMARY,
                    font=(FONT, 11, "bold"),
                    command=lambda tid=task["id"]: complete_task(tid)
                ).pack(side="right", padx=(8, 0))
        else:
            ctk.CTkLabel(
                tasks_strip,
                text="No upcoming tasks. Add a crop to auto-generate its care calendar.",
                font=(FONT, 12), text_color=SUBTEXT
            ).pack(anchor="w", padx=10, pady=26)

    refresh()
    refresh_callbacks["Dashboard"] = refresh
    return page


def get_recent_activity():
    rows = []
    for s in db.get_sales():
        rows.append((s["sale_date"], f"Sale  ·  {s['crop_name']}  ·  ₹{s['quantity'] * s['price']:,.0f}"))
    for e in db.get_expenses():
        rows.append((e["expense_date"], f"Expense  ·  {e['category']}  ·  ₹{e['amount']:,.0f}"))
    for c in db.get_crops():
        rows.append((c["planting_date"], f"Crop planted  ·  {c['name']}"))
    rows = [r for r in rows if r[0]]
    rows.sort(key=lambda r: r[0], reverse=True)
    return rows[:5]


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------

def build_weather_page(container, refresh_callbacks):
    page = ctk.CTkFrame(container, fg_color="transparent")
    make_page_header(page, "Weather", subtitle="Plan irrigation, spraying and field work with live conditions")

    controls = ctk.CTkFrame(page, fg_color=BG_CARD, corner_radius=12, border_width=1, border_color=BORDER)
    controls.pack(fill="x", pady=(0, 14))
    city_entry = ctk.CTkEntry(
        controls, width=260, height=38, corner_radius=8,
        border_color="#CBD8CB", placeholder_text="City, e.g. Mumbai"
    )
    city_entry.insert(0, "Mumbai")
    city_entry.pack(side="left", padx=(14, 8), pady=12)
    status_label = ctk.CTkLabel(controls, text="", font=(FONT, 11), text_color=SUBTEXT)
    status_label.pack(side="left", padx=10)
    refresh_button = ctk.CTkButton(
        controls, text="↻  Refresh weather", width=150, height=38, corner_radius=8,
        fg_color=PRIMARY, hover_color=PRIMARY_DARK, font=(FONT, 12, "bold")
    )
    refresh_button.pack(side="right", padx=14, pady=12)

    summary = ctk.CTkFrame(page, fg_color="transparent")
    summary.pack(fill="x", pady=(0, 14))
    current_card = ctk.CTkFrame(summary, width=330, corner_radius=16, fg_color=BG_CARD, border_width=1, border_color=BORDER)
    current_card.pack(side="left", fill="y", padx=(0, 14))
    current_card.pack_propagate(False)
    suggestions_card = ctk.CTkFrame(summary, corner_radius=16, fg_color=BG_CARD, border_width=1, border_color=BORDER)
    suggestions_card.pack(side="left", fill="both", expand=True)

    forecast_card = ctk.CTkFrame(page, corner_radius=16, fg_color=BG_CARD, border_width=1, border_color=BORDER)
    forecast_card.pack(fill="both", expand=True)
    ctk.CTkLabel(
        forecast_card, text="📅  Five-day outlook", font=(FONT, 16, "bold"), text_color=TEXT
    ).pack(anchor="w", padx=20, pady=(16, 2))
    forecast_rows = ctk.CTkScrollableFrame(forecast_card, orientation="horizontal", height=185, fg_color="transparent", corner_radius=0)
    forecast_rows.pack(fill="x", padx=14, pady=(0, 14))

    condition_emoji = {
        "Rain": "🌧", "Clear": "☀", "Clouds": "☁", "Mist": "🌫",
        "Thunderstorm": "⛈", "Haze": "🌫", "Snow": "❄", "Drizzle": "🌦"
    }

    def clear(frame):
        for widget in frame.winfo_children():
            widget.destroy()

    def render(data, forecast):
        clear(current_card)
        clear(suggestions_card)
        clear(forecast_rows)
        city = data.get("city", city_entry.get().strip()) if data else city_entry.get().strip()
        if not data:
            ctk.CTkLabel(current_card, text="Weather unavailable", font=(FONT, 16, "bold"), text_color=TEXT).pack(pady=(28, 6))
            ctk.CTkLabel(current_card, text="Check the city name or your internet connection.", font=(FONT, 11), text_color=SUBTEXT, wraplength=270, justify="center").pack(padx=22)
            ctk.CTkLabel(suggestions_card, text="No suggestions until weather data is available.", font=(FONT, 13), text_color=SUBTEXT).pack(anchor="w", padx=20, pady=24)
        else:
            ctk.CTkLabel(current_card, text=f"☁  {city}", font=(FONT, 17, "bold"), text_color=TEXT).pack(pady=(16, 4))
            ctk.CTkLabel(current_card, text=condition_emoji.get(data["condition"], "🌤"), font=(FONT, 42), text_color=PRIMARY).pack(pady=(4, 0))
            ctk.CTkLabel(current_card, text=f"{data['temperature']:.0f} °C", font=(FONT, 30, "bold"), text_color=PRIMARY).pack()
            ctk.CTkLabel(current_card, text=data["condition"], font=(FONT, 13), text_color=SUBTEXT).pack(pady=(0, 10))
            for label, value in [("Humidity", f"{data['humidity']}%"), ("Wind", f"{data['wind']} km/h")]:
                row = ctk.CTkFrame(current_card, fg_color="transparent")
                row.pack(fill="x", padx=24, pady=3)
                ctk.CTkLabel(row, text=label, font=(FONT, 12), text_color=SUBTEXT).pack(side="left")
                ctk.CTkLabel(row, text=value, font=(FONT, 12, "bold"), text_color=TEXT).pack(side="right")

            ctk.CTkLabel(suggestions_card, text="🌿  Farming suggestions", font=(FONT, 16, "bold"), text_color=TEXT).pack(anchor="w", padx=20, pady=(16, 8))
            for suggestion in weatherModule.get_farming_suggestion(data):
                tip = ctk.CTkFrame(suggestions_card, fg_color=BG, corner_radius=9)
                tip.pack(fill="x", padx=20, pady=3)
                ctk.CTkLabel(tip, text=suggestion, font=(FONT, 12), text_color=TEXT, anchor="w", justify="left", wraplength=520).pack(anchor="w", padx=12, pady=8)

        if not forecast:
            ctk.CTkLabel(forecast_rows, text="Forecast unavailable for this location.", font=(FONT, 12), text_color=SUBTEXT).pack(anchor="w", padx=10, pady=28)
        else:
            for day in forecast:
                try:
                    day_label = datetime.strptime(day["date"], "%Y-%m-%d").strftime("%a\n%d %b")
                except (TypeError, ValueError):
                    day_label = day.get("date", "")
                rain_text = f"Rain {day.get('pop', 0) * 100:.0f}%" if day.get("will_rain") else "Dry window"
                card = ctk.CTkFrame(forecast_rows, width=150, height=145, fg_color="#EAF2FB" if day.get("will_rain") else BG, corner_radius=12, border_width=1, border_color="#BFD6EE" if day.get("will_rain") else BORDER)
                card.pack(side="left", padx=6, pady=5)
                card.pack_propagate(False)
                ctk.CTkLabel(card, text=day_label, font=(FONT, 11, "bold"), text_color=TEXT, justify="center").pack(pady=(10, 2))
                ctk.CTkLabel(card, text=condition_emoji.get(day.get("condition"), "🌤"), font=(FONT, 24), text_color=PRIMARY).pack()
                temp_min = day.get("temp_min")
                temp_max = day.get("temp_max")
                temp_text = "--" if temp_min is None or temp_max is None else f"{temp_min:.0f}° / {temp_max:.0f}°C"
                ctk.CTkLabel(card, text=temp_text, font=(FONT, 12, "bold"), text_color=TEXT).pack()
                ctk.CTkLabel(card, text=rain_text, font=(FONT, 10), text_color=BLUE if day.get("will_rain") else SUBTEXT).pack(pady=(2, 0))

    def load_weather():
        city = city_entry.get().strip()
        if not city:
            status_label.configure(text="Enter a city first.", text_color=DANGER)
            return
        refresh_button.configure(state="disabled", text="Loading...")
        status_label.configure(text="Fetching live conditions...", text_color=SUBTEXT)

        def worker():
            try:
                data = weatherModule.get_weather(city)
                forecast = weatherModule.get_forecast(city, 5) if data else []
            except Exception:
                data, forecast = None, []
            app.after(0, lambda: finish(data, forecast))

        def finish(data, forecast):
            refresh_button.configure(state="normal", text="↻  Refresh weather")
            status_label.configure(text="Updated just now" if data else "Could not load weather", text_color=PRIMARY if data else DANGER)
            render(data, forecast)

        threading.Thread(target=worker, daemon=True).start()

    refresh_button.configure(command=load_weather)
    city_entry.bind("<Return>", lambda event: load_weather())
    refresh_callbacks["Weather"] = load_weather
    load_weather()
    return page


# ---------------------------------------------------------------------------
# Crops
# ---------------------------------------------------------------------------

def build_crops_page(container, refresh_callbacks):
    page = ctk.CTkFrame(container, fg_color="transparent")
    make_page_header(page, "Crops", subtitle="Track what's planted across your land")

    form = make_form_card(page)
    entries = build_inline_form(form, [
        {"key": "name", "placeholder": "Crop name", "width": 140, "col": 0},
        {"key": "area", "placeholder": "Area (acres)", "width": 100, "col": 1},
        {"key": "date", "placeholder": "Planting date", "width": 120,
         "value": date.today().isoformat(), "col": 2},
        {"key": "status", "kind": "menu", "values": db.CROP_STATUSES,
         "width": 115, "col": 3},
        {"key": "harvest", "placeholder": "Expected harvest", "width": 120, "col": 4},
    ])
    add_form_button(form, "+  Add Crop", lambda: add_handler(), column=5, width=115)

    crops_feedback = ctk.CTkLabel(page, text="", font=(FONT, 12), text_color=PRIMARY)
    crops_feedback.pack(anchor="e", pady=(0, 4))

    list_frame = make_list_area(page)

    def refresh():
        for widget in list_frame.winfo_children():
            widget.destroy()

        crops = db.get_crops()
        if not crops:
            ctk.CTkLabel(
                list_frame, text="No crops added yet.", font=(FONT, 13),
                text_color=SUBTEXT
            ).pack(pady=40)
            return

        make_table_header(list_frame, [
            ("CROP", 230), ("AREA", 90), ("PLANTED", 110),
            ("HARVEST", 110), ("STATUS", 120), ("PROFIT", 110),
        ])

        profit_map = {p["id"]: p for p in db.get_profit_by_crop()}

        for crop in crops:
            row = ctk.CTkFrame(
                list_frame, fg_color=BG_CARD, corner_radius=12,
                border_width=1, border_color=BORDER
            )
            row.pack(fill="x", pady=5, padx=4)
            row.grid_columnconfigure(6, weight=1)

            ctk.CTkLabel(
                row, text=crop["name"], font=(FONT, 14, "bold"),
                text_color=TEXT, anchor="w", width=230
            ).grid(row=0, column=0, padx=(16, 8), pady=12, sticky="w")

            ctk.CTkLabel(
                row, text=crop["area"] or "—", font=(FONT, 13),
                text_color=SUBTEXT, anchor="w", width=90
            ).grid(row=0, column=1, padx=8, sticky="w")

            ctk.CTkLabel(
                row, text=crop["planting_date"] or "—", font=(FONT, 13),
                text_color=SUBTEXT, anchor="w", width=110
            ).grid(row=0, column=2, padx=8, sticky="w")

            harvest_days = db.days_until(crop["expected_harvest_date"])
            harvest_text = harvest_label(crop["expected_harvest_date"])
            harvest_color = DANGER if (harvest_days is not None and harvest_days < 0) else TEXT
            ctk.CTkLabel(
                row, text=harvest_text, font=(FONT, 13), text_color=harvest_color,
                anchor="w", width=110
            ).grid(row=0, column=3, padx=8, sticky="w")

            label, badge_fg, badge_bg = badge_for_status(crop["status"])
            make_badge(row, label, badge_fg, badge_bg).grid(
                row=0, column=4, padx=8, sticky="w"
            )

            entry = profit_map.get(crop["id"], {"profit": 0})
            ctk.CTkLabel(
                row, text=f"₹{entry['profit']:,.0f}", font=(FONT, 13, "bold"),
                text_color=PRIMARY if entry["profit"] >= 0 else DANGER,
                anchor="w", width=110
            ).grid(row=0, column=5, padx=8, sticky="w")

            make_row_actions(
                row,
                lambda c=crop: edit_handler(c),
                lambda cid=crop["id"]: delete_handler(cid),
                column=7,
                extra_buttons=[
                    {"text": "📅", "command": lambda c=crop: open_calendar_dialog(
                        c, on_change=lambda: refresh_callbacks["Dashboard"]())},
                    {"text": "🔬", "command": lambda c=crop: open_diagnose_dialog(
                        c, on_logged=lambda: refresh_callbacks["Dashboard"]())},
                ]
            )

    def add_handler():
        name = entries["name"].get().strip()
        if not name:
            return
        area = entries["area"].get().strip()
        planting = entries["date"].get().strip()
        crop_id = db.add_crop(
            name,
            area,
            planting,
            entries["status"].get().strip() or "Planted",
            entries["harvest"].get().strip() or None
        )
        reset_inline_form(entries)
        refresh()
        if planting and crop_id:
            flash(crops_feedback, f"Generating a care calendar for {name}…", SUBTEXT)
            generate_calendar_for_crop(
                crop_id, name, planting, area,
                on_done=lambda n=name: calendar_ready(n)
            )

    def calendar_ready(name):
        flash(crops_feedback, f"Calendar ready for {name}.", PRIMARY)
        refresher = refresh_callbacks.get("Dashboard")
        if refresher:
            refresher()

    def edit_handler(crop):
        fields = [
            {"key": "name", "label": "Crop name", "value": crop["name"]},
            {"key": "area", "label": "Area", "value": crop["area"]},
            {"key": "planting_date", "label": "Planting date (YYYY-MM-DD)", "value": crop["planting_date"]},
            {"key": "status", "label": "Status", "kind": "menu", "values": db.CROP_STATUSES,
             "value": crop["status"] or "Planted"},
            {"key": "expected_harvest_date", "label": "Expected harvest date (YYYY-MM-DD)",
             "value": crop["expected_harvest_date"]},
        ]

        def save(values):
            if not values["name"]:
                return
            db.update_crop(
                crop["id"], values["name"], values["area"], values["planting_date"],
                values["status"], values["expected_harvest_date"] or None
            )
            refresh()

        open_form_dialog("Edit Crop", fields, save)

    def delete_handler(crop_id):
        db.delete_crop(crop_id)
        refresh()

    bind_form_enter(entries, add_handler)
    refresh()
    refresh_callbacks["Crops"] = refresh
    return page


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def build_inventory_page(container, refresh_callbacks):
    page = ctk.CTkFrame(container, fg_color="transparent")
    make_page_header(page, "Inventory", subtitle="Supplies, seeds and equipment in store")

    form = make_form_card(page)
    entries = build_inline_form(form, [
        {"key": "item", "placeholder": "Item name", "width": 190},
        {"key": "qty", "placeholder": "Quantity", "width": 110},
        {"key": "unit", "placeholder": "Unit (kg, bags, L...)", "width": 160},
        {"key": "threshold", "placeholder": "Reorder at qty", "width": 130},
    ])
    add_form_button(form, "+  Add Item", lambda: add_handler(), column=4, width=115)

    list_frame = make_list_area(page)

    def refresh():
        for widget in list_frame.winfo_children():
            widget.destroy()

        items = db.get_inventory()
        if not items:
            ctk.CTkLabel(
                list_frame, text="No inventory items yet.", font=(FONT, 13),
                text_color=SUBTEXT
            ).pack(pady=40)
            return

        make_table_header(list_frame, [
            ("ITEM", 260), ("QUANTITY", 140), ("REORDER AT", 130), ("STATUS", 150),
        ])

        for item in items:
            row = ctk.CTkFrame(
                list_frame, fg_color=BG_CARD, corner_radius=12,
                border_width=1, border_color=BORDER
            )
            row.pack(fill="x", pady=5, padx=4)
            row.grid_columnconfigure(5, weight=1)

            qty_text = f"{item['quantity']:g} {item['unit'] or ''}".strip()
            ctk.CTkLabel(
                row, text=item["item_name"], font=(FONT, 14, "bold"),
                text_color=TEXT, anchor="w", width=260
            ).grid(row=0, column=0, padx=(16, 8), pady=12, sticky="w")

            ctk.CTkLabel(
                row, text=qty_text, font=(FONT, 13), text_color=SUBTEXT,
                anchor="w", width=140
            ).grid(row=0, column=1, padx=8, sticky="w")

            threshold = item["reorder_threshold"] or 0
            ctk.CTkLabel(
                row, text=f"{threshold:g}" if threshold else "—", font=(FONT, 13),
                text_color=SUBTEXT, anchor="w", width=130
            ).grid(row=0, column=2, padx=8, sticky="w")

            if db.is_low_stock(item):
                badge = make_badge(row, "⚠  Reorder now", WARN, WARN_BG)
            else:
                badge = make_badge(row, "● In stock", BLUE, "#E3F2FD")
            badge.grid(row=0, column=3, padx=8, sticky="w")

            make_row_actions(
                row,
                lambda it=item: edit_handler(it),
                lambda iid=item["id"]: delete_handler(iid),
                column=6
            )

    def add_handler():
        name = entries["item"].get().strip()
        qty_raw = entries["qty"].get().strip()
        if not name or not qty_raw:
            return
        try:
            qty = float(qty_raw)
        except ValueError:
            return
        threshold_raw = entries["threshold"].get().strip()
        try:
            threshold = float(threshold_raw) if threshold_raw else 0
        except ValueError:
            threshold = 0

        db.add_inventory_item(name, qty, entries["unit"].get().strip(), threshold)
        reset_inline_form(entries)
        refresh()

    def edit_handler(item):
        fields = [
            {"key": "item_name", "label": "Item name", "value": item["item_name"]},
            {"key": "quantity", "label": "Quantity", "value": f"{item['quantity']:g}"},
            {"key": "unit", "label": "Unit", "value": item["unit"]},
            {"key": "reorder_threshold", "label": "Reorder threshold (low when qty ≤ this)",
             "value": f"{item['reorder_threshold']:g}" if item["reorder_threshold"] else ""},
        ]

        def save(values):
            if not values["item_name"]:
                return
            try:
                quantity = float(values["quantity"])
            except ValueError:
                return
            try:
                threshold = float(values["reorder_threshold"]) if values["reorder_threshold"] else 0
            except ValueError:
                threshold = 0
            db.update_inventory_item(
                item["id"], values["item_name"], quantity, values["unit"], threshold
            )
            refresh()

        open_form_dialog("Edit Inventory Item", fields, save)

    def delete_handler(item_id):
        db.delete_inventory_item(item_id)
        refresh()

    bind_form_enter(entries, add_handler)
    refresh()
    refresh_callbacks["Inventory"] = refresh
    return page


# ---------------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------------

def build_sales_page(container, refresh_callbacks):
    page = ctk.CTkFrame(container, fg_color="transparent")
    make_page_header(page, "Sales", subtitle="Record harvest sales and revenue")

    state = {"rows": [], "name_to_id": {}}

    def crop_lookup():
        crops = db.get_crops()
        names = sorted({c["name"] for c in crops}, key=str.lower)
        return names, {c["name"]: c["id"] for c in crops}

    names = crop_lookup()[0]
    state["name_to_id"] = crop_lookup()[1]

    form = make_form_card(page)
    entries = build_inline_form(form, [
        {"key": "crop", "kind": "menu", "values": names or ["No crops yet"], "width": 160},
        {"key": "qty", "placeholder": "Quantity", "width": 110},
        {"key": "price", "placeholder": "Price per unit (₹)", "width": 145},
        {"key": "date", "placeholder": "Sale date", "width": 130, "value": date.today().isoformat()},
    ])
    add_form_button(form, "+  Record Sale", lambda: add_handler(), column=4, width=130)

    total_label = ctk.CTkLabel(page, text="", font=(FONT, 15, "bold"), text_color=BLUE)
    total_label.pack(anchor="e", pady=(0, 6))

    feedback = ctk.CTkLabel(page, text="", font=(FONT, 12), text_color=PRIMARY)
    feedback.pack(anchor="e", pady=(0, 6))

    filters = build_filter_bar(
        page, SALES_SORTS, lambda: refresh(), lambda: export_csv(), lambda: export_pdf()
    )

    list_frame = make_list_area(page)

    def refresh():
        for widget in list_frame.winfo_children():
            widget.destroy()

        fresh_names, fresh_map = crop_lookup()
        state["name_to_id"] = fresh_map
        current_crop = entries["crop"].get()
        entries["crop"].configure(values=fresh_names or ["No crops yet"])
        if current_crop in fresh_names:
            entries["crop"].set(current_crop)
        elif fresh_names:
            entries["crop"].set(fresh_names[0])
        else:
            entries["crop"].set("No crops yet")

        sales = db.get_sales()
        filtered = apply_filters(
            sales,
            filters["search"].get(),
            ["crop_name"],
            "sale_date",
            filters["date_from"].get(),
            filters["date_to"].get(),
        )

        sort = filters["sort"].get()
        if sort == "Newest first":
            filtered.sort(key=lambda s: str(s["sale_date"] or ""), reverse=True)
        elif sort == "Oldest first":
            filtered.sort(key=lambda s: str(s["sale_date"] or ""))
        elif sort == "Highest amount":
            filtered.sort(key=lambda s: s["quantity"] * s["price"], reverse=True)
        elif sort == "Lowest amount":
            filtered.sort(key=lambda s: s["quantity"] * s["price"])
        elif sort == "Crop A-Z":
            filtered.sort(key=lambda s: str(s["crop_name"]).lower())

        state["rows"] = filtered
        shown_total = sum(s["quantity"] * s["price"] for s in filtered)
        total_label.configure(
            text=f"Showing {len(filtered)} sale(s)    ₹{shown_total:,.0f}"
        )

        if not filtered:
            ctk.CTkLabel(
                list_frame, text="No sales match your filters.", font=(FONT, 13),
                text_color=SUBTEXT
            ).pack(pady=40)
            return

        for sale in filtered:
            row = ctk.CTkFrame(
                list_frame, fg_color=BG_CARD, corner_radius=12,
                border_width=1, border_color=BORDER
            )
            row.pack(fill="x", pady=5, padx=4)
            row.grid_columnconfigure(4, weight=1)

            ctk.CTkLabel(
                row, text=sale["crop_name"], font=(FONT, 14, "bold"),
                text_color=TEXT, anchor="w"
            ).grid(row=0, column=0, padx=(16, 8), pady=12, sticky="w")

            ctk.CTkLabel(
                row, text=f"{sale['quantity']:g} units @ ₹{sale['price']:g}",
                font=(FONT, 13), text_color=SUBTEXT, anchor="w"
            ).grid(row=1, column=0, padx=(16, 8), pady=(0, 12), sticky="w")

            ctk.CTkLabel(
                row, text=f"₹{sale['quantity'] * sale['price']:,.0f}",
                font=(FONT, 15, "bold"), text_color=BLUE, anchor="w"
            ).grid(row=0, column=2, padx=8, sticky="w")

            ctk.CTkLabel(
                row, text=sale["sale_date"], font=(FONT, 12),
                text_color=SUBTEXT, anchor="e"
            ).grid(row=1, column=2, padx=8, pady=(0, 12), sticky="e")

            make_row_actions(
                row,
                lambda s=sale: edit_handler(s),
                lambda sid=sale["id"]: delete_handler(sid),
                column=5, rowspan=2
            )

    def add_handler():
        name = entries["crop"].get().strip()
        qty_raw = entries["qty"].get().strip()
        price_raw = entries["price"].get().strip()
        if not name or name == "No crops yet" or not qty_raw or not price_raw:
            return
        try:
            qty = float(qty_raw)
            price = float(price_raw)
        except ValueError:
            return

        db.add_sale(name, qty, price, entries["date"].get().strip(),
                    state["name_to_id"].get(name))
        entries["qty"].delete(0, "end")
        entries["price"].delete(0, "end")
        refresh()

    def edit_handler(sale):
        edit_names, edit_map = crop_lookup()
        values = list(edit_names)
        if sale["crop_name"] and sale["crop_name"] not in values:
            values.insert(0, sale["crop_name"])
        if not values:
            values = [sale["crop_name"] or ""]

        fields = [
            {"key": "crop_name", "label": "Crop", "kind": "menu", "values": values,
             "value": sale["crop_name"]},
            {"key": "quantity", "label": "Quantity", "value": f"{sale['quantity']:g}"},
            {"key": "price", "label": "Price per unit (₹)", "value": f"{sale['price']:g}"},
            {"key": "sale_date", "label": "Sale date (YYYY-MM-DD)", "value": sale["sale_date"]},
        ]

        def save(v):
            try:
                qty = float(v["quantity"])
                price = float(v["price"])
            except ValueError:
                return
            crop_id = edit_map.get(v["crop_name"])
            if crop_id is None and v["crop_name"] == sale["crop_name"]:
                crop_id = sale["crop_id"]
            db.update_sale(
                sale["id"], v["crop_name"], qty, price, v["sale_date"], crop_id
            )
            refresh()

        open_form_dialog("Edit Sale", fields, save)

    def delete_handler(sale_id):
        db.delete_sale(sale_id)
        refresh()

    def export_csv():
        rows = state["rows"]
        if not rows:
            flash(feedback, "Nothing to export.", WARN)
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile="sales.csv", title="Export sales to CSV"
        )
        if not path:
            return
        save_csv(path, ["Crop", "Quantity", "Price", "Total", "Date"], [
            [s["crop_name"], s["quantity"], s["price"],
             s["quantity"] * s["price"], s["sale_date"]] for s in rows
        ])
        flash(feedback, f"Exported {len(rows)} sale(s) to CSV.")

    def export_pdf():
        rows = state["rows"]
        if not rows:
            flash(feedback, "Nothing to export.", WARN)
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF", "*.pdf")],
            initialfile="sales.pdf", title="Export sales to PDF"
        )
        if not path:
            return
        save_pdf(path, "Farm Sales Report", ["Crop", "Quantity", "Price", "Total", "Date"], [
            [s["crop_name"], f"{s['quantity']:g}", f"₹{s['price']:g}",
             f"₹{s['quantity'] * s['price']:,.0f}", s["sale_date"]] for s in rows
        ])
        flash(feedback, f"Exported {len(rows)} sale(s) to PDF.")

    bind_form_enter(entries, add_handler)
    refresh()
    refresh_callbacks["Sales"] = refresh
    return page


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------

def build_expenses_page(container, refresh_callbacks):
    page = ctk.CTkFrame(container, fg_color="transparent")
    make_page_header(page, "Expenses", subtitle="Track costs and spending")

    state = {"rows": [], "crop_to_id": {}, "crop_id_to_name": {}}

    crops = db.get_crops()
    crop_names = sorted({c["name"] for c in crops}, key=str.lower)
    state["crop_to_id"] = {c["name"]: c["id"] for c in crops}
    state["crop_id_to_name"] = {c["id"]: c["name"] for c in crops}
    crop_options = ["— None —"] + crop_names

    form = make_form_card(page)
    entries = build_inline_form(form, [
        {"key": "cat", "kind": "menu", "values": db.EXPENSE_CATEGORIES,
         "width": 150, "row": 0, "col": 0},
        {"key": "amount", "placeholder": "Amount (₹)", "width": 120, "row": 0, "col": 1},
        {"key": "date", "placeholder": "Date", "width": 130,
         "value": date.today().isoformat(), "row": 0, "col": 2},
        {"key": "desc", "placeholder": "Description", "width": 240, "row": 1, "col": 0},
        {"key": "crop", "kind": "menu", "values": crop_options, "width": 160,
         "row": 1, "col": 1},
    ])
    add_form_button(
        form, "+  Record Expense", lambda: add_handler(), column=2, row=1,
        color=DANGER, hover=DANGER_HOVER, width=160
    )
    scan_btn = ctk.CTkButton(
        form, text="📷  Scan bill", width=130, height=38, corner_radius=9,
        fg_color=BLUE, hover_color="#1565C0", font=(FONT, 13, "bold"),
        command=lambda: scan_bill()
    )
    scan_btn.grid(row=0, column=3, padx=(12, 16), pady=(14, 4), sticky="w")

    total_label = ctk.CTkLabel(page, text="", font=(FONT, 15, "bold"), text_color=DANGER)
    total_label.pack(anchor="e", pady=(0, 6))

    feedback = ctk.CTkLabel(page, text="", font=(FONT, 12), text_color=PRIMARY)
    feedback.pack(anchor="e", pady=(0, 6))

    filters = build_filter_bar(
        page, EXPENSE_SORTS, lambda: refresh(), lambda: export_csv(), lambda: export_pdf()
    )

    list_frame = make_list_area(page)

    def refresh():
        for widget in list_frame.winfo_children():
            widget.destroy()

        fresh_crops = db.get_crops()
        fresh_names = sorted({c["name"] for c in fresh_crops}, key=str.lower)
        state["crop_to_id"] = {c["name"]: c["id"] for c in fresh_crops}
        state["crop_id_to_name"] = {c["id"]: c["name"] for c in fresh_crops}
        current_crop = entries["crop"].get()
        entries["crop"].configure(values=["— None —"] + fresh_names)
        if current_crop in fresh_names or current_crop == "— None —":
            entries["crop"].set(current_crop)
        else:
            entries["crop"].set("— None —")

        expenses = db.get_expenses()
        filtered = apply_filters(
            expenses,
            filters["search"].get(),
            ["category", "description"],
            "expense_date",
            filters["date_from"].get(),
            filters["date_to"].get(),
        )

        sort = filters["sort"].get()
        if sort == "Newest first":
            filtered.sort(key=lambda e: str(e["expense_date"] or ""), reverse=True)
        elif sort == "Oldest first":
            filtered.sort(key=lambda e: str(e["expense_date"] or ""))
        elif sort == "Highest amount":
            filtered.sort(key=lambda e: e["amount"], reverse=True)
        elif sort == "Lowest amount":
            filtered.sort(key=lambda e: e["amount"])
        elif sort == "Category A-Z":
            filtered.sort(key=lambda e: str(e["category"]).lower())

        state["rows"] = filtered
        shown_total = sum(e["amount"] for e in filtered)
        total_label.configure(
            text=f"Showing {len(filtered)} expense(s)    ₹{shown_total:,.0f}"
        )

        if not filtered:
            ctk.CTkLabel(
                list_frame, text="No expenses match your filters.", font=(FONT, 13),
                text_color=SUBTEXT
            ).pack(pady=40)
            return

        for expense in filtered:
            row = ctk.CTkFrame(
                list_frame, fg_color=BG_CARD, corner_radius=12,
                border_width=1, border_color=BORDER
            )
            row.pack(fill="x", pady=5, padx=4)
            row.grid_columnconfigure(5, weight=1)

            ctk.CTkLabel(
                row, text=expense["category"], font=(FONT, 14, "bold"),
                text_color=TEXT, anchor="w"
            ).grid(row=0, column=0, padx=(16, 8), pady=12, sticky="w")

            subtitle = expense["description"] or ""
            linked = state["crop_id_to_name"].get(expense["crop_id"])
            if linked:
                subtitle = (subtitle + "  ·  " if subtitle else "") + f"🌱 {linked}"
            if subtitle:
                ctk.CTkLabel(
                    row, text=subtitle, font=(FONT, 13), text_color=SUBTEXT,
                    anchor="w"
                ).grid(row=1, column=0, padx=(16, 8), pady=(0, 12), sticky="w")

            ctk.CTkLabel(
                row, text=f"₹{expense['amount']:,.0f}", font=(FONT, 15, "bold"),
                text_color=DANGER, anchor="w"
            ).grid(row=0, column=2, padx=8, sticky="w")

            ctk.CTkLabel(
                row, text=expense["expense_date"], font=(FONT, 12),
                text_color=SUBTEXT, anchor="e"
            ).grid(row=1, column=2, padx=8, pady=(0, 12), sticky="e")

            make_row_actions(
                row,
                lambda e=expense: edit_handler(e),
                lambda eid=expense["id"]: delete_handler(eid),
                column=6, rowspan=2
            )

    def add_handler():
        cat = entries["cat"].get().strip()
        amount_raw = entries["amount"].get().strip()
        if not cat or not amount_raw:
            return
        try:
            amount = float(amount_raw)
        except ValueError:
            return
        crop_value = entries["crop"].get().strip()
        crop_id = state["crop_to_id"].get(crop_value)

        db.add_expense(
            cat, amount, entries["date"].get().strip(),
            entries["desc"].get().strip(), crop_id
        )
        entries["amount"].delete(0, "end")
        entries["desc"].delete(0, "end")
        refresh()

    def edit_handler(expense):
        current_crops = db.get_crops()
        names = sorted({c["name"] for c in current_crops}, key=str.lower)
        options = ["— None —"] + names
        current_name = state["crop_id_to_name"].get(expense["crop_id"])
        if current_name and current_name not in options:
            options.append(current_name)

        fields = [
            {"key": "category", "label": "Category", "kind": "menu",
             "values": db.EXPENSE_CATEGORIES,
             "value": expense["category"] if expense["category"] in db.EXPENSE_CATEGORIES
             else db.EXPENSE_CATEGORIES[0]},
            {"key": "amount", "label": "Amount (₹)", "value": f"{expense['amount']:g}"},
            {"key": "expense_date", "label": "Date (YYYY-MM-DD)", "value": expense["expense_date"]},
            {"key": "description", "label": "Description", "value": expense["description"]},
            {"key": "crop", "label": "Linked crop", "kind": "menu", "values": options,
             "value": current_name or "— None —"},
        ]

        def save(v):
            try:
                amount = float(v["amount"])
            except ValueError:
                return
            crop_id = None
            if v["crop"] != "— None —":
                crop_id = {c["name"]: c["id"] for c in current_crops}.get(v["crop"])
                if crop_id is None and v["crop"] == current_name:
                    crop_id = expense["crop_id"]
            db.update_expense(
                expense["id"], v["category"], amount, v["expense_date"],
                v["description"], crop_id
            )
            refresh()

        open_form_dialog("Edit Expense", fields, save)

    def delete_handler(expense_id):
        db.delete_expense(expense_id)
        refresh()

    def scan_bill():
        path = filedialog.askopenfilename(
            title="Choose a bill photo", filetypes=IMAGE_FILETYPES
        )
        if not path:
            return
        scan_btn.configure(state="disabled", text="Scanning…")
        flash(feedback, "Reading the bill with Gemini vision…", SUBTEXT)

        def worker():
            try:
                result = aiModule.scan_receipt(path)
            except Exception as exc:
                result = {"ok": False, "error": f"Could not read the bill: {exc}"}
            app.after(0, lambda: apply_scan(result))

        threading.Thread(target=worker, daemon=True).start()

    def apply_scan(result):
        scan_btn.configure(state="normal", text="📷  Scan bill")
        if not result.get("ok"):
            flash(feedback, result.get("error", "Could not read the bill."), DANGER)
            return
        if result.get("category"):
            entries["cat"].set(result["category"])
        if result.get("amount") is not None:
            entries["amount"].delete(0, "end")
            entries["amount"].insert(0, f"{result['amount']:g}")
        if result.get("date"):
            entries["date"].delete(0, "end")
            entries["date"].insert(0, result["date"])
        if result.get("description"):
            entries["desc"].delete(0, "end")
            entries["desc"].insert(0, result["description"])

        confidence = result.get("confidence")
        low = isinstance(confidence, (int, float)) and confidence < 0.5
        if low:
            flash(feedback, "Bill scanned but confidence is low — please double-check the fields.", WARN)
        else:
            flash(feedback, "Bill scanned — review the fields, then click Record Expense.")

    def export_csv():
        rows = state["rows"]
        if not rows:
            flash(feedback, "Nothing to export.", WARN)
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile="expenses.csv", title="Export expenses to CSV"
        )
        if not path:
            return
        save_csv(path, ["Category", "Amount", "Date", "Description", "Crop"], [
            [e["category"], e["amount"], e["expense_date"], e["description"] or "",
             state["crop_id_to_name"].get(e["crop_id"], "")] for e in rows
        ])
        flash(feedback, f"Exported {len(rows)} expense(s) to CSV.")

    def export_pdf():
        rows = state["rows"]
        if not rows:
            flash(feedback, "Nothing to export.", WARN)
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF", "*.pdf")],
            initialfile="expenses.pdf", title="Export expenses to PDF"
        )
        if not path:
            return
        save_pdf(path, "Farm Expenses Report",
                 ["Category", "Amount", "Date", "Description", "Crop"], [
            [e["category"], f"₹{e['amount']:,.0f}", e["expense_date"],
             e["description"] or "", state["crop_id_to_name"].get(e["crop_id"], "")] for e in rows
        ])
        flash(feedback, f"Exported {len(rows)} expense(s) to PDF.")

    bind_form_enter(entries, add_handler)
    refresh()
    refresh_callbacks["Expenses"] = refresh
    return page


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def build_charts_page(container, refresh_callbacks):
    page = ctk.CTkFrame(container, fg_color="transparent")
    make_page_header(page, "Charts", subtitle="Visual insights into your farm finances")

    body = ctk.CTkScrollableFrame(page, fg_color="transparent", corner_radius=0)
    body.pack(fill="both", expand=True)

    monthly_fig = Figure(figsize=(8.4, 3.3), dpi=100, facecolor=BG_CARD)
    monthly_canvas = FigureCanvasTkAgg(monthly_fig, master=body)
    monthly_widget = monthly_canvas.get_tk_widget()
    monthly_widget.configure(bg=BG_CARD, highlightthickness=0)
    monthly_widget.pack(fill="x", pady=(0, 18))

    category_fig = Figure(figsize=(8.4, 3.3), dpi=100, facecolor=BG_CARD)
    category_canvas = FigureCanvasTkAgg(category_fig, master=body)
    category_widget = category_canvas.get_tk_widget()
    category_widget.configure(bg=BG_CARD, highlightthickness=0)
    category_widget.pack(fill="x", pady=(0, 18))

    def draw():
        monthly_fig.clear()
        axis = monthly_fig.add_subplot(111)
        data = db.get_monthly_totals()

        if data:
            months = [row[0] for row in data]
            sales = [row[1] for row in data]
            expenses = [row[2] for row in data]
            positions = range(len(months))
            width = 0.4

            axis.bar([p - width / 2 for p in positions], sales, width,
                     label="Sales", color=PRIMARY)
            axis.bar([p + width / 2 for p in positions], expenses, width,
                     label="Expenses", color=DANGER)
            axis.set_xticks(list(positions))
            axis.set_xticklabels(months, rotation=30, ha="right", fontsize=9)
            axis.set_title("Monthly Sales vs Expenses", fontsize=12, fontweight="bold")
            axis.set_ylabel("₹", fontsize=10)
            axis.legend(fontsize=9)
            axis.grid(axis="y", alpha=0.25)
            axis.set_facecolor(BG_CARD)
        else:
            axis.text(0.5, 0.5, "No financial data yet", ha="center", va="center",
                      fontsize=12, color=SUBTEXT)
            axis.axis("off")

        monthly_fig.tight_layout()
        monthly_canvas.draw()

        category_fig.clear()
        axis2 = category_fig.add_subplot(111)
        categories = db.get_expenses_by_category()

        if categories:
            labels = [row[0] for row in categories]
            values = [row[1] for row in categories]
            colors = [PIE_COLORS[i % len(PIE_COLORS)] for i in range(len(labels))]
            axis2.pie(
                values, labels=labels, autopct="%1.0f%%", startangle=90,
                colors=colors, textprops={"fontsize": 9}
            )
            axis2.set_title("Expenses by Category", fontsize=12, fontweight="bold")
            axis2.axis("equal")
        else:
            axis2.text(0.5, 0.5, "No expenses recorded yet", ha="center",
                       va="center", fontsize=12, color=SUBTEXT)
            axis2.axis("off")

        category_fig.tight_layout()
        category_canvas.draw()

    refresh_callbacks["Charts"] = draw
    draw()
    return page


# ---------------------------------------------------------------------------
# AI Assistant
# ---------------------------------------------------------------------------

_AI_LANGUAGES = {
    "English": "en",
    "हिन्दी": "hi",
    "मराठी": "mr",
    "తెలుగు": "te",
}

_AI_WELCOME = (
    "Hello! I'm FarmOS AI 🌾 I can see your live farm data and also update it "
    "for you.\n\nTry a quick question above, type naturally (like \"sold 40 kg "
    "onions at 22 yesterday\"), or tap 🎙 to speak. I'll always ask for "
    "confirmation before saving anything."
)


def _record_with_sounddevice(recognizer, duration=5, rate=16000):
    import numpy as np
    import sounddevice as sd
    import speech_recognition as sr

    frames = sd.rec(int(duration * rate), samplerate=rate, channels=1, dtype="int16")
    sd.wait()
    return sr.AudioData(np.asarray(frames).tobytes(), rate, 2)


def transcribe_speech(locale="en-IN", duration=5):
    """Record from the microphone and return recognised text. Raises on failure."""
    import speech_recognition as sr

    recognizer = sr.Recognizer()
    try:
        mic = sr.Microphone()
        with mic as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(
                source, timeout=duration, phrase_time_limit=duration
            )
    except AttributeError:
        audio = _record_with_sounddevice(recognizer, duration=duration)
    return recognizer.recognize_google(audio, language=locale)


def build_ai_page(container, refresh_callbacks, username="guest"):
    page = ctk.CTkFrame(container, fg_color="transparent")

    head = ctk.CTkFrame(page, fg_color="transparent")
    head.pack(fill="x", pady=(0, 10))
    title_col = ctk.CTkFrame(head, fg_color="transparent")
    title_col.pack(side="left")
    ctk.CTkLabel(
        title_col, text="AI Assistant", font=(FONT, 26, "bold"),
        text_color=TEXT, anchor="w"
    ).pack(anchor="w")
    ctk.CTkLabel(
        title_col,
        text="Ask, type naturally, or speak — it can read and update your farm",
        font=(FONT, 12), text_color=SUBTEXT, anchor="w"
    ).pack(anchor="w", pady=(2, 0))

    connected = aiModule.is_ai_configured()
    badge_text = "● Gemini connected" if connected else "● Local mode (set GEMINI_API_KEY)"
    badge_fg = PRIMARY if connected else WARN
    badge_bg = INFO_BG if connected else WARN_BG
    badge = make_badge(head, badge_text, badge_fg, badge_bg)
    badge.pack(side="right")

    controls = ctk.CTkFrame(page, fg_color="transparent")
    controls.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(
        controls, text="Reply language", font=(FONT, 12), text_color=SUBTEXT
    ).pack(side="left", padx=(0, 8))
    language_menu = ctk.CTkOptionMenu(
        controls, values=list(_AI_LANGUAGES.keys()), width=140, height=32,
        corner_radius=10, fg_color=BG_CARD, button_color="#DCE6DC",
        button_hover_color="#CBD8CB", text_color=TEXT, font=(FONT, 12),
        dropdown_font=(FONT, 12)
    )
    language_menu.set("English")
    language_menu.pack(side="left")

    suggestions = ctk.CTkScrollableFrame(
        page, fg_color="transparent", orientation="horizontal",
        height=44, corner_radius=0
    )
    suggestions.pack(fill="x", pady=(0, 10))

    quick_prompts = [
        "🤖 Analyze my farm",
        "💰 How is my profit?",
        "🌱 Which crops need care?",
        "📦 Low stock items",
        "📅 What's due this week?",
        "🌤 Weather farming advice",
    ]
    for prompt in quick_prompts:
        ctk.CTkButton(
            suggestions, text=prompt, height=34, corner_radius=17,
            fg_color=BG_CARD, hover_color="#E6EDE7", text_color=TEXT,
            border_width=1, border_color="#DCE6DC",
            font=(FONT, 12), command=lambda p=prompt: quick_send(p)
        ).pack(side="left", padx=4)

    chat_frame = ctk.CTkScrollableFrame(
        page, fg_color="transparent", corner_radius=0
    )
    chat_frame.pack(fill="both", expand=True, pady=(0, 8))

    typing_ref = {"widget": None}
    state = {"busy": False}

    def scroll_to_bottom():
        chat_frame._parent_canvas.yview_moveto(1.0)

    def persist(role, text):
        try:
            db.add_chat_message(username, role, text)
        except Exception:
            pass

    def load_history():
        try:
            return [
                {"role": m["role"], "text": m["text"]}
                for m in db.get_chat_messages(username, limit=40)
            ]
        except Exception:
            return []

    def add_message(role, text):
        row = ctk.CTkFrame(chat_frame, fg_color="transparent")
        row.pack(fill="x", pady=5)

        is_user = role == "You"
        bubble = ctk.CTkFrame(
            row, corner_radius=14,
            fg_color=PRIMARY if is_user else BG_CARD,
            border_width=0 if is_user else 1,
            border_color=BORDER
        )
        bubble.pack(side="right" if is_user else "left", anchor="e" if is_user else "w")

        ctk.CTkLabel(
            bubble, text=text, font=(FONT, 13), justify="left",
            text_color="white" if is_user else TEXT, anchor="w",
            wraplength=620
        ).pack(padx=16, pady=10)

        scroll_to_bottom()

    def add_action_card(action):
        row = ctk.CTkFrame(chat_frame, fg_color="transparent")
        row.pack(fill="x", pady=5)
        card = ctk.CTkFrame(
            row, corner_radius=14, fg_color="#FFFDF5",
            border_width=1, border_color="#EAD9A8"
        )
        card.pack(side="left", anchor="w")
        ctk.CTkLabel(
            card, text="⚠  Confirmation needed", font=(FONT, 11, "bold"),
            text_color="#8A6D00"
        ).pack(anchor="w", padx=16, pady=(10, 0))
        ctk.CTkLabel(
            card, text=action["summary"], font=(FONT, 13), text_color=TEXT,
            justify="left", anchor="w", wraplength=560
        ).pack(anchor="w", padx=16, pady=(4, 8))

        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(anchor="w", padx=12, pady=(0, 12))

        def decide(confirm):
            confirm_btn.configure(state="disabled")
            cancel_btn.configure(state="disabled")
            try:
                card.destroy()
            except Exception:
                pass
            if not confirm:
                add_message("AI", "Cancelled — nothing was saved.")
                persist("model", "Cancelled — nothing was saved.")
                return
            add_message("You", "confirm")
            persist("user", "confirm")

            def work():
                try:
                    result = aiModule.execute_pending_action(action)
                except Exception as exc:
                    result = f"Sorry, I couldn't save that: {exc}"
                app.after(0, lambda: finish_result_text(result))

            threading.Thread(target=work, daemon=True).start()

        confirm_btn = ctk.CTkButton(
            btns, text="Confirm", width=92, height=32, corner_radius=16,
            fg_color=PRIMARY, hover_color=PRIMARY_DARK, font=(FONT, 12, "bold"),
            command=lambda: decide(True)
        )
        confirm_btn.pack(side="left")
        cancel_btn = ctk.CTkButton(
            btns, text="Cancel", width=92, height=32, corner_radius=16,
            fg_color="transparent", text_color=SUBTEXT, hover_color="#E6EDE7",
            border_width=1, border_color="#DCE6DC", font=(FONT, 12),
            command=lambda: decide(False)
        )
        cancel_btn.pack(side="left", padx=(8, 0))
        scroll_to_bottom()

    def show_typing():
        remove_typing()
        row = ctk.CTkFrame(chat_frame, fg_color="transparent")
        row.pack(fill="x", pady=5)
        bubble = ctk.CTkFrame(
            row, corner_radius=14, fg_color=BG_CARD,
            border_width=1, border_color=BORDER
        )
        bubble.pack(side="left", anchor="w")
        label = ctk.CTkLabel(
            bubble, text="AI is thinking", font=(FONT, 13),
            text_color=SUBTEXT
        )
        label.pack(padx=16, pady=10)
        typing_ref["widget"] = label
        scroll_to_bottom()

    def remove_typing():
        widget = typing_ref["widget"]
        if widget is not None:
            try:
                widget.master.destroy()
            except Exception:
                pass
            typing_ref["widget"] = None

    def set_busy(busy):
        state["busy"] = busy
        send_btn.configure(state="disabled" if busy else "normal")
        input_entry.configure(state="disabled" if busy else "normal")
        voice_btn.configure(state="disabled" if busy else "normal")

    def finish_result_text(text):
        remove_typing()
        set_busy(False)
        add_message("AI", text)
        persist("model", text)
        refresh_callbacks["Dashboard"]()

    def finish_result(result):
        remove_typing()
        set_busy(False)
        text = (result.get("text") or "").strip()
        if result.get("type") == "action" and result.get("actions"):
            if text:
                add_message("AI", text)
                persist("model", text)
            for action in result["actions"]:
                add_action_card(action)
        else:
            text = text or "(no reply)"
            add_message("AI", text)
            persist("model", text)
        refresh_callbacks["Dashboard"]()

    def send(text=None):
        message = (text if text is not None else input_entry.get()).strip()
        if not message or state["busy"]:
            return

        language = _AI_LANGUAGES.get(language_menu.get(), "en")
        history = load_history()

        input_entry.delete(0, "end")
        set_busy(True)
        add_message("You", message)
        persist("user", message)
        show_typing()

        def worker():
            try:
                result = aiModule.agent_reply(message, history, language)
            except Exception as exc:
                result = {"type": "text", "text": f"Sorry, something went wrong: {exc}"}
            app.after(0, lambda: finish_result(result))

        threading.Thread(target=worker, daemon=True).start()

    def quick_send(prompt):
        clean = prompt.split(" ", 1)[1].strip()
        send(clean)

    def voice_input():
        if state["busy"]:
            return
        set_busy(True)
        voice_btn.configure(text="🎙…")
        input_entry.configure(placeholder_text="🎤 Listening… speak now")
        locale = aiModule.speech_locale(_AI_LANGUAGES.get(language_menu.get(), "en"))

        def worker():
            try:
                spoken = transcribe_speech(locale)
                app.after(0, lambda: voice_done(spoken, None))
            except Exception as exc:
                app.after(0, lambda: voice_done(None, exc))

        threading.Thread(target=worker, daemon=True).start()

    def voice_done(text, error):
        voice_btn.configure(text="🎙")
        input_entry.configure(placeholder_text=PLACEHOLDER)
        set_busy(False)
        if error is not None or not text:
            reason = str(error) if error else "no speech detected"
            add_message("AI", f"Couldn't catch that ({reason}). Please try again or type it.")
            return
        send(text)

    def clear_history():
        if state["busy"]:
            return
        try:
            db.clear_chat_messages(username)
        except Exception:
            pass
        for widget in chat_frame.winfo_children():
            widget.destroy()
        typing_ref["widget"] = None
        add_message("AI", _AI_WELCOME)
        scroll_to_bottom()

    ctk.CTkButton(
        controls, text="🗑  Clear chat", width=110, height=32, corner_radius=16,
        fg_color="transparent", text_color=SUBTEXT, hover_color="#E6EDE7",
        border_width=1, border_color="#DCE6DC", font=(FONT, 12),
        command=clear_history
    ).pack(side="right")

    PLACEHOLDER = "Ask about crops, profit, inventory, weather..."
    input_row = ctk.CTkFrame(page, fg_color="transparent")
    input_row.pack(fill="x", pady=(4, 2))

    input_entry = ctk.CTkEntry(
        input_row, placeholder_text=PLACEHOLDER,
        height=46, corner_radius=12, border_color="#CBD8CB", font=(FONT, 13)
    )
    input_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
    input_entry.bind("<Return>", lambda e: send())

    send_btn = ctk.CTkButton(
        input_row, text="Send ➤", width=110, height=46, corner_radius=12,
        fg_color=PRIMARY, hover_color=PRIMARY_DARK, font=(FONT, 13, "bold"),
        command=lambda: send()
    )
    send_btn.pack(side="right")

    voice_btn = ctk.CTkButton(
        input_row, text="🎙", width=52, height=46, corner_radius=12,
        fg_color=BG_CARD, hover_color="#E6EDE7", text_color=TEXT,
        border_width=1, border_color="#DCE6DC", font=(FONT, 16),
        command=voice_input
    )
    voice_btn.pack(side="right", padx=(0, 10))

    existing = load_history()
    if existing:
        for msg in existing:
            add_message("You" if msg["role"] == "user" else "AI", msg["text"])
    else:
        add_message("AI", _AI_WELCOME)

    refresh_callbacks["AI Assistant"] = lambda: None
    return page


# ---------------------------------------------------------------------------
# App shell
# ---------------------------------------------------------------------------

nav_buttons = {}


def build_main_app(username):
    nav_buttons.clear()
    sidebar = ctk.CTkFrame(
        app, width=230, height=750, corner_radius=0, fg_color=SIDEBAR
    )
    sidebar.pack(side="left", fill="y")
    sidebar.pack_propagate(False)

    logo = ctk.CTkFrame(sidebar, fg_color="transparent")
    logo.pack(fill="x", padx=20, pady=(36, 30))
    ctk.CTkLabel(
        logo, text="🌾", font=(FONT, 34), text_color=ACCENT
    ).pack()
    ctk.CTkLabel(
        logo, text="FARMOS", font=(FONT, 21, "bold"), text_color="white"
    ).pack(pady=(6, 0))
    ctk.CTkLabel(
        logo, text="Farm Management", font=(FONT, 11),
        text_color="#9DB8A9"
    ).pack()

    ctk.CTkLabel(
        sidebar, text="MENU", font=(FONT, 10, "bold"),
        text_color="#6E8B7A", anchor="w"
    ).pack(fill="x", padx=24, pady=(0, 8))

    nav_container = ctk.CTkFrame(sidebar, fg_color="transparent")
    nav_container.pack(fill="x", padx=12)

    main = ctk.CTkFrame(app, fg_color=BG, corner_radius=0)
    main.pack(side="left", fill="both", expand=True, padx=30, pady=24)

    topbar = ctk.CTkFrame(main, fg_color="transparent")
    topbar.pack(fill="x", pady=(0, 16))

    user_chip = ctk.CTkFrame(
        topbar, fg_color=BG_CARD, corner_radius=22,
        border_width=1, border_color=BORDER
    )
    user_chip.pack(side="left")
    avatar = ctk.CTkFrame(
        user_chip, width=32, height=32, corner_radius=16, fg_color=PRIMARY
    )
    avatar.pack(side="left", padx=(6, 8), pady=4)
    avatar.pack_propagate(False)
    ctk.CTkLabel(
        avatar, text=username[0].upper(), font=(FONT, 14, "bold"),
        text_color="white"
    ).pack(expand=True)
    ctk.CTkLabel(
        user_chip, text=f"Welcome, {username}", font=(FONT, 13, "bold"),
        text_color=TEXT
    ).pack(side="left", padx=(0, 16))

    ctk.CTkButton(
        topbar, text="Logout  ➜", width=100, height=34, corner_radius=17,
        fg_color="transparent", text_color=SUBTEXT, hover_color="#E6EDE7",
        font=(FONT, 12, "bold"), command=logout
    ).pack(side="right")

    container = ctk.CTkFrame(main, fg_color="transparent")
    container.pack(fill="both", expand=True)

    pages = {}
    refresh_callbacks = {}

    pages["Dashboard"] = build_dashboard_page(container, refresh_callbacks)
    pages["Weather"] = build_weather_page(container, refresh_callbacks)
    pages["AI Assistant"] = build_ai_page(container, refresh_callbacks, username)
    pages["Crops"] = build_crops_page(container, refresh_callbacks)
    pages["Inventory"] = build_inventory_page(container, refresh_callbacks)
    pages["Sales"] = build_sales_page(container, refresh_callbacks)
    pages["Expenses"] = build_expenses_page(container, refresh_callbacks)

    for page in pages.values():
        page.place(relwidth=1, relheight=1)

    def set_nav_active(active_item):
        for item, btn in nav_buttons.items():
            if item == active_item:
                btn.configure(fg_color=PRIMARY, text_color="white")
            else:
                btn.configure(fg_color="transparent", text_color="#B8CEBF")

    def show_page(name):
        if name not in pages:
            return
        page = pages[name]
        page.lift()
        set_nav_active(name)
        if name in refresh_callbacks:
            try:
                refresh_callbacks[name]()
            except Exception:
                # A failed network-backed refresh must not block navigation.
                pass

    for item in menu_items:
        btn = ctk.CTkButton(
            nav_container, text=f"{MENU_ICONS[item]}  {item}",
            width=190, height=44, corner_radius=10,
            fg_color="transparent", text_color="#B8CEBF",
            hover_color=SIDEBAR_DIM, anchor="w",
            font=(FONT, 14, "bold"), command=lambda x=item: show_page(x)
        )
        btn.pack(pady=3)
        nav_buttons[item] = btn

    show_page("Dashboard")


def logout():
    clear_window()
    show_login_screen()


def show_login_screen():
    clear_window()

    wrapper = ctk.CTkFrame(app, fg_color=BG)
    wrapper.pack(fill="both", expand=True)

    left_panel = ctk.CTkFrame(wrapper, width=420, fg_color=SIDEBAR)
    left_panel.pack(side="left", fill="y")
    left_panel.pack_propagate(False)

    left_inner = ctk.CTkFrame(left_panel, fg_color=SIDEBAR)
    left_inner.place(relx=0.5, rely=0.5, anchor="center")

    ctk.CTkLabel(
        left_inner, text="🌾", font=(FONT, 58), text_color=ACCENT
    ).pack()
    ctk.CTkLabel(
        left_inner, text="FARMOS", font=(FONT, 30, "bold"),
        text_color="white"
    ).pack(pady=(10, 4))
    ctk.CTkLabel(
        left_inner, text="Smart farm management made simple",
        font=(FONT, 14), text_color="#9DB8A9"
    ).pack()
    ctk.CTkLabel(
        left_inner, text="Crops  ·  Inventory  ·  Sales  ·  Expenses",
        font=(FONT, 12), text_color="#6E8B7A"
    ).pack(pady=(18, 0))

    right = ctk.CTkFrame(wrapper, fg_color=BG)
    right.pack(side="left", fill="both", expand=True)

    card = ctk.CTkFrame(
        right, width=390, height=470, corner_radius=18, fg_color=BG_CARD,
        border_width=1, border_color=BORDER
    )
    card.place(relx=0.5, rely=0.5, anchor="center")
    card.pack_propagate(False)

    ctk.CTkLabel(
        card, text="Welcome back 👋", font=(FONT, 22, "bold"),
        text_color=TEXT
    ).pack(pady=(42, 4))
    ctk.CTkLabel(
        card, text="Sign in to manage your farm",
        font=(FONT, 13), text_color=SUBTEXT
    ).pack(pady=(0, 28))

    username_entry = ctk.CTkEntry(
        card, placeholder_text="Username", width=300, height=42,
        corner_radius=10, border_color="#CBD8CB"
    )
    username_entry.pack(pady=8)

    password_entry = ctk.CTkEntry(
        card, placeholder_text="Password", show="*", width=300, height=42,
        corner_radius=10, border_color="#CBD8CB"
    )
    password_entry.pack(pady=8)

    error_label = ctk.CTkLabel(
        card, text="", font=(FONT, 12), text_color=DANGER, wraplength=290
    )
    error_label.pack(pady=(10, 0))

    def do_login():
        username = username_entry.get().strip()
        password = password_entry.get()

        if not username or not password:
            error_label.configure(
                text="Enter username and password", text_color=DANGER)
            return

        if db.verify_user(username, password):
            clear_window()
            build_main_app(username)
        else:
            error_label.configure(
                text="Invalid username or password", text_color=DANGER)

    def do_register():
        username = username_entry.get().strip()
        password = password_entry.get()

        if not username or not password:
            error_label.configure(
                text="Enter username and password", text_color=DANGER)
            return

        if len(password) < 4:
            error_label.configure(
                text="Password must be at least 4 characters",
                text_color=DANGER)
            return

        if db.create_user(username, password):
            error_label.configure(
                text="Account created — click Login", text_color=PRIMARY)
        else:
            error_label.configure(
                text="Username already taken", text_color=DANGER)

    ctk.CTkButton(
        card, text="Login", width=300, height=42, corner_radius=10,
        fg_color=PRIMARY, hover_color=PRIMARY_DARK,
        font=(FONT, 14, "bold"), command=do_login
    ).pack(pady=(18, 10))

    divider = ctk.CTkFrame(card, height=1, fg_color=BORDER)
    divider.pack(fill="x", padx=40, pady=(4, 10))

    ctk.CTkButton(
        card, text="Create Account", width=300, height=42, corner_radius=10,
        fg_color="transparent", border_width=1, border_color=PRIMARY,
        text_color=PRIMARY, hover_color="#E8F5E9",
        font=(FONT, 13, "bold"), command=do_register
    ).pack(pady=4)

    username_entry.bind("<Return>", lambda e: do_login())
    password_entry.bind("<Return>", lambda e: do_login())
    username_entry.focus()


show_login_screen()
app.mainloop()

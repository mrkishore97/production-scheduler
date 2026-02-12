import re

STATUS_COLORS = {
    "open": {"backgroundColor": "#2563eb", "borderColor": "#1d4ed8", "textColor": "#ffffff"},
    "in progress": {"backgroundColor": "#d97706", "borderColor": "#b45309", "textColor": "#ffffff"},
    "completed": {"backgroundColor": "#16a34a", "borderColor": "#15803d", "textColor": "#ffffff"},
    "on hold": {"backgroundColor": "#6b7280", "borderColor": "#4b5563", "textColor": "#ffffff"},
    "cancelled": {"backgroundColor": "#dc2626", "borderColor": "#b91c1c", "textColor": "#ffffff"},
    "default": {"backgroundColor": "#0f766e", "borderColor": "#115e59", "textColor": "#ffffff"},
}

SOLD_COLORS = {"backgroundColor": "#cbd5e1", "borderColor": "#94a3b8", "textColor": "#475569"}

STATUS_KEYWORDS = {
    "open": ["open", "new", "pending"],
    "in progress": ["in progress", "inprogress", "wip", "started", "working"],
    "completed": ["completed", "complete", "done", "closed", "shipped", "delivered"],
    "on hold": ["on hold", "hold", "paused", "waiting"],
    "cancelled": ["cancelled", "canceled", "void"],
}


def normalize_status_key(status: str) -> str:
    raw = str(status or "").strip().lower()
    if not raw:
        return "default"
    compact = re.sub(r"[^a-z0-9]+", " ", raw).strip()
    if compact in STATUS_COLORS:
        return compact
    for canonical, keywords in STATUS_KEYWORDS.items():
        if any(k in compact for k in keywords):
            return canonical
    return "default"


def status_to_colors(status: str) -> dict:
    return STATUS_COLORS[normalize_status_key(status)]

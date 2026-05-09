"""Patch pages_core.py to expose a rich Masterpiece summary panel.

Run from repo root:

    python scripts/patch_masterpiece_summary_panel.py
    python -m py_compile craftworld_tools/routes/pages_core.py craftworld_tools/services/masterpiece_view_model.py

The patch is intentionally string based because pages_core.py is still a large
legacy migrated function. It imports build_masterpiece_summary_html and passes a
rendered summary panel into templates as `rich_masterpiece_summary_html`.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "craftworld_tools" / "routes" / "pages_core.py"

IMPORT_LINE = "from craftworld_tools.services.masterpiece_view_model import build_masterpiece_summary_html\n"

DETAIL_ASSIGNMENTS = [
    "mp_detail = cached_masterpiece_details",
    "selected_mp = cached_masterpiece_details",
    "masterpiece_detail = cached_masterpiece_details",
    "detail = cached_masterpiece_details",
]

TEMPLATE_INSERT_ANCHORS = [
    "{{ prediction_html|safe }}",
    "{{ selected_masterpiece_html|safe }}",
    "{{ details_html|safe }}",
    "{{ detail_html|safe }}",
]

CONTEXT_ANCHORS = [
    "prediction_html=prediction_html,",
    "selected_masterpiece_html=selected_masterpiece_html,",
    "details_html=details_html,",
    "detail_html=detail_html,",
]


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    original = text

    if IMPORT_LINE not in text:
        lines = text.splitlines(keepends=True)
        insert_at = 0
        for idx, line in enumerate(lines):
            if line.startswith("from ") or line.startswith("import "):
                insert_at = idx + 1
        lines.insert(insert_at, IMPORT_LINE)
        text = "".join(lines)

    if "rich_masterpiece_summary_html" not in text:
        # Add a default near the start of masterpieces_view if possible.
        marker = "def masterpieces_view():\n"
        if marker in text:
            text = text.replace(marker, marker + "    rich_masterpiece_summary_html = \"\"\n", 1)
        else:
            print("Could not find masterpieces_view function marker.")
            return

    # After any cached detail assignment, compute the summary from that variable.
    if "build_masterpiece_summary_html(" not in text:
        changed_assignment = False
        for prefix in DETAIL_ASSIGNMENTS:
            pos = text.find(prefix)
            if pos == -1:
                continue
            line_end = text.find("\n", pos)
            if line_end == -1:
                continue
            line = text[pos:line_end]
            var_name = line.split("=", 1)[0].strip()
            insert = f"\n            rich_masterpiece_summary_html = build_masterpiece_summary_html({var_name})"
            text = text[:line_end] + insert + text[line_end:]
            changed_assignment = True
            break
        if not changed_assignment:
            print("Could not find cached_masterpiece_details assignment to attach summary panel.")

    # Insert panel into content template at the first known anchor.
    if "rich_masterpiece_summary_html|safe" not in text:
        inserted_template = False
        for anchor in TEMPLATE_INSERT_ANCHORS:
            if anchor in text:
                text = text.replace(anchor, "{{ rich_masterpiece_summary_html|safe }}\n" + anchor, 1)
                inserted_template = True
                break
        if not inserted_template:
            print("Could not find template anchor. You may need to place {{ rich_masterpiece_summary_html|safe }} manually.")

    # Pass the variable into render_template_string context.
    if "rich_masterpiece_summary_html=rich_masterpiece_summary_html" not in text:
        inserted_context = False
        for anchor in CONTEXT_ANCHORS:
            if anchor in text:
                text = text.replace(anchor, anchor + "\n            rich_masterpiece_summary_html=rich_masterpiece_summary_html,", 1)
                inserted_context = True
                break
        if not inserted_context:
            # Fallback: add to first content render context after content=.
            anchor = "content=render_template_string("
            if anchor in text:
                print("Could not safely place context variable automatically. Add rich_masterpiece_summary_html manually if needed.")
            else:
                print("Could not find render context anchor.")

    if text == original:
        print("No changes made.")
        return

    TARGET.write_text(text, encoding="utf-8")
    print("Patched Masterpiece summary panel into pages_core.py")


if __name__ == "__main__":
    main()

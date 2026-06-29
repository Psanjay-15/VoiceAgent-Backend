from __future__ import annotations


def admin_final_body(summary: str, action_lines: list[str]) -> str:
    lines = ["Call summary:", summary]
    if action_lines:
        lines += ["", "Actions:"]
        lines.extend(f"- {line}" for line in action_lines)
    return "\n".join(lines)

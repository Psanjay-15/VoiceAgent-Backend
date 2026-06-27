from __future__ import annotations

from app.config import settings


def admin_final_body(summary: str, action_lines: list[str]) -> str:
    lines = ["Call summary:", summary]
    if action_lines:
        lines += ["", "Actions:"]
        lines.extend(f"- {line}" for line in action_lines)
    return "\n".join(lines)


def admin_action_body(action_lines: list[str]) -> str:
    lines = ["Action requested during the call:"]
    lines.extend(f"- {line}" for line in action_lines)
    return "\n".join(lines)


def material_email_body() -> str:
    lines = ["Hi,", "", "Thanks for speaking with us."]
    if settings.business_contact_phone or settings.business_contact_email:
        lines += ["", "Contact details:"]
        if settings.business_contact_phone:
            lines.append(f"Phone: {settings.business_contact_phone}")
        if settings.business_contact_email:
            lines.append(f"Email: {settings.business_contact_email}")
    if settings.brochure_url:
        lines += ["", f"Brochure: {settings.brochure_url}"]
    lines += [
        "",
        "Our team will follow up with you if any more details are needed.",
        "",
        "Regards,",
        "Real Estate Team",
    ]
    return "\n".join(lines)

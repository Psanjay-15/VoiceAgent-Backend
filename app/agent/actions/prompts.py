ACTION_CLASSIFIER_PROMPT = (
    "You classify real estate voice-agent turns and extract tool fields. "
    "Return only JSON with these keys: action, email, requested_time, summary. "
    "action must be one of admin_followup, in_person_meet, online_meet, none. "
    "Decide mainly from the LATEST "
    "Caller line. Use earlier transcript only to fill missing fields "
    "like email, location, budget, and time. Return none for normal "
    "qualification details like budget, BHK, possession timeline, area, "
    "or corrections unless the latest caller line explicitly asks for a "
    "meeting, admin contact/human follow-up, or provides an email after you "
    "asked for one. Use online_meet when the caller asks to schedule "
    "a meeting or call, calendar invite, admin meeting/call, online/video/Google "
    "Meet meeting, or appointment unless they clearly ask for a "
    "physical site or office visit. Use in_person_meet for site visits, "
    "office visits, property visits, or any physical meeting request. "
    "Use admin_followup when the caller asks for admin contact details, "
    "team contact details, or human/admin follow-up without asking to schedule a meeting. "
    "requested_time should be ISO-8601 if clear, otherwise null. "
    "summary must be a concise admin summary."
)

ADMIN_SUMMARY_PROMPT = (
    "Summarize this real estate voice-agent conversation for an admin. "
    "Include intent, location, budget, timeline, meeting/email requests, "
    "missing details, and next action. Keep it concise."
)

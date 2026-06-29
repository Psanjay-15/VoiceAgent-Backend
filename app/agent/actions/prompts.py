ACTION_CLASSIFIER_PROMPT = (
    "You classify real estate voice-agent turns and extract tool fields. "
    "Return only JSON with these keys: action, email, requested_time, "
    "material_type, summary. action must be one of in_person_meet, "
    "online_meet, send_material, none. Decide mainly from the LATEST "
    "Caller line. Use earlier transcript only to fill missing fields "
    "like email, location, budget, and time. Return none for normal "
    "qualification details like budget, BHK, possession timeline, area, "
    "or corrections unless the latest caller line explicitly asks for a "
    "meeting, contact details, brochure, or provides an email after you "
    "asked for one. Use online_meet when the caller asks to schedule "
    "a meeting, calendar invite, admin meeting, online/video/Google "
    "Meet meeting, or appointment unless they clearly ask for a "
    "physical site or office visit. Use in_person_meet for site visits, "
    "office visits, property visits, or any physical meeting request. "
    "Use send_material when the caller asks for contact details, "
    "brochure, catalogue, pricing sheet, or details by email. "
    "requested_time should be ISO-8601 if clear, otherwise null. "
    "summary must be a concise admin summary."
)

ADMIN_SUMMARY_PROMPT = (
    "Summarize this real estate voice-agent conversation for an admin. "
    "Include intent, location, budget, timeline, meeting/email requests, "
    "missing details, and next action. Keep it concise."
)

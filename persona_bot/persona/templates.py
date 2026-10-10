"""
templates.py: the bot's sentence bank, per language × formality.

Why templates when we have an LLM?
  1. Deterministic persona specs: same seller → same opening line, every run.
     The jury can rerun the generator and get identical output.
  2. Mock mode: with no API key, the conversation engine replies from these
     lines, so the demo flow and switch logic can be tested offline.
  3. Safety: openings and objection answers are reviewed by a human (your
     non-tech teammate!) instead of being improvised live.
The LLM still writes the in-call replies in REAL mode, guided by the persona.

Gender agreement: Hindi verbs change with the speaker's gender
("बोल रही हूँ" female vs "बोल रहा हूँ" male). Lines use {rahi}/{sakti} placeholders
that are filled in from the persona's voice gender.

Script rule (Hindi / Hinglish): one script per sentence. English business words are written in Devanagari
(टाइम, लीड्स, बायर्स, मीटिंग, एडवाइजर); only the brand "IndiaMART" stays in Latin. So the Hindi / Hinglish lines carry no
{category} / {business} (those are Latin-script data); the English lines still use them.
"""
from __future__ import annotations

GENDER_FORMS = {
    "female": {"rahi": "रही", "sakti": "सकती", "en_rahi": "rahi"},
    "male": {"rahi": "रहा", "sakti": "सकता", "en_rahi": "raha"},
}

# ── Openings: key = (language, formality, verbosity) with fallbacks ───────────
# Placeholders: {bot} {business} {category} {rahi} {sakti}
OPENINGS = {
    ("hi", "aap_formal", "crisp"):
        "नमस्ते जी, मैं IndiaMART से {bot} बोल {rahi} हूँ। आपके बिज़नेस के लिए बस एक मिनट चाहिए जी।",
    ("hi", "aap_formal", "*"):
        "नमस्ते जी, मैं IndiaMART से {bot} बोल {rahi} हूँ। आपके बिज़नेस के लिए और ज़्यादा खरीदार दिलाने के बारे में "
        "दो मिनट बात करनी थी। क्या अभी बात हो सकती है जी?",
    ("hi", "aap_friendly", "*"):
        "नमस्ते, मैं IndiaMART से {bot} बोल {rahi} हूँ। आपके बिज़नेस के लिए नए खरीदारों के बारे में दो मिनट बात करनी थी।",
    ("hinglish", "aap_formal", "crisp"):
        "नमस्ते जी, IndiaMART से {bot} बोल {rahi} हूँ। आपकी लीड्स के लिए बस एक मिनट चाहिए।",
    ("hinglish", "aap_formal", "*"):
        "नमस्ते जी, मैं IndiaMART से {bot} बोल {rahi} हूँ। आपकी बायर लीड्स बढ़ाने के लिए "
        "एक क्विक बात करनी थी, दो मिनट मिलेंगे?",
    ("hinglish", "aap_friendly", "crisp"):
        "हेलो, IndiaMART से {bot} बोल {rahi} हूँ। आपकी लीड्स के लिए बस एक मिनट।",
    ("hinglish", "aap_friendly", "*"):
        "हेलो, मैं IndiaMART से {bot} बोल {rahi} हूँ। आपकी बायर लीड्स के बारे में क्विक बात करनी थी, दो मिनट मिलेंगे?",
    ("en", "aap_formal", "*"):
        "Good morning sir, this is {bot} from IndiaMART. I'm calling about getting {business} more quality buyer enquiries. "
        "Do you have two minutes?",
    ("en", "aap_friendly", "crisp"):
        "Hi, this is {bot} from IndiaMART. Quick one about your {category} leads, one minute?",
    ("en", "aap_friendly", "*"):
        "Hi, this is {bot} from IndiaMART. I'm calling about getting {business} better {category} leads. Do you have two minutes?",
}

# ── Objection playbook: one reviewed answer per objection per language ────────
PLAYBOOK = {
    "busy": {
        "hi": "बिल्कुल जी, आपका समय कीमती है। बस बता दीजिए, आज शाम या कल सुबह, कब पंद्रह मिनट मिल सकते हैं?",
        "hinglish": "बिल्कुल, आपका टाइम कीमती है। बस बता दीजिए, आज शाम या कल सुबह, 15 मिनट का स्लॉट कब ठीक रहेगा?",
        "en": "Of course, I'll be quick. Would this evening or tomorrow morning work for a 15-minute call?",
    },
    "price": {
        "hi": "मैं समझ {sakti} हूँ जी। यह मीटिंग बिल्कुल मुफ़्त है, सलाहकार पहले दिखाएँगे कि आपको कितने ऑर्डर मिल सकते हैं।",
        "hinglish": "मैं समझ {sakti} हूँ। मीटिंग बिल्कुल फ्री है, एडवाइजर पहले आपको दिखाएँगे कि कितने ऑर्डर मिल सकते हैं, फिर आप फ़ैसला कीजिए।",
        "en": "I understand. The meeting is free. Our advisor will first show you the expected return, and then you decide.",
    },
    "not_needed": {
        "hi": "ठीक है जी। बस एक बात, आपके इलाके में कई खरीदार रोज़ आपके जैसा सामान ढूँढ रहे हैं। पंद्रह मिनट में सलाहकार दिखा देंगे।",
        "hinglish": "ठीक है। बस इतना बता दूँ, आपके एरिया में कई बायर्स रोज़ आपके जैसे प्रोडक्ट्स सर्च कर रहे हैं, 15 मिनट में एडवाइजर दिखा देंगे।",
        "en": "Fair enough. Buyers in your area search for {category} every day, and in 15 minutes our advisor can show you that demand.",
    },
    "already_using_other": {
        "hi": "बहुत अच्छी बात है जी। सलाहकार आपको दोनों की तुलना करके दिखाएँगे, फ़ैसला आपका।",
        "hinglish": "अच्छी बात है। एडवाइजर आपको दोनों प्लेटफॉर्म्स की तुलना दिखा देंगे, फ़ैसला आपका।",
        "en": "That's great. Our advisor can do a side-by-side comparison for you, and the decision stays yours.",
    },
    "trust": {
        "hi": "आपका सवाल सही है जी। मैं IndiaMART की आधिकारिक टीम से हूँ, और मीटिंग के लिए कोई पैसा नहीं लगेगा।",
        "hinglish": "आपका शक सही है। मैं IndiaMART की ऑफिशियल टीम से हूँ, मीटिंग का कोई चार्ज नहीं है।",
        "en": "That's a fair question. I'm from IndiaMART's official team, and there is no charge for this meeting.",
    },
    "lead_quality": {
        "hi": "मैं समझ {sakti} हूँ जी, गलत लीड से समय बर्बाद होता है। सलाहकार आपकी लीड सेटिंग ठीक करेंगे ताकि सही खरीदार आएँ।",
        "hinglish": "मैं समझ {sakti} हूँ, गलत लीड्स से टाइम वेस्ट होता है। एडवाइजर आपकी लीड सेटिंग्स ठीक करेंगे ताकि सही बायर्स आएँ।",
        "en": "I understand, irrelevant leads waste your time. Our advisor will tune your lead preferences so you get the right buyers.",
    },
}

# ── Short generic replies used by the MOCK conversation engine ────────────────
MOCK = {
    "ask_slot": {
        "hi": "क्या कल सुबह ग्यारह बजे पंद्रह मिनट की मीटिंग ठीक रहेगी जी?",
        "hinglish": "क्या कल 11 बजे 15 मिनट की मीटिंग ठीक रहेगी?",
        "en": "Would tomorrow at 11 AM work for a 15-minute meeting?",
    },
    "explain": {
        "hi": "आसान भाषा में बताऊँ जी, लीड मतलब ऐसा खरीदार जो आपका सामान खरीदना चाहता है। हमारे सलाहकार आपको ऐसे और खरीदार दिलाएँगे। क्या यह समझ आया?",
        "hinglish": "सिंपल भाषा में, लीड मतलब ऐसा बायर जो आपका प्रोडक्ट खरीदना चाहता है। एडवाइजर आपको ऐसे और बायर्स दिलाएँगे। क्लियर हुआ?",
        "en": "Simply put, a lead is a buyer who wants your product. Our advisor helps you get more of them. Does that make sense?",
    },
    "empathy": {
        "hi": "माफ़ कीजिए जी, आपको परेशान करने का इरादा नहीं था। अगर आप चाहें तो बाद में पंद्रह मिनट बात कर लें, या हम कॉल बंद कर देते हैं?",
        "hinglish": "सॉरी, आपको डिस्टर्ब करने का इरादा नहीं था। चाहें तो बाद में 15 मिनट बात कर लें, या हम कॉल्स बंद कर दें?",
        "en": "I'm sorry, I didn't mean to bother you. Would you prefer a short call later, or shall we stop calling?",
    },
    "interest": {
        "hi": "बढ़िया जी! सलाहकार आपको बताएँगे कि ज़्यादा ऑर्डर कैसे मिलें। कल सुबह ग्यारह बजे या शाम पाँच बजे, कौन सा ठीक है?",
        "hinglish": "बढ़िया! एडवाइजर बताएँगे कि ज़्यादा ऑर्डर्स कैसे मिलें। कल 11 बजे या शाम 5 बजे, कौन सा स्लॉट ठीक है?",
        "en": "Great! Our advisor will show you how to win more orders. Tomorrow 11 AM or 5 PM, which works better?",
    },
    "rush": {
        "hi": "बस एक सवाल जी, कल ग्यारह बजे पंद्रह मिनट?",
        "hinglish": "बस एक सवाल, कल 11 बजे 15 मिनट?",
        "en": "Just one thing: tomorrow 11 AM, 15 minutes?",
    },
    "confirm": {
        "hi": "धन्यवाद जी! मीटिंग पक्की हो गई, आपको एसएमएस आ जाएगा।",
        "hinglish": "थैंक यू! मीटिंग कन्फर्म हो गई, आपको एसएमएस आ जाएगा।",
        "en": "Thank you! The meeting is confirmed, and you'll get an SMS shortly.",
    },
}


def fill(text: str, gender: str, **kw) -> str:
    return text.format(**GENDER_FORMS[gender], **kw)


def opening_for(lang: str, formality: str, verbosity: str) -> str:
    """Most specific template wins: exact verbosity → '*' → aap_formal fallback."""
    for key in ((lang, formality, verbosity), (lang, formality, "*"), (lang, "aap_formal", "*")):
        if key in OPENINGS:
            return OPENINGS[key]
    return OPENINGS[("en", "aap_friendly", "*")]

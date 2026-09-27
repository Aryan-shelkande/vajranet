"""Reviewed copy for SMS and short AI answers.

Emergency SMS uses these templates only. An LLM must not rewrite them.
"""

from __future__ import annotations

LANGUAGES = (
    ("en", "English"),
    ("hi", "Hindi"),
    ("mr", "Marathi"),
)

ALERT_CATEGORIES = (
    ("heavy_rain", "Heavy Rain"),
    ("thunderstorm", "Thunderstorm"),
    ("lightning", "Lightning"),
    ("flood", "Flood"),
    ("cyclone", "Cyclone"),
    ("extreme_heat", "Extreme Heat"),
    ("earthquake", "Earthquake"),
    ("severe_weather", "Severe Weather"),
)

CATEGORY_KEYS = {key for key, _label in ALERT_CATEGORIES}
LANGUAGE_KEYS = {key for key, _label in LANGUAGES}

HAZARD_TO_CATEGORY = {
    "thunderstorm": "thunderstorm",
    "heavy_rain": "heavy_rain",
    "extreme_heat": "extreme_heat",
    "extreme_cold": "severe_weather",
    "strong_wind": "severe_weather",
    "flood": "flood",
    "cyclone": "cyclone",
    "lightning": "lightning",
    "earthquake": "earthquake",
    "severe_weather": "severe_weather",
}

_SMS = {
    "en": {
        "heavy_rain": (
            "VAJRANET ALERT: Heavy rainfall warning for {place}. "
            "Risk: {severity}.{window} Model estimate, not an official warning."
        ),
        "thunderstorm": (
            "VAJRANET ALERT: Thunderstorm risk near {place}. "
            "Risk: {severity}.{window} Model estimate, not an official warning."
        ),
        "lightning": (
            "VAJRANET ALERT: Lightning risk near {place}. "
            "Risk: {severity}. Stay indoors. Not an official warning."
        ),
        "flood": (
            "VAJRANET ALERT: Flood risk estimate for {place}. "
            "Risk: {severity}. Model estimate, not an official warning."
        ),
        "cyclone": (
            "VAJRANET ALERT: Cyclone concern for {place}. "
            "Risk: {severity}. Follow IMD and local authorities."
        ),
        "extreme_heat": (
            "VAJRANET ALERT: Extreme heat near {place}. "
            "Risk: {severity}. Limit outdoor exposure. Model estimate."
        ),
        "earthquake": (
            "VAJRANET ALERT: Earthquake reported near {place}. "
            "Risk: {severity}. Follow NDMA guidance. Observed event."
        ),
        "severe_weather": (
            "VAJRANET ALERT: Severe weather near {place}. "
            "Risk: {severity}.{window} Model estimate, not an official warning."
        ),
        "confirm": (
            "VAJRANET: Welcome! Your weather and disaster alerts for {place} "
            "are now active. You'll receive important alerts based on your "
            "selected preferences. No promotional messages."
        ),
    },
    "hi": {
        "heavy_rain": (
            "VAJRANET अलर्ट: {place} में भारी बारिश की चेतावनी। "
            "जोखिम: {severity}.{window} यह मॉडल अनुमान है, आधिकारिक चेतावनी नहीं।"
        ),
        "thunderstorm": (
            "VAJRANET अलर्ट: {place} के पास तूफान का जोखिम। "
            "जोखिम: {severity}.{window} मॉडल अनुमान, आधिकारिक चेतावनी नहीं।"
        ),
        "lightning": (
            "VAJRANET अलर्ट: {place} के पास बिजली का जोखिम। "
            "जोखिम: {severity}। घर के अंदर रहें। आधिकारिक चेतावनी नहीं।"
        ),
        "flood": (
            "VAJRANET अलर्ट: {place} में बाढ़ जोखिम का अनुमान। "
            "जोखिम: {severity}। मॉडल अनुमान, आधिकारिक चेतावनी नहीं।"
        ),
        "cyclone": (
            "VAJRANET अलर्ट: {place} के लिए चक्रवात संबंधी सावधानी। "
            "जोखिम: {severity}। IMD और स्थानीय प्रशासन का पालन करें।"
        ),
        "extreme_heat": (
            "VAJRANET अलर्ट: {place} में भीषण गर्मी। "
            "जोखिम: {severity}। धूप में कम निकलें। मॉडल अनुमान।"
        ),
        "earthquake": (
            "VAJRANET अलर्ट: {place} के पास भूकंप दर्ज। "
            "जोखिम: {severity}। NDMA मार्गदर्शन का पालन करें।"
        ),
        "severe_weather": (
            "VAJRANET अलर्ट: {place} के पास गंभीर मौसम। "
            "जोखिम: {severity}.{window} मॉडल अनुमान, आधिकारिक चेतावनी नहीं।"
        ),
        "confirm": (
            "VAJRANET: स्वागत है! {place} के लिए आपके मौसम और आपदा अलर्ट सक्रिय हैं। "
            "चुनी हुई प्राथमिकताओं के अनुसार महत्वपूर्ण अलर्ट मिलेंगे। कोई प्रचार संदेश नहीं।"
        ),
    },
    "mr": {
        "heavy_rain": (
            "VAJRANET इशारा: {place} येथे मुसळधार पावसाचा इशारा. "
            "जोखीम: {severity}.{window} हा मॉडेल अंदाज आहे, अधिकृत इशारा नाही."
        ),
        "thunderstorm": (
            "VAJRANET इशारा: {place} जवळ वादळाचा धोका. "
            "जोखीम: {severity}.{window} मॉडेल अंदाज, अधिकृत इशारा नाही."
        ),
        "lightning": (
            "VAJRANET इशारा: {place} जवळ विजेचा धोका. "
            "जोखीम: {severity}. घरात रहा. अधिकृत इशारा नाही."
        ),
        "flood": (
            "VAJRANET इशारा: {place} येथे पुराचा धोका अंदाज. "
            "जोखीम: {severity}. मॉडेल अंदाज, अधिकृत इशारा नाही."
        ),
        "cyclone": (
            "VAJRANET इशारा: {place} साठी चक्रीवादळाची दक्षता. "
            "जोखीम: {severity}. IMD आणि स्थानिक प्रशासनाचे पालन करा."
        ),
        "extreme_heat": (
            "VAJRANET इशारा: {place} येथे तीव्र उष्णता. "
            "जोखीम: {severity}. बाहेर कमी वेळ राहा. मॉडेल अंदाज."
        ),
        "earthquake": (
            "VAJRANET इशारा: {place} जवळ भूकंप नोंदला. "
            "जोखीम: {severity}. NDMA मार्गदर्शनाचे पालन करा."
        ),
        "severe_weather": (
            "VAJRANET इशारा: {place} जवळ गंभीर हवामान. "
            "जोखीम: {severity}.{window} मॉडेल अंदाज, अधिकृत इशारा नाही."
        ),
        "confirm": (
            "VAJRANET: स्वागत आहे! {place} साठी तुमचे हवामान आणि आपत्ती इशारे सक्रिय आहेत. "
            "निवडलेल्या पसंतींनुसार महत्त्वाचे इशारे मिळतील. प्रचार संदेश नाही."
        ),
    },
}

DISCLAIMERS = {
    "en": (
        "Follow official instructions from local authorities such as IMD, NDMA, "
        "or your state disaster management agency. This assistant does not issue "
        "official warnings."
    ),
    "hi": (
        "IMD, NDMA या राज्य आपदा प्रबंधन के निर्देशों का पालन करें। "
        "यह सहायक आधिकारिक चेतावनी जारी नहीं करता।"
    ),
    "mr": (
        "IMD, NDMA किंवा राज्य आपत्ती व्यवस्थापनाच्या सूचनांचे पालन करा. "
        "हा सहाय्यक अधिकृत इशारा देत नाही."
    ),
}


def render_sms(language: str, category: str, **kwargs) -> str:
    """Fill a reviewed SMS template. Unknown languages fall back to English."""
    lang = language if language in _SMS else "en"
    catalog = _SMS[lang]
    template = catalog.get(category) or catalog["severe_weather"]
    window = (kwargs.get("window") or "").strip()
    window_txt = f" Expected window: {window}." if window else ""
    return template.format(
        place=(kwargs.get("place") or "your area").strip() or "your area",
        severity=(kwargs.get("severity") or "HIGH").strip() or "HIGH",
        window=window_txt,
        url=(kwargs.get("url") or "").strip(),
    )


def _fmt(value, suffix: str = "", missing: str = "unavailable") -> str:
    if value is None or value == "":
        return missing
    if isinstance(value, float):
        text = f"{value:.0f}"
    else:
        text = str(value)
    return f"{text}{suffix}"


def briefing_text(
    language: str,
    *,
    place: str,
    condition: str | None,
    temp,
    humidity,
    rain_prob,
    storm_level: str | None,
) -> str:
    """Deterministic briefing. Numbers come only from the caller."""
    lang = language if language in DISCLAIMERS else "en"
    place = place or "This location"
    condition = condition or "conditions unavailable"
    temp_txt = _fmt(temp, "°C")
    hum_txt = _fmt(humidity, "%")
    rain_txt = _fmt(rain_prob, "%")
    storm = storm_level or "unavailable"
    if lang == "hi":
        body = (
            f"{place} में इस समय {condition} है और तापमान {temp_txt} है। "
            f"आर्द्रता {hum_txt} है। अगले कुछ घंटों में बारिश की संभावना {rain_txt} है। "
            f"तूफान का मॉडल अनुमान {storm} है। "
            "यह उपलब्ध VajraNet डेटा की स्वचालित व्याख्या है, आधिकारिक पूर्वानुमान नहीं।"
        )
    elif lang == "mr":
        body = (
            f"{place} येथे सध्या {condition} आहे आणि तापमान {temp_txt} आहे. "
            f"आर्द्रता {hum_txt} आहे. पुढील काही तासांत पावसाची शक्यता {rain_txt} आहे. "
            f"वादळाचा मॉडेल अंदाज {storm} आहे. "
            "ही उपलब्ध VajraNet डेटाची स्वयंचलित व्याख्या आहे, अधिकृत अंदाज नाही."
        )
    else:
        body = (
            f"{place} is currently {condition} at {temp_txt}. "
            f"Humidity is {hum_txt}. Rain probability over the next few hours is {rain_txt}. "
            f"Thunderstorm model estimate is {storm}. "
            "This is an automated interpretation of available VajraNet data, "
            "not an official forecast."
        )
    return body


def localized_answer(question: str, context: dict, language: str) -> str | None:
    """Reviewed-template answers for Hindi and Marathi. English stays in the assistant."""
    if language not in {"hi", "mr"}:
        return None
    q = (question or "").lower()
    weather = context.get("weather") or {}
    nowcast = context.get("nowcast") or {}
    risk = context.get("risk") or {}
    if language == "hi":
        city = context.get("city") or "इस स्थान"
    else:
        city = context.get("city") or "हे ठिकाण"
    temp = _fmt(weather.get("temperature_c"), "°C")
    rain = _fmt(weather.get("rainfall_mm"), " mm")
    desc = weather.get("weather_description") or (
        "अनुपलब्ध" if language == "hi" else "उपलब्ध नाही"
    )
    level = (
        risk.get("overall_level")
        or nowcast.get("risk_level")
        or ("अनुपलब्ध" if language == "hi" else "उपलब्ध नाही")
    )
    radar = context.get("radar_status") or "unavailable"
    disclaimer = DISCLAIMERS[language]

    if any(k in q for k in ("radar", "रडार")):
        if language == "hi":
            detail = (
                f"{city} के लिए रडार स्थिति: {radar}. "
                "यह RainViewer मोज़ेक है, स्थानीय IMD रडार उत्पाद नहीं।"
                if radar == "available"
                else f"{city} के लिए इस समय रडार अवलोकन प्लेटफ़ॉर्म पर उपलब्ध नहीं है।"
            )
        else:
            detail = (
                f"{city} साठी रडार स्थिती: {radar}. "
                "हा RainViewer मोझेक आहे, स्थानिक IMD रडार नाही."
                if radar == "available"
                else f"{city} साठी सध्या रडार निरीक्षण प्लॅटफॉर्मवर उपलब्ध नाही."
            )
    elif any(k in q for k in ("risk", "जोखिम", "जोखीम", "why", "क्यों", "का")):
        why = risk.get("why") or risk.get("summary") or ""
        if language == "hi":
            detail = (
                f"{city} का मॉडल जोखिम {level} है। {why} "
                "यह VajraNet मॉडल अनुमान है, आधिकारिक चेतावनी नहीं।"
            )
        else:
            detail = (
                f"{city} चा मॉडेल धोका {level} आहे. {why} "
                "हा VajraNet मॉडेल अंदाज आहे, अधिकृत इशारा नाही."
            )
    elif any(k in q for k in ("rain", "बारिश", "पाऊस")):
        if language == "hi":
            detail = f"पूर्वानुमान/अवलोकन: {city} में वर्तमान वर्षा {rain} है। स्थिति: {desc}।"
        else:
            detail = (
                f"निरीक्षण/अंदाज: {city} येथे सध्या पर्जन्य {rain} आहे. स्थिती: {desc}."
            )
    elif any(k in q for k in ("alert", "warning", "चेतावनी", "इशारा")):
        alerts = context.get("alerts") or []
        if alerts:
            title = alerts[0].get("title") or "Alert"
            if language == "hi":
                detail = (
                    f"{city} के लिए सक्रिय प्लेटफ़ॉर्म अलर्ट: {title}. "
                    "व्युत्पन्न अलर्ट आधिकारिक IMD/NDMA चेतावनी नहीं हैं।"
                )
            else:
                detail = (
                    f"{city} साठी सक्रिय प्लॅटफॉर्म इशारा: {title}. "
                    "व्युत्पन्न इशारे अधिकृत IMD/NDMA इशारे नाहीत."
                )
        elif language == "hi":
            detail = f"{city} के लिए अभी कोई सक्रिय प्लेटफ़ॉर्म अलर्ट नहीं है।"
        else:
            detail = f"{city} साठी सध्या सक्रिय प्लॅटफॉर्म इशारा नाही."
    else:
        if language == "hi":
            detail = (
                f"{city} का उपलब्ध सार: तापमान {temp}, स्थिति {desc}, "
                f"मॉडल जोखिम {level}। जिस बात का डेटा नहीं है, उसे यहाँ नहीं जोड़ा गया।"
            )
        else:
            detail = (
                f"{city} चा उपलब्ध सार: तापमान {temp}, स्थिती {desc}, "
                f"मॉडेल धोका {level}. ज्याचा डेटा नाही तो येथे दिललेला नाही."
            )
    return f"{detail} {disclaimer}"

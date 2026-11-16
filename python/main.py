import random
import re
import threading
import time

from arduino.app_utils import App, Bridge
from arduino.app_bricks.web_ui import WebUI
from arduino.app_bricks.llm import LargeLanguageModel, tool

# ---------------- SETTINGS ----------------
# The AI runs on the board through the Large Language Model (LLM) brick.
# Pick Qwen 3.5 0.8B in the brick's AI models tab: it is the model that can use tools.
MAX_TOKENS = 140          # length of ASTRO's advice on the results screen and in topics
USE_AI_OPENER = True      # True: the AI writes the chat's opening line. False: built-in openings only (instant).
OPENER_MAX_TOKENS = 40    # the short, kind opening line ASTRO writes in the chat
TIPS_PER_REPLY = 3        # how many tips from the tip library each chat reply includes
CHAT_CLOSER = "What would you like help with next?"   # added to the end of chat replies

# ElevenLabs voice for ASTRO (needs internet). Leave the key empty to use the browser voice instead.
ELEVENLABS_API_KEY = ""                        # paste your key here, it starts with sk_
ELEVENLABS_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"   # the voice (this one is "George"); change it to try other voices
ELEVENLABS_MODEL = "eleven_flash_v2_5"         # the fast model, good for live conversation
NO_GENERIC_ENDINGS = (
    "Never end a reply with a generic offer like 'How can I help you?', 'Is there anything else?', "
    "or 'Let me know if you need anything'. "
)

SYSTEM_PROMPT = (
    "Your name is ASTRO. You are a calm, supportive wellness assistant in a health check app "
    "for adult astronauts on a space station. "
    "You are not a doctor. Never diagnose, never say what illness someone has, never suggest medicines. "
    "Give practical, realistic tips the astronaut can use on the station today. When it fits, encourage them to "
    "talk to a crewmate, the crew medical officer, or the crew psychologist at Mission Control. "
    "Never mention emergency phone numbers. "
    + NO_GENERIC_ENDINGS +
    "Answer in 3 or 4 short, clear sentences. No lists, no markdown, no emojis."
)

# In the chat, the AI only writes ONE warm sentence. The tips come from the checked tip library below.
OPENER_PROMPT = (
    "You are ASTRO, a kind wellness companion on a space station. The astronaut will tell you how they feel. "
    "Write exactly ONE short, warm sentence that shows you understand how they feel. "
    "Examples of good sentences: "
    "'Not being able to sleep is exhausting, so let's work on it together.' "
    "'Missing your family is completely natural when you're this far from home.' "
    "'Stress can pile up fast up here, so it's good you're taking a moment for it.' "
    "Only write the one sentence, nothing else."
)

# Opening lines containing these words are thrown away and replaced with a built-in opening.
BAD_OPENER = re.compile(
    r"\b(ai|artificial|language model|chatbot|cannot|can't|can not|unable|not able|not allowed|"
    r"tips?|advice|advise|doctor|as an|sorry, but|listen)\b",
    re.IGNORECASE,
)

AGENT_PROMPT = (
    "You are ASTRO, the wellness agent on a space station. "
    "Call exactly ONE tool: start_breathing, start_grounding_exercise, or open_topic. "
    "Then say in one short sentence which exercise you picked and why. Never diagnose."
)

# When someone reports or types about self-harm, the AI is not used.
# A fixed, safe message is shown instead, every time.
SAFE_MESSAGE = (
    "Thank you for telling me. You matter, and you don't have to handle this alone. "
    "Please tell a crewmate or someone near you right now, and ask for a private call with the crew psychologist. "
    "Stay with someone until the feeling eases."
)

# If a typed message contains any of these, ASTRO answers with SAFE_MESSAGE instead of the AI.
CRISIS_WORDS = [
    "kill myself", "killing myself", "suicide", "suicidal", "end my life", "end it all",
    "hurt myself", "hurting myself", "harm myself", "self harm", "self-harm", "selfharm",
    "want to die", "wanna die", "don't want to live", "dont want to live", "do not want to live",
    "not worth living", "cut myself", "better off dead", "no reason to live",
]

# Generic closing lines that get removed from the end of ASTRO's replies.
GENERIC_ENDINGS = re.compile(
    r"(how (can|may|else can|could) i (help|assist|support)"
    r"|what can i do for you"
    r"|is there anything else"
    r"|anything else (i can|you)"
    r"|let me know if"
    r"|feel free to"
    r"|i'?m (here|always here) (to help|for you|if|whenever)"
    r"|how can i be of)",
    re.IGNORECASE,
)

# ---------------- TIP LIBRARY ----------------
# Checked tips for the chat. The code finds the topic from the astronaut's words,
# and each reply shows a few tips the astronaut hasn't seen yet in this chat.
# Topics are checked in this order, so the more serious ones come first.
TIPS = {
    "medical": {
        "words": r"\b(chest pain|chest hurts|chest is tight|tight chest|can'?t breathe|cannot breathe|can not breathe|"
                 r"hard to breathe|short of breath|numb|numbness|faint|fainted|passing out|pass out|confused|confusion)\b",
        "opener": "I want to make sure you're safe.",
        "tips": [
            "Chest pain, trouble breathing, sudden confusion, or numbness can be serious, so tell the crew medical officer right now.",
            "Don't wait to see if it passes, and don't stay alone.",
            "Ask a crewmate to stay with you and help you contact Mission Control's flight surgeon.",
        ],
    },
    "panic": {
        "words": r"\b(panic|panicking|panicky|heart (is )?racing|freaking out)\b",
        "opener": "That sounds really frightening.",
        "tips": [
            "Remind yourself that a panic attack feels scary but usually peaks within about 10 minutes and then passes.",
            "Breathe slowly, making each breath out longer than the breath in, because this tells your body it is safe.",
            "Use the 5-4-3-2-1 grounding exercise to bring your attention back to the room around you.",
            "Stay with a crewmate until the feeling passes, so you aren't alone with it.",
            "If it's your first panic attack or you have chest pain, tell the crew medical officer to be safe.",
        ],
    },
    "sleep": {
        "words": r"\b(sleep|sleeping|slept|sleepless|insomnia|awake|nightmares?)\b",
        "opener": "Not being able to sleep is exhausting, so let's work on it together.",
        "tips": [
            "Go to sleep and wake up at the same time every day, because a steady routine helps reset a body clock that sees about 16 sunrises a day.",
            "Wear your eye mask and earplugs, since light and the constant hum of the station's fans can keep you from sleeping deeply.",
            "Put screens away 30 to 60 minutes before sleep, because their bright light keeps your brain alert.",
            "Avoid caffeine in the afternoon and evening, since its effects can last for many hours.",
            "If you can't fall asleep after about 20 minutes, read something calm for a while and then try again, so you don't lie there worrying.",
            "Try the guided breathing exercise before bed, because slow breathing helps your body relax.",
        ],
    },
    "anxiety": {
        "words": r"\b(anxious|anxiety|nervous|worr(y|ied|ying|ies)|scared|afraid|fear|on edge|calm down|uneasy)\b",
        "opener": "Feeling worried or on edge is really tiring.",
        "tips": [
            "Slow your breathing, making each breath out longer than the breath in, because this signals to your body that it is safe.",
            "Try the 5-4-3-2-1 grounding exercise, because it pulls your attention back to the present moment.",
            "Write your worries down, since putting them on paper can stop them from going around in your head.",
            "Focus on what you can control today and let the rest wait, because worrying about everything at once is exhausting.",
            "If worry is affecting your work or sleep, ask for a private call with the crew psychologist.",
        ],
    },
    "stress": {
        "words": r"\b(stress|stressed|stressful|pressure|overwhelm\w*|workload|too much work|deadlines?)\b",
        "opener": "That sounds like a lot to carry right now.",
        "tips": [
            "Break big tasks into small steps and focus only on the next one, because it makes the workload feel manageable.",
            "Take a five-minute break at the window, since looking at Earth helps many astronauts reset.",
            "Keep up your daily exercise, because physical activity helps your body handle stress.",
            "Talk to a crewmate about what's on your mind, since sharing a problem often makes it feel lighter.",
            "If the workload is too much, tell the commander, because schedules can sometimes be adjusted.",
        ],
    },
    "mood": {
        "words": r"\b(sad|depressed|depression|empty|hopeless|cry|crying|unhappy|miserable|feel(ing)? (low|down|bad))\b",
        "opener": "I'm sorry you're feeling this way, and thank you for telling me.",
        "tips": [
            "Tell someone you trust how you've been feeling, because you don't have to carry it alone.",
            "Do one small thing you usually enjoy, even if you don't feel like it, since activity can lift your mood a little at a time.",
            "Spend a few minutes at the window looking at Earth, which many astronauts find calming.",
            "Keep up sleep, meals, and exercise, because they affect mood more than most people expect.",
            "If you've felt low most days for two weeks or more, ask for a private call with the crew psychologist.",
        ],
    },
    "homesick": {
        "words": r"\b(homesick|miss (my|home|family|friends|earth)|family|lonely|loneliness|alone|isolated|isolation)\b",
        "opener": "Missing the people you love is completely natural when you're this far from home.",
        "tips": [
            "Schedule a call or video chat with family or friends, because hearing familiar voices helps a lot.",
            "Look at photos or messages from home, since small reminders can make the distance feel smaller.",
            "Share a meal with the crew, because time together helps the station feel more like home.",
            "Keep up a hobby you enjoy, like music, reading, or photography, so your free time feels like your own.",
            "Remember that almost every astronaut feels homesick, and it usually gets easier with time.",
        ],
    },
    "crew": {
        "words": r"\b(crewmates?|argument|argue|arguing|fight|fighting|conflict|annoyed|angry|tension|commander)\b",
        "opener": "Tension with people you live and work with every day is tough.",
        "tips": [
            "Raise the problem early and calmly, because small issues can grow in a small space.",
            "Use 'I' statements, like 'I feel stressed when...', so the other person doesn't feel attacked.",
            "Take some time in your own quarters to cool down before talking, since calm conversations go better.",
            "Look for one thing you appreciate about the other person, which can soften the tension.",
            "If it doesn't improve, ask the commander or the crew psychologist to help.",
        ],
    },
    "energy": {
        "words": r"\b(tired|exhausted|fatigue|fatigued|energy|unmotivated|motivation|lazy|bored|boring|drained)\b",
        "opener": "Running low on energy makes every task feel heavier.",
        "tips": [
            "Keep a regular sleep schedule, because tiredness often starts with irregular sleep.",
            "Drink water regularly, since thirst is easy to miss in space and can leave you feeling tired.",
            "Do your daily exercise, because moving your body can actually raise your energy.",
            "Start with one small, easy task, since finishing something builds momentum.",
            "Plan short breaks between tasks, so you don't run on empty for the whole day.",
        ],
    },
    "focus": {
        "words": r"\b(focus|focusing|concentrat\w*|forget\w*|forgot|memory|distracted)\b",
        "opener": "Trouble focusing can be really frustrating.",
        "tips": [
            "Work on one task at a time, because switching between tasks drains your attention.",
            "Use a checklist for complex steps, so you don't have to hold everything in your head.",
            "Take a short break every hour, since attention naturally fades over time.",
            "Get enough sleep and drink water, because both strongly affect concentration.",
            "If your thinking suddenly feels foggy or confused, tell the crew medical officer.",
        ],
    },
    "food": {
        "words": r"\b(hungry|thirsty|eat|eating|food|meals?|appetite|water|drink|drinking)\b",
        "opener": "Eating and drinking well can be tricky up here.",
        "tips": [
            "Eat regular meals even when you're not very hungry, because appetite often drops in space.",
            "Drink water throughout the day, since many astronauts don't feel thirsty even when their body needs fluids.",
            "Eat with the crew when you can, which makes meals more enjoyable.",
            "Add sauces and spices, since food can taste blander in space.",
            "If your appetite changes a lot for several days, tell the crew medical officer.",
        ],
    },
    "exercise": {
        "words": r"\b(exercise|exercising|workout|work out|fitness|muscles?|bones?|gym|treadmill)\b",
        "opener": "Staying active is one of the best things you can do in orbit.",
        "tips": [
            "Do your daily exercise session, because it protects your bones and muscles from weakening in microgravity.",
            "Mix cardio and resistance training, since each one helps your body in a different way.",
            "Stretch after exercise, which can help with the back pain many astronauts get.",
            "Use exercise as a stress break, because it helps your mind as well as your body.",
            "Drink water after working out to replace the fluids you lost.",
        ],
    },
    "body": {
        "words": r"\b(headaches?|head hurts|back pain|backache|pain|painful|sore|nausea|nauseous|sick|dizzy|ache|aches)\b",
        "opener": "I'm sorry you're not feeling well physically.",
        "tips": [
            "Drink water regularly, because not drinking enough can cause headaches and tiredness.",
            "Stretch your back and neck each day, since spaceflight often causes back pain.",
            "Keep up your daily exercise, which helps protect your muscles and bones.",
            "Rest when you can, since your body recovers better when you're not exhausted.",
            "If pain or sickness lasts more than a day or gets worse, tell the crew medical officer.",
        ],
    },
    "general": {
        "words": None,
        "opener": "Thanks for checking in with me.",
        "tips": [
            "Keep a steady sleep schedule, because good sleep helps both your body and your mind.",
            "Drink water regularly, since thirst is easy to miss in space.",
            "Do your daily exercise, which protects your body and lifts your mood.",
            "Stay connected with the crew and with family back home, because support matters on a long mission.",
            "Take a few minutes at the window looking at Earth when you need a break.",
        ],
    },
}
TOPIC_ORDER = ["medical", "panic", "sleep", "anxiety", "stress", "mood", "homesick",
               "crew", "energy", "focus", "food", "exercise", "body"]
MORE_WORDS = re.compile(r"\b(more|another|other|else|again|next|continue)\b", re.IGNORECASE)

TOPIC_IDS = ["anxiety", "panic", "depression", "talk", "friend", "stress",
             "homesick", "crew", "sleep", "psych", "selfcare"]

ui = WebUI()
llm = None
talk_llm = None
agent = None
llm_lock = threading.Lock()
safety_mode = False
talk_safety = False
pending = {"action": None}   # the exercise the agent picked
mission_log = []             # check-ins since the app started
last_checkin = ""            # short summary of the latest check-in
last_topic = None            # the chat's current topic, for "give me more tips"
shown_tips = {}              # tips already shown in this chat, per topic


def error_text(e):
    """A short, readable error for the screen, so you can see what actually went wrong."""
    detail = f"{type(e).__name__}: {e}"
    return ("My AI isn't responding. Check that the Large Language Model brick is added and its model "
            "is downloaded, then press Stop and Run. Error details: " + detail[:200])


def clean_reply(text):
    """Remove 'ASTRO:' at the start and generic closing lines like 'How can I help you?' at the end."""
    text = re.sub(r"^\s*ASTRO:\s*", "", str(text).strip(), flags=re.IGNORECASE)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    while len(sentences) > 1 and GENERIC_ENDINGS.search(sentences[-1]):
        sentences.pop()
    return " ".join(sentences)


def clean_opener(text):
    """Keep ASTRO's first sentence only if it's a good, warm opening. Otherwise return "" (use the built-in one)."""
    text = re.sub(r"^\s*ASTRO:\s*", "", str(text).strip(), flags=re.IGNORECASE).strip(" '\"")
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if not sentences:
        return ""
    first = sentences[0].strip(" '\"")
    if first.endswith("?") or len(first) < 15 or len(first) > 200:
        return ""
    if BAD_OPENER.search(first) or GENERIC_ENDINGS.search(first):
        return ""
    if not first.endswith((".", "!")):
        first += "."
    return first


def find_topic(lowered):
    for name in TOPIC_ORDER:
        if re.search(TIPS[name]["words"], lowered):
            return name
    return None


def pick_tips(topic):
    """Pick tips the astronaut hasn't seen yet in this chat. Start over when all have been shown."""
    all_tips = TIPS[topic]["tips"]
    seen = shown_tips.setdefault(topic, [])
    fresh = [t for t in all_tips if t not in seen]
    if not fresh:
        seen.clear()
        fresh = list(all_tips)
    chosen = random.sample(fresh, min(TIPS_PER_REPLY, len(fresh)))
    seen.extend(chosen)
    return chosen


def stream_to_page(model, message):
    """Show the reply word by word, then send a cleaned-up final version."""
    full = ""
    for chunk in model.chat_stream(message):
        full += chunk
        ui.send_message("ai_chunk", {"text": chunk})
    cleaned = clean_reply(full)
    done = {}
    if cleaned != full.strip():
        print("Tidied the end of ASTRO's reply")
        done["final"] = cleaned
    ui.send_message("ai_done", done)
    return cleaned


# ---------------- AGENT TOOLS ----------------
# Each tool is a "gate": it checks the request before anything happens on screen.

@tool
def start_breathing() -> str:
    """Start the guided breathing exercise on screen. Good when the astronaut feels stressed, tense, or nervous."""
    print("Tool call: start_breathing()")
    if pending["action"]:
        return "Refused: an exercise is already chosen."
    pending["action"] = {"name": "breathe"}
    return "Done: the breathing exercise will start."


@tool
def start_grounding_exercise() -> str:
    """Start the 5-4-3-2-1 grounding exercise on screen. Good when the astronaut feels panicky, overwhelmed, or worried."""
    print("Tool call: start_grounding_exercise()")
    if pending["action"]:
        return "Refused: an exercise is already chosen."
    pending["action"] = {"name": "ground"}
    return "Done: the grounding exercise will start."


@tool
def open_topic(topic_id: str) -> str:
    """Open a mental health topic on screen. topic_id must be one of: anxiety, panic, depression, talk, friend, stress, homesick, crew, sleep, psych, selfcare."""
    print(f"Tool call: open_topic({topic_id!r})")
    if pending["action"]:
        return "Refused: an exercise is already chosen."
    topic_id = str(topic_id).strip().lower()
    if topic_id not in TOPIC_IDS:
        return "Refused: unknown topic_id. Use one of: " + ", ".join(TOPIC_IDS)
    pending["action"] = {"name": "topic", "id": topic_id}
    return f"Done: the {topic_id} topic will open."


# ---------------- AI HELPERS ----------------
def new_chat():
    model = LargeLanguageModel(system_prompt=SYSTEM_PROMPT, temperature=0.3, max_tokens=MAX_TOKENS)
    model.with_memory(6)
    return model


def get_agent():
    global agent
    if agent is None:
        agent = LargeLanguageModel(
            system_prompt=AGENT_PROMPT,
            temperature=0.2,
            max_tokens=60,
            tools=[start_breathing, start_grounding_exercise, open_topic],
        )
        agent.with_memory(0)  # every decision starts fresh
    return agent


def log_summary():
    """The mission log, written straight into the agent's instructions (saves a whole AI round)."""
    if len(mission_log) < 2:
        return "This is their first check-in."
    earlier = [f"body {e['body']}% / mind {e['mind']}%" for e in mission_log[-4:-1]]
    return "Their earlier check-ins, oldest first: " + "; ".join(earlier) + "."


def describe(data):
    lines = [
        f"Body score: {data.get('body')}% and Mind score: {data.get('mind')}% "
        "(0% means feeling fine, 100% means the worst).",
        "Their highest ratings out of 10:",
    ]
    for c in data.get("concerns", []):
        lines.append(f"{c.get('label')}: {c.get('score')}")
    if not data.get("concerns"):
        lines.append("Nothing rated high.")
    return lines


def send_safe_message():
    ui.send_message("ai_chunk", {"text": SAFE_MESSAGE})
    ui.send_message("ai_done", {"crisis": True})


def stream_reply(prompt):
    """ASTRO's advice on the results screen and in the topics."""
    global llm
    if safety_mode:
        send_safe_message()
        return
    with llm_lock:
        try:
            if llm is None:
                llm = new_chat()
            stream_to_page(llm, prompt)
        except Exception as e:
            print("AI error:", repr(e))
            llm = None  # start fresh next time
            ui.send_message("ai_done", {"error": error_text(e)})


def talk_reply(text):
    """Chat: the code finds the topic, the AI writes one warm sentence, and checked tips are added.
    The whole reply is built first and then sent in one piece, so it works with any version of the page."""
    global talk_llm, talk_safety, last_topic
    lowered = text.lower().replace("’", "'")

    # 1. Self-harm words: fixed safe message, no AI
    if talk_safety or any(w in lowered for w in CRISIS_WORDS):
        talk_safety = True
        print("Chat: crisis words found, sending the safe message")
        send_safe_message()
        return

    # 2. Find the topic ("more tips" keeps the last topic)
    topic = find_topic(lowered)
    if topic is None and last_topic and MORE_WORDS.search(lowered):
        topic = last_topic
    if topic is None:
        topic = "general"
    last_topic = topic
    print("Chat topic:", topic)

    # 3. Serious physical symptoms: fixed safety reply, no AI
    if topic == "medical":
        reply = TIPS["medical"]["opener"] + " " + " ".join(TIPS["medical"]["tips"])
        ui.send_message("ai_chunk", {"text": reply})
        ui.send_message("ai_done", {})
        return

    # 4. The AI writes one warm sentence. Bad ones are thrown away.
    opener = ""
    if USE_AI_OPENER:
        with llm_lock:
            try:
                if talk_llm is None:
                    talk_llm = LargeLanguageModel(system_prompt=OPENER_PROMPT, temperature=0.4, max_tokens=OPENER_MAX_TOKENS)
                    talk_llm.with_memory(0)
                raw = talk_llm.chat(text)
                opener = clean_opener(raw)
                if opener:
                    print("AI opening:", opener)
                else:
                    print("AI opening thrown away:", repr(raw))
            except Exception as e:
                print("Chat AI error (tips are still shown):", repr(e))
                talk_llm = None

    if not opener:
        opener = TIPS[topic]["opener"]

    # 5. Build the full reply: opening + checked tips + closing question, and send it in one piece
    tips = pick_tips(topic)
    reply = opener + " Here are a few things that can help. " + " ".join(tips) + " " + CHAT_CLOSER
    ui.send_message("ai_chunk", {"text": reply})
    ui.send_message("ai_done", {})


def run_agent(data):
    prompt = "\n".join(describe(data) + [log_summary(), "Pick one exercise for this astronaut now."])
    reply = ""
    with llm_lock:
        pending["action"] = None
        try:
            reply = get_agent().chat(prompt)
        except Exception as e:
            print("Agent error:", repr(e))
        action = pending["action"]

    if action is None:
        # The small model didn't pick a tool, so the code picks a sensible default.
        if int(data.get("mind", 0)) >= int(data.get("body", 0)):
            action = {"name": "breathe"}
            fallback = "Let's slow things down with some guided breathing."
        else:
            action = {"name": "topic", "id": "selfcare"}
            fallback = "Here are some small daily habits that can help you feel better."
        if not str(reply).strip():
            reply = fallback

    print("Agent picked:", action)
    ui.send_message("ai_chunk", {"text": clean_reply(reply)})
    ui.send_message("ai_done", {"action": action})


# ---------------- MESSAGES FROM THE PAGE ----------------
def handle_advice(sid, data):
    global llm, safety_mode, last_checkin
    safety_mode = int(data.get("selfharm", 0)) >= 4
    llm = None  # fresh conversation for every new check
    mission_log.append({"time": time.strftime("%H:%M"), "body": data.get("body"), "mind": data.get("mind")})

    top = [f"{c.get('label')} {c.get('score')}/10" for c in data.get("concerns", [])[:3]]
    last_checkin = (f"body score {data.get('body')}%, mind score {data.get('mind')}%"
                    + (", highest ratings: " + ", ".join(top) if top else ", nothing rated high"))

    prompt = "\n".join(describe(data) + ["Give this astronaut supportive, practical advice for today."])
    threading.Thread(target=stream_reply, args=(prompt,), daemon=True).start()


def handle_agent(sid, data):
    if safety_mode:
        send_safe_message()
        return
    threading.Thread(target=run_agent, args=(data,), daemon=True).start()


def handle_followup(sid, data):
    question = str(data.get("question", "")).strip()
    if question:
        threading.Thread(target=stream_reply, args=(question,), daemon=True).start()


def handle_talk_start(sid, data):
    """Opening the chat screen starts a fresh conversation."""
    global talk_llm, talk_safety, last_topic, shown_tips
    talk_llm = None
    last_topic = None
    shown_tips = {}
    talk_safety = safety_mode


def handle_talk(sid, data):
    text = str(data.get("text", "")).strip()[:300]
    if text:
        print("Chat message:", text)
        threading.Thread(target=talk_reply, args=(text,), daemon=True).start()


def handle_reset(sid, data):
    """A new person is starting from the home screen: forget the last conversation."""
    global llm, safety_mode
    llm = None
    safety_mode = False


def warm_up():
    """Load the model into memory at startup so the first real answer is faster."""
    try:
        with llm_lock:
            LargeLanguageModel(max_tokens=1).chat("Hi")
        print("ASTRO's AI is loaded and ready")
    except Exception as e:
        print("AI warm-up failed (is the LLM brick added and the model downloaded?):", repr(e))


# ---------------- BUTTONS FROM THE BOARD (not used with a keyboard, kept harmless) ----------------
def on_button(name):
    ui.send_message("button", {"name": str(name)})


Bridge.provide("button_pressed", on_button)
ui.on_message("get_advice", handle_advice)
ui.on_message("agent_pick", handle_agent)
ui.on_message("ask_followup", handle_followup)
ui.on_message("talk_start", handle_talk_start)
ui.on_message("talk_message", handle_talk)
ui.on_message("reset_chat", handle_reset)
threading.Thread(target=warm_up, daemon=True).start()

# ================= HEART CHECK (HRV) =================
# HRV = heart rate variability: how much the time between heartbeats changes.
# The math is the same as the Kaggle notebook (NeuroKit2 / pyHRV), written in plain Python so nothing extra has to be installed.
# A higher HRV usually means the body is relaxed and recovered; a lower HRV can be a sign of stress or tiredness.
# This is a wellness guide only, NOT a medical test.
# The heartbeats are REAL recordings from PhysioNet (no made-up data). Later, a heart sensor can send the astronaut's own.
import math                                                    # square roots and sine waves for the HRV math

def clean_rr(rr):
    """Removes impossible values (like a missed beat), the same idea as NeuroKit's cleaning step."""
    return [x for x in rr if 300 <= x <= 2000]                 # keeps only 30 to 200 beats per minute


def hrv_stats(rr):
    """Works out heart rate and the 3 main HRV numbers (time-domain analysis, like the notebook)."""
    rr = clean_rr(rr)                                          # clean the data first
    if len(rr) < 10:                                           # not enough beats to say anything...
        return None                                            # ...so give up
    mean_rr = sum(rr) / len(rr)                                # average gap between beats
    diffs = [rr[i + 1] - rr[i] for i in range(len(rr) - 1)]    # how much each gap changed from the one before
    sdnn = math.sqrt(sum((x - mean_rr) ** 2 for x in rr) / len(rr))  # SDNN: how spread out all the gaps are
    rmssd = math.sqrt(sum(d * d for d in diffs) / len(diffs))  # RMSSD: the "calm" number, beat-to-beat change
    pnn50 = 100.0 * sum(1 for d in diffs if abs(d) > 50) / len(diffs)  # pNN50: % of beats that changed by more than 50 ms
    return {                                                   # give back the results
        "heart_rate": round(60000 / mean_rr),                  # beats per minute
        "sdnn": round(sdnn, 1),                                # in ms
        "rmssd": round(rmssd, 1),                              # in ms
        "pnn50": round(pnn50, 1),                              # in %
        "beats": len(rr),                                      # how many beats we used
    }                                                          # end of the results


HRV_LEVELS = {                                                 # fixed, checked advice for each level (not from the AI)
    "relaxed": {"title": "Relaxed and recovered", "mood": "happy",
                "text": "Your heartbeat changes a lot from beat to beat. That usually means your body is calm and well rested. Keep doing what works: regular sleep, exercise and time to talk with the crew.",
                "action": None},
    "balanced": {"title": "Balanced", "mood": "happy",
                 "text": "Your HRV is in the middle. A short break, a glass of water or a few slow breaths can help you stay steady through the day.",
                 "action": "breathe"},
    "strained": {"title": "Your body may be under strain", "mood": "worried",
                 "text": "Your heartbeat is very regular and fast, which can happen with stress, poor sleep or hard work. Try slow breathing for two minutes, and talk to the crew medical officer if you feel unwell.",
                 "action": "breathe"},
}                                                              # end of the levels


def hrv_level(stats):
    """Picks a level from RMSSD. These limits are a rough guide for adults, not a diagnosis."""
    if stats["rmssd"] >= 40:                                   # lots of beat-to-beat change
        return "relaxed"                                       # relaxed
    if stats["rmssd"] >= 20:                                   # a medium amount
        return "balanced"                                      # balanced
    return "strained"                                          # very little change


def send_result(name, beats, real=None):
    """Works out HRV for a list of heartbeat gaps and sends the results to the page."""
    stats = hrv_stats(beats)                                   # do the math
    if stats is None:                                          # not enough beats...
        ui.send_message("hrv_result", {"error": "Not enough heartbeats to check."})  # ...say so
        return                                                 # ...and stop
    level = hrv_level(stats)                                   # pick the level
    step = max(1, len(beats) // 120)                           # keep about 120 points for the graph
    ui.send_message("hrv_result", {                            # send everything to the page
        "name": name, "stats": stats, "level": level,
        "advice": HRV_LEVELS[level], "graph": beats[::step], "real": real,
    })                                                         # end of the message
    mission_log.append({"time": time.strftime("%H:%M"), "hrv_rmssd": stats["rmssd"], "heart_rate": stats["heart_rate"]})  # remember it in the mission log
    print("Heart check:", name, stats, level)                  # show it in the Python tab too


def handle_hrv(sid, data):
    """FOR LATER: a heart sensor (like a MAX30102) sends the astronaut's own heartbeat gaps here."""
    try:                                                       # if anything goes wrong, tell the page
        beats = clean_rr([float(x) for x in data.get("rr", [])])  # the gaps sent by the sensor
        send_result("Your heart sensor", beats)                # check them and send the results
    except Exception as e:                                     # something broke...
        ui.send_message("hrv_result", {"error": (type(e).__name__ + ": " + str(e))[:150]})  # ...send the error


ui.on_message("hrv_check", handle_hrv)                         # when the page sends "hrv_check", run handle_hrv
# ----- REAL DATA: PhysioNet "RR interval time series from healthy subjects" (free, no key, CC BY 4.0) -----
# Credit: Irurzun et al., PhysioNet. https://www.physionet.org/content/rr-interval-healthy-subjects/
import urllib.request                                          # lets Python download files from the internet

PHYSIONET = "https://physionet.org/files/rr-interval-healthy-subjects/1.0.0/"  # the database's web address
physionet_results = []                                         # every adult's results, sorted from lowest to highest HRV
physionet_lock = threading.Lock()                              # makes sure we only download everything once


def download_text(url):
    """Downloads a text file from the internet (gives up after 20 seconds)."""
    request = urllib.request.Request(url, headers={"User-Agent": "Astro911"})  # says who is asking
    with urllib.request.urlopen(request, timeout=20) as answer:  # downloads it (follows redirects by itself)
        return answer.read().decode("utf-8", errors="ignore")  # turns it into text


def find_adults(csv_text):
    """Reads patient-info.csv and keeps people 18 and older."""
    lines = [l for l in csv_text.strip().splitlines() if l.strip()]  # the lines, skipping empty ones
    sep = ";" if ";" in lines[0] else ","                      # the separator: ; or ,
    head = [c.strip().lower() for c in lines[0].split(sep)]    # the column names
    age_col = next((i for i, c in enumerate(head) if "age" in c), -1)  # the "age" column
    id_col = next((i for i, c in enumerate(head) if re.search(r"file|record|id", c)), 0)  # the file name column
    unit = 12 if age_col > -1 and "month" in head[age_col] else 365 if age_col > -1 and "day" in head[age_col] else 1  # years, months or days
    people = []                                                # everyone we can read
    for line in lines[1:]:                                     # for each person...
        cells = line.split(sep)                                # ...their values
        number = re.sub(r"[^0-9]", "", cells[id_col] if id_col < len(cells) else "")  # ...their number, e.g. 401
        if not number:                                         # ...skip broken lines
            continue
        try:                                                   # ...read their age
            age = float(cells[age_col].replace(",", ".")) / unit if age_col > -1 else -1
        except (ValueError, IndexError):                       # ...if the age is missing or strange
            age = -1                                           # ...mark it as unknown
        people.append({"id": number, "file": number.zfill(3) + ".txt", "age": age})  # ...e.g. 401.txt
    adults = [p for p in people if p["age"] >= 18]             # keep the adults
    return adults or people                                    # adults if any, otherwise everyone


def read_beats(text):
    """Turns the file into a list of gaps between heartbeats in ms (up to 5 minutes)."""
    numbers = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)]  # every number in the file
    if numbers and sum(1 for x in numbers if 0 < x < 3) > len(numbers) / 2:  # if they're in seconds...
        numbers = [x * 1000 for x in numbers]                  # ...change them to ms
    beats, total = [], 0                                       # the gaps we keep and their total time
    for x in numbers:                                          # for each number...
        if 300 <= x <= 2000 and total < 5 * 60 * 1000:         # ...keep real heartbeats, up to 5 minutes
            beats.append(round(x))
            total += x
    return beats                                               # give back the gaps


def load_physionet():
    """Downloads every adult's recording once (the first time only) and sorts them by HRV."""
    global physionet_results
    with physionet_lock:                                       # one download at a time
        if physionet_results:                                  # already done...
            return                                             # ...nothing to do
        people = find_adults(download_text(PHYSIONET + "patient-info.csv"))[:12]  # the list of adults (up to 12)
        results = []                                           # what we work out
        for person in people:                                  # for each adult...
            try:                                               # ...one bad file shouldn't stop the rest
                beats = read_beats(download_text(PHYSIONET + person["file"]))  # ...download their heartbeats
                stats = hrv_stats(beats)                       # ...do the HRV math
                if stats:                                      # ...if there were enough beats...
                    results.append({"person": person, "beats": beats, "rmssd": stats["rmssd"]})  # ...keep them
                    print("PhysioNet:", person["file"], "RMSSD", stats["rmssd"])  # ...show it in the Python tab
            except Exception as e:                             # ...if this one failed...
                print("PhysioNet: skipped", person["file"], repr(e))  # ...say so and carry on
        physionet_results = sorted(results, key=lambda r: r["rmssd"])  # lowest HRV first, highest last


def check_real_recording(choice):
    """Picks a real person (highest, middle, lowest HRV, or random) and checks their heartbeats."""
    try:                                                       # if anything goes wrong, tell the page
        load_physionet()                                       # download everyone (first time only)
        if not physionet_results:                              # nobody could be downloaded...
            ui.send_message("hrv_result", {"error": "No recordings could be downloaded. Check the board's internet."})
            return
        if choice == "high":                                   # most relaxed real person
            r = physionet_results[-1]
        elif choice == "low":                                  # most strained real person
            r = physionet_results[0]
        elif choice == "middle":                               # the one in the middle
            r = physionet_results[len(physionet_results) // 2]
        else:                                                  # anyone
            r = random.choice(physionet_results)
        p = r["person"]                                        # who it is
        send_result("PhysioNet person #" + p["id"], r["beats"],  # check their heartbeats and send the results
                    {"id": p["id"], "age": round(p["age"]) if p["age"] >= 0 else None,
                     "rank": choice, "count": len(physionet_results)})
    except Exception as e:                                     # no internet, website down, etc.
        print("PhysioNet problem:", repr(e))                   # show the full problem in the Python tab
        ui.send_message("hrv_result", {"error": "I couldn't download the real recordings (" + (type(e).__name__ + ": " + str(e))[:150] + "). Check the board's internet."})


def handle_hrv_real(sid, data):
    """The page asked for a real recording: download in the background so the page doesn't freeze."""
    threading.Thread(target=check_real_recording, args=(str(data.get("pick", "random")),), daemon=True).start()


ui.on_message("hrv_real", handle_hrv_real)                     # when the page sends "hrv_real", run handle_hrv_real
# ================= END OF HEART CHECK =================

print("Astro911 is running")
App.run()
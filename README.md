# Astro911 · Crew Body & Mind

**An offline AI health assistant for astronauts, built on the Arduino UNO Q for the NASA Space Apps Challenge 2026.**

Long missions are hard on the mind as well as the body: small living spaces, months away from family, a body clock that sees about 16 sunrises a day, and constant pressure. Astro911 gives crew members a private, easy way to check in on how they feel and get practical support, even when Mission Control is far away.

At its center is **ASTRO**, an animated robot assistant powered by a small AI model that runs directly on the board, with no internet needed.

---

## Features

- **Crew check-in:** 13 questions rated from 1 to 10. Each check-in mixes 4 random Body and 4 random Mind questions with 5 fixed safety questions (chest pain, breathing, confusion or numbness, mood, and self-harm).
- **Results:** separate Body and Mind scores, a colored level from Green to Red, recommended next steps, and personal advice from ASTRO.
- **AI agent:** choose "Suggest an exercise for me" and ASTRO picks and starts an exercise on its own using tools.
- **Talk to ASTRO:** type how you feel and get a kind reply with checked, practical tips.
- **Guided breathing:** an animated circle (breathe in 3 s, hold 4 s, breathe out 6 s).
- **5-4-3-2-1 grounding exercise:** a real technique for anxiety and panic.
- **Mental health in space:** 12 written topics, including anxiety, panic, sleep, homesickness, and crew tension.
- **NASA data explorer:** live search of [data.nasa.gov](https://data.nasa.gov) plus published NASA research on astronaut sleep.
- **Voice:** ASTRO reads replies aloud with an optional ElevenLabs voice, or the browser's voice as a backup.
- **Keyboard control:** no touch screen needed.

---

## Safety design

A small AI model can make mistakes, so the important parts never depend on it:

- **Urgent warnings** for chest pain, breathing trouble, confusion, and self-harm come from fixed rules in the code.
- **Self-harm protection:** if someone reports or types about self-harm, the AI is skipped and a fixed, caring message points them to a crewmate or someone near them.
- **Checked tips:** chat advice comes from a reviewed tip library. The AI only writes a short, kind opening sentence, and bad ones are filtered out.
- **Not a doctor:** ASTRO never diagnoses or suggests medicines, and points people to the crew medical officer or crew psychologist.

> ⚠️ Astro911 is a student prototype and is **not** a medical device. The questions and tips have not been reviewed by medical professionals.

---

## Hardware

| Part | Purpose |
|---|---|
| Arduino UNO Q (4 GB RAM) | A small computer with a microcontroller plus a Linux processor that runs Python, the web page, and the AI |
| USB-C hub with HDMI | Connects the screen, keyboard, and power |
| HDMI screen (5–7 inch) | Shows the app |
| USB keyboard | Controls everything |
| Battery pack (5 V, 3 A, USB-C) | Makes the device portable |
| Speaker (optional) | Reads ASTRO's replies aloud |

---

## Project structure

```
Astro911/
├── app.yaml               # App Lab project settings (lists the bricks)
├── assets/
│   ├── index.html         # The screens and app logic (JavaScript)
│   ├── style.css          # The space-themed design and animations
│   ├── nasa.js            # The NASA data explorer screen
│   └── libs/
│       └── socket.io.min.js  # Lets the page talk to Python
├── python/
│   └── main.py            # The "brain": AI, agent tools, safety rules, NASA and ElevenLabs APIs
└── sketch/
    └── sketch.ino         # Optional code for physical buttons (not needed with a keyboard)
```

Every line of code has a comment explaining what it does.

---

## How it works

```
Keyboard ──► index.html (web page) ◄──socket.io──► main.py (Python on the UNO Q)
                                                     ├── LLM brick: Qwen 3.5 0.8B (offline AI)
                                                     ├── data.nasa.gov API (NASA datasets)
                                                     └── ElevenLabs API (voice, optional)
```

---

## Setup

1. **Open the project** in [Arduino App Lab](https://www.arduino.cc/) on your UNO Q.
2. **Add the bricks:** click **+** next to **Bricks** and add **WebUI - HTML** and **Large Language Model (LLM)**.
3. **Download the AI model:** in the LLM brick's **AI models** tab, choose **Qwen 3.5 0.8B**. It's the model on the UNO Q that supports tools. The board needs internet for this one-time download.
5. **Run the app:** click **Run** and wait for `ASTRO's AI is loaded and ready` in the **Python** tab.
6. **Open the page:** go to `http://<board-IP>:7000` in a browser and click once on the page to allow sound.

---

## Keyboard controls

| Screen | Keys |
|---|---|
| Anywhere | **Esc** = home |
| Menus | **↑ ↓** move · **Enter** choose · **Backspace** back |
| Check-in | **1–9**, or **0** for 10 · **← →** change · **Enter** next · **Backspace** previous |
| Talk to ASTRO | Type · **Enter** send · **↑ ↓** example messages |
| Breathing | **Enter** stop |
| Grounding | **Enter** move to next one· **Space** to fill in |
| NASA data | Type · **Enter** search · **↑ ↓** example searches |

---


## Data

- **PhysioNet heart data (live):** Astro911 uses real heartbeat recordings from the open PhysioNet database "RR interval time series from healthy subjects." It's free, with no key or sign-up needed. The Arduino downloads the adult recordings, works out each person's heart rate and heart rate variability (HRV), and shows the most relaxed, middle, most strained or a random real person.
  - Dataset: https://www.physionet.org/content/rr-interval-healthy-subjects/
  - Files used: https://physionet.org/files/rr-interval-healthy-subjects/1.0.0/
- **HRV analysis:** the app calculates heart rate, RMSSD, SDNN and pNN50 (the same time-domain measures used in NeuroKit2 and pyHRV) in plain Python on the board, with no cloud.
- **Own heart sensor (future):** a MAX30102 finger sensor or a smartwatch could send the astronaut's own heartbeats into the same code, so ASTRO can notice stress early.
- **Credit:** Irurzun et al., "RR interval time series from healthy subjects," PhysioNet, CC BY 4.0.

---

## Future improvements

- Voice conversations with a USB microphone
- Heart rate, blood oxygen, and temperature sensors
- Private crew profiles and saved history
- A fully offline voice (such as Piper)
- A stronger board for a larger, more accurate AI model
- Access to NASA's Life Sciences Data Archive
- Expert medical review, more languages, and a enclosed  box to keep everything in

## Challenges for real spaceflight

Before flying, the device would need safety certification (materials, battery, electrical interference), protection from radiation and heat, secure mounting for microgravity, a fully offline design, encrypted private health data, and long testing in space-like conditions.

---

## Built with

Arduino UNO Q · Arduino App Lab · Python · HTML · CSS · JavaScript · Socket.IO · Qwen 3.5 0.8B · PhysioNet heart data 

## Acknowledgments

Created for the **NASA Space Apps Challenge 2026**. NASA data and research are used under NASA's open data policy. This project is not endorsed by NASA.



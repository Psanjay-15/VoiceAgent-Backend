# Agentic Voice Assistant

A FastAPI backend for a low-latency voice agent. It powers browser-based voice conversations using streaming speech-to-text, LLM responses, streamed text-to-speech audio, LangGraph business-action routing, Google Calendar scheduling, SMTP admin summaries, MongoDB user authentication, and WebSocket-based real-time communication.

## Table of Contents

- [Problem Statement](#problem-statement)
- [Solution](#solution)
- [Features](#features)
- [Architecture](#architecture)
- [Request Flow](#request-flow)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Server](#running-the-server)

## Problem Statement

Real Estate businesses often lose leads because initial qualification and meeting coordination depend on manual follow-up. A potential buyer or renovation customer may ask about budget, location, BHK, timeline, admin contact, or meeting availability, but human teams cannot always respond instantly.

The goal of this server is to support a voice-first AI assistant that can:

- Talk with users in real time
- Understand real estate and renovation requirements
- Keep latency low enough for a smooth voice conversation
- Decide when a business action is needed
- Schedule online meetings with an admin
- Send final conversation summaries to the admin
- Use the logged-in user's verified email instead of repeatedly asking for it

## Solution

This backend implements a real-time voice-agent pipeline:

```text
Browser microphone -> WebSocket -> STT -> LLM -> LangGraph actions -> TTS -> WebSocket audio
```

The user speaks in the browser. Audio is streamed to the backend over a WebSocket. The backend sends the audio to a speech-to-text provider, accumulates final transcripts, detects the end of a user turn, asks the LLM for a response, streams that response back to the frontend, and converts speakable chunks into audio.

For business actions, a LangGraph workflow classifies the conversation turn and queues the correct action:

- `online_meet` for Google Calendar meeting requests
- `in_person_meet` for physical meeting or site visit requests
- `admin_followup` for contact/admin follow-up requests
- `none` for normal qualification conversation

At the end of the call, queued actions are executed and a final admin summary is sent.

## Features

- Real-time browser voice conversation over FastAPI WebSockets
- Streaming STT provider abstraction with Deepgram support
- Streaming LLM provider abstraction with Gemini and OpenAI support
- Streaming TTS provider abstraction with Deepgram support
- Low-latency TTS chunking for faster first spoken response
- LangGraph-based business action routing
- Google Calendar OAuth integration for online meeting scheduling
- Google Meet link generation through Calendar API
- SMTP email integration for final admin summaries
- Logged-in user email passed into the voice session as verified meeting email
- Conversation summary generation for admins

## Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Agentic Real Estate Voice Assistant                      │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌──────────────────┐
                              │  React/Vite UI   │
                              │  Auth + Bot Page │
                              └────────┬─────────┘
                                       │
                      HTTP auth        │ WebSocket audio + JSON
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                               FastAPI Server                               │
│                                                                            │
│  ┌─────────────────┐       ┌─────────────────────┐      ┌────────────────┐ │
│  │ Auth API        │       │ WebSocket /ws       │      │ Google OAuth   │ │
│  │ signup/login    │       │ voice session       │      │ calendar token │ │
│  └────────┬────────┘       └──────────┬──────────┘      └───────┬────────┘ │
│           │                           │                         │          │
│           ▼                           ▼                         ▼          │
│  ┌─────────────────┐       ┌─────────────────────┐      ┌────────────────┐ │
│  │ MongoDB         │       │ TranscriptionService│      │ Calendar Tool  │ │
│  │ users           │       │ turn detection      │      │ Meet invite    │ │
│  └─────────────────┘       └──────────┬──────────┘      └────────────────┘ │
│                                       │                                    │
│                                       ▼                                    │
│                           ┌─────────────────────┐                          │
│                           │ LLMService          │                          │
│                           │ response streaming  │                          │
│                           └──────────┬──────────┘                          │
│                                      │                                     │
│                  ┌───────────────────┼───────────────────┐                 │
│                  ▼                   ▼                   ▼                 │
│        ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐   │
│        │ STT Provider    │  │ LLM Provider    │  │ TTS Provider        │   │
│        │ Deepgram        │  │ Gemini/OpenAI   │  │ Deepgram audio      │   │
│        └─────────────────┘  └────────┬────────┘  └─────────────────────┘   │
│                                      │                                     │
│                                      ▼                                     │
│                           ┌─────────────────────┐                          │
│                           │ LangGraph Agent     │                          │
│                           │ action decision     │                          │
│                           └──────────┬──────────┘                          │
│                                      │                                     │
│                     ┌────────────────┴────────────────┐                    │
│                     ▼                                 ▼                    │
│              ┌──────────────┐                  ┌──────────────┐            │
│              │ Google Meet  │                  │ SMTP Summary │            │
│              │ scheduling   │                  │ to admin     │            │
│              └──────────────┘                  └──────────────┘            │
└────────────────────────────────────────────────────────────────────────────┘
```

## Request Flow

### Voice conversation flow

```text
User clicks Start Talking
-> frontend opens WebSocket /ws?token=<jwt>
-> backend accepts session and extracts logged-in user email from JWT
-> frontend streams microphone audio
-> backend streams audio to STT provider
-> STT returns interim and final transcripts
-> backend waits for short silence to detect end of turn
-> LangGraph checks whether the turn needs a business action
-> LLM generates a short voice-friendly response
-> TTS synthesizes response chunks
-> backend streams audio bytes to frontend
-> frontend plays audio
```

## Tech Stack

| Component          | Technology                             |
| ------------------ | -------------------------------------- |
| Web framework      | FastAPI                                |
| Realtime transport | WebSocket                              |
| ASGI server        | Uvicorn                                |
| Agent workflow     | LangGraph                              |
| LLM providers      | Gemini, OpenAI                         |
| STT providers      | Deepgram, OpenAI stub, ElevenLabs stub |
| TTS providers      | Deepgram, OpenAI stub, ElevenLabs stub |
| Database           | MongoDB                                |
| Auth               | JWT, bcrypt                            |
| Calendar           | Google Calendar API, Google OAuth      |
| Email              | SMTP                                   |

## Prerequisites

Install or create accounts for:

- Python 3.11+
- MongoDB Atlas or local MongoDB
- Deepgram API key
- Gemini API key or OpenAI API key
- Gmail SMTP app password, or another SMTP provider
- Google Cloud OAuth client with Calendar API enabled

## Installation

From the server folder:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the Server

Local development:

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{ "status": "healthy" }
```

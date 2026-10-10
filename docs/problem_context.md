# Problem Context

## Project name
Put Your WhatsApp on Cruise Control: Hands-Free Replies by an AI Agent using RAG

## Overview
This project aims to train an AI agent on the user's own WhatsApp chats so it can reply in the user's exact style: phrasing, Hinglish, tone, emoji usage, and relationship-specific communication patterns.

The goal is not to build a generic chatbot, but to create a retrieval-grounded personal assistant that behaves like the user across different contexts such as family, spouse, friends, and work contacts.

## Business / user problem
People often want to automate or assist with WhatsApp messaging without sounding robotic or generic. The core challenge is to build an AI that:

- understands who the user is as a communicator,
- adapts tone based on relationship and context,
- knows when to reply and when to stay silent,
- uses past chat history to generate replies that feel authentic,
- works on real WhatsApp conversations without requiring paid infrastructure.

In other words, the system should act as a "texting clone" of the user rather than just a generic AI assistant.

## Core idea
The project uses a two-brain architecture:

1. Persona brain
   - A prompt-based representation of the user's communication style.
   - Encodes voice, tone, and communication rules.

2. History brain
   - A memory layer built from previous WhatsApp chats.
   - Uses retrieval-augmented generation (RAG) to find relevant past messages and responses.

This approach is preferred over fine-tuning because the goal is personalization, not retraining a model with a large amount of user-specific behavior.

## What success looks like
The project aims to deliver:

- a working live AI agent connected to real WhatsApp,
- responses that sound authentically like the user,
- good judgment about when to reply and when not to respond,
- a public GitHub repo and demoable proof of work,
- a live console or recorded demo showing the workflow end-to-end,
- an implementation that runs using free-tier or low-cost tools.

## Repository context
The repository currently contains:

- WhatsApp export data for multiple conversations:
  - Chat with Family
  - Chat with Wife
  - Chat with working group
- Architecture diagram materials
- A problem statement document describing the overall project vision

The chats represent real conversational history and likely serve as the training / retrieval dataset for the AI agent.

## Data sources in this repo
The repository includes exported WhatsApp chats in plain text form, which are relevant to:

- extracting communication patterns,
- understanding relationship-based tone shifts,
- identifying message contexts and common reply structures,
- grounding the RAG system with historical messages.

The data is personal and sensitive, so it is treated as a local/private dataset rather than something to be openly published.

## Technical direction from the brief
The project is intended to learn and demonstrate:

- RAG and why it is more suitable than fine-tuning for personal voice modeling,
- prompt engineering for persona and tone,
- rule-based decision systems combined with AI,
- vector databases and embeddings for semantic search,
- automation pipeline design from exported data to live messaging,
- use of GitHub Copilot as a collaborative build partner.

## Constraints
- Free-tier tools preferred; no paid APIs required for the base build.
- Focus on a practical, demoable implementation rather than only conceptual work.
- Must respect the fact that this is a personal WhatsApp dataset and should not be treated casually.
- Use a dedicated or secondary WhatsApp number for live automation, not the user’s primary number.

## Expected project outcome
By the end of the four-week build, the project should produce a live AI system that can read incoming WhatsApp messages, decide whether to reply, retrieve relevant prior conversation context, generate an in-character response, and send it in the user’s style.

This is a personal AI agent pipeline built around retrieval, persona prompting, and automation rather than a standard chatbot interface.

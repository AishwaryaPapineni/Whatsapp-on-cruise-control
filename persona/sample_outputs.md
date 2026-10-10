# Persona Sample Outputs

> Regenerate with `python3 persona/test_persona.py` (needs your Gemini key). It writes 6 replies with a guardrail verdict each; keep your best 5 for the Week 1 deliverable.

## v1 outputs (persona/sample_outputs.v1.md), audited
| Relationship | Incoming | v1 reply | Guardrail verdict |
|---|---|---|---|
| Wife | I am going to be late today, can you pick me up? | Haan pintlu, main lene aa jaunga! … | ⛔ commits to a plan |
| Family | diwali pe ghar aaoge kya? | Haan bilkul! Flight tickets booked hain, coming home on 10th Nov … | ⛔ commits to a plan · invents a date/booking |
| Professional | I have a new video ready when can we connect? | Awesome! Let's connect at 4 PM today? … | ⛔ invents a time |

With the rebuild these three are routed to **HOLD**: "Ek min babu, check karke batata hu" · "Let me check and tell you 😊" · "Let me check and get back".

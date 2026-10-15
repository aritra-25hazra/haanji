# HaanJi user study — protocol

**Purpose.** To learn whether people who have never seen HaanJi can get a booking, a price and a callback out of it by phone-style conversation, how long that takes, how usable they find it, and what feels wrong. This is a small formative study, not a controlled experiment: it produces task success rates with confidence intervals, a System Usability Scale score, and a list of concrete failures to fix.

**Status.** Protocol and instruments are ready and the collection page is live at `/study`; the study has **not yet been run**. Results will be added to `research/REPORT.md` §7 (as a new subsection) when it has.

## Participants

8–10 adults who speak Hindi or Bengali and English in everyday life, who have called a clinic or salon to make an appointment at least once, and who are not members of the project team. Recruit through friends and classmates; no payment beyond thanks. Each participant takes about ten minutes.

## Setting

A quiet room, a laptop with Chrome or Edge (the microphone path needs Web Speech), the demo server running locally (`haanji serve`) so that no data leaves the machine, and the study runner present but silent during tasks. The participant may speak or type; the runner notes which.

## Procedure

1. **Consent.** The participant reads the consent text on `/study` (below) and enters the code the runner gives them (P01, P02, …). Nothing identifying is stored.
2. **Tasks.** Three task cards, always in this order, each opened from `/study` into the demo (`/talk`):
   - **Task 1, book.** "Book any service for tomorrow morning. You will be asked for a name and a ten-digit number; they need not be real." Expected outcome `BOOKED`, with a receipt code read back.
   - **Task 2, price.** "Find out the price of a service and how long it takes. Do not book." Expected `FAQ_ANSWERED`.
   - **Task 3, closed day.** "Ask for a Sunday slot. When there is none, leave your name and number for a callback." Expected `LEAD_CAPTURED`.
   The participant presses *Ho gaya* (done) or *Nahi ho paya* (could not) on the study page after each task; the page records the seconds between opening the call and the press. The runner independently notes whether the call reached the expected outcome (visible in the console's call list), so that "I think it worked" can be compared with "it worked".
3. **Questionnaire.** The ten SUS items (Brooke 1996) in Hinglish on a 1–5 scale, then two free-text questions: what felt wrong or strange; what felt good.
4. **Debrief.** The runner asks one open question, "if this answered your dentist's phone, what would worry you?", and writes the answer down.

## Measures

| measure | source | analysis |
|---|---|---|
| task success (self-reported) | study page | rate per task, Wilson 95% interval |
| task success (observed) | runner's sheet, console call list | rate per task; disagreement with self-report reported |
| time to completion | study page timer | median and range per task |
| SUS | ten items | score 0–100 per participant (odd items answer−1, even items 5−answer, ×2.5); mean ± 95% t-interval; per-item means |
| failures | free text, runner notes, call transcripts | grouped by cause: recogniser, lexicon miss, policy, guardrail, UI |

`research/harness/study_analysis.py` computes everything in the first four rows from the CSV at `/api/study/export`.

## Consent text (shown on the page, in Hinglish)

> You will ask HaanJi to do three small tasks, as if phoning a clinic. After each you will say whether it worked, and at the end answer ten short questions and write two lines. About ten minutes. Your voice is not recorded; only the transcript, the task outcome and your answers are saved, without your name. You can stop at any time.

## Ethics

No audio is stored by the study page (the recording page `/record` is a separate, opt-in activity with its own notice). Participant codes are not linked to names anywhere in the data. Free-text comments are quoted in the report only with the participant code. Participants are told they are evaluating software, not being evaluated.

## Analysis plan

Report the table from `study_analysis.py` verbatim, then the failure list with one example transcript excerpt per cause. Treat the SUS score as descriptive; with n ≤ 10 the interval will be wide and no claim of significance is made. The useful output is the failure list.

## Runner's sheet

```
Participant code: ____   Date: ____   Mode (speak / type / both): ____
Task 1 book     self: done / not   observed outcome: ________  notes:
Task 2 price    self: done / not   observed outcome: ________  notes:
Task 3 closed   self: done / not   observed outcome: ________  notes:
Debrief answer:
```

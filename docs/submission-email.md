**To:** careers-uobinterns@bristol.ac.uk
**Subject:** Pfizer Hackathon Submission

Dear AI Studio and Newpage team,

Please find my submission for the Second Brain for Managers challenge.

**Prototype:** https://github.com/bilanabdi2345-bot/offline-agents
**Demo video:** [paste your video link here]

**Second Brain** is a private assistant for a manager's scattered notes. It runs entirely on the laptop, with a local AI model.

The moment it improves is preparing for a 1:1. With one click, it pulls together what happened last time, open and overdue actions, what has changed, and what to follow up on. Every point links to the exact note it came from.

How it keeps the One Rule:
- **Nothing leaves the device.** The model runs locally, and a network guard blocks every outside connection. Users can test this themselves: there is a "Try to break the rule" button, a live check using macOS's own lsof tool, and it keeps working with Wi-Fi off.
- **No copies.** There is no database or search index. Notes are read fresh for each question and then dropped. The app is blocked from writing any file, and the model is unloaded after each answer.
- **In control.** Notes are split into compartments that the user switches on and off. A switched-off compartment is never opened.
- **Honest.** If nothing matches, the AI isn't asked at all. Warnings for overdue, unfinished, out-of-date and private notes come from code. Each answer shows a confidence level and explains where it came from.

It works across five kinds of content: notes, action lists, calendar files and two kinds of saved links. It was tested with made-up sample notes.

Kind regards,
Bilan Salim
BSc Biochemistry, University of Bristol

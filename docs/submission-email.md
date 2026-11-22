**To:** careers-uobinterns@bristol.ac.uk
**Subject:** Pfizer Hackathon Submission

Dear AI Studio and Newpage team,

Please find my submission for the Second Brain for Managers challenge.

**Prototype:** https://github.com/bilanabdi2345-bot/offline-agents
**Demo video:** [paste your video link here]

**Codicilix** is a private second brain for a manager's scattered notes. It runs entirely on the laptop, with a local AI model.

The moment it improves is coming back after the holidays. In our demo, Tommy, a manager in Pfizer's AI Studio, returns on 5 January to a check-in with his two interns. With one click, Codicilix finds everything he wrote about them before the break, including a handwritten note his Mac reads itself, lists open actions correctly marked overdue, and suggests what to ask. Every point links to the exact note it came from.

How it keeps the One Rule:
- **Nothing leaves the device.** The model runs locally, and a network guard blocks every outside connection. Users can test this themselves: there is a "Try to break the rule" button, a live check using macOS's own lsof tool, and it keeps working with Wi-Fi off.
- **No copies.** There is no database or search index. Notes are read fresh for each question and then dropped. The app is blocked from writing any file, and the model is unloaded after each answer.
- **In control.** Notes are split into compartments that the user switches on and off. A switched-off compartment is never opened.
- **Honest.** If nothing matches, the AI isn't asked at all. Warnings for overdue, unfinished, out-of-date and private notes come from code. Each answer shows a confidence level and explains where it came from.

It works across five kinds of content: notes, action lists, calendar files and two kinds of saved links. It was tested with made-up sample notes.

Kind regards,
Bilan Salim
BSc Biochemistry, University of Bristol

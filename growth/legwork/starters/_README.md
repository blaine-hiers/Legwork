# The starters — edit these, not the Python

One file, one trade. **Adding a file adds a starter**; there is nothing to
register and nothing to restart on the server side beyond reopening the app.

The rule these exist to serve: *every conversation happens in the other
person's own vocabulary*. **When an owner uses a different word for a step,
come back here and change it.** A starter that still says "work order" to a
company that says "ticket" is worse than an empty form, because it says you
were listening to somebody else.

## What a file looks like

```json
{
  "key": "hvac-service-call",
  "order": 10,
  "title": "A service call, start to finish",
  "industry": "Heating and air",
  "blurb": "The phone rings and something is broken. Everything to getting paid.",
  "asks": "Walk me through what happens from the phone ringing to the invoice.",
  "sample": "From: ...\n\nthe kind of email this trade actually gets\n",
  "steps": [
    {
      "name": "Take the call and write it down",
      "who": "Whoever picks up",
      "system": "Notepad, then the software",
      "minutes": 6,
      "handling": ["retyped", "paper"],
      "note": "Usually written on a pad first because the caller is still talking."
    }
  ]
}
```

- **`key`** — must be unique. Two files claiming the same key: the first wins
  and the second is reported on screen.
- **`order`** — low numbers first in the picker. Missing means 500, i.e. last.
- **`asks`** — the question you actually say out loud to open the conversation.
  It shows above the sheet.
- **`sample`** — the kind of message this trade really gets. It is what the
  **Use the sample** button pastes into the live demo. Make it realistic and
  make it messy; a tidy sample proves nothing.
- **`minutes`** — per run, and it is a guess for the owner to correct.

## `handling` — the only list with fixed values

These are what happens to the *information* in that step. Use these exact
words; anything else is dropped:

| Word | Means |
|---|---|
| `retyped` | Somebody types it in again somewhere else |
| `looked-up` | Somebody has to go and find something |
| `written` | The same document or email gets written again |
| `chased` | Somebody has to chase a person |
| `paper` | It's on paper, a whiteboard, or a text message |
| `checked` | Somebody checks somebody else's work |
| `scheduled` | Somebody works out who goes where |
| `decided` | Somebody makes a judgement call |

They come from `patterns.py`, which is where the arithmetic behind each one
lives. Adding a ninth kind of handling **is** a code change — that one is a
pattern with a saving range and an argument attached, not a label.

## What you cannot put in a file

**`runs_per_month`.** It is forced to zero and a file that sets one is reported
on the screen rather than obeyed. How often something happens is the one number
that has to come out of the owner's mouth: a seeded volume would put a figure
nobody stated onto a sheet with their company name at the top, and every number
downstream is built on it.

That is also why a fresh starter's sheet says **0 hours addressable** until you
start asking. It is not broken. It is refusing to make something up.

## If you break one

The app still starts. The bad file is dropped and what was wrong with it is on
the screen, not in a log — a starter that vanished quietly looks exactly like
one nobody ever wrote.

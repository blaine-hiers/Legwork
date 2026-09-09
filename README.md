# Legwork

Sit down with somebody who runs a business, and in ten seconds have a workflow
they recognise on the screen. Change every number as they talk. Then paste in
their actual mess — the customer's email, the voicemail somebody typed up, the
text from site — and watch it come out the other side as a filled-in work
order.

It is not a slideshow. The same code runs on whatever gets pasted in, including
an email the owner opens themselves in front of you. That is the entire point.

```
py growth/legwork/app.py          # opens in your browser
py run_all_tests.py               # 102 tests
```

Windows: double-click `run.cmd`.

## The two halves

**The sheet.** Pick a trade and a workflow appears, already populated with steps
somebody in that trade would recognise. Every step is scored by what happens to
the *information* in it — typed in twice, hunted for, written down again,
chased, on paper, checked, scheduled, decided. Each of those has a pattern
behind it that knows what the automated version looks like and what it takes
off the step.

**The live demo.** Paste the real thing. It pulls the fields out, writes the
work order, or lists what is late with the follow-up already drafted.

## Three things are enforced in code, not promised

**No saving is ever a single figure.** Patterns compose by what each one leaves
for the next rather than adding up, every step is squeezed by a ceiling so
nothing can read as 100%, and a guard raises the range rather than letting it
collapse to a point.

**Nothing turns into money unless you state an hourly cost.** A dollar figure on
an invented rate is a guess with a dollar sign on it.

**One of the eight patterns says no.** A judgement call stays with the person.
That is what makes the other seven credible in the room — a tool where
everything is automatable is a tool nobody believes.

The demo also reports **what it could not find** beside what it found, and says
out loud that it catches missing and malformed fields but never *wrong* ones.

## The starters are files, not code

`growth/legwork/starters/*.json` — one file per trade, edited in a text editor.
Adding a file adds a starter; there is nothing to register.

That matters more than it sounds. The rule these serve is that every
conversation happens in the other person's vocabulary, and "when they use a
different word, change the template" only actually happens if changing it
doesn't mean editing Python.

A starter file **cannot carry a volume** — `runs_per_month` is forced to zero
and the attempt is reported on screen, because how often something runs is
theirs to say, not the template's to assume. A broken file is dropped with its
reason on the screen rather than in a log.

Sample data in the starters uses `.example` domains, which are reserved by
RFC 2606 and can never resolve.

## Layout

```
_shared/           server, storage and design system (vendored — see below)
growth/legwork/    the app
tests/             102 tests, mirroring the app tree
```

`_shared/` is vendored from a larger private workspace of about twenty of these
apps that share one server base, one storage layer and one visual language. The
two-level `growth/…` path is not decoration: the folder an app sits in decides
its colour, and the test tree mirrors the app tree exactly. Its comments
occasionally mention sibling apps that are not in this repo.

`tests/test_publishable.py` guards the seam between that private workspace and
this one — it fails if a copied file brings private fixture data back with it.

No dependencies, no installer, no network. Standard library only.

## Licence

MIT. See [`LICENSE`](LICENSE).
